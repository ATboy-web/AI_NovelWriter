"""题材与标签注册表（v3.2 新增）—— 可扩展 + 用户可自定义。

## 它替代了什么

原先 `MALE_GENRES`(78) / `FEMALE_GENRES`(57) / `MALE_TAGS`(100) / `FEMALE_TAGS`(104)
**全部内联在 `lifecycle_ui.py` 的一个 UI 构建函数里**（约 370 行）。这带来三个问题：

| 问题 | 后果 |
|---|---|
| 不可自定义 | 用户想加一个题材必须**改源码**并重新打包 |
| 不可单测 | 数据藏在 GUI 函数内 ⇒ 要拿它得先起 Tk |
| 职责混乱 | 一个 UI 函数里塞了 370 行业务数据 |

现在三层分离：
- **数据** → `app/genres_data.py`（纯清单）
- **逻辑** → 本模块（读取 / 校验 / 增删 / 持久化）
- **UI** → `lifecycle_ui.py` 只读注册表，不再持有清单

## 设计要点

1. **注册表驱动** —— 与 `PLUGIN_TYPES` / `ProviderRegistry` / `IMAGE_BACKENDS` / `TRANSPORTS`
   同构：新增一个频道只改 `CHANNEL_LABELS` 一处。
2. **结构化结果** `GenreResult`（`ok`/`message`/`as_dict()`），
   仿 `PluginResult` / `MCPResult` / `BalanceResult`。
3. **路径唯一来源** `default_genres_file()` —— 别在别处再拼一次。
4. **宽松读、严格写**：配置损坏一律**忽略并降级为内置清单**，绝不抛
   （题材选择不该让应用起不来）；但写入要校验、去重、原子替换。
5. **不破坏已有作品**：`with_novel_genre()` 保证"某本小说用的题材即使
   已被用户删除，也仍能在选择器里显示"，不会静默把作品的题材改掉。

## 题材的字符串形态

约定为 `大类-子类`（如 `玄幻-东方玄幻`）。但自定义题材**允许不含 `-`**
（用户可能只写 "蒸汽朋克"）—— 此时整串即大类，子类为空。
解析统一走 `split_genre()` / `make_genre()`，别在别处手写 `split("-")`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from .genres_data import BUILTIN_GENRES, BUILTIN_TAGS, CHANNEL_LABELS

__all__ = [
    "CHANNEL_LABELS",
    "DEFAULT_CHANNEL",
    "GENRE_SEPARATOR",
    "MAX_GENRE_LENGTH",
    "GenreRegistry",
    "GenreResult",
    "default_genres_file",
    "get_genre_registry",
    "make_genre",
    "reset_genre_registry",
    "split_genre",
    "validate_name",
]

#: 默认频道（男频）。别名见 `DEFAULT_CHANNEL_ALIASES`。
DEFAULT_CHANNEL = "male"

#: 频道别名 → 规范键。用户/旧数据可能写 `男`/`男生`/`male`。
DEFAULT_CHANNEL_ALIASES: Dict[str, str] = {
    "male": "male",
    "m": "male",
    "男": "male",
    "男生": "male",
    "男频": "male",
    "男生频道": "male",
    "female": "female",
    "f": "female",
    "女": "female",
    "女生": "female",
    "女频": "female",
    "女生频道": "female",
}

#: 题材的大类/子类分隔符。
GENRE_SEPARATOR = "-"

#: 名称长度上限（题材与标签一致）。留出余量且远小于文件系统/展示限制。
MAX_GENRE_LENGTH = 64

#: 名称禁止字符：控制字符、路径分隔符、换行（它们会破坏 JSON/展示/文件名）。
_FORBIDDEN_CHARS = ("\x00", "\n", "\r", "\t", "/", "\\")

#: 允许出现的字符：字母 / 数字 / 中文 / 常见标点 / 空格。
#: ❗ 与插件名同理：判据是"拦真正危险的"，不是"尽量少放行"
#: —— 窄白名单曾把 `·` 这类中文标点误判为非法（插件系统踩过一次）。
_NAME_PATTERN = re.compile(
    r"^[\w\u4e00-\u9fff\u00b7\u2022\u3001\u3002\u300a\u300b\u300c\u300d\u300e\u300f\uff08\uff09\uff1a\uff0c\uff01\uff1f—\-·. +]+$"
)


def default_genres_file() -> Path:
    """题材自定义配置的唯一来源 —— 别在别处再拼一次这个路径。"""
    return Path.home() / ".ai_novel_writer" / "genres.json"


def normalize_channel(channel: str) -> str:
    """把频道别名归一化；无法识别时回落默认频道。"""
    key = str(channel or "").strip().lower()
    return DEFAULT_CHANNEL_ALIASES.get(key, DEFAULT_CHANNEL_ALIASES.get(str(channel or "").strip(), DEFAULT_CHANNEL))


def validate_name(name: str, *, max_length: int = MAX_GENRE_LENGTH) -> Tuple[bool, str]:
    """校验题材 / 标签 / 分类名。返回 `(是否合法, 原因)`。

    为什么单独一个函数：三处（题材、标签、分类）判据必须一致，
    否则会出现"题材能加、标签不能加"这种让人困惑的不一致。
    """
    text = str(name or "").strip()
    if not text:
        return False, "名称不能为空"
    if len(text) > max_length:
        return False, f"名称过长（{len(text)} > {max_length}）"
    for ch in _FORBIDDEN_CHARS:
        if ch in text:
            shown = {"\n": "换行", "\r": "回车", "\t": "制表符", "\x00": "空字符"}.get(ch, ch)
            return False, f"名称不能包含「{shown}」"
    if not _NAME_PATTERN.match(text):
        return False, "名称包含不允许的字符（仅支持中英文、数字与常见标点）"
    return True, ""


def split_genre(genre: str) -> Tuple[str, str]:
    """把 `玄幻-东方玄幻` 拆成 `("玄幻", "东方玄幻")`。

    不含分隔符时返回 `(整串, "")` —— 自定义题材允许只写一个词。
    """
    text = str(genre or "").strip()
    if not text:
        return "", ""
    if GENRE_SEPARATOR in text:
        category, _, detail = text.partition(GENRE_SEPARATOR)
        return category.strip(), detail.strip()
    return text, ""


def make_genre(category: str, detail: str = "") -> str:
    """由大类与子类拼回题材串；子类为空则只返回大类。"""
    cat = str(category or "").strip()
    det = str(detail or "").strip()
    if not det:
        return cat
    return f"{cat}{GENRE_SEPARATOR}{det}"


@dataclass
class GenreResult:
    """题材操作结果（结构化）。仿 `PluginResult` / `MCPResult` / `BalanceResult`。"""

    ok: bool
    message: str = ""
    detail: dict = field(default_factory=dict)

    @classmethod
    def success(cls, message: str = "", **detail) -> "GenreResult":
        return cls(ok=True, message=message, detail=dict(detail))

    @classmethod
    def failed(cls, message: str, reason: str = "", **detail) -> "GenreResult":
        data = dict(detail)
        if reason:
            data["reason"] = reason
        return cls(ok=False, message=message, detail=data)

    @property
    def reason(self) -> str:
        return str(self.detail.get("reason", ""))

    def as_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, "detail": self.detail}

    def __bool__(self) -> bool:
        return self.ok


class GenreRegistry:
    """内置题材/标签 + 用户自定义，统一从这里读。

    配置文件（`default_genres_file()`）形如：

    ```json
    {
      "custom_genres": {"male": ["蒸汽朋克", "硬科幻-太空歌剧"], "female": []},
      "custom_tags": {"male": {"世界观": ["蒸汽动力", "飞空艇"]}},
      "removed_genres": {"male": ["玄幻-宗门林立"]}
    }
    ```

    `removed_genres` 让用户可以**隐藏内置项**而不必改源码 —
    这是"完善管理"的必要一环：只能加不能减的清单不是可管理的清单。
    """

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = Path(config_file) if config_file else default_genres_file()
        self._custom_genres: Dict[str, List[str]] = {}
        self._custom_tags: Dict[str, Dict[str, List[str]]] = {}
        self._removed_genres: Dict[str, List[str]] = {}
        self._load()

    # ------------------------------------------------------------ 配置读写

    def _load(self) -> None:
        """读配置。文件不存在/损坏/形状不对 ⇒ 忽略并降级为内置清单，绝不抛。"""
        self._custom_genres = {}
        self._custom_tags = {}
        self._removed_genres = {}
        if not self.config_file.exists():
            return
        try:
            raw = json.loads(self.config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"[题材] 配置文件无法读取，已回退到内置清单：{e}")
            return
        if not isinstance(raw, dict):
            logger.warning("[题材] 配置文件顶层不是对象，已忽略")
            return

        # ❗ 每段都必须显式 `isinstance` 检查，**不能**靠 `or {}` 兜底：
        # `raw.get("x") or {}` 在 x 是**非空列表**时会原样返回列表，
        # 后续 `.items()` 直接抛 AttributeError —— 而本函数的契约是"绝不抛"。
        # 这正是"损坏配置必须降级"这条承诺的实际检验点。
        raw_genres = raw.get("custom_genres")
        if isinstance(raw_genres, dict):
            for channel, names in raw_genres.items():
                if not isinstance(names, list):
                    continue
                ch = normalize_channel(channel)
                for name in names:
                    ok, _why = validate_name(name)
                    if ok:
                        self._custom_genres.setdefault(ch, []).append(str(name).strip())

        raw_tags = raw.get("custom_tags")
        if isinstance(raw_tags, dict):
            for channel, cats in raw_tags.items():
                if not isinstance(cats, dict):
                    continue
                ch = normalize_channel(channel)
                for cat, tag_list in cats.items():
                    if not isinstance(tag_list, list):
                        continue
                    ok_cat, _ = validate_name(cat)
                    if not ok_cat:
                        continue
                    bucket = self._custom_tags.setdefault(ch, {}).setdefault(str(cat).strip(), [])
                    for tag in tag_list:
                        ok, _why = validate_name(tag)
                        if ok:
                            bucket.append(str(tag).strip())

        raw_removed = raw.get("removed_genres")
        if isinstance(raw_removed, dict):
            for channel, names in raw_removed.items():
                if not isinstance(names, list):
                    continue
                ch = normalize_channel(channel)
                for name in names:
                    if isinstance(name, str) and name.strip():
                        self._removed_genres.setdefault(ch, []).append(name.strip())

    def as_dict(self) -> dict:
        return {
            "custom_genres": {k: list(v) for k, v in self._custom_genres.items()},
            "custom_tags": {k: {c: list(t) for c, t in v.items()} for k, v in self._custom_tags.items()},
            "removed_genres": {k: list(v) for k, v in self._removed_genres.items()},
        }

    def save(self) -> GenreResult:
        """原子写回配置（唯一临时名 + `os.replace`，避免写一半被截断）。"""
        try:
            from .storage import atomic_write_json
        except ImportError:  # pragma: no cover - storage 是核心模块，理论上不会缺
            return GenreResult.failed("无法导入存储模块", reason="io_error")
        try:
            atomic_write_json(self.config_file, self.as_dict(), indent=2)
        except OSError as e:
            return GenreResult.failed(f"保存失败：{e}", reason="io_error")
        return GenreResult.success("已保存自定义题材配置", file=str(self.config_file))

    def reload(self) -> GenreResult:
        self._load()
        return GenreResult.success("已重新加载题材配置")

    # ------------------------------------------------------------ 读取

    def channels(self) -> List[str]:
        """全部频道键（顺序稳定，便于 UI 展示）。"""
        return list(CHANNEL_LABELS)

    def channel_label(self, channel: str) -> str:
        return CHANNEL_LABELS.get(normalize_channel(channel), str(channel))

    def builtin_genres(self, channel: str) -> List[str]:
        return list(BUILTIN_GENRES.get(normalize_channel(channel), ()))

    def custom_genres(self, channel: str) -> List[str]:
        return list(self._custom_genres.get(normalize_channel(channel), []))

    def removed_genres(self, channel: str) -> List[str]:
        return list(self._removed_genres.get(normalize_channel(channel), []))

    def genres_for(self, channel: str) -> List[str]:
        """该频道的**生效**题材列表 = 内置（去掉被隐藏的）+ 自定义。

        ❗ 顺序是刻意的：内置在前（保持稳定、老用户的位置感不变），
        自定义在后（新加的可见）。**不去重会出问题**，所以自定义里
        与内置重名的条目会被跳过（由 `add_genre` 拦，但配置可能被手改）。
        """
        ch = normalize_channel(channel)
        removed = set(self._removed_genres.get(ch, []))
        seen: set[str] = set()
        result: List[str] = []
        for name in self.builtin_genres(ch):
            if name in removed or name in seen:
                continue
            seen.add(name)
            result.append(name)
        for name in self._custom_genres.get(ch, []):
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result

    def builtin_tags(self, channel: str) -> Dict[str, List[str]]:
        ch = normalize_channel(channel)
        return {cat: list(tags) for cat, tags in BUILTIN_TAGS.get(ch, {}).items()}

    def tags_for(self, channel: str) -> Dict[str, List[str]]:
        """该频道生效的标签表 = 内置分类 + 自定义补充。

        ❗ 同一分类下的自定义标签**追加在内置之后**，并去重 ——
        直接 `update()` 会把内置标签整组替换掉（那是数据丢失，不是"扩充"）。
        """
        ch = normalize_channel(channel)
        merged: Dict[str, List[str]] = {}
        for cat, tags in self.builtin_tags(ch).items():
            merged[cat] = list(tags)
        for cat, tags in self._custom_tags.get(ch, {}).items():
            bucket = merged.setdefault(cat, [])
            for tag in tags:
                if tag not in bucket:
                    bucket.append(tag)
        return merged

    def categories_for(self, channel: str) -> List[str]:
        return list(self.tags_for(channel))

    def all_genres(self) -> Dict[str, List[str]]:
        return {ch: self.genres_for(ch) for ch in self.channels()}

    def is_builtin_genre(self, channel: str, name: str) -> bool:
        return str(name) in BUILTIN_GENRES.get(normalize_channel(channel), ())

    def is_custom_genre(self, channel: str, name: str) -> bool:
        return str(name) in self._custom_genres.get(normalize_channel(channel), [])

    def stats(self) -> dict:
        return {
            ch: {
                "builtin_genres": len(self.builtin_genres(ch)),
                "custom_genres": len(self.custom_genres(ch)),
                "removed_genres": len(self.removed_genres(ch)),
                "effective_genres": len(self.genres_for(ch)),
                "tag_categories": len(self.categories_for(ch)),
                "tags": sum(len(v) for v in self.tags_for(ch).values()),
            }
            for ch in self.channels()
        }

    # ------------------------------------------------------------ 写入

    def add_genre(self, channel: str, name: str) -> GenreResult:
        """新增自定义题材；若该名字是**被隐藏的内置题材**则等于"恢复显示"。"""
        ch = normalize_channel(channel)
        ok, why = validate_name(name)
        if not ok:
            return GenreResult.failed(f"题材名不合法：{why}", reason="bad_name")
        text = str(name).strip()
        # ❗ 顺序关键：**必须先查"是否曾被隐藏"，再查"是否是内置"**。
        # 反过来的话，恢复隐藏项会命中 `already_builtin` 分支而被拒绝 ——
        # 那条分支的本意是"别重复添加"，却正好挡住了唯一合法的恢复路径，
        # 于是界面承诺的"再次添加同名即可恢复"变成空话（实测踩到）。
        if text in self._removed_genres.get(ch, []):
            self._removed_genres[ch] = [n for n in self._removed_genres[ch] if n != text]
            res = self.save()
            if not res.ok:
                self._removed_genres.setdefault(ch, []).append(text)  # 回滚
                return res
            return GenreResult.success(f"已恢复内置题材「{text}」", name=text, channel=ch, restored=True)
        if self.is_builtin_genre(ch, text):
            return GenreResult.failed(f"「{text}」已是内置题材，无需重复添加", reason="already_builtin")
        if text in self._custom_genres.get(ch, []):
            return GenreResult.failed(f"「{text}」已存在", reason="duplicate")
        self._custom_genres.setdefault(ch, []).append(text)
        res = self.save()
        if not res.ok:
            self._custom_genres[ch] = [n for n in self._custom_genres[ch] if n != text]  # 回滚
            return res
        return GenreResult.success(f"已添加题材「{text}」", name=text, channel=ch)

    def remove_genre(self, channel: str, name: str) -> GenreResult:
        """删除题材。

        - 自定义题材 ⇒ 从配置中移除；
        - 内置题材 ⇒ 加入 `removed_genres`（**隐藏**，不改源码）。
          这是有意为之：源码里的清单是事实，配置只表达"我不想看到它"。
        """
        ch = normalize_channel(channel)
        text = str(name or "").strip()
        if not text:
            return GenreResult.failed("题材名不能为空", reason="bad_name")
        if text in self._custom_genres.get(ch, []):
            self._custom_genres[ch] = [n for n in self._custom_genres[ch] if n != text]
            res = self.save()
            if not res.ok:
                return res
            return GenreResult.success(f"已删除自定义题材「{text}」", name=text, channel=ch)
        if self.is_builtin_genre(ch, text):
            bucket = self._removed_genres.setdefault(ch, [])
            if text in bucket:
                return GenreResult.failed(f"「{text}」已隐藏", reason="duplicate")
            bucket.append(text)
            res = self.save()
            if not res.ok:
                bucket.remove(text)
                return res
            return GenreResult.success(
                f"已隐藏内置题材「{text}」（可再次添加以恢复）", name=text, channel=ch, hidden=True
            )
        return GenreResult.failed(f"没有名为「{text}」的题材", reason="not_found")

    def add_tag(self, channel: str, category: str, tag: str) -> GenreResult:
        """在某个分类下新增自定义标签（分类不存在则创建）。"""
        ch = normalize_channel(channel)
        ok_cat, why_cat = validate_name(category)
        if not ok_cat:
            return GenreResult.failed(f"分类名不合法：{why_cat}", reason="bad_name")
        ok_tag, why_tag = validate_name(tag)
        if not ok_tag:
            return GenreResult.failed(f"标签名不合法：{why_tag}", reason="bad_name")
        cat = str(category).strip()
        text = str(tag).strip()
        existing = self.tags_for(ch).get(cat, [])
        if text in existing:
            return GenreResult.failed(f"标签「{text}」已存在于分类「{cat}」", reason="duplicate")
        bucket = self._custom_tags.setdefault(ch, {}).setdefault(cat, [])
        bucket.append(text)
        res = self.save()
        if not res.ok:
            bucket.remove(text)
            return res
        return GenreResult.success(f"已在「{cat}」下添加标签「{text}」", category=cat, tag=text, channel=ch)

    def remove_tag(self, channel: str, category: str, tag: str) -> GenreResult:
        """删除**自定义**标签。内置标签不可删除（与题材同理，只隐藏整类太粗，故明确拒绝）。"""
        ch = normalize_channel(channel)
        cat = str(category or "").strip()
        text = str(tag or "").strip()
        bucket = self._custom_tags.get(ch, {}).get(cat, [])
        if text not in bucket:
            if text in self.tags_for(ch).get(cat, []):
                return GenreResult.failed(f"「{text}」是内置标签，不能删除（可改为添加自己的标签）", reason="builtin")
            return GenreResult.failed(f"没有找到标签「{text}」", reason="not_found")
        bucket.remove(text)
        if not bucket:
            self._custom_tags.get(ch, {}).pop(cat, None)
        res = self.save()
        if not res.ok:
            return res
        return GenreResult.success(f"已删除标签「{text}」", category=cat, tag=text, channel=ch)

    def add_genre_batch(self, channel: str, names: List[str]) -> GenreResult:
        """批量添加（便于"粘贴一列题材"）。返回成功/跳过条数。"""
        added, skipped = [], []
        for name in names or []:
            res = self.add_genre(channel, name)
            (added if res.ok else skipped).append(str(name).strip())
        if not added:
            return GenreResult.failed(
                f"没有新增任何题材（跳过 {len(skipped)} 条）",
                reason="nothing_added",
                added=[],
                skipped=skipped,
            )
        return GenreResult.success(
            f"已添加 {len(added)} 个题材" + (f"，跳过 {len(skipped)} 条" if skipped else ""),
            added=added,
            skipped=skipped,
        )

    # ------------------------------------------------------------ 与作品协同

    def with_novel_genre(self, channel: str, genre: str) -> List[str]:
        """返回"该频道题材列表 + 某作品的题材（若不在列表中则补上）"。

        ❗ 这是**不破坏已有作品**的关键：
        用户可能删掉/隐藏了某本小说正在用的题材。若不补上，
        `ttk.Combobox` 会把值设成不在候选项里的字符串 ——
        界面显示空白，用户一保存就把作品的题材静默改掉了。
        """
        names = self.genres_for(channel)
        text = str(genre or "").strip()
        if text and text not in names:
            names.append(text)
        return names


# ------------------------------------------------------------ 模块级单例

_registry: Optional[GenreRegistry] = None


def get_genre_registry() -> Optional[GenreRegistry]:
    """拿到全局注册表；构造失败返回 `None`（绝不抛）。

    与 `get_plugin_manager()` / `get_mcp_manager()` 同策略：
    题材配置有问题只是少一个功能，不该让应用起不来。
    """
    global _registry
    if _registry is None:
        try:
            _registry = GenreRegistry()
        except Exception as e:  # noqa: BLE001 - 见 docstring
            logger.warning(f"[题材] 注册表初始化失败：{e}")
            return None
    return _registry


def reset_genre_registry() -> None:
    """清空单例（**仅供测试**）。"""
    global _registry
    _registry = None
