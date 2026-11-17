"""门禁校准工具 —— 用**真实稿对**复算预设阈值，而不是拍脑袋定数字。

## 为什么需要它

预设门禁现在是"人类参考 × 系数"（见 `writing_presets.calibrated_limits`）。
系数本身也必须能被质疑：如果某一项在你的稿件上**反复超标**，只有两种可能 ——

1. 你的写法确实偏离了人类参考（那就该改稿）；
2. 门禁过紧，或这批稿件的体裁与技能包的语料不同（那就该**重定 human_ref**，
   而不是把 limit 往上调 —— 调 limit 等于把门禁变成橡皮图章）。

本工具只做第 2 条的**取证**：把你积累的"改后稿"（= 你认可的合格稿）跑一遍，
给出各检测器的实测分布，并明确回答"当前门禁是不是过紧"。

## 用法

```bash
# 从目录读稿对（命名约定 <name>.before.md / <name>.after.md）
python scripts/calibrate_presets.py --pairs-dir ./我的稿对 --preset deai-full

# 显式指定若干稿对（可重复）
python scripts/calibrate_presets.py --pair a.md:b.md --pair c.md:d.md

# 只跑改后稿（没有原文时，只能看绝对密度）
python scripts/calibrate_presets.py --corpus ./合格稿 --preset novel-voice
```

## 输出口径

- `P50 / P75 / P90`：合格稿里该检测器的密度分位
- `当前门禁`：预设里的 limit
- `判定`：
  - `✅ 合适` —— 门禁 ≥ P75（四分之三的合格稿能过）
  - `⚠️ 偏紧` —— 门禁 < P75 但 ≥ P50（有相当一部分合格稿过不了）
  - `❌ 过紧` —— 门禁 < P50（过半合格稿被误判）
- `建议`：给的是 **human_ref 的重定建议**（= P50 附近），**不是**"把 limit 调高"

> 刻意**不自动改代码/配置**：门禁是发布门槛，改它必须有人的判断。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: 文件名里出现这些片段的，**一律不算合格稿**。
#:
#: 🔴 这是本工具最危险的误用点，实测踩过：把案例目录里的 `00-原稿.md`
#: （AI 原稿，本身就是待清理对象）当成"合格稿"，于是 P50 直接被不合格文本拉高，
#: 工具会理直气壮地建议"门禁过紧、请放宽"——**方向完全反了**。
#: 宁可漏收样本（少一篇只是分位不稳），也不能收错样本（结论会反向）。
_NOT_ACCEPTABLE = (
    "原稿",
    "改前",
    "before",
    "draft",
    "草稿",
    "未改",
    "待改",
)

#: 文件名里出现这些片段的，是**元文件**（说明、报告、索引），不是稿件正文。
#: 实测：`04-复测结论.md` 的表格含大量顿号，把顿号 P50 从 1.53 拉到 5.41 ——
#: 一份报告就能让工具建议"把门禁放宽 3 倍"。
_NOT_CONTENT = (
    "readme",
    "结论",
    "报告",
    "report",
    "说明",
    "索引",
    "index",
    "changelog",
    "摘要",
    "目录",
)

# 允许从仓库根直接运行（`python scripts/xxx.py`）
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.writing_presets import (  # noqa: E402
    PRESETS,
    _per_ktx,
    calibrated_limits,
    count_hanzi,
    detect_text,
    gate_factor_issues,
)


def _percentile(values: Sequence[float], q: float) -> float:
    """线性插值分位数（`q` ∈ [0,1]）。样本为空返回 0。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def collect_after_texts(
    pairs_dir: Optional[Path],
    pairs: Sequence[str],
    corpus: Optional[Path],
) -> List[Tuple[str, str]]:
    """收集要统计的文本，返回 `[(来源标签, 文本)]`。"""
    items: List[Tuple[str, str]] = []
    skipped: List[str] = []

    if pairs_dir:
        base = Path(pairs_dir)
        for after in sorted(base.glob("*.after.md")):
            items.append((after.name, _read(after)))

    for spec in pairs or ():
        parts = spec.split(":", 1)
        if len(parts) != 2:
            continue
        after_path = Path(parts[1])
        if after_path.is_file():
            items.append((after_path.name, _read(after_path)))

    if corpus:
        # 作品成稿是 `chapters/chapter_*.txt` —— 只收 *.md 会把最真实的那批语料漏掉
        candidates = sorted(Path(corpus).glob("*.md")) + sorted(Path(corpus).glob("*.txt"))
        for path in candidates:
            name = path.name.lower()
            if any(marker in name for marker in _NOT_ACCEPTABLE):
                skipped.append(path.name)
                continue
            if any(marker in name for marker in _NOT_CONTENT):
                skipped.append(path.name)
                continue
            items.append((path.name, _read(path)))

    if skipped:
        print(
            "⚠️ 已排除（疑似不合格稿 / 说明报告类元文件）："
            + "、".join(skipped[:8])
            + ("…" if len(skipped) > 8 else ""),
            file=sys.stderr,
        )
        print("   如果其中其实是合格稿，请改名后重跑 —— 收错样本会让结论反向。", file=sys.stderr)
    return items


def analyze(texts: Sequence[Tuple[str, str]], preset_key: str) -> Dict[str, Any]:
    """对每篇算密度，汇总成分布 + 判定。"""
    preset = PRESETS[preset_key]
    limits = {row["detector"]: row for row in calibrated_limits(preset)}
    per_detector: Dict[str, List[float]] = {key: [] for key in limits}
    hanzi_list: List[int] = []
    used_names: List[str] = []

    for label, text in texts:
        used_names.append(label)
        hanzi = count_hanzi(text)
        hanzi_list.append(hanzi)
        hits = detect_text(text)
        for key in limits:
            per_detector[key].append(_per_ktx(hits.get(key, 0), hanzi))

    rows: List[Dict[str, Any]] = []
    for key, samples in per_detector.items():
        info = limits[key]
        p50 = _percentile(samples, 0.50)
        p75 = _percentile(samples, 0.75)
        p90 = _percentile(samples, 0.90)
        limit = info["limit"]
        gate_class = info.get("gate_class", "review")
        if limit >= p75:
            verdict, note = "ok", "门禁覆盖 75% 以上的合格稿"
        elif gate_class == "review":
            # 粗筛项超标**不会阻断交付**（技能包自己的合格稿也超）⇒
            # 这不是"误判"，只是提示噪音。把它判成"过紧"会诱导人去放宽门禁，
            # 而正确做法是保持门禁、靠逐条复核。
            verdict, note = (
                "noisy",
                f"{'偏紧' if limit < p50 else '略紧'}，但该项为粗筛（不阻断）⇒ 保持门禁、逐条复核即可",
            )
        elif limit >= p50:
            verdict, note = "tight", "相当一部分合格稿会超标 ⇒ 建议按体裁重定 human_ref"
        else:
            verdict, note = "too_tight", "过半合格稿被误判 ⇒ human_ref 或被滥用，需重定"
        rows.append(
            {
                "detector": key,
                "label": info["label"],
                "samples": len(samples),
                "p50": round(p50, 3),
                "p75": round(p75, 3),
                "p90": round(p90, 3),
                "limit": limit,
                "human_ref": info["human_ref"],
                "basis": info["basis"],
                "gate_class": gate_class,
                "verdict": verdict,
                "note": note,
                "suggested_human_ref": round(p50, 3) if samples else None,
            }
        )

    return {
        "preset": preset_key,
        "small_sample": len(texts) < 5,
        "preset_name": preset.name,
        "documents": len(texts),
        "documents_used": used_names,
        "hanzi_total": sum(hanzi_list),
        "rows": rows,
        "gate_issues": gate_factor_issues(preset),
    }


def render(result: Dict[str, Any]) -> str:
    lines = [
        f"预设：{result['preset_name']}（{result['preset']}）",
        f"样本：{result['documents']} 篇 / {result['hanzi_total']} 汉字",
        "口径：密度 = 次数 × 1000 / 汉字数；分位基于**合格稿**（改后稿或既有成稿）",
        "",
        f"{'检测器':<14}{'P50':>7}{'P75':>7}{'P90':>7}{'门禁':>7}  判定",
    ]
    # 先插"实际纳入"，再插"小样本"提示 —— 两条都在表格之前，用户先看样本再看结论
    used = result.get("documents_used") or []
    if used:
        lines.insert(3, "实际纳入：" + "、".join(used[:8]) + ("…" if len(used) > 8 else ""))
    if result.get("small_sample"):
        lines.insert(
            3,
            "⚠️ 样本不足 5 篇：分位数不稳定，以下结论仅供参考（不要据此改 human_ref）",
        )
    icons = {"ok": "✅ 合适", "tight": "⚠️ 偏紧", "too_tight": "❌ 过紧", "noisy": "🔉 提示偏多"}
    for row in result["rows"]:
        lines.append(
            f"{row['label'][:12]:<14}{row['p50']:>7.2f}{row['p75']:>7.2f}"
            f"{row['p90']:>7.2f}{row['limit']:>7g}  {icons[row['verdict']]}"
        )
        if row["verdict"] not in ("ok", "noisy"):
            lines.append(f"{'':14}↳ {row['note']}")
            if row["suggested_human_ref"] is not None:
                lines.append(
                    f"{'':14}  建议 human_ref ≈ {row['suggested_human_ref']:g}"
                    f"（当前 {row['human_ref'] if row['human_ref'] is not None else '无'}）"
                )
    if result["gate_issues"]:
        lines.extend(["", "门禁自审计发现问题："])
        lines.extend(f"- {item}" for item in result["gate_issues"])
    lines.extend(
        [
            "",
            "提示：本工具**不会**改代码。采纳建议时改的是检测器的 `human_ref`，",
            "而不是把 `limit` 往上调 —— 后者会让门禁失去意义。",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="用真实稿对复算写作预设门禁")
    parser.add_argument("--pairs-dir", type=Path, help="目录，含 <name>.before.md / <name>.after.md")
    parser.add_argument("--pair", action="append", default=[], help="原文:改后稿（可重复）")
    parser.add_argument("--corpus", type=Path, help="只含合格稿的目录（*.md）")
    parser.add_argument("--preset", default="deai-full", choices=sorted(PRESETS))
    parser.add_argument("--json-out", type=Path, help="把结果写成 JSON")
    args = parser.parse_args(argv)

    texts = collect_after_texts(args.pairs_dir, args.pair, args.corpus)
    if not texts:
        print("没有可分析的文本。用 --pairs-dir / --pair / --corpus 指定。", file=sys.stderr)
        return 2

    result = analyze(texts, args.preset)
    print(render(result))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {args.json_out}")
    # 有"过紧"项时以非零退出，便于在 CI / 脚本里拦住
    # 只有「阻断项过紧」才值得让脚本失败：review 项偏紧是设计常态
    too_tight = [r for r in result["rows"] if r["verdict"] == "too_tight" and r["gate_class"] == "blocker"]
    return 1 if too_tight else 0


if __name__ == "__main__":
    raise SystemExit(main())
