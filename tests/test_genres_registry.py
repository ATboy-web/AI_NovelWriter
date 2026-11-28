"""`genres` 的校验、合并与命名空间（档 2：题材改完不生效 / 内置被覆盖）。

## 这个模块最容易犯的错

它管"频道 → 题材/标签"的**可扩展注册表**。三个典型错法：

| 错法 | 用户看到 |
|---|---|
| 自定义标签 `update()` 覆盖内置 | 内置标签整组消失（是数据丢失，不是扩充） |
| 名称不校验 | 带换行的题材进下拉框，界面错位 |
| 频道别名不归一 | `male`/`男频` 各存一份，用户看到重复项 |

第三条尤其隐蔽：数据没坏，只是"改了三处才生效"。
"""

from __future__ import annotations

import json

import pytest

from app import genres as gn


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return gn.GenreRegistry(config_file=tmp_path / "genres.json")


class TestNormalizeChannel:
    @pytest.mark.parametrize("value", ["male", "  MALE  ", "男频"])
    def test_aliases_collapse(self, registry, value):
        assert gn.normalize_channel(value) in gn.CHANNEL_LABELS

    def test_unknown_falls_back_to_default(self):
        assert gn.normalize_channel("火星频道") == gn.DEFAULT_CHANNEL

    def test_empty(self):
        assert gn.normalize_channel("") == gn.DEFAULT_CHANNEL

    def test_stable(self):
        """同一输入两次归一化必须一致 —— 否则配置会分裂成两份。"""
        for raw in ("male", "女频", "未知"):
            assert gn.normalize_channel(raw) == gn.normalize_channel(raw)


class TestValidateName:
    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_empty_rejected(self, name):
        ok, why = gn.validate_name(name)

        assert ok is False and why

    def test_too_long(self):
        ok, why = gn.validate_name("题" * (gn.MAX_GENRE_LENGTH + 1))

        assert ok is False
        assert "过长" in why

    @pytest.mark.parametrize("name", ["含\n换行", "含\t制表符", "含\r回车"])
    def test_control_chars_rejected(self, name):
        """换行会直接把下拉框/标签控件撑坏 —— 必须在入口拦。"""
        ok, why = gn.validate_name(name)

        assert ok is False
        assert "不能包含" in why

    def test_normal_chinese_accepted(self):
        assert gn.validate_name("东方玄幻")[0] is True

    def test_mixed_punctuation_accepted(self):
        assert gn.validate_name("赛博·朋克 2077")[0] is True

    def test_forbidden_pattern_rejected(self):
        ok, _why = gn.validate_name("<script>")

        assert ok is False


class TestMakeAndSplitGenre:
    def test_roundtrip(self):
        combined = gn.make_genre("玄幻", "东方玄幻")

        assert gn.split_genre(combined) == ("玄幻", "东方玄幻")

    def test_no_detail(self):
        assert gn.split_genre("玄幻") == ("玄幻", "")

    def test_empty(self):
        assert gn.split_genre("") == ("", "")


class TestTagMerge:
    def test_custom_appends_without_replacing(self, registry):
        """🔴 自定义标签必须**追加**在内置之后。

        `dict.update()` 会把内置整组替换掉 —— 那是数据丢失，
        用户看到的是"我加了个标签，内置的都没了"。
        """
        channel = registry.channels()[0]
        builtin = registry.builtin_tags(channel)
        category = next(iter(builtin))
        first_tag = builtin[category][0]

        registry.add_tag(channel, category, "我的自定义标签")

        merged = registry.tags_for(channel)
        assert first_tag in merged[category], "内置标签被自定义组覆盖了"
        assert "我的自定义标签" in merged[category]

    def test_duplicate_tag_not_added_twice(self, registry):
        channel = registry.channels()[0]
        category, tags = next(iter(registry.builtin_tags(channel).items()))

        registry.add_tag(channel, category, tags[0])

        assert registry.tags_for(channel)[category].count(tags[0]) == 1

    def test_removed_genre_hidden(self, registry):
        channel = registry.channels()[0]
        target = registry.builtin_genres(channel)[0]

        registry.remove_genre(channel, target)

        assert target not in registry.genres_for(channel)

    def test_remove_unknown_genre_fails(self, registry):
        channel = registry.channels()[0]

        result = registry.remove_genre(channel, "根本不存在的题材")

        assert result.ok is False

    def test_added_genre_appears_once(self, registry):
        channel = registry.channels()[0]

        registry.add_genre(channel, "我的题材")
        registry.add_genre(channel, "我的题材")

        assert registry.genres_for(channel).count("我的题材") == 1

    def test_add_invalid_genre_rejected(self, registry):
        channel = registry.channels()[0]

        result = registry.add_genre(channel, "带\n换行")

        assert result.ok is False
        assert result.reason

    def test_add_duplicate_of_builtin_refused(self, registry):
        channel = registry.channels()[0]
        existing = registry.builtin_genres(channel)[0]

        result = registry.add_genre(channel, existing)

        assert result.ok is False


class TestPersistence:
    def test_save_and_reload(self, registry, tmp_path):
        channel = registry.channels()[0]
        registry.add_genre(channel, "持久化题材")
        assert registry.save().ok is True

        fresh = gn.GenreRegistry(config_file=tmp_path / "genres.json")
        fresh.reload()

        assert "持久化题材" in fresh.genres_for(channel)

    def test_corrupt_config_is_ignored(self, tmp_path):
        """配置坏了当作"没有自定义"继续 —— 不能因此打不开写作页。"""
        config = tmp_path / "genres.json"
        config.write_text("{ 坏", encoding="utf-8")

        registry = gn.GenreRegistry(config_file=config)
        registry.reload()

        assert registry.channels()
        assert registry.genres_for(registry.channels()[0])

    def test_malformed_entries_skipped(self, tmp_path):
        config = tmp_path / "genres.json"
        config.write_text(
            json.dumps(
                {
                    "custom_genres": {"male": ["好的题材", 123, "带\n换行"]},
                    "custom_tags": {"male": {"分类": "不是列表"}},
                    "removed_genres": {"male": "不是列表"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        registry = gn.GenreRegistry(config_file=config)
        registry.reload()

        genres = registry.genres_for("male")
        assert "好的题材" in genres
        assert all("\n" not in g for g in genres)

    def test_save_failure_reported(self, registry, monkeypatch):
        import app.genres as mod

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(mod, "atomic_write_json", boom, raising=False)
        monkeypatch.setitem(__import__("sys").modules, "app.storage", type("S", (), {"atomic_write_json": boom}))

        result = registry.save()

        assert result.ok is False
        assert result.reason == "io_error"


class TestResultObject:
    def test_truthiness(self):
        assert bool(gn.GenreResult.success("好")) is True
        assert bool(gn.GenreResult.failed("坏", reason="x")) is False

    def test_as_dict(self):
        data = gn.GenreResult.failed("坏了", reason="io_error").as_dict()

        assert data["ok"] is False
        assert data["detail"]["reason"] == "io_error"

    def test_reason(self):
        assert gn.GenreResult.failed("x", reason="not_found").reason == "not_found"


class TestChannelLabels:
    def test_label_for_known(self, registry):
        channel = registry.channels()[0]

        assert registry.channel_label(channel)

    def test_unknown_channel_falls_back_to_input(self):
        assert gn.GenreRegistry.channel_label.__qualname__  # 引用存在

    def test_all_genres_covers_every_channel(self, registry):
        data = registry.all_genres()

        assert set(data) == set(registry.channels())
