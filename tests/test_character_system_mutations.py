"""`character_system` 的删除 / 重命名 / 重载 / 自定义装备（档 1：角色数据）。

## 为什么这几个函数值得单独测

它们都直接改**角色数据本身**，错法全是"看起来成功、实际丢东西"：

| 函数 | 错法 |
|---|---|
| `delete_character` | 删了内存条目但文件还在（下次启动角色"复活"） |
| `rename_character` | 先删旧文件再写新文件，中途失败 ⇒ **两边都没了** |
| `reload_character` | 文件坏了就抛 ⇒ 切个角色把面板搞崩 |
| `_load_custom` / `_save_custom` | 非原子写 ⇒ 自定义武器技能整批静默消失 |

`rename_character` 的注释里写着"旧实现是先后删旧文件"导致的 R5 事故 ——
现在的顺序是"内存改名 → 写新文件 → 删旧文件 → 失败回滚"，
用例要钉的正是这个顺序保证：**任何一步失败，磁盘上至少有一份完整数据**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import character_system as cs


@pytest.fixture
def system(tmp_path, monkeypatch):
    """注意 `characters/` 目录要先建 —— 构造时会扫它，缺目录直接 FileNotFoundError。"""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    book = tmp_path / "book"
    (book / "characters").mkdir(parents=True)
    return cs.CharacterSystem(novel_dir=book)


def _seed(system, name: str = "林风", **fields) -> None:
    profile = cs.CharacterProfile(name=name)
    for key, value in fields.items():
        setattr(profile, key, value)
    system.characters[name] = profile
    system.save_character(name)


class TestDeleteCharacter:
    def test_unknown_returns_false(self, system):
        assert system.delete_character("不存在") is False

    def test_removes_memory_and_file(self, system):
        _seed(system)

        assert system.delete_character("林风") is True
        assert "林风" not in system.characters
        assert not (system.save_dir / "林风.json").exists(), "内存删了但文件还在（下次启动会复活）"

    def test_active_switches_to_first_remaining(self, system):
        _seed(system, "甲")
        _seed(system, "乙")
        system.active_name = "甲"

        system.delete_character("甲")

        assert system.active_name == "乙"

    def test_active_becomes_none_when_empty(self, system):
        _seed(system)
        system.active_name = "林风"

        system.delete_character("林风")

        assert system.active_name is None

    def test_deleting_inactive_keeps_active(self, system):
        _seed(system, "甲")
        _seed(system, "乙")
        system.active_name = "乙"

        system.delete_character("甲")

        assert system.active_name == "乙"


class TestRenameCharacter:
    def test_unknown_old_returns_false(self, system):
        assert system.rename_character("不存在", "新名") is False

    def test_conflict_with_existing_returns_false(self, system):
        _seed(system, "甲")
        _seed(system, "乙")

        assert system.rename_character("甲", "乙") is False
        assert "甲" in system.characters

    def test_normal_rename_moves_memory_and_file(self, system):
        _seed(system, "旧名")

        assert system.rename_character("旧名", "新名") is True
        assert "新名" in system.characters
        assert "旧名" not in system.characters
        assert (system.save_dir / "新名.json").exists()
        assert not (system.save_dir / "旧名.json").exists(), "旧文件没删，启动时会读出一个重影角色"

    def test_active_follows_rename(self, system):
        _seed(system, "旧名")
        system.active_name = "旧名"

        system.rename_character("旧名", "新名")

        assert system.active_name == "新名"

    def test_write_failure_rolls_back_memory(self, system, monkeypatch):
        """🔴 写新文件失败时必须**回滚内存态** —— 保证内存与磁盘一致，不丢数据。"""
        _seed(system, "旧名")

        def boom(*_a, **_kw):
            raise OSError("磁盘满")

        monkeypatch.setattr(system, "save_character", boom)

        result = system.rename_character("旧名", "新名")

        assert result is False
        assert "旧名" in system.characters, "内存里改成了新名，但磁盘上没有（数据分裂）"
        assert "新名" not in system.characters
        assert (system.save_dir / "旧名.json").exists(), "旧文件被删了 —— 两边都没了"

    def test_active_restored_on_failure(self, system, monkeypatch):
        _seed(system, "旧名")
        system.active_name = "旧名"
        monkeypatch.setattr(system, "save_character", lambda *a, **kw: (_ for _ in ()).throw(OSError("满")))

        system.rename_character("旧名", "新名")

        assert system.active_name == "旧名"

    def test_old_file_delete_failure_is_tolerated(self, system, monkeypatch):
        """旧文件删不掉只影响整洁，不影响正确性 —— 不能因此报失败。"""
        _seed(system, "旧名")
        real_unlink = Path.unlink

        def boom(self, *a, **kw):
            if "旧名" in str(self):
                raise OSError("占用")
            return real_unlink(self, *a, **kw)

        monkeypatch.setattr(Path, "unlink", boom)

        assert system.rename_character("旧名", "新名") is True
        assert "新名" in system.characters


class TestReloadCharacter:
    def test_no_dir_or_name(self):
        assert cs.CharacterSystem(novel_dir=None).reload_character("甲") is False

    def test_missing_file_keeps_memory(self, system):
        _seed(system, "甲")
        (system.save_dir / "甲.json").unlink()

        assert system.reload_character("甲") is False
        assert "甲" in system.characters, "文件没了就把角色从列表里删掉（应沿用旧数据）"

    def test_corrupt_file_keeps_memory(self, system):
        _seed(system, "甲")
        (system.save_dir / "甲.json").write_text("{ 坏", encoding="utf-8")

        assert system.reload_character("甲") is False
        assert "甲" in system.characters

    def test_non_object_file_keeps_memory(self, system):
        _seed(system, "甲")
        (system.save_dir / "甲.json").write_text("[]", encoding="utf-8")

        assert system.reload_character("甲") is False

    def test_success_refreshes_from_disk(self, system):
        _seed(system, "甲", category="配角")
        (system.save_dir / "甲.json").write_text(
            json.dumps({"name": "甲", "category": "主角"}, ensure_ascii=False), encoding="utf-8"
        )

        assert system.reload_character("甲") is True
        assert system.characters["甲"].category == "主角"

    def test_unsanitizable_name_returns_false(self, system, monkeypatch):
        monkeypatch.setattr(system, "_sanitize_name", lambda _n: (_ for _ in ()).throw(ValueError("非法")))

        assert system.reload_character("../逃逸") is False


class TestCustomEquipment:
    def test_missing_file_is_empty(self, system):
        assert system.custom_weapons == []
        assert system.custom_skills == []

    def test_corrupt_file_is_logged_and_skipped(self, system):
        """损坏时跳过但**不覆盖** —— 用户还有手工修复的机会。"""
        system.custom_file.parent.mkdir(parents=True, exist_ok=True)
        system.custom_file.write_text("{ 坏", encoding="utf-8")

        system._load_custom()

        assert system.custom_weapons == []
        assert system.custom_file.read_text(encoding="utf-8") == "{ 坏", "损坏文件被覆盖了"

    def test_roundtrip(self, system):
        system.add_custom_weapon("黑剑", "剑", "史诗", "来历不明", {"attack": 88})
        system.add_custom_skill("剑气", "攻击", "挥出一道剑气", mp_cost=30)

        fresh = cs.CharacterSystem(novel_dir=system.novel_dir)

        assert any(w["name"] == "黑剑" for w in fresh.custom_weapons)
        assert any(s["name"] == "剑气" for s in fresh.custom_skills)

    def test_delete_by_index(self, system):
        system.add_custom_weapon("甲", "剑", "普通", "", {})
        system.add_custom_weapon("乙", "刀", "普通", "", {})

        assert system.delete_custom_weapon(0) is True
        assert [w["name"] for w in system.custom_weapons] == ["乙"]

    @pytest.mark.parametrize("index", [-1, 5, 99])
    def test_delete_out_of_range(self, system, index):
        system.add_custom_weapon("甲", "剑", "普通", "", {})

        assert system.delete_custom_weapon(index) is False
        assert len(system.custom_weapons) == 1

    def test_skill_delete_out_of_range(self, system):
        assert system.delete_custom_skill(0) is False

    def test_custom_weapon_appears_in_category(self, system):
        system.add_custom_weapon("黑剑", "自定义类别", "史诗", "", {})

        assert "自定义类别" in system.get_weapon_categories()
        assert [w["name"] for w in system.get_weapons("自定义类别")] == ["黑剑"]

    def test_custom_skill_appears_in_category(self, system):
        system.add_custom_skill("剑气", "自定义类型", "描述")

        assert "自定义类型" in system.get_skill_categories()
        assert [s["name"] for s in system.get_skills("自定义类型")] == ["剑气"]

    def test_builtin_library_not_polluted(self, system):
        """`get_weapons` 返回的是**浅拷贝** —— 调用方改动不能污染内置库。"""
        category = next(iter(system.weapon_library))
        original_len = len(system.weapon_library[category])

        weapons = system.get_weapons(category)
        weapons.append({"name": "偷偷加的"})

        assert len(system.weapon_library[category]) == original_len


class TestStatusChanges:
    def test_mark_death_unknown(self, system):
        assert system.mark_death("不存在", 10) is False

    def test_mark_death_sets_fields(self, system):
        _seed(system, "甲")

        assert system.mark_death("甲", 12) is True
        assert system.characters["甲"].status == "死亡"
        assert system.characters["甲"].death_chapter == 12

    def test_mark_revival_unknown(self, system):
        assert system.mark_revival("不存在", 20) is False

    def test_mark_revival_sets_fields(self, system):
        _seed(system, "甲")
        system.mark_death("甲", 12)

        assert system.mark_revival("甲", 20) is True
        assert system.characters["甲"].status == "存活"
        assert system.characters["甲"].revival_chapter == 20

    def test_death_does_not_delete_character(self, system):
        """🔴 `apply_death_status` 绝不删角色 —— 死了也要能查到。"""
        _seed(system, "甲")

        system.mark_death("甲", 12)

        assert "甲" in system.characters


class TestCategoryQueries:
    def test_by_category(self, system):
        _seed(system, "甲", category="主角")
        _seed(system, "乙", category="配角")

        assert system.get_characters_by_category("主角") == ["甲"]

    def test_by_faction(self, system):
        _seed(system, "甲", faction="青云宗")
        _seed(system, "乙", faction="血月教")

        assert system.get_characters_by_faction("青云宗") == ["甲"]

    def test_unknown_category_returns_empty(self, system):
        assert system.get_characters_by_category("没有这个分类") == []


class TestLegacyMigration:
    """旧版单文件 `character_profile.json` 的迁移。

    它的硬要求是「**一律不删除**，改为改名归档」——
    旧实现把 `unlink()` 放在 if 同级，名字已存在时旧文件**没被读就被删**，
    用户失去最后一次人工比对机会，且不可逆（L6 事故）。
    """

    @staticmethod
    def _legacy(book: Path, name: str = "老主角") -> Path:
        path = book / "character_profile.json"
        path.write_text(json.dumps({"name": name, "category": "主角"}, ensure_ascii=False), encoding="utf-8")
        return path

    def _load(self, book: Path):
        return cs.CharacterSystem(novel_dir=book)

    def test_imports_and_archives(self, tmp_path):
        book = tmp_path / "book"
        (book / "characters").mkdir(parents=True)
        legacy = self._legacy(book)

        system = self._load(book)

        assert "老主角" in system.characters
        assert not legacy.exists(), "旧文件还在原位置（迁移没生效）"
        archived = book / "character_profile.json.migrated"
        assert archived.exists(), "旧文件被删了而不是归档"
        assert json.loads(archived.read_text(encoding="utf-8"))["name"] == "老主角"

    def test_existing_name_is_not_duplicated_but_file_kept(self, tmp_path):
        """名字已在库中 ⇒ 不重复导入，但**旧文件仍要归档保留**。"""
        book = tmp_path / "book"
        (book / "characters").mkdir(parents=True)
        self._legacy(book, "老主角")
        (book / "characters" / "老主角.json").write_text(
            json.dumps({"name": "老主角", "category": "配角"}, ensure_ascii=False), encoding="utf-8"
        )

        system = self._load(book)

        assert system.characters["老主角"].category == "配角", "旧文件覆盖了库里已有的角色"
        assert (book / "character_profile.json.migrated").exists()

    def test_second_migration_uses_timestamp(self, tmp_path):
        """已存在 `.migrated` 时再迁移要加时间戳，不能覆盖上一份归档。"""
        book = tmp_path / "book"
        (book / "characters").mkdir(parents=True)
        (book / "character_profile.json.migrated").write_text("旧归档", encoding="utf-8")
        self._legacy(book)

        self._load(book)

        archives = list(book.glob("character_profile.json.migrated*"))
        assert len(archives) >= 2, "第二次迁移把上一份归档覆盖了"
        assert (book / "character_profile.json.migrated").read_text(encoding="utf-8") == "旧归档"

    def test_corrupt_legacy_kept_in_place(self, tmp_path):
        """旧文件坏掉 ⇒ 原样保留并记日志，不能删（用户可能手工修）。"""
        book = tmp_path / "book"
        (book / "characters").mkdir(parents=True)
        legacy = book / "character_profile.json"
        legacy.write_text("{ 坏", encoding="utf-8")

        self._load(book)

        assert legacy.exists(), "损坏的旧文件被删了"


class TestAliveQueries:
    def test_alive_and_dead_split(self, system):
        _seed(system, "活的")
        _seed(system, "死的")
        system.mark_death("死的", 5)

        assert system.get_alive_characters() == ["活的"]
        assert system.get_dead_characters() == ["死的"]

    def test_revival_moves_back(self, system):
        _seed(system, "甲")
        system.mark_death("甲", 5)
        system.mark_revival("甲", 8)

        assert system.get_alive_characters() == ["甲"]
        assert system.get_dead_characters() == []


class TestPromoteMinor:
    def test_no_minor_returns_none(self, system):
        _seed(system, "主角甲", category="主角")

        assert system.random_promote_minor(1) is None

    def test_dead_minor_not_promoted(self, system):
        _seed(system, "龙套", category="无名小卒")
        system.mark_death("龙套", 3)

        assert system.random_promote_minor(4) is None

    def test_promotes_to_key_character(self, system):
        _seed(system, "龙套", category="无名小卒")

        name = system.random_promote_minor(4)

        assert name == "龙套"
        assert system.characters["龙套"].category == "关键人物"
        assert system.characters["龙套"].faction in ("主角阵营", "敌对阵营", "中立")
