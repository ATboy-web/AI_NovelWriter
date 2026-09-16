"""小说生命周期层：新建/打开/载入/续写/续集/外传/设置/简介/导入分析

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import shutil
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from loguru import logger

from app import AIClient, ImageGenerator, MemoryManager, NoteManager, NovelAgent, UIStyle
from app.events import TOPIC_CONFIG_CHANGED, TOPIC_NOVEL_CLOSED, TOPIC_NOVEL_OPENED


class NovelLifecycleMixin:
    """小说生命周期层：新建/打开/载入/续写/续集/外传/设置/简介/导入分析"""

    # ===== v3 P4：领域事件出口 =====

    def _announce_novel_opened(self, novel_dir):
        """广播 `novel.opened`（必要时先广播 `novel.closed`），让全部面板刷新到新小说（v3 §2.3）。

        统一收在这里，而不是散在 4 个打开入口里：新建 / 打开 / 续集 / 同人
        四条路径共用同一处发起，将来加第 5 条路径也不会漏。

        ⚠️ 调用时机：本方法只在入口把 `current_novel_dir` 改成新目录**之后**才被调用
        （4 处入口都是这个顺序），因此 `novel.closed` 的载荷里显式带上旧目录 ——
        订阅方不要在这个事件里读 `app.current_novel_dir`，那时它已经指向新书了。
        """
        events = getattr(self, "events", None)
        if events is None:
            return

        previous = getattr(self, "_announced_novel_dir", None)
        if previous and previous != str(novel_dir):
            self._publish_event(TOPIC_NOVEL_CLOSED, {"novel_dir": previous})
        self._announced_novel_dir = str(novel_dir)

        title = ""
        try:
            meta = json.loads((Path(novel_dir) / "meta.json").read_text(encoding="utf-8"))
            title = meta.get("title") or meta.get("original_title") or ""
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as e:
            # 标题只用于界面展示与日志，读不到不影响广播
            logger.debug(f"读取 meta.json 标题失败（不影响 novel.opened 广播）: {e}")
        self._publish_event(TOPIC_NOVEL_OPENED, {"novel_dir": str(novel_dir), "title": title})

    def _new_novel(self):
        """新建小说 - 支持用户输入想法"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建小说")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(900, sw - 60), int(sh * 0.88)
        x, y = (sw - w) // 2, (sh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.resizable(True, True)
        dialog.minsize(650, 700)
        dialog.transient(self.root)
        dialog.grab_set()

        C = UIStyle.COLORS

        # ===== 顶部固定区域 =====
        top = tk.Frame(dialog, bg=C["bg_dark"])
        top.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(8, 0))

        tk.Label(top, text="小说标题:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).grid(
            row=0, column=0, sticky=tk.W, pady=3
        )
        title_entry = tk.Entry(
            top,
            font=("微软雅黑", 10),
            bg=C["bg_card"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
            relief=tk.FLAT,
            width=40,
        )
        title_entry.grid(row=0, column=1, sticky=tk.EW, padx=(5, 0), pady=3)

        # 用户想法输入框
        tk.Label(top, text="你的想法:", bg=C["bg_dark"], fg=C["warning"], font=("微软雅黑", 9, "bold")).grid(
            row=1, column=0, sticky=tk.NW, pady=3
        )
        idea_frame = tk.Frame(top, bg=C["bg_dark"])
        idea_frame.grid(row=1, column=1, sticky=tk.EW, padx=(5, 0), pady=3)

        idea_text = tk.Text(
            idea_frame,
            font=("微软雅黑", 9),
            bg=C["bg_card"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
            relief=tk.FLAT,
            height=4,
            wrap=tk.WORD,
        )
        idea_text.pack(fill=tk.X)
        idea_text.insert("1.0", "例如：一个现代程序员穿越到修仙世界，用编程思维修炼...")

        # 点击时清空提示文字
        def clear_placeholder(event):
            if idea_text.get("1.0", tk.END).strip() == "例如：一个现代程序员穿越到修仙世界，用编程思维修炼...":
                idea_text.delete("1.0", tk.END)

        idea_text.bind("<FocusIn>", clear_placeholder)

        # 快速模板
        tk.Label(top, text="快速模板:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        template_var = tk.StringVar(value="无")
        template_combo = ttk.Combobox(top, textvariable=template_var, state="readonly", width=35)
        template_combo["values"] = ["无", "穿越异世", "重生归来", "系统流", "都市异能", "修仙问道"]
        template_combo.grid(row=2, column=1, sticky=tk.EW, padx=(5, 0), pady=3)

        # 模板变量输入区域
        template_vars_frame = tk.Frame(top, bg=C["bg_dark"])
        template_vars_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=3)

        template_entries = {}

        TEMPLATES = {
            "穿越异世": {
                "genre": "玄幻-异世大陆",
                "tags": ["穿越", "异世界"],
                "template": "一道白光闪过，{name}睁开眼发现自己躺在陌生的{place}，身边站着一位{creature}。",
                "vars": {"name": ("主角名", "李云"), "place": ("地点", "竹林"), "creature": ("人物", "白发老者")},
            },
            "重生归来": {
                "genre": "都市-都市异能",
                "tags": ["重生", "复仇"],
                "template": "当{name}再次睁开眼，发现自己回到了{year}年，一切还来得及改变。",
                "vars": {"name": ("主角名", "张伟"), "year": ("年份", "2010")},
            },
            "系统流": {
                "genre": "玄幻-东方玄幻",
                "tags": ["系统流", "升级"],
                "template": "叮！恭喜宿主{name}激活{system_name}系统，当前等级：Lv.1。",
                "vars": {"name": ("主角名", "王明"), "system_name": ("系统名", "万界商城")},
            },
            "都市异能": {
                "genre": "都市-都市异能",
                "tags": ["异能", "都市"],
                "template": "一场意外让{name}获得了{ability}的能力，从此生活发生了翻天覆地的变化。",
                "vars": {"name": ("主角名", ""), "ability": ("能力", "透视")},
            },
            "修仙问道": {
                "genre": "仙侠-古典仙侠",
                "tags": ["修仙", "问道"],
                "template": "少年{name}偶得{treasure}，踏上漫漫修仙路。",
                "vars": {"name": ("主角名", "陈轩"), "treasure": ("宝物", "上古功法")},
            },
        }

        def on_template_change(event=None):
            # 清除旧的模板变量输入框
            for widget in template_vars_frame.winfo_children():
                widget.destroy()
            template_entries.clear()

            template_name = template_var.get()
            if template_name == "无":
                return

            template = TEMPLATES.get(template_name, {})
            vars_def = template.get("vars", {})

            row = 0
            col = 0
            for var_name, (label, default) in vars_def.items():
                lbl = tk.Label(
                    template_vars_frame, text=f"{label}:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 8)
                )
                lbl.grid(row=row, column=col * 2, sticky=tk.W, padx=(0, 3), pady=1)
                entry = tk.Entry(
                    template_vars_frame, font=("微软雅黑", 8), bg=C["bg_card"], fg=C["text_primary"], width=12
                )
                entry.insert(0, default)
                entry.grid(row=row, column=col * 2 + 1, padx=(0, 10), pady=1)
                template_entries[var_name] = entry
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

        template_combo.bind("<<ComboboxSelected>>", on_template_change)

        tk.Label(top, text="小说频道:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).grid(
            row=4, column=0, sticky=tk.W, pady=3
        )
        channel_var = tk.StringVar(value="male")
        ch_frame = tk.Frame(top, bg=C["bg_dark"])
        ch_frame.grid(row=4, column=1, sticky=tk.W, padx=(5, 0), pady=3)

        # 男女频类型列表
        MALE_GENRES = [
            "玄幻-东方玄幻",
            "玄幻-异世大陆",
            "玄幻-高武世界",
            "玄幻-王朝争霸",
            "玄幻-宗门林立",
            "仙侠-古典仙侠",
            "仙侠-现代修真",
            "仙侠-洪荒封神",
            "仙侠-修真文明",
            "仙侠-凡人修仙",
            "都市-都市生活",
            "都市-都市异能",
            "都市-青春校园",
            "都市-商战职场",
            "都市-娱乐明星",
            "历史-架空历史",
            "历史-两宋元明",
            "历史-三国争霸",
            "历史-秦汉三国",
            "历史-五代十国",
            "科幻-星际文明",
            "科幻-末世危机",
            "科幻-时空穿梭",
            "科幻-赛博朋克",
            "科幻-机甲战争",
            "悬疑-灵异恐怖",
            "悬疑-侦探推理",
            "悬疑-探险揭秘",
            "悬疑-盗墓笔记",
            "悬疑-法医刑侦",
            "游戏-电子竞技",
            "游戏-虚拟网游",
            "游戏-游戏异界",
            "游戏-游戏制作",
            "游戏-数据流",
            "军事-抗战烽火",
            "军事-谍战特工",
            "军事-战争幻想",
            "军事-特种兵",
            "军事-谍战风云",
            "武侠-传统武侠",
            "武侠-国术古武",
            "武侠-武侠幻想",
            "武侠-古武未来",
            "武侠-江湖恩怨",
            "体育-篮球风云",
            "体育-足球天下",
            "体育-综合竞技",
            "体育-格斗搏击",
            "体育-赛车竞速",
            "轻小说-原生幻想",
            "轻小说-搞笑吐槽",
            "轻小说-恋爱日常",
            "轻小说-异世界",
            "轻小说-魔法少女",
            "二次元-青春日常",
            "二次元-变身入替",
            "二次元-同人衍生",
            "二次元-穿越动漫",
            "二次元-系统穿越",
            "无限流-诸天万界",
            "无限流-副本挑战",
            "无限流-轮回空间",
            "无限流-世界穿梭",
            "系统流-签到系统",
            "系统流-抽奖系统",
            "系统流-任务系统",
            "系统流-模拟器",
            "末日-丧尸末日",
            "末日-废土求生",
            "末日-病毒危机",
            "末日-冰河世纪",
            "克苏鲁-神话恐怖",
            "克苏鲁-未知恐惧",
            "克苏鲁-理智崩坏",
            "赛博朋克-赛博修仙",
            "赛博朋克-数字生命",
            "赛博朋克-虚拟现实",
        ]
        FEMALE_GENRES = [
            "古代言情-女尊王朝",
            "古代言情-宫闱宅斗",
            "古代言情-穿越奇情",
            "古代言情-种田经商",
            "古代言情-江湖侠女",
            "现代言情-豪门总裁",
            "现代言情-都市婚恋",
            "现代言情-职场丽人",
            "现代言情-娱乐圈",
            "现代言情-军婚甜宠",
            "幻想言情-异世恋歌",
            "幻想言情-快穿攻略",
            "幻想言情-魔法幻情",
            "幻想言情-星际恋歌",
            "幻想言情-兽世奇缘",
            "纯爱-古代纯爱",
            "纯爱-现代纯爱",
            "纯爱-幻想纯爱",
            "纯爱-星际纯爱",
            "纯爱-电竞纯爱",
            "耽美-古代耽美",
            "耽美-现代耽美",
            "耽美-校园耽美",
            "耽美-娱乐圈耽美",
            "浪漫青春-青春校园",
            "浪漫青春-疼痛成长",
            "浪漫青春-纯爱唯美",
            "浪漫青春-暗恋成真",
            "浪漫青春-双向奔赴",
            "仙侠奇缘-古典仙缘",
            "仙侠奇缘-修仙情劫",
            "仙侠奇缘-洪荒情缘",
            "仙侠奇缘-凡人仙缘",
            "悬疑灵异-推理侦探",
            "悬疑灵异-恐怖惊悚",
            "悬疑灵异-灵异鬼怪",
            "悬疑灵异-法医档案",
            "游戏竞技-电子竞技",
            "游戏竞技-全息网游",
            "游戏竞技-电竞爱情",
            "游戏竞技-游戏主播",
            "短篇-短篇言情",
            "短篇-微小说",
            "短篇-轻小说",
            "短篇-同人小说",
            "百合-古代百合",
            "百合-现代百合",
            "百合-幻想百合",
            "年代文-七八十年代",
            "年代文-知青岁月",
            "年代文-重生年代",
            "穿书-穿成炮灰",
            "穿书-穿成反派",
            "穿书-穿成女配",
            "重生-重生复仇",
            "重生-重生逆袭",
            "重生-重生日常",
        ]

        tk.Label(top, text="小说类型:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).grid(
            row=5, column=0, sticky=tk.W, pady=3
        )
        genre_var = tk.StringVar(value=MALE_GENRES[0])
        genre_combo = ttk.Combobox(top, textvariable=genre_var, values=MALE_GENRES, state="readonly", width=35)
        genre_combo.grid(row=5, column=1, sticky=tk.EW, padx=(5, 0), pady=3)
        top.columnconfigure(1, weight=1)

        # 男生标签（8类 80+标签）
        MALE_TAGS = {
            "角色设定": [
                "废材崛起",
                "扮猪吃虎",
                "杀伐果断",
                "智商在线",
                "低调男主",
                "独行侠",
                "狠人大帝",
                "稳健型",
                "腹黑型",
                "热血少年",
                "冷面高手",
                "逍遥自在",
                "护短",
                "不圣母",
                "有底线",
                "重生者",
            ],
            "情节元素": [
                "系统流",
                "穿越大军",
                "重生复仇",
                "无敌流",
                "升级流",
                "种田流",
                "争霸流",
                "诸天流",
                "无限流",
                "签到流",
                "数据化",
                "聊天群",
                "直播流",
                "召唤流",
                "转生流",
                "模拟器",
            ],
            "世界观": [
                "异界大陆",
                "王朝争霸",
                "宗门林立",
                "末世废土",
                "星空宇宙",
                "灵气复苏",
                "赛博朋克",
                "求生冒险",
                "东方神话",
                "洪荒封神",
                "修真文明",
                "巫师世界",
            ],
            "爽点标签": [
                "越级挑战",
                "越阶杀敌",
                "装逼打脸",
                "逆天改命",
                "一人成军",
                "万古不朽",
                "超神之路",
                "武道巅峰",
                "碾压全场",
                "秀翻天",
                "骚操作",
                "神级操作",
            ],
            "成长路线": [
                "废柴逆袭",
                "天才陨落再起",
                "散修崛起",
                "赘婿翻身",
                "上门女婿",
                "退婚打脸",
                "回归都市",
                "隐世归来",
                "退役兵王",
                "回归豪门",
            ],
            "战斗风格": [
                "肉身成圣",
                "剑道独尊",
                "拳拳到肉",
                "法术流",
                "武技流",
                "炼丹大师",
                "阵法宗师",
                "器道大师",
                "驭兽师",
                "暗杀流",
                "群战之王",
            ],
            "感情线": [
                "单女主",
                "多女主",
                "后宫流",
                "无女主",
                "暧昧流",
                "青梅竹马",
                "天降系",
                "傲娇女主",
                "御姐型",
                "萝莉型",
                "病娇女主",
            ],
            "特殊设定": [
                "万界穿梭",
                "时间回溯",
                "读心术",
                "透视眼",
                "隐身术",
                "空间戒指",
                "金手指",
                "老爷爷",
                "神级血脉",
                "远古传承",
                "神器认主",
                "神兽伙伴",
            ],
        }
        FEMALE_TAGS = {
            "角色设定": [
                "甜宠女主",
                "女强逆袭",
                "马甲大佬",
                "团宠担当",
                "万人迷",
                "病娇偏执",
                "霸总老公",
                "白月光",
                "替身前妻",
                "软萌娇妻",
                "女王御姐",
                "萌宝来袭",
                "戏精女主",
                "佛系女主",
                "毒舌女主",
                "学霸女主",
            ],
            "情节元素": [
                "先婚后爱",
                "追妻火葬场",
                "带球跑",
                "契约婚姻",
                "养成系",
                "宅斗宫斗",
                "真假千金",
                "失忆重逢",
                "假戏真做",
                "隐婚密爱",
                "替身文学",
                "重生虐渣",
                "闪婚闪离",
                "破镜重圆",
                "日久生情",
                "强取豪夺",
            ],
            "气氛风格": [
                "虐恋情深",
                "欢喜冤家",
                "温馨治愈",
                "爆笑甜宠",
                "暗恋成真",
                "虐渣打脸",
                "逆袭爽文",
                "甜到齁",
                "虐到哭",
                "轻松欢脱",
                "高甜无虐",
                "玻璃渣里找糖",
            ],
            "甜宠类型": [
                "一见钟情",
                "日久生情",
                "暗恋成真",
                "宠妻狂魔",
                "双向奔赴",
                "青梅竹马",
                "师生恋",
                "姐弟恋",
                "大叔宠",
                "萌宝助攻",
                "豪门恩怨",
                "总裁文",
            ],
            "身份设定": [
                "豪门千金",
                "落魄千金",
                "穿越女主",
                "重生女主",
                "系统女主",
                "异能女主",
                "修仙女主",
                "古代女主",
                "现代女主",
                "末世女主",
                "娱乐圈女主",
                "军嫂文",
            ],
            "男主人设": [
                "霸道总裁",
                "冷面军少",
                "腹黑王爷",
                "温柔竹马",
                "傲娇少爷",
                "冰山校草",
                "禁欲系",
                "病娇男主",
                "忠犬男主",
                "渣男回头",
                "高冷学长",
                "阳光少年",
            ],
            "感情模式": [
                "甜宠",
                "先虐后甜",
                "先甜后虐",
                "甜虐交织",
                "高甜",
                "暗恋",
                "明恋",
                "单箭头",
                "双箭头",
                "三角恋",
                "四角恋",
                "骨科",
            ],
            "特殊元素": [
                "萌宝",
                "双胞胎",
                "龙凤胎",
                "穿越",
                "重生",
                "系统",
                "空间",
                "异能",
                "修仙",
                "娱乐圈",
                "豪门",
                "校园",
            ],
        }

        # ===== 中间可滚动标签区域 =====
        tag_outer = tk.LabelFrame(
            dialog,
            text=" 附加标签（可多选，滚轮上下/左右移动） ",
            padx=5,
            pady=5,
            bg=C["bg_dark"],
            fg=C["accent_light"],
            font=("微软雅黑", 9),
        )
        tag_outer.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        tag_canvas = tk.Canvas(tag_outer, bg=C["bg_dark"], highlightthickness=0, bd=0, height=200)
        tag_scrollbar_y = tk.Scrollbar(tag_outer, orient=tk.VERTICAL, command=tag_canvas.yview)
        tag_scrollbar_x = tk.Scrollbar(tag_outer, orient=tk.HORIZONTAL, command=tag_canvas.xview)
        tag_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        tag_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        tag_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tag_canvas.configure(yscrollcommand=tag_scrollbar_y.set, xscrollcommand=tag_scrollbar_x.set)

        tags_container = tk.Frame(tag_canvas, bg=C["bg_dark"])
        tag_canvas_window = tag_canvas.create_window((0, 0), window=tags_container, anchor=tk.NW)

        # 鼠标滚轮滚动标签 - 支持上下和左右
        def on_tag_mousewheel(event):
            # 垂直滚动
            tag_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_tag_shift_mousewheel(event):
            # Shift+滚轮 = 水平滚动
            tag_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

        tag_canvas.bind("<MouseWheel>", on_tag_mousewheel)
        tag_canvas.bind("<Shift-MouseWheel>", on_tag_shift_mousewheel)
        tags_container.bind("<MouseWheel>", on_tag_mousewheel)
        tags_container.bind("<Shift-MouseWheel>", on_tag_shift_mousewheel)
        tag_outer.bind("<MouseWheel>", on_tag_mousewheel)
        tag_outer.bind("<Shift-MouseWheel>", on_tag_shift_mousewheel)

        # 使tags_container宽度跟随canvas
        def on_canvas_configure(event):
            tag_canvas.itemconfig(tag_canvas_window, width=event.width)

        tag_canvas.bind("<Configure>", on_canvas_configure)

        self.tag_vars = {}

        def update_tags(channel):
            """更新标签显示"""
            genre_combo["values"] = MALE_GENRES if channel == "male" else FEMALE_GENRES
            genre_var.set(MALE_GENRES[0] if channel == "male" else FEMALE_GENRES[0])
            for w in tags_container.winfo_children():
                w.destroy()
            self.tag_vars.clear()
            tags = MALE_TAGS if channel == "male" else FEMALE_TAGS
            for cat_name, cat_tags in tags.items():
                cat_label = tk.Label(
                    tags_container,
                    text=cat_name,
                    font=("微软雅黑", 9, "bold"),
                    bg=C["bg_dark"],
                    fg=C["accent_light"],
                    anchor=tk.W,
                )
                cat_label.pack(fill=tk.X, pady=(6, 1), padx=5)
                tag_line = tk.Frame(tags_container, bg=C["bg_dark"])
                tag_line.pack(fill=tk.X, padx=5)
                for tag in cat_tags:
                    var = tk.BooleanVar(value=False)
                    self.tag_vars[tag] = var
                    cb = tk.Checkbutton(
                        tag_line,
                        text=tag,
                        variable=var,
                        font=("微软雅黑", 8),
                        bg=C["bg_dark"],
                        fg=C["text_secondary"],
                        selectcolor=C["bg_card"],
                        activebackground=C["bg_dark"],
                        activeforeground=C["accent_light"],
                        relief=tk.FLAT,
                        padx=1,
                        pady=0,
                    )
                    cb.pack(side=tk.LEFT, padx=2, pady=1)
            tags_container.update_idletasks()
            tag_canvas.configure(scrollregion=tag_canvas.bbox("all"))
            tag_canvas.yview_moveto(0)

        # 频道选择
        for text, val in [("男生频道", "male"), ("女生频道", "female")]:
            rb = tk.Radiobutton(
                ch_frame,
                text=text,
                variable=channel_var,
                value=val,
                command=lambda v=val: update_tags(v),
                bg=C["bg_dark"],
                fg=C["text_primary"],
                selectcolor=C["bg_card"],
                activebackground=C["bg_dark"],
                activeforeground=C["accent_light"],
                font=("微软雅黑", 9),
            )
            rb.pack(side=tk.LEFT, padx=8)

        # 初始化标签
        update_tags("male")

        # 自定义标签输入
        custom_frame = tk.Frame(tag_outer, bg=C["bg_dark"])
        custom_frame.pack(fill=tk.X, padx=5, pady=(3, 0))
        tk.Label(custom_frame, text="自定义:", bg=C["bg_dark"], fg=C["text_secondary"], font=("微软雅黑", 8)).pack(
            side=tk.LEFT
        )
        custom_tag_entry = tk.Entry(
            custom_frame,
            font=("微软雅黑", 9),
            bg=C["bg_card"],
            fg=C["text_primary"],
            insertbackground=C["text_primary"],
            relief=tk.FLAT,
            width=20,
        )
        custom_tag_entry.pack(side=tk.LEFT, padx=3)

        def add_custom_tag():
            tag = custom_tag_entry.get().strip()
            if not tag:
                return
            if tag in self.tag_vars:
                messagebox.showinfo("提示", f"标签 '{tag}' 已存在")
                return
            var = tk.BooleanVar(value=True)
            self.tag_vars[tag] = var
            # 添加到最后一行
            last_line = None
            for w in tags_container.winfo_children():
                if isinstance(w, tk.Frame):
                    last_line = w
            if last_line is None:
                last_line = tk.Frame(tags_container, bg=C["bg_dark"])
                last_line.pack(fill=tk.X, padx=5)
            cb = tk.Checkbutton(
                last_line,
                text=tag,
                variable=var,
                font=("微软雅黑", 8),
                bg=C["bg_card"],
                fg=C["accent_light"],
                selectcolor=C["bg_dark"],
                activebackground=C["bg_card"],
                activeforeground=C["accent_light"],
                relief=tk.RAISED,
                padx=3,
                pady=1,
            )
            cb.pack(side=tk.LEFT, padx=2, pady=1)
            custom_tag_entry.delete(0, tk.END)
            self._log(f"添加自定义标签: {tag}")

        tk.Button(
            custom_frame,
            text="添加",
            command=add_custom_tag,
            font=("微软雅黑", 8),
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            padx=5,
        ).pack(side=tk.LEFT, padx=3)
        custom_tag_entry.bind("<Return>", lambda e: add_custom_tag())

        # ===== 底部固定区域 =====
        bottom = tk.Frame(dialog, bg=C["bg_dark"])
        bottom.pack(fill=tk.X, padx=15, pady=(0, 5), side=tk.BOTTOM)

        # 章节数 + 每章字数 + 创建按钮（同一行）
        action_row = tk.Frame(bottom, bg=C["bg_dark"])
        action_row.pack(fill=tk.X, pady=3)
        tk.Label(action_row, text="章节数:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).pack(
            side=tk.LEFT
        )
        chapters_var = tk.StringVar(value="20")
        tk.Spinbox(
            action_row,
            from_=1,
            to=500,
            textvariable=chapters_var,
            width=6,
            font=("微软雅黑", 9),
            bg=C["bg_card"],
            fg=C["text_primary"],
        ).pack(side=tk.LEFT, padx=5)

        tk.Label(action_row, text="每章字数:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).pack(
            side=tk.LEFT, padx=(15, 0)
        )
        word_count_var = tk.StringVar(value="10000")
        word_count_combo = ttk.Combobox(action_row, textvariable=word_count_var, width=8, font=("微软雅黑", 9))
        word_count_combo["values"] = ["1000", "2000", "3000", "5000", "8000", "10000", "15000", "20000"]
        word_count_combo.pack(side=tk.LEFT, padx=5)

        tk.Label(action_row, text="首次生成:", bg=C["bg_dark"], fg=C["text_primary"], font=("微软雅黑", 9)).pack(
            side=tk.LEFT, padx=(15, 0)
        )
        first_batch_var = tk.StringVar(value="0")  # 0=一次性全部生成
        tk.Spinbox(
            action_row,
            from_=0,
            to=100,
            textvariable=first_batch_var,
            width=4,
            font=("微软雅黑", 9),
            bg=C["bg_card"],
            fg=C["text_primary"],
        ).pack(side=tk.LEFT, padx=5)
        tk.Label(action_row, text="章(0=全部)", bg=C["bg_dark"], fg=C["text_secondary"], font=("微软雅黑", 8)).pack(
            side=tk.LEFT
        )

        def confirm():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("提示", "请输入小说标题")
                return

            genre_full = genre_var.get().split("-")
            genre = genre_full[0] if len(genre_full) > 0 else ""
            sub_genre = genre_full[1] if len(genre_full) > 1 else ""
            total_chapters = int(chapters_var.get())
            first_batch = int(first_batch_var.get())

            # 如果用户指定了首次生成章数，且小于总章节数
            if 0 < first_batch < total_chapters:
                chapters = first_batch
                self._log(f"首次生成{chapters}章，完成后可继续创作剩余章节")
            else:
                chapters = total_chapters

            # 获取用户想法
            user_idea = idea_text.get("1.0", tk.END).strip()
            if user_idea == "例如：一个现代程序员穿越到修仙世界，用编程思维修炼...":
                user_idea = ""

            concept = user_idea  # 优先使用用户想法

            # 收集选中的标签
            selected_tags = [tag for tag, var in self.tag_vars.items() if var.get()]

            # 处理模板
            template_name = template_var.get()
            if template_name != "无" and template_name in TEMPLATES:
                template_data = TEMPLATES[template_name]
                # 收集模板变量值
                vars_values = {}
                for var_name, entry in template_entries.items():
                    vars_values[var_name] = entry.get().strip()

                # 生成模板内容
                template_content = template_data["template"]
                for var_name, value in vars_values.items():
                    template_content = template_content.replace(f"{{{var_name}}}", value)

                # 使用模板的类型和标签
                if not selected_tags:
                    selected_tags = template_data.get("tags", [])

                # 保存模板内容到概念
                if not concept:
                    concept = template_content

            # 创建小说目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)

            # 保存小说元数据
            meta = {
                "title": title,
                "genre": genre,
                "sub_genre": sub_genre,
                "channel": channel_var.get(),
                "tags": selected_tags,
                "concept": concept,
                "chapter_count": chapters,  # 当前要生成的章节数
                "total_chapters": total_chapters,  # 用户期望的总章节数（预览模式下用）
                "word_count_per_chapter": int(word_count_var.get()),
                "created_at": datetime.now().isoformat(),
                "template": template_name if template_name != "无" else None,
            }
            with open(novel_dir / "meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            # 初始化
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()

            self.title_var.set(title)
            self.genre_var.set(f"{genre}-{sub_genre}")
            self.chapter_var.set(f"0/{total_chapters}")

            dialog.destroy()
            self._log(f"新建小说《{title}》({sub_genre}) 创建成功，目标{total_chapters}章，首先生成{chapters}章")

        tk.Button(
            action_row,
            text="创建小说",
            command=confirm,
            font=("微软雅黑", 10, "bold"),
            bg=C["accent"],
            fg="white",
            relief=tk.FLAT,
            padx=20,
            pady=3,
        ).pack(side=tk.RIGHT)

    def _open_novel(self):
        """打开小说 - 直接使用文件对话框"""
        novel_dir = filedialog.askdirectory(title="选择小说目录", initialdir=str(self.config.novels_dir))
        if not novel_dir:
            return

        self._load_novel(Path(novel_dir))

    def _load_novel(self, novel_dir: Path):
        """加载小说数据"""
        self._log(f"正在加载小说: {novel_dir}")

        meta_file = novel_dir / "meta.json"

        if not meta_file.exists():
            messagebox.showerror("错误", "该目录不是有效的小说目录")
            return

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self._log(f"读取meta.json成功: {meta.get('title')}")
        except Exception as e:
            messagebox.showerror("错误", f"读取meta.json失败: {e}")
            return

        try:
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self._log("设置current_novel_dir成功")
        except Exception as e:
            self._log(f"设置current_novel_dir失败: {e}")
            return

        try:
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self._log("MemoryManager初始化成功")
        except Exception as e:
            self._log(f"MemoryManager初始化失败: {e}")
            return

        try:
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self._log("NovelAgent初始化成功")
        except Exception as e:
            self._log(f"NovelAgent初始化失败: {e}")
            return

        try:
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self._log("NoteManager初始化成功")
        except Exception as e:
            self._log(f"NoteManager初始化失败: {e}")
            return

        try:
            self._init_character_system()
            self._log("角色系统初始化成功")
        except Exception as e:
            self._log(f"角色系统初始化失败: {e}")
            return

        try:
            self.title_var.set(meta.get("title", "未知"))
            self.genre_var.set(meta.get("genre", "未知"))
            self._log("标题和类型设置成功")
        except Exception as e:
            self._log(f"标题设置失败: {e}")

        # 加载大纲
        outline_file = novel_dir / "outline.json"
        if outline_file.exists():
            try:
                with open(outline_file, "r", encoding="utf-8") as f:
                    self.outline = json.load(f)
                self._refresh_outline_list()
                self._log(f"已加载大纲: {len(self.outline)} 章")
            except Exception as e:
                self._log(f"加载大纲失败: {e}")

        # 更新章节选择器
        try:
            self._update_chapter_selector()
            self._log("章节选择器更新成功")
        except Exception as e:
            self._log(f"章节选择器更新失败: {e}")

        # 计算进度
        chapters_dir = novel_dir / "chapters"
        total_chapters = meta.get("total_chapters", meta.get("chapter_count", 0))
        completed_chapters = 0

        if chapters_dir.exists():
            chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
            completed_chapters = len(chapter_files)
            self.current_chapter = completed_chapters
            self.chapter_var.set(f"{completed_chapters}/{total_chapters or '?'}")
            self._log(f"章节数量: {completed_chapters}")

            # 加载最后一章内容到编辑器
            if chapter_files:
                last_chapter_file = chapter_files[-1]
                try:
                    content = last_chapter_file.read_text(encoding="utf-8")
                    self._log(f"读取章节内容: {len(content)} 字符")

                    # 清空并插入内容
                    self.content_text.delete("1.0", tk.END)
                    self.content_text.insert("1.0", content)

                    # 强制更新UI
                    self.content_text.update_idletasks()
                    self.root.update_idletasks()

                    self.word_count_var.set(f"字数: {len(content)}")
                    chapter_num = int(last_chapter_file.stem.split("_")[-1])
                    self.chapter_select_var.set(f"第{chapter_num}章")
                    self._log(f"已加载第{chapter_num}章内容到编辑器")
                except Exception as e:
                    self._log(f"加载最后一章失败: {e}")

        # 切换到章节内容标签页
        try:
            for i in range(self.notebook.index("end")):
                tab_text = self.notebook.tab(i, "text").strip()
                if tab_text == "章节内容":
                    self.notebook.select(i)
                    self._log(f"已切换到标签页: {tab_text}")
                    break
        except Exception as e:
            self._log(f"切换标签页失败: {e}")

        self._sync_characters_from_memory()
        self._log(f"已打开小说《{meta.get('title', '未知')}》")

        # 🛡️ 检查是否有未完成的生成任务（断电恢复）
        self._check_recovery()

        # 显示进度提示
        if total_chapters and completed_chapters > 0:
            if completed_chapters < total_chapters:
                remaining = total_chapters - completed_chapters
                msg = f"小说《{meta.get('title')}》进度：已完成 {completed_chapters}/{total_chapters} 章\n\n"
                msg += f"还剩 {remaining} 章未完成。\n\n"
                msg += "接下来可以：\n"
                msg += "1. 点击「自动创作」继续自动生成剩余章节\n"
                msg += "2. 点击「生成下一章」手动逐章创作\n"
                msg += "3. 在编辑器中手动编写"
                self.root.after(500, lambda: messagebox.showinfo("继续创作", msg))
            elif completed_chapters >= total_chapters:
                result = messagebox.askyesno(
                    "已完成", f"小说《{meta.get('title')}》已全部完成！共 {completed_chapters} 章。\n\n是否续写新章？"
                )
                if result:
                    self._continue_novel()

    def _continue_novel(self):
        """续写已完成的小说 - 扩展大纲和新章节"""
        if not self.current_novel_dir:
            return

        # 计算当前总章数
        chapters_dir = self.current_novel_dir / "chapters"
        existing = sorted(chapters_dir.glob("chapter_*.txt")) if chapters_dir.exists() else []
        current_count = len(existing)

        # 询问续写多少章
        add_count = simpledialog.askinteger(
            "续写",
            f"当前已完成 {current_count} 章\n输入要续写的章数（10-50）:",
            minvalue=1,
            maxvalue=100,
            initialvalue=10,
        )

        if not add_count:
            return

        self._log(f"开始续写 {add_count} 章...")

        # 扩展大纲
        if not self.outline:
            self.outline = []

        meta = self._get_meta()
        title = meta.get("title", "小说")
        genre = meta.get("genre", "未知")

        # 生成新的大纲章节
        try:
            context = self.memory.get_global_summary() if self.memory else ""
            new_chapters = self.agent.generate_outline_continuation(genre, title, add_count, context, current_count)
            self.outline.extend(new_chapters)

            # 保存更新后的大纲
            self._novel_store().write_outline(self.outline)

            # 更新meta（读-改-写在同一把锁内，避免覆盖并发方的改动）
            if self._novel_store().exists("meta.json"):
                self._novel_store().update_meta({"chapter_count": len(self.outline)})

            self.current_chapter = current_count
            self._refresh_outline_list()
            self.chapter_var.set(f"{current_count}/{len(self.outline)}")
            self._log(f"大纲已扩展到 {len(self.outline)} 章，可以继续创作了")

            messagebox.showinfo(
                "续写",
                f"已添加 {add_count} 章新大纲\n总章数: {len(self.outline)}\n\n点击「自动创作」或「生成下一章」继续写作",
            )

        except Exception as e:
            self._log(f"续写大纲生成失败: {e}")
            messagebox.showerror("错误", f"续写失败: {e}")

    def _create_sequel(self):
        """基于当前小说创建续集（第二部）"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开一部已完成的小说")
            return

        meta_file = self.current_novel_dir / "meta.json"
        if not meta_file.exists():
            messagebox.showerror("错误", "当前目录不是有效的小说目录")
            return

        with open(meta_file, "r", encoding="utf-8") as f:
            original_meta = json.load(f)

        # 检查是否已完成
        chapters_dir = self.current_novel_dir / "chapters"
        if chapters_dir.exists():
            chapter_count = len(list(chapters_dir.glob("chapter_*.txt")))
            if chapter_count < original_meta.get("chapter_count", 0):
                if not messagebox.askyesno("提示", "当前小说尚未全部完成，确定要创建续集吗？"):
                    return

        # 读取原始小说的全局摘要
        global_summary = ""
        summary_file = self.current_novel_dir / "memory" / "global_summary.txt"
        if summary_file.exists():
            global_summary = summary_file.read_text(encoding="utf-8")

        # 创建续集对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("创建续集 - 第二部")
        dialog.geometry("600x500")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog,
            text=f"《{original_meta.get('title', '')}》续集",
            font=("微软雅黑", 14, "bold"),
            bg=C["bg_dark"],
            fg=C["accent_light"],
        ).pack(pady=(15, 10))

        # 续集标题
        title_frame = tk.Frame(dialog, bg=C["bg_dark"])
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(title_frame, text="续集标题:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        title_entry = tk.Entry(title_frame, font=("微软雅黑", 10), bg=C["bg_card"], fg=C["text_primary"])
        title_entry.insert(0, f"{original_meta.get('title', '')} 第二部")
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 续集概念
        tk.Label(dialog, text="续集概念/方向:", bg=C["bg_dark"], fg=C["text_primary"]).pack(
            anchor=tk.W, padx=20, pady=(10, 3)
        )
        concept_text = tk.Text(
            dialog, wrap=tk.WORD, font=("微软雅黑", 10), bg=C["bg_card"], fg=C["text_primary"], height=5
        )
        concept_text.pack(fill=tk.X, padx=20, pady=5)
        concept_text.insert("1.0", "延续第一部的世界观和角色，展开新的冒险...")

        # 原著摘要预览
        if global_summary:
            tk.Label(dialog, text="原著摘要（AI将基于此生成续集）:", bg=C["bg_dark"], fg=C["text_muted"]).pack(
                anchor=tk.W, padx=20, pady=(10, 3)
            )
            summary_preview = tk.Text(
                dialog, wrap=tk.WORD, font=("微软雅黑", 9), bg=C["bg_card"], fg=C["text_secondary"], height=4
            )
            summary_preview.pack(fill=tk.X, padx=20, pady=5)
            summary_preview.insert("1.0", global_summary[:500] + ("..." if len(global_summary) > 500 else ""))
            summary_preview.config(state=tk.DISABLED)

        # 章节数和字数
        params_frame = tk.Frame(dialog, bg=C["bg_dark"])
        params_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(params_frame, text="章节数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        chapters_var = tk.StringVar(value=str(original_meta.get("chapter_count", 20)))
        tk.Spinbox(params_frame, from_=1, to=500, textvariable=chapters_var, width=6, font=("微软雅黑", 9)).pack(
            side=tk.LEFT, padx=5
        )
        tk.Label(params_frame, text="每章字数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT, padx=(15, 0))
        word_count_var = tk.StringVar(value=str(original_meta.get("word_count_per_chapter", 3000)))
        ttk.Combobox(
            params_frame, textvariable=word_count_var, values=["1000", "2000", "3000", "5000", "8000"], width=8
        ).pack(side=tk.LEFT, padx=5)

        def confirm():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("提示", "请输入续集标题")
                return

            concept = concept_text.get("1.0", tk.END).strip()

            # 创建续集目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)

            # 保存续集元数据（关联原著）
            sequel_meta = {
                "title": title,
                "genre": original_meta.get("genre", ""),
                "sub_genre": original_meta.get("sub_genre", ""),
                "channel": original_meta.get("channel", "male"),
                "tags": original_meta.get("tags", []),
                "concept": concept,
                "chapter_count": int(chapters_var.get()),
                "word_count_per_chapter": int(word_count_var.get()),
                "created_at": datetime.now().isoformat(),
                "is_sequel": True,
                "original_novel": str(self.current_novel_dir),
                "original_title": original_meta.get("title", ""),
            }
            with open(novel_dir / "meta.json", "w", encoding="utf-8") as f:
                json.dump(sequel_meta, f, indent=2, ensure_ascii=False)

            # 复制原著的世界观和角色设定
            orig_memory = self.current_novel_dir / "memory"
            new_memory = novel_dir / "memory"
            new_memory.mkdir(exist_ok=True)

            # 复制世界观
            orig_settings = orig_memory / "settings.json"
            if orig_settings.exists():
                shutil.copy2(orig_settings, new_memory / "settings.json")

            # 复制角色
            orig_chars = self.current_novel_dir / "characters"
            if orig_chars.exists():
                shutil.copytree(orig_chars, novel_dir / "characters", dirs_exist_ok=True)

            # 保存续集概念作为参考
            with open(novel_dir / "sequel_concept.txt", "w", encoding="utf-8") as f:
                f.write(f"原著: {original_meta.get('title', '')}\n\n")
                f.write(f"原著摘要:\n{global_summary}\n\n")
                f.write(f"续集概念:\n{concept}")

            # 切换到续集
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()

            self.title_var.set(title)
            self.genre_var.set(f"{original_meta.get('genre', '')}-{original_meta.get('sub_genre', '')}")
            self.chapter_var.set(f"0/{chapters_var.get()}")

            dialog.destroy()
            self._log(f"续集《{title}》已创建，基于原著《{original_meta.get('title', '')}》")
            messagebox.showinfo(
                "成功", f"续集《{title}》已创建！\n世界观和角色已继承自原著。\n点击「自动创作」开始生成。"
            )

        tk.Button(
            dialog,
            text="创建续集",
            command=confirm,
            bg=C["accent"],
            fg="white",
            font=("微软雅黑", 11, "bold"),
            padx=30,
            pady=8,
        ).pack(pady=15)

    def _create_spinoff(self):
        """基于当前小说创建同人衍生作品"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开一部小说作为原著")
            return

        meta_file = self.current_novel_dir / "meta.json"
        if not meta_file.exists():
            messagebox.showerror("错误", "当前目录不是有效的小说目录")
            return

        with open(meta_file, "r", encoding="utf-8") as f:
            original_meta = json.load(f)

        # 读取角色信息
        characters = self.memory.get_characters() if self.memory else {}
        char_names = list(characters.keys()) if characters else []

        # 创建同人作品对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("创建同人衍生作品")
        dialog.geometry("650x600")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog,
            text=f"基于《{original_meta.get('title', '')}》的同人作品",
            font=("微软雅黑", 14, "bold"),
            bg=C["bg_dark"],
            fg=C["accent_light"],
        ).pack(pady=(15, 10))

        # 同人作品标题
        title_frame = tk.Frame(dialog, bg=C["bg_dark"])
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(title_frame, text="作品标题:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        title_entry = tk.Entry(title_frame, font=("微软雅黑", 10), bg=C["bg_card"], fg=C["text_primary"])
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 衍生类型
        type_frame = tk.Frame(dialog, bg=C["bg_dark"])
        type_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(type_frame, text="衍生类型:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        spinoff_type = tk.StringVar(value="平行世界")
        ttk.Combobox(
            type_frame,
            textvariable=spinoff_type,
            values=["平行世界", "角色外传", "前传", "IF线", "现代AU", "古代AU", "其他"],
            state="readonly",
            width=15,
        ).pack(side=tk.LEFT, padx=5)

        # 选择主要角色
        if char_names:
            tk.Label(dialog, text="选择主要角色（可多选）:", bg=C["bg_dark"], fg=C["text_primary"]).pack(
                anchor=tk.W, padx=20, pady=(10, 3)
            )
            char_frame = tk.Frame(dialog, bg=C["bg_card"])
            char_frame.pack(fill=tk.X, padx=20, pady=5)

            char_vars = {}
            for name in char_names[:10]:  # 最多显示10个角色
                var = tk.BooleanVar(value=False)
                char_vars[name] = var
                tk.Checkbutton(
                    char_frame,
                    text=name,
                    variable=var,
                    bg=C["bg_card"],
                    fg=C["text_primary"],
                    selectcolor=C["bg_dark"],
                    font=("微软雅黑", 9),
                ).pack(side=tk.LEFT, padx=5)

        # 衍生概念
        tk.Label(dialog, text="衍生概念/设定:", bg=C["bg_dark"], fg=C["text_primary"]).pack(
            anchor=tk.W, padx=20, pady=(10, 3)
        )
        concept_text = tk.Text(
            dialog, wrap=tk.WORD, font=("微软雅黑", 10), bg=C["bg_card"], fg=C["text_primary"], height=6
        )
        concept_text.pack(fill=tk.X, padx=20, pady=5)
        concept_text.insert("1.0", "在这个平行世界中...")

        # 章节数和字数
        params_frame = tk.Frame(dialog, bg=C["bg_dark"])
        params_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(params_frame, text="章节数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT)
        chapters_var = tk.StringVar(value="10")
        tk.Spinbox(params_frame, from_=1, to=200, textvariable=chapters_var, width=6, font=("微软雅黑", 9)).pack(
            side=tk.LEFT, padx=5
        )
        tk.Label(params_frame, text="每章字数:", bg=C["bg_dark"], fg=C["text_primary"]).pack(side=tk.LEFT, padx=(15, 0))
        word_count_var = tk.StringVar(value="3000")
        ttk.Combobox(params_frame, textvariable=word_count_var, values=["1000", "2000", "3000", "5000"], width=8).pack(
            side=tk.LEFT, padx=5
        )

        def confirm():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("提示", "请输入作品标题")
                return

            concept = concept_text.get("1.0", tk.END).strip()
            selected_chars = [name for name, var in char_vars.items() if var.get()] if char_names else []

            # 创建同人作品目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)

            # 保存同人作品元数据
            spinoff_meta = {
                "title": title,
                "genre": original_meta.get("genre", ""),
                "sub_genre": original_meta.get("sub_genre", ""),
                "channel": original_meta.get("channel", "male"),
                "tags": original_meta.get("tags", []) + ["同人", spinoff_type.get()],
                "concept": concept,
                "chapter_count": int(chapters_var.get()),
                "word_count_per_chapter": int(word_count_var.get()),
                "created_at": datetime.now().isoformat(),
                "is_spinoff": True,
                "spinoff_type": spinoff_type.get(),
                "original_novel": str(self.current_novel_dir),
                "original_title": original_meta.get("title", ""),
                "selected_characters": selected_chars,
            }
            with open(novel_dir / "meta.json", "w", encoding="utf-8") as f:
                json.dump(spinoff_meta, f, indent=2, ensure_ascii=False)

            # 复制世界观设定
            orig_memory = self.current_novel_dir / "memory"
            new_memory = novel_dir / "memory"
            new_memory.mkdir(exist_ok=True)

            orig_settings = orig_memory / "settings.json"
            if orig_settings.exists():
                shutil.copy2(orig_settings, new_memory / "settings.json")

            # 复制选定的角色
            if selected_chars and characters:
                chars_dir = novel_dir / "characters"
                chars_dir.mkdir(exist_ok=True)
                for char_name in selected_chars:
                    char_file = self.current_novel_dir / "characters" / f"{char_name}.json"
                    if char_file.exists():
                        shutil.copy2(char_file, chars_dir / f"{char_name}.json")

            # 保存同人设定文档
            with open(novel_dir / "spinoff_concept.txt", "w", encoding="utf-8") as f:
                f.write(f"原著: {original_meta.get('title', '')}\n")
                f.write(f"衍生类型: {spinoff_type.get()}\n")
                f.write(f"主要角色: {', '.join(selected_chars)}\n\n")
                f.write(f"衍生概念:\n{concept}")

            # 切换到同人作品
            self.current_novel_dir = novel_dir
            self._bind_usage_novel(novel_dir)
            self._announce_novel_opened(novel_dir)
            self.memory = MemoryManager(novel_dir)
            self.memory.set_event_sink(getattr(self, "events", None))
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()

            self.title_var.set(title)
            self.chapter_var.set(f"0/{chapters_var.get()}")

            dialog.destroy()
            self._log(f"同人作品《{title}》已创建，类型：{spinoff_type.get()}")
            messagebox.showinfo(
                "成功",
                f"同人作品《{title}》已创建！\n类型：{spinoff_type.get()}\n角色：{', '.join(selected_chars) or '无'}\n点击「自动创作」开始生成。",
            )

        tk.Button(
            dialog,
            text="创建同人作品",
            command=confirm,
            bg=C["accent"],
            fg="white",
            font=("微软雅黑", 11, "bold"),
            padx=30,
            pady=8,
        ).pack(pady=15)

    def _show_settings(self):
        """显示设置对话框 - 带滚动支持"""
        dialog = tk.Toplevel(self.root)
        dialog.title("系统配置")
        dialog.geometry("600x520")
        dialog.transient(self.root)
        dialog.grab_set()

        # 创建Canvas和滚动条
        canvas = tk.Canvas(dialog, highlightthickness=0)
        h_scrollbar = ttk.Scrollbar(dialog, orient=tk.HORIZONTAL, command=canvas.xview)
        v_scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=canvas.yview)

        canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)

        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 创建内容框架
        content_frame = tk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=content_frame, anchor=tk.NW)

        # 更新滚动区域
        def update_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

        content_frame.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_scrollregion)

        # 鼠标滚轮支持
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_shift_mousewheel(event):
            canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Shift-MouseWheel>", on_shift_mousewheel)

        notebook = ttk.Notebook(content_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # ===== Tab 1: AI模型配置 =====
        # P2-5：整页交给 AISettingsMixin 构建（注册表驱动下拉 + 多 Profile +
        # 超时/重试/思考模式 + 测试连接/余额/URL 预览）。
        # 旧实现把服务商清单、模型预设、API 地址预设在这里维护了第二份，
        # 与注册表漂移（选不到 kimi/mimo）；并且有两个温度输入框绑同一变量。
        ai_frame = ttk.Frame(notebook)
        notebook.add(ai_frame, text="AI模型")
        ai_save = self._build_ai_settings_tab(ai_frame, dialog)

        # ===== Tab 2: 文生图配置 =====
        img_frame = ttk.Frame(notebook)
        notebook.add(img_frame, text="文生图")

        ttk.Label(img_frame, text="文生图后端:").pack(anchor=tk.W, padx=20, pady=(15, 3))
        img_provider_var = tk.StringVar(value=self.config.get("img_provider", "comfyui"))
        ttk.Combobox(
            img_frame,
            textvariable=img_provider_var,
            values=["comfyui", "sdapi", "disabled"],
            state="readonly",
            width=50,
        ).pack(padx=20, pady=3)

        ttk.Label(img_frame, text="API地址:").pack(anchor=tk.W, padx=20, pady=(10, 3))
        img_base_entry = ttk.Entry(img_frame, width=52)
        img_base_entry.insert(0, self.config.get("img_api_base", "http://127.0.0.1:8188"))
        img_base_entry.pack(padx=20, pady=3)

        ttk.Label(img_frame, text="ComfyUI默认端口: 8188, SD WebUI默认端口: 7860").pack(
            anchor=tk.W, padx=20, pady=(3, 10)
        )

        ttk.Label(img_frame, text="模型文件名:").pack(anchor=tk.W, padx=20, pady=(5, 3))
        img_model_entry = ttk.Entry(img_frame, width=52)
        img_model_entry.insert(0, self.config.get("img_model", "sd_xl_base_1.0.safetensors"))
        img_model_entry.pack(padx=20, pady=3)

        auto_detect_var = tk.BooleanVar(value=self.config.get("auto_detect_scene", True))
        ttk.Checkbutton(img_frame, text="生成章节后自动检测名场面并提醒生成插图", variable=auto_detect_var).pack(
            anchor=tk.W, padx=20, pady=15
        )

        ttk.Label(
            img_frame,
            text="支持的后端:\n- ComfyUI: 本地部署的ComfyUI，需启动API模式\n- SD API: Stable Diffusion WebUI的API模式\n- Disabled: 不使用文生图",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=20, pady=10)

        # ===== Tab 3: 云端存储配置 =====
        cloud_frame = ttk.Frame(notebook)
        notebook.add(cloud_frame, text="云端存储")

        ttk.Label(cloud_frame, text="云端存储配置", font=("", 11, "bold")).pack(anchor=tk.W, padx=20, pady=(15, 10))
        ttk.Label(cloud_frame, text="支持: WebDAV（坚果云）、百度网盘、夸克网盘、迅雷网盘、阿里云盘").pack(
            anchor=tk.W, padx=20, pady=(0, 10)
        )

        # 云存储提供商选择
        cloud_provider_var = tk.StringVar(value="webdav")
        providers = self.cloud_storage.get_available_providers()
        provider_names = [p["name"] for p in providers]
        provider_ids = [p["id"] for p in providers]

        ttk.Label(cloud_frame, text="选择云存储:").pack(anchor=tk.W, padx=20, pady=(5, 3))
        cloud_combo = ttk.Combobox(
            cloud_frame, textvariable=cloud_provider_var, values=provider_names, state="readonly", width=50
        )
        cloud_combo.pack(padx=20, pady=3)
        cloud_combo.set(provider_names[0] if provider_names else "")

        # 配置区域
        config_frame = ttk.LabelFrame(cloud_frame, text="配置信息", padding=10)
        config_frame.pack(fill=tk.X, padx=20, pady=10)

        # WebDAV配置
        webdav_frame = ttk.Frame(config_frame)
        ttk.Label(webdav_frame, text="WebDAV地址:").grid(row=0, column=0, sticky=tk.W, pady=2)
        webdav_url_entry = ttk.Entry(webdav_frame, width=40)
        webdav_url_entry.insert(
            0, self.cloud_storage.config.get("webdav", {}).get("url", "https://dav.jianguoyun.com/dav/")
        )
        webdav_url_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(webdav_frame, text="用户名:").grid(row=1, column=0, sticky=tk.W, pady=2)
        webdav_user_entry = ttk.Entry(webdav_frame, width=40)
        webdav_user_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("username", ""))
        webdav_user_entry.grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(webdav_frame, text="密码/应用密钥:").grid(row=2, column=0, sticky=tk.W, pady=2)
        webdav_pass_entry = ttk.Entry(webdav_frame, width=40, show="*")
        webdav_pass_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("password", ""))
        webdav_pass_entry.grid(row=2, column=1, padx=5, pady=2)
        webdav_frame.pack(fill=tk.X, padx=10, pady=5)

        # 百度网盘配置
        baidu_frame = ttk.Frame(config_frame)
        ttk.Label(baidu_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        baidu_token_entry = ttk.Entry(baidu_frame, width=40)
        baidu_token_entry.insert(0, self.cloud_storage.config.get("baidu", {}).get("access_token", ""))
        baidu_token_entry.grid(row=0, column=1, padx=5, pady=2)
        baidu_frame.pack(fill=tk.X, padx=10, pady=5)

        # 夸克网盘配置
        quark_frame = ttk.Frame(config_frame)
        ttk.Label(quark_frame, text="Cookie:").grid(row=0, column=0, sticky=tk.W, pady=2)
        quark_cookie_entry = ttk.Entry(quark_frame, width=40)
        quark_cookie_entry.insert(0, self.cloud_storage.config.get("quark", {}).get("cookie", ""))
        quark_cookie_entry.grid(row=0, column=1, padx=5, pady=2)
        quark_frame.pack(fill=tk.X, padx=10, pady=5)

        # 迅雷网盘配置
        xunlei_frame = ttk.Frame(config_frame)
        ttk.Label(xunlei_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        xunlei_token_entry = ttk.Entry(xunlei_frame, width=40)
        xunlei_token_entry.insert(0, self.cloud_storage.config.get("xunlei", {}).get("access_token", ""))
        xunlei_token_entry.grid(row=0, column=1, padx=5, pady=2)
        xunlei_frame.pack(fill=tk.X, padx=10, pady=5)

        # 阿里云盘配置
        aliyun_frame = ttk.Frame(config_frame)
        ttk.Label(aliyun_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        aliyun_token_entry = ttk.Entry(aliyun_frame, width=40)
        aliyun_token_entry.insert(0, self.cloud_storage.config.get("aliyun", {}).get("access_token", ""))
        aliyun_token_entry.grid(row=0, column=1, padx=5, pady=2)
        aliyun_frame.pack(fill=tk.X, padx=10, pady=5)

        # 测试连接按钮
        def test_cloud_connection():
            provider_name = cloud_combo.get()
            provider_id = (
                provider_ids[provider_names.index(provider_name)] if provider_name in provider_names else "webdav"
            )

            # 保存配置
            if provider_id == "webdav":
                self.cloud_storage.configure_provider(
                    "webdav",
                    {
                        "url": webdav_url_entry.get(),
                        "username": webdav_user_entry.get(),
                        "password": webdav_pass_entry.get(),
                    },
                )
            elif provider_id == "baidu":
                self.cloud_storage.configure_provider("baidu", {"access_token": baidu_token_entry.get()})
            elif provider_id == "quark":
                self.cloud_storage.configure_provider("quark", {"cookie": quark_cookie_entry.get()})
            elif provider_id == "xunlei":
                self.cloud_storage.configure_provider("xunlei", {"access_token": xunlei_token_entry.get()})
            elif provider_id == "aliyun":
                self.cloud_storage.configure_provider("aliyun", {"access_token": aliyun_token_entry.get()})

            # 测试连接
            if self.cloud_storage.connect_provider(provider_id):
                messagebox.showinfo("成功", f"{provider_name} 连接成功！")
            else:
                messagebox.showwarning("失败", f"{provider_name} 连接失败，请检查配置")

        ttk.Button(cloud_frame, text="测试连接", command=test_cloud_connection).pack(pady=10)

        # ===== Tab 5: 高级设置 =====
        advanced_frame = ttk.Frame(notebook)
        notebook.add(advanced_frame, text="高级")

        # 18+内容开关（隐藏按钮）
        adult_frame = tk.LabelFrame(advanced_frame, text=" 内容控制 ", padx=10, pady=10)
        adult_frame.pack(fill=tk.X, padx=15, pady=10)

        # 三角形隐藏按钮
        secret_frame = tk.Frame(adult_frame)
        secret_frame.pack(fill=tk.X, pady=5)

        self._adult_toggle_visible = False
        adult_var = tk.BooleanVar(value=self.config.get("adult_content", False))

        def toggle_adult_visibility():
            """点击三角形显示/隐藏18+开关"""
            self._adult_toggle_visible = not self._adult_toggle_visible
            if self._adult_toggle_visible:
                adult_controls.pack(fill=tk.X, pady=5)
                secret_btn.configure(text="▼ 18+内容设置")
            else:
                adult_controls.pack_forget()
                secret_btn.configure(text="▶ 点击展开更多设置")

        secret_btn = tk.Button(
            secret_frame,
            text="▶ 点击展开更多设置",
            command=toggle_adult_visibility,
            relief=tk.FLAT,
            fg="gray",
            font=("微软雅黑", 8),
            anchor=tk.W,
        )
        secret_btn.pack(side=tk.LEFT)

        adult_controls = tk.Frame(adult_frame)

        tk.Label(adult_controls, text="⚠️ 以下功能仅供成年用户使用", fg="red", font=("微软雅黑", 9, "bold")).pack(
            anchor=tk.W, pady=(5, 10)
        )

        adult_check = tk.Checkbutton(adult_controls, text="启用18+内容生成", variable=adult_var, font=("微软雅黑", 10))
        adult_check.pack(anchor=tk.W, pady=3)

        edge_var = tk.BooleanVar(value=self.config.get("edge_content", False))
        edge_check = tk.Checkbutton(adult_controls, text="允许擦边内容", variable=edge_var, font=("微软雅黑", 10))
        edge_check.pack(anchor=tk.W, pady=3)

        tk.Label(
            adult_controls, text="启用后，AI在创作时会根据剧情需要加入相关描写", fg="gray", font=("微软雅黑", 8)
        ).pack(anchor=tk.W, pady=(5, 0))

        # 卷管理设置
        volume_frame = tk.LabelFrame(advanced_frame, text=" 卷管理 ", padx=10, pady=10)
        volume_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(volume_frame, text="每卷默认章节数:", font=("微软雅黑", 10)).pack(anchor=tk.W, pady=3)
        vol_chapters_var = tk.StringVar(value=str(self.config.get("chapters_per_volume", 100)))
        ttk.Spinbox(volume_frame, from_=10, to=500, textvariable=vol_chapters_var, width=10).pack(anchor=tk.W, pady=3)

        tk.Label(volume_frame, text="角色传记默认字数:", font=("微软雅黑", 10)).pack(anchor=tk.W, pady=(10, 3))
        bio_words_var = tk.StringVar(value=str(self.config.get("biography_word_count", 100000)))
        bio_combo = ttk.Combobox(
            volume_frame, textvariable=bio_words_var, values=["10000", "30000", "50000", "100000", "200000"], width=10
        )
        bio_combo.pack(anchor=tk.W, pady=3)
        tk.Label(volume_frame, text="生成角色个人传时的默认字数", fg="gray", font=("微软雅黑", 8)).pack(anchor=tk.W)

        # 智能体优化
        agent_frame = tk.LabelFrame(advanced_frame, text=" 智能体优化 ", padx=10, pady=10)
        agent_frame.pack(fill=tk.X, padx=15, pady=10)

        context_var = tk.BooleanVar(value=self.config.get("smart_context", True))
        tk.Checkbutton(
            agent_frame, text="智能上下文管理（防止章节过多卡死）", variable=context_var, font=("微软雅黑", 10)
        ).pack(anchor=tk.W, pady=3)

        summary_var = tk.BooleanVar(value=self.config.get("auto_summary", True))
        tk.Checkbutton(
            agent_frame, text="自动生成章节摘要（改善上下文连贯性）", variable=summary_var, font=("微软雅黑", 10)
        ).pack(anchor=tk.W, pady=3)

        # ===== 保存 =====
        def save():
            # AI 页签（含 provider / key / base / model / 采样 / 超时 / 多档案）
            # 由 AISettingsMixin 负责；它内部按字段逐个校验，非法值会弹窗并中止。
            ai_save()

            def _num(var, caster, label):
                """数值输入的统一校验：空串按未填写处理，非法值明确报错。"""
                raw = str(var.get()).strip()
                if not raw:
                    raise ValueError(f"{label}不能为空")
                return caster(raw)

            try:
                self.config.set("img_provider", img_provider_var.get())
                self.config.set("img_api_base", img_base_entry.get().strip())
                self.config.set("img_model", img_model_entry.get().strip())
                self.config.set("auto_detect_scene", auto_detect_var.get())
                self.config.set("adult_content", adult_var.get())
                self.config.set("edge_content", edge_var.get())
                self.config.set("chapters_per_volume", _num(vol_chapters_var, int, "每卷章节数"))
                self.config.set("biography_word_count", _num(bio_words_var, int, "传记字数"))
                self.config.set("smart_context", context_var.get())
                self.config.set("auto_summary", summary_var.get())
            except (ValueError, RuntimeError) as exc:
                messagebox.showerror("配置未保存", f"输入有误：{exc}", parent=dialog)
                return

            self.ai_client = AIClient(self.config)
            self.image_gen = ImageGenerator(self.config)
            if self.memory:
                self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)

            self._update_status()
            # v3 P4：配置已落盘 + 客户端已重建，广播出去（状态栏/面板据此刷新）
            self._publish_event(
                TOPIC_CONFIG_CHANGED,
                {
                    "active_profile": getattr(self.config, "active_profile", ""),
                },
            )
            dialog.destroy()
            self._log("配置已保存")

        # 底部按钮区
        btn_frame = tk.Frame(content_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        ttk.Button(btn_frame, text="保存配置", command=save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def _generate_synopsis(self):
        """AI生成书籍简介"""
        if not self._check_ready():
            return

        def run():
            try:
                self._log("正在生成书籍简介...")

                meta = self._get_meta()
                settings = self.memory.get_settings() if self.memory else {}
                outline = self.outline if self.outline else []

                system = """你是专业的书籍简介撰写专家。根据小说的世界观、大纲和设定，撰写一段吸引读者的书籍简介。

简介要求：
1. 150-300字
2. 突出故事亮点和卖点
3. 设置悬念，吸引读者
4. 不要剧透关键情节
5. 语言精炼有力"""

                prompt = f"""小说信息：
标题：{meta.get("title", "未命名")}
类型：{meta.get("genre", "未知")}
概念：{meta.get("concept", "无")}

世界观：{json.dumps(settings, ensure_ascii=False)[:500]}

大纲概要：{json.dumps(outline[:10], ensure_ascii=False)[:500]}

请生成书籍简介。"""

                result = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=1000)

                # 保存简介
                synopsis_file = self.current_novel_dir / "synopsis.txt"
                synopsis_file.write_text(result, encoding="utf-8")

                self.root.after(0, lambda: self._show_synopsis(result))
                self._log("书籍简介生成完成")

            except Exception as e:
                self._log(f"简介生成失败: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _show_synopsis(self, content: str):
        """显示书籍简介"""
        dialog = tk.Toplevel(self.root)
        dialog.title("书籍简介")
        dialog.geometry("500x400")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="书籍简介", font=("微软雅黑", 14, "bold"), bg=C["bg_dark"], fg=C["accent_light"]).pack(
            pady=(15, 10)
        )

        synopsis_text = tk.Text(
            dialog, wrap=tk.WORD, font=("微软雅黑", 12), bg=C["bg_card"], fg=C["text_primary"], padx=20, pady=15
        )
        synopsis_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        synopsis_text.insert("1.0", content)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def save():
            new_content = synopsis_text.get("1.0", tk.END).strip()
            synopsis_file = self.current_novel_dir / "synopsis.txt"
            synopsis_file.write_text(new_content, encoding="utf-8")
            dialog.destroy()
            self._log("书籍简介已保存")

        tk.Button(
            btn_frame, text="保存", command=save, bg=C["success"], fg="white", font=("微软雅黑", 10), padx=20
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="关闭",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)

    def _import_document(self):
        """导入作者文档（txt/docx/md）"""
        file_path = filedialog.askopenfilename(
            title="选择要导入的文档",
            filetypes=[
                ("所有支持格式", "*.txt *.docx *.md"),
                ("TXT文件", "*.txt"),
                ("Word文档", "*.docx"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*"),
            ],
        )

        if not file_path:
            return

        try:
            file_path = Path(file_path)
            content = ""

            if file_path.suffix.lower() == ".txt" or file_path.suffix.lower() == ".md":
                content = file_path.read_text(encoding="utf-8")
            elif file_path.suffix.lower() == ".docx":
                try:
                    from docx import Document

                    doc = Document(str(file_path))
                    content = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                except ImportError:
                    messagebox.showerror(
                        "错误", "需要安装 python-docx 库才能导入 Word 文档\n请运行: pip install python-docx"
                    )
                    return
            else:
                messagebox.showerror("错误", f"不支持的文件格式: {file_path.suffix}")
                return

            if not content.strip():
                messagebox.showwarning("提示", "文档内容为空")
                return

            self._imported_content = content
            self._imported_file = file_path.name

            self._show_import_preview(content, file_path.name)

        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {str(e)}")

    def _show_import_preview(self, content, filename):
        """显示导入内容预览"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"导入预览 - {filename}")
        dialog.geometry("600x500")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(
            dialog, text=f"已导入: {filename}", font=("微软雅黑", 12, "bold"), bg=C["bg_dark"], fg=C["accent_light"]
        ).pack(pady=(15, 5))

        tk.Label(
            dialog, text=f"字数: {len(content)}", font=("微软雅黑", 10), bg=C["bg_dark"], fg=C["text_secondary"]
        ).pack(pady=(0, 10))

        preview_text = tk.Text(
            dialog, wrap=tk.WORD, font=("微软雅黑", 10), bg=C["bg_card"], fg=C["text_primary"], height=15
        )
        preview_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        preview_text.insert("1.0", content[:2000] + ("..." if len(content) > 2000 else ""))
        preview_text.config(state=tk.DISABLED)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def insert_direct():
            self.content_text.insert(tk.INSERT, content)
            dialog.destroy()
            self._log(f"已插入导入内容: {filename}")

        def ai_analyze():
            dialog.destroy()
            self._ai_analyze_content()

        tk.Button(
            btn_frame,
            text="直接插入",
            command=insert_direct,
            bg=C["accent"],
            fg="white",
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="AI分析建议",
            command=ai_analyze,
            bg=C["success"],
            fg="white",
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)

    def _ai_analyze_content(self):
        """AI分析导入的内容并给出建议"""
        if not hasattr(self, "_imported_content") or not self._imported_content:
            messagebox.showwarning("提示", "请先导入文档（创作流程 → 导入文档）")
            return

        if not self._check_ready():
            return

        content = self._imported_content
        filename = self._imported_file

        def run():
            try:
                self._log(f"正在AI分析导入内容: {filename}...")

                meta = self._get_meta()
                outline = self.outline if self.outline else []

                system = """你是专业小说顾问。分析导入的文档内容，给出详细的创作建议。

分析维度：
1. 内容摘要（200字以内）
2. 写作风格分析
3. 优点与亮点
4. 需要改进的地方
5. 与当前小说的关联建议
6. 下一步创作建议（具体可执行的3-5条建议）

输出格式要求：
- 使用清晰的标题和分段
- 建议要具体可执行
- 语言要专业但易懂"""

                context = f"当前小说：《{meta.get('title', '未命名')}》\n类型：{meta.get('genre', '未知')}\n"
                if outline:
                    context += f"大纲章节数：{len(outline)}\n"

                prompt = f"""{context}

导入的文档内容（文件名：{filename}）：
---
{content[:3000]}
---

请分析以上内容并给出创作建议。"""

                result = self.ai_client.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)

                self.root.after(0, lambda: self._display_analysis_result(result, filename))
                self._log("AI分析完成")

            except Exception as e:
                self._log(f"AI分析失败: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _display_analysis_result(self, analysis, filename):
        """显示AI分析结果"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"AI分析报告 - {filename}")
        dialog.geometry("700x600")
        dialog.configure(bg=UIStyle.COLORS["bg_dark"])
        C = UIStyle.COLORS

        tk.Label(dialog, text="AI分析报告", font=("微软雅黑", 14, "bold"), bg=C["bg_dark"], fg=C["accent_light"]).pack(
            pady=(15, 10)
        )

        result_text = tk.Text(
            dialog, wrap=tk.WORD, font=("微软雅黑", 11), bg=C["bg_card"], fg=C["text_primary"], padx=20, pady=15
        )
        result_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        result_text.insert("1.0", analysis)

        scrollbar = tk.Scrollbar(result_text, command=result_text.yview)
        result_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = tk.Frame(dialog, bg=C["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def insert_content():
            if hasattr(self, "_imported_content"):
                self.content_text.insert(tk.INSERT, self._imported_content)
                dialog.destroy()
                self._log("已插入导入内容")

        def use_as_reference():
            if self.note_manager:
                self.note_manager.add_project_note("AI分析参考", analysis)
                self._log("分析结果已保存到笔记")
            dialog.destroy()

        tk.Button(
            btn_frame,
            text="插入原文",
            command=insert_content,
            bg=C["accent"],
            fg="white",
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="保存为参考",
            command=use_as_reference,
            bg=C["success"],
            fg="white",
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame,
            text="关闭",
            command=dialog.destroy,
            bg=C["bg_light"],
            fg=C["text_primary"],
            font=("微软雅黑", 10),
            padx=15,
        ).pack(side=tk.RIGHT, padx=5)
