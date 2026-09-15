"""角色数据完整性回归测试（第二轮优化新增）。

背景：角色条目是小说内容资产 —— 线上真实作品实测包含 **286 个角色**、
1094 章。本轮优化前存在 4 条真实的数据丢失路径（详见
docs/OPTIMIZATION_ROUND2.md R1–R6），本文件把它们全部固化为回归测试：

- R1 角色生成整体覆盖既有角色集（最危险：一次"重新生成角色"即清空整库）
- R2 写入非原子（写一半被截断）
- R3 读损坏后可能级联成空覆盖
- R4 读-改-写无锁导致丢失更新
- R5 重命名先删后写，中途失败丢角色
- R6 损坏的角色文件被静默跳过

外加一项**用户约束**的源码级断言：角色详情面板不得提供删除入口。
"""

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.character_system import CharacterProfile, CharacterSystem
from app.memory_manager import (
    CharacterDataCorruptError,
    CharacterDataGuardError,
    MemoryManager,
)

REPO_ROOT = Path(__file__).parent.parent
# 线上真实作品的规模，用于构造"大角色库"场景
REAL_WORLD_CHARACTER_COUNT = 286


def make_characters(n: int, prefix: str = "角色") -> dict:
    return {
        f"{prefix}{i:03d}": {"personality": f"性格{i}", "category": "配角", "faction": "中立"}
        for i in range(n)
    }


@pytest.fixture
def mm(tmp_path):
    return MemoryManager(tmp_path)


# ---------------------------------------------------------------- R2/R3 写入侧


class TestCharactersWriteSafety:
    def test_empty_overwrite_is_refused(self, mm):
        """以空集合覆盖既有角色必须被拒绝，且磁盘内容原样保留（R3）。"""
        original = make_characters(REAL_WORLD_CHARACTER_COUNT)
        mm.save_characters(original)

        with pytest.raises(CharacterDataGuardError):
            mm.save_characters({})

        assert len(mm.get_characters()) == REAL_WORLD_CHARACTER_COUNT
        assert set(mm.get_characters()) == set(original)

    def test_empty_overwrite_can_be_forced_explicitly(self, mm):
        mm.save_characters(make_characters(5))
        mm.save_characters({}, allow_empty=True)
        assert mm.get_characters() == {}

    def test_first_write_of_empty_set_is_allowed(self, mm):
        """从未有过角色时写空集是合法的（不存在"被删掉的角色"）。"""
        mm.save_characters({})
        assert mm.get_characters() == {}

    def test_corrupt_file_blocks_empty_overwrite_and_archives(self, mm):
        """文件损坏时拒绝空覆盖，并把损坏文件留档（R3）。"""
        chars_file = mm.characters_file
        chars_file.write_text('{"角色000": {"personality": "截断', encoding="utf-8")

        with pytest.raises(CharacterDataGuardError):
            mm.save_characters({})

        archives = list(chars_file.parent.glob("characters.corrupt-*.json"))
        assert len(archives) == 1
        assert "角色000" in archives[0].read_text(encoding="utf-8")

    def test_save_is_atomic_and_keeps_backup(self, mm):
        mm.save_characters({"甲": {"personality": "1"}})
        mm.save_characters({"甲": {"personality": "1"}, "乙": {"personality": "2"}})

        assert len(mm.get_characters()) == 2
        backup = mm.characters_file.with_name(mm.characters_file.name + ".bak")
        assert backup.exists()
        assert json.loads(backup.read_text(encoding="utf-8")) == {"甲": {"personality": "1"}}
        assert [p.name for p in mm.characters_file.parent.iterdir() if p.name.endswith(".tmp")] == []

    def test_no_disk_write_when_guard_trips(self, mm):
        """守卫触发时不得留下任何半成品或备份污染。"""
        mm.save_characters(make_characters(3))
        before = mm.characters_file.read_bytes()
        with pytest.raises(CharacterDataGuardError):
            mm.save_characters({})
        assert mm.characters_file.read_bytes() == before


class TestCharactersReadSafety:
    def test_corrupt_primary_falls_back_to_backup(self, mm):
        mm.save_characters(make_characters(10, "旧"))
        mm.save_characters(make_characters(12, "新"), )  # 生成 .bak = 10 个"旧"

        mm.characters_file.write_text("{截断", encoding="utf-8")
        chars = mm.get_characters()
        assert len(chars) == 10
        assert all(name.startswith("旧") for name in chars)

    def test_corrupt_without_backup_returns_empty_but_flags(self, mm):
        mm.characters_file.write_text("彻底不是 JSON", encoding="utf-8")
        assert mm.get_characters() == {}
        assert mm._characters_corrupt is True

    def test_corrupt_without_backup_can_raise(self, mm):
        mm.characters_file.write_text("彻底不是 JSON", encoding="utf-8")
        with pytest.raises(CharacterDataCorruptError):
            mm.get_characters(raise_on_corrupt=True)

    def test_missing_file_is_not_corrupt(self, mm):
        assert mm.get_characters() == {}
        assert mm._characters_corrupt is False


# ------------------------------------------------------------------- R4 并发


class TestConcurrentMutation:
    def test_mutate_characters_has_no_lost_update(self, mm):
        """20 个线程各自新增一个角色，最终必须 20 个都在（R4）。

        旧实现是"读全量 → 改 → 写全量"，无锁，必然丢更新。
        """
        mm.save_characters(make_characters(REAL_WORLD_CHARACTER_COUNT))
        added = 20
        barrier = threading.Barrier(added)
        errors = []

        def worker(idx):
            def mutate(chars):
                chars[f"新增{idx:02d}"] = {"personality": "并发写入"}
            try:
                barrier.wait(timeout=10)
                mm.mutate_characters(mutate)
            except Exception as e:  # pragma: no cover - 失败时提供诊断
                errors.append(repr(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(added)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        chars = mm.get_characters()
        assert len(chars) == REAL_WORLD_CHARACTER_COUNT + added
        for i in range(added):
            assert f"新增{i:02d}" in chars

    def test_update_character_merges_and_preserves_others(self, mm):
        mm.save_characters(make_characters(REAL_WORLD_CHARACTER_COUNT))
        mm.update_character("角色001", {"age": 20})

        chars = mm.get_characters()
        assert len(chars) == REAL_WORLD_CHARACTER_COUNT
        assert chars["角色001"]["age"] == 20
        assert chars["角色001"]["personality"] == "性格1"  # 原有字段保留
        assert "角色000" in chars and "角色285" in chars

    def test_mutate_returns_and_persists(self, mm):
        mm.save_characters({"甲": {}})

        def mutate(chars):
            chars["乙"] = {"personality": "x"}
            return chars

        result = mm.mutate_characters(mutate)
        assert set(result) == {"甲", "乙"}
        assert set(mm.get_characters()) == {"甲", "乙"}


# ------------------------------------------------------- R1 角色生成不得覆盖


class TestGenerateCharactersMerges:
    """`NovelAgent.generate_characters` 必须与既有角色取并集（R1）。"""

    @staticmethod
    def _agent(memory, payload: dict):
        from app.novel_agent import NovelAgent

        ai = MagicMock()
        ai.chat.return_value = json.dumps(payload, ensure_ascii=False)
        ai.is_configured.return_value = True
        return NovelAgent(ai, memory)

    def test_existing_characters_survive_regeneration(self, mm):
        existing = make_characters(REAL_WORLD_CHARACTER_COUNT)
        mm.save_characters(existing)

        new_batch = {
            "新角色A": {"personality": "新", "category": "关键人物"},
            "新角色B": {"personality": "新", "category": "配角"},
        }
        agent = self._agent(mm, new_batch)
        agent.generate_characters("科幻", "测试书名", count=2)

        chars = mm.get_characters()
        # 既有的 286 个必须一个不少
        assert set(existing).issubset(set(chars)), (
            f"角色生成覆盖了既有角色，丢失 {sorted(set(existing) - set(chars))[:5]} ..."
        )
        # 新批次也要写进去
        assert "新角色A" in chars and "新角色B" in chars
        assert len(chars) == REAL_WORLD_CHARACTER_COUNT + 2

    def test_same_name_character_fields_are_merged_not_dropped(self, mm):
        mm.save_characters({"林风": {"personality": "沉稳", "age": 20}})

        agent = self._agent(mm, {"林风": {"weapon": {"name": "青锋剑"}}})
        agent.generate_characters("仙侠", "测试书名", count=1)

        info = mm.get_characters()["林风"]
        assert info["weapon"] == {"name": "青锋剑"}  # 新数据并入
        assert info["personality"] == "沉稳"          # 既有字段不丢
        assert info["age"] == 20


# ------------------------------------------------- R5/R6 CharacterSystem 侧


class TestCharacterSystemSafety:
    def test_rename_keeps_data_when_write_fails(self, tmp_path, monkeypatch):
        """重命名写盘失败时必须回滚，且旧文件仍在（R5）。"""
        cs = CharacterSystem(tmp_path)
        cs.create_character("甲")
        cs.create_character("乙")
        old_file = tmp_path / "characters" / "甲.json"
        assert old_file.exists()

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(cs, "save_character", boom)
        assert cs.rename_character("甲", "丙") is False

        assert "甲" in cs.characters and "丙" not in cs.characters
        assert old_file.exists()
        assert "乙" in cs.characters

    def test_rename_moves_file_and_updates_active(self, tmp_path):
        cs = CharacterSystem(tmp_path)
        cs.create_character("甲")
        cs.set_active("甲")

        assert cs.rename_character("甲", "丙") is True

        assert cs.active_name == "丙"
        assert "丙" in cs.characters and "甲" not in cs.characters
        assert (tmp_path / "characters" / "丙.json").exists()
        assert not (tmp_path / "characters" / "甲.json").exists()
        assert CharacterSystem(tmp_path).get_character("丙") is not None

    def test_rename_rejects_existing_name(self, tmp_path):
        cs = CharacterSystem(tmp_path)
        cs.create_character("甲")
        cs.create_character("乙")
        assert cs.rename_character("甲", "乙") is False
        assert "甲" in cs.characters and "乙" in cs.characters

    def test_corrupt_file_is_reported_not_silently_dropped(self, tmp_path, caplog):
        """损坏的角色文件不得被静默忽略：文件必须保留、其它角色正常加载（R6）。"""
        cs = CharacterSystem(tmp_path)
        cs.create_character("正常角色")
        corrupt = tmp_path / "characters" / "坏文件.json"
        corrupt.write_text("{not json", encoding="utf-8")

        reloaded = CharacterSystem(tmp_path)
        assert "正常角色" in reloaded.get_character_names()
        assert corrupt.exists(), "损坏文件不应被删除"

    def test_save_character_is_atomic(self, tmp_path):
        cs = CharacterSystem(tmp_path)
        cs.create_character("甲")
        cs.character.personality = "改过了"
        cs.save_character()

        data = json.loads((tmp_path / "characters" / "甲.json").read_text(encoding="utf-8"))
        assert data["personality"] == "改过了"
        assert list((tmp_path / "characters").glob("*.tmp")) == []

    def test_load_does_not_delete_character_files(self, tmp_path):
        """加载过程不得删除任何角色文件（R6 的强断言）。"""
        cs = CharacterSystem(tmp_path)
        for name in ("甲", "乙", "丙"):
            cs.create_character(name)
        before = {p.name for p in (tmp_path / "characters").glob("*.json")}

        CharacterSystem(tmp_path).load()

        after = {p.name for p in (tmp_path / "characters").glob("*.json")}
        assert before == after


# ------------------------------------------------- 用户约束：不可删除角色名


class TestNoCharacterDeletionEntryPoint:
    """角色条目是小说内容资产 —— 面板不得提供删除入口。"""

    def test_detail_dialog_has_no_delete_button(self):
        src = (REPO_ROOT / "app" / "character_ui.py").read_text(encoding="utf-8")
        assert 'text="删除角色"' not in src
        assert "command=lambda: self._delete_character" not in src

    def test_delete_method_is_documented_as_unwired(self):
        src = (REPO_ROOT / "app" / "character_ui.py").read_text(encoding="utf-8")
        assert "刻意不接线" in src

    def test_no_button_binds_delete_character_anywhere(self):
        for rel in ("app/character_ui.py", "app/shell_ui.py", "app/toolkit_ui.py"):
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "_delete_character(" not in src.replace("def _delete_character", ""), rel

    def test_detail_dialog_is_actually_wired(self):
        """反向断言：详情入口必须存在，否则重命名/休息/故事线又变成不可达。"""
        shell = (REPO_ROOT / "app" / "shell_ui.py").read_text(encoding="utf-8")
        assert "command=self._show_char_detail" in shell
        detail = (REPO_ROOT / "app" / "character_ui.py").read_text(encoding="utf-8")
        for wired in ("self._rename_character(dialog)", "self._rest_character()",
                      "self._edit_character_story(char.name)"):
            assert wired in detail


class TestCharacterProfileRoundtrip:
    def test_to_dict_from_dict_keeps_name(self):
        char = CharacterProfile("林风")
        char.personality = "沉稳"
        restored = CharacterProfile(data=char.to_dict())
        assert restored.name == "林风"
        assert restored.personality == "沉稳"
