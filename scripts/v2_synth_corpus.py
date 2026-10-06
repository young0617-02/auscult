"""V2 压力档批量语料合成器（仅供延迟/内存实测，不追求语义准确性）。

仅用于 V2 压力档（`reports/v2-report.md` §六），目标是从同一套工业模板/术语
合成大规模**中文文本块**，固定 seed 可复现，保证语料多样性与规模（1万/3万/10万）。

字段结构与 `run_v2.load_corpus` 兼容：`{chunk_id, text, category, doc_title}`。
chunk_id 格式 `seg_<k>`（从 1 递增）。

用法（在本仓库 `.venv` 下）：
  python scripts/v2_synth_corpus.py --n 10000
  python scripts/v2_synth_corpus.py --n 30000
  python scripts/v2_synth_corpus.py --n 100000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PROJECT_ROOT / "experiments" / "v2" / "raw" / "corpora_v2"

# 工业主题 / 类别（压力档不关心语义准确性，仅保证术语多样性覆盖）
CATEGORIES = ("设备手册", "振动标准", "故障诊断", "维护规程", "油液分析")

# 设备部件
PARTS = (
    "离心泵", "轴承箱", "轴承座", "机械密封", "联轴器", "叶轮", "蜗壳", "泵轴",
    "泵壳", "端盖", "机封腔", "轴封", "密封环", "口环", "导叶", "进水喇叭口")

# 参数 / 单位
PARAMS = (
    "额定流量", "额定扬程", "转速", "电机功率", "振动烈度", "轴承温度",
    "机械密封腔温度", "油位", "油温", "电流", "压力", "汽蚀余量", "清洁度等级",
    "包络值", "速度均方根值", "位移", "加速度", "油膜厚度", "泵出口压力", "进口真空度")

# 状态 / 特征词
FEATURES = (
    "异常振动", "松动", "对中不良", "不平衡", "气蚀", "动态失稳", "过热",
    "磨损", "疲劳剥落", "打滑", "乳化", "结垢", "劣化", "高频分量", "边频带",
    "谐波", "次谐波", "共振", "皮带打滑", "轴向窜动")

# 数值/单位词
NUM_WORDS = ("mm/s", "mm", "MPa", "m³/h", "r/min", "℃", "A", "kW", "Hz", "ppm")

# 句子模板：{part}->部件, {param}->参数, {feat}->特征, {num}->数值词
SENTENCE_TPL = (
    "{part}的{param}实测值为 {v1} {num}，较基线偏高 {pct}%。",
    "对{part}进行诊断时发现{feat}迹象，需要结合{param}与频谱特征综合判断。",
    "按巡检规程记录：{part}的{param}处于 {v2} {num}，未触发 {thr} {num} 的报警阈值。",
    "历史数据显示{param}存在缓慢上升趋势，可能由{feat}或{feat}引起，建议安排{param}复核。",
    "{part}投用后累计运行 {hours} 小时，期间多次捕获到{feat}的{num}高频分量。",
    "本次分析重点关注{param}，其变化与{feat}高度相关，已列入下月{param}重点跟踪项。",
    "参考标准评定，{part}的{param}分区属于 {zone} 区，若持续{feat}应安排检修窗口。",
    "对{part}加装了传感器监测{param}，采样间隔 {sample}s，用于捕捉{feat}的早期预警。",
)

# 报警/停机阈值
THRESHOLDS = ("报警值 4.5", "停机值 7.1", "报警值 1.5", "停机值 3.2")
ZONES = ("A", "B", "C", "D")


def make_text(rng: random.Random) -> str:
    n_sent = rng.randint(3, 6)
    sentences: list[str] = []
    for _ in range(n_sent):
        tpl = rng.choice(SENTENCE_TPL)
        part = rng.choice(PARTS)
        param = rng.choice(PARAMS)
        feat = rng.choice(FEATURES)
        num = rng.choice(NUM_WORDS)
        sentences.append(tpl.format(
            part=part, param=param, feat=feat, num=num,
            v1=rng.randint(10, 900) / 10,
            v2=rng.randint(5, 500) / 10,
            pct=rng.randint(2, 40),
            thr=rng.choice(THRESHOLDS),
            hours=rng.randint(500, 20000),
            zone=rng.choice(ZONES),
            sample=rng.choice((1, 2, 5, 10)),
        ))
    return "".join(sentences)


def build_corpus(n: int, seed: int, out: Path) -> None:
    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for k in range(1, n + 1):
            rec = {
                "chunk_id": f"seg_{k}",
                "text": make_text(rng),
                "category": rng.choice(CATEGORIES),
                "doc_title": "压力档合成语料",
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"已生成 {n} 段 -> {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 压力档语料合成器")
    parser.add_argument("--n", type=int, required=True,
                        help="语料规模（压力档取 10000/30000/100000）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="输出目录（默认 experiments/v2/raw/corpora_v2）")
    args = parser.parse_args()

    out = args.out_dir / f"corpus_{args.n}.jsonl"
    build_corpus(args.n, args.seed, out)

    # load_corpus 兼容自检
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from run_v2 import load_corpus  # noqa: PLC0415
    docs = load_corpus(out)
    ok = len(docs) == args.n and docs[0].chunk_id == "seg_1"
    print(f"load_corpus 读取校验：len={len(docs)} ({'PASS' if ok else 'FAIL'})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())