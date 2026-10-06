<#
.SYNOPSIS
    T1.3 Port availability check for Phase 0.

.DESCRIPTION
    Checks the 12 frozen Phase-0 ports on the Windows host and inside WSL2,
    identifies conflicts and suggests remapping. Task T1.3 of Phase 0.

    Port baseline (frozen in env/ports.md):
      19530 Milvus gRPC      / 9091  Milvus metrics
      7474  Neo4j HTTP       / 7687  Neo4j Bolt
      6030  TDengine native  / 6041  TDengine REST
      5432  PostgreSQL       / 6379  Redis checkpoint
      11434 Ollama (expected occupant) / 1883 Mosquitto
      8000  backend API      / 3000  frontend

.PARAMETER Ports
    Port list to check. Defaults to the Phase-0 baseline.

.PARAMETER ShowOwner
    Show owning process name and PID for occupied ports.

.PARAMETER WslDistro
    WSL2 distro used for the secondary check. Default docker-desktop.
    Pass an empty string to skip the WSL2 check.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\check_ports.ps1 -ShowOwner
    powershell -File scripts\check_ports.ps1 -Ports 19530,6379,11434

.NOTES
    Exit code: 0 = no conflict (expected occupants allowed); 1 = unexpected conflict.
    ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less .ps1 files
    using the ANSI code page, which corrupts non-ASCII literals.
#>
[CmdletBinding()]
param(
    [int[]]$Ports = @(19530, 9091, 7474, 7687, 6030, 6041, 5432, 6379, 11434, 1883, 8000, 3000),
    [switch]$ShowOwner,
    [string]$WslDistro = 'docker-desktop'
)

$ErrorActionPreference = 'Continue'

# Ports that are expected to be occupied and are NOT conflicts.
$expected = @{
    11434 = 'Ollama (this project, expected occupant)'
}

$labels = @{
    19530 = 'Milvus gRPC'
    9091  = 'Milvus metrics'
    7474  = 'Neo4j HTTP'
    7687  = 'Neo4j Bolt'
    6030  = 'TDengine native'
    6041  = 'TDengine REST'
    5432  = 'PostgreSQL'
    6379  = 'Redis checkpoint'
    11434 = 'Ollama'
    1883  = 'Mosquitto MQTT'
    8000  = 'Backend API'
    3000  = 'Frontend'
    2379  = 'etcd'
    9000  = 'MinIO S3'
    9001  = 'MinIO Console'
}

Write-Host "=== Auscult Phase 0 port check ===" -ForegroundColor Cyan
Write-Host ("Time : {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
Write-Host ("Scope: {0}" -f ($Ports -join ', '))
Write-Host ""

# ---------- Windows host side ----------
Write-Host "--- Windows host ---" -ForegroundColor Cyan
$listening = @()
try {
    $listening = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
                   Select-Object -ExpandProperty LocalPort -Unique)
} catch {
    Write-Host ("  Get-NetTCPConnection failed: {0}" -f $_.Exception.Message) -ForegroundColor Red
}

$conflicts = @()
$results   = @()

foreach ($p in $Ports) {
    $occupied = $listening -contains $p
    $label    = if ($labels.ContainsKey($p)) { $labels[$p] } else { 'unregistered' }

    if ($occupied) {
        $owner = ''
        if ($ShowOwner) {
            try {
                $conn = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue |
                        Select-Object -First 1
                if ($conn) {
                    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                    if ($proc) {
                        $owner = "  <- {0} (PID {1})" -f $proc.ProcessName, $proc.Id
                    } else {
                        $owner = "  <- PID {0}" -f $conn.OwningProcess
                    }
                }
            } catch { }
        }

        if ($expected.ContainsKey($p)) {
            Write-Host ("  {0,-6} OCCUPIED  {1,-18} [EXPECTED] {2}{3}" -f $p, $label, $expected[$p], $owner) -ForegroundColor DarkYellow
        } else {
            Write-Host ("  {0,-6} OCCUPIED  {1,-18} [CONFLICT]{2}" -f $p, $label, $owner) -ForegroundColor Red
            $conflicts += $p
        }
    } else {
        Write-Host ("  {0,-6} free      {1}" -f $p, $label) -ForegroundColor Green
    }

    $status = if ($occupied) { 'OCCUPIED' } else { 'free' }
    $results += New-Object psobject -Property @{ Port = $p; Label = $label; Status = $status }
}

# ---------- WSL2 side ----------
if ($WslDistro) {
    Write-Host ""
    Write-Host ("--- WSL2 ({0}) ---" -f $WslDistro) -ForegroundColor Cyan
    # Probe method (2026-09-29): run netstat ONCE inside the distro and parse the output
    # here. The previous per-port shell probe could not work in docker-desktop at all:
    #   - bash is NOT installed there ("/bin/sh: bash: not found"), and
    #   - busybox sh has no /dev/tcp redirection, so it always reported "free".
    # busybox netstat IS present (/bin/netstat), so "netstat -ltn" is the portable probe.
    # ASCII-ONLY: keep every comment in this file ASCII (see file header / PS 5.1 ANSI note).

    # Guard (same defect class as ISS-019): only exec INSIDE the distro when it is Running.
    # Starting a Stopped distro can block for minutes, so an unguarded probe could hang the
    # whole check with no output.
    $distroState = 'Unknown'
    $listOut = ((wsl -l -v 2>$null) -join "`n") -replace "`0", ''
    if ($listOut -match ('(?m)^\s*\*?\s*' + [regex]::Escape($WslDistro) + '\s+(\S+)')) {
        $distroState = $Matches[1]
    }
    Write-Host ("  distro state: {0}" -f $distroState)

    if ($distroState -ne 'Running') {
        Write-Host ("  SKIPPED: distro '{0}' is {1}; start it (e.g. launch Docker Desktop) and re-run" -f $WslDistro, $distroState) -ForegroundColor Yellow
    } else {
        $listenPorts = @()
        try {
            $raw = (wsl -d $WslDistro -- sh -c "netstat -ltn" 2>&1)
            $lines = @()
            foreach ($r in $raw) { $lines += ($r -split "`r?`n") }
            foreach ($line in $lines) {
                if ($line -notmatch '^\s*tcp') { continue }
                $cols = @(($line -split '\s+') | Where-Object { $_ })
                if ($cols.Count -lt 4) { continue }
                $local = [string]$cols[3]
                $idx = $local.LastIndexOf(':')
                if ($idx -lt 0) { continue }
                $pnum = $local.Substring($idx + 1)
                if ($pnum -match '^\d+$') { $listenPorts += [int]$pnum }
            }
            $listenPorts = @($listenPorts | Sort-Object -Unique)
        } catch {
            Write-Host ("  probe failed: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
        }

        if ($listenPorts.Count -eq 0) {
            Write-Host "  WARNING: no listening TCP port observed inside the distro; results below are not authoritative" -ForegroundColor Yellow
        }
        foreach ($wp in $Ports) {
            if ($listenPorts -contains $wp) {
                Write-Host ("  {0,-6} OCCUPIED" -f $wp) -ForegroundColor DarkYellow
            } else {
                Write-Host ("  {0,-6} free" -f $wp) -ForegroundColor Green
            }
        }
    }
}

# ---------- Verdict ----------
Write-Host ""
Write-Host "--- Verdict ---" -ForegroundColor Cyan
$freeCount = @($results | Where-Object { $_.Status -eq 'free' }).Count
Write-Host ("Free: {0} / {1}" -f $freeCount, $Ports.Count)

if ($conflicts.Count -gt 0) {
    Write-Host ("Unexpected conflicts on: {0}" -f ($conflicts -join ', ')) -ForegroundColor Red
    Write-Host "Suggested remap:" -ForegroundColor Yellow
    foreach ($c in $conflicts) {
        Write-Host ("  port {0} busy -> use {1}, then update docker/compose.base.yml and env/ports.md" -f $c, ($c + 10000)) -ForegroundColor Yellow
    }
    exit 1
}

Write-Host "No conflict (11434 is Ollama, the expected occupant). No remap needed." -ForegroundColor Green
exit 0