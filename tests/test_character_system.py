"""
character_system 单元测试
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from character_system import CharacterSystem, CharacterProfile


class TestCharacterProfile(unittest.TestCase):
    def test_create_character(self):
        char = CharacterProfile(name="张三")
        self.assertEqual(char.name, "张三")
        self.assertEqual(char.level, 1)
    
    def test_hp_mp(self):
        char = CharacterProfile(name="张三")
        self.assertEqual(char.hp, 100)
        self.assertEqual(char.mp, 50)
    
    def test_has_attributes(self):
        char = CharacterProfile(name="张三")
        # 检查基本属性存在
        self.assertTrue(hasattr(char, 'name'))
        self.assertTrue(hasattr(char, 'level'))
        self.assertTrue(hasattr(char, 'hp'))
        self.assertTrue(hasattr(char, 'mp'))


class TestCharacterSystem(unittest.TestCase):
    def setUp(self):
        self.cs = CharacterSystem()
    
    def test_initialization(self):
        self.assertIsNotNone(self.cs)
    
    def test_create_character(self):
        char = self.cs.create_character("张三")
        self.assertIsNotNone(char)
        self.assertEqual(char.name, "张三")
    
    def test_character_attribute(self):
        self.cs.create_character("张三")
        self.assertIsNotNone(self.cs.character)
        self.assertEqual(self.cs.character.name, "张三")


if __name__ == '__main__':
    unittest.main()
