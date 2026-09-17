"""插图工坊面板 —— 把"名场面提示词"生成成插图（补全审计项 D10）。

## 为什么需要这个面板

审计发现 `ImageGenerator.generate()` **全仓零调用**：实例在 `lifecycle_ui` 建了，
但唯一用途是 `shell_ui` 里拼一句状态栏文案 `" + 文生图"`。
于是 `img_provider` / `img_api_base` / `img_model` / `img_width` / `img_height`
整组配置喂给了一个没人调用的对象 —— **界面上根本没有能生成一张图的路径**。

本面板就是那个缺失的调用入口，同时把已有产物接起来：
名场面检测写入的 `scene_prompts/*.txt`（含提示词、画面比例、镜头、构图等）
此前也只落盘、无人消费。

## 设计要点

- **不要求 PIL**：打包 EXE 的 spec **有意排除 `PIL`**（EXE 内的图片预览是既有的降级点），
  所以预览走 `try: from PIL ... except ImportError`，
  拿不到 PIL 时只显示文件路径 + 「打开图片目录」，功能不残废。
- **不阻塞界面**：生成是网络+等待（SD 一张图几十秒），走 `BackgroundRunner`
  回主线程后再碰控件（Tk 非线程安全）。
- **失败要说人话**：用 `ImageGenResult.message`，区分
  "未启用 / 连不上 / 模型名不对 / 超时"，而不是一句"生成失败"。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Optional

from loguru import logger

from app.async_runner import BackgroundRunner
from app.events import TOPIC_CHAPTER_SAVED, TOPIC_NOVEL_OPENED
from app.ui_style import UIStyle

from . import ui_kit
from .base import BasePanel

__all__ = ["IllustrationPanel"]


class IllustrationPanel(BasePanel):
    """把名场面提示词生成为插图。"""

    key = "illustration"
    title = "插图工坊"
    category = "创作素材"
    order = 80
    description = "用名场面提示词生成插图（ComfyUI / Stable Diffusion WebUI）"

    #: 小说切换与章节保存都会改变"有哪些提示词"，所以订阅这两个主题
    topics_of_interest = (TOPIC_NOVEL_OPENED, TOPIC_CHAPTER_SAVED)

    # ------------------------------------------------------------------ 构造

    def build(self, parent: tk.Widget) -> tk.Widget:
        C = UIStyle.COLORS
        self._prompts: list[Path] = []
        self._current: Optional[Path] = None
        self._runner = BackgroundRunner(ui=getattr(self.app, "root", None), log=self._log)
        self._busy = False

        body = tk.Frame(parent, bg=C["bg_dark"])
        body.pack(fill=tk.BOTH, expand=True)

        # ---- 顶部工具条：后端状态 + 三个动作
        bar = ui_kit.toolbar(body)
        bar["bar"].pack(fill=tk.X)  # ❗ toolbar 只返回三块 Frame，**不自行 pack**
        ui_kit.button(bar["left"], "检测后端", self._on_check, kind="ghost")
        ui_kit.button(bar["left"], "刷新提示词", self._on_reload, kind="ghost")
        ui_kit.button(bar["left"], "打开图片目录", self._on_open_dir, kind="ghost")
        self._status_badge = ui_kit.badge(bar["right"], "未检测", kind="info")

        # ---- 左：提示词列表；右：内容与生成
        split = tk.Frame(body, bg=C["bg_dark"])
        split.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        left = tk.Frame(split, bg=C["bg_dark"], width=280)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        ui_kit.section_title(left, "名场面提示词")
        # `pretty_tree` 返回的是 dict（frame/tree/scrollbar/sort_by），且 columns 是
        # **列名序列**、宽度另传 `widths` —— 与"传 (名,宽) 元组"的直觉写法不同。
        holder = ui_kit.pretty_tree(
            left,
            columns=["文件"],
            widths=[240],
            height=14,
            on_select=lambda _e: self._on_pick(),
        )
        holder["frame"].pack(fill=tk.BOTH, expand=True)
        self._tree = holder["tree"]
        self._tree_holder = holder

        right = tk.Frame(split, bg=C["bg_dark"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))

        ui_kit.section_title(right, "提示词内容")
        self._preview = tk.Text(
            right,
            height=12,
            wrap=tk.WORD,
            font=UIStyle.font("body"),
            bg=C["bg_card"],
            fg=C["text_primary"],
            relief=tk.FLAT,
            padx=8,
            pady=6,
        )
        self._preview.pack(fill=tk.BOTH, expand=True)
        self._preview.config(state=tk.DISABLED)

        actions = tk.Frame(right, bg=C["bg_dark"])
        actions.pack(fill=tk.X, pady=(6, 2))
        self._gen_btn = ui_kit.button(actions, "生成插图", self._on_generate, kind="primary")
        ui_kit.hint(actions, "生成结果保存到作品目录的 images/ 下")
        self._gen_btn.config(state=tk.DISABLED)

        self._hint = ui_kit.hint(right, "")
        self._hint.pack(fill=tk.X, pady=(6, 0))

        self._on_reload()
        # 与其它原生面板一致：构建完成必须显式标记，否则宿主会以为还没建好
        # 而重复构建（`host` 靠 `is_built` 判断走"复用"还是"重建"）。
        self.mark_built(True)
        return body

    # ------------------------------------------------------------------ 事件

    def on_show(self) -> None:
        # 切回面板时刷新一次：期间可能新建了章节、产生了新提示词
        self._on_reload()

    def on_event(self, topic: str, payload: Any = None) -> None:
        if topic in (TOPIC_NOVEL_OPENED, TOPIC_CHAPTER_SAVED):
            self._on_reload()

    # ------------------------------------------------------------------ 内部

    def _novel_dir(self) -> Optional[Path]:
        d = getattr(self, "current_novel_dir", None)
        return Path(d) if d else None

    def _generator(self):
        """取文生图器：宿主有就用宿主的，没有就按需造一个。

        宿主在 `lifecycle_ui` 里建过 `image_gen`；但不保证每个入口都走到那段，
        所以这里兜一层，避免"面板存在但宿主属性缺失"时整块功能消失。
        """
        gen = getattr(self.app, "image_gen", None)
        if gen is not None:
            return gen
        try:
            from app.image_generator import ImageGenerator

            gen = ImageGenerator(self.config)
            self.app.image_gen = gen
            return gen
        except Exception as exc:  # noqa: BLE001 - 构造失败要能显示出来
            logger.debug(f"[插图工坊] 构造 ImageGenerator 失败：{exc}")
            return None

    def _set_hint(self, text: str, kind: str = "info") -> None:
        self._hint.config(text=text)

    def _on_reload(self) -> None:
        novel = self._novel_dir()
        self._prompts = []
        if novel:
            d = novel / "scene_prompts"
            if d.is_dir():
                # 按文件名排序即按章节/序号排序（ch0001_epic_scene_1 → ch0002_...）
                self._prompts = sorted(d.glob("*.txt"))
        ui_kit.fill_tree(self._tree, [(p.name, (p.name,)) for p in self._prompts])
        if not self._prompts:
            self._current = None
            self._gen_btn.config(state=tk.DISABLED)
            self._set_hint("暂无提示词。生成章节后会自动写入 scene_prompts/，或先在编辑器里手动生成。")
        else:
            self._set_hint(f"共 {len(self._prompts)} 条提示词。选中一条后点「生成插图」。")

    def _on_pick(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if 0 <= idx < len(self._prompts):
            self._current = self._prompts[idx]
            try:
                text = self._current.read_text(encoding="utf-8")
            except OSError as exc:
                text = f"（读取失败：{exc}）"
            self._preview.config(state=tk.NORMAL)
            self._preview.delete("1.0", tk.END)
            self._preview.insert("1.0", text)
            self._preview.config(state=tk.DISABLED)
            self._gen_btn.config(state=tk.DISABLED if self._busy else tk.NORMAL)

    def _on_check(self) -> None:
        gen = self._generator()
        if gen is None:
            self._set_hint("文生图模块不可用", "error")
            return
        self._set_hint("正在检测后端…")
        self._runner.submit(gen.check_backend, on_success=self._after_check, on_finally=None)

    def _after_check(self, result) -> None:
        kind = "success" if result.ok else "error"
        self._status_badge.config(text=result.message, fg=UIStyle.COLORS.get(f"{kind}_text", ""))
        self._set_hint(result.message, kind)

    def _on_open_dir(self) -> None:
        novel = self._novel_dir()
        if not novel:
            self._set_hint("请先打开一本小说")
            return
        target = novel / "images"
        target.mkdir(parents=True, exist_ok=True)
        self._open_path(target)

    @staticmethod
    def _open_path(path: Path) -> None:
        """在系统文件管理器里打开目录（跨平台，失败不抛）。"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606 - 本地目录，非用户输入
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        except Exception as exc:  # noqa: BLE001 - 打不开目录不该影响其它功能
            logger.debug(f"[插图工坊] 打开目录失败：{exc}")

    def _on_generate(self) -> None:
        if self._busy:
            self._set_hint("上一张还在生成中…")
            return
        gen = self._generator()
        novel = self._novel_dir()
        if gen is None or novel is None:
            self._set_hint("文生图模块不可用，或尚未打开小说", "error")
            return
        if self._current is None:
            self._set_hint("请先选中一条提示词")
            return

        prompt = self._read_prompt_body(self._current)
        if not prompt:
            self._set_hint("提示词内容为空", "error")
            return

        self._busy = True
        self._gen_btn.config(state=tk.DISABLED, text="生成中…")
        self._set_hint("正在生成插图…（本地后端通常需要数十秒）")

        name = f"{self._current.stem}"
        self._runner.submit(
            gen.generate_to_novel,
            prompt,
            novel,
            name,
            on_success=self._after_generate,
            on_error=lambda exc: self._after_generate_error(exc),
            on_finally=self._reset_busy,
        )

    @staticmethod
    def _read_prompt_body(path: Path) -> str:
        """从提示词文件里取出真正用于生成的文本。

        文件由名场面检测写入，形如：
        ```
        章节: 第1章
        类型: 震撼场面
        场景: …（这句才是画面内容）
        画面比例: 16:9 (1024x576)
        ...
        AI提示词:
        …（这段最完整，优先用它）
        ```
        优先取 `AI提示词:` 之后的内容；没有该标记就退回 `场景:` 行；再不行用全文。
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return ""
        marker = "AI提示词:"
        if marker in text:
            body = text.split(marker, 1)[1].strip()
            if body:
                return body
        for line in text.splitlines():
            if line.startswith("场景:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    return value
        return text.strip()

    def _after_generate(self, result) -> None:
        if result.ok:
            where = f"，已保存到 {result.path.name}" if result.path else ""
            self._set_hint(f"{result.message}{where}", "success")
            self._maybe_preview(result.path)
        else:
            self._set_hint(result.message, "error")

    def _after_generate_error(self, exc: BaseException) -> None:
        self._set_hint(f"生成失败：{type(exc).__name__}: {exc}", "error")

    def _reset_busy(self) -> None:
        self._busy = False
        self._gen_btn.config(state=tk.NORMAL if self._current else tk.DISABLED, text="生成插图")

    def _maybe_preview(self, path: Optional[Path]) -> None:
        """有 PIL 就顺手预览；没有就跳过（打包 EXE 有意排除 PIL）。

        这里**必须**容忍 ImportError —— 与 `toolkit_ui` 的插图预览同一处理方式。
        """
        if path is None:
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        try:
            img = Image.open(path)
            img.thumbnail((360, 360))
            photo = ImageTk.PhotoImage(img)
            if not hasattr(self, "_preview_refs"):
                self._preview_refs = []
            self._preview_refs.append(photo)
            if getattr(self, "_thumb_label", None) is None:
                self._thumb_label = tk.Label(self._host_widget(), image=photo, bg=UIStyle.COLORS["bg_dark"])
            self._thumb_label.config(image=photo)
            self._thumb_label.pack(anchor=tk.W)
        except Exception as exc:  # noqa: BLE001 - 预览失败不影响"已生成"这个事实
            logger.debug(f"[插图工坊] 预览失败：{exc}")

    #: 供 `ui_kit.pretty_tree` 之外的测试引用（`ttk.Treeview` 实例）
    def _tree_widget(self) -> ttk.Treeview:
        return self._tree
