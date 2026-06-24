"""
设置管理器 - 处理设置相关的操作
从novel_app.py中提取的设置相关代码
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novel_app import NovelWriterApp


class SettingsManagerMixin:
    """设置管理Mixin类"""
    
    def _show_settings(self: 'NovelWriterApp'):
        """显示设置对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.geometry("600x700")
        dialog.configure(bg=self.C['bg_dark'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        C = self.C
        
        # 创建Notebook
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # === AI设置页 ===
        ai_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(ai_frame, text="🤖 AI设置")
        
        tk.Label(ai_frame, text="AI API配置", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(pady=10)
        
        # API提供者
        tk.Label(ai_frame, text="API提供者:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        provider_var = tk.StringVar(value=self.config.get("api_provider", "openai"))
        provider_combo = ttk.Combobox(ai_frame, textvariable=provider_var,
                                     values=["openai", "deepseek", "mimo", "claude", "ollama", "custom"],
                                     state="readonly", width=20)
        provider_combo.pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        # API端点
        tk.Label(ai_frame, text="API端点:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        endpoint_entry = tk.Entry(ai_frame, font=('微软雅黑', 10), bg=C['bg_medium'], fg=C['text_primary'], width=50)
        endpoint_entry.insert(0, self.config.get("api_endpoint", ""))
        endpoint_entry.pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        # API密钥
        tk.Label(ai_frame, text="API密钥:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        key_entry = tk.Entry(ai_frame, font=('微软雅黑', 10), bg=C['bg_medium'], fg=C['text_primary'], 
                            width=50, show="*")
        key_entry.insert(0, self.config.get("api_key", ""))
        key_entry.pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        # 模型
        tk.Label(ai_frame, text="模型:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20)
        model_entry = tk.Entry(ai_frame, font=('微软雅黑', 10), bg=C['bg_medium'], fg=C['text_primary'], width=30)
        model_entry.insert(0, self.config.get("model", ""))
        model_entry.pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        # 思考模式
        thinking_var = tk.BooleanVar(value=self.config.get("thinking_enabled", True))
        tk.Checkbutton(ai_frame, text="启用思考模式 (DeepSeek/MIMO)", variable=thinking_var,
                      font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                      selectcolor=C['bg_card']).pack(anchor=tk.W, padx=20, pady=5)
        
        # === 创作设置页 ===
        create_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(create_frame, text="📝 创作设置")
        
        tk.Label(create_frame, text="创作偏好", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['accent']).pack(pady=10)
        
        # 内容模式
        mode_frame = tk.LabelFrame(create_frame, text="内容模式", bg=C['bg_dark'], fg=C['text_primary'])
        mode_frame.pack(fill=tk.X, padx=20, pady=5)
        
        adult_var = tk.BooleanVar(value=self.adult_mode)
        edge_var = tk.BooleanVar(value=self.edge_mode)
        
        tk.Checkbutton(mode_frame, text="18+ 成人内容", variable=adult_var,
                      font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                      selectcolor=C['bg_card']).pack(anchor=tk.W, padx=10, pady=3)
        tk.Checkbutton(mode_frame, text="擦边内容", variable=edge_var,
                      font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                      selectcolor=C['bg_card']).pack(anchor=tk.W, padx=10, pady=3)
        
        # 生成参数
        param_frame = tk.LabelFrame(create_frame, text="生成参数", bg=C['bg_dark'], fg=C['text_primary'])
        param_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(param_frame, text="每章目标字数:", font=('微软雅黑', 10),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=10, pady=(5, 0))
        word_count_var = tk.StringVar(value=str(self.config.get("word_count_per_chapter", 10000)))
        word_count_spin = tk.Spinbox(param_frame, from_=1000, to=50000, increment=1000,
                                    textvariable=word_count_var, font=('微软雅黑', 10),
                                    bg=C['bg_medium'], fg=C['text_primary'], width=10)
        word_count_spin.pack(anchor=tk.W, padx=10, pady=(0, 5))
        
        # 保存函数
        def save_settings():
            # 保存AI设置
            self.config["api_provider"] = provider_var.get()
            self.config["api_endpoint"] = endpoint_entry.get().strip()
            self.config["api_key"] = key_entry.get().strip()
            self.config["model"] = model_entry.get().strip()
            self.config["thinking_enabled"] = thinking_var.get()
            
            # 保存创作设置
            self.adult_mode = adult_var.get()
            self.edge_mode = edge_var.get()
            self.config["word_count_per_chapter"] = int(word_count_var.get())
            
            # 重新初始化AI客户端
            if self.config["api_endpoint"] and self.config["api_key"]:
                from app import AIClient
                self.ai_client = AIClient(self.config)
                self._log(f"[设置] AI配置已更新: {self.config['api_provider']}")
            
            # 保存配置文件
            config_file = Path.home() / ".ai_novel_writer" / "config.json"
            config_file.parent.mkdir(exist_ok=True)
            config_file.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding='utf-8')
            
            self._update_status()
            dialog.destroy()
            messagebox.showinfo("保存成功", "设置已保存！")
        
        # 按钮
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(btn_frame, text="保存设置", command=save_settings,
                 bg=C['accent'], fg='white', font=('微软雅黑', 11, 'bold'),
                 padx=25, pady=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=dialog.destroy,
                 bg=C['bg_light'], fg=C['text_primary'],
                 font=('微软雅黑', 10), padx=20, pady=5).pack(side=tk.LEFT, padx=5)
    
    def _gen_settings(self: 'NovelWriterApp'):
        """生成世界观设置"""
        if not self._check_ready() or not self.current_novel_dir:
            return
        
        meta = self._get_meta()
        title = meta.get('title', '未知')
        genre = meta.get('type', '未知')
        concept = meta.get('concept', '')
        
        self._log("[世界观] 正在生成世界观...")
        
        def run():
            try:
                system = f"""你是世界观设定专家。为小说《{title}》({genre})创建详细的世界观设定。

输出JSON格式:
{{
    "world_name": "世界名称",
    "time_period": "时代背景",
    "magic_system": "力量体系描述",
    "geography": ["地区1", "地区2", ...],
    "factions": ["势力1", "势力2", ...],
    "rules": ["世界规则1", "世界规则2", ...],
    "technology": "科技水平",
    "culture": "文化特色"
}}"""
                
                response = self.ai_client.chat(
                    [{"role": "user", "content": f"概念: {concept}\n请创建世界观设定"}],
                    system=system, max_tokens=1500
                )
                
                if not response:
                    return
                
                # 保存世界观
                import re
                match = re.search(r'\{[\s\S]*\}', response)
                if match:
                    settings = json.loads(match.group())
                    settings_file = self.current_novel_dir / "memory" / "settings.json"
                    settings_file.parent.mkdir(exist_ok=True)
                    settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding='utf-8')
                    
                    self.root.after(0, lambda: self._log("[世界观] 世界观生成完成"))
                    self.root.after(0, lambda: messagebox.showinfo("成功", "世界观生成完成！"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("失败", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _gen_characters(self: 'NovelWriterApp'):
        """自动生成角色"""
        if not self._check_ready() or not self.current_novel_dir:
            return
        
        meta = self._get_meta()
        title = meta.get('title', '未知')
        genre = meta.get('type', '未知')
        
        self._log("[角色] 正在自动生成角色...")
        
        def run():
            try:
                # 读取世界观
                settings_file = self.current_novel_dir / "memory" / "settings.json"
                world_context = ""
                if settings_file.exists():
                    world_context = settings_file.read_text(encoding='utf-8')[:1000]
                
                system = f"""你是角色创建专家。为小说《{title}》({genre})创建主要角色。

世界观: {world_context[:500]}

创建以下角色:
1. 主角 - 性格鲜明，有成长空间
2. 女主/男主 - 与主角有化学反应
3. 反派 - 有合理动机
4. 导师 - 引导主角成长
5. 伙伴 - 忠诚可靠

输出JSON数组:
[
    {{
        "name": "角色名",
        "role": "主角/女主/反派/导师/伙伴",
        "faction": "正派/反派/中立",
        "description": "角色描述(50字)",
        "personality": "性格特点",
        "goal": "角色目标"
    }},
    ...
]"""
                
                response = self.ai_client.chat(
                    [{"role": "user", "content": "请创建主要角色"}],
                    system=system, max_tokens=2000
                )
                
                if not response:
                    return
                
                # 解析JSON
                import re
                match = re.search(r'\[[\s\S]*\]', response)
                if not match:
                    return
                
                chars_data = json.loads(match.group())
                
                # 创建角色
                chars_dir = self.current_novel_dir / "characters"
                chars_dir.mkdir(exist_ok=True)
                
                for char_data in chars_data:
                    name = char_data.get('name', '')
                    if not name:
                        continue
                    
                    # 保存到角色系统
                    self.character_system.create_character(
                        name=name,
                        faction=char_data.get('faction', '中立'),
                        category=char_data.get('role', '无名小卒'),
                        description=char_data.get('description', '')
                    )
                    self.character_system.save_character(name)
                
                self.root.after(0, lambda: [
                    self._update_char_display(),
                    self._log(f"[角色] 生成了{len(chars_data)}个角色"),
                    messagebox.showinfo("成功", f"生成了{len(chars_data)}个角色！")
                ])
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("失败", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _sync_memory_chars_to_dir(self: 'NovelWriterApp'):
        """同步记忆中的角色到characters目录"""
        if not self.current_novel_dir:
            return
        
        try:
            # 读取记忆中的角色
            chars_file = self.current_novel_dir / "memory" / "characters.json"
            if not chars_file.exists():
                return
            
            memory_chars = json.loads(chars_file.read_text(encoding='utf-8'))
            
            # 同步到CharacterSystem
            for name, data in memory_chars.items():
                if not self.character_system.get_character(name):
                    self.character_system.create_character(
                        name=name,
                        first_appearance=data.get('first_appearance', 1),
                        faction=data.get('faction', '中立'),
                        category=data.get('category', '无名小卒')
                    )
                    self.character_system.save_character(name)
            
            self._update_char_display()
            self._log(f"[同步] 同步了{len(memory_chars)}个角色")
        except Exception as e:
            self._log(f"[同步] 角色同步失败: {e}")
    
    def _sync_characters_from_memory(self: 'NovelWriterApp'):
        """从记忆同步角色"""
        self._sync_memory_chars_to_dir()
