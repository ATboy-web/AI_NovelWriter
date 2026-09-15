# AI绘图集成规划

## 概述

将AI绘图功能集成到小说创作工坊，实现：
- 文字描述自动生成插图
- 角色立绘生成
- 场景插图生成
- 封面设计

## 支持的后端

### 1. ComfyUI（推荐）
- 本地部署，完全免费
- 支持SDXL/SD3等最新模型
- 可自定义工作流

**连接方式：**
```
API地址: http://127.0.0.1:8188
```

### 2. Stable Diffusion WebUI
- 本地部署
- 社区生态丰富

**连接方式：**
```
API地址: http://127.0.0.1:7860
```

### 3. 云端API
- DALL-E 3（OpenAI）
- Midjourney API
- Stability AI

## 功能设计

### 1. 场景插图生成

**触发方式：**
- 手动输入描述
- 自动检测章节中的场景描写
- AI提取关键场景

**提示词模板：**
```
{场景描述}, masterpiece, best quality, 
anime style, detailed background, 
cinematic lighting, 8k resolution
```

### 2. 角色立绘生成

**触发方式：**
- 从角色档案自动生成
- 手动输入角色描述

**提示词模板：**
```
{角色名}, {外貌描述}, {服装描述}, 
character portrait, anime style, 
detailed face, masterpiece
```

### 3. 封面设计

**触发方式：**
- 根据小说标题和类型自动生成
- 手动输入封面描述

## 实现计划

### 阶段1：基础集成
- [ ] ComfyUI连接测试
- [ ] 基础文生图功能
- [ ] 图片保存到项目

### 阶段2：智能生成
- [ ] 场景自动检测
- [ ] 角色立绘生成
- [ ] 提示词优化

### 阶段3：高级功能
- [ ] 封面设计
- [ ] 图片编辑
- [ ] 批量生成
- [ ] 风格控制

## 代码示例

### ComfyUI连接

```python
import httpx

def generate_image(prompt: str, negative_prompt: str = "") -> bytes:
    """通过ComfyUI生成图片"""
    workflow = build_workflow(prompt, negative_prompt)
    
    # 提交工作流
    resp = httpx.post("http://127.0.0.1:8188/prompt", json={"prompt": workflow})
    prompt_id = resp.json()["prompt_id"]
    
    # 等待完成
    for _ in range(120):
        time.sleep(1)
        hist = httpx.get(f"http://127.0.0.1:8188/history/{prompt_id}").json()
        if prompt_id in hist:
            # 获取图片
            img_info = hist[prompt_id]["outputs"]["9"]["images"][0]
            img = httpx.get(f"http://127.0.0.1:8188/view", params=img_info)
            return img.content
    
    return None
```

### 场景检测

```python
def detect_scenes(content: str) -> List[str]:
    """从文本中检测适合插图的场景"""
    keywords = ["战斗", "风景", "城市", "宫殿", "森林", "海洋", "星空"]
    scenes = []
    
    for keyword in keywords:
        if keyword in content:
            # 提取包含关键词的段落
            for para in content.split('\n'):
                if keyword in para and len(para) > 20:
                    scenes.append(para[:200])
    
    return scenes
```

## 依赖

- ComfyUI: https://github.com/comfyanonymous/ComfyUI
- SD WebUI: https://github.com/AUTOMATIC1111/stable-diffusion-webui
- httpx: `pip install httpx`
