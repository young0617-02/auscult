# V4b 压测 S0 空载基线（2026-09-24 实测）

> 决策依据：口径 B（宿主总占用）；GPU 已决议改走宿主 Ollama。
> 采集命令见各表旁注。原始采集于 PowerShell + `wsl -d docker-desktop`。

## DoD 前置核验

| 检查项 | 实测 | 判定 |
|---|---|---|
| `.wslconfig` 存在 | `Test-Path` → **True** | ✅ |
| Docker 内存上限 | `MemTotal=20972691456` ≈ **20GB** | ✅ |
| Docker NCPU | **10** | ✅ |

## 空载（S0）基线

| 项 | 值 |
|---|---|
| WSL2 (docker-desktop) 总内存 | 20001 MB |
| WSL2 已用 / 可用 | 956 MB / 18779 MB |
| Windows 宿主总内存 | 31.80 GB |
| **Windows 宿主已用（口径 B 基线）** | **19.65 GB** |
| 显存 | 983 MiB / 8188 MiB |

> 口径 B 的门禁核算 = Windows 宿主占用（19.65GB 起）+ WSL2/Docker 容器占用
> + 宿主 Ollama 占用，合计峰值 ≤ 24GB 判 Pass。

## 运行容器

启动压测前 `docker ps` 为 **空**（0 个本项目容器）。