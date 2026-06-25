"""
写作技能面板 - 管理写作风格和技能
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novel_app import NovelWriterApp


class WritingSkillsPanelMixin:
    """写作技能面板Mixin"""
    
    def _create_writing_skills_panel(self: 'NovelWriterApp', parent):
        """创建写作技能面板"""
        from app.ui_style import UIStyle
        C = UIStyle.COLORS
        
        # 主框架
        main_frame = tk.Frame(parent, bg=C['bg_dark'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 标题
        tk.Label(main_frame, text="✍️ 写作技能系统", font=('微软雅黑', 14, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(anchor=tk.W, pady=(0, 10))
        
        # 风格配置区
        style_frame = tk.LabelFrame(main_frame, text="写作风格配置", bg=C['bg_dark'], fg=C['text_primary'])
        style_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 风格旋钮
        sliders = [
            ("描写细腻度", "descriptiveness", "简洁 ← → 华丽"),
            ("对话比例", "dialogue_ratio", "叙述 ← → 对话"),
            ("节奏", "pacing", "慢节奏 ← → 快节奏"),
            ("情感深度", "emotional_depth", "表面 ← → 深入"),
            ("动作强度", "action_intensity", "平淡 ← → 激烈"),
        ]
        
        self._style_sliders = {}
        for i, (label, key, desc) in enumerate(sliders):
            row_frame = tk.Frame(style_frame, bg=C['bg_dark'])
            row_frame.pack(fill=tk.X, padx=10, pady=3)
            
            tk.Label(row_frame, text=label, font=('微软雅黑', 10),
                    bg=C['bg_dark'], fg=C['text_primary'], width=10).pack(side=tk.LEFT)
            
            slider = tk.Scale(row_frame, from_=1, to=10, orient=tk.HORIZONTAL,
                            bg=C['bg_dark'], fg=C['text_primary'], highlightthickness=0,
                            troughcolor=C['bg_medium'], command=lambda v, k=key: self._on_style_change(k, v))
            slider.set(5)
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
            self._style_sliders[key] = slider
            
            tk.Label(row_frame, text=desc, font=('微软雅黑', 8),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(side=tk.RIGHT)
        
        # 按钮区
        btn_frame = tk.Frame(main_frame, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=10)
        
        tk.Button(btn_frame, text="🔍 分析当前章节", command=self._analyze_current_chapter,
                 bg=C['accent'], fg='white', font=('微软雅黑', 10),
                 padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="📝 应用风格", command=self._apply_writing_style,
                 bg=C['success'], fg='white', font=('微软雅黑', 10),
                 padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="💾 保存配置", command=self._save_writing_config,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 10),
                 padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        # 分析结果区
        result_frame = tk.LabelFrame(main_frame, text="分析结果", bg=C['bg_dark'], fg=C['text_primary'])
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self._analysis_text = tk.Text(result_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                                     bg=C['bg_medium'], fg=C['text_primary'],
                                     height=10, state=tk.DISABLED)
        self._analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 知识图谱区
        graph_frame = tk.LabelFrame(main_frame, text="知识图谱", bg=C['bg_dark'], fg=C['text_primary'])
        graph_frame.pack(fill=tk.X, pady=(10, 0))
        
        self._graph_info_label = tk.Label(graph_frame, text="暂无数据", font=('微软雅黑', 10),
                                         bg=C['bg_dark'], fg=C['text_secondary'])
        self._graph_info_label.pack(anchor=tk.W, padx=10, pady=5)
        
        tk.Button(graph_frame, text="🔄 更新图谱", command=self._update_knowledge_graph,
                 bg=C['bg_light'], fg=C['text_primary'], font=('微软雅黑', 9),
                 padx=10, pady=3).pack(anchor=tk.W, padx=10, pady=5)
    
    def _on_style_change(self: 'NovelWriterApp', key: str, value: str):
        """风格旋钮变化"""
        from app.writing_skills import writing_skill_manager
        setattr(writing_skill_manager.style_config, key, int(value))
    
    def _analyze_current_chapter(self: 'NovelWriterApp'):
        """分析当前章节"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        if not hasattr(self, 'content_text'):
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "章节内容为空")
            return
        
        from app.writing_skills import writing_skill_manager
        
        # 获取小说类型（从meta.json的genre字段）
        try:
            meta = self._get_meta()
            genre = meta.get('genre', '玄幻-东方玄幻')
        except Exception:
            genre = '玄幻-东方玄幻'
        
        # 分析
        _, improvements = writing_skill_manager.analyze_and_improve(content, genre)
        
        # 显示结果
        self._analysis_text.config(state=tk.NORMAL)
        self._analysis_text.delete("1.0", tk.END)
        self._analysis_text.insert("1.0", '\n'.join(improvements))
        self._analysis_text.config(state=tk.DISABLED)
        
        self._log("[写作技能] 章节分析完成")
    
    def _apply_writing_style(self: 'NovelWriterApp'):
        """应用写作风格到配置"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        from app.writing_skills import writing_skill_manager
        
        # 更新配置
        for key, slider in self._style_sliders.items():
            setattr(writing_skill_manager.style_config, key, slider.get())
        
        # 获取小说类型
        try:
            meta = self._get_meta()
            writing_skill_manager.style_config.genre_style = meta.get('genre', '玄幻-东方玄幻')
        except Exception:
            pass
        
        messagebox.showinfo("成功", "写作风格已更新！\n下次生成章节时将应用新风格。")
        self._log("[写作技能] 风格配置已更新")
    
    def _save_writing_config(self: 'NovelWriterApp'):
        """保存写作配置"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        from app.writing_skills import writing_skill_manager
        
        # 更新配置
        for key, slider in self._style_sliders.items():
            setattr(writing_skill_manager.style_config, key, slider.get())
        
        # 保存
        config_dir = self.current_novel_dir / "writing_skills"
        writing_skill_manager.save_all(str(config_dir))
        
        messagebox.showinfo("成功", "写作配置已保存！")
        self._log("[写作技能] 配置已保存")
    
    def _update_knowledge_graph(self: 'NovelWriterApp'):
        """更新知识图谱"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先打开小说")
            return
        
        from app.writing_skills import writing_skill_manager
        
        # 加载角色信息
        if hasattr(self, 'character_system') and self.character_system:
            chars = self.character_system.get_all_characters()
            for name, char in chars.items():
                if name not in writing_skill_manager.knowledge_graph.entities:
                    writing_skill_manager.knowledge_graph.add_entity(name, "character", {
                        "level": char.level,
                        "title": char.title,
                        "faction": char.faction
                    })
            
            # 更新显示
            kg = writing_skill_manager.knowledge_graph
            self._graph_info_label.config(
                text=f"实体: {len(kg.entities)} | 关系: {len(kg.relations)} | 事件: {len(kg.events)}"
            )
            
            self._log(f"[知识图谱] 已更新: {len(kg.entities)}个实体")
