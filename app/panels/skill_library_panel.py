"""技能库面板（第 19 个面板）—— 让 `SKILL.md` 技能包**可见、可检索、可注入**。

## 它解决的问题

`skill_library.py` 能解析技能包，但"能解析"不等于"用户用得上"：

| 只有核心模块时 | 有本面板之后 |
|---|---|
| 用户不知道技能库在哪、怎么放 | 「导入技能」「登记目录」「打开技能库目录」 |
| 不知道一个技能包到底有什么规则 | 详情区显示规则分级、场景、调用参数、文件清单 |
| 不知道启用后会往提示词里塞什么 | 「预览注入」原样展示将注入的文本（含字数 / token） |
| 不知道手上这章该用哪个技能 | 「匹配当前稿件」按相关度排序并给出命中理由 |
| 启用了却没感觉 | 「一键应用」= 启用 + 立刻预览注入效果 |

## 两个设计取舍

1. **不执行技能自带的脚本**。预览只展示"将注入的提示词"，不是"跑一遍技能"。
   理由见 `skill_library.py` 模块文档：同等权限的 Python 无法沙箱化，
   把"运行别人的代码"藏在一个按钮后面是危险的设计。
2. **匹配是可解释的加权命中**，不是黑盒打分。面板会显示命中词，
   用户能判断"它推这个技能是不是因为我说了『去AI味』"，从而敢点应用。
"""

from __future__ import annotations

import hashlib
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Optional

from loguru import logger

from app import dialogs
from app.async_runner import BackgroundRunner
from app.skill_library import (
    LEVEL_LABELS,
    MatchResult,
    SkillLibrary,
    SkillResult,
    get_skill_library,
)
from app.style_dna import format_dna
from app.ui_style import UIStyle
from app.writing_presets import (
    PRESETS,
    build_rewrite_instruction,
    format_qc,
    get_preset_manager,
    qc_report,
)

from . import ui_kit
from .base import BasePanel

__all__ = ["SkillLibraryPanel", "match_report", "skill_detail_lines", "skill_rows"]

#: 资源角色 → 中文名（与 `skill_library._classify_file` 的取值一一对应）
_ROLE_LABELS = {
    "script": "脚本",
    "reference": "参考",
    "example": "示例",
    "asset": "素材",
    "doc": "文档",
    "other": "其它",
}


# ====================================================================== 纯函数（可单测）


def skill_rows(skills: list[dict]) -> list[tuple[str, tuple[str, ...]]]:
    """技能列表 → 表格行。提成纯函数是为了可脱离 Tk 单测。"""
    rows: list[tuple[str, tuple[str, ...]]] = []
    for info in skills:
        key = str(info.get("key", ""))
        name = str(info.get("name", key))
        stats = info.get("level_stats") or {}
        rules = str(info.get("rules_total") or sum(int(v) for v in stats.values()))
        scenarios = info.get("scenarios") or []
        scenario = str(scenarios[0]) if scenarios else "（未声明）"
        if len(scenario) > 18:
            scenario = scenario[:17] + "…"
        status = "已启用" if info.get("enabled") else "未启用"
        if info.get("mode") == "ref":
            status += "（引用）"
        rows.append((key, (name, rules, scenario, status)))
    return rows


def skill_detail_lines(info: dict) -> list[tuple[str, str]]:
    """技能详情 → `[(标题, 内容)]`；空内容不返回该项。"""
    if not info:
        return []
    lines: list[tuple[str, str]] = []
    lines.append(("名称", f"{info.get('name', '')}" + (f"  v{info['version']}" if info.get("version") else "")))
    if info.get("description"):
        lines.append(("说明", str(info["description"])))
    lines.append(("键", str(info.get("key", ""))))
    if info.get("license"):
        lines.append(("授权", str(info["license"])))
    lines.append(("状态", "已启用" if info.get("enabled") else "未启用"))
    lines.append(("来源", "库内副本" if info.get("mode") == "copy" else "外部登记（不复制）"))
    lines.append(("目录", str(info.get("root", ""))))

    scenarios = info.get("scenarios") or []
    lines.append(("适用场景", "；".join(str(s) for s in scenarios) if scenarios else "（技能未声明）"))
    triggers = info.get("triggers") or []
    if triggers:
        lines.append(("触发词", "、".join(f"「{t}」" for t in triggers)))

    stats = info.get("level_stats") or {}
    if stats:
        parts = [f"{LEVEL_LABELS.get(level, level)} {count} 条" for level, count in stats.items()]
        lines.append(("规则分级", " · ".join(parts)))
    rules = info.get("rules") or []
    if rules:
        blocked = [r for r in rules if not r.get("injectable", True)]
        lines.append(
            (
                "可注入",
                f"{len(rules) - len(blocked)} 条" + (f"（{len(blocked)} 条 X/H 级永不注入）" if blocked else ""),
            )
        )

    params = info.get("params") or []
    if params:
        rendered = []
        for param in params[:10]:
            flag = str(param.get("flag", ""))
            if param.get("takes_value", True):
                flag += " <值>"
            rendered.append(flag)
        more = f" 等 {len(params)} 个" if len(params) > 10 else ""
        lines.append(("调用参数", "、".join(rendered) + more))

    file_stats = info.get("file_stats") or {}
    if file_stats:
        rendered = [f"{_ROLE_LABELS.get(role, role)} {count}" for role, count in file_stats.items()]
        lines.append(("包含文件", " · ".join(rendered)))
    return lines


def match_report(matches: list[MatchResult], names: dict[str, str], text_len: int = 0) -> str:
    """把匹配结果渲染成一段人读的报告（面板弹窗用）。"""
    if not matches:
        return (
            "没有技能匹配到当前稿件。\n\n"
            "可能原因：\n"
            "  · 已导入的技能与该稿件题材/任务不同\n"
            "  · 技能没有声明触发词或适用场景\n"
            f"  · 稿件过短（当前 {text_len} 字），缺少判断依据"
        )
    lines = [f"按当前稿件（{text_len} 字）匹配到 {len(matches)} 个技能：", ""]
    for index, item in enumerate(matches, 1):
        name = names.get(item.key, item.key)
        reason = "、".join(item.reasons) if item.reasons else "无明确命中词"
        lines.append(f"{index}. {name}    相关度 {item.score:.0%}")
        lines.append(f"   命中：{reason}")
    lines.append("")
    lines.append("相关度只用于排序建议，不会自动启用技能 —— 请自行确认后再「一键应用」。")
    return "\n".join(lines)


def preview_text(data: dict) -> str:
    """把 `SkillLibrary.preview()` 的结果渲染成可读文本（含作者自带对照）。"""
    if not data.get("ok", True):
        return str(data.get("message", "预览失败"))
    name = data.get("name", "")
    stats = data.get("level_stats") or {}
    stats_text = " · ".join(f"{LEVEL_LABELS.get(k, k)} {v}" for k, v in stats.items()) or "无"
    parts = [
        f"技能：{name}",
        f"规则：共 {data.get('rules_total', 0)} 条，其中 {data.get('rules_injected', 0)} 条可注入"
        f"（X 级已否决 / H 级人审不注入）",
        f"分级：{stats_text}",
        f"注入量：{data.get('chars', 0)} 字 / 约 {data.get('tokens', 0)} tokens",
        "",
        "──────── 将注入写作提示词的内容 ────────",
        str(data.get("prompt", "")),
    ]
    examples = data.get("examples") or []
    if examples:
        parts.extend(["", "──────── 作者自带的改动示例 ────────"])
        for item in examples:
            parts.append(f"❌ {item.get('before', '')}")
            parts.append(f"✅ {item.get('after', '')}")
            parts.append("")
    warnings = data.get("warnings") or []
    if warnings:
        parts.extend(["", "解析提示：", *[f"  · {w}" for w in warnings]])
    return "\n".join(parts)


# ====================================================================== 面板


class SkillLibraryPanel(BasePanel):
    """技能库：导入 / 登记 / 检索 / 启停 / 预览 / 自动匹配。"""

    key = "skills"
    title = "技能库"
    category = "运维"
    order = 62
    description = "导入与管理 SKILL.md 技能包，把规则注入写作提示词（降低 AI 腔调）"

    #: 技能库与作品无关：切书不需要刷新。
    topics_of_interest = ()

    # ------------------------------------------------------------------ 构建

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._skills: list[dict[str, Any]] = []
        #: 两段式状态：`{preset, fingerprint, report}`。第二步只认这份报告。
        self._pending: Optional[dict[str, Any]] = None
        self._current = ""
        self._query = tk.StringVar(value="")
        self._busy = False
        # ❗ 原生面板不能假设宿主已绑定（自动化测试用 app=None）：
        # 直接传 self._log 会在未绑定时抛 AttributeError，导致整个 build 中断。
        self._runner = BackgroundRunner(ui=getattr(self.app, "root", None), log=self._log_safe)

        body = tk.Frame(parent, bg=C["bg_dark"])
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 工具条
        bar = ui_kit.toolbar(body)
        bar["bar"].pack(fill=tk.X)  # ❗ toolbar 不自行 pack
        # ❗ button / badge / section_title / hint **不自行 pack**，必须显式挂载
        ui_kit.button(bar["left"], "导入技能", self._on_import, kind="primary").pack(side=tk.LEFT)
        ui_kit.button(bar["left"], "登记目录", self._on_register, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0)
        )
        ui_kit.button(bar["left"], "重新扫描", self._on_reload, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0)
        )
        self._count_badge = ui_kit.badge(bar["right"], "未扫描", kind="info")
        self._count_badge.pack(side=tk.RIGHT)

        # ---- 写作预设行（把技能规则装配成「阶段 / 体裁 / 长度」三个维度的能力单元）
        # ❗ 预设与技能规则是**单选**关系（预设已含规则子集），所以放在同一面板里
        # 让用户一眼看到"现在生效的是哪一层"，而不是再开一个第 20 面板。
        preset_row = tk.Frame(body, bg=C["bg_dark"])
        preset_row.pack(fill=tk.X, pady=(ui_kit.SPACE["sm"], 0))
        ui_kit.section_title(preset_row, "写作预设").pack(side=tk.LEFT)
        self._preset_var = tk.StringVar(value="（自动选择）")
        self._preset_box = ttk.Combobox(
            preset_row,
            textvariable=self._preset_var,
            values=self._preset_labels(),
            state="readonly",
            width=28,
        )
        self._preset_box.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._preset_box.bind("<<ComboboxSelected>>", lambda _e: self._on_preset_pick())
        ui_kit.button(preset_row, "应用预设", self._on_preset_apply, kind="primary").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0)
        )
        ui_kit.button(preset_row, "质检当前稿件", self._on_qc, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["xs"], 0)
        )
        # 两段式的第二步：只有先跑过质检（有 pending 报告）才能生成改写指令
        ui_kit.button(preset_row, "生成改写指令", self._on_build_instruction, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["xs"], 0)
        )
        ui_kit.button(preset_row, "从成稿学风格", self._on_learn_style, kind="ghost").pack(
            side=tk.LEFT, padx=(ui_kit.SPACE["xs"], 0)
        )
        self._preset_badge = ui_kit.badge(preset_row, "未加载", kind="info")
        self._preset_badge.pack(side=tk.RIGHT)

        # ---- 搜索行（技能自动匹配之外的第二条查找路径）
        self._search = ui_kit.search_entry(
            body,
            self._query,
            placeholder="搜索技能 / 规则 / 触发词…",
            on_change=self._on_search,
        )
        self._search["frame"].pack(fill=tk.X, pady=(ui_kit.SPACE["sm"], ui_kit.SPACE["xs"]))

        # ---- 左右分栏
        split = tk.Frame(body, bg=C["bg_dark"])
        split.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        left = tk.Frame(split, bg=C["bg_dark"], width=430)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left.pack_propagate(False)
        ui_kit.section_title(left, "已登记技能").pack(anchor=tk.W, pady=(0, ui_kit.SPACE["xs"]))
        holder = ui_kit.pretty_tree(
            left,
            columns=["技能", "规则", "场景", "状态"],
            widths=[160, 48, 140, 76],
            height=13,
            on_select=lambda _e: self._on_pick(),
        )
        holder["frame"].pack(fill=tk.BOTH, expand=True)
        self._tree = holder["tree"]
        self._hint_line = ui_kit.hint(left, "")
        self._hint_line.pack(fill=tk.X, pady=(ui_kit.SPACE["xs"], 0))

        right = tk.Frame(split, bg=C["bg_dark"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        ui_kit.section_title(right, "技能详情").pack(anchor=tk.W, pady=(0, ui_kit.SPACE["xs"]))
        detail_box = ui_kit.scrollable(right)
        detail_box["frame"].pack(fill=tk.BOTH, expand=True)
        self._detail = tk.Text(
            detail_box["inner"],
            wrap=tk.WORD,
            font=UIStyle.font("body"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=8,
            pady=6,
            height=13,
        )
        self._detail.pack(fill=tk.BOTH, expand=True)
        self._detail.config(state=tk.DISABLED)

        actions = tk.Frame(right, bg=C["bg_dark"])
        actions.pack(fill=tk.X, pady=(6, 2))
        self._apply_btn = ui_kit.button(actions, "一键应用", self._on_apply, kind="primary")
        self._apply_btn.pack(side=tk.LEFT)
        self._preview_btn = ui_kit.button(actions, "预览注入", self._on_preview, kind="ghost")
        self._preview_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._match_btn = ui_kit.button(actions, "匹配当前稿件", self._on_match, kind="ghost")
        self._match_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._disable_btn = ui_kit.button(actions, "停用", self._on_disable, kind="ghost")
        self._disable_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))
        self._uninstall_btn = ui_kit.button(actions, "卸载", self._on_uninstall, kind="danger")
        self._uninstall_btn.pack(side=tk.LEFT, padx=(ui_kit.SPACE["sm"], 0))

        # ---- 底部：生效证据（"启用了" vs "注入了"）
        self._effect_line = ui_kit.hint(body, "")
        self._effect_line.pack(fill=tk.X, pady=(4, 0))

        self._on_reload()
        self.mark_built(True)  # ❗ 不标记会被宿主反复重建
        return body

    # ------------------------------------------------------------------ 生命周期

    def on_show(self) -> None:
        self._on_reload()

    # ------------------------------------------------------------------ 内部

    def _log_safe(self, message: str) -> None:
        host_log = getattr(self.app, "_log", None) if self.app is not None else None
        if callable(host_log):
            host_log(message)
        else:
            logger.debug(f"[技能库] {message}")

    def _library(self) -> Optional[SkillLibrary]:
        library = get_skill_library()
        if library is None:
            self._set_effect("技能库不可用（技能目录无法访问），本面板功能受限", "error")
        return library

    def _set_effect(self, text: str, kind: str = "info") -> None:
        try:
            self._effect_line.config(text=text)
        except tk.TclError:  # pragma: no cover - 面板已销毁
            pass

    def _selected_key(self) -> str:
        selection = self._tree.selection()
        return selection[0] if selection else ""

    def _info_of(self, key: str) -> dict[str, Any]:
        for info in self._skills:
            if str(info.get("key")) == key:
                return info
        return {}

    def _on_reload(self) -> None:
        library = self._library()
        if library is None:
            self._skills = []
            ui_kit.fill_tree(self._tree, [])
            self._set_detail("技能库不可用。")
            return
        library.reload()
        self._skills = library.list_skills()
        self._refresh_tree()
        enabled = sum(1 for info in self._skills if info.get("enabled"))
        self._count_badge.config(
            text=f"共 {len(self._skills)} 个 / 启用 {enabled}",
            fg=UIStyle.COLORS.get("warning_text" if library.load_failures else "text_secondary", ""),
        )
        failures = library.load_failures
        if failures:
            self._hint_line.config(
                text="；".join(f"{name}：{why}" for name, why in failures[:2]),
                fg=UIStyle.COLORS.get("warning_text", ""),
            )
        else:
            self._hint_line.config(text="", fg=UIStyle.COLORS.get("text_muted", ""))
        if not self._skills:
            self._set_detail(
                "技能库里还没有技能。\n\n"
                "点左上角「导入技能」选择来源：\n"
                "  · 技能目录（含 SKILL.md）\n"
                "  · ZIP 压缩包（解压后能找到 SKILL.md）\n\n"
                "也可以点「登记目录」直接引用本机已有的技能仓库（不复制文件）。\n\n"
                "❗ 本软件**只解析规则**，不会执行技能包里的脚本。"
            )
        self._refresh_effect()
        self._refresh_preset_badge()

    def _refresh_tree(self) -> None:
        query = self._query.get().strip()
        library = get_skill_library()
        skills = library.search(query) if (query and library) else None
        if skills is None:
            visible = self._skills
        else:
            keys = {s.key for s in skills}
            visible = [info for info in self._skills if info.get("key") in keys]
        ui_kit.fill_tree(self._tree, skill_rows(visible))

    def _refresh_effect(self) -> None:
        """底部"生效证据"：已启用技能**实际注入**了多少字。"""
        library = get_skill_library()
        if library is None:
            return
        enabled = library.enabled_skills()
        if not enabled:
            self._set_effect("当前没有已启用的技能 —— 启用后规则会在下次生成章节时注入提示词。")
            return
        context = library.prompt_context()
        self._set_effect(
            f"已生效：{len(enabled)} 个技能注入写作提示词（{len(context)} 字） · X 级已否决 / H 级人审规则不会被注入",
            "success",
        )

    def _on_search(self) -> None:
        self._refresh_tree()

    def _on_pick(self) -> None:
        key = self._selected_key()
        self._current = key
        info = self._info_of(key)
        if not info:
            return
        self._set_detail("\n".join(f"{title}：{value}" for title, value in skill_detail_lines(info)))
        self._apply_btn.config(text="重新应用" if info.get("enabled") else "一键应用")
        self._disable_btn.config(state=tk.NORMAL if info.get("enabled") else tk.DISABLED)

    # ------------------------------------------------------------------ 预设

    def _preset_labels(self) -> list[str]:
        """下拉项：第一项是「自动选择」，其余按维度标注。"""
        labels = ["（自动选择）"]
        for preset in PRESETS.values():
            labels.append(f"{preset.name} · {preset.dimension}")
        return labels

    def _preset_by_label(self, label: str) -> Optional[str]:
        """下拉文案 → 预设 key。"""
        for preset in PRESETS.values():
            if label == f"{preset.name} · {preset.dimension}":
                return preset.key
        return None

    def _on_preset_pick(self) -> None:
        self._refresh_preset_badge()

    def _on_preset_apply(self) -> None:
        manager = get_preset_manager()
        if manager is None:
            self._set_effect("写作预设不可用（状态文件无法访问）", "error")
            return
        label = self._preset_var.get()
        key = "" if label == "（自动选择）" else self._preset_by_label(label)
        if key is None:
            self._set_effect(f"无法识别的预设：{label}", "error")
            return
        ok, message = manager.activate(key)
        self._set_effect(message, "success" if ok else "error")
        self._refresh_preset_badge()
        if hasattr(self, "_effect_line"):
            self._refresh_effect()

    def _refresh_preset_badge(self) -> None:
        manager = get_preset_manager()
        if manager is None:
            self._preset_badge.config(text="未加载")
            return
        key = manager.active
        name = PRESETS[key].name if key in PRESETS else "自动选择"
        self._preset_badge.config(text=f"生效：{name}")

    def _on_learn_style(self) -> None:
        """从当前作品的成稿学习风格 DNA 草稿。

        刻意**不直接覆盖**已有 DNA：学习结果是统计草稿，覆盖掉用户手写的
        `tone` / `banned_words` 等于把人工信息冲成机器猜测。
        """
        novel_dir = getattr(self.app, "current_novel_dir", None) if self.app is not None else None
        if not novel_dir:
            self._set_effect("没有打开的作品 —— 需要先打开小说才能从成稿学习", "info")
            return
        try:
            from app.style_dna import learn_and_save, learn_from_novel

            dna = learn_from_novel(novel_dir)
            if dna is None:
                self._set_effect("本作品还没有章节（chapters/ 为空），无法学习风格", "info")
                return

            target = Path(novel_dir) / "风格DNA.json"
            if target.exists():
                preview = format_dna(dna)
                dialogs.show_text(
                    self._host_widget(),
                    "学习到的风格指纹（未覆盖已有文件）",
                    preview + chr(10) * 2 + f"⚠️ {target.name} 已存在，本次**未写入**。"
                    "如需采用，请先备份原文件后手动替换。",
                )
                self._set_effect("已生成指纹预览；已有 DNA 文件，未覆盖", "info")
                return

            ok, message = learn_and_save(novel_dir)
            self._set_effect(message, "success" if ok else "error")
            if ok:
                dialogs.show_text(self._host_widget(), "已生成风格 DNA 草稿", format_dna(dna))
        except Exception as exc:  # noqa: BLE001 - 学习是增强项，不该让面板崩
            logger.warning(f"[技能库] 学习风格失败：{exc}")
            self._set_effect(f"学习风格失败：{exc}", "error")

    def _on_qc(self) -> None:
        """对当前稿件跑质检：脚本层给数字，语义层只列待判读项。"""
        manager = get_preset_manager()
        text = self._current_text()
        if not text.strip():
            self._set_effect("没有可质检的正文：请先打开小说或写入内容", "info")
            return
        preset = manager.current(text=text) if manager is not None else None
        if preset is None:
            preset = PRESETS["qc-gate"]
        dna = self._load_dna()
        report = qc_report(text, preset, dna=dna)
        dialogs.show_text(
            self._host_widget(),
            f"写作质检 · {preset.name}",
            format_qc(report, preset.name),
        )
        # 记下这次报告对应的**稿件指纹**：第二步要校验稿件没变过
        self._pending = {
            "preset": preset.key,
            "fingerprint": self._text_fingerprint(text),
            "report": report,
            "dna": dna,
        }
        state = "通过" if report["ok"] else f"{report['blockers']} 项阻断"
        self._set_effect(
            f"质检完成：{state}（{report['passed']}/{report['total']} 项达标） —— 可点「生成改写指令」进入第二步",
            "success" if report["ok"] else "error",
        )

    def _text_fingerprint(self, text: str) -> str:
        """稿件指纹（sha1 前 16 位）。用于判断"报告是不是针对当前这版稿件"。"""
        return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]

    def _load_dna(self):
        """读当前作品的风格 DNA（没有作品或未配置时返回 None）。"""
        novel_dir = getattr(self.app, "current_novel_dir", None) if self.app is not None else None
        if not novel_dir:
            return None
        try:
            from app.style_dna import load_style_dna

            return load_style_dna(novel_dir)
        except Exception as exc:  # noqa: BLE001 - 风格 DNA 是加分项
            logger.debug(f"[技能库] 读取风格 DNA 失败：{exc}")
            return None

    def _on_build_instruction(self) -> None:
        """两段式的第二步：由**已完成的报告**生成改写指令。

        ❗ 这里必须校验前置条件。若允许"直接生成指令"，模型就会一步改完 ——
        技能包"先报告后改写"的闸门等于没有。
        """
        if not self._pending:
            self._set_effect(
                "请先点「质检当前稿件」生成报告 —— 改写指令只能由检测结论生成",
                "info",
            )
            return
        text = self._current_text()
        if self._text_fingerprint(text) != self._pending["fingerprint"]:
            self._pending = None
            self._set_effect("稿件在这次检测之后被修改过，请重新质检再生成指令", "error")
            return

        preset = PRESETS.get(self._pending["preset"]) or PRESETS["qc-gate"]
        instruction = build_rewrite_instruction(
            self._pending["report"],
            preset,
            dna=self._pending.get("dna"),
        )

        # 落到作品目录，便于复用与审计（不落盘就只是"弹窗一关就没了"）
        saved = ""
        novel_dir = getattr(self.app, "current_novel_dir", None) if self.app is not None else None
        if novel_dir:
            try:
                workspace = Path(novel_dir) / "_去AI味工作区"
                workspace.mkdir(parents=True, exist_ok=True)
                target = workspace / "改写指令.md"
                target.write_text(instruction, encoding="utf-8")
                saved = f"（已写入 {target.name}）"
            except OSError as exc:
                logger.warning(f"[技能库] 改写指令落盘失败：{exc}")

        dialogs.show_text(self._host_widget(), "改写指令（可复制给 Agent）", instruction)
        self._set_effect(f"改写指令已生成{saved}：复制给 Agent 执行第二步", "success")

    # ------------------------------------------------------------------ 动作

    def _on_import(self) -> None:
        if self._busy:
            self._set_effect("正在处理上一个技能，请稍候…")
            return
        library = self._library()
        if library is None:
            return
        choice = dialogs.ask_text(
            self._host_widget(),
            "导入技能",
            "选择来源类型并填入内容：\n\n  dir  —— 技能目录（含 SKILL.md）\n  zip  —— ZIP 压缩包\n\n请输入 dir / zip：",
        )
        if choice is None:
            return
        kind = choice.strip().lower()
        if kind == "dir":
            source = filedialog.askdirectory(title="选择技能目录") or ""
        elif kind == "zip":
            source = (
                filedialog.askopenfilename(
                    title="选择技能 ZIP",
                    filetypes=[("ZIP 压缩包", "*.zip"), ("所有文件", "*.*")],
                )
                or ""
            )
        else:
            self._set_effect("来源类型无效，请输入 dir / zip", "error")
            return
        if not source:
            return
        self._busy = True
        self._set_effect(f"正在导入：{source} …")
        # 复制/解压是磁盘操作，放后台线程，回主线程再碰控件（Tk 非线程安全）
        self._runner.submit(library.install, source, on_success=self._after_import, on_finally=self._clear_busy)

    def _clear_busy(self) -> None:
        self._busy = False

    def _after_import(self, result: SkillResult) -> None:
        if not isinstance(result, SkillResult):
            self._set_effect("导入返回了非预期结果", "error")
            return
        self._set_effect(result.message, "success" if result.ok else "error")
        if result.security_warning:
            # 用模态而不是底栏：用户必须知道"这个包里带了可执行代码"
            dialogs.showwarning("安全提示", result.security_warning)
        self._on_reload()
        if result.ok:
            self._select(result.skill_key)

    def _on_register(self) -> None:
        library = self._library()
        if library is None:
            return
        source = filedialog.askdirectory(title="选择要登记的技能目录") or ""
        if not source:
            return
        result = library.register(source)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        if result.ok:
            self._select(result.skill_key)

    def _select(self, key: str) -> None:
        if key and self._tree.exists(key):
            self._tree.selection_set(key)
            self._tree.see(key)
            self._on_pick()

    def _on_apply(self) -> None:
        """一键应用 = 启用 + 立刻预览注入效果。

        为什么不是"改正文"：技能的规则是**写作约束**，真正生效点在生成时。
        启用后直接展示将注入的内容，用户才能确认"我应用的是什么"。
        """
        library = self._library()
        key = self._selected_key()
        if library is None or not key:
            self._set_effect("请先在左侧选中一个技能", "info")
            return
        result = library.enable(key)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._select(key)
        self._on_preview()

    def _on_disable(self) -> None:
        library = self._library()
        key = self._selected_key()
        if library is None or not key:
            return
        result = library.disable(key)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._on_reload()
        self._select(key)

    def _on_preview(self) -> None:
        library = self._library()
        key = self._selected_key()
        if library is None or not key:
            self._set_effect("请先在左侧选中一个技能", "info")
            return
        data = library.preview(key)
        dialogs.show_text(self._host_widget(), f"注入预览 · {data.get('name', key)}", preview_text(data))

    def _current_text(self) -> str:
        """取当前稿件正文：优先编辑器实时内容，退回当前章节文件。"""
        app = self.app
        editor = getattr(app, "content_text", None) if app is not None else None
        if editor is not None:
            try:
                text = editor.get("1.0", tk.END)
                if text and text.strip():
                    return text
            except tk.TclError:  # pragma: no cover - 控件已销毁
                pass
        novel_dir = getattr(app, "current_novel_dir", None) if app is not None else None
        chapter = getattr(app, "current_chapter", 0) if app is not None else 0
        if novel_dir:
            path = Path(novel_dir) / "chapters" / f"chapter_{int(chapter or 0):04d}.txt"
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        return ""

    def _on_match(self) -> None:
        library = self._library()
        if library is None:
            return
        text = self._current_text()
        if not text.strip():
            self._set_effect("没有可匹配的正文：请先打开小说或在新章节里写入内容", "info")
            return
        matches = library.match(text)
        names = {str(info.get("key")): str(info.get("name")) for info in self._skills}
        self._set_effect(
            f"已按当前稿件（{len(text)} 字）匹配：{len(matches)} 个候选"
            if matches
            else f"当前稿件（{len(text)} 字）未匹配到技能",
            "success" if matches else "info",
        )
        if matches:
            self._select(matches[0].key)
        dialogs.show_text(
            self._host_widget(),
            "技能自动匹配",
            match_report(matches, names, len(text)),
        )

    def _on_uninstall(self) -> None:
        library = self._library()
        key = self._selected_key()
        if library is None or not key:
            return
        info = self._info_of(key)
        name = str(info.get("name", key))
        if info.get("mode") == "ref":
            message = f"确定要取消登记「{name}」吗？\n\n这是外部目录，**不会删除任何文件**，只移除登记项。"
        else:
            message = f"确定要删除技能「{name}」的全部文件吗？此操作不可撤销。"
        if not dialogs.confirm(message, title="卸载技能", parent=self._host_widget()):
            return
        result = library.uninstall(key)
        self._set_effect(result.message, "success" if result.ok else "error")
        self._current = ""
        self._on_reload()
        self._set_detail("已卸载。")
