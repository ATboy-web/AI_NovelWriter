"""
向量数据库管理器
用于存储和检索历史内容，确保剧情连贯性
"""

import os
import json
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib

class VectorStoreManager:
    """向量数据库管理器"""
    
    def __init__(self, persist_directory: str = "./vectorstore"):
        self.persist_directory = persist_directory
        self.collections: Dict[str, Any] = {}
        self.embeddings = None
        self.client = None
        
        # 确保存储目录存在
        os.makedirs(persist_directory, exist_ok=True)
        
        # 初始化向量数据库
        self._init_vector_store()
    
    def _init_vector_store(self):
        """初始化向量数据库"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # 创建持久化客户端
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 初始化嵌入模型
            self._init_embeddings()
            
            print(f"向量数据库初始化成功，存储路径: {self.persist_directory}")
            
        except ImportError:
            print("警告: chromadb未安装，向量检索功能将不可用")
            print("请运行: pip install chromadb")
        except Exception as e:
            print(f"向量数据库初始化失败: {e}")
    
    def _init_embeddings(self):
        """初始化嵌入模型"""
        try:
            from sentence_transformers import SentenceTransformer
            
            # 使用轻量级的多语言模型
            self.embeddings = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            print("嵌入模型加载成功")
            
        except ImportError:
            print("警告: sentence-transformers未安装，将使用默认嵌入")
            self.embeddings = None
        except Exception as e:
            print(f"嵌入模型加载失败: {e}")
            self.embeddings = None
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的嵌入向量"""
        if self.embeddings:
            return self.embeddings.encode(text).tolist()
        else:
            # 使用简单的哈希作为后备方案
            hash_obj = hashlib.md5(text.encode())
            return [float(int(b)) / 255.0 for b in hash_obj.digest()]
    
    def create_collection(self, collection_name: str) -> bool:
        """创建或获取集合"""
        try:
            if not self.client:
                print("向量数据库未初始化")
                return False
            
            # 获取或创建集合
            self.collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"created_at": datetime.now().isoformat()}
            )
            
            print(f"集合 '{collection_name}' 已创建/获取")
            return True
            
        except Exception as e:
            print(f"创建集合失败: {e}")
            return False
    
    def add_documents(
        self,
        collection_name: str,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> bool:
        """添加文档到集合"""
        try:
            if collection_name not in self.collections:
                self.create_collection(collection_name)
            
            collection = self.collections[collection_name]
            
            # 生成ID
            if ids is None:
                ids = [f"doc_{i}_{datetime.now().timestamp()}" for i in range(len(documents))]
            
            # 生成嵌入向量
            embeddings = [self._get_embedding(doc) for doc in documents]
            
            # 添加文档
            collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas or [{}] * len(documents),
                ids=ids
            )
            
            print(f"成功添加 {len(documents)} 个文档到集合 '{collection_name}'")
            return True
            
        except Exception as e:
            print(f"添加文档失败: {e}")
            return False
    
    def add_chapter(
        self,
        collection_name: str,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """添加章节到集合"""
        try:
            # 构建元数据
            chapter_metadata = {
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "added_at": datetime.now().isoformat(),
                "content_length": len(chapter_content),
                **(metadata or {})
            }
            
            # 将章节分块存储（每块约500字符）
            chunks = self._split_text(chapter_content, chunk_size=500)
            
            # 生成文档ID
            doc_ids = [
                f"chapter_{chapter_number}_chunk_{i}"
                for i in range(len(chunks))
            ]
            
            # 为每个块添加元数据
            metadatas = [
                {**chapter_metadata, "chunk_index": i, "total_chunks": len(chunks)}
                for i in range(len(chunks))
            ]
            
            # 添加到集合
            return self.add_documents(
                collection_name=collection_name,
                documents=chunks,
                metadatas=metadatas,
                ids=doc_ids
            )
            
        except Exception as e:
            print(f"添加章节失败: {e}")
            return False
    
    def _split_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """将文本分割成块"""
        chunks = []
        
        # 按段落分割
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) <= chunk_size:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """搜索相似内容"""
        try:
            if collection_name not in self.collections:
                print(f"集合 '{collection_name}' 不存在")
                return []
            
            collection = self.collections[collection_name]
            
            # 生成查询向量
            query_embedding = self._get_embedding(query)
            
            # 执行搜索
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=filter_metadata
            )
            
            # 格式化结果
            formatted_results = []
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    result = {
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "distance": results['distances'][0][i] if results['distances'] else 0,
                        "id": results['ids'][0][i] if results['ids'] else None
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            print(f"搜索失败: {e}")
            return []
    
    def search_chapters(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        chapter_range: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        """搜索章节内容"""
        filter_metadata = None
        if chapter_range:
            filter_metadata = {
                "chapter_number": {
                    "$gte": chapter_range[0],
                    "$lte": chapter_range[1]
                }
            }
        
        return self.search(
            collection_name=collection_name,
            query=query,
            n_results=n_results,
            filter_metadata=filter_metadata
        )
    
    def get_chapter_context(
        self,
        collection_name: str,
        chapter_number: int,
        context_size: int = 3
    ) -> str:
        """获取章节上下文"""
        try:
            # 获取指定章节及其前后章节
            results = self.search_chapters(
                collection_name=collection_name,
                query=f"第{chapter_number}章",
                n_results=context_size * 3,
                chapter_range=(max(1, chapter_number - context_size), chapter_number)
            )
            
            # 按章节号排序
            results.sort(key=lambda x: x['metadata'].get('chapter_number', 0))
            
            # 合并内容
            context_parts = []
            for result in results:
                chapter_num = result['metadata'].get('chapter_number', 0)
                chunk_index = result['metadata'].get('chunk_index', 0)
                
                # 只添加每个章节的第一个块
                if chunk_index == 0:
                    context_parts.append(f"第{chapter_num}章: {result['content'][:200]}...")
            
            return "\n\n".join(context_parts)
            
        except Exception as e:
            print(f"获取章节上下文失败: {e}")
            return ""
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            if collection_name not in self.collections:
                return {"error": "集合不存在"}
            
            collection = self.collections[collection_name]
            
            return {
                "name": collection_name,
                "count": collection.count(),
                "metadata": collection.metadata
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def delete_collection(self, collection_name: str) -> bool:
        """删除集合"""
        try:
            if not self.client:
                return False
            
            self.client.delete_collection(collection_name)
            
            if collection_name in self.collections:
                del self.collections[collection_name]
            
            print(f"集合 '{collection_name}' 已删除")
            return True
            
        except Exception as e:
            print(f"删除集合失败: {e}")
            return False
    
    def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            if not self.client:
                return []
            
            collections = self.client.list_collections()
            return [c.name for c in collections]
            
        except Exception as e:
            print(f"列出集合失败: {e}")
            return []
    
    def clear_all(self) -> bool:
        """清空所有数据"""
        try:
            if not self.client:
                return False
            
            # 删除所有集合
            collections = self.list_collections()
            for collection_name in collections:
                self.delete_collection(collection_name)
            
            print("所有数据已清空")
            return True
            
        except Exception as e:
            print(f"清空数据失败: {e}")
            return False


# 全局实例
_vector_store_manager = None
_vector_store_manager_lock = threading.Lock()

def get_vector_store_manager() -> VectorStoreManager:
    """获取向量数据库管理器实例"""
    global _vector_store_manager
    with _vector_store_manager_lock:
        if _vector_store_manager is None:
            _vector_store_manager = VectorStoreManager()
        return _vector_store_manager


# 便捷函数
def add_chapter_to_vector_store(
    novel_id: str,
    chapter_number: int,
    chapter_title: str,
    chapter_content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """添加章节到向量数据库"""
    manager = get_vector_store_manager()
    collection_name = f"novel_{novel_id}"
    return manager.add_chapter(
        collection_name=collection_name,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        chapter_content=chapter_content,
        metadata=metadata
    )

def search_novel_content(
    novel_id: str,
    query: str,
    n_results: int = 5
) -> List[Dict[str, Any]]:
    """搜索小说内容"""
    manager = get_vector_store_manager()
    collection_name = f"novel_{novel_id}"
    return manager.search(
        collection_name=collection_name,
        query=query,
        n_results=n_results
    )

def get_chapter_context(
    novel_id: str,
    chapter_number: int,
    context_size: int = 3
) -> str:
    """获取章节上下文"""
    manager = get_vector_store_manager()
    collection_name = f"novel_{novel_id}"
    return manager.get_chapter_context(
        collection_name=collection_name,
        chapter_number=chapter_number,
        context_size=context_size
    )
