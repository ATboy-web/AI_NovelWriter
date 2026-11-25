"""世界线读写端口的契约测试。

`TimelineStore` 用**结构化类型**满足端口（不继承 Protocol）—— 这是有意的：
store 的历史比端口久，强行继承会让导入关系倒挂（ports ← timeline_store）。

但结构化类型也意味着**改名不会报错**，只有 `isinstance` 与属性检查才会发现。
本文件就是那道检查。
"""

from __future__ import annotations

import pytest

from app.ports import TimelineReader, TimelineWriter
from app.timeline_store import TimelineStore


class TestTimelinePorts:
    def test_store_satisfies_reader(self, tmp_path):
        store = TimelineStore(str(tmp_path))
        assert isinstance(store, TimelineReader), "TimelineStore 不再满足读端口（方法被改名？）"

    def test_store_satisfies_writer(self, tmp_path):
        store = TimelineStore(str(tmp_path))
        assert isinstance(store, TimelineWriter), "TimelineStore 不再满足写端口（方法被改名？）"

    @pytest.mark.parametrize(
        "method",
        ["read_memory_events", "read_world_lines", "chapter_axis", "snapshot"],
    )
    def test_reader_methods_are_callable(self, tmp_path, method):
        store = TimelineStore(str(tmp_path))
        assert callable(getattr(store, method))

    @pytest.mark.parametrize("method", ["sync", "annotate", "invalidate"])
    def test_writer_methods_are_callable(self, tmp_path, method):
        store = TimelineStore(str(tmp_path))
        assert callable(getattr(store, method))

    def test_ports_do_not_drift_apart(self):
        """端口声明的方法名必须都能在 store 上找到 —— 防止端口单方面加方法。"""
        for proto in (TimelineReader, TimelineWriter):
            names = [n for n in dir(proto) if not n.startswith("_")]
            assert names, f"{proto.__name__} 没有任何方法，端口形同虚设"
            for name in names:
                assert hasattr(TimelineStore, name), f"端口声明了 {name}，但 store 没有"

    def test_reader_and_writer_are_disjoint(self):
        """读写端口不应重叠：重叠说明职责没分清楚。"""
        reader = {n for n in dir(TimelineReader) if not n.startswith("_")}
        writer = {n for n in dir(TimelineWriter) if not n.startswith("_")}
        assert not (reader & writer), f"读写端口重叠：{reader & writer}"


class TestTimelineDomainRules:
    """纯函数（原在 timeline_store 末尾）的边界。"""

    def test_char_list_unique_keeps_order(self):
        from app.domain.timeline import char_list_unique

        assert char_list_unique(["甲", "乙", "甲", "丙"]) == ["甲", "乙", "丙"]

    def test_char_list_unique_skips_blank(self):
        from app.domain.timeline import char_list_unique

        assert char_list_unique(["甲", "", "  ", "乙"]) == ["甲", "乙"]

    def test_extraction_prompt_mentions_json(self):
        from app.domain.timeline import extraction_prompt

        text = extraction_prompt(3, "正文内容")
        assert "JSON" in text
        assert "3" in text

    def test_parse_result_survives_broken_json(self):
        """模型输出不可信：坏 JSON 必须降级，不能抛。"""
        from app.domain.timeline import parse_extraction_result

        assert parse_extraction_result("这不是 JSON", 1) == []

    def test_parse_result_skips_non_dict_items(self):
        from app.domain.timeline import parse_extraction_result

        rows = parse_extraction_result('[{"chapter": 1, "event": "开篇"}, "字符串", 42]', 1)
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_parse_result_fills_chapter_when_missing(self):
        from app.domain.timeline import parse_extraction_result

        rows = parse_extraction_result('[{"event": "无章号的事件"}]', 7)
        if rows:
            assert rows[0].get("chapter") == 7
