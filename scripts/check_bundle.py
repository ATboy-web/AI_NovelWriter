"""核对 PyInstaller 构建产物里**到底打进了哪些模块**。

## 为什么需要一个独立脚本

`app/__init__` 对导入失败的处理是**降级为 `_ImportStub`**，而不是抛异常 ——
这是刻意的容错设计，但它的副作用是：**一个缺依赖的 EXE 不会报错，只会静默丢功能**。

本项目真发生过：release 作业只装了 `pyinstaller loguru`，于是 EXE 里缺
httpx / Pillow / cryptography，程序照常启动、界面照常出现，直到用户点了某个
功能才发现用不了。而"构建成功"的日志看起来完全正常。

所以 **"构建成功"不等于"功能齐全"**。本脚本用构建产物的 TOC 做静态核对，
把这件事变成一条可复现的检查。

## 两个已踩过的判据陷阱（别重犯）

1. **不能用字符串匹配**。PyInstaller 的 TOC typecode 里有一个就叫 `PIL`
   （用于 Pillow 图像资源），字符串搜索 `"PIL" in toc_text` 会把
   "有没有 PIL 这个**标签**"误当成"有没有 PIL 这个**包**"。必须解析 TOC 结构。
2. **不能把 `pyproject.toml` 的声明当"代码用到"**。`markdown` 与 `beautifulsoup4`
   都声明了，但 `app/` 全仓无人 `import`；把"声明了"当成"必需"会报出一个假缺口。
   所以必需清单来自**实际的 import 语句**（见 `REQUIRED_BY_IMPORT` 的注释）。

## 用法

    python scripts/check_bundle.py <Analysis-00.toc 路径>

构建时会生成在 `--workpath` 下的 `<spec名>/Analysis-00.toc`，例如：

    cd installer
    python -m PyInstaller novel_app.spec --noconfirm \\
        --distpath "%TEMP%\\anw_dist_x" --workpath "%TEMP%\\anw_work_x"
    python ../scripts/check_bundle.py "%TEMP%\\anw_work_x\\novel_app\\Analysis-00.toc"

退出码：0 = 必需模块齐全；1 = 有缺失（不应分发该产物）；2 = 用法/文件错误。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _console_utf8 import make_stdout_utf8_safe  # noqa: E402

make_stdout_utf8_safe()

#: 「`app/` 里**真的写了 import**」的第三方模块 —— 清单来源是调用点，**不是 pyproject**。
#: 每条附上调用点，方便下次核对时判断清单是否还成立。
#: 由 `tests/test_bundle_manifest.py` 从源码重新推导后对账，过期即变红。
REQUIRED_BY_IMPORT = {
    "httpx": "所有 AI API 调用（app/ai_client.py）",
    "loguru": "日志（多处）",
    "cryptography": "API Key 加密（app/config.py）",
    "tkinter": "界面框架（app/ui_style.py 等）",
    "docx": "Word 导出/导入（format_converter / generation_ui / lifecycle_ui / reading_manager）",
    "ebooklib": "EPUB 导出/导入（format_converter / reading_manager）",
    "pypdf": "PDF 导入（reading_manager）",
}

#: `app/` **不直接** import、但必须在产物里，否则直接依赖会在**运行时**报错。
#: 之所以单列：这些"必需"无法用"源码里有没有 import"来判定，
#: 混进 `REQUIRED_BY_IMPORT` 会让守门测试误报（第一版就把 `lxml` 放错了地方）。
REQUIRED_TRANSITIVE = {
    "lxml": "python-docx 与 ebooklib 的 XML 后端（两者都在 Requires-Dist 里声明）",
}

#: 在 `pyproject.toml` 里声明、但 `app/` 全仓**没有 import** 的依赖。
#: 键用**真实的 import 名**（`beautifulsoup4` 的 import 名是 `bs4`）——
#: 用发行名当键会让"确实没被 import"这条断言永远为真，退化成空转。
#: 它们不进 EXE 是正常的；列出来是为了避免下次误判成缺口。
DECLARED_BUT_UNUSED = {
    "markdown": "`_to_markdown` 是自己拼 md 文本，不需要 md→html 的 `markdown` 包",
    "bs4": "无 `import bs4`；被打包是被 lxml 的**可选** `html.soupparser` 带进来的",
}

#: `installer/novel_app.spec` 里**有意排除**、且代码中带降级分支的项。
INTENTIONAL_EXCLUDES = {
    "PIL": "toolkit_ui.py 的图片预览；有 `except ImportError` 分支，只保留 Markdown 标记",
    "numpy": "无本地张量计算",
    "pandas": "同上",
    "matplotlib": "同上",
    "chromadb": "已移入可选 extra，桌面端零 import",
    "fastapi": "仅后端使用",
    "uvicorn": "同上",
    "pydantic": "同上",
    "scipy": "无需求",
    "sentence_transformers": "无需求",
}


def _load_toc(path: Path):
    """读 TOC。它是 `repr()` 出来的 Python 字面量，用 `ast.literal_eval` 安全解析。"""
    return ast.literal_eval(path.read_text(encoding="utf-8", errors="replace"))


def analyse(toc) -> dict:
    """按位置索引取各段（索引由 PyInstaller 6.22.3 实测确定）。"""
    pure = {e[0] for e in toc[14]}
    binaries = {e[0] for e in toc[15]}
    return {
        "pure": pure,
        "binaries": binaries,
        "datas": {e[0] for e in toc[18]},
        "excludes": set(toc[5]),
        "all_names": pure | binaries,
    }


def has_module(all_names: set, name: str) -> bool:
    return name in all_names or any(p.startswith(name + ".") for p in all_names)


def check(toc_path: Path) -> int:
    info = analyse(_load_toc(toc_path))
    all_names, excludes = info["all_names"], info["excludes"]

    print(f"TOC: {toc_path}")
    print(f"  纯 Python 模块 {len(info['pure'])} / 二进制 {len(info['binaries'])} / 数据 {len(info['datas'])}")
    print(f"  excludes = {sorted(excludes)}")
    print()

    print(f"{'必需模块（app/ 直接 import）':<28}{'状态':<6}调用点")
    missing = []
    for mod, desc in REQUIRED_BY_IMPORT.items():
        ok = has_module(all_names, mod)
        if not ok:
            missing.append(mod)
        print(f"  {mod:<26}{'OK' if ok else '缺':<6}{desc}")

    print()
    print("必需模块（app/ 不直接 import，但直接依赖需要它）：")
    for mod, desc in REQUIRED_TRANSITIVE.items():
        ok = has_module(all_names, mod)
        if not ok:
            missing.append(mod)
        print(f"  {mod:<26}{'OK' if ok else '缺':<6}{desc}")

    print()
    print("声明但 app/ 未 import（不进 EXE 属正常，勿当缺口）：")
    for mod, desc in DECLARED_BUT_UNUSED.items():
        print(f"  {mod:<18} 已打包={has_module(all_names, mod)!s:<6}{desc}")

    print()
    print("spec 有意排除（代码内有降级分支）：")
    for mod, desc in INTENTIONAL_EXCLUDES.items():
        packaged = has_module(all_names, mod)
        if packaged:
            state = "⚠️ 实际被打包（与 spec 不符）"
        elif mod in excludes:
            state = "已按预期排除"
        else:
            state = "未打包但也不在 excludes（检查是否真被引用）"
        print(f"  {mod:<22} {state}  — {desc}")

    print()
    if missing:
        print(f"❌ 缺失「代码真的会 import」的模块：{missing}")
        print("   该产物**不要分发** —— 缺少时应用不会报错，只会静默丢功能。")
        return 1
    print("✅ 所有「代码真的会 import」的模块均已打包")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        print("\n错误：需要且只需要一个参数 —— Analysis-00.toc 的路径", file=sys.stderr)
        return 2
    toc_path = Path(argv[1])
    if not toc_path.is_file():
        print(f"错误：找不到 TOC 文件：{toc_path}", file=sys.stderr)
        return 2
    return check(toc_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
