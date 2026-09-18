# 文档索引

本目录集中存放项目文档。根目录仅保留 `README.md`（中文主文档）、`README_EN.md`（英文）、
`CHANGELOG.md`、`CONTRIBUTING.md`、`QUICKSTART.md`、`USAGE.md`、`LICENSE`。

> 版本号权威源为 `pyproject.toml`；`app.__version__`、README 与 CHANGELOG 的一致性由
> `tests/test_version_consistency.py` 守护。

## 使用与上手
| 文档 | 说明 |
|------|------|
| [../QUICKSTART.md](../QUICKSTART.md) | 快速开始 |
| [../USAGE.md](../USAGE.md) | 使用说明 |
| [API.md](API.md) | 后端 API 文档 |
| [UI_DESIGN.md](UI_DESIGN.md) | UI 设计 |
| [ui_review/](ui_review/) | 界面改造前后对照截图（同窗口尺寸，含改造前后各 4 张） |
| [development-roadmap.md](development-roadmap.md) | 开发路线图 |

## 项目治理
| 文档 | 说明 |
|------|------|
| [PROJECT_CHARTER.md](PROJECT_CHARTER.md) | 项目章程 |
| [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md) | 项目文档总览 |
| [PROJECT_MANAGEMENT_UPGRADE.md](PROJECT_MANAGEMENT_UPGRADE.md) | 项目管理升级 |
| [RISK_REGISTER.md](RISK_REGISTER.md) | 风险登记册 |
| [TEAM_IMPROVEMENT_PLAN.md](TEAM_IMPROVEMENT_PLAN.md) | 团队提升方案 |
| [project-summary.md](project-summary.md) | 项目总结 |
| [VERSION_RELEASE_SPEC.md](VERSION_RELEASE_SPEC.md) | 版本发布规范 |
| [RELEASE_HISTORY_NOTES.md](RELEASE_HISTORY_NOTES.md) | 发布历史异常记录（乱码页修复、缺失标签、标签指向异常） |
| [AUTH_PAYMENT_SERVICES_EVALUATION.md](AUTH_PAYMENT_SERVICES_EVALUATION.md) | 认证 / 支付服务立项评估（结论：暂不立项） |
| [FEATURE_VALUE_ASSESSMENT.md](FEATURE_VALUE_ASSESSMENT.md) | 功能实用性与使用价值评估（保留 / 优化 / 删除清单） |
| [BACKLOG_REGISTER.md](BACKLOG_REGISTER.md) | **待办 / 遗留问题 / 已知缺陷总登记册**（每条带证据，接班先看这份） |
| [PACKAGING_AND_PANEL_PLAYBOOK.md](PACKAGING_AND_PANEL_PLAYBOOK.md) | 打包与新增面板的操作手册（含踩坑记录） |

## 质量与安全
| 文档 | 说明 |
|------|------|
| [CODE_REVIEW_REPORT.md](CODE_REVIEW_REPORT.md) | 代码审查报告 |
| [TEST_ANALYSIS_REPORT.md](TEST_ANALYSIS_REPORT.md) | 测试分析报告 |
| [API_TESTING_PLAN.md](API_TESTING_PLAN.md) | API 测试计划 |
| [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md) | 安全审计报告 |
| [OPTIMIZATION_REVIEW.md](OPTIMIZATION_REVIEW.md) | 优化审阅报告 |
| [RUNTIME_AUDIT_20260917.md](RUNTIME_AUDIT_20260917.md) | 运行时审计：真实生成日志逐项核对，9 项缺陷（D1–D9）与修复 |
| [CONSISTENCY_AUDIT_20260917.md](CONSISTENCY_AUDIT_20260917.md) | 配置项与功能接线一致性审计（谁写它 / 谁读它） |
| [OPTIMIZATION_ROUND2.md](OPTIMIZATION_ROUND2.md) | 第二轮优化：健壮性/结构/可维护性（含角色数据保护） |
| [CODE_REVIEW_ROUND3.md](CODE_REVIEW_ROUND3.md) | 第三轮代码复查：安全漏洞 / 逻辑缺陷 / 边界问题（含实测核验） |
| [CODE_REVIEW_P4.md](CODE_REVIEW_P4.md) | P4（面板框架与联动）代码与功能复核：8 项修复 + 7 项既有缺陷与建议 |
| [OPTIMIZATION_P4.md](OPTIMIZATION_P4.md) | P4 面板层优化：读取缓存 / 目录扫描 / 一次取数（含前后实测对照） |
| [DAY_SUMMARY_20260630.md](DAY_SUMMARY_20260630.md) | 阶段小结 |

## 设计
| 文档 | 说明 |
|------|------|
| [ARCHITECTURE_BOUNDARY.md](ARCHITECTURE_BOUNDARY.md) | 桌面端/后端架构边界约定（P2-2） |
| [UI_DESIGN.md](UI_DESIGN.md) | UI 设计 |
| [ROADMAP_V3_PANELS_AND_PROVIDERS.md](ROADMAP_V3_PANELS_AND_PROVIDERS.md) | v3 改造方案与实施进度：面板化框架与联动 · 多 API 适配与用量统计 · 模块整合去重（**P0–P4b 已随 v3.0.0 发布**，P5 样式收敛待做） |
| [MODULE_DEPENDENCY_MAP.md](MODULE_DEPENDENCY_MAP.md) | **模块依赖关系图**（由 `scripts/module_graph.py` 从源码生成，勿手工编辑） |
| [NEXT_STEPS.md](NEXT_STEPS.md) | 下一步行动计划：优先级的建议 / 目标 / 风险 / 执行顺序（含 S1–S7 执行情况与两轮面板 UI 改造记录） |

## 功能模块
| 文档 | 说明 |
|------|------|
| [GENRE_SYSTEM.md](GENRE_SYSTEM.md) | **题材系统**：可扩展注册表 + 用户自定义题材/标签 + 配置格式 + 不破坏已有作品的约束 |
| [MCP_SUPPORT.md](MCP_SUPPORT.md) | **MCP 支持**：客户端（stdio/http）与服务端、配置、安全边界、测试分层 |
| [PLUGIN_SYSTEM.md](PLUGIN_SYSTEM.md) | **插件系统**：五种插件类型、接口约定、安装与启用、静态体检与安全边界 |
| [NOVEL_AUDIT_1789640077.md](NOVEL_AUDIT_1789640077.md) | 《快速统治》生成审计：文件/功能一致性、6 类结构性错误、结尾「烂尾」成因与修复项 |

## 归档（对应功能模块已移除）
| 文档 | 说明 |
|------|------|
| [AI_DRAWING_PLAN.md](AI_DRAWING_PLAN.md) | 早期文生图规划（`ai_drawing.py` 已移除；**该能力后来由「插图工坊」面板 + `app/image_generator.py` 重建**，见 `BACKLOG_REGISTER.md` D10） |
| [COLLABORATION_PLAN.md](COLLABORATION_PLAN.md) | 协作网络规划（`collaboration.py` 已作为死代码移除） |
