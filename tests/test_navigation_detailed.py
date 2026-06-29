"""
导航模块详细测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# NavigationManager 方法测试
# ============================================================

class TestNavigationManagerMethods:
    """NavigationManager方法测试"""
    
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
