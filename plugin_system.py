"""
插件系统 - 支持扩展功能
"""

import json
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime


class Plugin:
    """插件基类"""
    
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self.config = self._load_config()
        self.name = self.config.get("name", plugin_dir.name)
        self.version = self.config.get("version", "1.0.0")
        self.author = self.config.get("author", "Unknown")
        self.description = self.config.get("description", "")
        self.plugin_type = self.config.get("type", "tool")
        self.entry = self.config.get("entry", "main.py")
        self.enabled = True
        
        # 加载插件模块
        self.module = self._load_module()
    
    def _load_config(self) -> Dict:
        """加载插件配置"""
        config_file = self.plugin_dir / "plugin.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_module(self):
        """加载插件模块"""
        entry_file = self.plugin_dir / self.entry
        if not entry_file.exists():
            return None
        
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{self.plugin_dir.name}", str(entry_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            print(f"加载插件 {self.name} 失败: {e}")
            return None
    
    def get_tools(self) -> List[Dict]:
        """获取插件提供的工具"""
        if self.module and hasattr(self.module, 'get_tools'):
            return self.module.get_tools()
        return []
    
    def get_library(self) -> Optional[Dict]:
        """获取插件提供的库"""
        if self.module and hasattr(self.module, 'get_library'):
            return self.module.get_library()
        return None
    
    def get_exporters(self) -> List[Dict]:
        """获取插件提供的导出器"""
        if self.module and hasattr(self.module, 'get_exporters'):
            return self.module.get_exporters()
        return []
    
    def get_ai_providers(self) -> List[Dict]:
        """获取插件提供的AI服务"""
        if self.module and hasattr(self.module, 'get_ai_providers'):
            return self.module.get_ai_providers()
        return []


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugins_dir: Path = None):
        self.plugins_dir = plugins_dir or Path.home() / ".ai_novel_writer" / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        self.plugins: Dict[str, Plugin] = {}
        self._load_all_plugins()
    
    def _load_all_plugins(self):
        """加载所有插件"""
        for plugin_dir in self.plugins_dir.iterdir():
            if plugin_dir.is_dir():
                plugin = Plugin(plugin_dir)
                if plugin.module:  # 只加载成功的插件
                    self.plugins[plugin.name] = plugin
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """获取指定插件"""
        return self.plugins.get(name)
    
    def get_all_plugins(self) -> List[Plugin]:
        """获取所有插件"""
        return list(self.plugins.values())
    
    def get_enabled_plugins(self) -> List[Plugin]:
        """获取已启用的插件"""
        return [p for p in self.plugins.values() if p.enabled]
    
    def enable_plugin(self, name: str) -> bool:
        """启用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = True
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = False
            return True
        return False
    
    def get_all_tools(self) -> List[Dict]:
        """获取所有插件提供的工具"""
        tools = []
        for plugin in self.get_enabled_plugins():
            plugin_tools = plugin.get_tools()
            for tool in plugin_tools:
                tool["plugin"] = plugin.name
                tools.append(tool)
        return tools
    
    def get_all_libraries(self) -> Dict[str, List[Dict]]:
        """获取所有插件提供的库"""
        libraries = {}
        for plugin in self.get_enabled_plugins():
            lib = plugin.get_library()
            if lib:
                lib_type = lib.get("type", "unknown")
                if lib_type not in libraries:
                    libraries[lib_type] = []
                libraries[lib_type].append({
                    "plugin": plugin.name,
                    "category": lib.get("category", ""),
                    "items": lib.get("items", [])
                })
        return libraries
    
    def get_all_exporters(self) -> List[Dict]:
        """获取所有插件提供的导出器"""
        exporters = []
        for plugin in self.get_enabled_plugins():
            plugin_exporters = plugin.get_exporters()
            for exporter in plugin_exporters:
                exporter["plugin"] = plugin.name
                exporters.append(exporter)
        return exporters
    
    def get_all_ai_providers(self) -> List[Dict]:
        """获取所有插件提供的AI服务"""
        providers = []
        for plugin in self.get_enabled_plugins():
            plugin_providers = plugin.get_ai_providers()
            for provider in plugin_providers:
                provider["plugin"] = plugin.name
                providers.append(provider)
        return providers
    
    def install_plugin(self, source: str) -> bool:
        """安装插件"""
        # TODO: 支持从URL、本地路径安装插件
        pass
    
    def uninstall_plugin(self, name: str) -> bool:
        """卸载插件"""
        if name in self.plugins:
            plugin = self.plugins[name]
            # 删除插件目录
            import shutil
            shutil.rmtree(plugin.plugin_dir)
            del self.plugins[name]
            return True
        return False
    
    def reload_plugins(self):
        """重新加载所有插件"""
        self.plugins.clear()
        self._load_all_plugins()


# 插件示例
PLUGIN_EXAMPLE = '''
# plugin.json
{
  "name": "我的插件",
  "version": "1.0.0",
  "author": "作者",
  "description": "插件描述",
  "type": "tool",
  "entry": "main.py"
}

# main.py
def get_tools():
    return [
        {
            "name": "我的工具",
            "desc": "工具描述",
            "icon": "star",
            "handler": my_tool_handler
        }
    ]

def my_tool_handler(ai_client, context):
    # 处理逻辑
    return "结果"
'''
