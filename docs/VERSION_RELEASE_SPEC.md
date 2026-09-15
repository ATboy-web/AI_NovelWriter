# AI_NovelWriter 版本发布规范

**文档编号**: PM-RELEASE-001  
**版本**: v1.0  
**日期**: 2026-06-30  
**状态**: 已批准

---

## 1. 版本命名规范

### 1.1 语义化版本 (Semantic Versioning)

格式：`MAJOR.MINOR.PATCH`

| 版本类型 | 说明 | 示例 |
|----------|------|------|
| **MAJOR** | 不兼容的API变更 | 1.0.0 → 2.0.0 |
| **MINOR** | 向后兼容的功能性新增 | 1.0.0 → 1.1.0 |
| **PATCH** | 向后兼容的问题修复 | 1.0.0 → 1.0.1 |

### 1.2 预发布版本

格式：`MAJOR.MINOR.PATCH-PRERELEASE`

| 预发布标签 | 说明 | 示例 |
|------------|------|------|
| **alpha** | 内部测试版本 | 1.0.0-alpha.1 |
| **beta** | 公开测试版本 | 1.0.0-beta.1 |
| **rc** | 候选发布版本 | 1.0.0-rc.1 |

### 1.3 版本号递增规则

```
# 开发阶段
0.1.0 → 0.2.0 → 0.3.0 → ...

# 正式发布
1.0.0

# 后续更新
1.0.1 (修复bug)
1.1.0 (新增功能)
2.0.0 (重大变更)
```

---

## 2. 发布类型

### 2.1 正式发布 (Release)

**触发条件**:
- 所有计划功能开发完成
- 所有测试通过
- 代码审查完成
- 文档更新完成

**版本号**: MAJOR.MINOR.PATCH

**发布频率**: 每月1次

### 2.2 热修复发布 (Hotfix)

**触发条件**:
- 生产环境严重bug
- 安全漏洞修复
- 数据损坏修复

**版本号**: MAJOR.MINOR.PATCH+1

**发布频率**: 按需（24小时内）

### 2.3 预发布 (Pre-release)

**触发条件**:
- 新功能开发完成
- 需要用户测试
- 准备正式发布

**版本号**: MAJOR.MINOR.PATCH-PRERELEASE.N

**发布频率**: 每2周1次

---

## 3. 发布流程

### 3.1 发布准备阶段

#### 步骤1：创建发布分支
```bash
# 从develop分支创建release分支
git checkout develop
git pull origin develop
git checkout -b release/v1.2.0
```

#### 步骤2：更新版本号
```bash
# 更新版本文件
echo "1.2.0" > VERSION

# 更新package.json
npm version 1.2.0 --no-git-tag-version

# 更新setup.py
sed -i "s/version='.*'/version='1.2.0'/" setup.py
```

#### 步骤3：更新变更日志
```bash
# 生成变更日志
git log --oneline --since="2026-05-01" --until="2026-06-01" > CHANGELOG_draft.md

# 编辑变更日志
# ... 编辑CHANGELOG.md ...
```

#### 步骤4：运行完整测试
```bash
# 运行所有测试
python -m pytest tests/ --cov=app --cov-report=html

# 检查覆盖率
# 覆盖率必须 ≥ 90%

# 运行代码质量检查
ruff check app/
mypy app/
```

#### 步骤5：构建发布包
```bash
# 构建EXE
cd installer
python -m PyInstaller novel_app.spec --clean --noconfirm

# 构建APK
cd mobile-app
./gradlew assembleRelease
```

### 3.2 发布评审阶段

#### 步骤6：创建Pull Request
```bash
# 创建PR到main分支
gh pr create --base main --head release/v1.2.0 \
  --title "Release v1.2.0" \
  --body "Release v1.2.0 - 见CHANGELOG.md"
```

#### 步骤7：代码审查
- 至少2人审查
- 所有CI检查通过
- 无高危安全问题

#### 步骤8：测试验证
- 功能测试通过
- 性能测试通过
- 安全测试通过
- 兼容性测试通过

### 3.3 发布执行阶段

#### 步骤9：合并到main分支
```bash
# 合并PR
gh pr merge --merge

# 合并回develop分支
git checkout develop
git merge main
```

#### 步骤10：创建Git标签
```bash
# 创建标签
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0
```

#### 步骤11：创建GitHub Release
```bash
# 创建Release
gh release create v1.2.0 \
  --title "Release v1.2.0" \
  --notes-file CHANGELOG.md \
  --draft=false \
  --prerelease=false \
  AI_NovelWriter.exe \
  AI_NovelWriter.apk
```

#### 步骤12：部署到生产环境
```bash
# 部署到生产服务器
./deploy.sh
```

### 3.4 发布后阶段

#### 步骤13：验证部署
```bash
# 检查服务状态
docker-compose -f docker-compose.prod.yml ps

# 检查健康状态
curl -f http://localhost/health

# 检查日志
docker-compose -f docker-compose.prod.yml logs -f
```

#### 步骤14：通知团队
- 发送发布通知
- 更新文档
- 更新知识库

#### 步骤15：监控和观察
- 监控系统状态
- 观察错误日志
- 收集用户反馈

---

## 4. 发布检查清单

### 4.1 代码质量检查
- [ ] 所有测试通过
- [ ] 测试覆盖率 ≥ 90%
- [ ] 代码审查完成
- [ ] 静态代码分析无高危问题
- [ ] 安全扫描无漏洞

### 4.2 功能检查
- [ ] 所有计划功能实现
- [ ] 所有用户故事验收
- [ ] 所有缺陷修复
- [ ] 回归测试通过

### 4.3 文档检查
- [ ] 变更日志更新
- [ ] 用户文档更新
- [ ] API文档更新
- [ ] 部署文档更新

### 4.4 构建检查
- [ ] EXE构建成功
- [ ] APK构建成功
- [ ] Docker镜像构建成功
- [ ] 构建产物验证

### 4.5 部署检查
- [ ] 测试环境部署成功
- [ ] 测试环境验证通过
- [ ] 生产环境部署成功
- [ ] 生产环境验证通过

### 4.6 发布检查
- [ ] Git标签创建
- [ ] GitHub Release创建
- [ ] 发布通知发送
- [ ] 文档更新完成

---

## 5. 变更日志规范

### 5.1 变更日志格式

```markdown
# 变更日志

## [1.2.0] - 2026-06-30

### 新增 (Added)
- 新增用户认证系统
- 新增支付订阅功能
- 新增移动端应用

### 变更 (Changed)
- 优化AI生成算法
- 改进用户界面
- 提升系统性能

### 修复 (Fixed)
- 修复登录bug
- 修复数据同步问题
- 修复内存泄漏

### 移除 (Removed)
- 移除旧版本API
- 移除废弃功能

### 安全 (Security)
- 修复XSS漏洞
- 加强数据加密
```

### 5.2 变更类型说明

| 类型 | 说明 | 示例 |
|------|------|------|
| **新增** | 新功能 | 新增用户认证系统 |
| **变更** | 功能改进 | 优化AI生成算法 |
| **修复** | Bug修复 | 修复登录bug |
| **移除** | 功能移除 | 移除旧版本API |
| **安全** | 安全修复 | 修复XSS漏洞 |

### 5.3 变更日志示例

```markdown
# 变更日志

## [2.14.4] - 2026-06-30

### 新增
- 新增生产环境部署配置
- 新增CI/CD自动化流程
- 新增监控告警系统
- 新增ima知识库集成

### 变更
- 优化测试覆盖率到87%
- 改进代码质量
- 提升系统稳定性

### 修复
- 修复_diag未定义导致崩溃
- 修复线程安全问题
- 修复路径遍历漏洞
- 修复解密回退泄露明文
- 修复双配置系统问题

### 安全
- 加强数据加密
- 修复安全漏洞
```

---

## 6. 回滚策略

### 6.1 回滚触发条件
- 生产环境严重故障
- 数据损坏
- 安全漏洞
- 性能严重下降

### 6.2 回滚流程

#### 步骤1：评估回滚需求
```bash
# 检查故障范围
# 评估影响程度
# 决定是否回滚
```

#### 步骤2：执行回滚
```bash
# 回滚到上一个稳定版本
git checkout main
git revert HEAD
git push origin main

# 或者回滚到特定版本
git checkout v1.2.3
git checkout -b hotfix/rollback
git push origin hotfix/rollback
```

#### 步骤3：重新部署
```bash
# 重新部署上一个稳定版本
./deploy.sh
```

#### 步骤4：验证回滚
```bash
# 验证服务正常
curl -f http://localhost/health

# 验证功能正常
# ... 功能测试 ...
```

#### 步骤5：通知团队
- 发送回滚通知
- 分析回滚原因
- 制定修复计划

### 6.3 回滚时间要求
- **热修复回滚**: 30分钟内
- **版本回滚**: 2小时内
- **重大回滚**: 4小时内

---

## 7. 发布自动化

### 7.1 GitHub Actions配置

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Build EXE
        run: |
          cd installer
          python -m PyInstaller novel_app.spec --clean --noconfirm
      
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            installer/dist/AI_NovelWriter.exe
          draft: false
          prerelease: false
```

### 7.2 自动化脚本

```bash
#!/bin/bash
# release.sh - 自动化发布脚本

set -e

VERSION=$1
if [ -z "$VERSION" ]; then
    echo "Usage: ./release.sh <version>"
    exit 1
fi

echo "Release version: $VERSION"

# 更新版本号
echo "$VERSION" > VERSION

# 运行测试
python -m pytest tests/ --cov=app

# 构建EXE
cd installer
python -m PyInstaller novel_app.spec --clean --noconfirm
cd ..

# 创建Git标签
git add .
git commit -m "release: $VERSION"
git tag -a "$VERSION" -m "Release $VERSION"
git push origin "$VERSION"

# 创建GitHub Release
gh release create "$VERSION" \
  --title "Release $VERSION" \
  --notes-file CHANGELOG.md \
  installer/dist/AI_NovelWriter.exe

echo "Release $VERSION completed!"
```

---

## 8. 发布后监控

### 8.1 监控指标

| 指标 | 阈值 | 告警方式 |
|------|------|----------|
| 错误率 | < 1% | 邮件、Slack |
| 响应时间 | < 3秒 | 邮件、Slack |
| 可用性 | > 99.9% | 邮件、短信 |
| CPU使用率 | < 80% | 邮件 |
| 内存使用率 | < 80% | 邮件 |

### 8.2 监控工具

- **Prometheus**: 指标收集
- **Grafana**: 可视化监控
- **AlertManager**: 告警管理
- **Sentry**: 错误追踪

### 8.3 监控流程

1. 发布后立即开始监控
2. 持续监控24小时
3. 记录监控数据
4. 分析异常情况
5. 及时处理问题

---

## 9. 文档更新

### 9.1 发布文档清单

- [ ] 变更日志 (CHANGELOG.md)
- [ ] 版本号更新 (VERSION)
- [ ] README.md 更新
- [ ] API文档更新
- [ ] 用户手册更新
- [ ] 部署文档更新
- [ ] 发布说明 (Release Notes)

### 9.2 文档更新流程

1. 更新变更日志
2. 更新版本号
3. 更新README
4. 更新API文档
5. 更新用户手册
6. 更新部署文档
7. 编写发布说明
8. 审查文档
9. 发布文档

---

## 10. 发布说明模板

```markdown
# Release v1.2.0

## 发布日期
2026-06-30

## 主要更新

### 新功能
- 新增用户认证系统
- 新增支付订阅功能
- 新增移动端应用

### 改进
- 优化AI生成算法
- 改进用户界面
- 提升系统性能

### 修复
- 修复登录bug
- 修复数据同步问题
- 修复内存泄漏

## 下载

- [AI_NovelWriter.exe](https://github.com/ATboy-web/AI_NovelWriter/releases/download/v1.2.0/AI_NovelWriter.exe)
- [AI_NovelWriter.apk](https://github.com/ATboy-web/AI_NovelWriter/releases/download/v1.2.0/AI_NovelWriter.apk)

## 系统要求

- Windows 10/11 (64位)
- 4GB内存
- 500MB磁盘空间

## 安装说明

1. 下载AI_NovelWriter.exe
2. 运行安装程序
3. 按照提示完成安装

## 已知问题

- 暂无已知问题

## 反馈

如有问题或建议，请提交[Issue](https://github.com/ATboy-web/AI_NovelWriter/issues)

---

感谢使用AI_NovelWriter！
```

---

*文档生成时间: 2026-06-30*
