# backend/ —— ⛔ 已冻结（仅维护稳定）

> 本目录**不再接受新功能**。完整边界约定见
> [`docs/ARCHITECTURE_BOUNDARY.md`](../docs/ARCHITECTURE_BOUNDARY.md)。

## 冻结的含义（逐条）

| 允许改动 | 不允许改动 |
|---|---|
| 影响可用性的**缺陷修复** | 与桌面端做功能对齐 |
| **安全补丁**（依赖 CVE、认证、限流、注入） | 新增业务能力 / 新接口 |
| 依赖升级（仅为消除安全告警） | 重构（除非修复缺陷必须） |
| 补测试（只为守住已有行为） | 改数据模型/迁移脚本 |

判断标准一句话：**这次改动是让"已有的东西继续正常工作"，还是让"它也能做桌面端的新功能"？** 后者一律在桌面端实现。

## 为什么冻结

项目同时维护桌面端（`app/` + `novel_app.py`）与后端微服务（本目录）两套实现，
同一业务逻辑在两处演进会持续漂移 —— 表现为"桌面端修了、服务端没修"或反之。
桌面端是面向终端用户的完整产品（Source of Truth），因此保留它、冻结这一端。

## 这条约束是**可验证的**，不是口号

`tests/test_backend_freeze.py` 会检查：

1. **`app/` 不得 import `backend.`** —— 一旦桌面端依赖后端，两者就无法独立演进；
2. 本文件与 `docs/ARCHITECTURE_BOUNDARY.md` 必须同时存在，且都声明了冻结；
3. `README.md` 的目录树里 `backend/` 必须带冻结标注。

第 1 条是核心：它把"边界"从文档约定变成了会在 CI 里变红的硬约束。

## 目录现状（供参考，冻结时的快照）

| 子目录 | 作用 |
|---|---|
| `ai-service/` | AI 模型服务（:8001） |
| `novel-service/` | 小说生成服务（:8002） |
| `shared/` | 两服务共享的中间件（认证、限流、日志） |
| `tests/` | 后端自有测试（`pytest backend/tests/`） |

## 相关文档

- `docs/ARCHITECTURE_BOUNDARY.md` —— 边界约定的**权威来源**
- `docs/AUTH_PAYMENT_SERVICES_EVALUATION.md` —— 认证/支付服务评估（含与此约束的冲突记录）
- `docs/AGENT_OPTIMIZATION_PLAN.md` —— 项目章程里的「冻结」条目
