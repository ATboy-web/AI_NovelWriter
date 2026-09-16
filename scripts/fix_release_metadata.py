"""修复历史 Release 的乱码标题与正文（幂等）。

## 背景
早期发布工具在非 UTF-8 控制台下把中文写成了 `?`，于是仓库的 Release 页面上留下
`v2.14.0 - ??BUG??: ?????+?????` 这类不可读条目（共 9 个版本受影响）。

## 还原依据（不编造）
1. **CHANGELOG.md 的项目条目** —— 项目自己的权威记录；
2. **标签指向提交的 message** —— 例如 v2.7.0 的 `feat: v2.7.0 AI工程化升级 + 多项修复`；
3. **字符数交叉验证** —— 乱码里的 `?` 个数保留了原文字数，例如：
   - `v2.14.1 - ??????`（6 字）= CHANGELOG「角色空壳修复」6 字 ✓
   - `GUI??(?????)` = GUI + 2 + (5) = 「GUI修复(无终端窗口)」，与正文
     "Built with --windowed mode. No console window." 一致 ✓
   - `v2.7.0 AI????? + ????` = AI + 5 + 4 = 「AI工程化升级 + 多项修复」，与提交一致 ✓
4. 无法确证的**不编造**：正文原样保留在 `<details>` 里供追溯，只补一行说明。

用法：`GITHUB_TOKEN=... python scripts/fix_release_metadata.py --dry-run`
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "ATboy-web/AI_NovelWriter"
REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
API = "https://api.github.com"
MARKER = (
    "> 本页说明于 2026-09-17 依据 `CHANGELOG.md` 与版本标签的提交记录**补记**："
    "早期发布工具的编码问题使原标题/正文不可读。\n"
    "> 未做任何证据不足的推断 —— 原始文本保留在下方折叠块中。\n"
)

#: 原文已被覆盖、无法完整取回时使用的标记（不得声称保留了原文）
MARKER_NO_ORIGINAL = (
    "> 本页说明于 2026-09-17 依据 `CHANGELOG.md` 与版本标签的提交记录**补记**："
    "早期发布工具的编码问题使原标题/正文不可读。\n"
    "> 原始正文在修复过程中已被覆盖、无法完整取回（曾因嵌套补记所致），"
    "故此处只保留**可核实**的内容，不作推断。\n"
)

#: 依据上文「还原依据」重建的标题
TITLES = {
    "v2.14.0": "v2.14.0 - 致命 BUG 修复：上下文被静默丢弃 + 大纲生成修复",
    "v2.14.1": "v2.14.1 - 角色空壳修复",  # 6 字，与 ?????? 吻合
    "v2.13.2": "v2.13.2 - GUI 修复（无终端窗口）",  # 与正文 windowed 说明吻合
    "v2.13.0": "v2.13.0 - 上下文连贯性 Bug 修复",  # 11 字，与 ??????????? 吻合
    "v2.12.3": "v2.12.3 - 新增 API 设置中心",  # 与 CHANGELOG「API设置中心」吻合
    "v2.7.0": "v2.7.0 - AI 工程化升级 + 多项修复",  # 与提交信息吻合
}

#: 无 CHANGELOG 条目时的补充说明（依据发布附件类型 / 标签提交信息，均为可核实的事实）
FALLBACK_NOTE = {
    "v2.12.1": "本版本为 **Android APK** 发布（附件 `AI_NovelWriter_v2.12.1.apk`），"
    "内容为移动端打包与资源路径修复 —— CHANGELOG 中无该版本条目，故不在此臆测细节。",
    "v2.7.0": "本版本对应提交 `788ab9c`：`feat: v2.7.0 AI工程化升级 + 多项修复`（CHANGELOG 中无该版本条目）。",
}


def _request(method: str, url: str, token: str, payload: dict | None = None) -> object:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "anw-release-metadata")
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - 固定 api.github.com
        return json.loads(resp.read().decode("utf-8"))


def changelog_section(version: str) -> str | None:
    text = CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(rf"^##\s+v?{re.escape(version)}\b.*?$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    section = match.group(1).strip()
    return section or None


def is_garbled(text: str | None) -> bool:
    """连续两个以上 `?` 视为乱码（正常文案几乎不会出现）。"""
    return bool(text) and bool(re.search(r"\?{2,}", text or ""))


def needs_body_fix(body: str | None) -> bool:
    """正文是否需要补记。

    ⚠️ 幂等性关键：补记后的正文会把**原始乱码文本**放进 `<details>` 里追溯，
    因此它自己仍然"含 `??`"。若只按 `is_garbled` 判断，第二次运行会再套一层补记
    （实测踩到）。故已含补记标记的正文一律视为已处理。
    """
    text = body or ""
    return is_garbled(text) and MARKER not in text and MARKER_NO_ORIGINAL not in text


#: 折叠块围栏。两种都要认：`build_body` 会把内层 ```` ``` ```` 转义成 `'''`
#: （否则折叠块会提前闭合），只看四个反引号会把内层原文整段漏掉。
FENCE_RE = re.compile(r"```|'''")


def extract_original(body: str, _depth: int = 0) -> str | None:
    """取回被折叠的**最内层**原始文本；取不到返回 `None`。

    两个实测踩到的细节：

    1. `build_body` 会把正文里的围栏转义成 `'''`，因此**嵌套补记的正文里不再有内层
       反引号围栏**，原文改由 `'''` 界定 —— 只认 ```` ``` ```` 会取不到（实测把
       v2.14.0 的原文丢了）。故两种围栏都认。
    2. 嵌套补记的候选内容 = 上一轮补记过的整篇正文，**仍含补记标记**；
       只按"含 `??` 且不含标记"过滤会把它整个丢掉。故遇到含标记的候选要**递归往里取**。
       递归必然收敛（候选严格更短），另加深度上限兜底。
    """
    if _depth > 5:  # pragma: no cover - 防御性上限
        return None

    fences = [match.start() for match in FENCE_RE.finditer(body)]
    best: str | None = None
    for index, start in enumerate(fences):
        for end in fences[index + 1 :]:
            candidate = body[start + 3 : end].strip("\n")
            if not candidate or "??" not in candidate:
                continue
            if MARKER in candidate or MARKER_NO_ORIGINAL in candidate:
                deeper = extract_original(candidate, _depth + 1)
                if deeper and (best is None or len(deeper) > len(best)):
                    best = deeper
                continue
            if best is None or len(candidate) > len(best):
                best = candidate
            break
    return best


def build_body(version: str, original: str | None) -> str:
    parts = [MARKER if original else MARKER_NO_ORIGINAL]
    section = changelog_section(version)
    if section:
        parts.append(f"## 本版本内容（依据 `CHANGELOG.md` 的 v{version} 条目）\n\n{section}\n")
    note = FALLBACK_NOTE.get(version)
    if note:
        parts.append(f"## 说明\n\n{note}\n")
    if original:
        parts.append(
            "<details>\n<summary>原始正文（编码损坏，仅供追溯）</summary>\n\n```\n"
            + original.replace("```", "'''")
            + "\n```\n\n</details>\n"
        )
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，打印中文/符号会抛 UnicodeEncodeError 并**中断整个脚本**
    # （实测：在处理完第 1 个 release 后崩掉）。统一把 stdout 设为 UTF-8 且永不因编码失败。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - 非标准流
        pass

    parser = argparse.ArgumentParser(description="修复历史 Release 的乱码标题与正文")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要做的修改，不写入")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("错误：需要环境变量 GITHUB_TOKEN", file=sys.stderr)
        return 2

    releases = _request("GET", f"{API}/repos/{REPO}/releases?per_page=100", token)
    assert isinstance(releases, list)
    print(f"共 {len(releases)} 个 release\n")

    fixed = 0
    for rel in releases:
        tag = rel["tag_name"]
        name = rel.get("name") or ""
        body = rel.get("body") or ""
        new_name = TITLES.get(tag) if is_garbled(name) else None

        # 正文的三种处理：
        #   ① 仍是乱码 → 补记；② 被重复补记 → 收敛为一层；
        #   ③ 标了"已保留原文"但实际取不到原文 → 换成诚实的标记（不得声称保留了原文）
        original = extract_original(body) if is_garbled(body) else None
        marker_count = body.count(MARKER) + body.count(MARKER_NO_ORIGINAL)
        new_body = None
        if needs_body_fix(body):
            new_body = build_body(tag, original)
        elif marker_count > 1:
            new_body = build_body(tag, original)
            print(f"    正文被重复补记（{marker_count} 层）→ 收敛为 1 层")
        elif MARKER in body and original is None:
            new_body = build_body(tag, None)
            print("    补记声称保留了原文，但实际取不到 → 换用诚实标记")

        if not new_name and not new_body:
            continue

        print(f"--- {tag}")
        if new_name:
            print(f"    标题: {name!r}\n      ->  {new_name!r}")
        if new_body:
            print(f"    正文: 乱码 {len(body)} 字符 -> 补记 {len(new_body)} 字符")
        if args.dry_run:
            fixed += 1
            continue

        payload: dict[str, str] = {}
        if new_name:
            payload["name"] = new_name
        if new_body:
            payload["body"] = new_body
        _request("PATCH", f"{API}/repos/{REPO}/releases/{rel['id']}", token, payload)
        print("    已更新 OK")
        fixed += 1

    print(f"\n{'将处理' if args.dry_run else '已处理'} {fixed} 个 release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
