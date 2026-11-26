"""角色生成用例：请求 → 三层回退解析 → 落盘 → 与既有角色取并集。

## 为什么回退有**三层**

模型的 JSON 输出经常"七成对"：外层被截断、某个 `goal` 写成数组、
或者干脆在 JSON 前后加一段解释。三层按保真度递降：

1. `parse_json_response` —— 标准解析（含围栏/尾逗号/截断补全）
2. `parse_characters_payload` —— 字符串感知清洗 + 结构性修复 + 逐个提取
3. 逐行抓 `"名字": {` —— **最后手段**，产出"待展开"骨架而不是放弃
   （用户至少能在面板里看到新角色并手改）

## 🔴 写回必须是并集

`chars` 只包含**本次**生成的几个角色。直接覆盖 `characters.json`
会把书里已有角色（实测 286 个）全清掉。而且如果磁盘档案已损坏，
`get_characters()` 降级返回 `{}`，并集会退化成覆盖 ——
所以读到降级结果时要**立即失败**（`CharacterDataGuardError`），
而不是写出一份"看起来正常"的残缺数据。
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional

from app.memory_manager import CharacterDataGuardError
from app.parsing import parse_characters_payload, parse_json_response
from app.storage import atomic_write_json, safe_filename

__all__ = ["GenerateCharacters"]


def _looks_like_character_map(value: Any) -> bool:
    """判断解析结果是否**像**角色表（至少有一个值是 dict）。

    只看"是不是 dict"是不够的：模型带前言时 `parse_json_response` 会抓
    到内层的单个对象（如 `{"personality": "沉默"}`），形状合法但根本不是
    角色表。若据此认为"解析成功"，后面的逐字段回退就全被跳过了。
    """
    if not isinstance(value, dict):
        return False
    return any(isinstance(item, dict) for item in value.values())


class GenerateCharacters:
    """生成角色并落盘。

    `memory` 需要提供：`get_meta` / `get_settings` / `get_characters` /
    `mutate_characters`，以及 `novel_dir`（或 `memory_dir`）。
    """

    def __init__(self, ai: Any, memory: Any, log: Optional[Callable[[str], None]] = None) -> None:
        self.ai = ai
        self.memory = memory
        self.log = log or (lambda _message: None)

    def execute(self, genre: str, title: str, count: int = None) -> dict:
        """生成角色 - 根据小说规模智能确定角色数量"""
        if count is None:
            chapter_count = self.memory.get_meta("chapter_count", 20)
            if chapter_count <= 20:
                count = 3
            elif chapter_count <= 50:
                count = 5
            else:
                count = 8

        # 🔒 读取已锁定的主角名，确保每次生成都用同一个名字
        protagonist = self.memory.get_meta("protagonist", "")

        self.log(f"[智能体] 正在生成{count}个角色...")
        settings = self.memory.get_settings()

        system = f"""你是专业角色设计师。世界观：{json.dumps(settings, ensure_ascii=False)[:500]}
    请为小说《{title}》创建{count}个角色。必须输出JSON格式：

    {{
      "角色名": {{
        "gender": "男/女/未知",
        "age": 25,
        "category": "主角/关键人物/配角/无名小卒",
        "faction": "中立/主角阵营/敌对阵营/第三方势力",
        "personality": "性格描述（50字以上，具体、有特点、有弱点）",
        "background": "背景故事（100字以上，包括出身、经历、动机）",
        "appearance": "外貌描述",
        "weapon": {{"name": "武器名", "quality": "普通/精良/稀有/史诗/传说", "desc": "描述"}},
        "skill_suggestions": ["技能1", "技能2"],
        "attributes": {{
          "力量": 随机值,
          "敏捷": 随机值,
          "体质": 随机值,
          "智力": 随机值,
          "精神": 随机值,
          "魅力": 随机值,
          "幸运": 随机值
        }},
        "relationship_to_main": "与主角的关系",
        "goal": "单一字符串，表示角色核心目标（如：成为最强武者），禁止使用数组！"
      }}
    }}

    严格要求：
    - 每个角色必须有独特的人格和背景
    - goal 必须是普通字符串，绝对不能是 [] 数组！
    - 所有键名必须用英文双引号，冒号用英文半角 ":"
    - 属性值合理分布（不是所有角色同属性）
    - 确保 JSON 语法完全正确，可被 json.loads 解析"""

        # 🔒 主角名锁定：如果已有主角名，强制AI使用该名字
        if protagonist:
            system += f"\n\n【重要】主角名已锁定为「{protagonist}」，必须使用此名字，不可更改！"

        prompt = f"小说类型：{genre}\n标题：{title}\n创建{count}个角色，每个角色有完整的性格、背景、武器、技能"
        if protagonist:
            prompt = f"主角名：{protagonist}\n" + prompt

        # 重试3次，处理AI返回空响应的情况（但不重试认证错误）
        response = None
        for attempt in range(3):
            try:
                response = self.ai.chat(
                    [{"role": "user", "content": prompt}], system=system, max_tokens=12000, thinking_enabled=False
                )
            except Exception as e:
                if "401" in str(e) or "Authorization" in str(e) or "API Key" in str(e):
                    raise  # 认证错误不重试
                if attempt < 2:
                    self.log(f"[角色] 调用失败({attempt + 1}/3): {e}，重试...")
                    time.sleep(3)
                    continue
                raise

            if response and len(response) > 50:
                break
            if attempt < 2:
                self.log(f"[角色] AI响应较慢，正在重试({attempt + 1}/3)，请稍候...")
                time.sleep(3)

        chars = parse_json_response(response, None)

        # 🔧 关键修复：即使解析成功，如果角色数量不足也需要回退
        parsed_count = len(chars) if isinstance(chars, dict) else 0
        if parsed_count > 0 and parsed_count < count:
            self.log(f"[角色] 初步解析仅获得 {parsed_count}/{count} 个角色，尝试从原始响应补充...")

        # 多层回退：如果标准解析失败（或数量不足），尝试从原始响应中提取
        # 🔴 判据是"像不像角色表"而不是"是不是 dict"：
        # 模型带前言时第 1 层会抓到内层单个对象，形状合法但内容不是角色表，
        # 若据此判"成功"，第 2/3 层就永远不跑（实测会一个角色都拿不到）。
        need_extract = not _looks_like_character_map(chars) or (isinstance(chars, dict) and len(chars) < count)
        if need_extract:
            self.log(f"[角色] 解析遇到问题 (当前{len(chars) if chars else 0}/{count})，尝试从原始响应恢复...")
            if response:
                self.log(f"[调试] 响应长度: {len(response)} 字符")
                self.log(f"[调试] 响应前200字: {response[:200]}")
            extracted = parse_characters_payload(response)
            if extracted:
                # 合并而非替换: 保留已解析的，补充新提取的
                if chars and isinstance(chars, dict):
                    for k, v in extracted.items():
                        if k not in chars:
                            chars[k] = v
                else:
                    chars = extracted
                self.log(f"[角色] 从原始响应补充了 {len(extracted)} 个角色 (总计 {len(chars)})")

        # Strategy 5: 如果还是失败，尝试逐行提取角色名并创建基础角色
        if not chars or len(chars) == 0:
            self.log("[角色] 尝试最终回退策略: 从响应中提取角色名...")
            if response:
                import re as _char_re

                # 前两层都失败时 `chars` 可能是 None —— 不先兜住，
                # 下面的赋值会抛 TypeError，把"最后手段"变成"最后崩溃"。
                if not isinstance(chars, dict):
                    chars = {}

                name_patterns = _char_re.findall(r'"([^"]{1,6})"\s*:\s*\{', response)
                if name_patterns:
                    t = title
                    for name in name_patterns[:count]:
                        if name not in [
                            "gender",
                            "age",
                            "category",
                            "faction",
                            "personality",
                            "background",
                            "appearance",
                            "weapon",
                            "attributes",
                            "skill_suggestions",
                            "goal",
                            "relationship_to_main",
                            "title",
                            "summary",
                            "key_events",
                        ]:
                            if name not in (chars or {}):
                                chars[name] = {
                                    "gender": "未知",
                                    "age": 25,
                                    "category": "关键人物",
                                    "faction": "中立",
                                    "personality": "待展开",
                                    "background": f"《{t}》中的重要角色",
                                    "appearance": "待展开",
                                    "weapon": {"name": "未设定", "quality": "普通", "desc": "待展开"},
                                    "skill_suggestions": [],
                                    "attributes": {"力量": 50, "敏捷": 50, "智力": 50, "体力": 50, "魅力": 50},
                                    "relationship_to_main": "待展开",
                                    "goal": "待展开",
                                }
                    if chars:
                        self.log(f"[角色] 最终回退创建了 {len(chars)} 个基础角色")
        elif isinstance(chars, dict) and len(chars) < count:
            # 补充: 已解析到部分角色但不足count，也从响应中提取角色名做基础角色
            self.log(f"[角色] 角色不足 (当前{len(chars)}/{count})，从响应补充基础角色...")
            if response:
                import re as _char_re2

                name_patterns = _char_re2.findall(r'"([^"]{1,6})"\s*:\s*\{', response)
                existing = set(chars.keys())
                # 🔴 先算死"还差几个"：写进循环条件里会变成移动靶 ——
                # 每补一个 `len(chars)` 就 +1，条件随之收紧 ⇒ 永远只补 1 个。
                missing = max(0, count - len(chars))
                field_names = {
                    "gender",
                    "age",
                    "category",
                    "faction",
                    "personality",
                    "background",
                    "appearance",
                    "weapon",
                    "attributes",
                    "skill_suggestions",
                    "goal",
                    "relationship_to_main",
                    "title",
                    "summary",
                    "key_events",
                    "name",
                    "level",
                    "hp",
                    "mp",
                    "exp",
                    "stats",
                }
                t = title
                added = 0
                for name in name_patterns:
                    if name not in existing and name not in field_names and added < missing:
                        chars[name] = {
                            "gender": "未知",
                            "age": 25,
                            "category": "配角",
                            "faction": "中立",
                            "personality": "待AI展开",
                            "background": f"《{t}》中的{name}",
                            "appearance": "待AI展开",
                            "weapon": {"name": "未设定", "quality": "普通", "desc": "待展开"},
                            "skill_suggestions": [],
                            "attributes": {"力量": 50, "敏捷": 50, "智力": 50, "体力": 50, "魅力": 50},
                            "relationship_to_main": "与主角的关系待展开",
                            "goal": "待AI展开",
                        }
                        existing.add(name)
                        added += 1
                if added > 0:
                    self.log(f"[角色] 补充了 {added} 个基础角色 (总计 {len(chars)}/{count})")

        if not chars or not isinstance(chars, dict):
            self.log("[角色] AI未能生成有效角色数据，将使用已有角色")
            return {}

        # 过滤掉 raw 键（_parse_json_response 的回退值）
        chars = {k: v for k, v in chars.items() if k != "raw" and isinstance(v, dict)}
        if not chars:
            self.log("[角色] 未能提取到有效角色，将使用已有角色")
            return {}

        # 保存角色文件
        saved_count = 0
        chars_dir = self.memory.novel_dir / "characters" if hasattr(self.memory, "novel_dir") else None
        if chars_dir is None:
            chars_dir = self.memory.memory_dir.parent / "characters"
        chars_dir.mkdir(exist_ok=True)

        for name, info in chars.items():
            if isinstance(info, dict):
                char_data = {"name": name, **info}
                # API-3修复: 文件名安全处理（统一委托 app.storage.safe_filename）
                safe_name = safe_filename(name)
                atomic_write_json(chars_dir / f"{safe_name}.json", char_data)
                saved_count += 1

        if saved_count > 0:
            self.log(f"[角色] 已保存 {saved_count} 个角色到 {chars_dir}")
        else:
            self.log("[角色] 警告：未能保存任何角色文件！")

        # 写回 memory/characters.json。
        # 关键：必须与既有角色取并集，不能整体覆盖 —— `chars` 只包含本次 AI
        # 生成的一批，直接覆盖会把小说里已有的角色（当前实测 286 个）全部清掉。
        # 同名角色的字段按"新数据优先"合并，未出现在本批次中的角色原样保留。
        def _merge(existing: dict):
            merged = dict(existing)
            for name, info in chars.items():
                old = merged.get(name)
                if isinstance(old, dict) and isinstance(info, dict):
                    combined = dict(old)
                    combined.update(info)
                    merged[name] = combined
                else:
                    merged[name] = info
            return merged

        # V4: 先确认底座可信。若磁盘上的角色档案已损坏且无可用备份，
        # `get_characters()` 会降级返回 {}，于是下面的"并集"退化成"整体覆盖"
        # ——上一轮修好的 R1 在损坏场景下完全不生效，且因为结果是非空，
        # 用户看不到任何告警。这里在读到降级结果后立即失败，交出可操作的提示。
        #
        # 用 `is True` 而非真值判断：`self.memory` 允许是鸭子类型的协作者
        # （单测里就是 MagicMock），`getattr(mock, "_characters_corrupt")` 会返回
        # 一个真值的子 Mock，真值判断会把**一切**调用都误判成"底座损坏"。
        before = len(self.memory.get_characters())
        if getattr(self.memory, "_characters_corrupt", False) is True:
            raise CharacterDataGuardError(
                "角色档案损坏且无可用备份，已拒绝本次角色写入以避免清空既有角色；"
                "请先修复 memory/characters.json（或其 .bak）后重试"
            )

        merged_chars = self.memory.mutate_characters(_merge)
        added = len(merged_chars) - before
        if added > 0:
            self.log(f"[角色] 新增 {added} 个角色（既有 {before} 个已保留）")

        return chars
