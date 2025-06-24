import os
import logging
from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import Optional, List, Dict, Any
from datetime import datetime

from .models import get_db, KnowledgeBase, CodeRepository, Document, User
from .auth import get_current_active_user

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(
    prefix="/knowledge-bases",
    tags=["knowledge_bases"]
)

@router.get("")
async def list_knowledge_bases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """获取当前用户组织的所有知识库列表"""
    try:
        # 查询当前用户组织的所有知识库
        knowledge_bases = db.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == current_user.organization_id
        ).all()
        
        # 手动计算每个知识库的代码库和文档数量
        result = []
        for kb in knowledge_bases:
            # 计算代码库数量
            repo_count = db.query(CodeRepository).filter(
                CodeRepository.knowledge_base_id == kb.id
            ).count()
            
            # 计算文档数量 - 如果documents表中没有knowledge_base_id列，则返回0
            try:
                doc_count = db.query(Document).filter(
                    Document.knowledge_base_id == kb.id
                ).count()
            except:
                # 如果查询失败，说明列不存在
                doc_count = 0
            
            result.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "created_at": kb.created_at.isoformat(),
                "repository_count": repo_count,
                "document_count": doc_count
            })
            
        return result
    except Exception as e:
        logger.error(f"获取知识库列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")

@router.post("")
async def create_knowledge_base(
    name: str = Body(...),
    description: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """为当前用户组织创建新的知识库"""
    try:
        # 创建知识库并关联到当前用户的组织
        kb = KnowledgeBase(
            name=name,
            description=description,
            organization_id=current_user.organization_id
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)
        
        return {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "created_at": kb.created_at.isoformat(),
            "repository_count": 0,
            "document_count": 0
        }
    except Exception as e:
        db.rollback()
        logger.error(f"创建知识库时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")

@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """删除指定ID的知识库，会校验知识库是否属于当前用户的组织"""
    try:
        # 查找属于当前用户组织的知识库
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.organization_id == current_user.organization_id
        ).first()
        
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{kb_id}的知识库或权限不足")
        
        # 删除知识库
        db.delete(kb)
        db.commit()
        
        return {"message": f"知识库 '{kb.name}' 已成功删除"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除知识库时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")

@router.get("/{kb_id}/repositories")
async def list_knowledge_base_repositories(
    kb_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """获取知识库中的所有代码库"""
    try:
        # 查找知识库
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.organization_id == current_user.organization_id
        ).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{kb_id}的知识库或权限不足")
        
        # 查询知识库中的代码库
        repositories = db.query(CodeRepository).filter(
            CodeRepository.knowledge_base_id == kb_id
        ).all()
        
        # 统计每个代码库的组件数量
        result = []
        for repo in repositories:
            # 计算组件数量
            component_count = 0  # 这里可以添加实际的组件计数查询
            
            result.append({
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "added_at": repo.added_at.isoformat(),
                "component_count": component_count,
                "status": repo.status
            })
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库代码库列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取知识库代码库列表失败: {str(e)}")

@router.get("/{kb_id}/documents")
async def list_knowledge_base_documents(
    kb_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """获取知识库中的所有文档"""
    try:
        # 查找知识库
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.organization_id == current_user.organization_id
        ).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{kb_id}的知识库或权限不足")
        
        # 尝试查询知识库中的文档
        try:
            documents = db.query(Document).filter(
                Document.knowledge_base_id == kb_id
            ).all()
        except Exception as e:
            logger.warning(f"查询文档时出错，可能是documents表中没有knowledge_base_id列: {str(e)}")
            documents = []  # 如果出错，返回空列表
        
        # 格式化结果
        result = []
        for doc in documents:
            result.append({
                "id": doc.id,
                "name": os.path.basename(doc.path),
                "path": doc.path,
                "added_at": doc.added_at.isoformat(),
                "chunks_count": doc.chunks_count
            })
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库文档列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取知识库文档列表失败: {str(e)}") 