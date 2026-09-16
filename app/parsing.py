"""
纯函数解析模块 (P2-6)。

从 NovelWriterApp 的巨型方法 `_parse_json_response` / `_parse_exp_json`
中抽取出的纯逻辑：不依赖 self、GUI 或任何全局可变状态 —— 输入字符串、输出数据结构，
因此可被独立单元测试（见 tests/test_parsing.py）。

第二轮优化（2026-09-16）新增：
- `clean_ai_json_text` / `repair_ai_json_text`：两种 JSON 清洗策略
- `extract_characters_payload` / `parse_characters_payload` / `strip_ai_json_fences`：
  收敛原先散落在 `character_ui` 中、已出现漂移的三份「角色原始文本解析」实现

第三轮修复（2026-09-17）：
- L1/L2 结构性修复改为**字符串感知**（`_repair_structures`），不再改写字符串正文
- L3 `clean_ai_json_text` 的弯引号状态机改为对称（`“` 开 / `”` 关）
- L10 不再把顶层键 `raw` 当作"必然是旧版载体"而丢弃名为 raw 的角色
- M2 删除全仓零引用的死常量 `_CHARACTER_FIELD_NAMES`
- M3 Strategy 5 从 O(n²) 降为 O(n)（配对括号预计算）
- M4 Strategy 4 增加"括号配平 + 顶层类型一致"校验，不再把失败伪装成成功
- M12 EXP 数值读取加保护与钳位（超长数字串会让 `int()` 抛错）
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

# Strategy 5 中不应被当作角色名的键：它们的值是角色的子对象（武器/属性等），
# 不是角色本身。
# L10：此前这里还包含 `"raw"`，导致一个**真的叫 raw 的角色**被静默丢弃；
# 现在只保留真正是子对象的字段名。
_PARSE_SKIP_KEYS = frozenset({"weapon", "attributes", "skill_suggestions"})

# 匹配 `"键": {` 的位置（Strategy 5 用）
_KEY_OBJECT_RE = re.compile(r'"([^"]+)"\s*:\s*\{')

# M12：EXP 单次增减的绝对上限。正则可能抓到超长数字串
# （如 100 位数字），`int()` 在超过 `sys.get_int_max_str_digits()` 时抛错；
# 即便不抛错，下游按数值计算也会溢出。这里统一钳位。
_MAX_ABS_EXP = 1_000_000


def clean_ai_json_text(text: str) -> str:
    """字符串感知的 AI JSON 清洗。

    只修复**字符串字面量之外**的全角标点与弯引号：

    - ``：`` → ``:``、``，`` → ``,``（仅在字符串外）
    - ``“`` / ``”`` → ``"``（仅在字符串外，此时它们是 JSON 分隔符）
    - 字符串内部的 ``，``、``：``、``“…”`` **原样保留**

    这样 ``{"personality": "外冷内热，常说“我不在乎”"}`` 这类含中文标点与
    内嵌引号的内容不会被破坏 —— 旧的朴素做法会把它们一并替换成半角或直引号，
    导致 JSON 非法或文案被改写。

    L3 修复（引号对称）：此前**字符串外**的 ``“`` 与 ``”`` 都会 `in_string = True`，
    于是 ``{“a”: “b”}`` 会被解析成"开、开"两次而永远关不上。现在记录进入字符串
    时用的是哪种引号：由 ``“`` 开启的字符串只有 ``”`` 能关闭（反之由 ``"`` 开启的
    字符串只有 ``"`` 能关闭），因此 ``{“a”: “b”}`` 能直接归一化为合法 JSON，
    而 ``{"口头禅": "他常说“我不在乎”"}`` 里的弯引号仍原样保留。
    """
    if not text:
        return text

    out = []
    in_string = False
    opener = ""  # 进入字符串时使用的引号：'"' 或 '“'
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
            if opener == '"':
                if ch == '"':
                    in_string = False
                # 字符串内部一律原样保留（含 ，： “ ” ‘ ’）
                out.append(ch)
            else:
                # 由 “ 开启的字符串
                if ch == "\u201d":  # ” 关闭
                    in_string = False
                    out.append('"')
                elif ch == '"':
                    # 直引号出现在弯引号字符串内部：作为字面量保留会破坏 JSON，
                    # 转义后保留内容
                    out.append('\\"')
                else:
                    out.append(ch)
        else:
            if ch == '"':
                in_string = True
                opener = '"'
                out.append(ch)
            elif ch == "\u201c":  # “ 作为分隔符
                in_string = True
                opener = "\u201c"
                out.append('"')
            elif ch == "\u201d":  # ” 出现在字符串外 —— 只可能是闭合符误入
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


# ----------------------------------------------------------------- 结构性修复


def _iter_segments(text: str):
    """把文本切成 ``(是否为字符串字面量, 片段)`` 的列表。

    字符串片段**包含两侧引号**；未闭合的字符串会一直延伸到串尾（容错）。
    """
    segments = []
    buf = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != '"':
            buf.append(ch)
            i += 1
            continue
        if buf:
            segments.append((False, "".join(buf)))
            buf = []
        j = i + 1
        chunk = ['"']
        while j < n:
            if text[j] == "\\" and j + 1 < n:
                chunk.append(text[j])
                chunk.append(text[j + 1])
                j += 2
                continue
            chunk.append(text[j])
            if text[j] == '"':
                j += 1
                break
            j += 1
        segments.append((True, "".join(chunk)))
        i = j
    if buf:
        segments.append((False, "".join(buf)))
    return segments


def _repair_outside_strings(chunk: str) -> str:
    """只作用于「字符串之外」片段的结构修复。"""
    # 连续冒号（AI 常写成 "key"::value）
    chunk = re.sub(r":{2,}", ":", chunk)
    # 尾随逗号：{"a": 1,}
    chunk = re.sub(r",\s*([\]}])", r"\1", chunk)
    return chunk


def _repair_structures(text: str) -> str:
    """字符串感知的结构性修复（L1/L2 的核心修复）。

    旧实现把三条正则直接作用在**整段文本**上，其中
    ``re.sub(r",\\s*([\\]}])", r"\\1", text)`` 会跨越字符串边界：
    ``{"a": "正文,}"}`` 里的 ``,}`` 被当成尾随逗号删掉 —— **小说正文被改写**。

    现在先按「字符串字面量 / 非字符串」切段，只对非字符串片段做替换；
    「缺失逗号」这条规则本身就在两个字符串片段之间生效，改为在切段结构上
    判断：前一段是字符串、中间段只含空白与换行、后一段也是字符串时补 ``,``。

    注：``goal`` 这类"数组型字段归一化为字符串"的修复需要跨越引号匹配，
    仍在整段上应用；它只有在冒号后紧跟 ``[`` 时才触发，误伤面远小于逗号规则。
    """
    segments = _iter_segments(text)

    for idx, (is_str, chunk) in enumerate(segments):
        if not is_str:
            segments[idx] = (False, _repair_outside_strings(chunk))

    # 缺失逗号：  "字符串片段" <换行/空白> "字符串片段"  →  前一段后补逗号
    for idx in range(1, len(segments) - 1):
        prev_is_str = segments[idx - 1][0]
        cur_is_str, cur_chunk = segments[idx]
        next_is_str = segments[idx + 1][0]
        if prev_is_str and next_is_str and not cur_is_str and re.fullmatch(r"\s*\n\s*", cur_chunk):
            segments[idx] = (False, "," + cur_chunk)

    fixed = "".join(chunk for _is_str, chunk in segments)

    # 数组型 goal / target / objective / purpose → 分号连接的字符串
    fixed = re.sub(
        r'("(?:goal|target|objective|purpose)")\s*:\s*\[([^\]]*)\]',
        lambda m: m.group(1) + ': "' + "; ".join(re.findall(r'"([^"]*)"', m.group(2))) + '"',
        fixed,
    )
    return fixed


def _fix_common_json_defects(text: str) -> str:
    """修复 AI 常见的结构性错误：数组型 goal、连续冒号、尾随逗号、缺失逗号。

    第三轮起改为调用字符串感知实现（见 `_repair_structures`），
    保证不会改写字符串正文。
    """
    return _repair_structures(text)


def _pair_braces(text: str) -> dict:
    """返回 ``{`` 下标 → 配对 ``}`` 下标 的映射（单次栈扫描，O(n)）。

    M3：Strategy 5 旧实现对**每个**键匹配都从该处向后扫到串尾寻找配对括号，
    最坏 O(n²)；200 KB 的 AI 响应可能长时间占住 UI 线程。
    """
    stack = []
    pairs = {}
    for idx, ch in enumerate(text):
        if ch == "{":
            stack.append(idx)
        elif ch == "}" and stack:
            pairs[stack.pop()] = idx
    return pairs


def _extract_complete_objects(text: str) -> dict:
    """逐个提取 ``"键": { ... }`` 形式的**完整**子对象。

    Strategy 5 与 `parse_characters_payload` 的共用实现（v3 A1/A2 去重）。

    末段对象被截断时尝试补 1~2 个 ``}`` 再解析 —— 这是旧
    `novel_agent._extract_characters_from_raw` 手写扫描里唯一有价值的能力，
    收敛实现时必须保留，否则"AI 响应被截断"场景的补救能力会静默退化。
    """
    result = {}
    pairs = _pair_braces(text)
    pos = 0
    while True:
        m = _KEY_OBJECT_RE.search(text, pos)
        if not m:
            break
        pos = m.end()
        name = m.group(1)
        if name in _PARSE_SKIP_KEYS:
            continue
        brace_start = m.end() - 1
        close = pairs.get(brace_start)
        if close is not None:
            try:
                result[name] = json.loads(text[brace_start : close + 1])
            except (json.JSONDecodeError, ValueError):
                pass
            continue
        # 该对象未闭合（响应被截断）→ 补括号后重试
        tail = text[brace_start:]
        for closing in ('"}', "}", "}}"):
            try:
                result[name] = json.loads(tail + closing)
                break
            except (json.JSONDecodeError, ValueError):
                continue
    return result


def _is_balanced(text: str) -> bool:
    """字符串感知地检查 ``{}`` / ``[]`` 是否配平且引号闭合。"""
    depth = 0
    bracket = 0
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
            if bracket < 0:
                return False
        i += 1
    return depth == 0 and bracket == 0 and not in_string


def parse_characters_payload(raw) -> dict:
    """从 AI 返回的 raw 文本中提取 ``{角色名: {...}}``。

    多层容错，按"保真度"依次尝试：字符串感知清洗 → 朴素清洗；每层再叠加
    结构性缺陷修复。任一候选能解析出非空角色字典即返回。

    L10：不再用保留键剔除 `raw` —— 只有**值不是 dict** 的条目会被丢掉，
    因此一个真的叫 `raw` 的角色（其值是 dict）不会被静默丢弃。
    """
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(v, dict)}
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
                chars = {k: v for k, v in parsed.items() if isinstance(v, dict)}
                if chars:
                    return chars

    # 兜底：外层 JSON 被截断、但内部角色对象本身已完整 → 逐个提取。
    # 只走**保真**变体（不做朴素的弯引号/全角逗号全量替换），
    # 避免"救回角色"的代价是把值里的中文标点改掉。
    #
    # v3 A2：这段能力原先由 `novel_agent._extract_characters_from_raw` 手写
    # 扫描承担（含"末段对象补括号"），实现收敛到这里后必须保留，
    # 否则截断响应的补救能力会静默退化。
    for variant in (clean_ai_json_text(text), _repair_structures(clean_ai_json_text(text))):
        chars = _extract_complete_objects(variant)
        if chars:
            return chars
    return {}


def extract_characters_payload(data) -> dict:
    """从 `memory/characters.json` 的解析结果中取出角色字典。

    兼容两种格式：
    - 现行格式：``{角色名: {字段...}}``
    - 旧版格式：``{"raw": "<AI 原始输出>"}``

    L10 修复：此前只凭键名 `raw` 就认定是旧版载体，且一旦把 `raw` 当载体就
    **提前返回**、不再看顶层其它条目 —— 于是「一个叫 raw 的角色」会被拿去当
    载体解析并从结果里消失。现在：
      - 只有 `raw` 的值是**字符串**时才视为旧版载体（旧格式存的就是文本）；
      - 解析结果与顶层条目**并集**返回，而不是提前返回，避免丢角色。
    """
    if not isinstance(data, dict):
        return {}

    # 现行格式的条目：所有 dict 值的条目都是角色
    result = {k: v for k, v in data.items() if isinstance(v, dict)}

    raw = data.get("raw")
    if isinstance(raw, str):
        parsed = parse_characters_payload(raw)
        if parsed:
            merged = dict(parsed)
            merged.update(result)  # 顶层现状更权威
            return merged

    return result


def _repair_json_preserving_strings(raw: str) -> str:
    """保真修复：只动字符串之外的标点，字符串内部原样保留（L2）。

    第三步起统一委托给 `clean_ai_json_text` + `_repair_structures`：
    旧版本这里一半的正则（尾随逗号、连续冒号、缺失逗号）其实是
    **字符串不感知**的，会把 `{"a": "正文,}"}` 里的 `,}` 删掉 ——
    名为"保真"却并不保真。现在所有结构性修复都走同一套字符串感知实现。
    """
    return _repair_structures(clean_ai_json_text(raw))


def _repair_json_naive(raw: str) -> str:
    """兼容修复：全角标点与弯引号一律替换（原实现行为，逐字保留）。

    这是**有意不保真**的兜底候选：AI 把弯引号当 JSON 分隔符时，
    只有全量替换能救回来。调用方按"保真版先试、朴素版兜底"的顺序解析。
    """
    fixed = repair_ai_json_text(raw)
    # 连续冒号
    fixed = re.sub(r'("\w+")\s*:{2,}', r"\1:", fixed)
    # goal数组→字符串
    fixed = re.sub(
        r'("(?:goal|target|objective|purpose)")\s*:\s*\[([^\]]*)\]',
        lambda m: m.group(1) + ': "' + "; ".join(re.findall(r'"([^"]*)"', m.group(2))) + '"',
        fixed,
    )
    # 尾随逗号
    fixed = re.sub(r",\s*([\]}])", r"\1", fixed)
    # 缺失逗号: "value"\n  "key" → "value",\n  "key"
    fixed = re.sub(r'"\s*\n(\s*")', '",\n\\1', fixed)
    return fixed


def parse_json_response(response: str, default, is_list: bool = False):
    """`_parse_json_response` 的纯逻辑（P2-6 抽取）。

    v3 A1：本函数是**唯一实现**。`NovelAgent._parse_json_response` /
    `GenerationUIMixin._parse_json_response` 都只是薄委托。

    `is_list=True` 时优先按 ``[ ]`` 提取，且**只接受 list 结果**
    —— 保留旧实现的类型语义（`generate_outline` 等调用点随后按序列遍历，
    若在期望列表时返回 dict，遍历到的会是键名字符串）。
    """
    if not response or not isinstance(response, str):
        return default

    text = response.strip()
    # 标记优先次序：期望列表时先找 [ ]，否则先找 { }
    marker_pairs = [("[", "]"), ("{", "}")] if is_list else [("{", "}"), ("[", "]")]
    strategies = []

    # Strategy 1: 直接提取 { } 或 [ ]
    for marker, end_marker in marker_pairs:
        start = text.find(marker)
        end = text.rfind(end_marker) + 1
        if start >= 0 and end > start:
            strategies.append(text[start:end])

    # Strategy 2: 清理 markdown 后提取
    clean = text.replace("```json", "").replace("```", "")
    for marker, end_marker in marker_pairs:
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
            parsed = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            continue
        if is_list and not isinstance(parsed, list):
            # 期望列表却解析出对象 → 这个候选不合格，继续找
            continue
        return parsed

    # Strategy 4: 尝试补全截断的JSON
    # M4：旧实现无条件把 `'"}', '"}]' …` 拼到候选串尾再 `json.loads`，
    # 只要恰好解析成功就 `return` —— 可能返回一个"合法但语义错误"的对象，
    # 把解析失败伪装成成功（下游据此走错分支，比直接失败更难排查）。
    # 现在要求补全后 **括号配平** 且 **顶层类型与候选开头字符一致**。
    for s in strategies:
        opener = s.lstrip()[:1]
        for suffix in ['"}', '"}]', '"}}', '"}]}}', '"]}}}', "}}}", '"}\n}', '"}\n}]']:
            candidate = s + suffix
            if not _is_balanced(candidate):
                # 补全后结构仍不平衡 → 这次"成功"必然是假象，跳过
                continue
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if opener == "{" and not isinstance(parsed, dict):
                continue
            if opener == "[" and not isinstance(parsed, list):
                continue
            if is_list and not isinstance(parsed, list):
                continue
            return parsed

    # Strategy 5: 逐个提取已完成的对象
    # M3：改为预计算配对括号（O(n)），不再对每个匹配向后扫到串尾（O(n²)）。
    for s in strategies:
        chars = _extract_complete_objects(s)
        if chars:
            # BUG-5：is_list=True 时返回 list 而非 dict（保留旧行为）
            return list(chars.values()) if is_list else chars

    return default


def _safe_exp_int(value, default: int = 0) -> int:
    """把 AI 返回的 EXP 值安全转成 int 并钳位（M12）。

    直接 `int()` 有两个坑：
    1. 值可能不是数字（None / 字符串 / 列表）→ 抛 TypeError/ValueError；
    2. 超过 `sys.get_int_max_str_digits()`（Python 3.11+ 默认 4300）位的数字串
       会让 `int()` 抛 ValueError —— 这个异常会一路冒到 UI 线程；即便不抛错，
       下游按数值计算也可能溢出。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        if re.fullmatch(r"-?\d+", text):
            # 超长数字串：按符号钳到边界，而不是把用户看到的数值变成 0
            return -_MAX_ABS_EXP if text.startswith("-") else _MAX_ABS_EXP
        return default
    return max(-_MAX_ABS_EXP, min(_MAX_ABS_EXP, number))


def _normalize_exp_entries(data: dict) -> dict:
    """把已解析结果中的 exp 统一钳位（M12）。

    Strategy 1/2 直接返回 `json.loads` 的结果，其中的 exp 可能是字符串、
    超大整数或非数字；统一走 `_safe_exp_int`，下游才能安全参与计算。
    """
    for val in data.values():
        if isinstance(val, dict) and "exp" in val:
            val["exp"] = _safe_exp_int(val.get("exp", 0))
    return data


def parse_exp_json(response: str) -> dict:
    """_parse_exp_json 的纯逻辑（P2-6 抽取）。"""
    if not response:
        return {}

    # Strategy 1: 括号深度追踪（最可靠，提取完整外层JSON）
    start = response.find("{")
    if start >= 0:
        depth = 0
        end_idx = -1
        for i in range(start, len(response)):
            if response[i] == "{":
                depth += 1
            elif response[i] == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        if end_idx > start:
            json_str = response[start:end_idx]
            json_str = re.sub(r",\s*}", "}", json_str)
            json_str = re.sub(r",\s*]", "]", json_str)
            try:
                result = json.loads(json_str)
                if isinstance(result, dict):
                    return _normalize_exp_entries(result)
            except (json.JSONDecodeError, ValueError):
                # M12: 超长数字串会让 json.loads 抛 ValueError（非 JSONDecodeError），
                # 旧实现只捕获 JSONDecodeError → 异常直接冒到调用方的 UI 线程
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

    start = cleaned.find("{")
    if start >= 0:
        depth = 0
        end_idx = -1
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        if end_idx > start:
            try:
                parsed = json.loads(cleaned[start:end_idx])
                if isinstance(parsed, dict):
                    return _normalize_exp_entries(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 3: 逐行提取key-value对
    result = {}
    pattern = r'"([^"]+)"\s*:\s*\{[^}]*"action"\s*:\s*"([^"]*)"[^}]*"exp"\s*:\s*(-?\d+)[^}]*"detail"\s*:\s*"([^"]*)"'
    for m in re.finditer(pattern, response):
        result[m.group(1)] = {"action": m.group(2), "exp": _safe_exp_int(m.group(3)), "detail": m.group(4)}

    # Strategy 4: 处理截断的JSON（AI响应被截断的情况）
    if not result:
        # 尝试提取部分数据：{"角色名": {"action": "行为", "exp": 数值, "detail": ...
        partial_pattern = r'"([^"]+)"\s*:\s*\{\s*"action"\s*:\s*"([^"]*)"[^}]*"exp"\s*:\s*(-?\d+)'
        for m in re.finditer(partial_pattern, response):
            result[m.group(1)] = {"action": m.group(2), "exp": _safe_exp_int(m.group(3)), "detail": ""}

    # Strategy 5: 尝试补全截断的JSON后解析
    if not result and response.strip().startswith("{"):
        # 尝试补全JSON
        truncated = response.strip()
        # 计算缺少的闭合括号
        open_braces = truncated.count("{") - truncated.count("}")
        open_brackets = truncated.count("[") - truncated.count("]")
        # 补全
        completed = truncated
        if not completed.endswith('"'):
            completed += '"'
        completed += "}" * open_braces + "]" * open_brackets
        try:
            data = json.loads(completed)
            if isinstance(data, dict):
                # 验证数据格式
                for key, val in data.items():
                    if isinstance(val, dict) and "exp" in val:
                        result[key] = {
                            "action": val.get("action", ""),
                            "exp": _safe_exp_int(val.get("exp", 0)),
                            "detail": val.get("detail", ""),
                        }
        except (json.JSONDecodeError, ValueError):
            pass

    return result
