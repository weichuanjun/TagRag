import os
from typing import List, Dict, Any, Optional
import json
import time
import chromadb
from chromadb.config import Settings
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
import logging

# 导入配置
from config import EMBEDDING_MODEL, VECTOR_DB_DIR

logger = logging.getLogger(__name__)

class VectorStore:
    """向量存储管理类，处理文档的存储和检索"""
    
    def __init__(self, repository_id: Optional[int] = None):
        """
        初始化向量存储
        
        Args:
            repository_id: 代码库ID，如果指定则创建特定代码库的向量存储
        """
        # 为每个代码库创建独立的向量存储目录
        if repository_id:
            self.repository_id = repository_id
            self.persist_directory = os.path.join(VECTOR_DB_DIR, f"repo_{repository_id}")
        else:
            self.repository_id = None
            self.persist_directory = os.path.join(VECTOR_DB_DIR, "default")
            
        os.makedirs(self.persist_directory, exist_ok=True)
        logger.info(f"向量存储目录: {self.persist_directory}")
        
        # 使用配置文件中的多语言嵌入模型
        try:
            self.embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL
            )
            logger.info(f"加载嵌入模型: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {str(e)}")
            # 尝试使用备选模型
            try:
                self.embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
                logger.info("使用备选嵌入模型")
            except Exception as e2:
                logger.error(f"加载备选模型也失败: {str(e2)}")
                raise RuntimeError("无法加载任何嵌入模型")
        
        # 初始化文档索引元数据存储
        self.metadata_path = os.path.join(self.persist_directory, "document_metadata.json")
        self.document_metadata = self._load_metadata()
        
        # 初始化ChromaDB客户端 - 更新为新的API
        try:
            # 使用新的API方式创建客户端
            self.client = chromadb.PersistentClient(
                path=self.persist_directory
            )
            logger.info("使用新版ChromaDB API创建客户端")
        except Exception as e:
            logger.warning(f"使用新版API创建ChromaDB客户端失败: {str(e)}，尝试使用旧版API")
            try:
                # 兼容旧版本
                self.client = chromadb.Client(Settings(
                    persist_directory=self.persist_directory,
                    anonymized_telemetry=False
                ))
                logger.info("使用旧版ChromaDB API创建客户端")
            except Exception as e2:
                logger.error(f"创建ChromaDB客户端失败: {str(e2)}")
                raise RuntimeError(f"无法创建ChromaDB客户端: {str(e2)}")
        
        # 创建LangChain的Chroma实例
        self._init_langchain_chroma()
        
        # 确保集合存在
        self._ensure_collection()
    
    def _init_langchain_chroma(self):
        """初始化LangChain的Chroma实例"""
        try:
            collection_name = f"repo_{self.repository_id}" if self.repository_id else "default"
            
            # 新版API
            self.langchain_chroma = Chroma(
                client=self.client,
                collection_name=collection_name,
                embedding_function=self.embeddings
            )
            logger.info(f"已初始化LangChain Chroma: {collection_name}")
        except Exception as e:
            logger.error(f"初始化LangChain Chroma失败: {str(e)}")
            raise e
    
    def _load_metadata(self) -> Dict[str, Any]:
        """加载文档元数据"""
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载元数据文件失败: {str(e)}")
                return {"documents": {}}
        return {"documents": {}}
    
    def _save_metadata(self):
        """保存文档元数据"""
        try:
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.document_metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存元数据文件失败: {str(e)}")
    
    def _ensure_collection(self):
        """确保集合存在"""
        try:
            collection_name = f"repo_{self.repository_id}" if self.repository_id else "default"
            # 检查集合是否存在
            try:
                self.collection = self.client.get_collection(name=collection_name)
                logger.info(f"获取到已存在的集合: {collection_name}")
            except Exception:
                # 集合不存在，创建新集合
                self.collection = self.client.create_collection(name=collection_name)
                logger.info(f"创建新集合: {collection_name}")
        except Exception as e:
            logger.error(f"创建集合时出错: {str(e)}")
            raise e
    
    async def add_documents(self, documents: List[Document], source_file: str, document_id: Optional[int] = None):
        """添加文档到向量存储
        
        Args:
            documents: 文档列表
            source_file: 源文件路径
            document_id: 数据库中的文档ID，用于关联
        """
        try:
            # 创建集合名称
            collection_name = f"repo_{self.repository_id}" if self.repository_id else "default"
            logger.info(f"添加文档到集合: {collection_name}，文档数: {len(documents)}")
            
            # 处理文档对象，确保都是Document类型
            processed_documents = []
            for doc in documents:
                # 检查是否为有效的Document对象
                if isinstance(doc, str):
                    # 转换字符串为Document对象
                    from langchain.schema import Document as LangchainDocument
                    doc = LangchainDocument(
                        page_content=doc,
                        metadata={
                            "source": os.path.basename(source_file),
                            "document_id": document_id,
                            "repository_id": self.repository_id
                        }
                    )
                
                # 确保元数据存在
                if not hasattr(doc, 'metadata') or doc.metadata is None:
                    doc.metadata = {}
                    
                # 确保元数据中保留知识库ID和仓库ID
                doc.metadata["repository_id"] = self.repository_id
                if document_id:
                    doc.metadata["document_id"] = document_id
                
                # 确保文档有page_content属性
                if not hasattr(doc, 'page_content'):
                    doc.page_content = str(doc)
                    
                # 应用元数据过滤 - 修正传递的参数，应该传递整个doc对象
                try:
                    from langchain_community.vectorstores.utils import filter_complex_metadata
                    # 创建新的元数据字典，防止修改原始对象
                    if isinstance(doc, tuple):
                        # 如果是元组，可能是(document, score)格式
                        logger.info("检测到元组格式的文档，尝试提取Document对象")
                        if len(doc) > 0 and hasattr(doc[0], 'metadata'):
                            # 使用元组中的Document对象
                            filtered_metadata = filter_complex_metadata(doc[0])
                            doc.metadata = filtered_metadata
                        else:
                            # 如果无法处理，使用空元数据
                            doc.metadata = {}
                    else:
                        # 正常处理Document对象
                        filtered_metadata = filter_complex_metadata(doc)
                        # 确保过滤后的元数据是字典
                        if not isinstance(filtered_metadata, dict):
                            filtered_metadata = {}
                        # 将过滤后的元数据分配给文档
                        doc.metadata = filtered_metadata
                except Exception as e:
                    logger.error(f"过滤元数据时出错: {str(e)}，使用空元数据")
                    # 如果过滤失败，使用空元数据
                    doc.metadata = {}
                
                processed_documents.append(doc)
            
            # 使用已创建的langchain_chroma实例添加文档
            if processed_documents:
                self.langchain_chroma.add_documents(processed_documents)
                logger.info(f"已添加 {len(processed_documents)} 个文档到 {collection_name}")
            else:
                logger.warning("没有有效的文档可以添加")
                return {"status": "warning", "message": "没有有效的文档可以添加"}
            
            # 更新元数据
            file_name = os.path.basename(source_file)
            kb_id = None
            # 从第一个文档中获取知识库ID（如果有）
            if processed_documents and processed_documents[0].metadata and "knowledge_base_id" in processed_documents[0].metadata:
                kb_id = processed_documents[0].metadata["knowledge_base_id"]
                
            self.document_metadata["documents"][file_name] = {
                "path": source_file,
                "chunks_count": len(processed_documents),
                "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "repository_id": self.repository_id,
                "document_id": document_id,
                "knowledge_base_id": kb_id
            }
            self._save_metadata()
            
            return {
                "status": "success",
                "document_id": document_id or file_name,
                "chunks_count": len(processed_documents)
            }
            
        except Exception as e:
            logger.error(f"添加文档时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise e
    
    async def search(self, query: str, k: int = 5, knowledge_base_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """搜索相关文档
        
        Args:
            query: 搜索查询
            k: 返回结果数量
            knowledge_base_id: 知识库ID，用于过滤文档
            
        Returns:
            相关文档列表
        """
        try:
            # 确定集合名称
            collection_name = f"repo_{self.repository_id}" if self.repository_id else "default"
            logger.info(f"在集合 {collection_name} 中搜索: {query}")
            
            # 使用已创建的langchain_chroma实例进行搜索
            documents = self.langchain_chroma.similarity_search_with_score(query, k=k*2)  # 查询更多结果，以便过滤后仍有足够的结果
            
            # 格式化结果
            results = []
            for doc, score in documents:
                # 如果指定了知识库ID，过滤不属于该知识库的文档
                if knowledge_base_id is not None:
                    doc_kb_id = doc.metadata.get("knowledge_base_id")
                    # 如果文档没有知识库ID或知识库ID不匹配，则跳过
                    if doc_kb_id is None or int(doc_kb_id) != int(knowledge_base_id):
                        logger.info(f"过滤掉不属于知识库 {knowledge_base_id} 的文档，该文档知识库ID: {doc_kb_id}")
                        continue
                
                results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score)
                })
                
                # 如果已经有足够的结果，则停止
                if len(results) >= k:
                    break
            
            logger.info(f"找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"搜索文档时出错: {str(e)}")
            raise e
    
    async def get_document_list(self, repository_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取已处理的文档列表
        
        Args:
            repository_id: 可选的仓库ID过滤
        """
        try:
            documents = []
            for doc_id, metadata in self.document_metadata["documents"].items():
                # 如果指定了仓库ID，只返回对应仓库的文档
                if repository_id is not None and metadata.get("repository_id") != repository_id:
                    continue
                    
                documents.append({
                    "id": doc_id,
                    "path": metadata["path"],
                    "chunks_count": metadata["chunks_count"],
                    "added_at": metadata.get("added_at", "未知"),
                    "repository_id": metadata.get("repository_id"),
                    "document_id": metadata.get("document_id")
                })
            return documents
        except Exception as e:
            logger.error(f"获取文档列表时出错: {str(e)}")
            raise e 