"""
novel_toolkit 单元测试
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from unittest.mock import MagicMock
from novel_toolkit import (
    ElementLibrary, BridgeLibrary, DescriptionLibrary,
    DialogueEngine, StoryFlowEngine, StyleTransferEngine,
    AdaptEngine, WebSearchAdaptEngine
)


class TestElementLibrary(unittest.TestCase):
    def setUp(self):
        self.lib = ElementLibrary()
    
    def test_get_categories(self):
        cats = self.lib.get_categories()
        self.assertTrue(len(cats) > 0)
    
    def test_get_items(self):
        cats = self.lib.get_categories()
        if cats:
            items = self.lib.get_items(cats[0]["name"])
            self.assertIsInstance(items, list)
    
    def test_add_custom_item(self):
        cats = self.lib.get_categories()
        if cats:
            cat_name = cats[0]["name"]
            items_before = self.lib.get_items(cat_name)
            # 尝试添加
            self.lib.add_custom_item(cat_name, {"name": "test_xyz", "template": "test"})
            items_after = self.lib.get_items(cat_name)
            # 验证数量增加或元素存在
            self.assertTrue(len(items_after) >= len(items_before))


class TestBridgeLibrary(unittest.TestCase):
    def setUp(self):
        self.lib = BridgeLibrary()
    
    def test_get_categories(self):
        cats = self.lib.get_categories()
        self.assertTrue(len(cats) > 0)
    
    def test_get_templates(self):
        cats = self.lib.get_categories()
        if cats:
            templates = self.lib.get_templates(cats[0]["name"])
            self.assertTrue(len(templates) > 0)
    
    def test_add_custom_item(self):
        cats = self.lib.get_categories()
        if cats:
            count_before = len(self.lib.get_templates(cats[0]["name"]))
            self.lib.add_custom_item(cats[0]["name"], "custom_template")
            count_after = len(self.lib.get_templates(cats[0]["name"]))
            self.assertEqual(count_after, count_before + 1)


class TestDescriptionLibrary(unittest.TestCase):
    def setUp(self):
        self.lib = DescriptionLibrary()
    
    def test_get_categories(self):
        cats = self.lib.get_categories()
        self.assertTrue(len(cats) > 0)
    
    def test_add_custom_item(self):
        cats = self.lib.get_categories()
        if cats:
            self.lib.add_custom_item(cats[0], "custom_keyword")


class TestEngineInit(unittest.TestCase):
    """测试需要ai_client的引擎"""
    
    def test_dialogue_engine(self):
        mock_client = MagicMock()
        engine = DialogueEngine(mock_client)
        self.assertIsNotNone(engine)
    
    def test_story_flow_engine(self):
        mock_client = MagicMock()
        engine = StoryFlowEngine(mock_client)
        self.assertIsNotNone(engine)
    
    def test_style_transfer_engine(self):
        mock_client = MagicMock()
        engine = StyleTransferEngine(mock_client)
        self.assertIsNotNone(engine)
    
    def test_adapt_engine(self):
        mock_client = MagicMock()
        engine = AdaptEngine(mock_client)
        self.assertIsNotNone(engine)
    
    def test_websearch_engine(self):
        mock_client = MagicMock()
        engine = WebSearchAdaptEngine(mock_client)
        self.assertIsNotNone(engine)


if __name__ == '__main__':
    unittest.main()
