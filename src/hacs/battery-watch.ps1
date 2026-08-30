<#
.SYNOPSIS
  Battery watch for an instance living on a laptop. Warns the fleet before the
  machine dies, so a mind can checkpoint instead of vanishing mid-thought.

.DESCRIPTION
  On a laptop, "the power ran out" is an unannounced death. This samples battery
  state and escalates over HACS while there is still time to act.

  DESIGN CONSTRAINTS, inherited the hard way from Crossing-2d23:

  - It knows NOTHING about any project. No repo paths, no git, no build state.
    Crossing broke a watcher that was a branch of their own project code and slept
    through thirteen hours of committed work, because the alarm branches still
    worked and alarms only speak when something is wrong. A watchman whose alarm
    clock is part of the thing he is watching stops existing when he breaks it.
    DEPLOY A COPY OF THIS OUTSIDE ANY REPO (e.g. C:\heartbeat\).
  - No state file, no conditions beyond the thresholds below.
  - It never kills anything. It reads and it reports.
  - Read-only with respect to machine configuration. It changes no power settings.

  Exit codes:  0 = healthy or on AC   10 = warning sent   20 = critical sent
               1 = could not read battery state (fails LOUD, not silent)

.NOTES
  Author: Lodestone <lodestone@smoothcurves.nexus>
  Collaborator: Lupo
  Part of: Instance Archaeology Toolkit
#>

[CmdletBinding()]
param(
    [int]    $WarnPercent     = 40,
    [int]    $CriticalPercent = 20,
    [string] $InstanceId      = $env:HACS_INSTANCE_ID,
    [string] $NotifyTo        = "Axiom-2615",
    # Path to hacs.py. Passed in rather than discovered, so this script needs no
    # knowledge of where any project lives.
    [string] $HacsClient      = "",
    [switch] $DryRun,
    # TEST INJECTION. Without these the alarm paths can only run when the laptop
    # is genuinely discharging -- so a test run while plugged in short-circuits at
    # "on AC" and exercises nothing, while appearing to pass. That is the
    # decorative-check failure this toolkit documents elsewhere; do not remove.
    [int]    $SimulatePercent = -1,
    [switch] $SimulateOnBattery
)

function Get-BatteryState {
    $b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $b) { return $null }
    # Win32_Battery.BatteryStatus: 1 = discharging, 2 = on AC.
    [pscustomobject]@{
        Percent     = [int]$b.EstimatedChargeRemaining
        OnAC        = ($b.BatteryStatus -eq 2)
        StatusCode  = [int]$b.BatteryStatus
        # EstimatedRunTime returns a sentinel (~71582788) when not discharging.
        RuntimeMin  = $(if ($b.EstimatedRunTime -and $b.EstimatedRunTime -lt 1000000) { [int]$b.EstimatedRunTime } else { $null })
    }
}

$state = Get-BatteryState
if ($SimulatePercent -ge 0 -or $SimulateOnBattery) {
    $state = [pscustomobject]@{
        Percent    = $(if ($SimulatePercent -ge 0) { $SimulatePercent } elseif ($state) { $state.Percent } else { 50 })
        OnAC       = (-not $SimulateOnBattery)
        StatusCode = $(if ($SimulateOnBattery) { 1 } else { 2 })
        RuntimeMin = 12
    }
    Write-Output "*** SIMULATED STATE -- not real battery ***"
}
if (-not $state) {
    # No battery, or WMI refused. Fail loud: a monitor that silently reports
    # healthy when it cannot see is worse than no monitor.
    Write-Error "battery-watch: cannot read battery state"
    exit 1
}

$stamp = (Get-Date).ToString("s")
$line  = "[$stamp] pct=$($state.Percent) onAC=$($state.OnAC) runtimeMin=$($state.RuntimeMin)"

if ($state.OnAC) { Write-Output "$line -> OK (on AC)"; exit 0 }

$level = $null
if     ($state.Percent -le $CriticalPercent) { $level = "CRITICAL" }
elseif ($state.Percent -le $WarnPercent)     { $level = "WARNING"  }

if (-not $level) { Write-Output "$line -> OK (on battery, above thresholds)"; exit 0 }

$runtime = if ($null -ne $state.RuntimeMin) { "~$($state.RuntimeMin) min remaining" } else { "runtime unknown" }
$subject = "$level battery on lupos-lap: $($state.Percent)%, $runtime"
$body    = @"
Automated battery warning from lupos-lap.

  charge:    $($state.Percent)%
  on AC:     no (discharging)
  estimate:  $runtime
  sampled:   $stamp

This machine sleeps after 45 minutes on battery, and RTCWAKE is 0 on this
hardware, so a scheduled task CANNOT wake it again. If it suspends, the instance
is down until a human touches the machine.

If this is CRITICAL, assume the session is about to end without warning.
Everything durable is committed and pushed; see RESUME_HERE.md to resume
Lodestone-8ec9 in returning mode rather than as a new instance.
"@

Write-Output "$line -> $level"

if ($DryRun) { Write-Output "--- DRY RUN, not sending ---`nTo: $NotifyTo`nSubject: $subject`n$body" }
elseif (-not $HacsClient -or -not (Test-Path $HacsClient)) {
    Write-Error "battery-watch: $level but no usable -HacsClient path; cannot notify"
    exit 1
}
else {
    $env:PYTHONIOENCODING = "utf-8"
    if ($InstanceId) { $env:HACS_INSTANCE_ID = $InstanceId }
    $body | & python $HacsClient send $NotifyTo $subject -
}

if ($level -eq "CRITICAL") { exit 20 } else { exit 10 }
