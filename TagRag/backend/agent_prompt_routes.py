from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from .models import get_db, AgentPrompt, KnowledgeBase
from .config import AGENT_PROMPTS  # 导入默认提示词配置

router = APIRouter(prefix="/agent-prompts", tags=["agent-prompts"])

logger = logging.getLogger(__name__)

# 初始化默认提示词
def initialize_default_prompts(db: Session):
    """初始化默认提示词配置到数据库"""
    try:
        # 检查是否已有记录
        existing_count = db.query(AgentPrompt).count()
        if existing_count > 0:
            logger.info(f"数据库中已有 {existing_count} 个提示词配置，跳过初始化")
            return
        
        # 添加默认配置
        for agent_type, prompt_template in AGENT_PROMPTS.items():
            default_prompt = AgentPrompt(
                name=f"默认{agent_type}提示词",
                description=f"{agent_type}的默认提示词配置",
                agent_type=agent_type,
                prompt_template=prompt_template,
                is_default=True,
                knowledge_base_id=None  # 全局默认
            )
            db.add(default_prompt)
        
        db.commit()
        logger.info(f"成功初始化 {len(AGENT_PROMPTS)} 个默认提示词配置")
    except Exception as e:
        logger.error(f"初始化默认提示词配置时出错: {str(e)}")
        db.rollback()

@router.get("/")
async def get_agent_prompts(
    knowledge_base_id: Optional[int] = None,
    agent_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取Agent提示词列表，可按知识库ID和Agent类型过滤"""
    # 确保有默认提示词
    initialize_default_prompts(db)
    
    query = db.query(AgentPrompt)
    
    if knowledge_base_id is not None:
        query = query.filter(
            (AgentPrompt.knowledge_base_id == knowledge_base_id) | 
            (AgentPrompt.knowledge_base_id == None)
        )
    
    if agent_type:
        query = query.filter(AgentPrompt.agent_type == agent_type)
    
    prompts = query.all()
    
    return [{
        "id": prompt.id,
        "name": prompt.name,
        "description": prompt.description,
        "agent_type": prompt.agent_type,
        "prompt_template": prompt.prompt_template,
        "is_default": prompt.is_default,
        "knowledge_base_id": prompt.knowledge_base_id,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None
    } for prompt in prompts]

@router.get("/{prompt_id}")
async def get_agent_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """获取特定ID的Agent提示词"""
    prompt = db.query(AgentPrompt).filter(AgentPrompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="找不到指定的Agent提示词")
    
    return {
        "id": prompt.id,
        "name": prompt.name,
        "description": prompt.description,
        "agent_type": prompt.agent_type,
        "prompt_template": prompt.prompt_template,
        "is_default": prompt.is_default,
        "knowledge_base_id": prompt.knowledge_base_id,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None
    }

@router.post("/")
async def create_agent_prompt(
    data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """创建新的Agent提示词"""
    # 如果设置为默认，检查同类型是否已有默认提示词
    if data.get("is_default"):
        existing_default = db.query(AgentPrompt).filter(
            AgentPrompt.agent_type == data.get("agent_type"),
            AgentPrompt.is_default == True,
            AgentPrompt.knowledge_base_id == data.get("knowledge_base_id")
        ).first()
        
        if existing_default:
            existing_default.is_default = False
            db.commit()
    
    # 如果指定了知识库，验证其存在性
    if data.get("knowledge_base_id"):
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == data.get("knowledge_base_id")).first()
        if not kb:
            raise HTTPException(status_code=404, detail="指定的知识库不存在")
    
    # 创建新提示词
    new_prompt = AgentPrompt(
        name=data.get("name"),
        description=data.get("description"),
        agent_type=data.get("agent_type"),
        prompt_template=data.get("prompt_template"),
        is_default=data.get("is_default", False),
        knowledge_base_id=data.get("knowledge_base_id")
    )
    
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)
    
    return {
        "id": new_prompt.id,
        "name": new_prompt.name,
        "description": new_prompt.description,
        "agent_type": new_prompt.agent_type,
        "prompt_template": new_prompt.prompt_template,
        "is_default": new_prompt.is_default,
        "knowledge_base_id": new_prompt.knowledge_base_id,
        "created_at": new_prompt.created_at.isoformat() if new_prompt.created_at else None,
        "updated_at": new_prompt.updated_at.isoformat() if new_prompt.updated_at else None
    }

@router.put("/{prompt_id}")
async def update_agent_prompt(
    prompt_id: int,
    data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """更新特定ID的Agent提示词"""
    prompt = db.query(AgentPrompt).filter(AgentPrompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="找不到指定的Agent提示词")
    
    # 如果设置为默认且之前不是默认，处理其他默认提示词
    if data.get("is_default") and not prompt.is_default:
        existing_default = db.query(AgentPrompt).filter(
            AgentPrompt.agent_type == data.get("agent_type", prompt.agent_type),
            AgentPrompt.is_default == True,
            AgentPrompt.knowledge_base_id == data.get("knowledge_base_id", prompt.knowledge_base_id),
            AgentPrompt.id != prompt_id
        ).first()
        
        if existing_default:
            existing_default.is_default = False
    
    # 如果指定了知识库，验证其存在性
    if "knowledge_base_id" in data and data["knowledge_base_id"] is not None:
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == data["knowledge_base_id"]).first()
        if not kb:
            raise HTTPException(status_code=404, detail="指定的知识库不存在")
    
    # 更新提示词字段
    for key, value in data.items():
        if hasattr(prompt, key):
            setattr(prompt, key, value)
    
    db.commit()
    db.refresh(prompt)
    
    return {
        "id": prompt.id,
        "name": prompt.name,
        "description": prompt.description,
        "agent_type": prompt.agent_type,
        "prompt_template": prompt.prompt_template,
        "is_default": prompt.is_default,
        "knowledge_base_id": prompt.knowledge_base_id,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None
    }

@router.delete("/{prompt_id}")
async def delete_agent_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """删除特定ID的Agent提示词"""
    prompt = db.query(AgentPrompt).filter(AgentPrompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="找不到指定的Agent提示词")
    
    db.delete(prompt)
    db.commit()
    
    return {"status": "success", "message": "成功删除Agent提示词"}

@router.get("/for-kb/{knowledge_base_id}")
async def get_prompts_for_knowledge_base(
    knowledge_base_id: int,
    agent_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取特定知识库的Agent提示词，如果不存在则返回默认提示词"""
    # 验证知识库是否存在
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="指定的知识库不存在")
    
    # 基本查询条件
    condition = (
        (AgentPrompt.knowledge_base_id == knowledge_base_id) | 
        (AgentPrompt.knowledge_base_id == None)
    )
    
    # 添加类型过滤
    if agent_type:
        condition = condition & (AgentPrompt.agent_type == agent_type)
    
    # 获取所有匹配的提示词
    prompts = db.query(AgentPrompt).filter(condition).all()
    
    # 处理结果
    result = []
    for prompt in prompts:
        result.append({
            "id": prompt.id,
            "name": prompt.name,
            "description": prompt.description,
            "agent_type": prompt.agent_type,
            "prompt_template": prompt.prompt_template,
            "is_default": prompt.is_default,
            "knowledge_base_id": prompt.knowledge_base_id,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None
        })
    
    return result

@router.get("/agent-types")
async def get_agent_types():
    """获取所有可用的Agent类型"""
    # 从配置中获取Agent类型
    agent_types = list(AGENT_PROMPTS.keys())
    return {"agent_types": agent_types} 