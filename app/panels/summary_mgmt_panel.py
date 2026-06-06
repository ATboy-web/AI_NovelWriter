"""卷级摘要管理面板混入"""
import tkinter as tk

from app.ui_style import UIStyle


class SummaryMgmtPanelMixin:
    """卷级摘要管理面板混入 - 提供摘要查看和编辑功能"""

    def _build_summary_mgmt_tool(self):
        """卷级摘要管理 - 查看和编辑摘要"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="分层摘要管理", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        if not self.current_novel_dir:
            tk.Label(f, text="请先新建或打开小说", font=("", 10),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
            return
        
        # 全局摘要
        tk.Label(f, text="全局摘要:", font=("", 10, "bold"),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(5, 2))
        global_text = tk.Text(f, height=3, wrap=tk.WORD, font=("微软雅黑", 9),
                             bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT)
        global_text.pack(fill=tk.X, pady=2)
        gs = self.memory.get_global_summary()
        if gs:
            global_text.insert("1.0", gs)
        
        def save_global():
            content = global_text.get("1.0", tk.END).strip()
            if content:
                self.memory.save_global_summary(content)
                self._log("全局摘要已保存")
        
        tk.Button(f, text="保存全局摘要", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT,
                 command=save_global).pack(anchor=tk.W, pady=3)
        
        # 卷级摘要列表
        tk.Label(f, text="卷级摘要:", font=("", 10, "bold"),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 2))
        
        vol_frame = tk.Frame(f, bg=C['bg_dark'])
        vol_frame.pack(fill=tk.BOTH, expand=True)
        
        vol_listbox = tk.Listbox(vol_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                font=('微软雅黑', 9), height=6, relief=tk.FLAT)
        vol_listbox.pack(fill=tk.X, pady=3)
        
        # 加载卷级摘要
        volumes_dir = self.memory.volumes_dir
        if volumes_dir.exists():
            for vf in sorted(volumes_dir.glob("volume_*.txt")):
                vol_num = vf.stem.split("_")[1]
                vol_listbox.insert(tk.END, f"第{vol_num}卷")
        
        # 卷摘要预览
        vol_preview = tk.Text(f, height=3, wrap=tk.WORD, font=("微软雅黑", 9),
                             bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT)
        vol_preview.pack(fill=tk.X, pady=3)
        
        def on_vol_select(event):
            sel = vol_listbox.curselection()
            if sel:
                vol_num = int(vol_listbox.get(sel[0]).replace("第", "").replace("卷", ""))
                summary = self.memory.get_volume_summary(vol_num)
                vol_preview.delete("1.0", tk.END)
                vol_preview.insert("1.0", summary)
        
        vol_listbox.bind('<<ListboxSelect>>', on_vol_select)
        
        # 弧线摘要
        tk.Label(f, text="弧线摘要:", font=("", 10, "bold"),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 2))
        
        arc_listbox = tk.Listbox(f, bg=C['bg_card'], fg=C['text_secondary'],
                                font=('微软雅黑', 9), height=4, relief=tk.FLAT)
        arc_listbox.pack(fill=tk.X, pady=3)
        
        arcs = self.memory.get_all_arcs()
        for arc in arcs:
            arc_listbox.insert(tk.END, arc.get('name', ''))
