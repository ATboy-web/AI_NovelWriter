"""
角色管理器 - 处理角色系统的相关操作
从novel_app.py中提取的角色相关代码
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from novel_app import NovelWriterApp


class CharacterManagerMixin:
    """角色管理Mixin类"""
    
    def _init_character_system(self: 'NovelWriterApp'):
        """初始化角色系统"""
        if not self.current_novel_dir:
            return
        
        from character_system import CharacterSystem
        self.character_system = CharacterSystem(self.current_novel_dir)
        self.character_system.load()
        self._log("[角色] 角色系统初始化成功")
    
    def _update_char_display(self: 'NovelWriterApp'):
        """更新角色列表显示"""
        if not hasattr(self, 'char_listbox') or not self.character_system:
            return
        
        self.char_listbox.delete(0, tk.END)
        chars = self.character_system.get_all_characters()
        for name, char in sorted(chars.items(), key=lambda x: x[1].level, reverse=True):
            level = char.level
            title = char.title
            self.char_listbox.insert(tk.END, f"Lv.{level} {name} [{title}]")
    
    def _create_char_card(self: 'NovelWriterApp', name: str) -> tk.Frame:
        """创建角色卡片"""
        C = self.C
        card = tk.Frame(self.char_list_frame, bg=C['bg_card'], padx=10, pady=8)
        
        char = self.character_system.get_character(name)
        if not char:
            return card
        
        # 角色名和等级
        header = tk.Frame(card, bg=C['bg_card'])
        header.pack(fill=tk.X)
        
        tk.Label(header, text=f"⭐ {name}", font=('微软雅黑', 11, 'bold'),
                bg=C['bg_card'], fg=C['accent']).pack(side=tk.LEFT)
        
        tk.Label(header, text=f"Lv.{char.level} {char.title}", 
                font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_muted']).pack(side=tk.RIGHT)
        
        # 经验条
        exp_frame = tk.Frame(card, bg=C['bg_card'])
        exp_frame.pack(fill=tk.X, pady=(4, 0))
        
        exp_ratio = char.exp / char.exp_to_next if char.exp_to_next > 0 else 0
        exp_bar = tk.Canvas(exp_frame, height=6, bg=C['bg_medium'], highlightthickness=0)
        exp_bar.pack(fill=tk.X)
        exp_bar.create_rectangle(0, 0, int(200 * exp_ratio), 6, fill=C['success'], outline='')
        
        tk.Label(exp_frame, text=f"EXP: {char.exp}/{char.exp_to_next}", 
                font=('微软雅黑', 8), bg=C['bg_card'], fg=C['text_muted']).pack(anchor=tk.W)
        
        # 属性摘要
        stats_text = f"❤️{char.hp}/{char.max_hp} 💙{char.mp}/{char.max_mp} ⚔️{char.attributes.get('力量', 0)} 🛡️{char.attributes.get('体质', 0)}"
        tk.Label(card, text=stats_text, font=('微软雅黑', 9),
                bg=C['bg_card'], fg=C['text_secondary']).pack(anchor=tk.W, pady=(4, 0))
        
        # 点击事件
        card.bind("<Button-1>", lambda e, n=name: self._display_char_details(self.character_system.get_character(n)))
        for child in card.winfo_children():
            child.bind("<Button-1>", lambda e, n=name: self._display_char_details(self.character_system.get_character(n)))
        
        return card
    
    def _display_char_details(self: 'NovelWriterApp', char):
        """显示角色详情"""
        if not char or not hasattr(self, 'char_detail_text'):
            return
        
        C = self.C
        self.char_detail_text.config(state=tk.NORMAL)
        self.char_detail_text.delete("1.0", tk.END)
        
        # 基本信息
        self.char_detail_text.insert(tk.END, f"{'═' * 30}\n", "separator")
        self.char_detail_text.insert(tk.END, f"  ⭐ {char.name}\n", "title")
        self.char_detail_text.insert(tk.END, f"  等级: Lv.{char.level} {char.title}\n", "info")
        self.char_detail_text.insert(tk.END, f"{'═' * 30}\n\n", "separator")
        
        # 状态
        self.char_detail_text.insert(tk.END, "📊 状态\n", "section")
        self.char_detail_text.insert(tk.END, f"  ❤️ 生命: {char.hp}/{char.max_hp}\n")
        self.char_detail_text.insert(tk.END, f"  💙 法力: {char.mp}/{char.max_mp}\n")
        self.char_detail_text.insert(tk.END, f"  ⚡ 经验: {char.exp}/{char.exp_to_next}\n\n")
        
        # 属性
        self.char_detail_text.insert(tk.END, "💪 属性\n", "section")
        for attr, value in char.attributes.items():
            self.char_detail_text.insert(tk.END, f"  {attr}: {value}\n")
        
        # 装备
        if char.weapon:
            self.char_detail_text.insert(tk.END, f"\n⚔️ 武器: {char.weapon.get('name', '无')}\n", "section")
        if char.armor:
            self.char_detail_text.insert(tk.END, f"🛡️ 防具: {char.armor.get('name', '无')}\n")
        
        # 技能
        if char.skills:
            self.char_detail_text.insert(tk.END, f"\n✨ 技能 ({len(char.skills)})\n", "section")
            for skill in char.skills:
                self.char_detail_text.insert(tk.END, f"  • {skill.get('name', '未知')}\n")
        
        # 统计
        self.char_detail_text.insert(tk.END, f"\n📈 统计\n", "section")
        self.char_detail_text.insert(tk.END, f"  战斗次数: {char.stats.get('战斗次数', 0)}\n")
        self.char_detail_text.insert(tk.END, f"  胜利次数: {char.stats.get('胜利次数', 0)}\n")
        self.char_detail_text.insert(tk.END, f"  最高等级: {char.stats.get('最高等级', 1)}\n")
        
        self.char_detail_text.config(state=tk.DISABLED)
    
    def _gen_char_biography(self: 'NovelWriterApp'):
        """生成角色传记"""
        if not self._check_ready():
            return
        
        # 获取选中的角色
        selection = self.char_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个角色")
            return
        
        char_name = self.char_listbox.get(selection[0]).split(']')[0].split(' ')[1]
        self._generate_character_biography(char_name)
    
    def _on_char_select(self: 'NovelWriterApp', event=None):
        """角色列表选择事件"""
        if not hasattr(self, 'char_listbox'):
            return
        
        selection = self.char_listbox.curselection()
        if not selection:
            return
        
        char_info = self.char_listbox.get(selection[0])
        # 提取角色名
        try:
            char_name = char_info.split(']')[0].split(' ', 1)[1]
            char = self.character_system.get_character(char_name)
            if char:
                self._display_char_details(char)
        except Exception:
            pass
    
    def _create_character_dialog(self: 'NovelWriterApp'):
        """创建新角色对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("创建新角色")
        dialog.geometry("400x350")
        dialog.configure(bg=self.C['bg_dark'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        C = self.C
        
        tk.Label(dialog, text="创建新角色", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(pady=10)
        
        # 角色名
        tk.Label(dialog, text="角色名:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        name_entry = tk.Entry(dialog, font=('微软雅黑', 10), bg=C['bg_medium'], fg=C['text_primary'])
        name_entry.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        # 阵营
        tk.Label(dialog, text="阵营:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        faction_var = tk.StringVar(value="中立")
        faction_combo = ttk.Combobox(dialog, textvariable=faction_var, 
                                    values=["正派", "反派", "中立", "亦正亦邪"], state="readonly")
        faction_combo.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        # 描述
        tk.Label(dialog, text="描述 (可选):", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        desc_text = tk.Text(dialog, height=4, font=('微软雅黑', 9), bg=C['bg_medium'], fg=C['text_primary'])
        desc_text.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        def create():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入角色名")
                return
            
            if self.character_system.get_character(name):
                messagebox.showwarning("提示", "角色已存在")
                return
            
            # 创建角色
            self.character_system.create_character(
                name=name,
                faction=faction_var.get(),
                description=desc_text.get("1.0", tk.END).strip()
            )
            self.character_system.save_character(name)
            
            # 更新显示
            self._update_char_display()
            self._sync_characters_from_memory()
            
            self._log(f"[角色] 创建新角色: {name}")
            dialog.destroy()
            messagebox.showinfo("成功", f"角色「{name}」创建成功！")
        
        tk.Button(dialog, text="创建", command=create,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10, 'bold'),
                 padx=20, pady=5).pack(pady=10)
    
    def _ai_create_character(self: 'NovelWriterApp'):
        """AI自动创建角色"""
        if not self._check_ready():
            return
        
        # 获取小说信息
        meta = self._get_meta()
        title = meta.get('title', '未知')
        genre = meta.get('type', '未知')
        
        self._log("[角色] AI正在创建角色...")
        
        def run():
            try:
                system = f"""你是角色创建专家。为小说《{title}》({genre})创建一个有趣的角色。

输出JSON格式:
{{
    "name": "角色名",
    "faction": "正派/反派/中立/亦正亦邪",
    "category": "主角/配角/反派/路人",
    "description": "角色描述(50字)",
    "attributes": {{
        "力量": 10-30,
        "智力": 10-30,
        "敏捷": 10-30,
        "体质": 10-30,
        "魅力": 10-30,
        "幸运": 10-30
    }},
    "skills": [
        {{"name": "技能名", "type": "攻击/防御/辅助", "description": "技能描述"}}
    ]
}}"""
                
                response = self.ai_client.chat(
                    [{"role": "user", "content": "请创建一个角色"}],
                    system=system, max_tokens=1000
                )
                
                if not response:
                    return
                
                # 解析JSON
                import re
                match = re.search(r'\{[\s\S]*\}', response)
                if not match:
                    return
                
                data = json.loads(match.group())
                name = data.get('name', '')
                
                if not name:
                    return
                
                # 创建角色
                self.character_system.create_character(
                    name=name,
                    faction=data.get('faction', '中立'),
                    category=data.get('category', '无名小卒'),
                    description=data.get('description', '')
                )
                
                # 设置属性
                char = self.character_system.get_character(name)
                if char and 'attributes' in data:
                    for attr, value in data['attributes'].items():
                        if attr in char.attributes:
                            char.attributes[attr] = max(5, min(30, int(value)))
                
                # 添加技能
                if char and 'skills' in data:
                    for skill in data['skills']:
                        char.learn_skill(skill)
                
                self.character_system.save_character(name)
                
                self.root.after(0, lambda: [
                    self._update_char_display(),
                    self._sync_characters_from_memory(),
                    self._log(f"[角色] AI创建角色: {name}"),
                    messagebox.showinfo("成功", f"AI创建了角色「{name}」！")
                ])
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("失败", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _show_char_detail(self: 'NovelWriterApp'):
        """显示角色详情对话框"""
        selection = self.char_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个角色")
            return
        
        char_info = self.char_listbox.get(selection[0])
        try:
            char_name = char_info.split(']')[0].split(' ', 1)[1]
            char = self.character_system.get_character(char_name)
            if not char:
                return
            
            dialog = tk.Toplevel(self.root)
            dialog.title(f"角色详情 - {char_name}")
            dialog.geometry("500x600")
            dialog.configure(bg=self.C['bg_dark'])
            
            C = self.C
            
            # 使用Text显示详情
            text = tk.Text(dialog, wrap=tk.WORD, font=('微软雅黑', 10),
                          bg=C['bg_medium'], fg=C['text_primary'], padx=15, pady=15)
            text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            text.insert(tk.END, f"{'═' * 40}\n", "separator")
            text.insert(tk.END, f"  ⭐ {char.name}\n", "title")
            text.insert(tk.END, f"  Lv.{char.level} {char.title}\n", "info")
            text.insert(tk.END, f"{'═' * 40}\n\n", "separator")
            
            text.insert(tk.END, "📊 状态\n", "section")
            text.insert(tk.END, f"  ❤️ HP: {char.hp}/{char.max_hp}\n")
            text.insert(tk.END, f"  💙 MP: {char.mp}/{char.max_mp}\n")
            text.insert(tk.END, f"  ⚡ EXP: {char.exp}/{char.exp_to_next}\n\n")
            
            text.insert(tk.END, "💪 属性\n", "section")
            for attr, value in char.attributes.items():
                text.insert(tk.END, f"  {attr}: {value}\n")
            
            if char.skills:
                text.insert(tk.END, f"\n✨ 技能\n", "section")
                for skill in char.skills:
                    text.insert(tk.END, f"  • {skill.get('name', '未知')}: {skill.get('description', '')}\n")
            
            text.config(state=tk.DISABLED)
            
            # 格式化
            text.tag_config("title", font=('微软雅黑', 14, 'bold'), foreground=C['accent'])
            text.tag_config("info", font=('微软雅黑', 10), foreground=C['text_secondary'])
            text.tag_config("section", font=('微软雅黑', 11, 'bold'), foreground=C['warning'])
            text.tag_config("separator", foreground=C['border'])
            
        except Exception as e:
            messagebox.showerror("错误", str(e))
    
    def _rename_character(self: 'NovelWriterApp', dialog):
        """重命名角色"""
        selection = self.char_listbox.curselection()
        if not selection:
            return
        
        old_name = self.char_listbox.get(selection[0]).split(']')[0].split(' ', 1)[1]
        new_name = simpledialog.askstring("重命名", f"输入新的角色名:", initialvalue=old_name)
        
        if new_name and new_name != old_name:
            if self.character_system.get_character(new_name):
                messagebox.showwarning("提示", "角色名已存在")
                return
            
            # 重命名
            char = self.character_system.get_character(old_name)
            if char:
                char.name = new_name
                self.character_system.save_character(new_name)
                # 删除旧文件
                old_file = self.character_system._get_char_file(old_name)
                if old_file.exists():
                    old_file.unlink()
                
                self._update_char_display()
                self._log(f"[角色] 重命名: {old_name} → {new_name}")
    
    def _delete_character(self: 'NovelWriterApp', dialog):
        """删除角色"""
        selection = self.char_listbox.curselection()
        if not selection:
            return
        
        char_name = self.char_listbox.get(selection[0]).split(']')[0].split(' ', 1)[1]
        
        if messagebox.askyesno("确认删除", f"确定要删除角色「{char_name}」吗？"):
            # 删除文件
            char_file = self.character_system._get_char_file(char_name)
            if char_file.exists():
                char_file.unlink()
            
            # 从内存中移除
            if char_name in self.character_system.characters:
                del self.character_system.characters[char_name]
            
            self._update_char_display()
            self._log(f"[角色] 删除角色: {char_name}")
    
    def _rest_character(self: 'NovelWriterApp'):
        """角色休息 - 恢复HP/MP"""
        selection = self.char_listbox.curselection()
        if not selection:
            return
        
        char_name = self.char_listbox.get(selection[0]).split(']')[0].split(' ', 1)[1]
        char = self.character_system.get_character(char_name)
        
        if char:
            char.hp = char.max_hp
            char.mp = char.max_mp
            self.character_system.save_character(char_name)
            self._update_char_display()
            self._display_char_details(char)
            self._log(f"[角色] {char_name} 休息恢复")
    
    def _edit_character_story(self: 'NovelWriterApp', char_name: str):
        """编辑角色故事"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"编辑角色故事 - {char_name}")
        dialog.geometry("500x400")
        dialog.configure(bg=self.C['bg_dark'])
        
        C = self.C
        
        tk.Label(dialog, text=f"编辑「{char_name}」的故事背景", 
                font=('微软雅黑', 11, 'bold'), bg=C['bg_dark'], fg=C['accent']).pack(pady=10)
        
        story_text = tk.Text(dialog, wrap=tk.WORD, font=('微软雅黑', 10),
                            bg=C['bg_medium'], fg=C['text_primary'], height=15)
        story_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # 加载现有故事
        char = self.character_system.get_character(char_name)
        if char and hasattr(char, 'story'):
            story_text.insert("1.0", char.story)
        
        def save_story():
            if char:
                char.story = story_text.get("1.0", tk.END).strip()
                self.character_system.save_character(char_name)
                self._log(f"[角色] 更新{char_name}的故事")
                dialog.destroy()
        
        tk.Button(dialog, text="保存", command=save_story,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10),
                 padx=20, pady=5).pack(pady=10)
    
    def _equip_weapon(self: 'NovelWriterApp'):
        """装备武器"""
        selection = self.char_listbox.curselection()
        if not selection:
            return
        
        char_name = self.char_listbox.get(selection[0]).split(']')[0].split(' ', 1)[1]
        char = self.character_system.get_character(char_name)
        
        if not char:
            return
        
        # 简单的武器选择对话框
        weapons = [
            {"name": "铁剑", "attack": 5, "type": "剑"},
            {"name": "钢刀", "attack": 8, "type": "刀"},
            {"name": "长枪", "attack": 10, "type": "枪"},
            {"name": "法杖", "attack": 3, "magic": 10, "type": "杖"},
            {"name": "弓箭", "attack": 7, "type": "弓"},
        ]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"装备武器 - {char_name}")
        dialog.geometry("300x250")
        dialog.configure(bg=self.C['bg_dark'])
        
        C = self.C
        
        tk.Label(dialog, text="选择武器:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=10)
        
        listbox = tk.Listbox(dialog, bg=C['bg_medium'], fg=C['text_primary'],
                            font=('微软雅黑', 10))
        listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        for w in weapons:
            listbox.insert(tk.END, f"{w['name']} (攻击+{w['attack']})")
        
        def equip():
            idx = listbox.curselection()
            if idx:
                weapon = weapons[idx[0]]
                char.equip_weapon(weapon)
                self.character_system.save_character(char_name)
                self._display_char_details(char)
                self._log(f"[角色] {char_name} 装备了 {weapon['name']}")
                dialog.destroy()
        
        tk.Button(dialog, text="装备", command=equip,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10),
                 padx=20).pack(pady=10)
    
    def _learn_skill(self: 'NovelWriterApp'):
        """学习技能"""
        selection = self.char_listbox.curselection()
        if not selection:
            return
        
        char_name = self.char_listbox.get(selection[0]).split(']')[0].split(' ', 1)[1]
        char = self.character_system.get_character(char_name)
        
        if not char:
            return
        
        # 简单的技能选择
        skills = [
            {"name": "火球术", "type": "攻击", "description": "发射火球攻击敌人"},
            {"name": "冰冻术", "type": "控制", "description": "冻结敌人"},
            {"name": "治疗术", "type": "辅助", "description": "恢复生命值"},
            {"name": "护盾术", "type": "防御", "description": "增加防御力"},
            {"name": "加速术", "type": "辅助", "description": "提高行动速度"},
        ]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"学习技能 - {char_name}")
        dialog.geometry("350x300")
        dialog.configure(bg=self.C['bg_dark'])
        
        C = self.C
        
        tk.Label(dialog, text="选择技能:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=10)
        
        listbox = tk.Listbox(dialog, bg=C['bg_medium'], fg=C['text_primary'],
                            font=('微软雅黑', 10))
        listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        for s in skills:
            listbox.insert(tk.END, f"{s['name']} ({s['type']}): {s['description']}")
        
        def learn():
            idx = listbox.curselection()
            if idx:
                skill = skills[idx[0]]
                if char.learn_skill(skill):
                    self.character_system.save_character(char_name)
                    self._display_char_details(char)
                    self._log(f"[角色] {char_name} 学会了 {skill['name']}")
                    messagebox.showinfo("成功", f"学会了「{skill['name']}」！")
                else:
                    messagebox.showwarning("提示", "已经学会了这个技能")
                dialog.destroy()
        
        tk.Button(dialog, text="学习", command=learn,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10),
                 padx=20).pack(pady=10)
