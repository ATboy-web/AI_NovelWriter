"""批量操作面板混入"""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, filedialog

from app.ui_style import UIStyle


class BatchOpsPanelMixin:
    """批量操作面板混入 - 提供批量导入导出和摘要生成功能"""

    def _build_batch_ops_tool(self):
        """批量操作 - 批量导入导出"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="批量操作", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        if not self.current_novel_dir:
            tk.Label(f, text="请先新建或打开小说", font=("", 10),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
            return
        
        # 批量导入
        import_frame = tk.LabelFrame(f, text="批量导入", padx=10, pady=10,
                                     bg=C['bg_dark'], fg=C['text_primary'])
        import_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(import_frame, text="从文件夹批量导入章节文件（支持txt/md格式）",
                font=("微软雅黑", 9), bg=C['bg_dark'], fg=C['text_secondary']).pack(anchor=tk.W)
        
        def batch_import():
            folder = filedialog.askdirectory(title="选择包含章节文件的文件夹")
            if not folder:
                return
            folder_path = Path(folder)
            text_files = sorted(list(folder_path.glob("*.txt")) + list(folder_path.glob("*.md")))
            if not text_files:
                messagebox.showinfo("提示", "该文件夹中没有txt/md文件")
                return
            
            chapters_dir = self.current_novel_dir / "chapters"
            chapters_dir.mkdir(exist_ok=True)
            existing = sorted(chapters_dir.glob("chapter_*.txt"))
            next_num = len(existing) + 1
            
            imported = 0
            for src in text_files:
                try:
                    content = src.read_text(encoding='utf-8')
                except (OSError, UnicodeDecodeError):
                    try:
                        content = src.read_text(encoding='gbk')
                    except Exception:
                        continue
                dest = chapters_dir / f"chapter_{next_num:05d}.txt"
                dest.write_text(content, encoding='utf-8')
                next_num += 1
                imported += 1
            
            self._log(f"批量导入 {imported} 个章节文件")
            messagebox.showinfo("成功", f"已导入 {imported} 个章节文件")
        
        tk.Button(import_frame, text="选择文件夹批量导入", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT,
                 command=batch_import).pack(anchor=tk.W, pady=5)
        
        # 批量导出
        export_frame = tk.LabelFrame(f, text="批量导出", padx=10, pady=10,
                                     bg=C['bg_dark'], fg=C['text_primary'])
        export_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(export_frame, text="导出所有章节到指定文件夹",
                font=("微软雅黑", 9), bg=C['bg_dark'], fg=C['text_secondary']).pack(anchor=tk.W)
        
        def batch_export():
            if not self.current_novel_dir:
                return
            folder = filedialog.askdirectory(title="选择导出目标文件夹")
            if not folder:
                return
            
            chapters_dir = self.current_novel_dir / "chapters"
            if not chapters_dir.exists():
                messagebox.showinfo("提示", "没有章节文件")
                return
            
            chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
            exported = 0
            for cf in chapter_files:
                dest = Path(folder) / cf.name
                dest.write_text(cf.read_text(encoding='utf-8'), encoding='utf-8')
                exported += 1
            
            self._log(f"批量导出 {exported} 个章节文件")
            messagebox.showinfo("成功", f"已导出 {exported} 个章节文件到 {folder}")
        
        tk.Button(export_frame, text="导出所有章节", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT,
                 command=batch_export).pack(anchor=tk.W, pady=5)
        
        # 批量生成摘要
        summary_frame = tk.LabelFrame(f, text="批量生成摘要", padx=10, pady=10,
                                      bg=C['bg_dark'], fg=C['text_primary'])
        summary_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(summary_frame, text="为所有卷自动生成摘要（需AI配置）",
                font=("微软雅黑", 9), bg=C['bg_dark'], fg=C['text_secondary']).pack(anchor=tk.W)
        
        def batch_summary():
            if not self.ai_client.is_configured():
                messagebox.showwarning("提示", "请先配置AI")
                return
            
            chapters_dir = self.current_novel_dir / "chapters"
            if not chapters_dir.exists():
                return
            
            total_chapters = len(list(chapters_dir.glob("chapter_*.txt")))
            total_volumes = (total_chapters - 1) // 100 + 1
            
            def run():
                for vol in range(1, total_volumes + 1):
                    self.memory.auto_generate_volume_summary(vol)
                    self.root.after(0, lambda v=vol: self._log(f"第{v}卷摘要已生成"))
                self.root.after(0, lambda: messagebox.showinfo("完成", f"已生成 {total_volumes} 个卷级摘要"))
            
            threading.Thread(target=run, daemon=True).start()
        
        tk.Button(summary_frame, text="批量生成卷级摘要", font=('微软雅黑', 9),
                 bg=C['warning'], fg='white', relief=tk.FLAT,
                 command=batch_summary).pack(anchor=tk.W, pady=5)
