# 插件系统设计（v3.2）

> ⚠️ **本文档已按实际实现重写。**
> 旧版本描述的 `"type": "tool|library|exporter|ai"` 与 `settings` 块
> **在代码里不存在** —— 那是典型的「同一事实写两处必然漂移」：
> 文档写了 4 个类型名，代码只有 `writing_skill` 等 5 个且名字对不上。
> 本文的类型名一律以 `app/plugin_system.py::PLUGIN_TYPES` 为准。

## 概述

AI 小说创作工坊支持通过插件扩展功能。插件可以：

- **写作技能包**（`writing_skill`）：向写作提示词注入风格与禁用规则 —— **真实生效**
- **素材库扩充**（`library`）：为 `novel_toolkit` 的元素 / 桥段 / 描写库补条目
- **导出格式**（`exporter`）：增加导出目标
- **AI 服务**（`ai_provider`）：登记额外 AI 服务（占位，接入需配 `app/providers/`）
- **创作工具**（`tool`）：通用工具扩展

## 插件目录结构

```
~/.ai_novel_writer/
├── plugins/                  # 插件根目录（唯一来源：default_plugins_dir()）
│   └── my-plugin/
│       ├── plugin.json       # 插件配置
│       ├── main.py           # 插件入口
│       └── data/             # 插件数据（可选）
└── plugins.json              # 启用状态（{"enabled": ["my-plugin"]}）
```

路径**不要自己拼** —— 用 `plugin_system.default_plugins_dir()` /
`default_state_file()`。有守卫测试拦"在别处重复拼这个路径"。

## plugin.json 格式

```json
{
  "name": "我的插件",
  "version": "1.0.0",
  "author": "作者名",
  "description": "插件描述",
  "type": "writing_skill",
  "entry": "main.py"
}
```

| 字段 | 必需 | 说明 |
|---|---|---|
| `name` | ✅ | 插件名。只允许字母/数字/中文/下划线/连字符/点，≤64 字符 |
| `version` | — | 版本号 |
| `author` | — | 作者 |
| `description` | — | 说明 |
| `type` | — | 五种之一（见 `PLUGIN_TYPES`），缺省按"探测能力"处理 |
| `entry` | — | 入口文件名，默认 `main.py` |

**没有 `settings` 块** —— 旧文档提到的它是未实现的字段，已删除。

## 插件类型与接口

判定方式是"插件导出了哪些函数"，`type` 只是**声明**，实际以探测结果为准
（`Plugin.capabilities()`）。

### 1. 写作技能包 (writing_skill)

```python
def get_writing_skills():
    return [
        {
            "name": "去油文风",
            "prompt": "禁止使用'总而言之''不禁感叹'等陈词。",
            "rules": ["总而言之", "不禁感叹"],   # 会进 anti_slop 的额外禁用表
        }
    ]
```

消费点（**这就是它生效的地方**）：

| 消费方 | 位置 | 作用 |
|---|---|---|
| `WritingSkillManager.plugin_skill_context()` | `app/writing_skills.py` | 把 `prompt` 拼进写作上下文 |
| `WritingSkillManager.plugin_ban_rules()` | `app/writing_skills.py` | 把 `rules` 交给 `AntiSlopProcessor.check_text()` |
| `NovelAgent._build_context` | `app/novel_agent.py` | 单独占一段预算（800 字）注入提示词 |

### 2. 库插件 (library)

```python
def get_library():
    return {
        "type": "elements",       # elements / bridges / descriptions
        "category": "我的分类",
        "items": [
            {"name": "元素1", "template": "..."},
        ],
    }
```

### 3. 导出插件 (exporter)

```python
def get_exporters():
    return [
        {"name": "自定义格式", "ext": ".custom", "handler": export_handler}
    ]
```

### 4. AI 插件 (ai_provider)

```python
def get_ai_providers():
    return [
        {"name": "我的AI", "base_url": "https://api.example.com/v1", "models": ["m1"]}
    ]
```

### 5. 工具插件 (tool)

```python
def get_tools():
    return [
        {"name": "我的工具", "desc": "工具描述", "handler": my_tool_handler}
    ]
```

## 安装与启用（通过界面）

**打开「插件中心」面板（运维分组）即可，不需要手改文件、不需要重启。**

| 操作 | 面板位置 |
|---|---|
| 安装 | 工具条「安装插件」→ 选 `dir` / `zip` / `url` |
| 查看 | 左侧插件表（名称 / 版本 / 类型 / 状态 / 风险） |
| 安全体检 | 右侧详情区：会 import 什么、触及哪些高危符号 |
| 启用 / 停用 | 右侧「启用」/「停用」（**状态持久化**） |
| 卸载 | 右侧「卸载」（带确认） |
| 生效验证 | 底部："当前有 N 个技能包注入写作提示词" |

## 🔴 安全默认

1. **插件默认不启用** —— 装完必须显式点「启用」。
2. **安装前做静态体检**（`audit_plugin`）：AST 扫描入口文件，
   列出 import 项与 `os.system` / `subprocess` / `eval` / `socket` /
   `shutil.rmtree` 等 14 个高危符号，并按 `safe` / `notice` / `high` 分级。
3. **Zip Slip 防护**：解压时逐成员校验 `is_relative_to`，
   拒绝 `../` 穿越与"前缀兄弟目录"（`/tmp/plugin_evil` 这种字符串 `startswith` 会被绕过）。
4. **安装路径限制**：卸载只允许删 `plugins_dir` 之内的目录。

### 本模块**做不到**什么（不做虚假承诺）

插件是**以本应用同等权限运行的 Python 代码**。它能读写你的文件、发起网络请求。
本模块能做的是：**限制安装路径、拒绝危险名称、启用前把风险摆出来**。
它**不能**沙箱化插件代码。定位是"降低误装风险 + 让风险可见"，
而不是"让不可信代码变安全"。

## 开发插件：最小示例

```python
# my-plugin/plugin.json
{
  "name": "Hello插件",
  "version": "1.0.0",
  "type": "writing_skill",
  "entry": "main.py"
}
```

```python
# my-plugin/main.py
def get_writing_skills():
    return [{
        "name": "Hello 风格",
        "prompt": "每章至少一个具体动作细节。",
        "rules": ["综上所述"],
    }]
```

装好后在「插件中心」点「启用」，底部会显示"已生效：1 个写作技能包注入写作提示词"——
**这就是"装上了"与"生效了"的区别**。

## 计划中的插件

- [ ] 番茄小说 API 对接
- [ ] 起点中文网 API 对接
- [ ] 有声书生成（TTS）
- [ ] AI 绘图集成（ComfyUI）
- [ ] 多语言翻译
