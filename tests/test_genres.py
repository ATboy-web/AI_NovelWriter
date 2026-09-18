"""题材系统测试（v3.2 新增：可扩展 + 用户自定义）。

## 分层

1. **纯函数** —— `split_genre` / `make_genre` / `validate_name` / `normalize_channel`
2. **注册表行为** —— 增删 / 隐藏 / 恢复 / 持久化 / 损坏配置降级
3. **不破坏作品** —— `with_novel_genre` 保证被删题材仍可见（否则会静默改掉作品题材）
4. **🔴 结构守卫** —— 数据不再内联在 UI 文件里（本轮"系统结构优化"的核心证据）
5. **真 Tk** —— 新建小说对话框能建出来、题材下拉真的被注册表填满

## 为什么第 4 层必须存在

本轮同时做了一件事：**把 357 行内联数据从 `lifecycle_ui.py` 搬进注册表**。
如果只搬不守，下一个人完全可能在 UI 里再内联一份 —— 那就回到了
「同一事实写两处必然漂移」的老路（本仓已踩过 5 次）。
所以要用断言把"数据只有一处"钉住。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import _source_scan as _scan  # noqa: E402

from app.genres import (  # noqa: E402
    CHANNEL_LABELS,
    GenreRegistry,
    get_genre_registry,
    make_genre,
    normalize_channel,
    reset_genre_registry,
    split_genre,
    validate_name,
)
from app.genres_data import BUILTIN_GENRES, BUILTIN_TAGS  # noqa: E402


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """指向临时配置文件的注册表（绝不碰用户真实的 ~/.ai_novel_writer）。"""
    monkeypatch.setattr("app.genres._registry", None)
    return GenreRegistry(config_file=tmp_path / "genres.json")


# ====================================================================== 1. 纯函数


class TestSplitAndMake:
    @pytest.mark.parametrize(
        ("raw", "expect"),
        [
            ("玄幻-东方玄幻", ("玄幻", "东方玄幻")),
            ("蒸汽朋克", ("蒸汽朋克", "")),
            ("", ("", "")),
            ("  仙侠-凡人修仙  ", ("仙侠", "凡人修仙")),
            ("A-B-C", ("A", "B-C")),  # 只按第一个分隔符拆
        ],
    )
    def test_split_genre(self, raw, expect):
        assert split_genre(raw) == expect

    def test_make_genre_roundtrip(self):
        for raw in ("玄幻-东方玄幻", "蒸汽朋克", "科幻-赛博朋克"):
            assert make_genre(*split_genre(raw)) == raw

    def test_make_genre_without_detail(self):
        assert make_genre("蒸汽朋克", "") == "蒸汽朋克"
        assert make_genre("蒸汽朋克", "   ") == "蒸汽朋克"

    def test_none_is_safe(self):
        assert split_genre(None) == ("", "")
        assert make_genre(None) == ""


class TestValidateName:
    @pytest.mark.parametrize(
        "name",
        ["玄幻", "蒸汽朋克", "玄幻-东方玄幻", "Sci-Fi", "克苏鲁·神话", "重生（逆袭）", "A B"],
    )
    def test_accepts_reasonable_names(self, name):
        ok, why = validate_name(name)
        assert ok, why

    @pytest.mark.parametrize(
        ("name", "needle"),
        [
            ("", "空"),
            ("   ", "空"),
            ("a/b", "/"),
            ("a\\b", "\\"),
            ("a\nb", "换行"),
            ("a\x00b", "空字符"),
            ("x" * 65, "过长"),
        ],
    )
    def test_rejects_dangerous_names(self, name, needle):
        ok, why = validate_name(name)
        assert not ok and needle in why

    def test_chinese_punctuation_is_not_over_blocked(self):
        """❗ 回归：窄白名单曾把合法中文标点判为非法（插件系统踩过一次）。"""
        for name in ["玄幻·东方", "重生（复仇）", "《我的题材》", "快穿：攻略"]:
            assert validate_name(name)[0] is True, name


class TestNormalizeChannel:
    @pytest.mark.parametrize("raw", ["male", "MALE", "男", "男生", "男频", "男生频道", "m"])
    def test_male_aliases(self, raw):
        assert normalize_channel(raw) == "male"

    @pytest.mark.parametrize("raw", ["female", "女生频道", "女频", "f"])
    def test_female_aliases(self, raw):
        assert normalize_channel(raw) == "female"

    def test_unknown_falls_back_to_default(self):
        assert normalize_channel("随便什么") == "male"
        assert normalize_channel(None) == "male"
        assert normalize_channel("") == "male"


# ====================================================================== 2. 内置数据完整性


class TestBuiltinData:
    """内置清单的**体量**必须被钉住。

    ❗ 抽取/搬运这类"清单数据"最危险的失败模式是**静默少几项**：
    不会报错、不影响启动，只是用户发现少了个题材。
    所以这里断言的是具体数量，而不是"非空"。
    """

    def test_genre_counts(self):
        assert len(BUILTIN_GENRES["male"]) == 78
        assert len(BUILTIN_GENRES["female"]) == 57

    def test_tag_counts(self):
        assert sum(len(v) for v in BUILTIN_TAGS["male"].values()) == 100
        assert sum(len(v) for v in BUILTIN_TAGS["female"].values()) == 104

    def test_tag_categories(self):
        assert len(BUILTIN_TAGS["male"]) == 8
        assert len(BUILTIN_TAGS["female"]) == 8

    def test_no_duplicates_inside_a_channel(self):
        for channel, names in BUILTIN_GENRES.items():
            assert len(names) == len(set(names)), f"{channel} 有重复题材"

    def test_channel_labels_cover_all_channels(self):
        for channel in BUILTIN_GENRES:
            assert channel in CHANNEL_LABELS


# ====================================================================== 3. 注册表行为


class TestReading:
    def test_starts_with_builtins(self, registry):
        assert len(registry.genres_for("male")) == 78
        assert len(registry.genres_for("female")) == 57

    def test_fresh_registry_has_no_custom(self, registry):
        for ch in registry.channels():
            assert registry.custom_genres(ch) == []

    def test_tags_are_merged_not_replaced(self, registry):
        """内置分类必须原样保留。"""
        tags = registry.tags_for("male")
        assert set(tags) == set(BUILTIN_TAGS["male"])
        for cat, items in BUILTIN_TAGS["male"].items():
            assert list(items) == tags[cat]

    def test_unknown_channel_reads_empty_not_crash(self, registry):
        assert registry.genres_for("不存在") == registry.genres_for("male")

    def test_stats_shape(self, registry):
        stats = registry.stats()
        assert stats["male"]["builtin_genres"] == 78
        assert stats["male"]["custom_genres"] == 0
        assert stats["male"]["effective_genres"] == 78


class TestAddGenre:
    def test_add_persists(self, registry, tmp_path):
        assert registry.add_genre("male", "蒸汽朋克").ok
        again = GenreRegistry(config_file=tmp_path / "genres.json")
        assert "蒸汽朋克" in again.genres_for("male")
        assert again.genres_for("male")[-1] == "蒸汽朋克", "自定义应追加在末尾"

    def test_add_rejects_duplicate(self, registry):
        registry.add_genre("male", "蒸汽朋克")
        res = registry.add_genre("male", "蒸汽朋克")
        assert not res.ok and res.reason == "duplicate"

    def test_add_rejects_builtin(self, registry):
        res = registry.add_genre("male", BUILTIN_GENRES["male"][0])
        assert not res.ok and res.reason == "already_builtin"

    @pytest.mark.parametrize("bad", ["", "  ", "a/b", "x" * 65])
    def test_add_rejects_bad_name(self, registry, bad):
        res = registry.add_genre("male", bad)
        assert not res.ok and res.reason == "bad_name"

    def test_add_to_female_does_not_leak_to_male(self, registry):
        registry.add_genre("female", "女尊天下")
        assert "女尊天下" not in registry.genres_for("male")
        assert "女尊天下" in registry.genres_for("female")

    def test_batch_add(self, registry):
        res = registry.add_genre_batch("male", ["蒸汽朋克", "硬科幻", "玄幻-东方玄幻"])
        assert res.ok
        assert len(res.detail["added"]) == 2
        assert res.detail["skipped"] == ["玄幻-东方玄幻"]

    def test_batch_add_all_skipped_reports_failure(self, registry):
        res = registry.add_genre_batch("male", [BUILTIN_GENRES["male"][0]])
        assert not res.ok and res.reason == "nothing_added"


class TestRemoveAndRestore:
    def test_remove_custom_deletes_it(self, registry):
        registry.add_genre("male", "蒸汽朋克")
        assert registry.remove_genre("male", "蒸汽朋克").ok
        assert "蒸汽朋克" not in registry.genres_for("male")
        assert registry.custom_genres("male") == []

    def test_remove_builtin_hides_it(self, registry):
        target = BUILTIN_GENRES["male"][5]
        res = registry.remove_genre("male", target)
        assert res.ok and res.detail.get("hidden") is True
        assert target not in registry.genres_for("male")
        # ❗ 关键：源码/内置清单**没有被改动**
        assert target in BUILTIN_GENRES["male"]

    def test_hiding_reduces_effective_count(self, registry):
        registry.remove_genre("male", BUILTIN_GENRES["male"][0])
        assert len(registry.genres_for("male")) == 77

    def test_readding_hidden_builtin_restores_it(self, registry):
        target = BUILTIN_GENRES["male"][3]
        registry.remove_genre("male", target)
        res = registry.add_genre("male", target)
        assert res.ok and res.detail.get("restored") is True, "应识别为'取消隐藏'而非'已存在'"
        assert target in registry.genres_for("male")
        assert registry.custom_genres("male") == [], "恢复内置项不该把它变成自定义项"

    def test_remove_unknown_is_not_found(self, registry):
        res = registry.remove_genre("male", "根本没有这个题材")
        assert not res.ok and res.reason == "not_found"

    def test_removal_persists(self, registry, tmp_path):
        target = BUILTIN_GENRES["male"][0]
        registry.remove_genre("male", target)
        again = GenreRegistry(config_file=tmp_path / "genres.json")
        assert target not in again.genres_for("male")


class TestTags:
    def test_add_tag_appends_after_builtins(self, registry):
        assert registry.add_tag("male", "世界观", "蒸汽动力").ok
        bucket = registry.tags_for("male")["世界观"]
        assert bucket[-1] == "蒸汽动力"
        assert len(bucket) == len(BUILTIN_TAGS["male"]["世界观"]) + 1

    def test_add_tag_does_not_replace_category(self, registry):
        """❗ 最容易犯的错：用 `dict.update()` 把整个分类替换掉 ⇒ 内置标签全丢。"""
        registry.add_tag("male", "世界观", "蒸汽动力")
        for item in BUILTIN_TAGS["male"]["世界观"]:
            assert item in registry.tags_for("male")["世界观"]

    def test_add_tag_creates_new_category(self, registry):
        registry.add_tag("male", "我的分类", "我的标签")
        assert "我的分类" in registry.tags_for("male")
        assert registry.tags_for("male")["我的分类"] == ["我的标签"]

    def test_duplicate_tag_rejected(self, registry):
        registry.add_tag("male", "世界观", "蒸汽动力")
        res = registry.add_tag("male", "世界观", "蒸汽动力")
        assert not res.ok and res.reason == "duplicate"

    def test_duplicate_against_builtin_rejected(self, registry):
        res = registry.add_tag("male", "世界观", BUILTIN_TAGS["male"]["世界观"][0])
        assert not res.ok and res.reason == "duplicate"

    def test_remove_custom_tag(self, registry):
        registry.add_tag("male", "世界观", "蒸汽动力")
        assert registry.remove_tag("male", "世界观", "蒸汽动力").ok
        assert "蒸汽动力" not in registry.tags_for("male")["世界观"]

    def test_remove_builtin_tag_is_refused_with_reason(self, registry):
        res = registry.remove_tag("male", "世界观", BUILTIN_TAGS["male"]["世界观"][0])
        assert not res.ok and res.reason == "builtin"

    def test_emptying_a_custom_category_drops_it(self, registry):
        registry.add_tag("male", "临时分类", "唯一标签")
        registry.remove_tag("male", "临时分类", "唯一标签")
        assert "临时分类" not in registry.tags_for("male")


class TestConfigRobustness:
    """宽松读：配置坏了必须**降级**而不是抛 —— 题材选择不该让应用起不来。"""

    def test_missing_file_is_fine(self, tmp_path):
        r = GenreRegistry(config_file=tmp_path / "nope.json")
        assert len(r.genres_for("male")) == 78

    def test_corrupt_json_is_ignored(self, tmp_path):
        f = tmp_path / "genres.json"
        f.write_text("{ 这不是 json", encoding="utf-8")
        r = GenreRegistry(config_file=f)
        assert len(r.genres_for("male")) == 78

    def test_non_dict_toplevel_is_ignored(self, tmp_path):
        f = tmp_path / "genres.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        assert len(GenreRegistry(config_file=f).genres_for("male")) == 78

    def test_wrong_shapes_inside_are_skipped_but_good_kept(self, tmp_path):
        f = tmp_path / "genres.json"
        f.write_text(
            json.dumps(
                {
                    "custom_genres": {"male": ["好题材", "", "a/b", "x" * 99], "female": "不是列表"},
                    "custom_tags": {"male": {"分类": ["标签", None], "坏分类/b": ["x"]}},
                    "removed_genres": "不是字典",
                }
            ),
            encoding="utf-8",
        )
        r = GenreRegistry(config_file=f)
        assert "好题材" in r.genres_for("male")
        assert "" not in r.genres_for("male")
        assert r.custom_genres("female") == []
        assert r.tags_for("male")["分类"] == ["标签"]

    def test_load_never_raises_on_weird_types(self, tmp_path):
        f = tmp_path / "genres.json"
        f.write_text(json.dumps({"custom_genres": [1, 2], "custom_tags": [], "removed_genres": 5}), encoding="utf-8")
        GenreRegistry(config_file=f)  # 不抛即通过

    def test_reload_picks_up_external_edits(self, registry, tmp_path):
        f = tmp_path / "genres.json"
        f.write_text(json.dumps({"custom_genres": {"male": ["外部加的"]}}), encoding="utf-8")
        assert registry.reload().ok
        assert "外部加的" in registry.genres_for("male")

    def test_save_is_atomic_and_leaves_no_temp(self, registry, tmp_path):
        registry.add_genre("male", "蒸汽朋克")
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "genres.json"]
        assert leftovers == [], f"残留临时文件：{leftovers}"


class TestNovelCompatibility:
    """❗ 本轮最关键的一组：不能因为用户删了题材而**静默改掉已有作品的题材**。"""

    def test_novel_genre_is_appended_when_missing(self, registry):
        target = BUILTIN_GENRES["male"][0]
        registry.remove_genre("male", target)
        names = registry.with_novel_genre("male", target)
        assert target in names, "作品在用的题材必须仍可显示"

    def test_unknown_genre_is_appended(self, registry):
        """老作品可能用着早期版本的自定义题材，现在清单里已没有。"""
        names = registry.with_novel_genre("male", "某个早已删除的题材")
        assert "某个早已删除的题材" in names

    def test_empty_genre_does_not_add_blank_option(self, registry):
        names = registry.with_novel_genre("male", "")
        assert "" not in names
        assert len(names) == 78

    def test_existing_genre_is_not_duplicated(self, registry):
        target = BUILTIN_GENRES["male"][0]
        names = registry.with_novel_genre("male", target)
        assert names.count(target) == 1


class TestGlobalRegistry:
    def test_get_and_reset(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.genres._registry", None)
        monkeypatch.setattr("app.genres.default_genres_file", lambda: tmp_path / "genres.json")
        assert get_genre_registry() is not None
        reset_genre_registry()
        assert get_genre_registry() is not None

    def test_returns_none_on_construction_failure(self, monkeypatch):
        monkeypatch.setattr("app.genres._registry", None)

        def _boom(*_a, **_k):
            raise OSError("磁盘炸了")

        monkeypatch.setattr("app.genres.GenreRegistry", _boom)
        assert get_genre_registry() is None


# ====================================================================== 4. 🔴 结构守卫


class TestDataLivesInOnePlace:
    """数据只能有一处 —— 否则就是「同一事实写两处必然漂移」的第 6 次。"""

    def test_lifecycle_ui_no_longer_inlines_the_lists(self):
        code = _scan.code_only("app/lifecycle_ui.py")
        for name in ("MALE_GENRES", "FEMALE_GENRES", "MALE_TAGS", "FEMALE_TAGS"):
            assert name not in code, f"{name} 又回到 UI 文件里了 —— 应放进 genres_data.py"

    def test_lifecycle_ui_has_no_bulk_genre_literals(self):
        """UI 文件里**不应出现整批**内置题材。

        ❗ 这条判据必须允许少量字面量：`TEMPLATES`（内置故事模板）会写
        `{"genre": "玄幻-异世大陆"}` 这类**默认值** —— 那是模板的字段默认，
        不是题材目录。目录被内联的特征是"**成批**出现"（原状是 78 条全在），
        所以判据取一个明显低于目录规模的上界，而不是"一条都不能有"。

        用上界而不是精确值，是因为模板数量会变；用 10（远小于 78）
        既能在目录被搬回来时立刻变红，又不会因为加了模板而误报。
        """
        code = _scan.code_only("app/lifecycle_ui.py")
        leaked = [g for g in BUILTIN_GENRES["male"] if g in code]
        assert len(leaked) < 10, (
            f"UI 文件里出现 {len(leaked)} 条内置题材字面量（目录规模 78）—— 疑似把题材目录搬回 UI 了：{leaked[:8]}"
        )

    def test_lifecycle_ui_has_no_bulk_tag_literals(self):
        """UI 文件里不应出现整批内置标签。

        ❗ 判据同样是**上界**而非"一条都不许"：实测 `系统流` 会命中 ——
        它既是标签目录里的一项，**也是** `TEMPLATES` 里的一个模板名
        （`"系统流": {"tags": ["系统流", "升级"]}`）。这种同名是巧合，
        不是"标签目录被内联"的证据。目录被内联的特征是**成批**出现
        （原状 100 条全在），所以用一个远低于目录规模的上界即可。
        """
        code = _scan.code_only("app/lifecycle_ui.py")
        leaked = [t for tags in BUILTIN_TAGS["male"].values() for t in tags if t in code]
        assert len(leaked) < 5, (
            f"UI 文件里出现 {len(leaked)} 条内置标签字面量（目录规模 100）—— 疑似把标签目录搬回 UI 了：{leaked[:8]}"
        )

    def test_ui_reads_the_registry(self):
        code = _scan.code_only("app/lifecycle_ui.py")
        assert "get_genre_registry" in code, "UI 没有从注册表读题材"

    def test_registry_consumes_the_data_module(self):
        code = _scan.code_only("app/genres.py")
        assert "BUILTIN_GENRES" in code and "BUILTIN_TAGS" in code
        assert "genres_data" in code

    def test_data_module_is_pure_data(self):
        """`genres_data.py` 只应有数据，不该有逻辑（否则又变成两处逻辑）。"""
        code = _scan.code_only("app/genres_data.py")
        assert "def " not in code, "genres_data.py 里出现了函数定义"
        assert "class " not in code, "genres_data.py 里出现了类定义"

    def test_single_config_path_source(self):
        """配置文件路径只允许出现在 `genres.py`。"""
        offenders = []
        for path in sorted((REPO_ROOT / "app").rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel == "app/genres.py":
                continue
            code = _scan.code_only(rel)
            if "genres.json" in code:
                offenders.append(rel)
        assert not offenders, f"这些文件自己拼了题材配置路径：{offenders}"


class TestWiringGuard:
    """双向：正向查调用点 + 反向断言被调者仍存在。"""

    def test_manage_genres_is_reachable_from_ui(self):
        code = _scan.code_only("app/lifecycle_ui.py")
        assert "_open_genre_manager" in code
        assert "genre_manage_btn" in code, "管理题材按钮不见了"
        assert "on_manage_genres" in code

    def test_manage_button_gets_a_command(self):
        """❗ 建了按钮却不 `config(command=...)` ⇒ 点了没反应（静默失效）。"""
        code = _scan.code_only("app/lifecycle_ui.py")
        assert "genre_manage_btn.config(command=" in code

    def test_registry_methods_still_exist(self):
        for name in (
            "genres_for",
            "custom_genres",
            "removed_genres",
            "add_genre",
            "remove_genre",
            "add_tag",
            "remove_tag",
            "add_genre_batch",
            "with_novel_genre",
            "tags_for",
            "categories_for",
            "stats",
            "save",
            "reload",
        ):
            assert hasattr(GenreRegistry, name), f"GenreRegistry.{name} 不见了"

    def test_ui_degrades_when_registry_unavailable(self):
        """注册表为 None 时必须能继续（界面可用，只是没得选），不能崩。"""
        code = _scan.code_only("app/lifecycle_ui.py")
        assert "registry is None" in code or "reg is None" in code


# ====================================================================== 5. 真 Tk


def _tk_available() -> bool:
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - 无显示环境
        return False


def _find_widgets(root, cls_name: str) -> list:
    """递归找指定类名的控件（Tk 没有现成的按类型查找）。"""
    found = []
    for child in root.winfo_children():
        if child.winfo_class() == cls_name:
            found.append(child)
        found.extend(_find_widgets(child, cls_name))
    return found


@pytest.mark.skipif(not _tk_available(), reason="无显示环境")
class TestNewNovelDialogTk:
    def _open(self, tmp_path, monkeypatch):
        import tkinter as tk

        from app.lifecycle_ui import NovelLifecycleMixin

        monkeypatch.setattr("app.genres._registry", None)
        monkeypatch.setattr("app.genres.default_genres_file", lambda: tmp_path / "genres.json")

        class Fake:
            def __init__(self):
                self.root = tk.Tk()
                self.root.withdraw()
                self.logs = []

            def _log(self, msg):
                self.logs.append(str(msg))

        fake = Fake()
        fake._new_novel = NovelLifecycleMixin._new_novel.__get__(fake)
        fake._open_genre_manager = NovelLifecycleMixin._open_genre_manager.__get__(fake)
        fake._new_novel()
        return fake

    def test_dialog_builds_and_combo_is_populated_from_registry(self, tmp_path, monkeypatch):
        fake = self._open(tmp_path, monkeypatch)
        try:
            toplevels = [w for w in fake.root.winfo_children() if w.winfo_class() == "Toplevel"]
            assert toplevels, "新建小说对话框没建出来"
            combos = _find_widgets(toplevels[0], "TCombobox")
            assert combos, "题材下拉框没建出来"
            # 找到题材那个（值最多的是题材框）
            widest = max(combos, key=lambda c: len(c.cget("values")))
            assert len(widest.cget("values")) == 78, "题材下拉没有从注册表填充"
        finally:
            fake.root.destroy()

    def test_custom_genre_appears_in_combo(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.genres._registry", None)
        import tkinter as tk

        from app.genres import GenreRegistry
        from app.lifecycle_ui import NovelLifecycleMixin

        cfg = tmp_path / "genres.json"
        GenreRegistry(config_file=cfg).add_genre("male", "蒸汽朋克")
        monkeypatch.setattr("app.genres.default_genres_file", lambda: cfg)

        class Fake:
            def __init__(self):
                self.root = tk.Tk()
                self.root.withdraw()

            def _log(self, msg):
                pass

        fake = Fake()
        fake._new_novel = NovelLifecycleMixin._new_novel.__get__(fake)
        fake._open_genre_manager = NovelLifecycleMixin._open_genre_manager.__get__(fake)
        fake._new_novel()
        try:
            toplevels = [w for w in fake.root.winfo_children() if w.winfo_class() == "Toplevel"]
            combos = _find_widgets(toplevels[0], "TCombobox")
            widest = max(combos, key=lambda c: len(c.cget("values")))
            assert "蒸汽朋克" in widest.cget("values")
            assert len(widest.cget("values")) == 79
        finally:
            fake.root.destroy()
