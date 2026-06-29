# 贡献指南

感谢你对 AI_NovelWriter 项目的关注！我们欢迎各种形式的贡献。

## 如何贡献

### 报告问题

1. 使用 [GitHub Issues](https://github.com/ATboy-web/AI_NovelWriter/issues) 报告 bug
2. 使用 Issue 模板，提供以下信息：
   - 问题描述
   - 复现步骤
   - 期望行为 vs 实际行为
   - 环境信息（OS、Python版本、Android版本等）
   - 相关日志或截图

### 提交代码

1. **Fork 项目**
   ```bash
   # 点击 GitHub 页面右上角的 Fork 按钮
   ```

2. **克隆你的 Fork**
   ```bash
   git clone https://github.com/你的用户名/AI_NovelWriter.git
   cd AI_NovelWriter
   ```

3. **创建特性分支**
   ```bash
   git checkout -b feature/你的特性名称
   # 或
   git checkout -b fix/你的修复名称
   ```

4. **安装开发依赖**
   ```bash
   pip install -e ".[dev]"
   ```

5. **进行修改并测试**
   ```bash
   # 运行测试
   python -m pytest tests/ -v
   
   # 运行 lint 检查
   ruff check app/ tests/
   ```

6. **提交更改**
   ```bash
   git add .
   git commit -m "feat: 添加新功能"  # 使用语义化提交信息
   ```

7. **推送并创建 Pull Request**
   ```bash
   git push origin feature/你的特性名称
   # 然后在 GitHub 上创建 Pull Request
   ```

## 开发环境设置

### Python 环境

```bash
# 推荐 Python 3.11+
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"
```

### Android 环境

1. 安装 Android Studio
2. 安装 JDK 17
3. 打开 `mobile-app/novel-app` 项目
4. 同步 Gradle

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_memory_manager.py -v

# 运行带覆盖率的测试
python -m pytest tests/ --cov=app --cov-report=html
```

### 代码质量检查

```bash
# Ruff lint
ruff check app/ tests/

# Ruff format
ruff format app/ tests/

# MyPy 类型检查
mypy app/ --ignore-missing-imports
```

## 代码规范

### Python

- 遵循 PEP 8 规范
- 使用类型注解
- 函数和类必须有文档字符串
- 行长度限制：120 字符

```python
def generate_chapter(
    novel_id: str,
    chapter_num: int,
    style: str = "default"
) -> dict:
    """
    生成小说章节
    
    Args:
        novel_id: 小说ID
        chapter_num: 章节号
        style: 写作风格
        
    Returns:
        dict: 章节数据
    """
    pass
```

### Kotlin (Android)

- 遵循 Kotlin 官方风格指南
- 使用 Jetpack Compose 最佳实践
- ViewModel 使用 MVVM 模式

### 提交信息格式

使用 [语义化提交](https://www.conventionalcommits.org/):

```
<类型>(<范围>): <描述>

[可选的正文]

[可选的脚注]
```

类型：
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具相关

示例：
```
feat(memory): 添加角色活跃度追踪

- 记录角色出场章节
- 按活跃度排序加载角色
- 支持自定义活跃窗口

Closes #123
```

## 项目结构

```
ai-novel-writer/
├── app/                    # 桌面版 Python 代码
│   ├── ai_client.py        # AI 客户端
│   ├── memory_manager.py   # 记忆管理器
│   └── ...
├── backend/                # 后端服务
│   ├── ai-service/         # AI 模型服务
│   └── novel-service/      # 小说生成服务
├── mobile-app/             # 手机版
│   ├── novel-app/          # Kotlin 原生应用
│   └── webview-app/        # WebView 应用
├── tests/                  # Python 测试
├── docs/                   # 文档
└── scripts/                # 工具脚本
```

## 发布流程

1. 更新版本号（`pyproject.toml` 和 `build.gradle.kts`）
2. 更新 CHANGELOG.md
3. 创建 Git tag
4. GitHub Actions 自动构建和发布

## 行为准则

- 尊重所有参与者
- 接受建设性批评
- 专注于对社区最有利的事情
- 对他人表示同理心

## 获取帮助

- GitHub Issues: 问题报告和功能请求
- GitHub Discussions: 一般讨论和问答

## 许可证

贡献即表示你同意你的贡献将在 [MIT Modified License](LICENSE) 下发布。
