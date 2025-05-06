import os
from typing import List, Dict, Any, Optional
import json
import time
import chromadb
from chromadb.config import Settings
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

# 导入配置
from config import EMBEDDING_MODEL, VECTOR_DB_DIR

class VectorStore:
    """向量存储管理类，处理文档的存储和检索"""
    
    def __init__(self, persist_directory: str = None):
        self.persist_directory = persist_directory or VECTOR_DB_DIR
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # 使用配置文件中的多语言嵌入模型
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL
        )
        
        # 初始化文档索引元数据存储
        self.metadata_path = os.path.join(self.persist_directory, "document_metadata.json")
        self.document_metadata = self._load_metadata()
        
        # 初始化ChromaDB客户端
        self.client = chromadb.Client(Settings(
            persist_directory=self.persist_directory,
            anonymized_telemetry=False
        ))
        
        # 确保集合存在
        self._ensure_collection()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """加载文档元数据"""
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"documents": {}}
    
    def _save_metadata(self):
        """保存文档元数据"""
        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.document_metadata, f, ensure_ascii=False, indent=2)
    
    def _ensure_collection(self):
        """确保集合存在"""
        try:
            self.collection = self.client.get_or_create_collection(
                name="document_collection",
                embedding_function=None  # 我们使用LangChain的embeddings
            )
        except Exception as e:
            print(f"创建集合时出错: {str(e)}")
            raise e
    
    async def add_documents(self, documents: List[Document], source_file: str):
        """添加文档到向量存储"""
        try:
            # 创建向量存储
            vectorstore = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                persist_directory=self.persist_directory,
                collection_name="document_collection"
            )
            
            # 更新元数据
            file_name = os.path.basename(source_file)
            self.document_metadata["documents"][file_name] = {
                "path": source_file,
                "chunks_count": len(documents),
                "added_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._save_metadata()
            
            return {
                "status": "success",
                "document_id": file_name,
                "chunks_count": len(documents)
            }
            
        except Exception as e:
            print(f"添加文档时出错: {str(e)}")
            raise e
    
    async def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """搜索相关文档"""
        try:
            # 创建向量存储实例用于检索
            vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings,
                collection_name="document_collection"
            )
            
            # 执行相似度搜索
            documents = vectorstore.similarity_search_with_score(query, k=k)
            
            # 格式化结果
            results = []
            for doc, score in documents:
                results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score)
                })
            
            return results
            
        except Exception as e:
            print(f"搜索文档时出错: {str(e)}")
            raise e
    
    async def get_document_list(self) -> List[Dict[str, Any]]:
        """获取已处理的文档列表"""
        try:
            documents = []
            for doc_id, metadata in self.document_metadata["documents"].items():
                documents.append({
                    "id": doc_id,
                    "path": metadata["path"],
                    "chunks_count": metadata["chunks_count"],
                    "added_at": metadata.get("added_at", "未知")
                })
            return documents
        except Exception as e:
            print(f"获取文档列表时出错: {str(e)}")
            raise e 