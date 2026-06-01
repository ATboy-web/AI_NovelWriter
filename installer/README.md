# AI自动写小说系统 - 安装程序构建指南

## 概述

本目录包含构建AI自动写小说系统安装程序所需的所有文件。

## 文件说明

| 文件 | 说明 |
|------|------|
| `ai_service.spec` | AI服务的PyInstaller打包配置 |
| `novel_service.spec` | 小说服务的PyInstaller打包配置 |
| `launcher.spec` | 启动器的PyInstaller打包配置 |
| `launcher.py` | 启动器源代码 |
| `installer.nsi` | NSIS安装程序脚本 |
| `license.txt` 许可协议 |
| `build.bat` | Windows打包脚本 |
| `build.sh` | Linux/Mac打包脚本 |
| `../icon.ico` | 应用图标（已放在项目根目录） |

## 构建步骤

### 1. 环境准备

#### Windows
```bash
# 安装Python 3.9+
# 安装pip
# 安装NSIS（用于创建安装程序）
# 下载地址: https://nsis.sourceforge.io/Download
```

#### Linux/Mac
```bash
# 安装Python 3.9+
# 安装pip3
```

### 2. 安装依赖

```bash
cd ai-novel-writer
pip install -r backend/ai-service/requirements.txt
pip install -r backend/novel-service/requirements.txt
pip install pyinstaller
```

### 3. 准备图标

应用图标文件已放在项目根目录 `icon.ico` 位置（256x256像素，32位真彩色）。

如需更换图标，请替换项目根目录的 `icon.ico` 文件。

### 4. 执行打包

#### Windows
```bash
cd installer
build.bat all
```

#### Linux/Mac
```bash
cd installer
chmod +x build.sh
./build.sh all
```

### 5. 输出文件

打包完成后，将生成以下文件：

```
dist/
├── AI_NovelService.exe    # AI服务
├── NovelGenerator.exe     # 小说服务
└── AI_NovelWriter.exe     # 启动器

installer/
└── AI_NovelWriter_Setup.exe  # 安装程序
```

## 打包选项

### 仅打包服务
```bash
# Windows
build.bat services

# Linux/Mac
./build.sh services
```

### 仅打包启动器
```bash
# Windows
build.bat launcher

# Linux/Mac
./build.sh launcher
```

### 仅创建安装程序
```bash
# Windows（需要先打包服务和启动器）
build.bat installer
```

### 清理构建文件
```bash
# Windows
build.bat clean

# Linux/Mac
./build.sh clean
```

## 自定义配置

### 修改端口

编辑 `launcher.py` 中的默认端口配置：

```python
self.config = {
    "ai_service_port": 8001,      # AI服务端口
    "novel_service_port": 8002,   # 小说服务端口
    "frontend_port": 3000,        # 前端服务端口
    "auto_open_browser": True,    # 自动打开浏览器
}
```

### 修改安装路径

编辑 `installer.nsi` 中的安装路径：

```nsis
InstallDir "$PROGRAMFILES\AI_NovelWriter"
```

### 修改应用名称

编辑 `installer.nsi` 中的应用名称：

```nsis
Name "AI自动写小说系统"
```

### 修改图标

图标文件已放在项目根目录 `icon.ico`，如需更换请替换该文件。

## 常见问题

### Q1: PyInstaller打包失败

**问题**: 找不到模块或依赖缺失

**解决**: 
1. 确保所有依赖已安装
2. 在spec文件中添加缺失的hiddenimports
3. 使用 `--hidden-import` 参数

### Q2: NSIS安装程序创建失败

**问题**: 未找到NSIS或脚本错误

**解决**:
1. 安装NSIS: https://nsis.sourceforge.io/Download
2. 确保NSIS已添加到PATH环境变量
3. 检查installer.nsi脚本语法

### Q3: 程序启动后立即退出

**问题**: 缺少依赖或配置错误

**解决**:
1. 在命令行运行exe查看错误信息
2. 检查是否缺少DLL文件
3. 确保所有配置文件正确

### Q4: 端口被占用

**问题**: 服务启动失败，端口已被占用

**解决**:
1. 修改config.json中的端口配置
2. 或关闭占用端口的程序

## 高级配置

### 添加自定义数据文件

在spec文件的datas部分添加：

```python
datas = [
    ('path/to/data', 'data'),
    ('path/to/config', 'config'),
]
```

### 添加自定义图标

1. 准备256x256的ICO文件
2. 替换项目根目录的icon.ico文件
3. spec文件和launcher.py中的图标路径已配置为 ../icon.ico

### 创建便携版

不使用安装程序，直接打包：

```bash
# 打包所有组件
build.bat all

# 复制dist目录下的所有exe文件
# 复制config.json和必要的配置文件
# 创建启动脚本
```

## 技术支持

如有问题，请通过以下方式联系：

- GitHub Issues: https://github.com/your-repo/ai-novel-writer/issues
- 邮箱: support@example.com

## 更新日志

### v1.0.0 (2026-05-30)
- 初始版本
- 支持Windows安装程序
- 支持Linux/Mac打包
- 包含图形界面启动器
