# 插件系统设计

## 概述

AI小说创作工坊支持通过插件扩展功能。插件可以：
- 添加新的创作工具
- 扩充元素库/桥段库/描写库
- 集成外部AI服务
- 添加新的导出格式

## 插件目录结构

```
~/.ai_novel_writer/plugins/
├── my-plugin/
│   ├── plugin.json      # 插件配置
│   ├── main.py          # 插件入口
│   └── data/            # 插件数据
```

## plugin.json 格式

```json
{
  "name": "我的插件",
  "version": "1.0.0",
  "author": "作者名",
  "description": "插件描述",
  "type": "tool|library|exporter|ai",
  "entry": "main.py",
  "settings": {
    "api_key": {
      "type": "string",
      "label": "API密钥",
      "default": ""
    }
  }
}
```

## 插件类型

### 1. 工具插件 (tool)
添加新的创作工具到工具栏。

```python
# main.py
def get_tools():
    return [
        {
            "name": "我的工具",
            "desc": "工具描述",
            "icon": "star",
            "handler": my_tool_handler
        }
    ]

def my_tool_handler(ai_client, context):
    # 处理逻辑
    return "结果"
```

### 2. 库插件 (library)
扩充元素库/桥段库/描写库。

```python
# main.py
def get_library():
    return {
        "type": "elements",  # elements/bridges/descriptions
        "category": "我的分类",
        "items": [
            {"name": "元素1", "template": "..."},
            {"name": "元素2", "template": "..."}
        ]
    }
```

### 3. 导出插件 (exporter)
添加新的导出格式。

```python
# main.py
def get_exporters():
    return [
        {
            "name": "自定义格式",
            "ext": ".custom",
            "handler": export_handler
        }
    ]

def export_handler(content, title, output_path):
    # 导出逻辑
    pass
```

### 4. AI插件 (ai)
集成外部AI服务。

```python
# main.py
def get_ai_providers():
    return [
        {
            "name": "我的AI",
            "base_url": "https://api.example.com/v1",
            "models": ["model1", "model2"]
        }
    ]
```

## 安装插件

1. 将插件文件夹放入 `~/.ai_novel_writer/plugins/`
2. 重启应用
3. 在设置中启用插件

## 开发插件

### 最小示例

```python
# my-plugin/plugin.json
{
  "name": "Hello插件",
  "version": "1.0.0",
  "type": "tool",
  "entry": "main.py"
}

# my-plugin/main.py
def get_tools():
    return [{
        "name": "Hello",
        "desc": "测试插件",
        "handler": hello
    }]

def hello(ai_client, context):
    return "Hello from plugin!"
```

### 使用AI客户端

```python
def my_tool(ai_client, context):
    response = ai_client.chat(
        [{"role": "user", "content": "你的提示"}],
        system="系统提示",
        max_tokens=1000
    )
    return response
```

## 计划中的插件

- [ ] 番茄小说API对接
- [ ] 起点中文网API对接
- [ ] 有声书生成（TTS）
- [ ] AI绘图集成（ComfyUI）
- [ ] 多语言翻译
- [ ] 语法检查
- [ ] 查重检测
