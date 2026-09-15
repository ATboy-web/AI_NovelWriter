"""
AI自动写小说系统 - 桌面应用程序
集成AI API、长上下文记忆、智能体机制

架构说明 (P2-1 巨石拆分):
    本文件原为 8394 行的单一巨型类。现已重建为「薄编排层」：
    应用的全部方法按功能域拆入 app/ 下的 12 个 Mixin 模块，
    由 NovelWriterApp 多重继承聚合；本文件仅保留导入、类声明与 __init__。

    功能域 Mixin 一览:
        app/shell_ui.py         应用外壳(主窗口构建/运行循环/日志/状态栏/帮助)
        app/lifecycle_ui.py     小说生命周期(新建/打开/载入/续写/续集/设置/导入分析)
        app/generation_ui.py    业务生成(设定/大纲/章节/审校/风格/EXP/批量创作/扩写)
        app/character_ui.py     角色(卡片/详情/传记/增删改/装备技能/同步)
        app/outline_ui.py       大纲(整体与故事大纲读写/条目管理/上下文注入)
        app/chapter_ui.py       章节(显示/保存/切换/导出/选择器)
        app/editor_ui.py        编辑器(正文编辑/右键菜单/全屏写作)
        app/reader_ui.py        阅读器(书库/书签/书内搜索)
        app/timeline_ui.py      时间线与分支(时间线可视化/分支小说)
        app/toolkit_ui.py       工具(格式转换/插图封面/云同步)
        app/persistence_ui.py   持久化(备份/检查点/断电恢复/原子写)
        app/note_ui.py          笔记(增删改查/便签)

    重构保证: 各 Mixin 内的方法体与原 NovelWriterApp 逐字节一致，行为不变。
"""

# 标准库
import threading
from pathlib import Path

# GUI
import tkinter as tk

# 结构化日志
from loguru import logger

# 小说工具集
from novel_toolkit import ElementLibrary, BridgeLibrary, DescriptionLibrary
from cloud_storage import CloudStorageManager
from app.navigation import NavigationManager

# 从 app 包导入核心类
from app import (AppConfig, AIClient, ImageGenerator,
                 NoteManager, ReadingManager, UIStyle, __version__)

from app.panels import (ElementsPanelMixin, BridgesPanelMixin,
                        DescriptionsPanelMixin, DialoguePanelMixin,
                        StoryFlowPanelMixin, StylePanelMixin,
                        AdaptPanelMixin, WebSearchPanelMixin,
                        MemoryVizPanelMixin, SummaryMgmtPanelMixin,
                        BatchOpsPanelMixin, ChapterAnalysisPanelMixin)

from app.writing_skills_panel import WritingSkillsPanelMixin

# ==================== P2-1 拆分出的功能域 Mixin ====================
from app.shell_ui import ShellMixin
from app.lifecycle_ui import NovelLifecycleMixin
from app.generation_ui import GenerationMixin
from app.character_ui import CharacterUIMixin
from app.outline_ui import OutlineUIMixin
from app.chapter_ui import ChapterUIMixin
from app.editor_ui import EditorUIMixin
from app.reader_ui import ReaderUIMixin
from app.timeline_ui import TimelineMixin
from app.toolkit_ui import ToolkitUIMixin
from app.persistence_ui import PersistenceMixin
from app.note_ui import NoteUIMixin


class NovelWriterApp(
    ShellMixin,
    NovelLifecycleMixin,
    GenerationMixin,
    CharacterUIMixin,
    OutlineUIMixin,
    ChapterUIMixin,
    EditorUIMixin,
    ReaderUIMixin,
    TimelineMixin,
    ToolkitUIMixin,
    PersistenceMixin,
    NoteUIMixin,
    WritingSkillsPanelMixin,
    ElementsPanelMixin, BridgesPanelMixin, DescriptionsPanelMixin,
    DialoguePanelMixin, StoryFlowPanelMixin, StylePanelMixin,
    AdaptPanelMixin, WebSearchPanelMixin, MemoryVizPanelMixin,
    SummaryMgmtPanelMixin, BatchOpsPanelMixin, ChapterAnalysisPanelMixin
):
    """AI自动写小说主应用（薄编排层，业务方法见各功能域 Mixin）"""

    def __init__(self):
        self.config = AppConfig()
        self.ai_client = AIClient(self.config)
        self.image_gen = ImageGenerator(self.config)
        self.note_manager = NoteManager(config=self.config)
        self.reading_manager = ReadingManager(self.config)

        # 工具集
        self.element_lib = ElementLibrary()
        self.bridge_lib = BridgeLibrary()
        self.desc_lib = DescriptionLibrary()
        self.dialogue_engine = None
        self.story_flow_engine = None
        self.style_engine = None
        self.adapt_engine = None
        self.web_search_engine = None
        self.character_system = None
        self.format_converter = None
        self.image_manager = None
        self.cloud_storage = CloudStorageManager()

        self.current_novel_dir = None
        self.memory = None
        self.agent = None
        self.outline = []
        self.current_chapter = 0
        self.is_modified = False  # 文档是否已修改
        self._state_lock = threading.Lock()  # 保护共享状态的锁
        self._exp_awarded_chapters = set()   # 防止同一章节重复发放EXP

        # 创建GUI
        self.root = tk.Tk()
        self.root.title(f"AI小说创作工坊 v{__version__}")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)

        # 设置图标
        try:
            icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception as e:
            logger.debug(f"图标加载失败（非致命）: {e}")

        # 应用主题
        UIStyle.apply_theme(self.root)

        self.nav_manager = NavigationManager(self)
        self.nav_manager.create_menu()
        self._create_widgets()
        self._update_status()

        # 绑定快捷键
        self.root.bind('<Control-s>', lambda e: self._save_chapter())
        self.root.bind('<Control-n>', lambda e: self._new_novel())
        self.root.bind('<Control-o>', lambda e: self._open_novel())
        self.root.bind('<F11>', lambda e: self._open_fullscreen_writer())


# ==================== 入口 ====================

if __name__ == "__main__":
    app = NovelWriterApp()
    app.run()
