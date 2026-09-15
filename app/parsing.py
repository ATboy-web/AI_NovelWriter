"""
纯函数解析模块 (P2-6)。

从 NovelWriterApp 的巨型方法 `_parse_json_response` / `_parse_exp_json`
中抽取出的纯逻辑：不依赖 self、GUI 或任何全局可变状态 —— 输入字符串、输出数据结构，
因此可被独立单元测试（见 tests/test_parsing.py）。

方法体与原实现逐字节一致，仅由「类方法」提升为「模块级函数」。
"""

import json
import re

__all__ = ["parse_json_response", "parse_exp_json"]



def parse_json_response(response: str, default):
    """_parse_json_response 的纯逻辑（P2-6 抽取）。"""
    if not response or not isinstance(response, str):
        return default

    text = response.strip()
    strategies = []

    # Strategy 1: 直接提取 { } 或 [ ]
    for marker, end_marker in [('{', '}'), ('[', ']')]:
        start = text.find(marker)
        end = text.rfind(end_marker) + 1
        if start >= 0 and end > start:
            strategies.append(text[start:end])

    # Strategy 2: 清理 markdown 后提取
    clean = text.replace('```json', '').replace('```', '')
    for marker, end_marker in [('{', '}'), ('[', ']')]:
        start = clean.find(marker)
        end = clean.rfind(end_marker) + 1
        if start >= 0 and end > start:
            strategies.append(clean[start:end])

    # Strategy 3: 修复常见AI JSON错误
    for raw in list(strategies):
        fixed = raw
        # 全角标点 → 半角
        fixed = fixed.replace('\uff1a', ':').replace('\uff0c', ',')
        fixed = fixed.replace('\u201c', '"').replace('\u201d', '"')
        fixed = fixed.replace('\u2018', "'").replace('\u2019', "'")
        # 连续冒号
        fixed = re.sub(r'("\w+")\s*:{2,}', r'\1:', fixed)
        # goal数组→字符串
        fixed = re.sub(
            r'("(?:goal|target|objective|purpose)")\s*:\s*\[([^\]]*)\]',
            lambda m: m.group(1) + ': "' + '; '.join(re.findall(r'"([^"]*)"', m.group(2))) + '"',
            fixed
        )
        # 尾随逗号
        fixed = re.sub(r',\s*([\]}])', r'\1', fixed)
        # 缺失逗号: "value"\n  "key" → "value",\n  "key"
        fixed = re.sub(r'"\s*\n(\s*")', '",\n\\1', fixed)
        strategies.append(fixed)

    # 依次尝试
    for s in strategies:
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 4: 尝试补全截断的JSON
    for s in strategies:
        for suffix in ['"}', '"}]', '"}}', '"}]}}', '"]}}}', '}}}', '"}\n}', '"}\n}]']:
            try:
                return json.loads(s + suffix)
            except (json.JSONDecodeError, ValueError):
                continue

    # Strategy 5: 逐个提取已完成的对象
    for s in strategies:
        chars = {}
        for m in re.finditer(r'"([^"]+)"\s*:\s*\{', s):
            name = m.group(1)
            if name in ('raw', 'weapon', 'attributes', 'skill_suggestions'):
                continue
            brace_start = m.end() - 1
            depth = 0
            for j in range(brace_start, len(s)):
                if s[j] == '{': depth += 1
                elif s[j] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(s[brace_start:j+1])
                            chars[name] = obj
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break
        if chars:
            return chars

    return default



def parse_exp_json(response: str) -> dict:
    """_parse_exp_json 的纯逻辑（P2-6 抽取）。"""
    if not response:
        return {}

    # Strategy 1: 括号深度追踪（最可靠，提取完整外层JSON）
    start = response.find('{')
    if start >= 0:
        depth = 0
        end_idx = -1
        for i in range(start, len(response)):
            if response[i] == '{': depth += 1
            elif response[i] == '}':
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        if end_idx > start:
            json_str = response[start:end_idx]
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            try:
                result = json.loads(json_str)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

    # Strategy 2: 清理markdown后重试
    cleaned = response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    start = cleaned.find('{')
    if start >= 0:
        depth = 0
        end_idx = -1
        for i in range(start, len(cleaned)):
            if cleaned[i] == '{': depth += 1
            elif cleaned[i] == '}':
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        if end_idx > start:
            try:
                return json.loads(cleaned[start:end_idx])
            except json.JSONDecodeError:
                pass

    # Strategy 3: 逐行提取key-value对
    result = {}
    pattern = r'"([^"]+)"\s*:\s*\{[^}]*"action"\s*:\s*"([^"]*)"[^}]*"exp"\s*:\s*(-?\d+)[^}]*"detail"\s*:\s*"([^"]*)"'
    for m in re.finditer(pattern, response):
        result[m.group(1)] = {
            "action": m.group(2),
            "exp": int(m.group(3)),
            "detail": m.group(4)
        }

    # Strategy 4: 处理截断的JSON（AI响应被截断的情况）
    if not result:
        # 尝试提取部分数据：{"角色名": {"action": "行为", "exp": 数值, "detail": ...
        partial_pattern = r'"([^"]+)"\s*:\s*\{\s*"action"\s*:\s*"([^"]*)"[^}]*"exp"\s*:\s*(-?\d+)'
        for m in re.finditer(partial_pattern, response):
            result[m.group(1)] = {
                "action": m.group(2),
                "exp": int(m.group(3)),
                "detail": ""
            }

    # Strategy 5: 尝试补全截断的JSON后解析
    if not result and response.strip().startswith('{'):
        # 尝试补全JSON
        truncated = response.strip()
        # 计算缺少的闭合括号
        open_braces = truncated.count('{') - truncated.count('}')
        open_brackets = truncated.count('[') - truncated.count(']')
        # 补全
        completed = truncated
        if not completed.endswith('"'):
            completed += '"'
        completed += '}' * open_braces + ']' * open_brackets
        try:
            data = json.loads(completed)
            if isinstance(data, dict):
                # 验证数据格式
                for key, val in data.items():
                    if isinstance(val, dict) and 'exp' in val:
                        result[key] = {
                            "action": val.get("action", ""),
                            "exp": int(val.get("exp", 0)),
                            "detail": val.get("detail", "")
                        }
        except (json.JSONDecodeError, ValueError):
            pass

    return result
