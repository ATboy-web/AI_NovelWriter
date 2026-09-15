"""角色层：角色系统/卡片/详情/传记/增删改/装备技能/角色同步

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from loguru import logger

from app import UIStyle
from character_system import CharacterSystem
from format_converter import FormatConverter, ImageManager


class CharacterUIMixin:
    """角色层：角色系统/卡片/详情/传记/增删改/装备技能/角色同步"""


    def _sync_characters_from_memory(self):
        """从 memory/characters.json 同步角色到 characters/ 目录"""
        if not self.current_novel_dir:
            return
        mem_file = self.current_novel_dir / "memory" / "characters.json"
        if not mem_file.exists():
            return
        chars_dir = self.current_novel_dir / "characters"
        chars_dir.mkdir(exist_ok=True)
        
        try:
            with open(mem_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw = data.get("raw", "")
            if not raw:
                # 可能 memory 文件本身就是 dict（旧格式）
                chars = {k: v for k, v in data.items() if k != "raw" and isinstance(v, dict)}
                if chars:
                    self._write_char_files(chars_dir, chars)
                    return
                return
            
            # 解析 raw JSON
            chars = {}
            if isinstance(raw, str):
                # 多层尝试
                clean = raw.strip()
                clean = clean.replace('\u3000', ' ')  # 全角空格
                clean = re.sub(r'^```(?:json)?\s*\n?', '', clean)
                clean = re.sub(r'\n?```\s*$', '', clean)
                clean = clean.replace('\uff1a', ':')  # 全角冒号
                clean = clean.replace('\u201c', '"').replace('\u201d', '"')  # 全角引号
                # 修复 "goal":["a","b"] → "goal":"a; b" 
                clean = re.sub(r'("(?:goal|target|objective)")\s*:\s*\[([^\]]*)\]',
                              lambda m: f'{m.group(1)}: "{m.group(2).strip()}"', clean)
                # 修复连续冒号
                clean = re.sub(r'("\w+")\s*:{2,}', r'\1:', clean)
                
                try:
                    chars = json.loads(clean)
                except json.JSONDecodeError as e:
                    self._log(f"[同步] JSON解析失败(line {e.lineno}): {e}")
                    # 用 agent 的提取方法尝试
                    if hasattr(self, 'agent'):
                        chars = self.agent._extract_characters_from_raw(clean)
            elif isinstance(raw, dict):
                chars = {k: v for k, v in raw.items() if isinstance(v, dict)}
            
            if chars:
                self._write_char_files(chars_dir, chars)
        except Exception as e:
            self._log(f"同步角色失败: {e}")
            import traceback
            self._log(traceback.format_exc())
    def _write_char_files(self, chars_dir: Path, chars: dict):
        """写入角色文件到磁盘"""
        count = 0
        for name, info in chars.items():
            if isinstance(info, dict):
                char_data = {"name": name, **info}
                # 文件名安全处理
                import re
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
                with open(chars_dir / f"{safe_name}.json", 'w', encoding='utf-8') as f:
                    json.dump(char_data, f, indent=2, ensure_ascii=False)
                count += 1
        if count > 0:
            self._log(f"已从记忆恢复 {count} 个角色")
    def _sync_memory_chars_to_dir(self):
        """将 memory/characters.json 同步到 characters/ 目录"""
        try:
            import json as _j
            mem_chars = self.current_novel_dir / "memory" / "characters.json"
            if not mem_chars.exists():
                return
            data = _j.loads(mem_chars.read_text(encoding='utf-8'))
            
            # 从 raw 字段提取角色数据
            chars = {}
            raw = data.get("raw", "")
            if raw and isinstance(raw, str):
                clean = raw.strip()
                clean = re.sub(r'```(?:json)?\s*\n?', '', clean)
                clean = re.sub(r'\n?```\s*$', '', clean)
                clean = clean.replace('\uff1a', ':')
                clean = clean.replace('\uff0c', ',')
                # 修复 goal 等数组字段
                clean = re.sub(r'"goal"\s*:\s*\[([^\]]*)',
                    lambda m: '"goal": "' + '; '.join(re.findall(r'"([^"]*)"', m.group(1))) + '"',
                    clean)
                clean = re.sub(r'("\w+")\s*:{2,}', r'\1:', clean)
                try:
                    parsed = _j.loads(clean)
                    if isinstance(parsed, dict):
                        chars = {k: v for k, v in parsed.items() if isinstance(v, dict)}
                except Exception:
                    # 尝试逐字符提取
                    chars = self._extract_chars_from_raw(clean) if hasattr(self, '_extract_chars_from_raw') else {}
            elif isinstance(data, dict):
                chars = {k: v for k, v in data.items() if k != "raw" and isinstance(v, dict)}
            
            if not chars:
                return
            
            if not self.character_system:
                from character_system import CharacterSystem
                self.character_system = CharacterSystem(self.current_novel_dir)
            
            existing_names = set(self.character_system.get_character_names())
            new_count = 0
            for name, info in chars.items():
                if name in existing_names:
                    continue
                info_dict = info if isinstance(info, dict) else {"description": str(info)}
                category = info_dict.get("role", info_dict.get("category", "配角"))
                faction = info_dict.get("faction", "中立")
                self.character_system.create_character(
                    name=name, category=category, faction=faction,
                    first_appearance=1
                )
                desc = info_dict.get("personality", "") or info_dict.get("description", "") or ""
                if desc:
                    c = self.character_system.get_character(name)
                    if c:
                        c.personality = str(desc)[:200]
                self.character_system.save_character(name)
                new_count += 1
            
            if new_count > 0:
                self._log(f"[角色同步] 从记忆恢复{new_count}个新角色 (共{len(chars)}个)")
            self.root.after(0, self._update_char_display)
        except Exception as e:
            self._log(f"[角色同步] 失败: {e}")
    def _auto_detect_characters(self, chapter_num: int, content: str):
        """自动检测新角色并创建"""
        try:
            if not self.ai_client or not self.ai_client.is_configured():
                return
            
            existing = self.memory.get_characters() if self.memory else {}
            existing_names = list(existing.keys()) if existing else []
            existing_str = ", ".join(existing_names[:10]) if existing_names else "空"
            
            system = f"""检测文本中出现的所有新角色名称。
已有角色: {existing_str}
只输出JSON数组，如["新角色名1","新角色名2"]
如果没有新角色,输出[]"""
            
            response = self.ai_client.chat(
                [{"role": "user", "content": f"第{chapter_num}章内容:\n{content[:2000]}"}],
                system=system, max_tokens=1500
            )
            if not response:
                return
            
            match = re.search(r'\[[\s\S]*\]', response)
            if not match:
                return
            new_names = json.loads(match.group())
            
            if new_names:
                characters = existing.copy() if existing else {}
                added = []
                for name in new_names:
                    if name and name not in characters:
                        characters[name] = {
                            "first_appearance": chapter_num,
                            "category": "无名小卒",
                            "faction": "中立",
                            "auto_created": True
                        }
                        added.append(name)
                
                if added:
                    self.memory.save_characters(characters)
                    # 同时同步到CharacterSystem
                    self._sync_characters_to_system(added, chapter_num)
                    self._log(f"[角色] 自动创建{len(added)}个新角色: {', '.join(added[:5])}")
        except Exception as e:
            self._log(f"[角色] 角色检测异常: {type(e).__name__}: {e}")
    def _sync_characters_to_system(self, names: list, chapter_num: int):
        """同步角色到CharacterSystem"""
        if not self.character_system:
            if self.current_novel_dir:
                self.character_system = CharacterSystem(self.current_novel_dir)
                self.character_system.load()
            else:
                return
        for name in names:
            if not self.character_system.get_character(name):
                self.character_system.create_character(
                    name=name,
                    category="无名小卒",
                    faction="中立",
                    first_appearance=chapter_num
                )
                self.character_system.save_character(name)
        if names:
            self._update_char_display()
    def _generate_character_biography(self, char_name: str = None):
        """生成角色个人传记"""
        if not self._check_ready():
            return
        
        # 如果没有指定角色，让用户选择
        if not char_name:
            characters = self.memory.get_characters() if self.memory else {}
            if not characters:
                messagebox.showwarning("提示", "请先创建角色")
                return
            
            # 角色选择对话框
            char_name = tk.simpledialog.askstring("选择角色", 
                f"请输入角色名称:\n可用角色: {', '.join(characters.keys())}")
            if not char_name:
                return
        
        # 获取字数设置
        default_words = self.config.get("biography_word_count", 100000)
        
        # 字数选择对话框
        word_dialog = tk.Toplevel(self.root)
        word_dialog.title("角色传记设置")
        word_dialog.geometry("400x250")
        word_dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(word_dialog, text=f"生成「{char_name}」个人传记", 
                font=('微软雅黑', 12, 'bold'), bg=C['bg_dark'], fg=C['accent_light']).pack(pady=(15, 10))
        
        tk.Label(word_dialog, text="传记字数:", bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=30)
        word_var = tk.StringVar(value=str(default_words))
        word_combo = ttk.Combobox(word_dialog, textvariable=word_var,
                                 values=["5000", "10000", "30000", "50000", "100000", "200000"],
                                 width=15)
        word_combo.pack(anchor=tk.W, padx=30, pady=5)
        
        include_mental = tk.BooleanVar(value=True)
        mental_btn = tk.Checkbutton(word_dialog, text="包含心理历程", variable=include_mental,
                      bg=C['bg_dark'], fg=C['text_primary'], selectcolor=C['bg_card'],
                      activebackground=C['bg_dark'], activeforeground=C['text_primary'])
        mental_btn.pack(anchor=tk.W, padx=30, pady=3)
        
        include_contrast = tk.BooleanVar(value=True)
        contrast_btn = tk.Checkbutton(word_dialog, text="分析性格反差", variable=include_contrast,
                      bg=C['bg_dark'], fg=C['text_primary'], selectcolor=C['bg_card'],
                      activebackground=C['bg_dark'], activeforeground=C['text_primary'])
        contrast_btn.pack(anchor=tk.W, padx=30, pady=3)
        
        def start_generate():
            word_count = int(word_var.get())
            word_dialog.destroy()
            
            def run():
                try:
                    self._log(f"正在生成「{char_name}」的个人传记（约{word_count}字）...")
                    
                    # 获取角色信息
                    characters = self.memory.get_characters()
                    char_info = characters.get(char_name, {})
                    
                    # 获取世界观和大纲
                    settings = self.memory.get_settings() if self.memory else {}
                    outline = self.outline if self.outline else []
                    
                    system = f"""你是专业的小说传记作家。请为角色「{char_name}」撰写一部完整的个人传记。

角色信息：{json.dumps(char_info, ensure_ascii=False)[:1000]}

世界观：{json.dumps(settings, ensure_ascii=False)[:500]}

传记要求：
1. 从角色的出生/起源开始写起
2. 详细描述角色的成长历程
3. 包含角色的心理变化过程
4. 分析角色的性格特点和反差
5. 描述角色的重要经历和转折点
6. 在结尾总结：
   - 这个角色是什么样的人
   - 他的核心性格特征
   - 他的心理发展过程
   - 他身上的反差和矛盾
   - 他对故事的意义

{"请重点描写角色的心理历程。" if include_mental.get() else ""}
{"请分析角色性格中的反差和矛盾。" if include_contrast.get() else ""}

字数要求：约{word_count}字"""
                    
                    prompt = f"请为「{char_name}」撰写个人传记。大纲参考：{json.dumps(outline[:5], ensure_ascii=False)}"
                    
                    result = self.ai_client.chat([{"role": "user", "content": prompt}], 
                                         system=system, max_tokens=word_count * 2)
                    
                    # 保存传记
                    bio_dir = self.current_novel_dir / "biographies"
                    bio_dir.mkdir(exist_ok=True)
                    bio_file = bio_dir / f"{char_name}_传记.txt"
                    bio_file.write_text(result, encoding='utf-8')
                    
                    # 同步到角色面板
                    if self.memory:
                        characters = self.memory.get_characters()
                        if char_name in characters:
                            characters[char_name]['biography'] = result[:500] + "..."
                            characters[char_name]['biography_file'] = str(bio_file)
                            self.memory.save_characters(characters)
                    
                    self.root.after(0, lambda: self._show_biography(result, char_name))
                    self._log(f"「{char_name}」个人传记生成完成，已保存到 {bio_file}")
                    
                except Exception as e:
                    self._log(f"传记生成失败: {e}")
            
            threading.Thread(target=run, daemon=True).start()
        
        tk.Button(word_dialog, text="开始生成", command=start_generate,
                 bg=C['accent'], fg='white', font=('微软雅黑', 11, 'bold'), padx=20, pady=5).pack(pady=15)
    def _show_biography(self, content: str, char_name: str):
        """显示角色传记"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"角色传记 - {char_name}")
        dialog.geometry("800x600")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text=f"「{char_name}」个人传记", 
                font=('微软雅黑', 14, 'bold'), bg=C['bg_dark'], fg=C['accent_light']).pack(pady=(10, 5))
        
        bio_text = tk.Text(dialog, wrap=tk.WORD, font=('微软雅黑', 11),
                          bg=C['bg_card'], fg=C['text_primary'], padx=20, pady=15)
        bio_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        bio_text.insert("1.0", content)
        
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        
        def insert_to_chapter():
            self.content_text.insert(tk.INSERT, "\n\n" + content)
            dialog.destroy()
        
        tk.Button(btn_frame, text="插入到当前章节", command=insert_to_chapter,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10), padx=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="关闭", command=dialog.destroy,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 10), padx=15).pack(side=tk.RIGHT, padx=5)
    def _init_character_system(self):
        """初始化角色系统"""
        if self.current_novel_dir:
            self.character_system = CharacterSystem(self.current_novel_dir)
            self.character_system.load()
            self._update_char_display()
            self.format_converter = FormatConverter(self.current_novel_dir)
            self.image_manager = ImageManager(self.current_novel_dir)
    def _update_char_display(self):
        """更新角色面板显示 - 同时更新左侧角色卡片"""
        C = UIStyle.COLORS
        
        # 更新左侧角色卡片
        for w in self.char_cards_container.winfo_children():
            w.destroy()
        
        if not self.character_system:
            tk.Label(self.char_cards_container, text="未创建角色", font=('微软雅黑', 9),
                    bg=C['bg_medium'], fg=C['text_muted']).pack(anchor=tk.W)
            self.char_select_combo['values'] = []
            return
        
        names = self.character_system.get_character_names()
        self.char_select_combo['values'] = names
        
        # 🔧 修复：同步下拉框选中项到当前活跃角色
        if self.character_system.active_name and self.character_system.active_name in names:
            self.char_select_var.set(self.character_system.active_name)
        elif names:
            self.char_select_var.set(names[0])
            self.character_system.set_active(names[0])
        else:
            self.char_select_var.set("无角色")
        
        # 生成角色卡片
        for name in names[:5]:  # 最多显示5个角色
            self._create_char_card(name)
        
        # 更新日志页的角色详情
        if hasattr(self, 'char_detail_frame'):
            for w in self.char_detail_frame.winfo_children():
                w.destroy()
            
            if not self.character_system.character:
                tk.Label(self.char_detail_frame, text="请选择角色", font=('微软雅黑', 9),
                        bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W, pady=2)
                return
            
            char = self.character_system.character
            self._display_char_details(char)
    def _create_char_card(self, name):
        """创建单个角色卡片"""
        C = UIStyle.COLORS
        char = self.character_system.get_character(name)
        if not char:
            return
        
        # 根据状态决定卡片颜色
        status = getattr(char, 'status', '存活')
        if status == '死亡':
            card_bg = '#3d1f1f'  # 暗红色背景
            text_color = '#808080'
        else:
            card_bg = C['bg_card']
            text_color = C['text_primary']
        
        card = tk.Frame(self.char_cards_container, bg=card_bg, padx=8, pady=6)
        card.pack(fill=tk.X, pady=2)
        
        # 头像 (首字母) - 根据分类和状态决定颜色
        category = getattr(char, 'category', '无名小卒')
        faction = getattr(char, 'faction', '中立')
        
        if status == '死亡':
            avatar_bg = '#666666'
        elif category == '关键人物':
            avatar_bg = '#f59e0b'  # 金色
        elif category == '主角朋友':
            avatar_bg = '#3b82f6'  # 蓝色
        elif category == '女友':
            avatar_bg = '#ec4899'  # 粉色
        elif category == '反派':
            avatar_bg = '#ef4444'  # 红色
        else:
            avatar_bg = '#6b7280'  # 灰色
        
        avatar = tk.Label(card, text=name[0], font=('微软雅黑', 10, 'bold'),
                         bg=avatar_bg, fg='white', width=2, height=1)
        avatar.pack(side=tk.LEFT, padx=(0, 8))
        
        # 角色信息
        info_frame = tk.Frame(card, bg=card_bg)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 名称和状态
        name_text = name
        if status == '死亡':
            name_text = f"†{name}"  # 添加死亡标记
        elif status == '复活':
            name_text = f"♻{name}"  # 添加复活标记
        
        tk.Label(info_frame, text=name_text, font=('微软雅黑', 10, 'bold'),
                bg=card_bg, fg=text_color).pack(anchor=tk.W)
        
        # 分类和等级
        level = getattr(char, 'level', 1)
        title = getattr(char, 'title', '无称号')
        tk.Label(info_frame, text=f"[{category}] Lv.{level} | {title}", font=('微软雅黑', 8),
                bg=card_bg, fg=C['text_muted']).pack(anchor=tk.W)
        
        # 点击事件
        def select_char(n=name):
            self.char_select_var.set(n)
            self._on_char_select()
        
        card.bind('<Button-1>', lambda e: select_char())
        avatar.bind('<Button-1>', lambda e: select_char())
    def _display_char_details(self, char):
        """显示角色详细信息"""
        C = UIStyle.COLORS
        
        # 基本信息
        tk.Label(self.char_detail_frame, text=f"「{char.name}」{char.title}", 
                font=('微软雅黑', 10, 'bold'), bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=2)
        tk.Label(self.char_detail_frame, text=f"等级: Lv.{char.level}  |  EXP: {char.exp}/{char.exp_to_next}", 
                font=('微软雅黑', 9), bg=C['bg_medium'], fg=C['text_primary']).pack(anchor=tk.W)
        
        # 属性
        tk.Label(self.char_detail_frame, text="─ 属性 ─", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W, pady=(5, 2))
        attrs_frame = tk.Frame(self.char_detail_frame, bg=C['bg_medium'])
        attrs_frame.pack(fill=tk.X)
        for attr_name, attr_val in [("HP", f"{char.hp}/{char.max_hp}"), ("MP", f"{char.mp}/{char.max_mp}"),
                                    ("攻击", getattr(char, 'attack', '?')), ("防御", getattr(char, 'defense', '?')),
                                    ("速度", getattr(char, 'speed', '?')), ("智力", getattr(char, 'intelligence', '?'))]:
            tk.Label(attrs_frame, text=f"{attr_name}: {attr_val}", font=('微软雅黑', 8),
                    bg=C['bg_medium'], fg=C['text_primary']).pack(side=tk.LEFT, padx=3)
        
        # 武器
        tk.Label(self.char_detail_frame, text="─ 武器 ─", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W, pady=(5, 2))
        if char.weapon:
            w = char.weapon
            w_name = w.get('name', '无')
            w_quality = w.get('quality', '普通')
            tk.Label(self.char_detail_frame, text=f"⚔ {w_name} [{w_quality}]", font=('微软雅黑', 9),
                    bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W)
        else:
            tk.Label(self.char_detail_frame, text="未装备武器", font=('微软雅黑', 8),
                    bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W)
        
        # 技能
        tk.Label(self.char_detail_frame, text="─ 技能 ─", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W, pady=(5, 2))
        if char.skills:
            for skill in char.skills[:5]:
                s_name = skill.get('name', '未知')
                s_lv = skill.get('level', 1)
                tk.Label(self.char_detail_frame, text=f"✦ {s_name} Lv.{s_lv}", font=('微软雅黑', 8),
                        bg=C['bg_medium'], fg=C['text_primary']).pack(anchor=tk.W)
        else:
            tk.Label(self.char_detail_frame, text="未学习技能", font=('微软雅黑', 8),
                    bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W)
        
        # 性格/背景
        tk.Label(self.char_detail_frame, text="─ 性格/背景 ─", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W, pady=(5, 2))
        personality = getattr(char, 'personality', '')
        backstory = getattr(char, 'backstory', '')
        appearance = getattr(char, 'appearance', '')
        if personality:
            tk.Label(self.char_detail_frame, text=f"性格: {str(personality)[:100]}", font=('微软雅黑', 8),
                    bg=C['bg_medium'], fg=C['text_primary'], wraplength=200).pack(anchor=tk.W)
        if backstory:
            tk.Label(self.char_detail_frame, text=f"背景: {str(backstory)[:100]}", font=('微软雅黑', 8),
                    bg=C['bg_medium'], fg=C['text_primary'], wraplength=200).pack(anchor=tk.W)
        if appearance:
            tk.Label(self.char_detail_frame, text=f"外貌: {str(appearance)[:80]}", font=('微软雅黑', 8),
                    bg=C['bg_medium'], fg=C['text_primary'], wraplength=200).pack(anchor=tk.W)
        
        # 角色成长日志
        tk.Label(self.char_detail_frame, text="─ 成长日志 ─", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(anchor=tk.W, pady=(5, 2))
        
        try:
            if self.memory and self.agent:
                events = self.memory.get_events() if hasattr(self.memory, 'get_events') else []
                char_events = []
                for ev in (events[-50:] if events else []):
                    ev_text = ev.get("event", "") if isinstance(ev, dict) else str(ev)
                    if char.name in ev_text:
                        chapter = ev.get("chapter", "?") if isinstance(ev, dict) else "?"
                        char_events.append(f"第{chapter}章: {ev_text[:60]}")
                
                if char_events:
                    for ev_text in char_events[-8:]:  # 显示最近8条
                        tk.Label(self.char_detail_frame, text=f"• {ev_text}", font=('微软雅黑', 7),
                                bg=C['bg_medium'], fg=C['text_secondary'], wraplength=200).pack(anchor=tk.W)
                else:
                    tk.Label(self.char_detail_frame, text="暂无成长记录", font=('微软雅黑', 7),
                            bg=C['bg_medium'], fg=C['text_muted']).pack(anchor=tk.W)
        except Exception:
            pass
        
        self.char_detail_frame.update_idletasks()
        # Update scroll region
        canvas = self.char_detail_frame.master
        canvas.configure(scrollregion=canvas.bbox("all"))
    def _gen_char_biography(self):
        """从角色面板按钮生成选中角色个人传"""
        name = self.char_select_var.get()
        if not name or name == "无角色":
            messagebox.showwarning("提示", "请先选择一个角色")
            return
        
        if not self._check_ready(silent=True):
            return
        
        # 直接生成传记（跳过角色选择对话框）
        self._generate_character_biography(name)
    def _on_char_select(self, event=None):
        """切换活跃角色 - 重新加载确保显示最新数据"""
        name = self.char_select_var.get()
        if self.character_system and name:
            self.character_system.load()  # 重新加载角色文件
            self.character_system.set_active(name)
            self._update_char_display()
            self._log(f"切换到角色: {name}")
        elif self.character_system:
            # 如果选择了空，也刷新一下
            self.character_system.load()
            self._update_char_display()
    def _create_character_dialog(self):
        """创建角色对话框 - 完善版"""
        dialog = tk.Toplevel(self.root)
        dialog.title("创建角色")
        dialog.geometry("450x500")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        fields = {}
        field_list = [
            ("角色名称:", "name", ""),
            ("称号:", "title", ""),
            ("等级:", "level", "1"),
            ("性格特点:", "personality", ""),
            ("外貌描述:", "appearance", ""),
            ("背景故事:", "backstory", ""),
        ]
        
        for label, key, default in field_list:
            tk.Label(dialog, text=label, font=('微软雅黑', 10),
                    bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(8, 2))
            if key in ("backstory",):
                entry = tk.Text(dialog, width=40, height=4, font=('微软雅黑', 10), bg=C['bg_card'], fg=C['text_primary'])
                entry.pack(padx=20)
            else:
                entry = tk.Entry(dialog, width=40, font=('微软雅黑', 10), bg=C['bg_card'], fg=C['text_primary'])
                entry.insert(0, default)
                entry.pack(padx=20)
            fields[key] = entry
        
        def create():
            name = fields["name"].get().strip() if isinstance(fields["name"], tk.Entry) else fields["name"].get("1.0", tk.END).strip()
            if not name:
                messagebox.showwarning("提示", "请输入角色名称")
                return
            if not self.character_system:
                self.character_system = CharacterSystem(self.current_novel_dir)
            
            if name in self.character_system.get_character_names():
                messagebox.showwarning("提示", "角色名已存在")
                return
            
            def get_val(key):
                widget = fields[key]
                if isinstance(widget, tk.Text):
                    return widget.get("1.0", tk.END).strip()
                return widget.get().strip()
            
            self.character_system.create_character(
                name=name,
                title=get_val("title"),
                level=int(get_val("level") or "1"),
                backstory=get_val("backstory"),
                personality=get_val("personality"),
                appearance=get_val("appearance"),
            )
            self._update_char_display()
            self._log(f"角色「{name}」创建成功")
            dialog.destroy()
        
        tk.Button(dialog, text="创建", font=('微软雅黑', 11),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=20, pady=5,
                 command=create).pack(pady=15)
    def _ai_create_character(self):
        """AI自动创建角色"""
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        # 获取小说上下文
        context = ""
        if self.memory:
            settings = self.memory.get_settings()
            if settings:
                context = json.dumps(settings, ensure_ascii=False)[:300]
        
        def run():
            try:
                if not self.character_system:
                    self.character_system = CharacterSystem(self.current_novel_dir)
                
                result = self.character_system.ai_create_character(self.ai_client, context)
                
                if result["success"]:
                    char = result["character"]
                    self.root.after(0, lambda: self._update_char_display())
                    self._log(f"AI创建角色「{char.name}」成功")
                    
                    # 如果有武器/技能建议，显示给用户
                    suggestions = f"角色「{char.name}」创建成功！\n\n"
                    if result.get("weapon_suggestion"):
                        suggestions += f"建议武器: {result['weapon_suggestion']}\n"
                    if result.get("skill_suggestions"):
                        suggestions += f"建议技能: {', '.join(result['skill_suggestions'])}\n"
                    self.root.after(0, lambda: messagebox.showinfo("AI创建成功", suggestions))
                else:
                    self.root.after(0, lambda: messagebox.showerror("创建失败", result.get("error", "未知错误")))
            except Exception as e:
                self.root.after(0, lambda _exc=e: messagebox.showerror("错误", str(_exc)))
        
        self._log("AI正在创建角色...")
        threading.Thread(target=run, daemon=True).start()
    def _show_char_detail(self):
        """显示角色详情"""
        if not self.character_system or not self.character_system.character:
            messagebox.showinfo("提示", "请先创建角色")
            return
        
        char = self.character_system.character
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"角色详情 - {char.name}")
        dialog.geometry("500x600")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        # 使用Notebook组织信息
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 属性页
        attr_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(attr_frame, text=" 属性 ")
        
        attr_text = tk.Text(attr_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                           bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT, padx=15, pady=15)
        attr_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        attr_text.insert("1.0", char.get_summary())
        attr_text.config(state=tk.DISABLED)
        
        # 武器/技能页
        equip_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(equip_frame, text=" 装备/技能 ")
        
        equip_text = tk.Text(equip_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                            bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT, padx=15, pady=15)
        equip_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        equip_info = "═══ 装备 ═══\n"
        equip_info += f"武器: {char.weapon.get('name', '无') if char.weapon else '无'}\n"
        equip_info += f"防具: {char.armor.get('name', '无') if char.armor else '无'}\n"
        equip_info += f"饰品: {char.accessory.get('name', '无') if char.accessory else '无'}\n\n"
        equip_info += "═══ 技能 ═══\n"
        for skill in char.skills:
            equip_info += f"• {skill.get('name', '')} ({skill.get('type', '')}) - {skill.get('desc', '')}\n"
        if not char.skills:
            equip_info += "暂无技能\n"
        
        equip_text.insert("1.0", equip_info)
        equip_text.config(state=tk.DISABLED)
        
        # 统计页
        stats_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(stats_frame, text=" 统计 ")
        
        stats_text = tk.Text(stats_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                            bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT, padx=15, pady=15)
        stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        stats_text.insert("1.0", self.character_system.get_stats_display())
        stats_text.config(state=tk.DISABLED)
        
        # 操作按钮
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(btn_frame, text="重命名", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=8,
                 command=lambda: self._rename_character(dialog)).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="删除角色", font=('微软雅黑', 9),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=8,
                 command=lambda: self._delete_character(dialog)).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="休息恢复", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=8,
                 command=lambda: self._rest_character()).pack(side=tk.RIGHT, padx=3)
        tk.Button(btn_frame, text="📖 故事线", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=8,
                 command=lambda: self._edit_character_story(char.name)).pack(side=tk.RIGHT, padx=3)
    def _rename_character(self, dialog):
        """重命名角色"""
        if not self.character_system or not self.character_system.character:
            return
        old_name = self.character_system.character.name
        new_name = tk.simpledialog.askstring("重命名", "输入新名称:", initialvalue=old_name)
        if new_name and new_name != old_name:
            if self.character_system.rename_character(old_name, new_name):
                self._update_char_display()
                self._log(f"角色已重命名: {old_name} → {new_name}")
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "名称已存在或无效")
    def _delete_character(self, dialog):
        """删除角色"""
        if not self.character_system or not self.character_system.character:
            return
        name = self.character_system.character.name
        if messagebox.askyesno("确认", f"确定删除角色「{name}」？"):
            self.character_system.delete_character(name)
            self._update_char_display()
            self._log(f"已删除角色: {name}")
            dialog.destroy()
    def _rest_character(self):
        """角色休息恢复"""
        if self.character_system and self.character_system.character:
            self.character_system.character.rest()
            self.character_system.save_character()
            self._update_char_display()
            self._log(f"{self.character_system.character.name} 休息恢复，HP/MP已满")
    def _edit_character_story(self, char_name: str):
        """编辑角色故事线"""
        if not self.current_novel_dir:
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"角色故事线 - {char_name}")
        dialog.geometry("600x500")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        # 加载角色故事
        stories_dir = self.current_novel_dir / "character_stories"
        stories_dir.mkdir(exist_ok=True)
        story_file = stories_dir / f"{char_name}.json"
        
        story_data = {"name": char_name, "story_arcs": [], "notes": ""}
        if story_file.exists():
            with open(story_file, 'r', encoding='utf-8') as f:
                story_data = json.load(f)
        
        tk.Label(dialog, text=f"📖 {char_name} 的故事线", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(pady=(15, 10))
        
        # 故事线列表
        list_frame = tk.Frame(dialog, bg=C['bg_dark'])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        story_list = tk.Listbox(list_frame, bg=C['bg_card'], fg=C['text_primary'],
                               font=('微软雅黑', 10), selectbackground=C['accent'],
                               relief=tk.FLAT, height=8)
        story_list.pack(fill=tk.BOTH, expand=True)
        
        for arc in story_data.get("story_arcs", []):
            story_list.insert(tk.END, f"• {arc.get('title', '未命名')}")
        
        # 故事详情
        detail_frame = tk.Frame(dialog, bg=C['bg_dark'])
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        tk.Label(detail_frame, text="故事详情:", bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W)
        detail_text = tk.Text(detail_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                             bg=C['bg_card'], fg=C['text_primary'], height=6)
        detail_text.pack(fill=tk.BOTH, expand=True)
        detail_text.insert("1.0", story_data.get("notes", ""))
        
        def on_story_select(event):
            selection = story_list.curselection()
            if selection and selection[0] < len(story_data.get("story_arcs", [])):
                arc = story_data["story_arcs"][selection[0]]
                detail_text.delete("1.0", tk.END)
                detail_text.insert("1.0", f"标题: {arc.get('title', '')}\n\n{arc.get('content', '')}")
        
        story_list.bind('<<ListboxSelect>>', on_story_select)
        
        # 操作按钮
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        
        def add_arc():
            title = tk.simpledialog.askstring("添加故事线", "故事线标题:")
            if title:
                story_data.setdefault("story_arcs", []).append({"title": title, "content": ""})
                story_list.insert(tk.END, f"• {title}")
                self._log(f"为 {char_name} 添加故事线: {title}")
        
        def edit_arc():
            selection = story_list.curselection()
            if not selection:
                messagebox.showwarning("提示", "请先选择故事线")
                return
            idx = selection[0]
            if idx < len(story_data.get("story_arcs", [])):
                content = detail_text.get("1.0", tk.END).strip()
                story_data["story_arcs"][idx]["content"] = content
                self._log(f"更新 {char_name} 的故事线")
        
        def save_story():
            story_data["notes"] = detail_text.get("1.0", tk.END).strip()
            with open(story_file, 'w', encoding='utf-8') as f:
                json.dump(story_data, f, indent=2, ensure_ascii=False)
            self._log(f"已保存 {char_name} 的故事线")
            messagebox.showinfo("成功", "故事线已保存")
        
        def view_all_stories():
            """查看所有角色的故事线"""
            all_stories_window = tk.Toplevel(dialog)
            all_stories_window.title("所有角色故事线")
            all_stories_window.geometry("700x500")
            all_stories_window.configure(bg=C['bg_dark'])
            
            all_text = tk.Text(all_stories_window, wrap=tk.WORD, font=('微软雅黑', 10),
                              bg=C['bg_card'], fg=C['text_primary'])
            all_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # 加载所有角色故事
            for f in stories_dir.glob("*.json"):
                try:
                    with open(f, 'r', encoding='utf-8') as fp:
                        data = json.load(fp)
                    name = data.get("name", f.stem)
                    all_text.insert(tk.END, f"═══ {name} ═══\n")
                    for arc in data.get("story_arcs", []):
                        all_text.insert(tk.END, f"  📖 {arc.get('title', '')}\n")
                        if arc.get('content'):
                            all_text.insert(tk.END, f"     {arc['content'][:100]}...\n")
                    if data.get("notes"):
                        all_text.insert(tk.END, f"  备注: {data['notes'][:100]}...\n")
                    all_text.insert(tk.END, "\n")
                except Exception as e:
                    logger.debug(f"读取角色故事失败 {f.name}: {e}")
            
            all_text.config(state=tk.DISABLED)
        
        tk.Button(btn_frame, text="添加故事线", command=add_arc, bg=C['accent'], fg='white',
                 font=('微软雅黑', 9), padx=8).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="更新内容", command=edit_arc, bg=C['bg_light'], fg=C['text_primary'],
                 font=('微软雅黑', 9), padx=8).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="保存", command=save_story, bg=C['success'], fg='white',
                 font=('微软雅黑', 9), padx=8).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="查看所有角色故事", command=view_all_stories, bg=C['bg_light'], fg=C['text_primary'],
                 font=('微软雅黑', 9), padx=8).pack(side=tk.RIGHT, padx=3)
    def _equip_weapon(self):
        """装备武器"""
        if not self.character_system or not self.character_system.character:
            messagebox.showinfo("提示", "请先创建角色")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("选择武器")
        dialog.geometry("500x450")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="选择武器:", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(10, 5))
        
        cat_var = tk.StringVar()
        cats = self.character_system.get_weapon_categories()
        cat_combo = ttk.Combobox(dialog, textvariable=cat_var, values=cats, state="readonly", width=20)
        cat_combo.pack(pady=5)
        cat_combo.set(cats[0] if cats else "")
        
        weapon_listbox = tk.Listbox(dialog, bg=C['bg_card'], fg=C['text_primary'],
                                   font=('微软雅黑', 9), selectbackground=C['accent'], height=10)
        weapon_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        def update_list(*args):
            weapon_listbox.delete(0, tk.END)
            weapons = self.character_system.get_weapons(cat_var.get())
            for w in weapons:
                q = w.get('quality', '')
                custom = " [自定义]" if w.get('custom') else ""
                attrs = ", ".join(f"{k}:{v}" for k, v in w.get('attributes', {}).items())
                weapon_listbox.insert(tk.END, f"[{q}]{custom} {w.get('name', '')} - {attrs}")
        
        cat_combo.bind('<<ComboboxSelected>>', update_list)
        update_list()
        
        def equip():
            sel = weapon_listbox.curselection()
            if sel:
                weapons = self.character_system.get_weapons(cat_var.get())
                if sel[0] < len(weapons):
                    weapon = weapons[sel[0]]
                    self.character_system.character.equip_weapon(weapon)
                    self.character_system.save_character()
                    self._update_char_display()
                    self._log(f"装备武器: {weapon.get('name', '')}")
                    dialog.destroy()
        
        def add_custom():
            """添加自定义武器"""
            sub = tk.Toplevel(dialog)
            sub.title("自定义武器")
            sub.geometry("350x300")
            sub.configure(bg=C['bg_dark'])
            
            fields = {}
            for label, default in [("名称:", ""), ("品质:", "凡品"), ("描述:", ""), ("力量加成:", "10"), 
                                   ("敏捷加成:", "0"), ("体质加成:", "0"), ("智力加成:", "0")]:
                tk.Label(sub, text=label, bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(5,0))
                e = tk.Entry(sub, width=30)
                e.insert(0, default)
                e.pack(padx=20)
                fields[label] = e
            
            def save_custom():
                name = fields["名称:"].get().strip()
                if not name:
                    return
                attrs = {}
                for attr_name, field_key in [("力量", "力量加成:"), ("敏捷", "敏捷加成:"), 
                                              ("体质", "体质加成:"), ("智力", "智力加成:")]:
                    try:
                        val = int(fields[field_key].get())
                        if val > 0:
                            attrs[attr_name] = val
                    except (ValueError, KeyError, tk.TclError):
                        pass
                
                self.character_system.add_custom_weapon(
                    name=name, category=cat_var.get(), quality=fields["品质:"].get(),
                    desc=fields["描述:"].get(), attributes=attrs
                )
                update_list()
                self._log(f"添加自定义武器: {name}")
                sub.destroy()
            
            tk.Button(sub, text="保存", bg=C['accent'], fg='white', command=save_custom).pack(pady=10)
        
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_frame, text="装备", font=('微软雅黑', 10),
                 bg=C['accent'], fg='white', relief=tk.FLAT, command=equip).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="+ 自定义武器", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, command=add_custom).pack(side=tk.RIGHT, padx=5)
    def _learn_skill(self):
        """学习技能"""
        if not self.character_system or not self.character_system.character:
            messagebox.showinfo("提示", "请先创建角色")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("学习技能")
        dialog.geometry("500x450")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="选择技能:", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(10, 5))
        
        cat_var = tk.StringVar()
        cats = self.character_system.get_skill_categories()
        cat_combo = ttk.Combobox(dialog, textvariable=cat_var, values=cats, state="readonly", width=20)
        cat_combo.pack(pady=5)
        cat_combo.set(cats[0] if cats else "")
        
        skill_listbox = tk.Listbox(dialog, bg=C['bg_card'], fg=C['text_primary'],
                                  font=('微软雅黑', 9), selectbackground=C['accent'], height=10)
        skill_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        def update_list(*args):
            skill_listbox.delete(0, tk.END)
            skills = self.character_system.get_skills(cat_var.get())
            for s in skills:
                custom = " [自定义]" if s.get('custom') else ""
                skill_listbox.insert(tk.END, f"{s.get('name', '')}{custom} - {s.get('desc', '')} (MP:{s.get('mp_cost', 0)})")
        
        cat_combo.bind('<<ComboboxSelected>>', update_list)
        update_list()
        
        def learn():
            sel = skill_listbox.curselection()
            if sel:
                skills = self.character_system.get_skills(cat_var.get())
                if sel[0] < len(skills):
                    skill = skills[sel[0]]
                    if self.character_system.character.learn_skill(skill):
                        self.character_system.save_character()
                        self._update_char_display()
                        self._log(f"学会技能: {skill.get('name', '')}")
                    else:
                        messagebox.showinfo("提示", "已学会该技能")
                    dialog.destroy()
        
        def add_custom():
            sub = tk.Toplevel(dialog)
            sub.title("自定义技能")
            sub.geometry("350x250")
            sub.configure(bg=C['bg_dark'])
            
            fields = {}
            for label, default in [("名称:", ""), ("类型:", cat_var.get() or "攻击"), ("描述:", ""), ("MP消耗:", "10")]:
                tk.Label(sub, text=label, bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(5,0))
                e = tk.Entry(sub, width=30)
                e.insert(0, default)
                e.pack(padx=20)
                fields[label] = e
            
            def save_custom():
                name = fields["名称:"].get().strip()
                if not name:
                    return
                mp = int(fields["MP消耗:"].get() or 0)
                self.character_system.add_custom_skill(
                    name=name, skill_type=fields["类型:"].get(),
                    desc=fields["描述:"].get(), mp_cost=mp
                )
                update_list()
                self._log(f"添加自定义技能: {name}")
                sub.destroy()
            
            tk.Button(sub, text="保存", bg=C['accent'], fg='white', command=save_custom).pack(pady=10)
        
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_frame, text="学习", font=('微软雅黑', 10),
                 bg=C['accent'], fg='white', relief=tk.FLAT, command=learn).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="+ 自定义技能", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, command=add_custom).pack(side=tk.RIGHT, padx=5)
