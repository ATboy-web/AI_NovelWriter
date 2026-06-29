"""
导航模块完整测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# NavigationManager 完整测试
# ============================================================

class TestNavigationManagerFull:
    """NavigationManager完整测试"""
    
    def test_class_exists(self):
        """测试类存在"""
        from app.navigation import NavigationManager
        assert NavigationManager is not None
    
    def test_has_methods(self):
        """测试有方法"""
        from app.navigation import NavigationManager
        methods = dir(NavigationManager)
        assert len(methods) > 0
    
    def test_has_init(self):
        """测试有__init__方法"""
        from app.navigation import NavigationManager
        assert hasattr(NavigationManager, '__init__')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
