# 交付包打包（v1.0.0 · 2026-10-22）
#
# 为什么需要它：Phase 6 §7.3 第 8 项「交付包封版（tag/压缩包）」此前无入口，
# 只有 baseline/gate 类 tag，没有语义版本、没有打包脚本 —— 验收无从执行。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File deploy\package.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\package.ps1 -Version v1.0.0 -Out dist
#
# 产物：dist\auscult-<Version>.zip（含源码/文档/配置/部署脚本；不含虚拟环境、模型、密钥、运行数据）
#
# 排除原则（宁可少打，不可泄漏）：
#   1. 环境与依赖：.venv / .venv-mineru / node_modules / __pycache__ / *.pyc / .next
#   2. 运行数据与产物：data / reports\traces / reports\metrics / logs / blobs / chunks / backups / experiments
#   3. 版本控制与临时：.git / dist / *.log / *.zip / *.dump / *.tgz / *.tsbuildinfo / test-results
#   4. 密钥：.env* 一律剔除（仅保留 .env.example 模板）
#
# 体积基线：约 10 MB / 800 余个文件；若 staging 超过 80 MB 说明有漏排除项，脚本会告警。

param(
    [string]$Version = "v1.0.0",
    [string]$Out = "dist"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $env:TEMP ("auscult-pkg-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$outDir = Join-Path $root $Out
$zip = Join-Path $outDir ("auscult-" + $Version + ".zip")

# 清理兜底：staging 在**失败路径**也必须删掉。
# 2026-10-22 实测踩到两次：关键件自检 throw 后 staging 留在 %TEMP%，其中 client\node_modules
# 路径超 260 字符，`Remove-Item -Recurse` 报"未能找到路径"，只能靠 robocopy 空目录镜像清掉。
# trap 在任意终止性错误时执行，清理后原样抛出（退出码仍非零，不掩盖失败）。
trap {
    if ($stage -and (Test-Path $stage)) {
        Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
    throw $_
}

Write-Host ("=== auscult 交付包打包 " + $Version + " ===") -ForegroundColor Cyan

# 版本一致性检查：git tag 与参数应一致（无 tag 时提示但不阻断）
Push-Location $root
try {
    $head = (git rev-parse --short HEAD) 2>$null
    $tagExists = (git tag --list $Version)
    $tagState = $(if ($tagExists) { "存在" } else { "不存在（建议先 git tag -a " + $Version + " -m `"release " + $Version + "`"）" })
    Write-Host ("[info] HEAD=" + $head + "  tag=" + $Version + " " + $tagState)
    $dirty = (git status --porcelain)
    if ($dirty) { Write-Host "[warn] 工作区有未提交改动，打包内容将包含这些改动（封版请先提交）" -ForegroundColor Yellow }
} finally {
    Pop-Location
}

# 1) 用 robocopy 做 staging（保留目录结构 + 精确排除）
$excludeDirs = @(
    ".git", ".venv", ".venv-mineru", "node_modules", "__pycache__", ".next", "test-results",
    "dist", "data", "traces", "metrics", "logs", "blobs", "chunks", "backups", "experiments",
    "env", ".pytest_cache", ".mypy_cache", ".trae"
)
$excludeFiles = @("*.pyc", "*.log", "*.err", "*.bak*", ".env", ".env.local", "*.zip", "*.dump", "*.tgz", "*.tsbuildinfo")
# 用目录名而非绝对路径：robocopy 按名匹配可命中任意层级（如 client\.next）
$xd = $excludeDirs

Write-Host ("[step] robocopy staging → " + $stage) -ForegroundColor DarkGray
robocopy $root $stage /E /XD $xd /XF $excludeFiles /NFL /NDL /NJH /NJS /MT:8 | Out-Null
if ($LASTEXITCODE -ge 8) { throw ("robocopy 失败，exit=" + $LASTEXITCODE) }

# 1.1) 兜底：任何 .env* 密钥文件一并剔除（.env.example 模板除外）
$leaks = Get-ChildItem $stage -Recurse -File -Filter ".env*" -Force |
         Where-Object { $_.Name -ne ".env.example" }
foreach ($l in $leaks) {
    Write-Host ("[warn] 剔除疑似密钥文件：" + $l.FullName.Substring($stage.Length + 1)) -ForegroundColor Yellow
    Remove-Item $l.FullName -Force
}

# 1.2) 兜底：扫描 staged 文本中的真实密钥形态（如 env/cloud.json 曾含 api_key）
$secretPat = 'sk-[A-Za-z0-9]{20,}|"api_key"\s*:\s*"[^"]{12,}"'
$secretHits = @(Get-ChildItem $stage -Recurse -File -Force |
    Where-Object { $_.Length -lt 512KB -and $_.Extension -in @('.json', '.yaml', '.yml', '.py', '.md', '.env', '.txt', '.toml', '.ini') } |
    Select-String -Pattern $secretPat -List -ErrorAction SilentlyContinue)
if ($secretHits.Count -gt 0) {
    Write-Host ("[warn] 以下文件疑似含真实密钥，请确认后再交付：") -ForegroundColor Yellow
    foreach ($h in $secretHits) { Write-Host ("       " + $h.Path.Substring($stage.Length + 1)) -ForegroundColor Yellow }
}

# 2) staging 体积与关键件自检
$staged = @(Get-ChildItem $stage -Recurse -File -Force)
$sizeMb = [math]::Round((($staged | Measure-Object Length -Sum).Sum) / 1MB, 1)
$must = @("README.md", "requirements.txt", "app\api\main.py", "deploy\up.ps1", "deploy\smoke.ps1",
          "db\migrations", "docs\prj-spec-deployment.md", "plan")
foreach ($m in $must) {
    if (-not (Test-Path (Join-Path $stage $m))) { throw ("交付包缺少关键件：" + $m) }
}

# 反向断言：环境目录一律不应出现
$badDirs = @(Get-ChildItem $stage -Recurse -Directory -Force |
             Where-Object { $_.Name -in @(".venv", ".venv-mineru", ".next", "node_modules", "backups", "experiments") })
if ($badDirs.Count -gt 0) { throw ("交付包误包含环境/产物目录：" + ($badDirs[0].FullName.Substring($stage.Length + 1))) }
if ($staged.Count -eq 0) { throw "staging 为空，robocopy 未生效" }
if ($sizeMb -gt 80) { Write-Host ("[warn] staging 体积 " + $sizeMb + " MB 超出基线，检查是否有漏排除项") -ForegroundColor Yellow }

# 3) 写清单（可审计：打了什么、多大、哪一版、排除了什么）
$manifest = Join-Path $stage "PACKAGE-MANIFEST.txt"
$files = $staged | Where-Object { $_.Name -ne "PACKAGE-MANIFEST.txt" }
$lines = @(
    ("auscult " + $Version + " 交付包清单"),
    ("生成时间: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")),
    ("git HEAD: " + (git -C $root rev-parse HEAD)),
    ("文件数: " + $files.Count),
    ("解压后体积: " + $sizeMb + " MB"),
    "",
    "=== 已排除目录 ===",
    ($excludeDirs -join "  "),
    "=== 已排除文件 ===",
    ($excludeFiles -join "  "),
    "",
    "=== 文件列表（相对路径 / 字节）==="
)
foreach ($f in $files) {
    $lines += ($f.FullName.Substring($stage.Length + 1) + "  " + $f.Length)
}
$lines | Set-Content -Path $manifest -Encoding UTF8

# 4) 压缩
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
$zipMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Remove-Item $stage -Recurse -Force

Write-Host ("[ok] " + $zip + "  (" + $zipMb + " MB, 解压后 " + $sizeMb + " MB, " + $files.Count + " 个文件)") -ForegroundColor Green
Write-Host "[提示] 交付前请确认：dist 内含敏感件？(data/.env/密钥)  →  见脚本头部排除原则" -ForegroundColor DarkGray
