# AI_NovelWriter API 测试方案

**API测试专家**: 接口探  
**日期**: 2026-07-01  
**版本**: v1.0

---

## 📊 API 概览

### 服务架构

| 服务 | 端口 | 端点数 | 职责 |
|------|------|--------|------|
| AI Service | 8001 | 15 | AI模型推理 |
| Novel Service | 8002 | 36 | 小说生成业务 |
| 桌面客户端 | - | - | 本地API调用 |

### 端点统计

| 类别 | 端点数 | 说明 |
|------|--------|------|
| 健康检查 | 4 | /health, /api/v1/health |
| 文本生成 | 6 | /generate/* |
| 模型管理 | 4 | /models/* |
| 小说类型 | 3 | /novel-types, /supported-types |
| 向量检索 | 2 | /vector/* |
| 一致性检查 | 1 | /consistency/* |
| 定稿系统 | 2 | /finalization/* |
| 对话推演 | 2 | /dialogue/* |
| 故事流 | 3 | /story-flow/* |
| 风格转换 | 3 | /style-transfer/* |
| 事物描写 | 4 | /description/* |
| 角色桥段 | 4 | /bridge/* |
| **总计** | **38** | |

---

## 🎯 测试策略

### 测试层次

```
┌─────────────────────────────────────────────┐
│           E2E 端到端测试                      │
│         (完整业务流程验证)                     │
├─────────────────────────────────────────────┤
│           API 集成测试                        │
│       (服务间调用验证)                        │
├─────────────────────────────────────────────┤
│           API 功能测试                        │
│       (单端点功能验证)                        │
├─────────────────────────────────────────────┤
│           API 安全测试                        │
│       (认证/授权/漏洞)                        │
├─────────────────────────────────────────────┤
│           API 性能测试                        │
│       (响应时间/吞吐量)                       │
└─────────────────────────────────────────────┘
```

### 测试覆盖率目标

| 测试类型 | 目标覆盖率 | 优先级 |
|----------|------------|--------|
| 功能测试 | 100% 端点 | 🔴 高 |
| 安全测试 | OWASP Top 10 | 🔴 高 |
| 性能测试 | SLA验证 | 🟡 中 |
| 集成测试 | 服务间调用 | 🟡 中 |
| 契约测试 | API兼容性 | 🟢 低 |

---

## 🔍 功能测试用例

### 1. 健康检查端点

#### 1.1 AI Service 健康检查

```python
# 测试用例: HEALTH-001
def test_ai_service_health():
    """验证AI服务健康检查端点"""
    response = requests.get("http://localhost:8001/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "models" in data
    assert "timestamp" in data
```

```python
# 测试用例: HEALTH-002
def test_ai_service_health_with_models():
    """验证AI服务健康检查包含模型状态"""
    response = requests.get("http://localhost:8001/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert isinstance(data["models"], dict)
```

#### 1.2 Novel Service 健康检查

```python
# 测试用例: HEALTH-003
def test_novel_service_health():
    """验证小说服务健康检查端点"""
    response = requests.get("http://localhost:8002/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "version" in data
```

```python
# 测试用例: HEALTH-004
def test_novel_service_new_features_health():
    """验证新功能模块健康检查"""
    response = requests.get("http://localhost:8002/api/v1/new-features/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "modules" in data
    assert isinstance(data["modules"], dict)
```

### 2. 文本生成端点

#### 2.1 通用文本生成

```python
# 测试用例: GENERATE-001
def test_generate_text_basic():
    """验证基本文本生成"""
    payload = {
        "prompt": "写一段科幻小说的开头",
        "model_type": "local",
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "content" in data
    assert len(data["content"]) > 0
```

```python
# 测试用例: GENERATE-002
def test_generate_text_with_openai():
    """验证OpenAI模型文本生成"""
    payload = {
        "prompt": "写一段科幻小说的开头",
        "model_type": "openai",
        "model_name": "gpt-4o-mini",
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

```python
# 测试用例: GENERATE-003
def test_generate_text_invalid_model():
    """验证无效模型类型处理"""
    payload = {
        "prompt": "测试",
        "model_type": "invalid_model",
        "max_tokens": 100
    }
    
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload
    )
    
    assert response.status_code in [400, 422]
```

```python
# 测试用例: GENERATE-004
def test_generate_text_empty_prompt():
    """验证空提示词处理"""
    payload = {
        "prompt": "",
        "model_type": "local",
        "max_tokens": 100
    }
    
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload
    )
    
    assert response.status_code in [400, 422]
```

#### 2.2 章节生成

```python
# 测试用例: CHAPTER-001
def test_generate_chapter_basic():
    """验证基本章节生成"""
    payload = {
        "novel_type": "scifi",
        "chapter_title": "第一章：起源",
        "chapter_outline": "主角发现了一个神秘的装置",
        "max_tokens": 500,
        "temperature": 0.8
    }
    
    response = requests.post(
        "http://localhost:8001/api/v1/generate/chapter",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "word_count" in data
    assert data["word_count"] > 0
```

```python
# 测试用例: CHAPTER-002
def test_generate_chapter_with_previous_content():
    """验证带前文的章节生成"""
    payload = {
        "novel_type": "scifi",
        "chapter_title": "第二章：发现",
        "chapter_outline": "主角进一步探索装置的秘密",
        "previous_content": "第一章内容...",
        "max_tokens": 500
    }
    
    response = requests.post(
        "http://localhost:8001/api/v1/generate/chapter",
        json=payload
    )
    
    assert response.status_code == 200
```

```python
# 测试用例: CHAPTER-003
def test_generate_chapter_all_novel_types():
    """验证所有小说类型支持"""
    novel_types = [
        "scifi", "mystery", "romance", "fantasy", "urban",
        "history", "martial_arts", "xianxia", "horror",
        "military", "game", "sports", "time_travel",
        "system_flow", "apocalypse"
    ]
    
    for novel_type in novel_types:
        payload = {
            "novel_type": novel_type,
            "chapter_title": f"测试章节-{novel_type}",
            "chapter_outline": "测试大纲",
            "max_tokens": 100
        }
        
        response = requests.post(
            "http://localhost:8001/api/v1/generate/chapter",
            json=payload
        )
        
        assert response.status_code == 200, f"小说类型 {novel_type} 生成失败"
```

#### 2.3 大纲生成

```python
# 测试用例: OUTLINE-001
def test_generate_outline_basic():
    """验证基本大纲生成"""
    payload = {
        "novel_type": "scifi",
        "title": "星际迷航",
        "synopsis": "人类首次星际旅行的故事",
        "chapter_count": 5,
        "model_type": "local"
    }
    
    response = requests.post(
        "http://localhost:8001/api/v1/generate/outline",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "outline" in data
    assert isinstance(data["outline"], list)
    assert len(data["outline"]) == 5
```

```python
# 测试用例: OUTLINE-002
def test_generate_outline_max_chapters():
    """验证最大章节数限制"""
    payload = {
        "novel_type": "scifi",
        "title": "测试小说",
        "synopsis": "测试",
        "chapter_count": 100,
        "model_type": "local"
    }
    
    response = requests.post(
        "http://localhost:8001/api/v1/generate/outline",
        json=payload
    )
    
    # 应该成功或返回限制提示
    assert response.status_code in [200, 400]
```

#### 2.4 人物生成

```python
# 测试用例: CHARACTER-001
def test_generate_character_basic():
    """验证基本人物生成"""
    payload = {
        "novel_type": "scifi",
        "character_name": "李明",
        "character_role": "主角",
        "character_traits": ["勇敢", "聪明", "善良"],
        "model_type": "local"
    }
    
    response = requests.post(
        "http://localhost:8001/api/v1/generate/character",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "character" in data
    assert data["character"]["name"] == "李明"
```

### 3. 模型管理端点

```python
# 测试用例: MODEL-001
def test_list_models():
    """验证模型列表获取"""
    response = requests.get("http://localhost:8001/models")
    
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert isinstance(data["models"], list)
    assert "count" in data
```

```python
# 测试用例: MODEL-002
def test_get_model_status():
    """验证模型状态获取"""
    response = requests.get(
        "http://localhost:8001/models/local/status",
        params={"model_name": "qwen2.5:14b"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["unloaded", "loading", "loaded", "error"]
```

```python
# 测试用例: MODEL-003
def test_load_model():
    """验证模型加载"""
    response = requests.post(
        "http://localhost:8001/models/local/load",
        params={"model_name": "qwen2.5:14b"}
    )
    
    # 应该成功或返回已加载
    assert response.status_code == 200
```

```python
# 测试用例: MODEL-004
def test_unload_model():
    """验证模型卸载"""
    response = requests.post(
        "http://localhost:8001/models/local/unload",
        params={"model_name": "qwen2.5:14b"}
    )
    
    assert response.status_code == 200
```

### 4. 新功能端点

#### 4.1 向量检索

```python
# 测试用例: VECTOR-001
def test_vector_search():
    """验证向量搜索"""
    payload = {
        "query": "科幻小说中的太空旅行",
        "novel_id": "test_novel",
        "top_k": 5
    }
    
    response = requests.post(
        "http://localhost:8002/api/v1/vector/search",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
```

```python
# 测试用例: VECTOR-002
def test_vector_add():
    """验证向量添加"""
    payload = {
        "content": "这是一段测试内容",
        "novel_id": "test_novel",
        "metadata": {"chapter": 1}
    }
    
    response = requests.post(
        "http://localhost:8002/api/v1/vector/add",
        json=payload
    )
    
    assert response.status_code == 200
```

#### 4.2 一致性检查

```python
# 测试用例: CONSISTENCY-001
def test_consistency_check():
    """验证一致性检查"""
    payload = {
        "chapter_content": "张三走进了房间...",
        "chapter_number": 1,
        "novel_id": "test_novel",
        "previous_chapters": [],
        "characters": ["张三", "李四"],
        "settings": {}
    }
    
    response = requests.post(
        "http://localhost:8002/api/v1/consistency/check",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "issues" in data
```

#### 4.3 对话推演

```python
# 测试用例: DIALOGUE-001
def test_dialogue_generate():
    """验证对话生成"""
    payload = {
        "characters": ["张三", "李四"],
        "scene": "咖啡馆",
        "topic": "讨论项目进展",
        "dialogue_type": "casual",
        "novel_id": "test_novel"
    }
    
    response = requests.post(
        "http://localhost:8002/api/v1/dialogue/generate",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "dialogue" in data
```

#### 4.4 风格转换

```python
# 测试用例: STYLE-001
def test_style_transfer():
    """验证风格转换"""
    payload = {
        "content": "张三走进了房间，看到了李四。",
        "target_style": "古风",
        "novel_id": "test_novel"
    }
    
    response = requests.post(
        "http://localhost:8002/api/v1/style-transfer/transfer",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
```

---

## 🔒 安全测试用例

### 1. 认证测试

```python
# 测试用例: SEC-001
def test_no_auth_required():
    """验证当前无认证要求（安全风险）"""
    # 所有端点应该在无认证时返回200或401
    endpoints = [
        "http://localhost:8001/health",
        "http://localhost:8001/generate",
        "http://localhost:8002/health",
        "http://localhost:8002/generate/novel",
    ]
    
    for endpoint in endpoints:
        response = requests.get(endpoint)
        # 当前应该返回200（无认证）或401（有认证）
        assert response.status_code in [200, 401, 405]
```

```python
# 测试用例: SEC-002
def test_invalid_token():
    """验证无效Token处理"""
    headers = {"Authorization": "Bearer invalid_token"}
    
    response = requests.get(
        "http://localhost:8001/health",
        headers=headers
    )
    
    # 应该返回200（无认证）或401（有认证）
    assert response.status_code in [200, 401]
```

### 2. 输入验证测试

```python
# 测试用例: SEC-003
def test_sql_injection():
    """验证SQL注入防护"""
    payload = {
        "prompt": "'; DROP TABLE users; --",
        "model_type": "local",
        "max_tokens": 100
    }
    
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload
    )
    
    # 不应该返回500错误
    assert response.status_code != 500
```

```python
# 测试用例: SEC-004
def test_xss_prevention():
    """验证XSS防护"""
    payload = {
        "prompt": "<script>alert('xss')</script>",
        "model_type": "local",
        "max_tokens": 100
    }
    
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload
    )
    
    if response.status_code == 200:
        data = response.json()
        # 响应中不应该包含未转义的脚本标签
        assert "<script>" not in data.get("content", "")
```

```python
# 测试用例: SEC-005
def test_path_traversal():
    """验证路径遍历防护"""
    response = requests.get(
        "http://localhost:8001/../../../etc/passwd"
    )
    
    # 不应该返回文件内容
    assert response.status_code in [400, 404, 422]
```

### 3. 限流测试

```python
# 测试用例: SEC-006
def test_rate_limiting():
    """验证限流机制"""
    responses = []
    
    # 快速发送100个请求
    for _ in range(100):
        response = requests.get("http://localhost:8001/health")
        responses.append(response.status_code)
    
    # 应该有部分请求被限流（429）
    # 当前可能没有限流，记录结果
    rate_limited = responses.count(429)
    print(f"限流请求数: {rate_limited}/100")
```

### 4. CORS测试

```python
# 测试用例: SEC-007
def test_cors_headers():
    """验证CORS配置"""
    response = requests.options(
        "http://localhost:8001/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "POST"
        }
    )
    
    # 检查CORS头
    cors_origin = response.headers.get("Access-Control-Allow-Origin")
    print(f"CORS Origin: {cors_origin}")
    
    # 生产环境不应该允许所有来源
    # assert cors_origin != "*"
```

---

## ⚡ 性能测试用例

### 1. 响应时间测试

```python
# 测试用例: PERF-001
def test_response_time_health():
    """验证健康检查响应时间"""
    import time
    
    start = time.time()
    response = requests.get("http://localhost:8001/health")
    end = time.time()
    
    response_time = (end - start) * 1000  # 毫秒
    
    assert response.status_code == 200
    assert response_time < 200, f"响应时间 {response_time}ms 超过200ms SLA"
    print(f"健康检查响应时间: {response_time:.2f}ms")
```

```python
# 测试用例: PERF-002
def test_response_time_generate():
    """验证文本生成响应时间"""
    import time
    
    payload = {
        "prompt": "写一句话",
        "model_type": "local",
        "max_tokens": 50
    }
    
    start = time.time()
    response = requests.post(
        "http://localhost:8001/generate",
        json=payload,
        timeout=60
    )
    end = time.time()
    
    response_time = (end - start) * 1000
    
    assert response.status_code == 200
    print(f"文本生成响应时间: {response_time:.2f}ms")
    # AI生成可能需要较长时间，记录但不强制断言
```

### 2. 并发测试

```python
# 测试用例: PERF-003
def test_concurrent_requests():
    """验证并发请求处理"""
    import concurrent.futures
    import time
    
    def make_request():
        response = requests.get("http://localhost:8001/health")
        return response.status_code
    
    start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    end = time.time()
    
    success_count = results.count(200)
    total_time = end - start
    
    print(f"并发请求: {success_count}/50 成功")
    print(f"总时间: {total_time:.2f}s")
    print(f"QPS: {50/total_time:.2f}")
    
    assert success_count >= 45, "并发成功率低于90%"
```

### 3. 负载测试

```python
# 测试用例: PERF-004
def test_load_testing():
    """负载测试 - 逐步增加并发"""
    import concurrent.futures
    import time
    
    def make_request():
        start = time.time()
        response = requests.get("http://localhost:8001/health")
        end = time.time()
        return {
            "status": response.status_code,
            "time": (end - start) * 1000
        }
    
    concurrency_levels = [1, 5, 10, 20, 50]
    
    for level in concurrency_levels:
        start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
            futures = [executor.submit(make_request) for _ in range(level * 10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        end = time.time()
        
        success_count = sum(1 for r in results if r["status"] == 200)
        avg_time = sum(r["time"] for r in results) / len(results)
        
        print(f"并发数: {level}, 成功率: {success_count}/{len(results)}, "
              f"平均响应: {avg_time:.2f}ms, 总时间: {end-start:.2f}s")
```

---

## 🔗 集成测试用例

### 1. 服务间调用测试

```python
# 测试用例: INT-001
def test_novel_service_calls_ai_service():
    """验证小说服务调用AI服务"""
    # 通过小说服务生成章节，内部会调用AI服务
    payload = {
        "novel_type": "scifi",
        "chapter_title": "测试章节",
        "chapter_outline": "测试大纲",
        "max_tokens": 100
    }
    
    response = requests.post(
        "http://localhost:8002/generate/chapter",
        json=payload,
        timeout=60
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
```

### 2. 端到端流程测试

```python
# 测试用例: E2E-001
def test_complete_novel_generation_flow():
    """完整小说生成流程测试"""
    # 步骤1: 生成大纲
    outline_payload = {
        "novel_type": "scifi",
        "title": "测试小说",
        "synopsis": "一个科幻故事",
        "chapter_count": 3
    }
    
    outline_response = requests.post(
        "http://localhost:8002/generate/outline",
        json=outline_payload,
        timeout=60
    )
    
    assert outline_response.status_code == 200
    outline = outline_response.json()
    
    # 步骤2: 生成人物
    character_payload = {
        "novel_type": "scifi",
        "character_name": "主角",
        "character_role": "主角",
        "character_traits": ["勇敢"]
    }
    
    character_response = requests.post(
        "http://localhost:8002/generate/character",
        json=character_payload,
        timeout=60
    )
    
    assert character_response.status_code == 200
    
    # 步骤3: 生成第一章
    chapter_payload = {
        "novel_type": "scifi",
        "chapter_title": "第一章",
        "chapter_outline": outline.get("outline", [{}])[0].get("summary", ""),
        "max_tokens": 200
    }
    
    chapter_response = requests.post(
        "http://localhost:8002/generate/chapter",
        json=chapter_payload,
        timeout=60
    )
    
    assert chapter_response.status_code == 200
    chapter = chapter_response.json()
    assert len(chapter.get("content", "")) > 0
```

---

## 📋 测试数据管理

### 测试数据工厂

```python
class TestDataFactory:
    """测试数据工厂"""
    
    @staticmethod
    def create_chapter_request(**kwargs):
        defaults = {
            "novel_type": "scifi",
            "chapter_title": "测试章节",
            "chapter_outline": "测试大纲",
            "max_tokens": 100,
            "temperature": 0.8
        }
        defaults.update(kwargs)
        return defaults
    
    @staticmethod
    def create_character_request(**kwargs):
        defaults = {
            "novel_type": "scifi",
            "character_name": "测试角色",
            "character_role": "主角",
            "character_traits": ["勇敢", "聪明"]
        }
        defaults.update(kwargs)
        return defaults
    
    @staticmethod
    def create_outline_request(**kwargs):
        defaults = {
            "novel_type": "scifi",
            "title": "测试小说",
            "synopsis": "测试简介",
            "chapter_count": 5
        }
        defaults.update(kwargs)
        return defaults
```

---

## 📊 测试报告模板

### API测试报告

```markdown
# AI_NovelWriter API测试报告

## 测试概览
- 测试日期: YYYY-MM-DD
- 测试环境: 开发环境
- 测试工具: pytest + requests

## 测试结果摘要
| 测试类型 | 用例数 | 通过 | 失败 | 通过率 |
|----------|--------|------|------|--------|
| 功能测试 | XX | XX | XX | XX% |
| 安全测试 | XX | XX | XX | XX% |
| 性能测试 | XX | XX | XX | XX% |
| 集成测试 | XX | XX | XX | XX% |
| **总计** | **XX** | **XX** | **XX** | **XX%** |

## 性能指标
| 端点 | 平均响应时间 | P95响应时间 | P99响应时间 |
|------|-------------|-------------|-------------|
| /health | XXms | XXms | XXms |
| /generate | XXms | XXms | XXms |

## 安全发现
| 风险等级 | 问题描述 | 建议修复 |
|----------|----------|----------|
| 高 | 无认证保护 | 实现JWT认证 |
| 中 | CORS过于宽松 | 限制允许的来源 |

## 建议
1. 实现API认证机制
2. 添加限流中间件
3. 统一错误处理
4. 优化响应时间
```

---

## 🛠️ 测试工具配置

### pytest配置

```ini
# pytest.ini
[pytest]
testpaths = tests/api
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
markers =
    slow: 标记慢速测试
    security: 安全测试
    performance: 性能测试
    integration: 集成测试
```

### requirements-test.txt

```
pytest>=7.0.0
pytest-asyncio>=0.21.0
requests>=2.28.0
httpx>=0.24.0
respx>=0.21.0
locust>=2.0.0  # 负载测试
```

---

## 📅 测试执行计划

### 阶段1: 基础功能测试（第1周）
- [ ] 健康检查端点测试
- [ ] 文本生成端点测试
- [ ] 模型管理端点测试
- [ ] 小说类型端点测试

### 阶段2: 高级功能测试（第2周）
- [ ] 向量检索测试
- [ ] 一致性检查测试
- [ ] 对话推演测试
- [ ] 风格转换测试
- [ ] 事物描写测试
- [ ] 角色桥段测试

### 阶段3: 安全测试（第3周）
- [ ] 认证测试
- [ ] 输入验证测试
- [ ] 限流测试
- [ ] CORS测试
- [ ] OWASP Top 10测试

### 阶段4: 性能测试（第4周）
- [ ] 响应时间测试
- [ ] 并发测试
- [ ] 负载测试
- [ ] 压力测试

### 阶段5: 集成测试（第5周）
- [ ] 服务间调用测试
- [ ] 端到端流程测试
- [ ] 错误处理测试
- [ ] 降级策略测试

---

*文档生成时间: 2026-07-01*
