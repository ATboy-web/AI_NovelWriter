"""角色成长检测：从本章正文里读出"谁变强了/谁死了/谁换了阵营"，写回角色数据。

## 为什么值得单独一个用例

这是唯一会**自动修改角色属性**的路径。它的失败方式很隐蔽：
模型返回的 JSON 结构稍有偏差，要么整批丢（角色永远不成长），
要么把"死亡"记成"重伤"（世界线就不自洽了）。而这些都不会报错。

## 依赖 memory 而不是直接写盘

属性写入走 `memory.update_character`（它内部有 `.bak` 与锁），
事件走 `memory.add_event`（供时间线与面板消费）。
用例本身不碰文件，因此也不需要原子写。
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from loguru import logger

from app.parsing import parse_json_response

__all__ = ["UpdateCharacterProgression"]


def _diag_logger():
    """取当前诊断日志实例。

    ❗ **不要缓存**返回值：测试隔离（`reset_logger()`）会换掉全局单例，
    缓存的快照会指向旧目录 —— 现象是"日志该写却没写"，且只在跑测试时出现。
    """
    try:
        from app.diagnostic_logger import get_logger

        return get_logger()
    except Exception:  # noqa: BLE001 - 诊断不可用时不该影响业务
        return None


class UpdateCharacterProgression:
    """检测并写回角色变化。

    `memory` 需要提供：`get_characters` / `update_character` / `add_event`。
    """

    def __init__(self, ai: Any, memory: Any, log: Optional[Callable[[str], None]] = None) -> None:
        self.ai = ai
        self.memory = memory
        self.log = log or (lambda _message: None)

    def execute(self, chapter_num: int, content: str, summary: str):
        """检测角色成长变化并更新属性"""
        try:
            chars = self.memory.get_characters()
            if not chars:
                return

            # 构建角色列表（含更多上下文）
            char_list = []
            for name, info in list(chars.items())[:20]:
                if isinstance(info, dict):
                    role = info.get("category", info.get("role", "未知"))
                    faction = info.get("faction", "未知")
                    char_list.append(f"{name}({role}/{faction})")
                else:
                    char_list.append(name)
            existing_names = ", ".join(char_list)

            system = f"""分析第{chapter_num}章中所有角色的变化（主角、配角、反派、路人等都算）。
    当前角色: {existing_names}

    【重要】检测本章中所有角色（不只主角）的：
    - 战斗成长（属性提升）
    - 关系变化（盟友/敌人）  
    - 物品得失（宝物/武器/装备）
    - 技能领悟
    - 角色死亡或重伤

    输出JSON:
    {{
      "updates": [
        {{"name": "角色名", "change": "+力量+3 或 +智力+2", "reason": "战斗中突破极限"}}
      ],
      "relationship_changes": [
        {{"name1": "角色A", "name2": "角色B", "old": "朋友", "new": "敌人", "reason": "背叛"}}
      ],
      "items_gained": [
        {{"name": "角色名", "item": "物品名", "quality": "普通/精良/稀有/史诗/传说", "from": "来源"}}
      ],
      "items_lost": [
        {{"name": "角色名", "item": "物品名", "reason": "战斗中毁坏"}}
      ],
      "skills_learned": [
        {{"name": "角色名", "skill": "技能名", "type": "攻击/防御/辅助", "how": "如何学会"}}
      ],
      "deaths": ["死亡角色名"],
      "new_allies": ["新盟友名"],
      "new_enemies": ["新敌人名"]
    }}

    变化包括正面和负面的。没有变化就输出{{"updates":[]}}。
    **必须检测所有出现的角色，不止主角。只输出JSON，不要其他文字！**"""

            # 采样策略：开头2000 + 中间1000 + 结尾1000，覆盖全文
            if len(content) > 4000:
                mid = len(content) // 2
                sample = (
                    content[:2000]
                    + "\n...(中间省略)...\n"
                    + content[mid - 500 : mid + 500]
                    + "\n...(省略)...\n"
                    + content[-1000:]
                )
            else:
                sample = content

            response = self.ai.chat(
                [
                    {
                        "role": "user",
                        "content": f"章节摘要: {summary}\n内容片段: {sample}\n\n请直接输出JSON，不要分析过程。",
                    }
                ],
                system=system,
                max_tokens=3000,
                thinking_enabled=False,
            )
            if not response:
                return

            # P2-7 收敛：此前这里有 **Strategy 1–3 三段共 60 余行手写解析**
            # （括号深度追踪 → 正则 + 再追踪一次 → 去 markdown 重试），
            # 全部是 `parse_json_response` Strategy 1/2/3 的真子集。
            # 行为只可能**变好**：本处的失败路径是直接 `[角色成长] JSON解析失败，跳过本章`
            # 丢数据，而统一解析器额外覆盖单引号、弯引号、截断补全（Strategy 4）。
            data = parse_json_response(response, None)

            # Strategy 4（**保留**）：逐字段提取。
            # 这一策略统一解析器覆盖不到 —— 它针对的是"AI 返回大段思考文本 +
            # 其中夹着一个**本身就不合法**的 updates 数组"的极端情况：
            # 只能靠正则把每个 `{..."name":..."}` 单独捞出来重建。
            if not isinstance(data, dict):
                try:
                    # 提取 "updates" 数组内容
                    updates_match = re.search(r'"updates"\s*:\s*\[([\s\S]*?)\]', response)
                    if updates_match:
                        updates_str = updates_match.group(1)
                        # 提取每个 {name:..., change:..., reason:...} 对象
                        update_items = re.finditer(r'\{[^{}]*"name"\s*:\s*"([^"]*)"[^{}]*\}', updates_str)
                        updates = []
                        for m in update_items:
                            obj_str = m.group(0)
                            name = re.search(r'"name"\s*:\s*"([^"]*)"', obj_str)
                            change = re.search(r'"change"\s*:\s*"([^"]*)"', obj_str)
                            reason = re.search(r'"reason"\s*:\s*"([^"]*)"', obj_str)
                            if name:
                                updates.append(
                                    {
                                        "name": name.group(1),
                                        "change": change.group(1) if change else "",
                                        "reason": reason.group(1) if reason else "",
                                    }
                                )
                        if updates:
                            data = {"updates": updates}
                except Exception as _silent_e:
                    logger.debug(f"[novel_agent] 捕获异常: {_silent_e}")

            if not data:
                self.log("[角色成长] JSON解析失败，跳过本章")
                diag = _diag_logger()
                if diag:
                    diag.log(
                        "WARN",
                        "character_growth_parse_failed",
                        {
                            "chapter": chapter_num,
                            "response_preview": response[:200] if response else "null",
                            "response_len": len(response) if response else 0,
                        },
                    )
                return

            # 保存到记忆
            changes = 0
            if data.get("updates"):
                for u in data["updates"]:
                    if isinstance(u, dict) and u.get("name"):
                        self.memory.add_event(
                            chapter_num,
                            f"角色变化: {u['name']} {u.get('change', '')} ({u.get('reason', '')})",
                            "character_growth",
                        )
                        changes += 1

            if data.get("skills_learned"):
                for s in data["skills_learned"]:
                    if isinstance(s, dict) and s.get("name"):
                        self.memory.add_event(
                            chapter_num, f"技能领悟: {s['name']} 学会 {s.get('skill', '')}", "skill_learn"
                        )
                        changes += 1

            if data.get("relationship_changes"):
                for r in data["relationship_changes"]:
                    if isinstance(r, dict) and r.get("name1"):
                        self.memory.add_event(
                            chapter_num,
                            f"关系变化: {r['name1']}与{r.get('name2', '')} {r.get('old', '')}→{r.get('new', '')}",
                            "relationship_change",
                        )
                        changes += 1

            if data.get("items_gained"):
                for item in data["items_gained"]:
                    if isinstance(item, dict) and item.get("name"):
                        self.memory.add_event(
                            chapter_num, f"获得物品: {item['name']} 获得 {item.get('item', '')}", "item_gain"
                        )

            if data.get("items_lost"):
                for item in data["items_lost"]:
                    if isinstance(item, dict) and item.get("name"):
                        self.memory.add_event(
                            chapter_num, f"失去物品: {item['name']} 失去 {item.get('item', '')}", "item_loss"
                        )

            if data.get("new_allies"):
                for name in data["new_allies"]:
                    # 纯空格也算脏数据：写进时间线只会得到一个空白条目
                    if isinstance(name, str) and name.strip():
                        self.memory.add_event(chapter_num, f"新盟友: {name}", "new_ally")

            if data.get("new_enemies"):
                for name in data["new_enemies"]:
                    # 纯空格也算脏数据：写进时间线只会得到一个空白条目
                    if isinstance(name, str) and name.strip():
                        self.memory.add_event(chapter_num, f"新敌人: {name}", "new_enemy")

            if data.get("deaths"):
                for name in data["deaths"]:
                    # 纯空格也算脏数据：写进时间线只会得到一个空白条目
                    if isinstance(name, str) and name.strip():
                        self.memory.add_event(chapter_num, f"角色死亡: {name}", "character_death")
                        self.memory.update_character(name, {"status": "死亡", "death_chapter": chapter_num})

            # 统计日志
            summary_parts = []
            if changes:
                summary_parts.append(f"{changes}个成长")
            if data.get("items_gained"):
                summary_parts.append(f"{len(data['items_gained'])}个获得")
            if data.get("items_lost"):
                summary_parts.append(f"{len(data['items_lost'])}个失去")
            if data.get("skills_learned"):
                summary_parts.append(f"{len(data['skills_learned'])}个技能")
            if data.get("relationship_changes"):
                summary_parts.append(f"{len(data['relationship_changes'])}个关系")
            if data.get("deaths"):
                summary_parts.append(f"{len(data['deaths'])}个死亡")
            if data.get("new_allies"):
                summary_parts.append(f"{len(data['new_allies'])}个新盟友")
            if data.get("new_enemies"):
                summary_parts.append(f"{len(data['new_enemies'])}个新敌人")

            if summary_parts:
                self.log(f"[角色成长] 第{chapter_num}章: {', '.join(summary_parts)}")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            self.log(f"[角色成长] 检测跳过: {e}")
