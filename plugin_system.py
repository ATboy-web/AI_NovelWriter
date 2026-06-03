"""
插件系统 - 支持扩展功能
"""

import json
import importlib.util
import sys
import shutil
import zipfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from urllib.parse import urlparse


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
    
    def install_plugin(self, source: str) -> Dict[str, Any]:
        """
        安装插件
        
        Args:
            source: 插件来源，支持以下格式：
                   - 本地目录路径: /path/to/plugin
                   - ZIP文件路径: /path/to/plugin.zip
                   - URL地址: https://example.com/plugin.zip
                   - GitHub仓库: https://github.com/user/repo
        
        Returns:
            安装结果字典，包含 success, message, plugin_name 等信息
        """
        try:
            # 判断来源类型
            if source.startswith(("http://", "https://")):
                return self._install_from_url(source)
            elif source.endswith(".zip"):
                return self._install_from_zip(source)
            else:
                return self._install_from_directory(source)
        except Exception as e:
            return {
                "success": False,
                "message": f"安装失败: {str(e)}",
                "error": str(e)
            }
    
    def _install_from_url(self, url: str) -> Dict[str, Any]:
        """从URL安装插件"""
        import urllib.request
        
        try:
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 处理GitHub仓库URL
                if "github.com" in url:
                    # 转换为下载链接
                    if not url.endswith(".zip"):
                        url = url.rstrip("/") + "/archive/main.zip"
                
                # 下载文件
                zip_path = temp_path / "plugin.zip"
                print(f"正在下载插件: {url}")
                urllib.request.urlretrieve(url, str(zip_path))
                
                # 从ZIP安装
                return self._install_from_zip(str(zip_path))
                
        except Exception as e:
            return {
                "success": False,
                "message": f"下载失败: {str(e)}",
                "error": str(e)
            }
    
    def _install_from_zip(self, zip_path: str) -> Dict[str, Any]:
        """从ZIP文件安装插件"""
        try:
            zip_file = Path(zip_path)
            if not zip_file.exists():
                return {
                    "success": False,
                    "message": f"ZIP文件不存在: {zip_path}"
                }
            
            # 创建临时目录解压
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 解压ZIP文件
                with zipfile.ZipFile(str(zip_file), 'r') as zip_ref:
                    zip_ref.extractall(str(temp_path))
                
                # 查找插件目录（可能在子目录中）
                plugin_dir = self._find_plugin_dir(temp_path)
                if not plugin_dir:
                    return {
                        "success": False,
                        "message": "ZIP文件中未找到有效的插件（缺少plugin.json）"
                    }
                
                # 读取插件配置获取名称
                config_file = plugin_dir / "plugin.json"
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    plugin_name = config.get("name", plugin_dir.name)
                else:
                    plugin_name = plugin_dir.name
                
                # 检查是否已安装
                if plugin_name in self.plugins:
                    return {
                        "success": False,
                        "message": f"插件 '{plugin_name}' 已存在，请先卸载"
                    }
                
                # 复制到插件目录
                dest_dir = self.plugins_dir / plugin_name
                if dest_dir.exists():
                    shutil.rmtree(str(dest_dir))
                shutil.copytree(str(plugin_dir), str(dest_dir))
                
                # 加载插件
                plugin = Plugin(dest_dir)
                if plugin.module:
                    self.plugins[plugin.name] = plugin
                    return {
                        "success": True,
                        "message": f"插件 '{plugin.name}' 安装成功",
                        "plugin_name": plugin.name,
                        "plugin_info": {
                            "name": plugin.name,
                            "version": plugin.version,
                            "author": plugin.author,
                            "description": plugin.description,
                            "type": plugin.plugin_type
                        }
                    }
                else:
                    # 加载失败，清理目录
                    shutil.rmtree(str(dest_dir))
                    return {
                        "success": False,
                        "message": f"插件加载失败，请检查插件代码"
                    }
                    
        except zipfile.BadZipFile:
            return {
                "success": False,
                "message": "无效的ZIP文件格式"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"安装失败: {str(e)}",
                "error": str(e)
            }
    
    def _install_from_directory(self, dir_path: str) -> Dict[str, Any]:
        """从本地目录安装插件"""
        try:
            source_dir = Path(dir_path)
            if not source_dir.exists():
                return {
                    "success": False,
                    "message": f"目录不存在: {dir_path}"
                }
            
            if not source_dir.is_dir():
                return {
                    "success": False,
                    "message": f"不是有效的目录: {dir_path}"
                }
            
            # 检查是否包含plugin.json
            config_file = source_dir / "plugin.json"
            if not config_file.exists():
                return {
                    "success": False,
                    "message": "目录中缺少plugin.json配置文件"
                }
            
            # 读取插件配置
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            plugin_name = config.get("name", source_dir.name)
            
            # 检查是否已安装
            if plugin_name in self.plugins:
                return {
                    "success": False,
                    "message": f"插件 '{plugin_name}' 已存在，请先卸载"
                }
            
            # 复制到插件目录
            dest_dir = self.plugins_dir / plugin_name
            if dest_dir.exists():
                shutil.rmtree(str(dest_dir))
            shutil.copytree(str(source_dir), str(dest_dir))
            
            # 加载插件
            plugin = Plugin(dest_dir)
            if plugin.module:
                self.plugins[plugin.name] = plugin
                return {
                    "success": True,
                    "message": f"插件 '{plugin.name}' 安装成功",
                    "plugin_name": plugin.name,
                    "plugin_info": {
                        "name": plugin.name,
                        "version": plugin.version,
                        "author": plugin.author,
                        "description": plugin.description,
                        "type": plugin.plugin_type
                    }
                }
            else:
                # 加载失败，清理目录
                shutil.rmtree(str(dest_dir))
                return {
                    "success": False,
                    "message": f"插件加载失败，请检查插件代码"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"安装失败: {str(e)}",
                "error": str(e)
            }
    
    def _find_plugin_dir(self, search_path: Path) -> Optional[Path]:
        """在目录中查找插件目录"""
        # 检查当前目录是否有plugin.json
        if (search_path / "plugin.json").exists():
            return search_path
        
        # 检查子目录（处理GitHub下载的ZIP，通常有一个顶级目录）
        for sub_dir in search_path.iterdir():
            if sub_dir.is_dir() and (sub_dir / "plugin.json").exists():
                return sub_dir
        
        return None
    
    def get_plugin_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取插件详细信息"""
        plugin = self.get_plugin(name)
        if not plugin:
            return None
        
        return {
            "name": plugin.name,
            "version": plugin.version,
            "author": plugin.author,
            "description": plugin.description,
            "type": plugin.plugin_type,
            "enabled": plugin.enabled,
            "plugin_dir": str(plugin.plugin_dir),
            "has_tools": len(plugin.get_tools()) > 0,
            "has_library": plugin.get_library() is not None,
            "has_exporters": len(plugin.get_exporters()) > 0,
            "has_ai_providers": len(plugin.get_ai_providers()) > 0
        }
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """列出所有插件"""
        result = []
        for plugin in self.plugins.values():
            result.append(self.get_plugin_info(plugin.name))
        return result
    
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
