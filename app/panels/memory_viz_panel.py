"""记忆系统可视化面板混入"""
import tkinter as tk

from app.ui_style import UIStyle


class MemoryVizPanelMixin:
    """记忆系统可视化面板混入 - 提供记忆状态查看功能"""

    def _build_memory_viz_tool(self):
        """记忆系统可视化 - 查看记忆状态"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="记忆系统可视化", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        if not self.current_novel_dir:
            tk.Label(f, text="请先新建或打开小说", font=("", 10),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
            return
        
        # 记忆统计
        stats_frame = tk.Frame(f, bg=C['bg_dark'])
        stats_frame.pack(fill=tk.X, pady=5)
        
        report = self.memory.health_check()
        
        stats_text = f"""记忆系统状态:
- 章节数: {report.get('total_chapters', 0)}
- 卷数: {report.get('total_volumes', 0)}
- 角色数: {report.get('total_characters', 0)}
- 弧线数: {report.get('total_arcs', 0)}
- 记忆块: {report.get('total_chunks', 0)}
- 衰减记忆: {len(report.get('stale_chunks', []))}"""
        
        tk.Label(stats_frame, text=stats_text, font=("微软雅黑", 10),
                bg=C['bg_dark'], fg=C['text_primary'], justify=tk.LEFT).pack(anchor=tk.W, padx=10)
        
        # 建议
        if report.get('recommendations'):
            tk.Label(f, text="建议:", font=("", 10, "bold"),
                    bg=C['bg_dark'], fg=C['warning']).pack(anchor=tk.W, pady=(10, 3))
            for rec in report['recommendations']:
                tk.Label(f, text=f"  - {rec}", font=("微软雅黑", 9),
                        bg=C['bg_dark'], fg=C['text_secondary']).pack(anchor=tk.W)
        
        # 操作按钮
        btn_frame = tk.Frame(f, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame, text="刷新", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT,
                 command=self._build_memory_viz_tool).pack(side=tk.LEFT, padx=5)
