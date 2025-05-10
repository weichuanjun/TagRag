import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from models import CodeRepository, CodeComponent
from vector_store import VectorStore
from langchain.schema import Document

logger = logging.getLogger(__name__)

class CodeRetrievalService:
    """代码检索服务，负责在向量数据库中搜索和检索代码片段"""
    
    def __init__(self, db_session: Session):
        """初始化代码检索服务
        
        Args:
            db_session: SQLAlchemy会话对象，用于数据库操作
        """
        self.db_session = db_session
    
    async def retrieve_code_by_query(
        self, 
        query: str, 
        repository_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """基于用户查询检索相关代码
        
        Args:
            query: 用户查询
            repository_id: 仓库ID，如不指定则在所有代码仓库中搜索
            top_k: 返回结果数量
            
        Returns:
            List[Dict]: 包含相关代码片段的结果列表
        """
        logger.info(f"代码检索: 查询='{query}', 仓库ID={repository_id}, top_k={top_k}")
        
        # 获取代码库对应的知识库ID
        knowledge_base_id = None
        if repository_id:
            repo = self.db_session.query(CodeRepository).filter(CodeRepository.id == repository_id).first()
            if repo:
                # 优先使用关联的知识库ID，如果没有则使用仓库ID
                knowledge_base_id = repo.knowledge_base_id or repository_id
                logger.info(f"代码库 {repository_id} 对应的知识库ID为: {knowledge_base_id}")
        
        # 创建向量存储实例，优先使用knowledge_base_id
        vector_store = None
        if knowledge_base_id:
            vector_store = VectorStore(knowledge_base_id=knowledge_base_id)
            logger.info(f"使用知识库ID {knowledge_base_id} 创建向量存储")
        elif repository_id:
            # 兼容旧代码，如果没有knowledge_base_id但有repository_id
            vector_store = VectorStore(repository_id=repository_id)
            logger.info(f"使用仓库ID {repository_id} 创建向量存储 (兼容模式)")
        else:
            vector_store = VectorStore()
            logger.info("使用默认向量存储")
        
        try:
            # 构建元数据过滤条件，限定只搜索代码类型的文档
            metadata_filter = {"content_type": "code"}
            
            # 在向量数据库中检索
            search_results = await vector_store.search(
                query=query, 
                k=top_k, 
                metadata_filter=metadata_filter
            )
            
            # 格式化结果
            formatted_results = []
            for result in search_results:
                # 从结果中提取组件ID
                component_id = result.get("metadata", {}).get("component_id")
                
                if component_id:
                    # 查询数据库以获取完整的组件信息，并加载关联的file
                    component = self.db_session.query(CodeComponent).options(
                        joinedload(CodeComponent.file)
                    ).filter(
                        CodeComponent.id == component_id
                    ).first()
                    
                    if component:
                        formatted_results.append({
                            "id": component.id,
                            "file_path": component.file.file_path if component.file else None,
                            "name": component.name,
                            "type": component.type,
                            "code": component.code,
                            "signature": component.signature,
                            "start_line": component.start_line,
                            "end_line": component.end_line,
                            "similarity_score": result.get("score", 0),
                            "repository_id": component.repository_id
                        })
            
            logger.info(f"代码检索完成，找到 {len(formatted_results)} 个结果")
            return formatted_results
            
        except Exception as e:
            logger.error(f"代码检索失败: {str(e)}")
            return []
    
    async def extract_code_keywords(self, query: str) -> List[str]:
        """从用户查询中提取与代码相关的关键词
        
        Args:
            query: 用户查询文本
        
        Returns:
            List[str]: 提取的关键词列表
        """
        # 简单实现，提取所有单词
        keywords = query.split()
        if len(keywords) > 2:
            # 返回前3个词作为代码关键词
            return keywords[:3]
        return keywords 