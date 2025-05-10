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
from langchain_community.vectorstores.utils import filter_complex_metadata

# 导入配置
from config import EMBEDDING_MODEL, VECTOR_DB_DIR

logger = logging.getLogger(__name__)

class VectorStore:
    """向量存储管理类，处理文档的存储和检索"""
    
    def __init__(self, repository_id: Optional[int] = None, knowledge_base_id: Optional[int] = None):
        """
        初始化向量存储
        
        Args:
            repository_id: 代码库ID，如果指定则创建特定代码库的向量存储
            knowledge_base_id: 知识库ID，如果指定，优先使用它来确定集合名称
        """
        # 保存输入的参数
        self.repository_id = repository_id
        self.knowledge_base_id = knowledge_base_id
        
        # 确定存储目录和集合名称
        # 优先使用 knowledge_base_id 来确定集合
        if knowledge_base_id is not None:
            self.persist_directory = os.path.join(VECTOR_DB_DIR, f"kb_{knowledge_base_id}")
            self.effective_id_for_collection = f"kb_{knowledge_base_id}"
            logger.info(f"使用知识库ID {knowledge_base_id} 创建向量存储")
        elif repository_id is not None:
            self.persist_directory = os.path.join(VECTOR_DB_DIR, f"repo_{repository_id}")
            self.effective_id_for_collection = f"repo_{repository_id}"
            logger.info(f"使用仓库ID {repository_id} 创建向量存储")
        else:
            self.persist_directory = os.path.join(VECTOR_DB_DIR, "default")
            self.effective_id_for_collection = "default"
            logger.info("使用默认向量存储")
            
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
            collection_name = self.effective_id_for_collection
            self.collection_name = collection_name # Assign to instance attribute
            
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
            # collection_name is already set in _init_langchain_chroma, or we can re-calculate it
            # For consistency, let's use the self.collection_name if available, 
            # or ensure it's set if this method is called independently (though it shouldn't be)
            if not hasattr(self, 'collection_name') or not self.collection_name:
                self.collection_name = self.effective_id_for_collection
            
            # 检查集合是否存在
            try:
                self.collection = self.client.get_collection(name=self.collection_name)
                logger.info(f"获取到已存在的集合: {self.collection_name}")
            except Exception:
                # 集合不存在，创建新集合
                self.collection = self.client.create_collection(name=self.collection_name)
                logger.info(f"创建新集合: {self.collection_name}")
        except Exception as e:
            logger.error(f"创建集合时出错: {str(e)}")
            raise e
    
    async def add_documents(self, documents: List[Document], source_file: Optional[str] = None, document_id: Optional[int] = None) -> Dict[str, Any]:
        """添加文档到向量存储
        
        Args:
            documents: Langchain Document 对象的列表，其 metadata 应该已经包含了 token_count, structural_type, tag_ids 等.
            source_file: 源文件路径 (可选, 主要用于元数据记录)
            document_id: 数据库中的文档ID (可选, 主要用于元数据记录)
        """
        logger.info(f"Adding {len(documents)} documents to collection: {self.collection_name}")
        # Ensure metadata is clean for ChromaDB
        processed_documents_lc: List[Document] = [] # Rename to avoid confusion with input `documents` if it was different
        for doc_input in documents: # Assuming input `documents` is already List[Document]
            if not isinstance(doc_input, Document):
                logger.warning(f"Skipping non-Document object: {type(doc_input)}")
                continue
            # No complex filtering needed here if DocumentProcessor already prepared clean metadata dicts.
            # The issue is HOW Langchain Chroma wrapper itself handles the dicts with lists.
            # However, the error *explicitly* suggests using filter_complex_metadata.
            # This function expects a Document object and cleans ITS metadata.
            
            # Create a new Document object for filter_complex_metadata to operate on, using a copy of original meta
            # This step seems redundant if doc_input.metadata is already what we want to filter.
            # Let's assume doc_input are the Langchain Documents from DocumentProcessor
            # and their metadata field is what needs filtering *before* passing to add_texts.
            processed_documents_lc.append(doc_input) 

        if not processed_documents_lc:
            logger.warning("No valid Langchain Document objects to process after initial check.")
            return {"status": "warning", "message": "No valid Langchain Document objects."}

        try:
            texts = [doc.page_content for doc in processed_documents_lc]
            
            # Prepare IDs and cleaned metadatas
            ids = []
            final_metadatas_for_chroma = []
            for i, doc_lc in enumerate(processed_documents_lc):
                if not isinstance(doc_lc, Document):
                    logger.warning(f"Item at index {i} is not a Document object, it is {type(doc_lc)}. Skipping.")
                    continue

                original_meta = doc_lc.metadata if doc_lc.metadata else {}
                doc_id_val = original_meta.get('document_id', f'unknown_doc_{i}')
                chunk_idx_val = original_meta.get('chunk_index', i)
                ids.append(f"{doc_id_val}_{chunk_idx_val}")
                
                # Manual metadata cleaning: Only keep scalar values.
                manually_cleaned_meta = {}
                for k, v in original_meta.items():
                    if isinstance(v, (str, int, float, bool)) or v is None: # ChromaDB allows None for scalar types
                        manually_cleaned_meta[k] = v
                
                final_metadatas_for_chroma.append(manually_cleaned_meta)

            if not hasattr(self, 'langchain_chroma') or self.langchain_chroma is None:
                logger.error("LangChain Chroma instance is not initialized.")
                return {"status": "error", "message": "LangChain Chroma instance is not initialized."}

            self.langchain_chroma.add_texts(
                texts=texts,
                metadatas=final_metadatas_for_chroma, # Use the list of cleaned metadata dicts
                ids=ids
            )
            logger.info(f"Successfully added {len(texts)} documents to {self.collection_name} using Langchain wrapper.")
            
            # Update a simplified local metadata store if source_file and document_id are provided
            if source_file and document_id:
                file_name_key = f"{os.path.basename(source_file)}_{document_id}"
                kb_id_from_docs = None
                if processed_documents_lc and processed_documents_lc[0].metadata.get("knowledge_base_id"):
                     kb_id_from_docs = processed_documents_lc[0].metadata["knowledge_base_id"]

                self.document_metadata["documents"][file_name_key] = {
                    "path": source_file,
                    "db_document_id": document_id,
                    "chunks_count_in_this_batch": len(processed_documents_lc),
                    "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "repository_id": self.repository_id,
                    "knowledge_base_id": kb_id_from_docs
                }
                self._save_metadata()
            
            return {
                "status": "success",
                "count": len(processed_documents_lc)
            }
        except Exception as e:
            logger.error(f"Error adding documents to Chroma: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    async def update_tags_for_document_chunks(self, document_id: int, new_overall_tag_ids: List[int]):
        """
        Updates the 'tag_ids' metadata for all chunks of a given document_id in ChromaDB.
        """
        logger.info(f"Attempting to update tag_ids for document_id {document_id} to {new_overall_tag_ids} in collection {self.collection_name}")
        try:
            # Retrieve all chunks belonging to the document_id
            # We need their ChromaDB internal IDs and current metadatas
            retrieved_chunks = self.client.get(
                where={"document_id": document_id}, # Assumes document_id is stored as int
                include=["metadatas"] # We need IDs and existing metadatas
            )
            
            chunk_chroma_ids_to_update = retrieved_chunks.get('ids')
            existing_metadatas_list = retrieved_chunks.get('metadatas')

            if not chunk_chroma_ids_to_update:
                logger.info(f"No chunks found in vector store for document_id {document_id} to update tags.")
                return {"status": "not_found", "message": "No chunks found for the document."}

            if len(chunk_chroma_ids_to_update) != len(existing_metadatas_list):
                logger.error(f"Mismatch between number of IDs ({len(chunk_chroma_ids_to_update)}) and metadatas ({len(existing_metadatas_list)}) for doc {document_id}.")
                return {"status": "error", "message": "Internal error: ID and metadata count mismatch."}

            updated_full_metadatas_for_chroma = []
            for current_meta_dict in existing_metadatas_list:
                # Start with a copy of the existing metadata for the chunk
                meta_copy = current_meta_dict.copy() if current_meta_dict else {}
                
                # Update the 'tag_ids' field
                if new_overall_tag_ids: # If there are new tags, update/add the field
                    meta_copy["tag_ids"] = new_overall_tag_ids
                elif "tag_ids" in meta_copy: # If new_overall_tag_ids is empty, remove the field
                    del meta_copy["tag_ids"]
                
                # Clean the potentially updated metadata again to ensure ChromaDB compatibility
                # This reuses the cleaning logic similar to add_documents
                final_meta_for_chunk_update = {}
                for k, v in meta_copy.items():
                    if isinstance(v, (str, int, float, bool)):
                        final_meta_for_chunk_update[k] = v
                    elif k == 'tag_ids' and isinstance(v, list):
                        if v and all(isinstance(item, (str, int, float, bool)) for item in v):
                            final_meta_for_chunk_update[k] = v
                    elif isinstance(v, list) and all(isinstance(item, (str, int, float, bool)) for item in v):
                        if v: 
                           final_meta_for_chunk_update[k] = v
                updated_full_metadatas_for_chroma.append(final_meta_for_chunk_update)
            
            if chunk_chroma_ids_to_update:
                self.client.update(
                    ids=chunk_chroma_ids_to_update,
                    metadatas=updated_full_metadatas_for_chroma
                )
                logger.info(f"Successfully updated tag_ids for {len(chunk_chroma_ids_to_update)} chunks of document_id {document_id} in collection {self.collection_name}.")
                return {"status": "success", "updated_chunks": len(chunk_chroma_ids_to_update)}
            else: # Should be caught by the earlier check, but as a safeguard
                logger.info(f"No chunk IDs to update for document_id {document_id} after processing.")
                return {"status": "no_action", "message": "No chunks to update after processing."}

        except Exception as e:
            logger.error(f"Error updating tags in vector store for document_id {document_id}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    async def search(self, query: str, k: int = 5, knowledge_base_id: Optional[int] = None, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """搜索相关文档
        
        Args:
            query: 搜索查询
            k: 返回结果数量
            knowledge_base_id: 知识库ID，用于定位正确的集合，优先级高于初始化时的repository_id
            metadata_filter: (Optional) ChromaDB metadata filter dictionary
            
        Returns:
            List of dictionaries, each containing 'content', 'metadata', and 'score'
        """
        try:
            # 如果传入了新的 knowledge_base_id，并且与初始化时的不同，
            # 需要创建一个新的 VectorStore 实例用于搜索
            if knowledge_base_id is not None and knowledge_base_id != self.knowledge_base_id:
                logger.info(f"搜索时指定了不同的知识库ID {knowledge_base_id}，为其创建专用的VectorStore实例")
                temp_vector_store = VectorStore(knowledge_base_id=knowledge_base_id)
                return await temp_vector_store.search(query, k, knowledge_base_id, metadata_filter)
            
            logger.info(f"执行搜索: query='{query[:50]}...', k={k}, collection='{self.collection_name}'")
            
            # 预处理标签过滤器，改为OR逻辑
            final_filter = None
            if metadata_filter:
                # 检查是否是标签过滤器（form: {"tag_X": True, "tag_Y": True}）
                tag_filters = [k for k in metadata_filter.keys() if k.startswith("tag_")]
                
                if tag_filters:
                    # 使用OR条件将多个标签过滤器组合
                    or_conditions = []
                    for tag_key in tag_filters:
                        or_conditions.append({tag_key: metadata_filter[tag_key]})
                    
                    # 转换为ChromaDB支持的$or格式
                    if len(or_conditions) > 1:
                        final_filter = {"$or": or_conditions}
                    else:
                        final_filter = or_conditions[0]
                    
                    logger.info(f"使用标签过滤器: {final_filter}")
                else:
                    # 非标签过滤器，转换为ChromaDB支持的格式
                    # ChromaDB要求使用$eq等操作符
                    if metadata_filter:
                        conditions = []
                        for key, value in metadata_filter.items():
                            conditions.append({key: {"$eq": value}})
                        
                        if len(conditions) > 1:
                            final_filter = {"$and": conditions}
                        else:
                            final_filter = conditions[0]
                    else:
                        final_filter = metadata_filter
                    logger.info(f"使用非标签过滤器: {final_filter}")
            
            # 如果设置了知识库ID，确保在过滤条件中
            if self.knowledge_base_id is not None:
                kb_condition = {"knowledge_base_id": {"$eq": self.knowledge_base_id}}
                
                if final_filter:
                    # 合并过滤条件
                    if "$and" in final_filter:
                        # 如果已经是$and条件，添加到条件列表中
                        final_filter["$and"].append(kb_condition)
                    elif "$or" in final_filter:
                        # 如果是$or条件，使用$and包装$or和kb_condition
                        final_filter = {"$and": [final_filter, kb_condition]}
                    else:
                        # 如果是单个条件，创建$and数组
                        final_filter = {"$and": [final_filter, kb_condition]}
                else:
                    # 只有知识库条件
                    final_filter = kb_condition
                
                logger.info(f"添加知识库过滤条件后的最终过滤器: {final_filter}")
            
            # 定义一个内部函数来执行实际的搜索，以便重用代码
            async def _execute_search_in_collection(langchain_chroma_instance, log_prefix=""):
                try:
                    if query:  # 语义搜索
                        logger.info(f"{log_prefix} 执行语义搜索")
                        results = langchain_chroma_instance.similarity_search_with_score(
                            query,
                            k=k,
                            filter=final_filter
                        )
                    elif final_filter:  # 仅基于过滤器的搜索
                        logger.info(f"{log_prefix} 执行基于过滤器的搜索 (无查询)")
                        dummy_query = " "
                        results = langchain_chroma_instance.similarity_search_with_score(
                            dummy_query,
                            k=k,
                            filter=final_filter
                        )
                    else:  # 无查询和无过滤器
                        logger.warning(f"{log_prefix} 搜索既无查询又无过滤器")
                        return []
                    
                    logger.info(f"{log_prefix} 获取到 {len(results)} 个结果")
                    
                    # 处理结果
                    processed_results = []
                    for doc, score in results:
                        doc_content = ""
                        if isinstance(doc, Document) and hasattr(doc, 'page_content') and doc.page_content is not None:
                            doc_content = str(doc.page_content)
                        elif isinstance(doc, dict) and 'page_content' in doc and doc['page_content'] is not None:
                            doc_content = str(doc['page_content'])
                        
                        doc_metadata = {}
                        if isinstance(doc, Document) and hasattr(doc, 'metadata') and doc.metadata is not None:
                            doc_metadata = doc.metadata
                        elif isinstance(doc, dict) and 'metadata' in doc and doc['metadata'] is not None:
                            doc_metadata = doc['metadata']
                        
                        # 收集文档中的标签键
                        tag_keys = [k for k in doc_metadata.keys() if k.startswith("tag_")]
                        
                        processed_results.append({
                            "text": doc_content,
                            "metadata": doc_metadata,
                            "score": score,
                            "tag_keys": tag_keys  # 添加标签键列表，方便调试
                        })
                    
                    if processed_results:
                        logger.info(f"{log_prefix} 成功处理 {len(processed_results)} 个结果")
                    else:
                        logger.info(f"{log_prefix} 没有处理出有效结果")
                    
                    return processed_results
                
                except Exception as e:
                    logger.error(f"{log_prefix} 执行搜索时出错: {str(e)}", exc_info=True)
                    return []
            
            # 执行搜索
            logger.info(f"在集合 '{self.collection_name}' 中搜索")
            current_results = await _execute_search_in_collection(self.langchain_chroma, "[当前集合]")
            
            # 返回当前集合中的结果
            logger.info(f"在当前集合中找到 {len(current_results)} 个结果，直接返回")
            return current_results
            
        except Exception as e:
            logger.error(f"搜索过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
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

    async def delete_document_chunks(self, document_id: int) -> Dict[str, Any]:
        """删除指定文档ID的所有块从向量存储中"
        
        Args:
            document_id: 要删除其块的文档ID。
            
        Returns:
            一个包含操作状态的字典。
        """
        logger.info(f"VECTOR_STORE: Attempting to delete all chunks for document_id: {document_id} from collection: {self.collection_name}")
        try:
            if not hasattr(self, 'collection') or self.collection is None:
                logger.error(f"VECTOR_STORE: Chroma collection '{self.collection_name}' is not initialized.")
                return {"status": "error", "message": "Collection not initialized."}

            # ChromaDB's delete method uses a 'where' filter similar to 'get'.
            # We need to find the ChromaDB internal IDs first if 'delete' doesn't directly support where filters for non-ID fields robustly,
            # or if we want to log exactly which IDs are being deleted.
            # However, modern Chroma versions support deleting by a 'where' filter directly.
            
            # Let's try direct deletion with a 'where' filter.
            # The metadata field storing the document_id is assumed to be 'document_id'.
            self.collection.delete(where={"document_id": document_id})
            # The delete operation in ChromaDB doesn't typically return the count of deleted items directly.
            # To confirm, one might 'get' before and after, but for this operation, we'll assume success if no error.
            
            logger.info(f"VECTOR_STORE: Successfully submitted delete request for chunks of document_id: {document_id} in collection: {self.collection_name}.")
            # Update local metadata cache if this document was tracked
            # This part needs careful consideration of the key format in self.document_metadata
            keys_to_delete_from_meta = [key for key, meta_val in self.document_metadata["documents"].items() if meta_val.get("db_document_id") == document_id]
            for key in keys_to_delete_from_meta:
                del self.document_metadata["documents"][key]
                logger.info(f"VECTOR_STORE: Removed document_id {document_id} (key: {key}) from local metadata cache.")
            if keys_to_delete_from_meta:
                self._save_metadata()

            return {"status": "success", "message": f"All chunks for document_id {document_id} requested for deletion."}

        except Exception as e:
            logger.error(f"VECTOR_STORE: Error deleting chunks for document_id {document_id}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)} 

    async def get_all_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """诊断功能：直接获取向量存储中的所有文档，以便检查存储状况
        
        Args:
            limit: 最大返回文档数
            
        Returns:
            List of documents with their metadata
        """
        try:
            if not hasattr(self, 'collection') or self.collection is None:
                logger.error(f"Collection '{self.collection_name}' not initialized")
                return []
                
            logger.info(f"尝试获取集合 '{self.collection_name}' 中的所有文档 (限制 {limit} 条)")
            
            # 直接从ChromaDB获取所有文档 (无过滤器)
            try:
                # 尝试使用 get_all 方法或类似方法获取所有文档
                # 注意：不同版本的ChromaDB API可能有所不同
                all_docs = self.collection.get(
                    limit=limit,
                    include=["metadatas", "documents", "embeddings"]
                )
                
                if not all_docs:
                    logger.info(f"集合 '{self.collection_name}' 中没有找到文档")
                    return []
                    
                # 处理获取到的文档
                results = []
                ids = all_docs.get('ids', [])
                metadatas = all_docs.get('metadatas', [])
                documents = all_docs.get('documents', [])
                
                for i in range(min(len(ids), len(metadatas), len(documents))):
                    doc_id = ids[i]
                    metadata = metadatas[i] or {}
                    content = documents[i] or ""
                    
                    # 检查标签格式
                    tag_keys = [k for k in metadata.keys() if k.startswith("tag_")]
                    
                    results.append({
                        "id": doc_id,
                        "text": content[:200] + "..." if len(content) > 200 else content,
                        "metadata": metadata,
                        "tag_keys": tag_keys,
                        "knowledge_base_id": metadata.get("knowledge_base_id"),
                        "document_id": metadata.get("document_id")
                    })
                
                logger.info(f"成功获取 {len(results)} 个文档从集合 '{self.collection_name}'")
                return results
                
            except Exception as e:
                logger.error(f"获取集合 '{self.collection_name}' 文档时出错: {e}", exc_info=True)
                return []
                
        except Exception as e:
            logger.error(f"执行get_all_documents时发生错误: {e}", exc_info=True)
            return [] 