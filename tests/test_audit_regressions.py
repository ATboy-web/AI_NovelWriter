# -*- coding: utf-8 -*-
"""2026-11-20 全仓审计修复的回归守卫。

每条用例钉住一个本轮修复的真实缺陷，防止回退：
- random_promote_minor 误用关键字 ``importance=``（应为 ``new_importance=``）⇒ TypeError；
- GenerationMixin._parse_json_response 缺 ``is_list`` 形参（与 NovelAgent 委托不一致）⇒ TypeError；
- scene_detector.get_cinematic_prompt 注解 ``-> str`` 与实际二元组返回不符；
- format_converter PDF 导出使用已废弃的 ``uni=`` / ``ln=``（fpdf2 3.x 将移除）；
- mcp_system.sanitize_server_name 的 startswith 元组合并；
- backend 请求日志中间件 _should_log 的 all() 等价改写。
"""

import importlib.util
import inspect
import warnings
from pathlib import Path
from typing import Any, Dict, Tuple, get_type_hints

import pytest

from app.character_system import CharacterProfile, CharacterSystem
from app.format_converter import CJK_FONT_CANDIDATES, FormatConverter
from app.generation_ui import GenerationMixin
from app.mcp_system import sanitize_server_name
from app.novel_agent import NovelAgent
from app.scene_detector import CinematicPromptGenerator, SceneDetector

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPromoteMinorRegression:
    def test_random_promote_minor_no_typeerror(self, tmp_path):
        cs = CharacterSystem(tmp_path)
        cs.characters["小卒"] = CharacterProfile("小卒")
        name = cs.random_promote_minor(1)
        assert name == "小卒"
        promoted = cs.characters["小卒"]
        assert promoted.category == "关键人物"
        assert promoted.importance == 5
        assert promoted.faction in {"主角阵营", "敌对阵营", "中立"}

    def test_random_promote_minor_empty_returns_none(self):
        cs = CharacterSystem()
        assert cs.random_promote_minor(1) is None

    def test_promote_character_importance_optional(self):
        cs = CharacterSystem()
        cs.characters["甲"] = CharacterProfile("甲")
        assert cs.promote_character("甲", "关键人物") is True
        assert cs.characters["甲"].importance == 1  # 未传则保持原值
        assert cs.promote_character("甲", "主角", new_importance=9) is True
        assert cs.characters["甲"].importance == 9

    def test_promote_unknown_character_returns_false(self):
        cs = CharacterSystem()
        assert cs.promote_character("不存在", "主角") is False


class TestParseDelegateParity:
    def test_generation_mixin_accepts_is_list(self):
        out = GenerationMixin._parse_json_response(None, '[{"a": 1}]', None, is_list=True)
        assert out == [{"a": 1}]

    def test_generation_mixin_is_list_rejects_dict(self):
        out = GenerationMixin._parse_json_response(None, '{"a": 1}', "fallback", is_list=True)
        assert out == "fallback"

    def test_generation_mixin_default_behavior_unchanged(self):
        assert GenerationMixin._parse_json_response(None, '{"a": 1}', None) == {"a": 1}
        assert GenerationMixin._parse_json_response(None, None, "d") == "d"

    def test_delegate_signature_parity(self):
        gen_params = inspect.signature(GenerationMixin._parse_json_response).parameters
        agent_params = inspect.signature(NovelAgent._parse_json_response).parameters
        assert "is_list" in gen_params
        assert "is_list" in agent_params
        assert gen_params["is_list"].default is False


class TestSceneDetectorContract:
    def test_return_annotation_is_tuple(self):
        hints = get_type_hints(CinematicPromptGenerator.get_cinematic_prompt)
        assert hints["return"] == Tuple[str, Dict[str, Any]]

    def test_returns_prompt_and_ratio(self):
        prompt, ratio = CinematicPromptGenerator.get_cinematic_prompt(
            {"type": "battle", "description": "两军对垒", "mood": "dramatic"}
        )
        assert isinstance(prompt, str) and prompt
        assert ratio["ratio"] in {"1:1", "3:4", "9:16", "16:9"}
        assert "size" in ratio

    def test_detect_for_volume_chapter_is_int(self):
        text = "他为了守护这座城池，最终牺牲了自己，战斗到最后一刻。" * 6
        scenes = SceneDetector.detect_for_volume([text], 2, ai_client=None)
        for scene in scenes:
            assert isinstance(scene["chapter"], int)
            assert scene["chapter"] >= 201


class TestPdfExportRegression:
    def test_pdf_real_output_without_deprecation(self, tmp_path):
        if not any(Path(p).exists() for p in CJK_FONT_CANDIDATES):
            pytest.skip("当前环境无中文字体，PDF 会按设计降级为 TXT")
        out = tmp_path / "book.pdf"
        converter = FormatConverter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = converter._to_pdf(
                "这是中文正文段落，用于验证 PDF 导出。",
                "书名",
                out,
                chapters=[{"title": "第一章", "content": "正文内容。\n第二段。"}],
                metadata={"author": "作者", "genre": "科幻"},
            )
        assert Path(result).suffix == ".pdf"
        assert out.read_bytes()[:4] == b"%PDF"
        assert not any("deprecated" in str(w.message).lower() for w in caught)


class TestMcpSanitizeServerName:
    @pytest.mark.parametrize("bad", [".hidden", "_private", "", "   ", "a" * 65, "bad/name", "x y"])
    def test_invalid_names_rejected(self, bad):
        assert sanitize_server_name(bad) is None

    @pytest.mark.parametrize("good", ["server-1", "我的服务器", "a_b.c", "ABC123"])
    def test_valid_names_kept(self, good):
        assert sanitize_server_name(good) == good


def _load_request_logger_module():
    path = REPO_ROOT / "backend" / "shared" / "middleware" / "logging.py"
    spec = importlib.util.spec_from_file_location("audit_request_logging", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRequestLoggerShouldLog:
    def test_excluded_and_normal_paths(self):
        module = _load_request_logger_module()
        logger_mw = module.RequestLogger(app=object())
        assert logger_mw._should_log("/health") is False
        assert logger_mw._should_log("/docs/anything") is False
        assert logger_mw._should_log("/openapi.json") is False
        assert logger_mw._should_log("/api/novel/list") is True
        assert logger_mw._should_log("/") is True
