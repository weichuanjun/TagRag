from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging

from models import get_db, KnowledgeBase
from graph_store import GraphStore

router = APIRouter(prefix="/graph", tags=["graph-visualization"])
logger = logging.getLogger(__name__)

@router.get("/data/{knowledge_base_id}")
async def get_graph_data(knowledge_base_id: int, db: Session = Depends(get_db)):
    """获取知识库的完整图数据（节点和边）"""
    try:
        # 验证知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
        
        # 获取图存储实例
        graph_store = GraphStore(knowledge_base_id=knowledge_base_id)
        
        # 获取图数据，格式化为前端可用格式
        nodes, links = await graph_store.get_visualization_data()
        
        return {
            "nodes": nodes,
            "links": links
        }
    except Exception as e:
        logger.error(f"获取图数据时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取图数据失败: {str(e)}")

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
        
        # 获取图存储实例
        graph_store = GraphStore(knowledge_base_id=knowledge_base_id)
        
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