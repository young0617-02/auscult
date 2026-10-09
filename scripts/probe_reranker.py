"""BGE-reranker-v2-m3 加载/延迟/显存驻留探针（Phase 2 W4 前置）

来源：`docs/prj-ledger-version-lock.md` §二.2.2.2（已选用本地模型）；P1 遗留项「probe_reranker 实测」
目的：在接入 `scripts/rerank.py` 之前，实测该模型在**当前主机**的加载延迟、编码延迟与资源驻留，
      据此决定重排默认设备（cpu / gpu）与批大小，满足 plan §5.4「按需加载、不可三者共存」。

输出：打印 加载耗时 / 参数量 / 各 batch 编码耗时 / 建议设备；本地写
      `experiments/p2/w4/probe_reranker.json` 留痕。

用法：
  python scripts/probe_reranker.py                      # 默认 cpu（避免与 7B 争 GPU）
  python scripts/probe_reranker.py --device cuda:0      # 有 GPU 时对比
  python scripts/probe_reranker.py --batch-sizes 8 16   # 自选批大小
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from retrieval_base import PROJECT_ROOT

RERANKER_MODEL_PATH = PROJECT_ROOT / (  # 与 version-lock §二.2.2.2 一致
    r"D:\modelscope\hub\models\BAAI--bge-reranker-v2-m3\snapshots\master")
OUT_PATH = PROJECT_ROOT / "experiments" / "p2" / "w4" / "probe_reranker.json"

# 探针用贴近检索语料的 query-passage 对（含中文设备术语）
SAMPLE_PAIRS = [
    ("离心泵振动烈度超标的原因排查", "振动烈度表征转子不平衡，联轴器不对中亦会导致高振动烈度"),
    ("离心泵振动烈度超标的原因排查", "轴承温度升高可能由润滑不足或轴承磨损引起"),
    ("离心泵振动烈度超标的原因排查", "轴向振动异常建议检查叶轮与轴对中及轴承游隙"),
    ("离心泵振动烈度超标的原因排查", "轴承箱温度若持续升高且伴随振动加剧，需重点排查轴承磨损"),
    ("离心泵振动烈度超标的原因排查", "泵入口汽蚀会导致振动与噪声异常，应检查入口压力"),
    ("离心泵振动烈度超标的原因排查", "驱动端振动主要表征外伸端悬臂质量不平衡或基础松动"),
    ("离心泵振动烈度超标的原因排查", "联轴器不对中在不同径向位置表现为相位稳定性差异"),
    ("离心泵振动烈度超标的原因排查", "密封摩擦可能产生高频振动分量，与泵的临界转速相关"),
    ("离心泵振动烈度超标的原因排查", "基础刚度不足会放大振动响应，需检查地脚螺栓预紧"),
    ("离心泵振动烈度超标的原因排查", "轴承游隙变化反映滚动体磨损状态，应结合频谱判断"),
    ("离心泵振动烈度超标的原因排查", "叶轮失衡是离心泵超限的主要机理之一，动平衡校验可降低"),
    ("离心泵振动烈度超标的原因排查", "电机与泵之间联轴器不对中会耦合出 2X 转速频率分量"),
    ("离心泵振动烈度超标的原因排查", "管道应力传递至泵体也会造成振动烈度超限，影响运行"),
    ("离心泵振动烈度超标的原因排查", "轴承跑外圈或保持架损坏会表现出宽带高频振动"),
    ("离心泵振动烈度超标的原因排查", "主轴弯曲可产生高 1X 振动分量，需轴向对中检查"),
    ("离心泵振动烈度超标的原因排查", "振动烈度标准阈值依据 GB 相关判据，超标需停机排查"),
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="bge-reranker-v2-m3 探针")
    p.add_argument("--device", default="cpu", help="cpu / cuda:0")
    p.add_argument("--batch-sizes", nargs="+", type=int, default=[8, 16])
    args = p.parse_args(argv)

    if not RERANKER_MODEL_PATH.exists():
        print(f"[FAIL] reranker 模型目录不存在: {RERANKER_MODEL_PATH}")
        return 2

    from sentence_transformers.cross_encoder import CrossEncoder   # noqa: PLC0415

    t0 = time.perf_counter()
    try:
        model = CrossEncoder(str(RERANKER_MODEL_PATH), device=args.device)
    except Exception as exc:                                       # noqa: BLE001
        print(f"[FAIL] CrossEncoder 加载失败: {type(exc).__name__}: {exc}")
        return 2
    load_s = time.perf_counter() - t0

    # 参数量（仅留痕不参与判据）
    n_params = 0.0
    try:
        import torch                                    # noqa: PLC0415
        n_params = sum(float(q.nelement()) for q in model.model.parameters() if q.requires_grad)
    except Exception:                                    # noqa: BLE001 - 仅尽力统计
        n_params = 0.0

    print(f"[加载] 设备={args.device} 耗时={load_s:.2f}s 参数量≈{n_params/1e6:.1f}M")

    results = {"device": args.device, "load_s": round(load_s, 3),
               "n_params_m": round(n_params / 1e6, 1), "batch": {}}
    pairs = [SAMPLE_PAIRS[i % len(SAMPLE_PAIRS)] for i in range(32)]
    for bs in args.batch_sizes:
        # 预热一轮（框架/算子初始化），不计入指标
        t1 = time.perf_counter()
        model.predict(pairs[:bs], batch_size=bs, show_progress_bar=False)
        warm = time.perf_counter() - t1
        # 正式计时：跑 3 轮取 min
        lat = []
        for _ in range(3):
            t2 = time.perf_counter()
            model.predict(pairs, batch_size=bs, show_progress_bar=False)
            lat.append(time.perf_counter() - t2)
        best = min(lat)
        per = best / len(pairs) * 1000
        results["batch"][str(bs)] = {"warm_ms": round(warm * 1000, 1),
                                     "n": len(pairs), "total_ms": round(best * 1000, 1),
                                     "ms_per_pair": round(per, 2)}
        print(f"[编码] batch={bs} 预热={warm*1000:.0f}ms 正式 min={best*1000:.1f}ms "
              f"({per:.2f} ms/对)")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 探针结果 → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())