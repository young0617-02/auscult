<#
.SYNOPSIS
    T1.2 Environment and hardware collector - produces the single project baseline.

.DESCRIPTION
    Collects OS / CPU / memory / GPU / disk / CUDA / WSL2 / Docker / toolchain /
    Ollama models / ports, writes JSON to env/hardware.json, and prints a summary
    that can be pasted into env-baseline-v2.md.
    Supports tasks T1.2 (hardware), T1.3 (ports) and T1.4 (component versions).

.PARAMETER OutFile
    Output JSON path. Default env/hardware.json, relative to the project root.

.PARAMETER Quiet
    Write the file only, skip the console summary.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\collect_env.ps1
    powershell -File scripts\collect_env.ps1 -OutFile env\hardware-v2.json

.NOTES
    Idempotent: safe to re-run; overwrites the output and refreshes collected_at.
    Docker Desktop / Ollama must be running for those sections to be populated;
    if they are down the fields become null and a warning is added instead of failing.
    ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less .ps1 files
    using the ANSI code page, which corrupts non-ASCII literals.
#>
[CmdletBinding()]
param(
    [string]$OutFile = 'env\hardware.json',
    [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
$warnings = New-Object System.Collections.Generic.List[string]

function Get-Safe {
    param([scriptblock]$Block, [string]$Label)
    try { & $Block } catch {
        $warnings.Add("$Label collection failed: $($_.Exception.Message)")
        $null
    }
}

function Repair-String {
    # Make a string safe for ConvertTo-Json on PowerShell 5.1.
    # wsl.exe writes UTF-16LE; when captured under a single-byte console codepage the
    # result carries NUL bytes and other control characters, and ConvertTo-Json then
    # hangs or throws OutOfMemoryException on the whole object graph. Unpaired
    # surrogates are equally fatal.
    param([string]$Text)
    if ($null -eq $Text) { return $null }
    $sb = New-Object System.Text.StringBuilder
    for ($i = 0; $i -lt $Text.Length; $i++) {
        $code = [int]$Text[$i]
        if ($code -ge 0xD800 -and $code -le 0xDBFF) {
            if (($i + 1) -lt $Text.Length) {
                $next = [int]$Text[$i + 1]
                if ($next -ge 0xDC00 -and $next -le 0xDFFF) {
                    [void]$sb.Append($Text[$i]).Append($Text[$i + 1])
                    $i++
                    continue
                }
            }
            [void]$sb.Append('?')
            continue
        }
        if ($code -ge 0xDC00 -and $code -le 0xDFFF) { [void]$sb.Append('?'); continue }
        if ($code -lt 32 -and $code -ne 9 -and $code -ne 10 -and $code -ne 13) {
            [void]$sb.Append(' ')
            continue
        }
        [void]$sb.Append($Text[$i])
    }
    $sb.ToString()
}

function ConvertTo-JsonSafe {
    # Recursively rebuild a value graph so that every string is JSON-safe.
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) { return (Repair-String $Value) }
    if ($Value -is [System.Collections.IDictionary]) {
        $d = [ordered]@{}
        foreach ($k in $Value.Keys) { $d[[string]$k] = (ConvertTo-JsonSafe $Value[$k]) }
        return [pscustomobject]$d
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $a = @()
        foreach ($item in $Value) { $a += ,(ConvertTo-JsonSafe $item) }
        return ,$a
    }
    if ($Value -is [ValueType]) { return $Value }
    if ($Value.PSObject.Properties.Count -gt 0) {
        $d = [ordered]@{}
        foreach ($p in $Value.PSObject.Properties) { $d[$p.Name] = (ConvertTo-JsonSafe $p.Value) }
        return [pscustomobject]$d
    }
    return $Value
}

Write-Host "=== Auscult Phase 0 environment collection ===" -ForegroundColor Cyan
Write-Host ("Time: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))

# ---------- OS ----------
$os = Get-Safe {
    $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    New-Object psobject -Property @{
        product_name    = $cv.ProductName
        display_version = $cv.DisplayVersion
        build           = $cv.CurrentBuild
        hostname        = $env:COMPUTERNAME
    }
} 'OS'

# ---------- CPU ----------
$cpu = Get-Safe {
    $c = Get-ItemProperty 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0'
    New-Object psobject -Property @{
        name               = $c.ProcessorNameString
        identifier         = $c.Identifier
        logical_processors = $env:NUMBER_OF_PROCESSORS -as [int]
    }
} 'CPU'

# ---------- Memory ----------
$mem = Get-Safe {
    $bytes = $null
    try {
        $bytes = (Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop |
                  Measure-Object -Property Capacity -Sum).Sum
    } catch {
        # Fallback: under ConstrainedLanguage CIM may be unavailable.
        $pc = (Get-Counter '\Memory\Total Physical Memory' -ErrorAction Stop).CounterSamples[0].CookedValue
        $bytes = [int64]$pc
    }
    New-Object psobject -Property @{
        total_bytes = [int64]$bytes
        total_gb    = [math]::Round($bytes / 1GB, 2)
    }
} 'MEM'

# ---------- GPU ----------
# Collection order: nvidia-smi first (authoritative for VRAM / driver / compute cap),
# then WMI (adapter name + Windows-side driver version).
# Defect fixed: the old code stored [ordered] hashtables inside an ArrayList and then
# assigned fields by string key. PowerShell wraps those values as PSObject and throws
# "The property 'driver_version_nvidia' cannot be found on this object", which made the
# whole GPU section return $null (see the old env/hardware.json warnings).
# Now: immutable arrays plus a single [pscustomobject] build at the end, and malformed
# nvidia-smi rows are skipped instead of failing the entire section.
# ASCII-ONLY: keep every comment in this file ASCII (see file header; PS 5.1 reads
# BOM-less .ps1 using the ANSI code page and non-ASCII text corrupts parsing).
$gpu = Get-Safe {
    $nv = @()
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $csv = nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,compute_cap --format=csv,noheader,nounits 2>$null
        foreach ($line in $csv) {
            if (-not $line) { continue }
            $p = $line -split ',\s*'
            if ($p.Count -lt 5) {
                $warnings.Add("nvidia-smi row malformed, skipped: $line")
                continue
            }
            $nv += [pscustomobject]@{
                name  = $p[0]
                drv   = $p[1]
                total = [int]$p[2]
                used  = [int]$p[3]
                cc    = $p[4]
            }
        }
    } else {
        $warnings.Add('nvidia-smi not found; GPU info incomplete')
    }

    try {
        $wmi = @(Get-CimInstance Win32_VideoController -ErrorAction Stop)
    } catch {
        $wmi = @()
        $warnings.Add('WMI video controller enumeration failed; relying on nvidia-smi only')
    }

    $out = @()
    $count = [Math]::Max($nv.Count, $wmi.Count)
    for ($i = 0; $i -lt $count; $i++) {
        $n = $null
        $w = $null
        if ($i -lt $nv.Count) { $n = $nv[$i] }
        if ($i -lt $wmi.Count) { $w = $wmi[$i] }

        $gpuName = $null
        $drvNv = $null
        $vramTotal = $null
        $vramUsed = $null
        $cc = $null
        if ($n) {
            $gpuName = $n.name
            $drvNv = $n.drv
            $vramTotal = $n.total
            $vramUsed = $n.used
            $cc = $n.cc
        }
        $drvWin = $null
        $ramWmi = $null
        if ($w) {
            $drvWin = $w.DriverVersion
            $ramWmi = $w.AdapterRAM
            if (-not $gpuName) { $gpuName = $w.Name }
        }

        $out += [pscustomobject]@{
            name                   = $gpuName
            driver_version_windows = $drvWin
            adapter_ram_wmi        = $ramWmi
            adapter_ram_note       = 'WMI AdapterRAM is a truncated 32-bit value; trust nvidia-smi'
            driver_version_nvidia  = $drvNv
            vram_total_mib         = $vramTotal
            vram_used_mib          = $vramUsed
            compute_capability     = $cc
        }
    }
    if ($out.Count -eq 0) {
        $warnings.Add('No GPU adapter detected by nvidia-smi or WMI; gpu will be empty')
    }
    @($out)
} 'GPU'

# ---------- Disk ----------
$disk = Get-Safe {
    Get-PSDrive -PSProvider FileSystem |
        Where-Object { $_.Used -ne $null } |
        ForEach-Object {
            New-Object psobject -Property @{
                drive   = $_.Name
                used_gb = [math]::Round($_.Used / 1GB, 1)
                free_gb = [math]::Round($_.Free / 1GB, 1)
            }
        }
} 'DISK'

# ---------- CUDA toolkit ----------
$cuda = Get-Safe {
    $p = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA'
    $installed = Test-Path $p
    New-Object psobject -Property @{
        toolkit_installed_in_default_path = $installed
        toolkit_path_checked              = $p
        versions                          = if ($installed) { @((Get-ChildItem $p).Name) } else { @() }
    }
} 'CUDA'

# ---------- WSL2 ----------
$wslDistro = 'docker-desktop'
$wsl = Get-Safe {
    $cfg = Join-Path $env:UserProfile '.wslconfig'
    $info = [ordered]@{
        wslconfig_path    = $cfg
        wslconfig_present = Test-Path $cfg
        distro_checked    = $wslDistro
    }
    if (Test-Path $cfg) { $info['wslconfig_content'] = (Get-Content $cfg -Raw) }
    $info['version_raw'] = ((wsl --version 2>$null) -join "`n")
    try {
        $info['distros_raw'] = (((wsl -l -v 2>$null) -join "`n") -replace "`0", '')
    } catch { $warnings.Add('wsl -l -v failed') }

    # Only exec INSIDE the distro when it is actually Running. Starting a Stopped
    # distro can block for minutes (observed: the collector hung forever when Docker
    # Desktop was down), which used to prevent the snapshot from ever being written.
    $state = 'Unknown'
    if ($info['distros_raw'] -match ('(?m)^\s*\*?\s*' + [regex]::Escape($wslDistro) + '\s+(\S+)')) {
        $state = $Matches[1]
    }
    $info['distro_state'] = $state

    if ($state -ne 'Running') {
        $info['live_raw'] = ("SKIPPED: distro '{0}' is {1}; start Docker Desktop to collect live quota" -f $wslDistro, $state)
        $info['gpu_passthrough_in_wsl'] = ("SKIPPED: distro '{0}' is {1}" -f $wslDistro, $state)
        $warnings.Add("WSL distro '$wslDistro' is $state; live quota and GPU passthrough probes skipped")
    } else {
        try {
            $live = wsl -d $wslDistro -- sh -c 'nproc; free -m | sed -n 2p' 2>$null
            $info['live_raw'] = ($live -join ' | ')
        } catch { $warnings.Add('WSL2 live quota collection failed') }
        try {
            $g = wsl -d $wslDistro -- nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
            if ($LASTEXITCODE -eq 0 -and $g -and ($g -notmatch 'not found')) {
                $info['gpu_passthrough_in_wsl'] = ($g -join ';')
            } else {
                $info['gpu_passthrough_in_wsl'] = 'UNVERIFIED: ' + ($g -join ';')
            }
        } catch { $info['gpu_passthrough_in_wsl'] = 'UNVERIFIED' }
    }
    New-Object psobject -Property $info
} 'WSL'

# ---------- Docker ----------
$docker = Get-Safe {
    $d = [ordered]@{}
    $d['engine_version']  = (docker info --format '{{.ServerVersion}}' 2>$null | Select-Object -First 1)
    $d['compose_version'] = (docker compose version --short 2>$null | Select-Object -First 1)
    $d['os']              = (docker info --format '{{.OperatingSystem}}' 2>$null | Select-Object -First 1)
    $d['ncpu']            = (docker info --format '{{.NCPU}}' 2>$null | Select-Object -First 1)
    $memBytes             = (docker info --format '{{.MemTotal}}' 2>$null | Select-Object -First 1)
    $d['mem_total_bytes'] = $memBytes
    if ("$memBytes" -match '^\d+$') { $d['mem_total_gb'] = [math]::Round([int64]$memBytes / 1GB, 2) }
    $d['images']             = @(docker images --digests --format '{{.Repository}}:{{.Tag}}|{{.Digest}}|{{.Size}}' 2>$null)
    $d['running_containers'] = @(docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' 2>$null)
    New-Object psobject -Property $d
} 'DOCKER'

# ---------- Toolchain ----------
$toolchain = [ordered]@{}
foreach ($t in 'python', 'node', 'git', 'ollama', 'docker', 'wsl', 'nvidia-smi') {
    $cmd = Get-Command $t -ErrorAction SilentlyContinue
    if ($cmd) {
        $v = ''
        # Every candidate needs its own switch branch; otherwise the branch never
        # matches and version stays an empty string (docker / wsl / nvidia-smi were
        # all empty in the old env/hardware.json for exactly this reason).
        switch ($t) {
            'python'     { $v = ((python --version 2>&1) -join '') }
            'node'       { $v = ((node --version 2>&1) -join '') }
            'git'        { $v = ((git --version 2>&1) -join '') }
            'ollama'     { $v = ((ollama --version 2>&1 |
                                   Where-Object { $_ -and ($_ -notmatch 'Warning|could not connect') } |
                                   Select-Object -First 1) -join '') }
            'docker'     { $v = ((docker --version 2>&1) -join '') }
            'wsl'        { $v = ((wsl --version 2>&1 | Select-Object -First 1) -join '') }
            'nvidia-smi' { $v = ((nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>&1 | Select-Object -First 1) -join '') }
        }
        if (-not $v) { $v = 'UNKNOWN(probe returned empty)' }
        $toolchain[$t] = New-Object psobject -Property @{ path = $cmd.Source; version = $v }
    } else {
        $toolchain[$t] = New-Object psobject -Property @{ path = $null; version = 'MISSING' }
        $warnings.Add("Missing tool: $t")
    }
}

# ---------- Ollama models with digests ----------
$models = Get-Safe {
    $root = 'D:\.ollama\models\manifests'
    if (-not (Test-Path $root)) { $warnings.Add("Ollama manifests dir not found: $root"); return @() }
    $out = @()
    foreach ($mf in (Get-ChildItem $root -Recurse -File)) {
        $rel = $mf.FullName.Substring($root.Length).TrimStart('\')
        $parts = $rel -split '\\'
        if ($parts.Count -ge 4) {
            $name = "{0}:{1}" -f $parts[-2], $parts[-1]
            $json = Get-Content $mf.FullName -Raw | ConvertFrom-Json
            $layer = $json.layers | Where-Object { $_.mediaType -eq 'application/vnd.ollama.image.model' } | Select-Object -First 1
            $out += New-Object psobject -Property @{
                model                  = $name
                manifest_path          = $mf.FullName
                manifest_config_digest = $json.config.digest
                model_layer_digest     = $layer.digest
                model_layer_size       = $layer.size
            }
        }
    }
    $out
} 'OLLAMA-MODELS'

# ---------- Ports ----------
$ports = Get-Safe {
    $want = 19530, 9091, 7474, 7687, 6030, 6041, 5432, 6379, 11434, 1883, 8000, 3000
    $listening = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
                   Select-Object -ExpandProperty LocalPort -Unique)
    $out = @()
    foreach ($p in $want) {
        $owner = $null
        if ($listening -contains $p) {
            try {
                $conn = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($conn) {
                    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                    if ($proc) { $owner = "{0} (PID {1})" -f $proc.ProcessName, $proc.Id }
                    else       { $owner = "PID {0}" -f $conn.OwningProcess }
                }
            } catch { }
        }
        $out += New-Object psobject -Property @{
            port   = $p
            status = if ($listening -contains $p) { 'OCCUPIED' } else { 'free' }
            owner  = $owner
        }
    }
    $out
} 'PORTS'

# ---------- Assemble ----------
$result = New-Object psobject -Property ([ordered]@{
    _meta = New-Object psobject -Property @{
        purpose      = 'T1.2 hardware collection / V4a physical constraint input'
        script       = 'scripts/collect_env.ps1'
        collected_at = (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')
        hostname     = $env:COMPUTERNAME
        note         = 'Reports citing this file must also cite env-baseline-v2.md version'
    }
    os        = $os
    cpu       = $cpu
    memory    = $mem
    gpu       = $gpu
    disk      = $disk
    cuda      = $cuda
    wsl       = $wsl
    docker    = $docker
    toolchain = $toolchain
    models    = $models
    ports     = $ports
    warnings  = @($warnings)
})

# ---------- Write ----------
$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
$target = if ([System.IO.Path]::IsPathRooted($OutFile)) { $OutFile } else { Join-Path $root $OutFile }
$dir = Split-Path -Parent $target
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

# Serialize section by section. ConvertTo-Json can throw on a single problematic object
# graph (observed on this host: System.OutOfMemoryException), and a throw used to abort
# the whole snapshot so that NO file was written at all. Now a failing section is recorded
# as null plus a warning, while every healthy section still lands on disk.
$clean = [ordered]@{}
foreach ($key in $result.PSObject.Properties.Name) {
    if ($key -eq 'warnings') { continue }
    $value = ConvertTo-JsonSafe $result.$key
    try {
        $null = $value | ConvertTo-Json -Depth 8 -Compress
        $clean[$key] = $value
    } catch {
        $clean[$key] = $null
        $warnings.Add("JSON serialization failed for section '$key': $($_.Exception.GetType().Name) - $($_.Exception.Message)")
        Write-Host ("  [WARN] section '{0}' failed to serialize; recorded as null" -f $key) -ForegroundColor Yellow
    }
}
# Assign warnings last so any serialization failure above is itself captured.
$clean['warnings'] = @($warnings | ForEach-Object { Repair-String $_ })

try {
    $jsonText = [pscustomobject]$clean | ConvertTo-Json -Depth 8
    # Write UTF-8 WITHOUT BOM. On PS 5.1 "Set-Content -Encoding UTF8" prepends a BOM,
    # which breaks strict JSON readers (json.load(open(p, encoding='utf-8')) fails).
    [System.IO.File]::WriteAllText($target, $jsonText, (New-Object System.Text.UTF8Encoding($false)))
} catch {
    Write-Host ("[ERROR] JSON write failed: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 2
}
Write-Host ("Written: {0}" -f $target) -ForegroundColor Green

# ---------- Summary ----------
if (-not $Quiet) {
    Write-Host ""
    Write-Host "--- Summary (paste into env-baseline-v2.md) ---" -ForegroundColor Cyan
    Write-Host ("OS       : {0} {1} build {2}" -f $os.product_name, $os.display_version, $os.build)
    Write-Host ("CPU      : {0} / {1} logical cores" -f $cpu.name, $cpu.logical_processors)
    Write-Host ("Memory   : {0} GB" -f $mem.total_gb)
    foreach ($g in $gpu) {
        Write-Host ("GPU      : {0} / {1} MiB / driver {2} / CC {3}" -f $g.name, $g.vram_total_mib, $g.driver_version_nvidia, $g.compute_capability)
    }
    Write-Host ("WSL2     : wslconfig_present={0}  live={1}" -f $wsl.wslconfig_present, $wsl.live_raw)
    Write-Host ("Docker   : {0} / Compose {1} / MemTotal {2} GB / NCPU {3}" -f $docker.engine_version, $docker.compose_version, $docker.mem_total_gb, $docker.ncpu)
    Write-Host "Models   :"
    foreach ($m in $models) {
        Write-Host ("           {0}  layer={1}" -f $m.model, $m.model_layer_digest)
    }
    Write-Host "Ports occupied:"
    foreach ($p in ($ports | Where-Object { $_.status -eq 'OCCUPIED' })) {
        Write-Host ("           {0} {1}" -f $p.port, $p.owner) -ForegroundColor Yellow
    }
    if ($warnings.Count -gt 0) {
        Write-Host ""
        Write-Host ("Warnings ({0}):" -f $warnings.Count) -ForegroundColor Yellow
        $warnings | ForEach-Object { Write-Host ("  - {0}" -f $_) -ForegroundColor Yellow }
    } else {
        Write-Host ""
        Write-Host "No warnings." -ForegroundColor Green
    }
}

exit 0