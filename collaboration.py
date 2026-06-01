"""
多人协作系统 - 基于Git的协作功能
"""

import json
import subprocess
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class CollaborationManager:
    """协作管理器"""
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config_file = project_dir / ".collaboration.json"
        self.config = self._load_config()
        
        # 角色定义
        self.roles = {
            "主编": {
                "permissions": ["edit_all", "manage_roles", "publish"],
                "description": "负责整体把控"
            },
            "作者": {
                "permissions": ["edit_assigned", "view_outline"],
                "description": "负责章节创作"
            },
            "编辑": {
                "permissions": ["review", "suggest"],
                "description": "负责质量把控"
            },
            "读者": {
                "permissions": ["view", "comment"],
                "description": "试读和反馈"
            }
        }
    
    def _load_config(self) -> Dict:
        """加载协作配置"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "users": {},
            "chapter_assignments": {},
            "locks": {},
            "version_history": []
        }
    
    def _save_config(self):
        """保存协作配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    # ===== 用户管理 =====
    
    def add_user(self, username: str, role: str = "作者") -> bool:
        """添加用户"""
        if role not in self.roles:
            return False
        
        self.config["users"][username] = {
            "role": role,
            "added_at": datetime.now().isoformat(),
            "permissions": self.roles[role]["permissions"]
        }
        self._save_config()
        return True
    
    def remove_user(self, username: str) -> bool:
        """移除用户"""
        if username in self.config["users"]:
            del self.config["users"][username]
            self._save_config()
            return True
        return False
    
    def get_users(self) -> Dict:
        """获取所有用户"""
        return self.config.get("users", {})
    
    def get_user_role(self, username: str) -> Optional[str]:
        """获取用户角色"""
        user = self.config.get("users", {}).get(username)
        return user.get("role") if user else None
    
    # ===== 章节分配 =====
    
    def assign_chapter(self, chapter_num: int, username: str) -> bool:
        """分配章节给用户"""
        if username not in self.config.get("users", {}):
            return False
        
        self.config["chapter_assignments"][str(chapter_num)] = username
        self._save_config()
        return True
    
    def get_chapter_assignment(self, chapter_num: int) -> Optional[str]:
        """获取章节分配"""
        return self.config.get("chapter_assignments", {}).get(str(chapter_num))
    
    # ===== 章节锁定 =====
    
    def lock_chapter(self, chapter_num: int, username: str) -> bool:
        """锁定章节"""
        locks = self.config.get("locks", {})
        if str(chapter_num) in locks:
            # 检查是否被同一用户锁定
            if locks[str(chapter_num)]["user"] == username:
                return True  # 已经锁定
            return False  # 被其他人锁定
        
        locks[str(chapter_num)] = {
            "user": username,
            "locked_at": datetime.now().isoformat()
        }
        self.config["locks"] = locks
        self._save_config()
        return True
    
    def unlock_chapter(self, chapter_num: int, username: str) -> bool:
        """解锁章节"""
        locks = self.config.get("locks", {})
        if str(chapter_num) in locks and locks[str(chapter_num)]["user"] == username:
            del locks[str(chapter_num)]
            self.config["locks"] = locks
            self._save_config()
            return True
        return False
    
    def is_chapter_locked(self, chapter_num: int) -> bool:
        """检查章节是否被锁定"""
        return str(chapter_num) in self.config.get("locks", {})
    
    def get_chapter_lock(self, chapter_num: int) -> Optional[Dict]:
        """获取章节锁定信息"""
        return self.config.get("locks", {}).get(str(chapter_num))
    
    # ===== 版本控制 =====
    
    def init_git(self):
        """初始化Git仓库"""
        try:
            subprocess.run(["git", "init"], cwd=str(self.project_dir), 
                          capture_output=True, check=True)
            subprocess.run(["git", "add", "."], cwd=str(self.project_dir),
                          capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "初始化项目"], 
                          cwd=str(self.project_dir), capture_output=True, check=True)
            return True
        except Exception as e:
            print(f"Git初始化失败: {e}")
            return False
    
    def commit_changes(self, message: str, author: str = None) -> bool:
        """提交更改"""
        try:
            subprocess.run(["git", "add", "."], cwd=str(self.project_dir),
                          capture_output=True, check=True)
            
            cmd = ["git", "commit", "-m", message]
            if author:
                cmd.extend(["--author", f"{author} <{author}@novel.local>"])
            
            subprocess.run(cmd, cwd=str(self.project_dir),
                          capture_output=True, check=True)
            
            # 记录版本历史
            self.config.setdefault("version_history", []).append({
                "message": message,
                "author": author,
                "timestamp": datetime.now().isoformat()
            })
            self._save_config()
            
            return True
        except Exception as e:
            print(f"提交失败: {e}")
            return False
    
    def push_to_remote(self, remote: str = "origin", branch: str = "main") -> bool:
        """推送到远程仓库"""
        try:
            subprocess.run(["git", "push", remote, branch], 
                          cwd=str(self.project_dir), capture_output=True, check=True)
            return True
        except Exception as e:
            print(f"推送失败: {e}")
            return False
    
    def pull_from_remote(self, remote: str = "origin", branch: str = "main") -> bool:
        """从远程仓库拉取"""
        try:
            subprocess.run(["git", "pull", remote, branch], 
                          cwd=str(self.project_dir), capture_output=True, check=True)
            return True
        except Exception as e:
            print(f"拉取失败: {e}")
            return False
    
    def get_version_history(self) -> List[Dict]:
        """获取版本历史"""
        return self.config.get("version_history", [])
    
    # ===== 冲突检测 =====
    
    def check_conflicts(self) -> List[str]:
        """检查Git冲突"""
        try:
            result = subprocess.run(["git", "status", "--porcelain"], 
                                   cwd=str(self.project_dir), capture_output=True, text=True)
            conflicts = []
            for line in result.stdout.split('\n'):
                if line.startswith('UU') or line.startswith('AA'):
                    conflicts.append(line[3:])
            return conflicts
        except:
            return []
    
    def resolve_conflicts(self, strategy: str = "ours") -> bool:
        """解决冲突"""
        try:
            if strategy == "ours":
                subprocess.run(["git", "checkout", "--ours", "."], 
                              cwd=str(self.project_dir), capture_output=True)
            elif strategy == "theirs":
                subprocess.run(["git", "checkout", "--theirs", "."], 
                              cwd=str(self.project_dir), capture_output=True)
            
            subprocess.run(["git", "add", "."], cwd=str(self.project_dir),
                          capture_output=True)
            return True
        except:
            return False
