"""pytest 公共配置：把 scripts/ 与项目根加入 import 路径。

对应缺口：`docs/prj-ledger-known-issues.md` 前多次状态核查均记录「pytest 0 用例、无回归防护」。
本目录为 2026-10-06 新增，专为**已修复的真实缺陷**建立回归防护。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
