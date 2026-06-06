"""
云端存储模块 - 支持多种云盘服务
支持: WebDAV（坚果云）、百度网盘、夸克网盘、迅雷网盘、阿里云盘
"""

import json
import os
import time
import hashlib
import httpx
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from abc import ABC, abstractmethod


class CloudProvider(ABC):
    """云存储提供者基类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.name = "Unknown"
        self.connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """连接到云存储"""
        pass
    
    @abstractmethod
    def upload(self, local_path: Path, remote_path: str) -> bool:
        """上传文件"""
        pass
    
    @abstractmethod
    def download(self, remote_path: str, local_path: Path) -> bool:
        """下载文件"""
        pass
    
    @abstractmethod
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        """列出文件"""
        pass
    
    @abstractmethod
    def delete_file(self, remote_path: str) -> bool:
        """删除文件"""
        pass
    
    @abstractmethod
    def create_folder(self, remote_path: str) -> bool:
        """创建文件夹"""
        pass
    
    def get_file_info(self, remote_path: str) -> Optional[Dict]:
        """获取文件信息"""
        return None


class WebDAVProvider(CloudProvider):
    """WebDAV提供者（坚果云等）"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "WebDAV"
        self.base_url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.client = None
    
    def connect(self) -> bool:
        try:
            self.client = httpx.Client(
                base_url=self.base_url,
                auth=(self.username, self.password),
                timeout=30.0
            )
            # 测试连接
            resp = self.client.request("PROPFIND", "/", headers={"Depth": "0"})
            self.connected = resp.status_code in [200, 207]
            return self.connected
        except Exception as e:
            print(f"WebDAV连接失败: {e}")
            return False
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            with open(local_path, 'rb') as f:
                data = f.read()
            resp = self.client.put(remote_path, content=data)
            return resp.status_code in [200, 201, 204]
        except Exception as e:
            print(f"上传失败: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            resp = self.client.get(remote_path)
            if resp.status_code == 200:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                return True
            return False
        except Exception as e:
            print(f"下载失败: {e}")
            return False
    
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self.client.request("PROPFIND", remote_path, headers={"Depth": "1"})
            if resp.status_code in [200, 207]:
                # 简单解析XML响应
                files = []
                content = resp.text
                # 这里简化处理，实际应该解析XML
                return files
            return []
        except Exception:
            return []
    
    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self.client.delete(remote_path)
            return resp.status_code in [200, 204]
        except Exception:
            return False
    
    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self.client.request("MKCOL", remote_path)
            return resp.status_code in [200, 201]
        except Exception:
            return False


class BaiduPanProvider(CloudProvider):
    """百度网盘提供者"""
    
    API_BASE = "https://pan.baidu.com/rest/2.0/xpan"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "百度网盘"
        self.access_token = config.get("access_token", "")
        self.refresh_token = config.get("refresh_token", "")
        self.client = httpx.Client(timeout=60.0)
    
    def connect(self) -> bool:
        try:
            if not self.access_token:
                return False
            resp = self.client.get(
                f"{self.API_BASE}/quota",
                params={"access_token": self.access_token}
            )
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            return False
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        """百度网盘上传（分片上传）"""
        try:
            file_size = local_path.stat().st_size
            
            # 1. 预上传
            resp = self.client.post(
                f"{self.API_BASE}/file",
                params={"method": "upload", "access_token": self.access_token},
                json={
                    "path": remote_path,
                    "size": file_size,
                    "isdir": 0,
                    "autoinit": 1,
                    "rtype": 3
                }
            )
            
            if resp.status_code != 200:
                return False
            
            data = resp.json()
            uploadid = data.get("uploadid")
            
            # 2. 分片上传
            with open(local_path, 'rb') as f:
                part_data = f.read()
            
            resp = self.client.post(
                f"{self.API_BASE}/file",
                params={
                    "method": "upload",
                    "access_token": self.access_token,
                    "type": "tmpfile",
                    "path": remote_path,
                    "uploadid": uploadid,
                    "partseq": 0
                },
                content=part_data
            )
            
            # 3. 合并文件
            if resp.status_code == 200:
                resp = self.client.post(
                    f"{self.API_BASE}/file",
                    params={"method": "createsuperfile", "access_token": self.access_token},
                    json={
                        "path": remote_path,
                        "size": file_size,
                        "isdir": 0,
                        "rtype": 3,
                        "uploadid": uploadid,
                        "block_list": [hashlib.md5(part_data).hexdigest()]
                    }
                )
                return resp.status_code == 200
            
            return False
        except Exception as e:
            print(f"百度网盘上传失败: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            resp = self.client.get(
                f"{self.API_BASE}/file",
                params={
                    "method": "download",
                    "access_token": self.access_token,
                    "path": remote_path
                }
            )
            if resp.status_code == 200:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                return True
            return False
        except Exception:
            return False
    
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self.client.get(
                f"{self.API_BASE}/file",
                params={
                    "method": "list",
                    "access_token": self.access_token,
                    "dir": remote_path
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("list", [])
            return []
        except Exception:
            return []
    
    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file",
                params={"method": "delete", "access_token": self.access_token},
                json={"filelist": [remote_path]}
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file",
                params={"method": "create", "access_token": self.access_token},
                json={"path": remote_path, "isdir": 1}
            )
            return resp.status_code == 200
        except Exception:
            return False


class QuarkPanProvider(CloudProvider):
    """夸克网盘提供者"""
    
    API_BASE = "https://drive-pc.quark.cn/1/clouddrive"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "夸克网盘"
        self.cookie = config.get("cookie", "")
        self.client = httpx.Client(timeout=60.0)
    
    def connect(self) -> bool:
        try:
            if not self.cookie:
                return False
            resp = self.client.get(
                f"{self.API_BASE}/quota",
                headers={"Cookie": self.cookie}
            )
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            return False
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        """夸克网盘上传"""
        try:
            file_size = local_path.stat().st_size
            
            # 1. 创建上传任务
            resp = self.client.post(
                f"{self.API_BASE}/file",
                headers={"Cookie": self.cookie},
                json={
                    "file_name": local_path.name,
                    "size": file_size,
                    "parent": remote_path,
                    "file_type": "file"
                }
            )
            
            if resp.status_code != 200:
                return False
            
            data = resp.json()
            upload_id = data.get("data", {}).get("upload_id")
            
            # 2. 上传文件
            with open(local_path, 'rb') as f:
                file_data = f.read()
            
            resp = self.client.put(
                f"{self.API_BASE}/file/upload/{upload_id}",
                headers={"Cookie": self.cookie},
                content=file_data
            )
            
            return resp.status_code == 200
        except Exception as e:
            print(f"夸克网盘上传失败: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            resp = self.client.get(
                f"{self.API_BASE}/file/download",
                headers={"Cookie": self.cookie},
                params={"file_id": remote_path}
            )
            if resp.status_code == 200:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                return True
            return False
        except Exception:
            return False
    
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self.client.get(
                f"{self.API_BASE}/file/sort",
                headers={"Cookie": self.cookie},
                params={"pdir_fid": remote_path, "_sort": "file_type", "_size": 50}
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", {}).get("list", [])
            return []
        except Exception:
            return []
    
    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file/delete",
                headers={"Cookie": self.cookie},
                json={"filelist": [remote_path]}
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file",
                headers={"Cookie": self.cookie},
                json={"file_name": remote_path, "pdir_fid": "", "file_type": "folder"}
            )
            return resp.status_code == 200
        except Exception:
            return False


class XunleiPanProvider(CloudProvider):
    """迅雷网盘提供者"""
    
    API_BASE = "https://api-pan.xunlei.com/drive/v1"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "迅雷网盘"
        self.access_token = config.get("access_token", "")
        self.client = httpx.Client(timeout=60.0)
    
    def connect(self) -> bool:
        try:
            if not self.access_token:
                return False
            resp = self.client.get(
                f"{self.API_BASE}/quota",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            return False
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            file_size = local_path.stat().st_size
            
            # 1. 创建上传任务
            resp = self.client.post(
                f"{self.API_BASE}/file",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "name": local_path.name,
                    "size": file_size,
                    "parent_id": remote_path
                }
            )
            
            if resp.status_code != 200:
                return False
            
            data = resp.json()
            upload_id = data.get("id")
            
            # 2. 上传文件
            with open(local_path, 'rb') as f:
                file_data = f.read()
            
            resp = self.client.put(
                f"{self.API_BASE}/file/{upload_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
                content=file_data
            )
            
            return resp.status_code == 200
        except Exception as e:
            print(f"迅雷网盘上传失败: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            resp = self.client.get(
                f"{self.API_BASE}/file/{remote_path}/download",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            if resp.status_code == 200:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                return True
            return False
        except Exception:
            return False
    
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self.client.get(
                f"{self.API_BASE}/file",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"parent_id": remote_path}
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("files", [])
            return []
        except Exception:
            return []
    
    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self.client.delete(
                f"{self.API_BASE}/file/{remote_path}",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"name": remote_path, "parent_id": "", "kind": "folder"}
            )
            return resp.status_code == 200
        except Exception:
            return False


class AliyunPanProvider(CloudProvider):
    """阿里云盘提供者"""
    
    API_BASE = "https://api.aliyundrive.com/v2"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = "阿里云盘"
        self.access_token = config.get("access_token", "")
        self.refresh_token = config.get("refresh_token", "")
        self.client = httpx.Client(timeout=60.0)
    
    def connect(self) -> bool:
        try:
            if not self.access_token:
                return False
            resp = self.client.post(
                f"{self.API_BASE}/user/get",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            self.connected = resp.status_code == 200
            return self.connected
        except Exception:
            return False
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        try:
            file_size = local_path.stat().st_size
            file_hash = hashlib.sha1(local_path.read_bytes()).hexdigest()
            
            # 1. 获取上传地址
            resp = self.client.post(
                f"{self.API_BASE}/file/create",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "name": local_path.name,
                    "size": file_size,
                    "parent_file_id": remote_path,
                    "type": "file",
                    "check_name_mode": "auto_rename",
                    "content_hash": file_hash,
                    "content_hash_name": "sha1"
                }
            )
            
            if resp.status_code != 200:
                return False
            
            data = resp.json()
            file_id = data.get("file_id")
            upload_url = data.get("upload_url")
            
            # 2. 上传文件
            with open(local_path, 'rb') as f:
                file_data = f.read()
            
            resp = self.client.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/octet-stream"
                },
                content=file_data
            )
            
            return resp.status_code == 200
        except Exception as e:
            print(f"阿里云盘上传失败: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file/get_download_url",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"file_id": remote_path}
            )
            
            if resp.status_code == 200:
                download_url = resp.json().get("url")
                if download_url:
                    resp = self.client.get(download_url)
                    if resp.status_code == 200:
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(local_path, 'wb') as f:
                            f.write(resp.content)
                        return True
            return False
        except Exception:
            return False
    
    def list_files(self, remote_path: str = "/") -> List[Dict]:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file/list",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"parent_file_id": remote_path, "limit": 100}
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("items", [])
            return []
        except Exception:
            return []
    
    def delete_file(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file/delete",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"file_id": remote_path}
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def create_folder(self, remote_path: str) -> bool:
        try:
            resp = self.client.post(
                f"{self.API_BASE}/file/create",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"name": remote_path, "parent_file_id": "", "type": "folder"}
            )
            return resp.status_code == 200
        except Exception:
            return False


class CloudStorageManager:
    """云存储管理器"""
    
    # 支持的云存储提供商
    PROVIDERS = {
        "webdav": {"name": "WebDAV（坚果云）", "class": WebDAVProvider},
        "baidu": {"name": "百度网盘", "class": BaiduPanProvider},
        "quark": {"name": "夸克网盘", "class": QuarkPanProvider},
        "xunlei": {"name": "迅雷网盘", "class": XunleiPanProvider},
        "aliyun": {"name": "阿里云盘", "class": AliyunPanProvider},
    }
    
    def __init__(self, config_file: Path = None):
        self.config_file = config_file or Path.home() / ".ai_novel_writer" / "cloud_config.json"
        self.config = self._load_config()
        self.providers: Dict[str, CloudProvider] = {}
        self._init_providers()
    
    def _load_config(self) -> Dict:
        """加载配置"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_config(self):
        """保存配置"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def _init_providers(self):
        """初始化云存储提供商"""
        for provider_id, provider_info in self.PROVIDERS.items():
            provider_config = self.config.get(provider_id, {})
            if provider_config:
                provider_class = provider_info["class"]
                self.providers[provider_id] = provider_class(provider_config)
    
    def get_provider(self, provider_id: str) -> Optional[CloudProvider]:
        """获取云存储提供商"""
        return self.providers.get(provider_id)
    
    def get_available_providers(self) -> List[Dict]:
        """获取可用的云存储提供商"""
        available = []
        for provider_id, provider_info in self.PROVIDERS.items():
            provider = self.providers.get(provider_id)
            available.append({
                "id": provider_id,
                "name": provider_info["name"],
                "configured": provider_id in self.config,
                "connected": provider.connected if provider else False
            })
        return available
    
    def configure_provider(self, provider_id: str, config: Dict):
        """配置云存储提供商"""
        self.config[provider_id] = config
        self._save_config()
        
        # 重新初始化提供商
        provider_info = self.PROVIDERS.get(provider_id)
        if provider_info:
            provider_class = provider_info["class"]
            self.providers[provider_id] = provider_class(config)
    
    def connect_provider(self, provider_id: str) -> bool:
        """连接到云存储提供商"""
        provider = self.providers.get(provider_id)
        if provider:
            return provider.connect()
        return False
    
    def upload_novel(self, novel_dir: Path, provider_id: str, 
                    remote_path: str = "/AI_NovelWriter") -> bool:
        """上传小说到云端"""
        provider = self.providers.get(provider_id)
        if not provider or not provider.connected:
            return False
        
        try:
            # 创建远程文件夹
            provider.create_folder(remote_path)
            
            # 上传所有文件
            for file in novel_dir.rglob("*"):
                if file.is_file():
                    relative_path = file.relative_to(novel_dir)
                    remote_file = f"{remote_path}/{relative_path}"
                    provider.upload(file, remote_file)
            
            return True
        except Exception as e:
            print(f"上传小说失败: {e}")
            return False
    
    def download_novel(self, remote_path: str, local_dir: Path, 
                      provider_id: str) -> bool:
        """从云端下载小说"""
        provider = self.providers.get(provider_id)
        if not provider or not provider.connected:
            return False
        
        try:
            # 列出远程文件
            files = provider.list_files(remote_path)
            
            for file_info in files:
                remote_file = f"{remote_path}/{file_info.get('name', '')}"
                local_file = local_dir / file_info.get("name", "")
                
                if file_info.get("isdir"):
                    local_file.mkdir(parents=True, exist_ok=True)
                    self.download_novel(remote_file, local_file, provider_id)
                else:
                    provider.download(remote_file, local_file)
            
            return True
        except Exception as e:
            print(f"下载小说失败: {e}")
            return False
    
    def sync_novel(self, novel_dir: Path, provider_id: str, 
                  remote_path: str = "/AI_NovelWriter") -> bool:
        """同步小说到云端（增量同步）"""
        provider = self.providers.get(provider_id)
        if not provider or not provider.connected:
            return False
        
        try:
            # 获取远程文件列表
            remote_files = provider.list_files(remote_path)
            remote_file_map = {f.get("name"): f for f in remote_files}
            
            # 上传本地文件
            for file in novel_dir.rglob("*"):
                if file.is_file():
                    relative_path = file.relative_to(novel_dir)
                    remote_file = f"{remote_path}/{relative_path}"
                    
                    # 检查是否需要更新
                    remote_info = remote_file_map.get(str(relative_path))
                    if not remote_info or remote_info.get("size") != file.stat().st_size:
                        provider.upload(file, remote_file)
            
            return True
        except Exception as e:
            print(f"同步小说失败: {e}")
            return False
