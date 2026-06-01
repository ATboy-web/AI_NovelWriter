# 贡献指南

感谢你对AI小说创作工坊的贡献兴趣！

## 如何贡献

### 报告Bug
1. 使用 [Bug报告模板](https://github.com/ATboy-web/AI_NovelWriter/issues/new?template=bug_report.md)
2. 提供详细的复现步骤
3. 附上截图和环境信息

### 提出功能建议
1. 使用 [功能建议模板](https://github.com/ATboy-web/AI_NovelWriter/issues/new?template=feature_request.md)
2. 描述使用场景和期望行为

### 提交代码
1. Fork本仓库
2. 创建功能分支: `git checkout -b feature/xxx`
3. 提交更改: `git commit -m 'Add xxx feature'`
4. 推送分支: `git push origin feature/xxx`
5. 创建Pull Request

## 开发环境

### 桌面版
```bash
# 安装依赖
pip install httpx fpdf2

# 运行
python novel_app.py
```

### Android版
```bash
cd mobile-app
npm install
npx expo start
```

## 代码规范
- Python: 遵循PEP8
- TypeScript: 使用ESLint
- 提交信息: 使用中文，简洁明了

## 贡献方向
- 🐛 Bug修复
- 📚 扩充创作工具内容（元素/桥段/描写/热点梗）
- 🌐 多语言支持
- 📱 移动版功能完善
- 📖 文档完善
- 🎨 UI/UX优化

## 联系方式
- GitHub Issues: https://github.com/ATboy-web/AI_NovelWriter/issues
