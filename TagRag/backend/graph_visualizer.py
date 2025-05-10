from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging

from models import get_db, KnowledgeBase, Tag
from graph_store import GraphStore

router = APIRouter(prefix="/graph", tags=["graph-visualization"])
logger = logging.getLogger(__name__)

@router.get("/data/{knowledge_base_id}")
async def get_graph_data(
    knowledge_base_id: int, 
    tag_types: Optional[str] = Query(None, description="筛选的标签类型，以逗号分隔"),
    db: Session = Depends(get_db)
):
    """获取知识库的完整图数据（节点和边）
    
    可选参数:
    - tag_types: 筛选特定类型的标签，多个类型以逗号分隔，如"API,字段,功能"
    """
    try:
        # 验证知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
        
        # 获取图存储实例，传递数据库会话
        graph_store = GraphStore(knowledge_base_id=knowledge_base_id, db=db)
        
        # 解析标签类型筛选条件
        filter_types = None
        if tag_types:
            filter_types = [t.strip() for t in tag_types.split(",") if t.strip()]
        
        # 获取图数据，格式化为前端可用格式
        nodes, links = await graph_store.get_visualization_data(tag_types=filter_types)
        
        return {
            "nodes": nodes,
            "links": links
        }
    except Exception as e:
        logger.error(f"获取图数据时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取图数据失败: {str(e)}")

@router.get("/tag-data/{knowledge_base_id}")
async def get_tag_graph_data(
    knowledge_base_id: int, 
    tag_types: Optional[str] = Query(None, description="筛选的标签类型，以逗号分隔"),
    db: Session = Depends(get_db)
):
    """获取知识库的标签图数据，只包含标签节点和关系
    
    可选参数:
    - tag_types: 筛选特定类型的标签，多个类型以逗号分隔，如"API,字段,功能"
    """
    try:
        # 验证知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
        
        # 获取图存储实例，传递数据库会话
        graph_store = GraphStore(knowledge_base_id=knowledge_base_id, db=db)
        
        # 强制只显示标签和内容
        only_tags = True
        
        # 解析标签类型筛选条件
        filter_types = None
        if tag_types:
            filter_types = [t.strip() for t in tag_types.split(",") if t.strip()]
        
        # 获取图数据，格式化为前端可用格式
        nodes, links = await graph_store.get_visualization_data(tag_types=filter_types, only_tags=only_tags)
        
        return {
            "nodes": nodes,
            "links": links
        }
    except Exception as e:
        logger.error(f"获取标签图数据时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取标签图数据失败: {str(e)}")

@router.get("/tag-types/{knowledge_base_id}")
async def get_tag_types(knowledge_base_id: int, db: Session = Depends(get_db)):
    """获取知识库中所有标签的类型列表"""
    try:
        # 验证知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
        
        # 查询与该知识库相关的文档
        documents = kb.documents
        
        # 收集所有标签
        all_tags = []
        for doc in documents:
            for tag in doc.tags:
                if tag not in all_tags:
                    all_tags.append(tag)
        
        # 提取不同的标签类型
        tag_types = set()
        for tag in all_tags:
            if tag.tag_type:
                tag_types.add(tag.tag_type)
        
        # 按字母顺序排序
        sorted_types = sorted(list(tag_types))
        
        return {"tag_types": sorted_types}
    except Exception as e:
        logger.error(f"获取标签类型列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取标签类型列表失败: {str(e)}")

@router.get("/search")
async def search_graph(
    query: str,
    knowledge_base_id: int,
    max_depth: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db)
):
    """搜索图中的实体并返回关联数据"""
    try:
        # 验证知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
        
        # 获取图存储实例，传递数据库会话
        graph_store = GraphStore(knowledge_base_id=knowledge_base_id, db=db)
        
        # 在图中搜索实体
        nodes, links = await graph_store.search_entities(query, max_depth)
        
        return {
            "nodes": nodes,
            "links": links
        }
    except Exception as e:
        logger.error(f"搜索图数据时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索图数据失败: {str(e)}")

@router.post("/extract")
async def extract_entities(
    text: str,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """从文本中提取实体和关系（测试用）"""
    try:
        # 简单的实体提取实现
        # 将文本按空格分词，作为简单实体
        words = [w for w in text.split() if len(w) > 1]
        
        # 创建基本实体
        entities = []
        for i, word in enumerate(words):
            if len(word) > 2:  # 忽略过短的词
                entities.append({
                    "id": f"entity_{i}",
                    "label": word,
                    "type": "WORD",
                    "description": f"从文本中提取的词: {word}"
                })
        
        # 简单关系提取（相邻实体）
        relations = []
        for i in range(len(entities)-1):
            relations.append({
                "source": entities[i]["id"],
                "target": entities[i+1]["id"],
                "type": "next_to",
                "strength": 0.5
            })
        
        # 如果提供了知识库ID，保存到图存储
        if knowledge_base_id:
            kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
            if not kb:
                raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
            
            graph_store = GraphStore(knowledge_base_id=knowledge_base_id)
            await graph_store.add_entities(entities)
            await graph_store.add_relations(relations)
        
        return {
            "entities": entities,
            "relations": relations
        }
    except Exception as e:
        logger.error(f"提取实体时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"提取实体失败: {str(e)}") 