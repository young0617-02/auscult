"""设备编号口径单一事实源（ISS-056 候选① · 2026-10-22）。

## 为什么需要它

ISS-056 的根因是**两套编号并存**：产品层（提示词/判据/告警契约/前端）用规范完整编号
`PUMP-A-01`，数据层（TDengine 子表 TAG、`v3_ingest_direct`/`gen_sparkplug` 灌数、PG `alerts`）
用短编号 `PUMP-A`。候选②（工具层别名垫片）只是让查询"查得到"，垫片本身仍是第二套口径。

候选①是根治：**把数据层统一成规范编号**。但迁移不是一次性的原子操作——灌数端、库内数据、
查询端三方必须在同一套映射下切换，否则"新数据规范、旧数据短编号"混存会让查询静默丢半。
本模块是这套映射的**唯一事实源**：

- `CANONICAL_TO_LEGACY` / `LEGACY_TO_CANONICAL`：双向映射（未登记的编号原样透传）；
- `canonical()` / `legacy()`：单跳转换；
- `storage_id()`：把任意输入映射到**库内当前形态**，由 `AUSCULT_DEVICE_ID_SCHEME` 决定——
  - `canonical`（默认，2026-10-22 迁移完成后）：库内是规范编号，与灌数端默认值一致；
  - `legacy`：连**未迁移的旧库**时显式设置，落回短编号（可复现迁移前行为）。
- `device_id_scheme()`：当前口径（非法值保守回退 `canonical`，绝不因配置手误把查询打到空）。

> 默认值为什么从 `legacy` 改成 `canonical`：2026-10-22 真机迁移已把三侧存量数据改写为规范编号，
> 且灌数脚本默认值同步改为 `PUMP-A-01` 体系。此时若查询端仍默认 `legacy`，API 一启动就会
> 把 `PUMP-A-01` 映射回已不存在的 `PUMP-A` → 全链路"设备不存在"（已实测）。
> 默认值必须与数据实际形态一致，**未迁移的旧库请显式设 `legacy`**。

## 迁移节奏（`scripts/migrate_device_ids.py`）

1. 灌数端默认值已改为规范编号（`v3_ingest_direct` / `gen_sparkplug` / `spb_simulator`）——
   迁移后新数据天然是规范口径；
2. `migrate_device_ids.py --apply` 把**存量**数据原地改写（PG `alerts` / TDengine TAG+子表名 /
   Neo4j 实体名），不重灌、不丢时序数据；
3. 重启 API（默认口径已是 `canonical`；仅连未迁移的旧库才显式设 `legacy`）→ 查询端查规范编号；
4. **映射退场判据（2026-10-22 定稿，暂保留兼容层）**：`auscult_device_id_scheme_mismatch_total`
   （`app/observability/prom_metrics.py`）连续一周为 0，且 `--verify` 的 `off_scheme` 恒空 →
   才删除映射表与 `storage_id()` 两跳。该指标由工具层三处调用点打点（`direction=short_input`
   表示 canonical 模式下仍有客户端传短编号）；在此之前保留兼容层——直接删会让历史调用方静默查空。

回滚：把 `AUSCULT_DEVICE_ID_SCHEME` 切回 `legacy` 即回到旧口径（数据侧需按迁移日志反向执行）。

## 展示口径与库内事实分离

`canonicalize_text()` / `canonicalize_ids()` 只在**展示层**（报告读取出口）把历史 payload 里的
短编号归一为规范编号；**库内 payload 不改写**——历史报告是证据，改它等于篡改当时事实。
新报告本就写规范编号，该归一对它们是幂等的（可重复执行）。

## 范围说明（重要）

`work_orders.device_id` **没有可迁移对象**：灌数源 `parsed/workorders_*.md` 的“设备”列是
`A 0泵` / 客户号这类图纸/台账口径，本就不含产品设备编号（2026-10-22 实测：全量语料
`PUMP-` 0 命中）。故工单侧继续沿用"空结果回灌库里真实编号样本"的过渡方案
（`tool_registry._exec_get_maintenance_history`），根治需重做台账解析映射，另立项。
"""

from __future__ import annotations

import os
import re
from typing import Any

#: 规范编号（产品口径）→ 短编号（历史数据层口径）
CANONICAL_TO_LEGACY: dict[str, str] = {
    "PUMP-A-01": "PUMP-A",
    "PUMP-B-01": "PUMP-B",
    "PUMP-C-01": "PUMP-C",
}

#: 短编号 → 规范编号（迁移方向）
LEGACY_TO_CANONICAL: dict[str, str] = {v: k for k, v in CANONICAL_TO_LEGACY.items()}

#: 短编号的「独立出现」匹配：前后不得是词字符或连字符。
#: 这样 `PUMP-A-01`（后接连字符）、`X-PUMP-A`、`PUMP-AX` 都不会被误改；
#: 而 `PUMP-A 振动超标`、`PUMP-A.vib_rms` 会命中（测点前缀也应同口径）。
_LEGACY_TOKEN_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(k) for k in LEGACY_TO_CANONICAL) + r")(?![\w-])"
)

#: 库内编号口径开关：`canonical`（默认，2026-10-22 迁移后）| `legacy`（未迁移的旧库）
SCHEME_ENV = "AUSCULT_DEVICE_ID_SCHEME"
SCHEMES: tuple[str, ...] = ("canonical", "legacy")
DEFAULT_SCHEME = "canonical"


def device_id_scheme() -> str:
    """当前库内编号口径（非法值保守回退 `canonical`）。"""
    raw = (os.environ.get(SCHEME_ENV) or DEFAULT_SCHEME).strip().lower()
    return raw if raw in SCHEMES else DEFAULT_SCHEME


def canonical(device_id: str) -> str:
    """任意输入 → 规范编号（`PUMP-A` → `PUMP-A-01`；未登记/已规范原样返回）。"""
    value = (device_id or "").strip()
    return LEGACY_TO_CANONICAL.get(value, value)


def legacy(device_id: str) -> str:
    """任意输入 → 短编号（`PUMP-A-01` → `PUMP-A`；未登记/已短原样返回）。"""
    value = (device_id or "").strip()
    return CANONICAL_TO_LEGACY.get(value, value)


def canonicalize_text(text: str) -> str:
    """把文本里**独立出现**的短编号改写为规范编号（展示层归一，2026-10-22）。

    用途：历史报告 payload 里的编号是**迁移前**写入的（`PUMP-A`，当时事实），
    而新报告已是 `PUMP-A-01`；若不在读取出口归一，前端会同时看到两套口径。

    刻意只在**展示层**做：库内 payload 是证据、不改写（"历史事实"与"展示口径"分开）。
    纯函数、幂等：已是规范编号 / 未登记编号 / 被连字符词字符包裹的片段均原样返回。
    """
    if not text:
        return text
    return _LEGACY_TOKEN_RE.sub(lambda m: LEGACY_TO_CANONICAL[m.group(1)], text)


def canonicalize_ids(value: Any) -> Any:
    """递归归一 JSON 里所有字符串的设备号（dict / list / str，其余原样）。"""
    if isinstance(value, str):
        return canonicalize_text(value)
    if isinstance(value, dict):
        return {k: canonicalize_ids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canonicalize_ids(v) for v in value]
    return value


def storage_id(device_id: str, *, scheme: str | None = None) -> str:
    """任意输入 → **库内当前形态**的编号（工具层查询前调用）。

    两跳（先规范再落到目标形态）保证「规范 / 短 / 未知」三种输入在任一 scheme 下
    落到同一个库内值：未知编号原样透传，不会被这张表伪装成已知设备。
    """
    target = scheme or device_id_scheme()
    if target == "canonical":
        return canonical(device_id)
    return legacy(canonical(device_id))


def canonical_ids() -> tuple[str, ...]:
    """全部规范编号（迁移脚本与校验用）。"""
    return tuple(CANONICAL_TO_LEGACY)


def legacy_ids() -> tuple[str, ...]:
    """全部短编号（迁移脚本反向/回滚用）。"""
    return tuple(CANONICAL_TO_LEGACY.values())
