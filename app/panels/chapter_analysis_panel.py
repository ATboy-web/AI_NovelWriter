"""章节分析面板混入"""
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, filedialog

from app.ui_style import UIStyle


class ChapterAnalysisPanelMixin:
    """章节分析面板混入 - 提供章节浏览、分析和智能推荐功能"""

    def _build_chapter_analysis_tool(self):
        """章节文件浏览+智能推荐"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="章节文件分析 - 浏览章节并推荐适用工具", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        if not self.current_novel_dir:
            tk.Label(f, text="请先新建或打开小说", font=("", 10),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        
        # 章节文件列表
        list_frame = tk.Frame(f, bg=C['bg_dark'])
        list_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(list_frame, text="章节文件:", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W)
        
        self.ch_file_listbox = tk.Listbox(list_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                          font=('微软雅黑', 9), height=8,
                                          selectbackground=C['accent'], relief=tk.FLAT)
        self.ch_file_listbox.pack(fill=tk.X, pady=3)
        self.ch_file_listbox.bind('<<ListboxSelect>>', self._on_chapter_file_select)
        
        # 刷新章节列表
        self._refresh_chapter_files()
        
        # 章节内容预览
        tk.Label(f, text="章节内容预览:", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 3))
        
        self.ch_preview = tk.Text(f, height=6, wrap=tk.WORD, font=('微软雅黑', 9),
                                 bg=C['bg_card'], fg=C['text_primary'],
                                 relief=tk.FLAT, padx=10, pady=10, state=tk.DISABLED)
        self.ch_preview.pack(fill=tk.X, pady=3)
        
        # 智能推荐区
        tk.Label(f, text="智能推荐 - 本章适用的创作工具:", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 3))
        
        self.ch_recommend = tk.Text(f, height=10, wrap=tk.WORD, font=('微软雅黑', 9),
                                   bg=C['bg_card'], fg=C['text_primary'],
                                   relief=tk.FLAT, padx=10, pady=10, state=tk.DISABLED)
        self.ch_recommend.pack(fill=tk.BOTH, expand=True, pady=3)
        
        # 操作按钮
        btn_frame = tk.Frame(f, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="刷新列表", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._refresh_chapter_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="导入章节文件", font=('微软雅黑', 9),
                 bg=C['warning'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._import_chapter_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="选择文件夹", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._browse_chapter_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="分析当前章节", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._analyze_current_chapter).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="加载到编辑区", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._load_chapter_to_editor).pack(side=tk.RIGHT, padx=5)

    def _refresh_chapter_files(self):
        """刷新章节文件列表"""
        self.ch_file_listbox.delete(0, tk.END)
        if not self.current_novel_dir:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        if not chapters_dir.exists():
            return
        
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        for f in chapter_files:
            size = f.stat().st_size
            size_kb = size / 1024
            name = f.stem.replace("chapter_", "第") + "章"
            self.ch_file_listbox.insert(tk.END, f"{name} ({size_kb:.1f}KB)")

    def _import_chapter_files(self):
        """从任意文件夹导入章节文件"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        file_paths = filedialog.askopenfilenames(
            title="选择章节文件",
            filetypes=[
                ("文本文件", "*.txt"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*")
            ]
        )
        
        if not file_paths:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        
        # 获取当前最大章节号
        existing = sorted(chapters_dir.glob("chapter_*.txt"))
        next_num = len(existing) + 1
        
        imported = 0
        for src in file_paths:
            src_path = Path(src)
            # 读取源文件
            try:
                with open(src_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(src_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError):
                    self._log(f"无法读取文件: {src_path.name}")
                    continue
            
            # 保存到章节目录
            dest = chapters_dir / f"chapter_{next_num:04d}.txt"
            with open(dest, 'w', encoding='utf-8') as f:
                f.write(content)
            
            next_num += 1
            imported += 1
        
        self._refresh_chapter_files()
        self._log(f"成功导入 {imported} 个章节文件")
        messagebox.showinfo("成功", f"已导入 {imported} 个章节文件")

    def _browse_chapter_folder(self):
        """选择文件夹浏览章节"""
        folder_path = filedialog.askdirectory(title="选择包含章节文件的文件夹")
        
        if not folder_path:
            return
        
        folder = Path(folder_path)
        
        # 扫描文件夹中的文本文件
        text_files = []
        for ext in ['*.txt', '*.md']:
            text_files.extend(folder.glob(ext))
        
        if not text_files:
            messagebox.showinfo("提示", "该文件夹中没有找到文本文件")
            return
        
        # 显示找到的文件
        text_files = sorted(text_files)
        
        # 创建选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"选择章节 - {folder.name}")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text=f"找到 {len(text_files)} 个文本文件:", 
                font=('微软雅黑', 10, 'bold')).pack(pady=10)
        
        # 文件列表（可多选）
        listbox = tk.Listbox(dialog, selectmode=tk.MULTIPLE, font=('微软雅黑', 9))
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        for f in text_files:
            size_kb = f.stat().st_size / 1024
            listbox.insert(tk.END, f"{f.name} ({size_kb:.1f}KB)")
        
        def import_selected():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("提示", "请选择要导入的文件")
                return
            
            if not self.current_novel_dir:
                messagebox.showwarning("提示", "请先新建或打开小说")
                dialog.destroy()
                return
            
            chapters_dir = self.current_novel_dir / "chapters"
            chapters_dir.mkdir(exist_ok=True)
            
            existing = sorted(chapters_dir.glob("chapter_*.txt"))
            next_num = len(existing) + 1
            
            imported = 0
            for idx in selected:
                src_path = text_files[idx]
                try:
                    with open(src_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(src_path, 'r', encoding='gbk') as f:
                            content = f.read()
                    except Exception:
                        continue
                
                dest = chapters_dir / f"chapter_{next_num:04d}.txt"
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                next_num += 1
                imported += 1
            
            self._refresh_chapter_files()
            self._log(f"从文件夹导入 {imported} 个章节文件")
            messagebox.showinfo("成功", f"已导入 {imported} 个章节文件")
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="全选", command=lambda: listbox.select_set(0, tk.END)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="导入选中", command=import_selected, bg='#10b981', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _on_chapter_file_select(self, event=None):
        """章节文件选中"""
        sel = self.ch_file_listbox.curselection()
        if not sel or not self.current_novel_dir:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        idx = sel[0]
        
        if idx < len(chapter_files):
            filepath = chapter_files[idx]
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 显示预览（前500字）
                preview = content[:500] + ("..." if len(content) > 500 else "")
                self.ch_preview.config(state=tk.NORMAL)
                self.ch_preview.delete("1.0", tk.END)
                self.ch_preview.insert("1.0", preview)
                self.ch_preview.config(state=tk.DISABLED)
                
                # 智能分析并推荐
                recommendations = self._analyze_chapter_content(content)
                self.ch_recommend.config(state=tk.NORMAL)
                self.ch_recommend.delete("1.0", tk.END)
                self.ch_recommend.insert("1.0", recommendations)
                self.ch_recommend.config(state=tk.DISABLED)
                
            except Exception as e:
                self._log(f"读取章节失败: {e}")

    def _analyze_chapter_content(self, content: str) -> str:
        """分析章节内容，推荐适用的创作工具"""
        recommendations = []
        
        # 战斗场景检测
        battle_keywords = ["战", "斗", "杀", "剑", "刀", "拳", "攻", "击", "斩", "劈", "刺"]
        battle_count = sum(1 for kw in battle_keywords if kw in content)
        if battle_count >= 3:
            recommendations.append("【桥段库 → 角色对战】检测到战斗场景，可使用「角色对战」桥段模板优化战斗描写。")
            recommendations.append("【描写库 → 战斗场景】建议使用「战斗场景」描写增强画面感。")
        
        # 情感场景检测
        emotion_keywords = ["爱", "恨", "泪", "笑", "心", "情", "思念", "牵挂", "拥抱", "吻"]
        emotion_count = sum(1 for kw in emotion_keywords if kw in content)
        if emotion_count >= 3:
            recommendations.append("【桥段库 → 情侣互动】检测到情感描写，可使用「情侣互动」「情侣对话」模板。")
            recommendations.append("【描写库 → 情感心理】建议使用「情感心理」描写增强感染力。")
        
        # 修炼/突破检测
        cultivate_keywords = ["修炼", "突破", "境界", "灵气", "丹田", "功法", "渡劫", "元婴"]
        cultivate_count = sum(1 for kw in cultivate_keywords if kw in content)
        if cultivate_count >= 2:
            recommendations.append("【桥段库 → 角色修炼】检测到修炼场景，可使用「角色修炼」桥段模板。")
            recommendations.append("【元素库 → 修炼体系】可参考「修炼体系」元素丰富设定。")
        
        # 登场/退场检测
        entrance_keywords = ["登场", "出场", "降临", "出现", "走来", "降临", "离开", "消失", "死去"]
        entrance_count = sum(1 for kw in entrance_keywords if kw in content)
        if entrance_count >= 2:
            recommendations.append("【桥段库 → 角色登场/退场】检测到角色出场或离场，可使用对应桥段模板。")
        
        # 对话检测
        dialogue_count = content.count('"') + content.count('"') + content.count('「') + content.count('」')
        if dialogue_count >= 10:
            recommendations.append("【对话推演】本章对话较多，可使用「情景对话推演」继续扩展对话。")
        
        # 描写场景检测
        scene_keywords = ["山", "水", "城", "宫", "殿", "天空", "大地", "森林", "海洋", "星空"]
        scene_count = sum(1 for kw in scene_keywords if kw in content)
        if scene_count >= 3:
            recommendations.append("【描写库 → 自然景观/建筑描写】检测到场景描写，可使用「自然景观」或「建筑描写」增强氛围。")
        
        # 角色外貌检测
        appearance_keywords = ["容貌", "美貌", "英俊", "潇洒", "绝美", "倾城", "飘逸", "冷峻"]
        appearance_count = sum(1 for kw in appearance_keywords if kw in content)
        if appearance_count >= 2:
            recommendations.append("【描写库 → 人物外貌】检测到外貌描写，可使用「人物外貌」描写模板。")
        
        # 追逐检测
        chase_keywords = ["追", "逃", "跑", "奔", "闪", "躲", "避"]
        chase_count = sum(1 for kw in chase_keywords if kw in content)
        if chase_count >= 3:
            recommendations.append("【桥段库 → 角色追逐】检测到追逐场景，可使用「角色追逐」桥段模板。")
        
        # 风格建议
        word_count = len(content)
        if word_count < 1500:
            recommendations.append("【风格转换】本章较短（{0}字），可使用「AI扩写」或「风格转换」丰富内容。".format(word_count))
        elif word_count > 5000:
            recommendations.append("【智能改编】本章较长（{0}字），可使用「AI简写」精简或「智能改编」优化节奏。".format(word_count))
        
        # 热点改编建议
        if "搞笑" in content or "幽默" in content or "哈哈" in content:
            recommendations.append("【热点改编】本章有幽默元素，可使用「热点改编→冷笑话」增加笑点。")
        
        if not recommendations:
            recommendations.append("本章暂无明显特征，可尝试使用以下工具：")
            recommendations.append("• 风格转换 - 调整文风")
            recommendations.append("• AI润色 - 优化语言表达")
            recommendations.append("• 描写库 - 增加细节描写")
            recommendations.append("• 桥段库 - 添加经典桥段")
        
        return "\n\n".join(recommendations)

    def _analyze_current_chapter(self):
        """分析当前编辑区的章节"""
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "编辑区没有内容")
            return
        
        recommendations = self._analyze_chapter_content(content)
        self.ch_recommend.config(state=tk.NORMAL)
        self.ch_recommend.delete("1.0", tk.END)
        self.ch_recommend.insert("1.0", recommendations)
        self.ch_recommend.config(state=tk.DISABLED)

    def _load_chapter_to_editor(self):
        """加载选中章节到编辑区"""
        sel = self.ch_file_listbox.curselection()
        if not sel or not self.current_novel_dir:
            messagebox.showinfo("提示", "请先选择一个章节文件")
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        idx = sel[0]
        
        if idx < len(chapter_files):
            filepath = chapter_files[idx]
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.content_text.delete("1.0", tk.END)
                self.content_text.insert("1.0", content)
                self.word_count_var.set(str(len(content)))
                
                # 更新当前章节号
                chapter_num = int(filepath.stem.split("_")[1])
                self.current_chapter = chapter_num
                self.chapter_title_var.set(f"第{chapter_num}章")
                
                self._log(f"已加载第{chapter_num}章到编辑区")
            except Exception as e:
                self._log(f"加载章节失败: {e}")
