"""
纯函数解析模块 (P2-6)。

从 NovelWriterApp 的巨型方法 `_parse_json_response` / `_parse_exp_json`
中抽取出的纯逻辑：不依赖 self、GUI 或任何全局可变状态 —— 输入字符串、输出数据结构，
因此可被独立单元测试（见 tests/test_parsing.py）。

方法体与原实现逐字节一致，仅由「类方法」提升为「模块级函数」。

第二轮优化（2026-09-16）新增：
- `clean_ai_json_text` / `repair_ai_json_text`：两种 JSON 清洗策略
- `extract_characters_payload` / `parse_characters_payload` / `strip_ai_json_fences`：
  收敛原先散落在 `character_ui` 中、已出现漂移的三份「角色原始文本解析」实现
"""

import json
import re

__all__ = [
    "parse_json_response",
    "parse_exp_json",
    "clean_ai_json_text",
    "repair_ai_json_text",
    "strip_ai_json_fences",
    "parse_characters_payload",
    "extract_characters_payload",
]

# 角色字典中不应被当作角色名的保留键
_RESERVED_CHARACTER_KEYS = frozenset({"raw"})
# 已知的"字段名而非角色名"集合（AI 响应里出现时需排除）
_CHARACTER_FIELD_NAMES = frozenset({
    "gender", "age", "category", "faction", "personality", "background",
    "appearance", "weapon", "attributes", "skill_suggestions", "goal",
    "relationship_to_main", "title", "summary", "key_events", "name",
    "level", "hp", "mp", "exp", "stats",
})


def clean_ai_json_text(text: str) -> str:
    """字符串感知的 AI JSON 清洗。

    只修复**字符串字面量之外**的全角标点与弯引号：

    - ``：`` → ``:``、``，`` → ``,``（仅在字符串外）
    - ``“`` / ``”`` → ``"``（仅在字符串外，此时它们是 JSON 分隔符）
    - 字符串内部的 ``，``、``：``、``“…”`` **原样保留**

    这样 ``{"personality": "外冷内热，常说“我不在乎”"}`` 这类含中文标点与
    内嵌引号的内容不会被破坏 —— 旧的朴素做法会把它们一并替换成半角或直引号，
    导致 JSON 非法或文案被改写。

    已知取舍：若 AI 把弯引号**当作 JSON 分隔符**（如 ``{“a”: “b”}``），
    本函数无法修复（字符串内部一律原样保留）；这种情况由
    `repair_ai_json_text` 作为兜底候选处理，见 `parse_characters_payload`。
    """
    if not text:
        return text

    out = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            # 字符串内部一律原样保留（含 ，： “ ” ‘ ’）
            out.append(ch)
        else:
            if ch == '"':
                in_string = True
                out.append(ch)
            elif ch in ("\u201c", "\u201d"):  # “ ” 用作分隔符
                in_string = True
                out.append('"')
            elif ch == "\uff1a":  # ：
                out.append(":")
            elif ch == "\uff0c":  # ，
                out.append(",")
            elif ch in ("\u2018", "\u2019"):  # ‘ ’ 出现在字符串外，只能是误写
                out.append("'")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def repair_ai_json_text(text: str) -> str:
    """朴素的 AI JSON 清洗（兼容策略）。

    全角标点与弯引号**一律**替换为半角/直引号。会破坏字符串内部的中文标点，
    仅在 `clean_ai_json_text` 的结果无法解析时作为兜底使用 —— 例如 AI 把
    ``“…”`` 当成 JSON 的键/值分隔符时，这种粗暴替换反而是唯一能救回的做法。
    """
    if not text:
        return text
    fixed = text
    fixed = fixed.replace("\uff1a", ":").replace("\uff0c", ",")
    fixed = fixed.replace("\u201c", '"').replace("\u201d", '"')
    fixed = fixed.replace("\u2018", "'").replace("\u2019", "'")
    return fixed


def strip_ai_json_fences(text: str) -> str:
    """去掉 markdown 代码围栏与全角空格。"""
    if not isinstance(text, str):
        return ""
    clean = text.strip().replace("\u3000", " ")
    clean = re.sub(r"^```(?:json)?\s*\n?", "", clean)
    clean = re.sub(r"\n?```\s*$", "", clean)
    return clean


def _fix_common_json_defects(text: str) -> str:
    """修复 AI 常见的结构性错误：数组型 goal、连续冒号、尾随逗号。"""
    fixed = re.sub(
        r'("(?:goal|target|objective|purpose)")\s*:\s*\[([^\]]*)\]',
        lambda m: m.group(1) + ': "' + "; ".join(re.findall(r'"([^"]*)"', m.group(2))) + '"',
        text,
    )
    fixed = re.sub(r'("\w+")\s*:{2,}', r"\1:", fixed)
    fixed = re.sub(r",\s*([\]}])", r"\1", fixed)
    return fixed


def parse_characters_payload(raw) -> dict:
    """从 AI 返回的 raw 文本中提取 ``{角色名: {...}}``。

    多层容错，按"保真度"依次尝试：字符串感知清洗 → 朴素清洗；每层再叠加
    结构性缺陷修复。任一候选能解析出非空角色字典即返回。
    """
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items()
                if k not in _RESERVED_CHARACTER_KEYS and isinstance(v, dict)}
    if not isinstance(raw, str) or not raw.strip():
        return {}

    text = strip_ai_json_fences(raw)
    candidates = [clean_ai_json_text(text), repair_ai_json_text(text)]

    for candidate in candidates:
        # 先做结构性修复再解析：``goal`` 等字段下游按字符串消费，
        # 数组形式必须在此归一化（与原实现一致）。
        # 修复可能误伤合法 JSON（例如字符串内含 `,}`），因此紧接着用未修复的
        # 原文再试一次，保证不因修复而降低解析成功率。
        for variant in (_fix_common_json_defects(candidate), candidate):
            try:
                parsed = json.loads(variant)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                chars = {k: v for k, v in parsed.items()
                         if k not in _RESERVED_CHARACTER_KEYS and isinstance(v, dict)}
                if chars:
                    return chars
    return {}


def extract_characters_payload(data) -> dict:
    """从 `memory/characters.json` 的解析结果中取出角色字典。

    兼容两种格式：
    - 现行格式：``{角色名: {字段...}}``
    - 旧版格式：``{"raw": "<AI 原始输出>"}``
    """
    if not isinstance(data, dict):
        return {}

    raw = data.get("raw", "")
    if isinstance(raw, (str, dict)):
        parsed = parse_characters_payload(raw)
        if parsed:
            return parsed

    return {k: v for k, v in data.items()
            if k not in _RESERVED_CHARACTER_KEYS and isinstance(v, dict)}



def _repair_json_preserving_strings(raw: str) -> str:
    """保真修复：只动字符串之外的标点，字符串内部原样保留。"""
    fixed = clean_ai_json_text(raw)
    fixed = re.sub(r'("(?:goal|target|objective|purpose)")\s*:\s*\[([^\]]*)\]',
                   lambda m: m.group(1) + ': "' + '; '.join(re.findall(r'"([^"]*)"', m.group(2))) + '"',
                   fixed)
    fixed = re.sub(r'("\w+")\s*:{2,}', r'\1:', fixed)
    fixed = re.sub(r',\s*([\]}])', r'\1', fixed)
    # 缺失逗号: "value"\n  "key" → "value",\n  "key"
    fixed = re.sub(r'"\s*\n(\s*")', '",\n\\1', fixed)
    return fixed


def _repair_json_naive(raw: str) -> str:
    """兼容修复：全角标点与弯引号一律替换（原实现行为，逐字保留）。"""
    fixed = repair_ai_json_text(raw)
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
    return fixed


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
    # 每个候选原文产出两个修复版本并**按保真度排序**：先字符串感知版本
    # （保留字符串内部的中文标点与弯引号），再朴素全量替换版本（兜底 AI 把
    # 弯引号当作 JSON 分隔符的极端情况）。先解析成功者胜出。
    for raw in list(strategies):
        strategies.append(_repair_json_preserving_strings(raw))
        strategies.append(_repair_json_naive(raw))

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
