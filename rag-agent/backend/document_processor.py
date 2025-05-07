import os
import pandas as pd
from typing import List, Dict, Any, Optional, Union
from langchain_community.document_loaders import (
    TextLoader, 
    PyPDFLoader, 
    CSVLoader,
    UnstructuredExcelLoader,
    UnstructuredMarkdownLoader,
    UnstructuredHTMLLoader,
    UnstructuredPowerPointLoader,
    Docx2txtLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_community.vectorstores.utils import filter_complex_metadata
import warnings
import logging
from sqlalchemy.orm import Session
from models import Document as DBDocument, DocumentChunk
import datetime
import tempfile
import json
import re
import traceback

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

class DocumentProcessor:
    """处理各种文档格式并进行分块处理的类"""
    
    def __init__(self, vector_store=None):
        # 文本分割配置
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.vector_store = vector_store
        
        # 文档加载器映射
        self.loaders = {
            '.txt': TextLoader,
            '.pdf': PyPDFLoader,
            '.docx': Docx2txtLoader,
            '.csv': CSVLoader,
            '.xlsx': UnstructuredExcelLoader,
            '.xls': UnstructuredExcelLoader,
            '.md': UnstructuredMarkdownLoader,
            '.html': UnstructuredHTMLLoader,
            '.htm': UnstructuredHTMLLoader,
            '.pptx': UnstructuredPowerPointLoader,
            '.ppt': UnstructuredPowerPointLoader,
        }
    
    def ensure_document(self, obj: Any, metadata: Dict[str, Any] = None) -> Document:
        """确保对象是Document类型，如果不是则转换为Document对象
        
        Args:
            obj: 要检查或转换的对象
            metadata: 要添加的元数据
            
        Returns:
            Document对象
        """
        try:
            # 如果已经是Document对象，只需要更新元数据
            if isinstance(obj, Document):
                if metadata and isinstance(metadata, dict):
                    # 确保元数据存在
                    if not hasattr(obj, 'metadata') or obj.metadata is None:
                        obj.metadata = {}
                    # 合并新的元数据
                    obj.metadata.update(metadata)
                return obj
                
            # 如果是字符串，创建新的Document对象
            if isinstance(obj, str):
                return Document(
                    page_content=obj,
                    metadata=metadata or {}
                )
                
            # 如果是其他类型，尝试转换为字符串
            try:
                content = str(obj)
                return Document(
                    page_content=content,
                    metadata=metadata or {}
                )
            except:
                # 如果转换失败，返回错误信息
                return Document(
                    page_content="[无法解析的内容]",
                    metadata=metadata or {}
                )
        except Exception as e:
            # 即使在处理过程中出现异常，也返回有效的Document对象
            logger.error(f"确保Document对象时出错: {str(e)}")
            return Document(
                page_content="[处理错误]",
                metadata=metadata or {"error": str(e)}
            )
    
    async def process_document(self, file_path: str, repository_id: int, db: Session, chunk_size: int = 1000, knowledge_base_id: Optional[int] = None):
        """处理文档并添加到向量存储和数据库
        
        Args:
            file_path: 文件路径
            repository_id: 代码库ID
            db: 数据库会话
            chunk_size: 块大小
            knowledge_base_id: 知识库ID
            
        Returns:
            处理结果
        """
        # 更新文本分割器的块大小
        self.text_splitter.chunk_size = chunk_size
        logger.info(f"处理文档: {file_path}, 仓库ID: {repository_id}, 知识库ID: {knowledge_base_id}, 块大小: {chunk_size}")
        
        # 创建数据库文档记录
        db_document = DBDocument(
            path=file_path,
            source=os.path.basename(file_path),
            document_type=os.path.splitext(file_path)[1].lower(),
            knowledge_base_id=knowledge_base_id,
            repository_id=repository_id
        )
        
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        
        document_id = db_document.id
        
        try:
            # 使用统一的方法来处理所有文档类型
            documents = await self._load_and_process_document(file_path, document_id, repository_id, db, knowledge_base_id)
            
            # 如果没有提取到任何有效文档，抛出错误
            if not documents or len(documents) == 0:
                raise Exception(f"未能从文档中提取有效内容: {file_path}")
            
            # 添加到向量存储
            from vector_store import VectorStore, Document as VectorDocument
            vector_store = VectorStore(repository_id)
            
            # 确保所有文档对象的元数据都被过滤和有效
            vector_documents = []
            for doc in documents:
                # 确保是Document对象
                doc = self.ensure_document(doc, {
                    "source": os.path.basename(file_path),
                    "document_id": document_id,
                    "knowledge_base_id": knowledge_base_id if knowledge_base_id else None,
                    "repository_id": repository_id
                })
                
                # 注意：filter_complex_metadata期望接收整个Document对象，而不是metadata字典
                # 所以我们直接将处理后的doc传递给它
                from langchain_community.vectorstores.utils import filter_complex_metadata
                try:
                    # 创建包含过滤元数据的新Document对象
                    filtered_doc = VectorDocument(
                        page_content=doc.page_content,
                        metadata=filter_complex_metadata(doc)  # 正确传递整个doc对象
                    )
                    vector_documents.append(filtered_doc)
                except Exception as e:
                    logger.error(f"过滤元数据时出错: {str(e)}")
                    # 如果过滤失败，尝试创建一个带有空元数据的文档
                    filtered_doc = VectorDocument(
                        page_content=doc.page_content,
                        metadata={}
                    )
                    vector_documents.append(filtered_doc)
            
            # 添加到向量存储
            await vector_store.add_documents(vector_documents, file_path, document_id)
            
            # 确保所有传递给图存储的文档都是有效的Document对象，不是字符串
            # 如果启用了图存储，提取并存储实体和关系 - 使用vector_documents而不是从_load_and_process_document返回的documents
            if knowledge_base_id:  # 仅当指定了知识库时才处理图存储
                try:
                    self._extract_and_store_entities(vector_documents, document_id, repository_id, knowledge_base_id)
                except Exception as e:
                    # 捕获图存储错误但不中断主流程
                    logger.error(f"图存储处理时出错: {str(e)}")
                    logger.error(traceback.format_exc())
            
            return {
                "status": "success",
                "document_id": document_id,
                "chunks": len(vector_documents),
                "source": os.path.basename(file_path)
            }
            
        except Exception as e:
            logger.error(f"处理文档时出错: {str(e)}")
            logger.error(traceback.format_exc())
            # 回滚事务
            db.rollback()
            # 删除文档记录
            db.query(DBDocument).filter(DBDocument.id == document_id).delete()
            db.commit()
            
            raise e
    
    async def _load_and_process_document(self, file_path: str, document_id: int, repository_id: int, db: Session, knowledge_base_id: Optional[int] = None):
        """统一的文档加载和处理方法"""
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            # 特殊处理Excel文件
            if ext in ['.xlsx', '.xls']:
                return await self._process_excel_simple(file_path, document_id, knowledge_base_id)
            
            # 特殊处理CSV文件
            if ext == '.csv':
                return await self._process_csv_simple(file_path, document_id, knowledge_base_id)
            
            # 特殊处理Markdown文件
            if ext == '.md':
                return await self._process_text_file(file_path, document_id, knowledge_base_id)
            
            # 其他文件尝试使用标准加载器，如果失败则使用文本加载器
            try:
                if ext in self.loaders:
                    loader_class = self.loaders[ext]
                    loader = loader_class(file_path)
                    documents = loader.load()
                else:
                    # 未知类型使用文本加载器
                    loader = TextLoader(file_path, encoding='utf-8')
                    documents = loader.load()
                    
                # 分割文档
                chunks = self.text_splitter.split_documents(documents)
                
                # 添加必要的元数据
                for chunk in chunks:
                    if not chunk.metadata:
                        chunk.metadata = {}
                    chunk.metadata["document_id"] = document_id
                    if knowledge_base_id:
                        chunk.metadata["knowledge_base_id"] = knowledge_base_id
                
                # 存储到数据库
                await self._save_chunks_to_db(chunks, document_id, db)
                
                # 确保返回非空列表
                if not chunks:
                    # 如果没有文档块，创建一个默认文档
                    doc = Document(
                        page_content="[空文档内容]",
                        metadata={
                            "source": os.path.basename(file_path),
                            "document_id": document_id,
                            "knowledge_base_id": knowledge_base_id if knowledge_base_id else None
                        }
                    )
                    return [doc]
                
                return chunks
                
            except Exception as e:
                logger.error(f"使用标准加载器失败: {str(e)}，尝试使用简单文本加载")
                # 所有方法失败，尝试直接读取文件内容
                return await self._process_text_file(file_path, document_id, knowledge_base_id)
                
        except Exception as e:
            logger.error(f"处理文档时发生严重错误: {str(e)}")
            # 即使所有方法都失败，也返回一个Document对象而不是抛出异常
            doc = Document(
                page_content=f"[文档处理失败: {str(e)}]",
                metadata={
                    "source": os.path.basename(file_path),
                    "document_id": document_id,
                    "error": str(e),
                    "knowledge_base_id": knowledge_base_id if knowledge_base_id else None
                }
            )
            return [doc]
    
    async def _process_text_file(self, file_path: str, document_id: int, knowledge_base_id: Optional[int] = None):
        """简单文本文件处理方法，适用于任何文本格式"""
        logger.info(f"使用简单文本处理方法处理文件: {file_path}")
        
        try:
            # 尝试不同的编码读取文件
            content = None
            encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    # 如果读取成功，跳出循环
                    break
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，尝试二进制模式
            if content is None:
                with open(file_path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='ignore')
            
            # 分割文本
            chunks = self.text_splitter.split_text(content)
            
            # 转换为Document对象
            documents = []
            for i, chunk_text in enumerate(chunks):
                metadata = {
                    "source": os.path.basename(file_path),
                    "document_id": document_id,
                    "chunk_index": i
                }
                
                if knowledge_base_id:
                    metadata["knowledge_base_id"] = knowledge_base_id
                    
                doc = Document(
                    page_content=chunk_text,
                    metadata=metadata
                )
                documents.append(doc)
            
            # 确保返回非空列表
            if not documents:
                # 如果没有文档块，创建一个包含整个内容的文档
                doc = Document(
                    page_content=content,
                    metadata={
                        "source": os.path.basename(file_path),
                        "document_id": document_id,
                        "knowledge_base_id": knowledge_base_id if knowledge_base_id else None
                    }
                )
                documents.append(doc)
                
            return documents
        
        except Exception as e:
            logger.error(f"处理文本文件时出错: {str(e)}")
            # 如果处理失败，仍然创建一个空文档以避免返回空列表
            doc = Document(
                page_content="[无法解析的文档内容]",
                metadata={
                    "source": os.path.basename(file_path),
                    "document_id": document_id,
                    "error": str(e),
                    "knowledge_base_id": knowledge_base_id if knowledge_base_id else None
                }
            )
            return [doc]
    
    async def _process_csv_simple(self, file_path: str, document_id: int, knowledge_base_id: Optional[int] = None):
        """简化版CSV文件处理"""
        logger.info(f"使用简化方法处理CSV文件: {file_path}")
        
        try:
            # 先尝试直接读取为文本
            return await self._process_text_file(file_path, document_id, knowledge_base_id)
        except Exception as e:
            logger.error(f"处理CSV为文本失败: {str(e)}")
            raise e
    
    async def _process_excel_simple(self, file_path: str, document_id: int, knowledge_base_id: Optional[int] = None):
        """简化版Excel文件处理"""
        logger.info(f"使用简化方法处理Excel文件: {file_path}")
        
        try:
            # 读取Excel文件
            excel_file = pd.ExcelFile(file_path)
            all_documents = []
            
            # 处理每个工作表
            for sheet_name in excel_file.sheet_names:
                try:
                    df = excel_file.parse(sheet_name)
                    
                    # 将DataFrame转换为文本表格
                    table_text = df.to_string(index=False)
                    
                    # 创建文档
                    content = f"# 工作表: {sheet_name}\n\n{table_text}"
                    
                    # 分割文本
                    chunks = self.text_splitter.split_text(content)
                    
                    # 转换为Document对象
                    for i, chunk_text in enumerate(chunks):
                        metadata = {
                            "source": os.path.basename(file_path),
                            "sheet_name": sheet_name,
                            "document_id": document_id,
                            "chunk_index": i
                        }
                        
                        if knowledge_base_id:
                            metadata["knowledge_base_id"] = knowledge_base_id
                            
                        doc = Document(
                            page_content=chunk_text,
                            metadata=metadata
                        )
                        all_documents.append(doc)
                except Exception as sheet_error:
                    logger.error(f"处理工作表 {sheet_name} 出错: {str(sheet_error)}")
                    # 继续处理其他工作表
                    continue
            
            # 如果没有成功处理任何工作表，抛出错误
            if len(all_documents) == 0:
                raise Exception("无法从Excel文件中提取有效内容")
                
            return all_documents
            
        except Exception as e:
            logger.error(f"处理Excel文件时出错: {str(e)}")
            # 尝试作为文本文件处理
            logger.info("尝试将Excel文件作为文本文件处理")
            return await self._process_text_file(file_path, document_id, knowledge_base_id)
    
    async def _save_chunks_to_db(self, chunks, document_id, db):
        """将文档块保存到数据库"""
        for i, chunk in enumerate(chunks):
            try:
                content = chunk.page_content
                # 如果内容太短，跳过
                if len(content.strip()) < 10:
                    continue
                
                # 获取元数据
                metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}
                
                # 处理页码
                page = metadata.get('page', None)
                
                # 创建块记录
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    content=content,
                    chunk_index=i,
                    chunk_metadata=json.dumps(metadata),
                    page=page
                )
                
                db.add(db_chunk)
            except Exception as e:
                logger.error(f"保存块 {i} 到数据库时出错: {str(e)}")
                # 继续处理其他块
                continue
                
        # 提交事务
        db.commit()

    def _extract_and_store_entities(self, documents, document_id, repository_id, knowledge_base_id):
        """从文档中提取实体并存储到图数据库
        
        这是一个简单的实现，实际应用中应使用NER或LLM进行更复杂的处理
        
        Args:
            documents: 向量文档列表
            document_id: 文档ID
            repository_id: 仓库ID
            knowledge_base_id: 知识库ID
        """
        try:
            # 如果知识库ID为空，不进行图存储
            if not knowledge_base_id:
                return
                
            # 导入图存储类
            from graph_store import GraphStore
            
            # 创建图存储实例
            graph_store = GraphStore(repository_id=repository_id, knowledge_base_id=knowledge_base_id)
            
            # 简单实体提取示例 (实际应用应使用更复杂的NER)
            entities = []
            relations = []
            entity_ids = set()  # 跟踪已创建的实体ID
            
            for i, doc in enumerate(documents):
                # 确保doc是Document对象
                doc = self.ensure_document(doc, {
                    "source": f"document_{document_id}",
                    "document_id": document_id,
                    "repository_id": repository_id,
                    "knowledge_base_id": knowledge_base_id
                })
                
                # 为文档创建一个实体
                doc_entity_id = f"doc_{document_id}_{i}"
                
                # 安全地获取元数据
                metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                source = metadata.get('source', '')
                page = metadata.get('page', '')
                sheet = metadata.get('sheet_name', '')
                
                # 构建源信息
                source_info = source
                if page:
                    source_info += f" (页码: {page})"
                if sheet:
                    source_info += f" (工作表: {sheet})"
                
                # 获取文本内容
                doc_content = doc.page_content
                
                # 创建文档实体
                doc_entity = {
                    "id": doc_entity_id,
                    "label": f"文档片段: {source}",
                    "type": "DOCUMENT",
                    "description": doc_content[:100] + "..." if len(doc_content) > 100 else doc_content,
                    "source": source_info,
                    "document_id": document_id
                }
                entities.append(doc_entity)
                entity_ids.add(doc_entity_id)
                
                # 提取关键词/短语
                # 这里使用简单的正则表达式，实际应用应使用更复杂的NLP方法
                keywords = set()
                
                # 匹配可能的关键词: 中文词汇、英文单词、数字等
                patterns = [
                    r'[\u4e00-\u9fa5]{2,6}',  # 2-6个中文字符
                    r'[A-Za-z]{5,15}',  # 5-15个英文字符
                    r'\d+[.\d]*'  # 数字（含小数）
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, doc_content)
                    for match in matches:
                        # 简单过滤一些常见词
                        if len(match) > 2 and match.lower() not in ["the", "and", "for", "that", "with"]:
                            keywords.add(match)
                
                # 为每个关键词创建实体和关系
                for keyword in list(keywords)[:10]:  # 限制每个文档最多10个关键词
                    # 创建唯一ID
                    keyword_id = f"kw_{keyword}_{knowledge_base_id}"
                    
                    # 如果是新的关键词，添加实体
                    if keyword_id not in entity_ids:
                        keyword_entity = {
                            "id": keyword_id,
                            "label": keyword,
                            "type": "KEYWORD",
                            "description": f"从文档中提取的关键词: {keyword}"
                        }
                        entities.append(keyword_entity)
                        entity_ids.add(keyword_id)
                    
                    # 创建关系
                    relation = {
                        "source": doc_entity_id,
                        "target": keyword_id,
                        "type": "CONTAINS",
                        "strength": 1.0
                    }
                    relations.append(relation)
            
            # 批量添加到图存储
            if entities:
                import asyncio
                
                # 修复事件循环问题 - 使用task创建方式而不是创建新的循环
                # 检查当前是否有运行的事件循环
                try:
                    # 尝试获取当前事件循环
                    current_loop = asyncio.get_event_loop()
                    
                    # 如果当前事件循环正在运行，使用create_task而不是run_until_complete
                    if current_loop.is_running():
                        logger.info("使用当前运行的事件循环")
                        # 创建任务但不等待完成 - 这是一个非阻塞操作
                        asyncio.create_task(graph_store.add_entities(entities, document_id))
                        asyncio.create_task(graph_store.add_relations(relations))
                    else:
                        # 如果当前循环未运行，可以使用run_until_complete
                        logger.info("使用当前未运行的事件循环")
                        current_loop.run_until_complete(graph_store.add_entities(entities, document_id))
                        current_loop.run_until_complete(graph_store.add_relations(relations))
                except RuntimeError:
                    # 如果无法获取当前循环，则使用备用方法
                    logger.info("无法获取事件循环，使用备用方法")
                    # 图存储不是关键功能，可以跳过或使用同步方法
                    pass
                
                logger.info(f"已为文档 {document_id} 添加 {len(entities)} 个实体和 {len(relations)} 个关系到图存储")
                
        except Exception as e:
            logger.error(f"提取和存储实体时出错: {str(e)}")
            logger.error(traceback.format_exc())
            # 这里不抛出异常，避免影响主流程 