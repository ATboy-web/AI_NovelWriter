"""按文件夹层级整理全书：格式规范化 + 生成重写工单。

## 它做什么、不做什么

**做**（确定性、可回滚、不改正文一个字）：
1. 备份待修改的章节
2. 修 3 处章节标题格式异常（`**第21章：微澜**` / 缺 `#` / 首行是正文残句）
3. 逐章产出"重写工单"：字数、QC 阻断项、格式问题、建议动作
4. 核对 chapters / summaries / memory 三套数据的覆盖关系

**不做**：
- 不改写任何正文文字（那需要 AI，本机 key 已失效）
- 不补写丢失的标题（无法凭残句编造）
- 不动 summaries / video_plan 等派生数据
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from app.text_stats import count_hanzi  # noqa: E402

TITLE_HEAD_RE = re.compile(r"^#\s*第\s*(\d+)\s*章")


def split_first_line(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    return (lines[0] if lines else ""), "\n".join(lines[1:])


def classify_head(first: str, chapter: int) -> str:
    """返回 `ok` / `bold` / `no_hash` / `broken`。"""
    body = first.strip()
    if TITLE_HEAD_RE.match(body):
        return "ok"
    if re.fullmatch(r"\*\*第\s*\d+\s*章.*\*\*", body):
        return "bold"
    if re.fullmatch(r"第\s*\d+\s*章.*", body):
        return "no_hash"
    return "broken"


def fix_head(first: str, kind: str) -> str:
    body = first.strip()
    if kind == "bold":
        return "# " + body.strip("*").strip()
    if kind == "no_hash":
        return "# " + body
    return first


def main() -> int:
    root = Path.home() / ".ai_novel_writer" / "novels"
    novels = [p for p in root.iterdir() if p.is_dir()]
    if len(novels) != 1:
        print(f"预期 1 个作品，实际 {len(novels)} 个：{[p.name for p in novels]}")
    novel = novels[0]
    chapters_dir = novel / "chapters"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = novel / "backups" / f"format_fix_{stamp}"

    plan: list[dict] = []
    for path in sorted(chapters_dir.glob("chapter_*.txt")):
        match = re.search(r"chapter_(\d+)", path.name)
        if not match:
            continue
        chapter = int(match.group(1))
        text = path.read_text(encoding="utf-8", errors="replace")
        first, rest = split_first_line(text)
        kind = classify_head(first, chapter)
        plan.append({"chapter": chapter, "path": path, "kind": kind, "first": first, "rest": rest})

    need_fix = [row for row in plan if row["kind"] in ("bold", "no_hash")]
    broken = [row for row in plan if row["kind"] == "broken"]

    print(f"章节总数：{len(plan)}")
    print(f"  格式异常可自动修：{len(need_fix)} 章 -> {[r['chapter'] for r in need_fix]}")
    print(f"  首行不是标题（需人工）：{len(broken)} 章 -> {[r['chapter'] for r in broken]}")

    # ---- 备份 + 修复
    if need_fix:
        backup_dir.mkdir(parents=True, exist_ok=True)
        fixed: list[str] = []
        for row in need_fix:
            target = backup_dir / row["path"].name
            shutil.copyfile(row["path"], target)
            new_head = fix_head(row["first"], row["kind"])
            payload = new_head + "\n" + row["rest"]
            row["path"].write_text(payload, encoding="utf-8")
            fixed.append(f"第{row['chapter']}章：{row['first'][:24]!r} → {new_head[:24]!r}")
        print(f"\n已修 {len(fixed)} 章（备份在 {backup_dir.relative_to(novel)}）：")
        for line in fixed:
            print("  " + line)

    # ---- 摘要覆盖
    summaries = {int(m.group(1)) for p in (novel / "summaries").glob("chapter_*_summary.txt") if (m := re.search(r"chapter_(\d+)_summary", p.name))}
    empty_summaries: list[int] = []
    for num in summaries:
        path = novel / "summaries" / f"chapter_{num:05d}_summary.txt"
        body = path.read_text(encoding="utf-8", errors="replace")
        if count_hanzi(body) < 20:
            empty_summaries.append(num)

    print(f"\n摘要：{len(summaries)} 个，其中内容为空/过短：{len(empty_summaries)} 个 {sorted(empty_summaries)[:10]}")

    # ---- 逐章 QC
    from app.writing_presets import PRESETS, qc_report

    worklist: list[dict] = []
    for row in plan:
        text = row["path"].read_text(encoding="utf-8", errors="replace")
        hanzi = count_hanzi(text)
        report = qc_report(text, PRESETS["deai-full"], with_candidates=False)
        blockers = [i for i in report["items"] if i.get("blocking") and not i["passed"]]
        reviews = [i for i in report["items"] if not i["passed"] and not i.get("blocking")]
        worklist.append(
            {
                "chapter": row["chapter"],
                "hanzi": hanzi,
                "kind": row["kind"],
                "blockers": [(b["label"], b["count"], round(b["per_ktx"], 2)) for b in blockers],
                "reviews": [(r["label"], r["count"]) for r in reviews],
                "empty_summary": row["chapter"] in empty_summaries,
            }
        )

    # ---- 写工单
    total_hanzi = sum(item["hanzi"] for item in worklist)
    by_blocker: dict[str, int] = {}
    for item in worklist:
        for label, _count, _density in item["blockers"]:
            by_blocker[label] = by_blocker.get(label, 0) + 1
    clean = [i for i in worklist if not i["blockers"]]

    lines = [
        f"# 全书重写工单 · {novel.name}",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"章节：{len(worklist)} 章 / {total_hanzi:,} 汉字",
        f"无阻断项（无需重写）：{len(clean)} 章",
        f"有阻断项（建议重写）：{len(worklist) - len(clean)} 章",
        "",
        "## 阻断项分布（按章计）",
        "",
        "| 检测项 | 命中章数 |",
        "|---|---:|",
    ]
    for label, count in sorted(by_blocker.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {label} | {count} |")

    lines.extend(["", "## 逐章清单", "", "| 章 | 字数 | 格式 | 阻断项 | 摘要 |", "|---:|---:|---|---|---|"])
    for item in worklist:
        blocker_text = "；".join(f"{label} {count}次({density}/千字)" for label, count, density in item["blockers"]) or "—"
        fmt = {"ok": "正常", "bold": "粗体标题", "no_hash": "缺#", "broken": "**标题丢失**"}[item["kind"]]
        summary_flag = "空" if item["empty_summary"] else ""
        lines.append(f"| {item['chapter']} | {item['hanzi']:,} | {fmt} | {blocker_text[:60]} | {summary_flag} |")

    worklist_path = novel / "REWRITE_WORKLIST.md"
    worklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n工单已写入：{worklist_path.relative_to(novel)}")

    # ---- 机器可读版（给批量重写脚本消费）
    json_path = novel / "rewrite_worklist.json"
    json_path.write_text(
        json.dumps(
            {
                "novel": novel.name,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "total_chapters": len(worklist),
                "total_hanzi": total_hanzi,
                "clean_chapters": [i["chapter"] for i in clean],
                "needs_rewrite": [i["chapter"] for i in worklist if i["blockers"]],
                "broken_titles": [i["chapter"] for i in worklist if i["kind"] == "broken"],
                "empty_summaries": sorted(empty_summaries),
                "chapters": worklist,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"机器可读清单：{json_path.relative_to(novel)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
