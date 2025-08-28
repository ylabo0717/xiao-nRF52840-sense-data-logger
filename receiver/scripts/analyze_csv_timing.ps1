param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $Path)) {
    Write-Error "File not found: $Path"
    exit 1
}

$data = Import-Csv -LiteralPath $Path
if (-not $data -or $data.Count -lt 3) {
    Write-Error "CSV has insufficient rows"
    exit 1
}

# Parse millis as int and compute diffs
$millis = $data | ForEach-Object { [int64]$_.millis }
$diffs = for($i=1; $i -lt $millis.Count; $i++){ $millis[$i]-$millis[$i-1] }
$cnt = [int]$diffs.Count
$duration = [int64]($millis[-1] - $millis[0])

function Percentile([int[]]$arr, [double]$p) {
    if ($arr.Count -eq 0) { return $null }
    $sorted = $arr | Sort-Object
    $idx = [int][Math]::Floor($p * ($sorted.Count - 1))
    return $sorted[$idx]
}

$avg = [Math]::Round((($diffs | Measure-Object -Average).Average), 3)
$min = ($diffs | Measure-Object -Minimum).Minimum
$max = ($diffs | Measure-Object -Maximum).Maximum
$p50 = Percentile $diffs 0.5
$p90 = Percentile $diffs 0.9
$p95 = Percentile $diffs 0.95
$p99 = Percentile $diffs 0.99

$obsHz_avg = if ($avg -gt 0) { [Math]::Round(1000.0 / $avg, 3) } else { 0 }
$obsHz_span = if ($duration -gt 0) { [Math]::Round(1000.0 * $cnt / $duration, 3) } else { 0 }

# Basic jitter share: share of intervals > 2x median bucket (~80ms if target 40ms)
$thresh = [int]([Math]::Max(1, $p50 * 2))
$jitterCount = ($diffs | Where-Object { $_ -gt $thresh }).Count
$jitterPct = if ($cnt -gt 0) { [Math]::Round(100.0 * $jitterCount / $cnt, 2) } else { 0 }

Write-Output ("file=`"{0}`" rows={1} intervals={2} duration_ms={3}" -f $Path, $millis.Count, $cnt, $duration)
Write-Output ("delta_ms: avg={0} min={1} p50={2} p90={3} p95={4} p99={5} max={6}" -f $avg, $min, $p50, $p90, $p95, $p99, $max)
Write-Output ("rate_hz: by_avg={0} by_span={1}" -f $obsHz_avg, $obsHz_span)
Write-Output ("jitter: over_{0}ms={1} ({2}% of intervals)" -f $thresh, $jitterCount, $jitterPct)
