"""NovelStore 单元测试（v3 A7）。

背景：`outline.json` / `meta.json` 原先被三个模块各自 `open(path, 'w')` 裸写 ——
既可能写一半被截断，也可能并发互相覆盖。本文件锁定收敛后的性质：

1. 写入**原子**（临时文件不残留，`.bak` 轮转可用）；
2. **读-改-写**不会丢掉并发方的改动（原先的裸写会丢）；
3. 损坏时**不静默变成空**（"读到空 → 写回空 → 清库"是已踩过的级联事故）；
4. `outline` 始终是 list（否则 `for ch in outline` 会遍历到键名字符串）；
5. **角色数据不得经此写入**（必须走 `mutate_characters` 的三道闸门）。
"""

import json
import threading

import pytest

from app.novel_store import NovelStore


@pytest.fixture
def store(tmp_path) -> NovelStore:
    return NovelStore(tmp_path)


class TestMeta:
    def test_read_missing_returns_empty_dict(self, store):
        assert store.read_meta() == {}

    def test_write_then_read(self, store):
        store.write_meta({"title": "测试书", "genre": "玄幻"})
        assert store.read_meta() == {"title": "测试书", "genre": "玄幻"}

    def test_write_creates_backup(self, store):
        store.write_meta({"title": "一"})
        store.write_meta({"title": "二"})
        assert store.read_meta()["title"] == "二"
        assert (store.novel_dir / "meta.json.bak").is_file()

    def test_update_meta_merges_instead_of_replacing(self, store):
        store.write_meta({"title": "书", "genre": "玄幻"})
        result = store.update_meta({"protagonist": "甲"})
        assert result == {"title": "书", "genre": "玄幻", "protagonist": "甲"}

    def test_update_meta_accepts_kwargs(self, store):
        store.write_meta({"title": "书"})
        assert store.update_meta(chapter_count=12)["chapter_count"] == 12

    def test_write_meta_rejects_non_dict(self, store):
        with pytest.raises(TypeError):
            store.write_meta(["not", "a", "dict"])

    def test_corrupt_meta_falls_back_to_backup(self, store):
        store.write_meta({"title": "好的"})
        store.write_meta({"title": "更好"})  # 产生 .bak = {"title": "好的"}
        (store.novel_dir / "meta.json").write_text("{坏掉的", encoding="utf-8")
        assert store.read_meta()["title"] == "好的"

    def test_corrupt_meta_can_raise(self, store):
        (store.novel_dir / "meta.json").write_text("{坏掉的", encoding="utf-8")
        with pytest.raises(Exception):
            store.read_meta(raise_on_corrupt=True)


class TestOutline:
    def test_read_missing_returns_empty_list(self, store):
        assert store.read_outline() == []

    def test_write_then_read(self, store):
        chapters = [{"title": "第一章"}, {"title": "第二章"}]
        store.write_outline(chapters)
        assert store.read_outline() == chapters

    def test_write_rejects_non_list(self, store):
        with pytest.raises(TypeError):
            store.write_outline({"chapter": 1})

    def test_non_list_content_is_normalized_to_empty_list(self, store):
        """写坏的 dict 不能让调用方遍历到键名。"""
        (store.novel_dir / "outline.json").write_text('{"a": 1}', encoding="utf-8")
        assert store.read_outline() == []

    def test_append_outline(self, store):
        store.write_outline([{"title": "一"}])
        result = store.append_outline([{"title": "二"}, {"title": "三"}])
        assert len(result) == 3
        assert store.read_outline()[-1]["title"] == "三"

    def test_update_outline_chapter(self, store):
        store.write_outline([{"title": "一"}, {"title": "二"}])
        store.update_outline_chapter(2, {"summary": "新摘要"})
        outline = store.read_outline()
        assert outline[0] == {"title": "一"}
        assert outline[1] == {"title": "二", "summary": "新摘要"}

    def test_update_out_of_range_changes_nothing(self, store):
        original = [{"title": "一"}]
        store.write_outline(original)
        assert store.update_outline_chapter(99, {"x": 1}) == original
        assert store.update_outline_chapter(0, {"x": 1}) == original
        assert store.read_outline() == original

    def test_corrupt_outline_falls_back_to_backup(self, store):
        store.write_outline([{"title": "好的"}])
        store.write_outline([{"title": "更好"}])
        (store.novel_dir / "outline.json").write_text("[坏掉的", encoding="utf-8")
        assert store.read_outline() == [{"title": "好的"}]


class TestConcurrency:
    """原先三处裸写会互相覆盖；读-改-写加锁后不得丢更新。"""

    def test_concurrent_meta_updates_do_not_lose_keys(self, store):
        store.write_meta({"title": "书"})

        def worker(index: int) -> None:
            for _ in range(20):
                store.update_meta({f"k{index}": index})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        meta = store.read_meta()
        for i in range(8):
            assert meta.get(f"k{i}") == i, f"k{i} 丢失 —— 读-改-写未串行化"
        assert meta["title"] == "书"

    def test_concurrent_outline_appends_no_lost_chapters(self, store):
        store.write_outline([])

        def worker(index: int) -> None:
            for _ in range(10):
                store.append_outline([{"title": f"ch-{index}"}])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(store.read_outline()) == 60


class TestAtomicity:
    def test_no_tmp_files_left_behind(self, store):
        store.write_meta({"a": 1})
        store.write_outline([{"b": 2}])
        leftovers = [p.name for p in store.novel_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_content_is_complete_json_after_write(self, store):
        payload = {"k": "中文" * 500}
        store.write_meta(payload)
        raw = (store.novel_dir / "meta.json").read_text(encoding="utf-8")
        assert json.loads(raw) == payload


class TestGenericJson:
    def test_read_write_roundtrip(self, store):
        store.write_json("outlines/overall.json", [{"title": "整体"}])
        assert store.read_json("outlines/overall.json") == [{"title": "整体"}]

    def test_write_json_creates_parent_dirs(self, store):
        store.write_json("outlines/created/later.json", {"x": 1})
        assert (store.novel_dir / "outlines" / "created" / "later.json").is_file()

    @pytest.mark.parametrize("rel", ["characters.json", "memory/characters.json", "memory\\characters.json"])
    def test_characters_json_write_is_refused(self, store, rel):
        """⚠️ 硬护栏：角色数据必须走 mutate_characters 的三道闸门，不得绕过。"""
        with pytest.raises(ValueError, match="mutate_characters"):
            store.write_json(rel, {"甲": {}})

    def test_exists(self, store):
        assert store.exists("meta.json") is False
        store.write_meta({"a": 1})
        assert store.exists("meta.json") is True


class TestEvents:
    def test_events_receive_outline_changes(self, tmp_path):
        class Recorder:
            def __init__(self):
                self.topics = []

            def publish(self, topic, payload=None):
                self.topics.append((topic, payload.get("count") if payload else None))

        recorder = Recorder()
        store = NovelStore(tmp_path, events=recorder)
        store.write_outline([{"t": 1}, {"t": 2}])
        assert ("outline.changed", 2) in recorder.topics

    def test_events_receive_meta_changes(self, tmp_path):
        class Recorder:
            def __init__(self):
                self.topics = []

            def publish(self, topic, payload=None):
                self.topics.append(topic)

        recorder = Recorder()
        store = NovelStore(tmp_path, events=recorder)
        store.write_meta({"a": 1})
        assert "novel.meta_changed" in recorder.topics

    def test_broken_subscriber_does_not_break_write(self, tmp_path):
        """订阅方抛异常不得影响数据落盘。"""

        class Broken:
            def publish(self, topic, payload=None):
                raise RuntimeError("订阅方炸了")

        store = NovelStore(tmp_path, events=Broken())
        store.write_meta({"a": 1})
        assert store.read_meta() == {"a": 1}

    def test_no_events_object_is_fine(self, store):
        store.write_meta({"a": 1})
        store.write_outline([])
        assert store.read_meta() == {"a": 1}


class TestDebugDump:
    def test_dump_is_json(self, store):
        store.write_meta({"title": "x"})
        store.write_outline([{"t": 1}])
        payload = json.loads(store.dump_debug())
        assert payload["outline_chapters"] == 1
        assert payload["meta_exists"] is True


def test_does_not_touch_characters_json(tmp_path):
    """NovelStore 的任何操作都不得改写 memory/characters.json。"""
    memory = tmp_path / "memory"
    memory.mkdir()
    char_file = memory / "characters.json"
    char_file.write_text('{"甲": {"personality": "x"}}', encoding="utf-8")
    before = char_file.read_bytes()

    store = NovelStore(tmp_path)
    store.write_meta({"title": "书"})
    store.write_outline([{"t": 1}])
    store.append_outline([{"t": 2}])
    store.update_meta({"x": 1})
    store.read_meta()
    store.read_outline()
    store.dump_debug()

    assert char_file.read_bytes() == before
