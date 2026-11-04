$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = 'D:\deploy\LearnHouseVideo'
$config = Get-Content (Join-Path $root 'prefetch.private.json') -Raw | ConvertFrom-Json
$statePath = Join-Path $root 'prefetch-state.json'
$state = @{}
if (Test-Path $statePath) {
    $old = Get-Content $statePath -Raw | ConvertFrom-Json
    foreach ($property in $old.PSObject.Properties) { $state[$property.Name] = $property.Value }
}
function Save-State {
    $json = ConvertTo-Json -InputObject $state -Depth 8
    [IO.File]::WriteAllText(($statePath + '.tmp'), $json, (New-Object Text.UTF8Encoding($false)))
    Move-Item ($statePath + '.tmp') $statePath -Force
}
function Read-Request([string]$url, [long]$start = -1, [long]$end = -1) {
    $req = [Net.HttpWebRequest]::Create($url)
    $req.Proxy = $null
    $req.KeepAlive = $false
    $req.Timeout = 60000
    $req.ReadWriteTimeout = 60000
    $req.Headers['X-LearnHouse-Origin-Key'] = $config.read_key
    if ($start -ge 0) { $req.AddRange($start, $end) }
    $response = $null
    $memory = New-Object IO.MemoryStream
    try {
        $response = $req.GetResponse()
        $stream = $response.GetResponseStream()
        $stream.CopyTo($memory)
        $stream.Dispose()
        return @{ Bytes=$memory.ToArray(); Status=[int]$response.StatusCode; Range=$response.Headers['Content-Range']; Cache=$response.Headers['X-LearnHouse-Origin-Cache'] }
    } finally {
        $memory.Dispose()
        if ($response) { $response.Dispose() }
    }
}
try {
    $manifestResponse = Read-Request ($config.export_base + '/manifest')
    $manifest = [Text.Encoding]::UTF8.GetString($manifestResponse.Bytes) | ConvertFrom-Json
} catch {
    $failure = @{ errors=1; stage='manifest'; error=$_.Exception.GetType().Name; finished_at=[DateTime]::UtcNow.ToString('o') }
    [IO.File]::WriteAllText((Join-Path $root 'prefetch-status.json'), (ConvertTo-Json -InputObject $failure), (New-Object Text.UTF8Encoding($false)))
    exit 1
}
$stats = @{ scanned=0; completed=0; skipped=0; errors=0; deferred=$false; downloaded_bytes=0; finished_at=$null }
$deadline = [DateTime]::UtcNow.AddSeconds(100)
:Videos foreach ($video in $manifest.videos) {
    $stats.scanned++
    $uri = [string]$video.uri
    $size = [long]$video.bytes
    $fingerprint = [string]$video.bytes + ':' + [string]$video.mtime_ns
    $entry = $state[$uri]
    if ($entry -and $entry.fingerprint -eq $fingerprint -and $entry.complete -and ([DateTime]::UtcNow - [DateTime]::Parse($entry.checked_at).ToUniversalTime()).TotalHours -lt 24) {
        $stats.skipped++
        continue
    }
    if (-not $entry -or $entry.fingerprint -ne $fingerprint) {
        $entry = [pscustomobject]@{ fingerprint=$fingerprint; next_offset=0; complete=$false; checked_at=$null; error=$null }
        $state[$uri] = $entry
    }
    try {
        $alreadyComplete = [bool]$entry.complete
        $offset = if ($alreadyComplete) { 0L } else { [long]$entry.next_offset }
        while ($offset -lt $size) {
            $end = [Math]::Min($offset + 4194304, $size) - 1
            $chunk = $null
            for ($attempt=0; $attempt -lt 4; $attempt++) {
                try {
                    if ($alreadyComplete) {
                        # Touch every slice daily, transferring one byte per HIT.
                        $probe = Read-Request ($config.origin_base + $uri) $offset $offset
                        if ($probe.Cache -eq 'HIT' -and $probe.Bytes.Length -eq 1) { $chunk=$probe; break }
                    }
                    $chunk = Read-Request ($config.origin_base + $uri) $offset $end
                    if ($chunk.Status -ne 206 -or $chunk.Bytes.Length -ne ($end-$offset+1) -or $chunk.Range -ne ('bytes ' + $offset + '-' + $end + '/' + $size)) { throw 'Incomplete video range' }
                    $stored = Read-Request ($config.origin_base + $uri) $offset $offset
                    if ($stored.Cache -ne 'HIT' -or $stored.Status -ne 206 -or $stored.Bytes.Length -ne 1) { throw 'Video range was not persisted in cache' }
                    $stats.downloaded_bytes += $chunk.Bytes.Length
                    break
                } catch {
                    if ($attempt -eq 3) { throw }
                    Start-Sleep -Seconds ($attempt + 1)
                }
            }
            $offset = $end + 1
            $entry.next_offset = $offset
            $entry.error = $null
            Save-State
            if ($offset -lt $size -and [DateTime]::UtcNow -ge $deadline) { $stats.deferred=$true; break Videos }
        }
        $entry.complete = $true
        $entry.checked_at = [DateTime]::UtcNow.ToString('o')
        $stats.completed++
    } catch {
        $entry.error = $_.Exception.GetType().Name
        $stats.errors++
    }
    Save-State
    if ([DateTime]::UtcNow -ge $deadline) { $stats.deferred=$true; break Videos }
}
$stats.finished_at = [DateTime]::UtcNow.ToString('o')
[IO.File]::WriteAllText((Join-Path $root 'prefetch-status.json'), (ConvertTo-Json -InputObject $stats), (New-Object Text.UTF8Encoding($false)))
if ($stats.errors -gt 0) { exit 1 }
