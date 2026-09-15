"""持久化层：备份、检查点、断电恢复、原子写

从 novel_app.py (P2-1 巨石拆分) 自动产生；方法体逐字节复制自原 NovelWriterApp，行为保持不变。
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


class PersistenceMixin:
    """持久化层：备份、检查点、断电恢复、原子写"""


    def _backup_novel(self, label: str = "auto"):
        """创建小说数据备份（带时间戳）"""
        if not self.current_novel_dir:
            return None
        try:
            backup_dir = self.current_novel_dir / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{label}_{timestamp}"
            backup_path = backup_dir / backup_name
            backup_path.mkdir(exist_ok=True)
            
            # 备份关键文件
            for src_name in ["meta.json", "outline.json"]:
                src = self.current_novel_dir / src_name
                if src.exists():
                    shutil.copy2(src, backup_path / src_name)
            
            # 备份 outlines/
            outlines_src = self.current_novel_dir / "outlines"
            if outlines_src.exists():
                outlines_dst = backup_path / "outlines"
                shutil.copytree(outlines_src, outlines_dst, dirs_exist_ok=True)
            
            # 备份 characters/
            chars_src = self.current_novel_dir / "characters"
            if chars_src.exists():
                chars_dst = backup_path / "characters"
                shutil.copytree(chars_src, chars_dst, dirs_exist_ok=True)
            
            # 备份 memory/settings.json 和 memory/characters.json
            mem_src = self.current_novel_dir / "memory"
            if mem_src.exists():
                mem_dst = backup_path / "memory"
                mem_dst.mkdir(exist_ok=True)
                for fn in ["settings.json", "characters.json", "settings.md"]:
                    fp = mem_src / fn
                    if fp.exists():
                        shutil.copy2(fp, mem_dst / fn)
            
            # 清理旧备份（保留最近10个）
            backups = sorted(backup_dir.iterdir(), key=lambda p: p.name, reverse=True)
            for old in backups[10:]:
                shutil.rmtree(old, ignore_errors=True)
            
            self._log(f"[备份] 已创建 {label} 备份: {backup_name}")
            return backup_path
        except Exception as e:
            self._log(f"[备份] 备份失败: {e}")
            return None
    def _save_checkpoint(self, chapter_num: int, status: str = "generating"):
        """保存生成检查点（用于断电恢复）"""
        if not self.current_novel_dir:
            return
        try:
            checkpoint = {
                "chapter": chapter_num,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "outline_count": len(self.outline) if self.outline else 0
            }
            cp_file = self.current_novel_dir / "checkpoint.json"
            # 原子写入：先写临时文件，再重命名
            tmp_file = cp_file.with_suffix('.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, indent=2, ensure_ascii=False)
            tmp_file.replace(cp_file)
        except Exception:
            pass
    def _clear_checkpoint(self):
        """清除检查点（生成完成）"""
        if not self.current_novel_dir:
            return
        try:
            cp_file = self.current_novel_dir / "checkpoint.json"
            if cp_file.exists():
                cp_file.unlink()
        except Exception:
            pass
    def _check_recovery(self):
        """检查是否有未完成的生成任务（断电恢复）"""
        if not self.current_novel_dir:
            return
        cp_file = self.current_novel_dir / "checkpoint.json"
        if not cp_file.exists():
            return
        try:
            with open(cp_file, 'r', encoding='utf-8') as f:
                cp = json.load(f)
            ch = cp.get("chapter", 0)
            ts = cp.get("timestamp", "未知")
            status = cp.get("status", "unknown")
            
            if status == "generating":
                self._log(f"[恢复] 检测到未完成的生成任务：第{ch}章 ({ts})")
                self._log(f"[恢复] 可使用「自动创作」继续，已完成的章节会自动跳过")
            elif status == "completed":
                self._clear_checkpoint()
        except Exception:
            pass
    def _atomic_write(self, filepath: Path, content: str, encoding: str = 'utf-8'):
        """原子写入文件（先写临时文件，再重命名，防止断电损坏）"""
        tmp_file = filepath.with_suffix('.tmp')
        with open(tmp_file, 'w', encoding=encoding) as f:
            f.write(content)
        tmp_file.replace(filepath)
    def _atomic_json_write(self, filepath: Path, data: Any):
        """原子写入JSON文件"""
        tmp_file = filepath.with_suffix('.tmp')
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_file.replace(filepath)
