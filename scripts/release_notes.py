#!/usr/bin/env python3
"""从 CHANGELOG 生成 GitHub Release 正文。

## 为什么要有这个脚本

发布说明与 CHANGELOG 表达的是同一件事。凡是"同一事实写在两处"，就必然漂移 ——
本仓库的 README 下载表曾长期指向旧版本、`docs/README.md` 的根级文档清单曾多出
一份陈旧的 `README_CN.md`，都是同一类事故。因此发布说明**由 CHANGELOG 派生**，
而不是手工另写一份。

CI 在 `v*` 标签上运行它（见 `.github/workflows/ci.yml` 的 release 作业），
也可以本地用来预览：

```bash
python scripts/release_notes.py            # 用 pyproject.toml 里的版本
python scripts/release_notes.py 3.0.0      # 指定版本
python scripts/release_notes.py 3.0.0 --out notes.md
```
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

HEADER = """**发布日期**：{date}　|　**版本**：`v{version}`　|　**许可证**：MIT Modified（商用需注明来源）

Windows 桌面版单文件免安装，下载后直接双击运行。

---

"""

FOOTER = """

---

## 下载

| 平台 | 文件 | 说明 |
|------|------|------|
| Windows 10/11 (64 位) | `AI_NovelWriter.exe` | 单文件免安装，首次启动在 **设置 → AI 服务** 里配置 API Key 或本地 Ollama |
| Android | 见 [v2.16.0 Release](https://github.com/ATboy-web/AI_NovelWriter/releases/tag/v2.16.0) | 沿用 v4.0.1 构建，桌面端与移动端分别发版 |

## 系统要求

- Windows 10/11（64 位），至少 4 GB 内存
- AI 服务二选一：本地 Ollama（推荐 14B+ 模型）或云端 API Key

## 校验

本文档由 `CHANGELOG.md` 的对应条目**自动派生**，版本号以 `pyproject.toml` 为唯一权威源
（`tests/test_version_consistency.py` 会拦截任何漂移）。

## 反馈

问题与建议请到 [Issues](https://github.com/ATboy-web/AI_NovelWriter/issues) 反馈。

---

感谢使用 AI小说创作工坊！
"""


def project_version() -> str:
    """读 `pyproject.toml` 的版本（唯一权威源）。"""
    import tomllib

    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def changelog_section(version: str, changelog_text: str | None = None) -> str:
    """抽取 `## vX.Y.Z` 到下一个 `## ` 之间的正文。找不到时抛 `KeyError`。"""
    text = changelog_text if changelog_text is not None else CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^##\s+v?{re.escape(version)}\b.*?$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise KeyError(f"CHANGELOG.md 中找不到版本 {version} 的条目")
    section = match.group(1).strip()
    if not section:
        raise KeyError(f"CHANGELOG.md 中 {version} 的条目是空的")
    return section


def build_release_notes(version: str, date: str | None = None) -> str:
    """组装完整发布说明（头部 + CHANGELOG 正文 + 尾部）。"""
    from datetime import date as _date

    when = date or _date.today().isoformat()
    return HEADER.format(version=version, date=when) + changelog_section(version) + FOOTER


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 CHANGELOG 生成 GitHub Release 正文")
    parser.add_argument("version", nargs="?", default=None, help="版本号（默认取 pyproject.toml）")
    parser.add_argument("--out", default=None, help="输出文件（默认写 stdout）")
    parser.add_argument("--date", default=None, help="发布日期（默认今天）")
    args = parser.parse_args(argv)

    version = args.version or project_version()
    version = version.lstrip("v")
    try:
        notes = build_release_notes(version, args.date)
    except KeyError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(notes, encoding="utf-8")
        print(f"已写入 {args.out}（{len(notes)} 字符）")
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
