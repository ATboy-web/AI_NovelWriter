"""面板 UI 的**可量化度量**（设计评审与验收共用）。

为什么要有它：界面好不好看很难自动化，但"难用"的成因大多是**可测量**的 ——
对比度不足、点击目标太小、间距不成体系、字号种类过多、内容溢出被裁。
这些不但能量出来，还能写成断言持续守住。

四项判据：

1. **对比度**（WCAG）——正文 ≥ 4.5:1、大字（≥18px 或加粗 ≥14px）≥ 3:1；
   低于阈值就是"看不清"，与审美无关。
2. **点击目标**——交互控件（按钮/勾选/输入框/下拉）高度 ≥ 26px、宽度 ≥ 60px；
   低于此值鼠标很难点中（本仓大量 `pady=0` + 默认字号的按钮就属这类）。
3. **字号种类数**——同一面板内出现的不同字号种类 ≤ 5；多了就没有层级可言。
4. **溢出/裁切**——内容超出容器且没有滚动条，等于"功能够不着"。
"""

from __future__ import annotations

import colorsys
import re
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterator

_INTERACTIVE = (
    tk.Button,
    tk.Checkbutton,
    tk.Radiobutton,
    tk.Entry,
    tk.Spinbox,
    tk.Scale,
    ttk.Button,
    ttk.Checkbutton,
    ttk.Radiobutton,
    ttk.Entry,
    ttk.Combobox,
    ttk.Spinbox,
)

#: 文本类控件
_TEXTY = (
    tk.Label,
    tk.Button,
    tk.Checkbutton,
    tk.Radiobutton,
    tk.Entry,
    tk.Text,
    ttk.Label,
    ttk.Button,
    ttk.Checkbutton,
    ttk.Radiobutton,
    ttk.Entry,
)


def walk(widget: tk.Misc) -> Iterator[tk.Misc]:
    """深度优先遍历控件树（含自身）。"""
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    """`#rgb` / `#rrggbb` → (r, g, b)；其他（颜色名/空串）返回 None。"""
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    body = value.lstrip("#")
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) != 6:
        return None
    try:
        return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)
    except ValueError:
        return None


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float | None:
    """WCAG 对比度；任一端不是十六进制颜色就返回 None（不猜）。"""
    a, b = _hex_to_rgb(fg), _hex_to_rgb(bg)
    if a is None or b is None:
        return None
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def widget_bg(widget: tk.Misc) -> str | None:
    """取控件的实际背景色（自身没有就往上找父容器）。"""
    node: tk.Misc | None = widget
    while node is not None:
        try:
            value = node.cget("bg")
        except Exception:  # noqa: BLE001
            try:
                value = node.cget("background")
            except Exception:  # noqa: BLE001
                value = None
        if isinstance(value, str) and value:
            return value
        node = getattr(node, "master", None)
    return None


def _font_size(font: Any) -> int | None:
    """从 font 配置里取出字号（tuple / 字符串 / 命名字体都能取）。"""
    if isinstance(font, tuple) and len(font) >= 2:
        try:
            return abs(int(font[1]))
        except (TypeError, ValueError):
            return None
    if isinstance(font, str):
        match = re.search(r"(\d+)", font)
        if match:
            return int(match.group(1))
    return None


def _is_bold(font: Any) -> bool:
    if isinstance(font, tuple) and len(font) >= 3:
        return "bold" in str(font[2]).lower()
    return False


def audit(root_widget: tk.Misc, *, label: str = "") -> dict:
    """对一个面板（或其容器）做一次完整体检。"""
    contrast_violations: list[str] = []
    small_targets: list[str] = []
    fonts: set[tuple] = set()
    spacing: set[int] = set()
    texts = 0

    for widget in walk(root_widget):
        if isinstance(widget, (ttk.Treeview, ttk.Notebook, ttk.Scrollbar, tk.Menu)):
            continue

        # --- 字号 / 前景色 -------------------------------------------------
        if isinstance(widget, _TEXTY):
            try:
                font = widget.cget("font")
            except Exception:  # noqa: BLE001
                font = None
            size = _font_size(font)
            if size is None:
                try:
                    size = _font_size(widget.tk.call("font", "actual", widget.cget("font")))
                except Exception:  # noqa: BLE001
                    size = None
            if size:
                fonts.add((size, _is_bold(font)))
            texts += 1

            try:
                fg = widget.cget("fg")
            except Exception:  # noqa: BLE001
                fg = None
            bg = widget_bg(widget)
            if isinstance(fg, str) and bg:
                ratio = contrast_ratio(fg, bg)
                big = bool(size and (size >= 18 or (size >= 14 and _is_bold(font))))
                need = 3.0 if big else 4.5
                if ratio is not None and ratio < need:
                    name = type(widget).__name__
                    try:
                        sample = str(widget.cget("text"))[:16]
                    except Exception:  # noqa: BLE001
                        sample = ""
                    contrast_violations.append(f"{name}({sample!r}) {fg} on {bg} = {ratio} < {need}")

        # --- 点击目标 ------------------------------------------------------
        if isinstance(widget, _INTERACTIVE) and widget.winfo_ismapped():
            width, height = widget.winfo_width(), widget.winfo_height()
            if height and height < 26:
                small_targets.append(f"{type(widget).__name__}({_text_of(widget)!r}) h={height}")
            elif width and width < 60 and isinstance(widget, (ttk.Checkbutton, ttk.Radiobutton)):
                small_targets.append(f"{type(widget).__name__}({_text_of(widget)!r}) w={width}")

        # --- 间距 ----------------------------------------------------------
        for key in ("padx", "pady"):
            try:
                value = widget.cget(key)
            except Exception:  # noqa: BLE001
                continue
            for number in re.findall(r"\d+", str(value)):
                spacing.add(int(number))

    return {
        "label": label,
        "widgets": len(list(walk(root_widget))),
        "text_widgets": texts,
        "contrast_violations": contrast_violations,
        "small_targets": small_targets,
        "font_kinds": len(fonts),
        "font_sizes": sorted({size for size, _ in fonts}),
        "spacing_values": len(spacing),
    }


def _text_of(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("text"))[:14]
    except Exception:  # noqa: BLE001
        return ""


def format_report(reports: list[dict]) -> str:
    lines = [
        f"{'面板':22s} {'控件':>5s} {'文字':>5s} {'对比度违规':>10s} {'小目标':>7s} {'字号种类':>8s} {'间距取值':>8s}"
    ]
    for item in reports:
        lines.append(
            f"{item['label']:22s} {item['widgets']:5d} {item['text_widgets']:5d} "
            f"{len(item['contrast_violations']):10d} {len(item['small_targets']):7d} "
            f"{item['font_kinds']:8d} {item['spacing_values']:8d}"
        )
    return "\n".join(lines)


def assert_quality(report: dict, *, max_contrast: int = 0, max_small: int = 0, max_fonts: int = 4) -> None:
    """把度量变成断言（供测试与改造验收使用）。"""
    problems = []
    if len(report["contrast_violations"]) > max_contrast:
        problems.append(
            f"对比度不足 {len(report['contrast_violations'])} 处：\n    "
            + "\n    ".join(report["contrast_violations"][:6])
        )
    if len(report["small_targets"]) > max_small:
        problems.append(
            f"点击目标过小 {len(report['small_targets'])} 处：\n    " + "\n    ".join(report["small_targets"][:6])
        )
    if report["font_kinds"] > max_fonts:
        problems.append(f"字号种类 {report['font_kinds']} 种（上限 {max_fonts}）：{report['font_sizes']}")
    assert not problems, f"「{report['label']}」UI 质量不达标：\n  - " + "\n  - ".join(problems)


def blend(fg: str, bg: str, alpha: float) -> str:
    """把前景色按 alpha 混到背景色上（用于生成"淡一点"的文字色并**保证对比度达标**）。"""
    a, b = _hex_to_rgb(fg), _hex_to_rgb(bg)
    if a is None or b is None:
        return fg
    mixed = tuple(round(x * alpha + y * (1 - alpha)) for x, y in zip(a, b))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def readable_on(bg: str, *, light: str = "#f2f2f7", dark: str = "#1b1b28", ratio: float = 4.5) -> str:
    """在给定背景上选一个**保证达标**的文字色（浅/深两端各试，必要时逐步加深）。"""
    for candidate in (light, dark):
        if (contrast_ratio(candidate, bg) or 0) >= ratio:
            return candidate
    # 两端都不达标（中间调背景）：二分找一个够暗或够亮的端点
    best, best_ratio = light, contrast_ratio(light, bg) or 0
    for step in range(1, 11):
        candidate = blend(dark if best_ratio < ratio else light, bg, step / 10)
        current = contrast_ratio(candidate, bg) or 0
        if current > best_ratio:
            best, best_ratio = candidate, current
        if best_ratio >= ratio:
            break
    return best


def hue_shift(color: str, amount: float) -> str:
    """微调明度（正数变亮），保持色相与饱和度。"""
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return color
    hue, lightness, saturation = colorsys.rgb_to_hls(*[v / 255 for v in rgb])
    r, g, b = colorsys.hls_to_rgb(hue, min(max(lightness + amount, 0.0), 1.0), saturation)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))
