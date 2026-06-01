# 多人协作系统规划

## 概述

支持多人协作创作小说，包括：
- 多人同时编辑
- 角色分工
- 版本控制
- 云端同步

## 架构设计

### 方案1：Git-based协作（推荐）

**优点：**
- 无需服务器
- 版本控制完善
- 冲突处理成熟

**工作流程：**
```
作者A → Git Push → GitHub
作者B → Git Pull → 本地编辑
作者B → Git Push → GitHub
作者A → Git Pull → 获取更新
```

**实现：**
```python
def sync_to_github():
    """同步到GitHub"""
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "更新小说内容"])
    subprocess.run(["git", "push", "origin", "main"])

def pull_from_github():
    """从GitHub拉取"""
    subprocess.run(["git", "pull", "origin", "main"])
```

### 方案2：云端服务器

**优点：**
- 实时同步
- 冲突自动处理
- 权限管理

**架构：**
```
作者A ─┐
作者B ─┼── 云端服务器 ── 数据库
作者C ─┘
```

**API设计：**
```
POST /api/novel/sync     # 同步内容
GET  /api/novel/latest   # 获取最新版本
POST /api/novel/lock     # 锁定章节
POST /api/novel/unlock   # 解锁章节
```

### 方案3：P2P直连

**优点：**
- 无需服务器
- 延迟低

**实现：**
- 使用WebRTC
- 通过信令服务器建立连接
- 直接传输文件

## 功能设计

### 1. 角色分工

```python
ROLES = {
    "主编": {
        "权限": ["编辑所有章节", "管理角色", "发布"],
        "描述": "负责整体把控"
    },
    "作者": {
        "权限": ["编辑分配章节", "查看大纲"],
        "描述": "负责章节创作"
    },
    "编辑": {
        "权限": ["审校", "建议修改"],
        "描述": "负责质量把控"
    },
    "读者": {
        "权限": ["查看", "评论"],
        "描述": "试读和反馈"
    }
}
```

### 2. 章节锁定

```python
class ChapterLock:
    def __init__(self):
        self.locks = {}
    
    def lock(self, chapter: int, user: str) -> bool:
        if chapter in self.locks:
            return False  # 已被锁定
        self.locks[chapter] = {
            "user": user,
            "time": datetime.now()
        }
        return True
    
    def unlock(self, chapter: int, user: str) -> bool:
        if chapter in self.locks and self.locks[chapter]["user"] == user:
            del self.locks[chapter]
            return True
        return False
```

### 3. 版本历史

```python
class VersionHistory:
    def __init__(self):
        self.versions = []
    
    def save_version(self, content: str, author: str, message: str):
        self.versions.append({
            "content": content,
            "author": author,
            "message": message,
            "timestamp": datetime.now(),
            "hash": hashlib.md5(content.encode()).hexdigest()
        })
    
    def get_diff(self, version1: int, version2: int) -> str:
        # 返回两个版本的差异
        pass
```

## 实现阶段

### 阶段1：基础同步（1周）
- [ ] Git集成
- [ ] 自动提交和推送
- [ ] 冲突检测

### 阶段2：协作功能（2周）
- [ ] 角色分工
- [ ] 章节锁定
- [ ] 版本历史

### 阶段3：实时协作（3周）
- [ ] 云端服务器
- [ ] 实时同步
- [ ] 冲突自动解决

## 技术选型

| 方案 | 复杂度 | 实时性 | 推荐度 |
|------|--------|--------|--------|
| Git-based | 低 | 低 | ⭐⭐⭐ |
| 云端服务器 | 高 | 高 | ⭐⭐ |
| P2P直连 | 中 | 中 | ⭐ |

**推荐：先实现Git-based，后期根据需求升级**
