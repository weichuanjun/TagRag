from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import logging
import re
from sqlalchemy import text
import time

from .models import get_db, Tag, Document, DocumentChunk, document_tags, document_chunk_tags, KnowledgeBase, TagDependency, User
from .config import get_autogen_config
from .auth import get_current_active_user

router = APIRouter(prefix="", tags=["tags-management"])
logger = logging.getLogger(__name__)

# 缓存机制
_cache = {
    "deletable_tags": {
        "data": None,
        "timestamp": 0,
        "ttl": 10 # 缓存10秒
    }
}

def get_cached_data(cache_key):
    """获取缓存数据，如果过期则返回None"""
    cache_entry = _cache.get(cache_key)
    if not cache_entry:
        return None
    
    if time.time() - cache_entry["timestamp"] > cache_entry["ttl"]:
        return None  # 缓存过期
    
    return cache_entry["data"]

def set_cached_data(cache_key, data, ttl=None):
    """设置缓存数据"""
    if cache_key not in _cache:
        _cache[cache_key] = {"data": None, "timestamp": 0, "ttl": 10}
    
    _cache[cache_key]["data"] = data
    _cache[cache_key]["timestamp"] = time.time()
    if ttl is not None:
        _cache[cache_key]["ttl"] = ttl

# LLM客户端 - 简化版本，使用与代码分析相同的模式
class LLMClient:
    """简单的大模型客户端，用于生成标签和摘要"""
    
    def __init__(self, config=None):
        self.config = config or get_autogen_config()
        self._results_cache = {}
    
    async def generate(self, prompt: str) -> str:
        """生成文本"""
        # 检查缓存
        if prompt in self._results_cache:
            logger.info("使用缓存的生成结果")
            return self._results_cache[prompt]
            
        try:
            # 配置API密钥
            if "config_list" in self.config and len(self.config["config_list"]) > 0:
                first_config = self.config["config_list"][0]
                api_key = first_config.get("api_key")
                api_base = first_config.get("api_base", "https://api.openai.com/v1")
                model = first_config.get("model", "gpt-3.5-turbo")
                temperature = self.config.get("temperature", 0.7)
                
                # 尝试使用新版API
                try:
                    # 新版OpenAI API (>=1.0.0)
                    from openai import OpenAI
                    logger.info("使用OpenAI新版API")
                    
                    client = OpenAI(api_key=api_key, base_url=api_base)
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "你是一个文档分析助手，负责分析文本内容并提取标签与摘要。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        max_tokens=800
                    )
                    result = response.choices[0].message.content
                    
                except (ImportError, AttributeError):
                    # 尝试旧版API
                    logger.info("尝试使用OpenAI旧版API")
                    import openai
                    
                    # 配置旧版API
                    openai.api_key = api_key
                    openai.api_base = api_base
                    
                    # 使用旧版ChatCompletion API
                    response = await openai.ChatCompletion.acreate(
                        model=model,
                        messages=[
                            {"role": "system", "content": "你是一个文档分析助手，负责分析文本内容并提取标签与摘要。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        max_tokens=800
                    )
                    result = response.choices[0].message.content
                
                # 缓存结果
                self._results_cache[prompt] = result
                return result
            else:
                return "未配置API密钥，无法生成标签和摘要"
        except Exception as e:
            logger.error(f"调用LLM API失败: {str(e)}")
            return f"标签生成失败: {str(e)}"

# 创建LLM客户端实例
llm_client = LLMClient()

@router.get("/tags")
async def get_all_tags(
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """获取所有标签，可选按知识库ID过滤"""
    try:
        org_id = current_user.organization_id
        query = db.query(Tag).filter(Tag.organization_id == org_id)
        
        # 如果指定了知识库ID，通过文档-标签关系过滤标签
        if knowledge_base_id is not None:
            # 首先获取该知识库下所有文档的ID
            doc_ids = db.query(Document.id).filter(Document.knowledge_base_id == knowledge_base_id).all()
            if not doc_ids:
                # 如果知识库没有文档，返回空列表
                return {"tags": []}
                
            # 将文档ID转换为列表
            doc_id_list = [doc_id[0] for doc_id in doc_ids]
            
            # 通过document_tags关联表过滤，只返回与这些文档关联的标签
            # 使用子查询找出与这些文档关联的标签ID
            from sqlalchemy import text
            tag_ids_query = f"""
                SELECT DISTINCT tag_id 
                FROM document_tags 
                WHERE document_id IN ({','.join(str(id) for id in doc_id_list)})
            """
            result = db.execute(text(tag_ids_query))
            tag_ids = [row[0] for row in result]
            
            if tag_ids:
                # 如果找到关联标签，筛选这些标签
                query = query.filter(Tag.id.in_(tag_ids))
            else:
                # 如果没有关联标签，返回空列表
                return {"tags": []}
        
        # 执行查询并返回所有标签
        tags = query.all()
        return {"tags": [
            {
                "id": tag.id, 
                "name": tag.name, 
                "color": tag.color, 
                "description": tag.description, 
                "parent_id": tag.parent_id,
                "hierarchy_level": tag.hierarchy_level,
                "tag_type": tag.tag_type if hasattr(tag, 'tag_type') else "general"
            } for tag in tags
        ]}
    except Exception as e:
        logger.error(f"获取标签列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取标签列表失败: {str(e)}")

@router.post("/tags")
async def create_tag(
    name: str = Body(...),
    color: str = Body("#1890ff"),
    description: Optional[str] = Body(None),
    parent_id: Optional[int] = Body(None),
    tag_type: Optional[str] = Body("general"),
    importance: Optional[float] = Body(0.5),
    related_content: Optional[str] = Body(None),
    hierarchy_level: Optional[str] = Body("leaf"),  # 新增层级参数，默认为叶节点
    is_system: Optional[bool] = Body(False),  # 新增是否为系统预设标签参数
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    创建新标签
    
    支持创建多个根标签（root），不再限制每种类型只能有一个根标签
    """
    try:
        # Check for existing tag *within the organization*
        existing_tag = db.query(Tag).filter(
            Tag.name == name, 
            Tag.organization_id == current_user.organization_id
        ).first()
        if existing_tag:
            return {"id": existing_tag.id, "name": existing_tag.name, "color": existing_tag.color}
        
        # 如果指定了父标签，检查是否存在
        if parent_id:
            parent_tag = db.query(Tag).filter(Tag.id == parent_id).first()
            if not parent_tag:
                raise HTTPException(status_code=404, detail=f"父标签ID {parent_id} 不存在")
            
            # 确定层级关系
            if parent_tag.hierarchy_level == "root":
                # 如果父标签是根标签，则当前标签为分支标签
                hierarchy_level = "branch"
            elif parent_tag.hierarchy_level == "branch":
                # 如果父标签是分支标签，则当前标签为叶标签
                hierarchy_level = "leaf"
        
        # 创建新标签
        tag = Tag(
            name=name,
            color=color,
            description=description,
            parent_id=parent_id,
            tag_type=tag_type,
            importance=importance,
            related_content=related_content,
            hierarchy_level=hierarchy_level,
            is_system=is_system,
            organization_id=current_user.organization_id
        )
        
        db.add(tag)
        db.commit()
        db.refresh(tag)
        
        return {"id": tag.id, "name": tag.name, "color": tag.color, "hierarchy_level": tag.hierarchy_level}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建标签失败: {str(e)}")

@router.post("/tags/system-roots")
async def create_system_root_tags(db: Session = Depends(get_db)):
    """创建系统预设的根标签，作为标签知识图谱的骨架"""
    try:
        # 预设根标签列表 - 可根据实际需要修改
        system_roots = [
            {"name": "技术领域", "color": "#1890ff", "tag_type": "domain", "description": "技术相关的领域标签"},
            {"name": "概念类型", "color": "#52c41a", "tag_type": "concept", "description": "反映文档中提到的概念类型"},
            {"name": "实体类别", "color": "#fa8c16", "tag_type": "entity", "description": "文档中提及的实体类别"},
            {"name": "关系类型", "color": "#722ed1", "tag_type": "relation", "description": "实体间的关系类别"},
            {"name": "操作类型", "color": "#eb2f96", "tag_type": "action", "description": "文档中描述的操作类型"},
        ]
        
        created_tags = []
        for root_info in system_roots:
            # 检查是否已存在
            existing = db.query(Tag).filter(
                Tag.name == root_info["name"],
                Tag.is_system == True,
                Tag.hierarchy_level == "root"
            ).first()
            
            if existing:
                created_tags.append({
                    "id": existing.id,
                    "name": existing.name,
                    "color": existing.color,
                    "tag_type": existing.tag_type,
                    "already_existed": True
                })
                continue
            
            # 创建新根标签
            root_tag = Tag(
                name=root_info["name"],
                color=root_info["color"],
                description=root_info.get("description"),
                tag_type=root_info["tag_type"],
                hierarchy_level="root",
                is_system=True,
                importance=1.0  # 根标签具有最高重要性
            )
            
            db.add(root_tag)
            db.flush()  # 获取ID但不提交事务
            
            created_tags.append({
                "id": root_tag.id,
                "name": root_tag.name,
                "color": root_tag.color,
                "tag_type": root_tag.tag_type,
                "already_existed": False
            })
        
        # 提交所有更改
        db.commit()
        
        return {"success": True, "root_tags": created_tags}
    except Exception as e:
        db.rollback()
        logger.error(f"创建系统根标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建系统根标签失败: {str(e)}")

@router.get("/tags/hierarchy")
async def get_tag_hierarchy(db: Session = Depends(get_db)):
    """获取标签层次结构，按根标签-分支标签-叶标签组织"""
    try:
        # 1. 获取所有根标签
        root_tags = db.query(Tag).filter(Tag.hierarchy_level == "root").all()
        
        result = []
        for root in root_tags:
            root_data = {
                "id": root.id,
                "name": root.name,
                "color": root.color,
                "tag_type": root.tag_type,
                "hierarchy_level": root.hierarchy_level,
                "is_system": root.is_system,
                "children": []
            }
            
            # 2. 获取根标签下的所有分支标签
            branch_tags = db.query(Tag).filter(Tag.parent_id == root.id).all()
            for branch in branch_tags:
                branch_data = {
                    "id": branch.id,
                    "name": branch.name,
                    "color": branch.color,
                    "tag_type": branch.tag_type,
                    "hierarchy_level": branch.hierarchy_level,
                    "children": []
                }
                
                # 3. 获取分支标签下的所有叶标签
                leaf_tags = db.query(Tag).filter(Tag.parent_id == branch.id).all()
                for leaf in leaf_tags:
                    branch_data["children"].append({
                        "id": leaf.id,
                        "name": leaf.name,
                        "color": leaf.color,
                        "tag_type": leaf.tag_type,
                        "hierarchy_level": leaf.hierarchy_level
                    })
                
                root_data["children"].append(branch_data)
            
            result.append(root_data)
        
        # 4. 获取未分类的标签（没有父标签，但不是根标签）
        uncategorized_tags = db.query(Tag).filter(
            Tag.parent_id == None,
            Tag.hierarchy_level != "root"
        ).all()
        
        if uncategorized_tags:
            result.append({
                "id": -1,  # 虚拟ID
                "name": "未分类标签",
                "color": "#8c8c8c",
                "hierarchy_level": "virtual",
                "children": [
                    {
                        "id": tag.id,
                        "name": tag.name,
                        "color": tag.color,
                        "tag_type": tag.tag_type,
                        "hierarchy_level": tag.hierarchy_level
                    }
                    for tag in uncategorized_tags
                ]
            })
        
        return {"hierarchy": result}
    except Exception as e:
        logger.error(f"获取标签层次结构失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取标签层次结构失败: {str(e)}")

@router.get("/tags/{tag_id}/can-delete")
async def can_delete_tag(
    tag_id: int,
    db: Session = Depends(get_db)
):
    """检查标签是否可以安全删除（无关联文档且无子标签）"""
    try:
        # 检查标签是否存在
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")
        
        # 检查是否有关联文档
        doc_count = db.query(document_tags).filter(document_tags.c.tag_id == tag_id).count()
        has_documents = doc_count > 0
        
        # 检查是否有子标签
        child_count = db.query(Tag).filter(Tag.parent_id == tag_id).count()
        has_children = child_count > 0
        
        # 构建返回结果
        result = {
            "can_delete": not has_documents and not has_children,
            "has_documents": has_documents,
            "has_children": has_children,
            "document_count": doc_count,
            "child_tag_count": child_count
        }
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查标签 {tag_id} 是否可删除时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查标签是否可删除失败: {str(e)}")

@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    force: bool = False,
    db: Session = Depends(get_db)
):
    """删除标签，并处理其在文档和块中的关联
    
    参数:
        tag_id: 要删除的标签ID
        force: 是否强制删除，设为True时忽略安全检查
    """
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")

        # 安全检查：不允许删除有子标签的父标签
        if not force:
            child_count = db.query(Tag).filter(Tag.parent_id == tag_id).count()
            if child_count > 0:
                raise HTTPException(
                    status_code=400, 
                    detail=f"标签 '{tag.name}' 有 {child_count} 个子标签，无法删除。请先删除所有子标签，或使用force=true参数强制删除"
                )

        # 1. 从 document_tags 中删除关联
        stmt_doc_tags = document_tags.delete().where(document_tags.c.tag_id == tag_id)
        db.execute(stmt_doc_tags)
        logger.info(f"已从 document_tags 中为 tag_id {tag_id} 删除关联")

        # 2. 从 document_chunk_tags 中删除关联
        stmt_chunk_tags = document_chunk_tags.delete().where(document_chunk_tags.c.tag_id == tag_id)
        db.execute(stmt_chunk_tags)
        logger.info(f"已从 document_chunk_tags 中为 tag_id {tag_id} 删除关联")
        
        # 3. 解除所有标签依赖关系
        db.query(TagDependency).filter(
            (TagDependency.source_tag_id == tag_id) | 
            (TagDependency.target_tag_id == tag_id)
        ).delete(synchronize_session=False)
        logger.info(f"已删除所有与标签ID {tag_id} 相关的依赖关系")
        
        # 4. 如果是强制删除，将所有子标签的parent_id设为null
        if force:
            child_tags = db.query(Tag).filter(Tag.parent_id == tag_id).all()
            for child_tag in child_tags:
                child_tag.parent_id = None
                # 如果子标签是branch但父标签是root，则子标签也变为root
                if child_tag.hierarchy_level == "branch" and tag.hierarchy_level == "root":
                    child_tag.hierarchy_level = "root"
            logger.info(f"已将所有子标签从父标签ID {tag_id} 解除关联")
        
        # 5. 将当前标签的parent_id设为null（解除与父标签的关系）
        tag.parent_id = None
        db.flush()
        
        # 6. 删除标签自身
        db.delete(tag)
        db.commit()
        
        return {"success": True, "message": f"标签 '{tag.name}' 及其所有关联已删除"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除标签 {tag_id} 失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除标签失败: {str(e)}")

# New internal helper function
async def _try_delete_orphaned_tag_after_document_removal(tag_id: int, db: Session):
    """
    尝试删除一个可能已成为孤立的标签。
    在文档被删除后，为其之前关联的每个标签调用此函数。
    """
    logger.info(f"检查标签ID {tag_id} 是否已成为孤立标签...")
    try:
        # 检查该标签是否还关联其他任何文档
        remaining_associations = db.query(document_tags).filter(document_tags.c.tag_id == tag_id).first()
        
        if remaining_associations:
            logger.info(f"标签ID {tag_id} 仍与其他文档关联，不删除。")
            return False # Not orphaned, not deleted
        else:
            logger.info(f"标签ID {tag_id} 已成为孤立标签，准备删除...")
            # 注意：delete_tag 是一个 FastAPI 路由操作函数，它期望 db 来自 Depends(get_db)。
            # 为了在内部调用它，我们需要确保它能接受一个 db session。
            # 当前的 delete_tag 定义是 async def delete_tag(tag_id: int, db: Session = Depends(get_db))
            # 这里的 db 参数可以直接传递。

            # 调用 delete_tag 来处理实际的删除逻辑 (包括从 chunk_tags 和 tags 表删除)
            # 因为 delete_tag 本身会 commit 或 rollback, 我们不需要在这里处理事务。
            # delete_tag 还会处理 HTTPException，这里可以捕获它或者让它冒泡。
            try:
                # We need to call delete_tag by passing the db session directly.
                # The Depends(get_db) in its signature is for FastAPI when called as an endpoint.
                # For an internal call, we provide the db session.
                
                # Since delete_tag is already an async function, we await it.
                # We need to simulate the dependency injection or ensure delete_tag can be called directly.
                # The current signature of delete_tag should allow direct call if db is provided.
                
                # Re-fetch tag for its name for the log message, as delete_tag expects it
                tag_to_delete = db.query(Tag).filter(Tag.id == tag_id).first()
                if not tag_to_delete:
                    logger.warning(f"尝试删除孤立标签时，标签ID {tag_id} 未找到 (可能已被并发操作删除)。")
                    return False # Tag was not found, so effectively not "deleted by this call"

                delete_response = await delete_tag(tag_id=tag_id, db=db) # Pass db session directly
                
                if delete_response.get("success"):
                    logger.info(f"孤立标签ID {tag_id} (名称: '{tag_to_delete.name}') 已成功删除。")
                    return True # Deleted
                else:
                    # This case might occur if delete_tag itself raises an HTTPException that gets caught by its own try-except
                    # or returns success: False.
                    logger.error(f"调用 delete_tag 删除孤立标签ID {tag_id} 失败，但未抛出异常。响应: {delete_response}")
                    return False # Not deleted due to internal issue in delete_tag

            except HTTPException as http_exc:
                # If delete_tag raises an HTTPException, log it and consider the tag not deleted by this attempt.
                logger.error(f"删除孤立标签ID {tag_id} 时 delete_tag 内部发生HTTPException: {http_exc.detail}")
                return False # Not deleted
            except Exception as e_inner_delete:
                # Catch any other unexpected error from delete_tag
                logger.error(f"调用 delete_tag 删除孤立标签ID {tag_id} 时发生意外错误: {e_inner_delete}", exc_info=True)
                # db.rollback() # delete_tag should handle its own rollback on error
                return False # Not deleted

    except Exception as e:
        logger.error(f"检查或删除孤立标签ID {tag_id} 时发生外部错误: {e}", exc_info=True)
        # db.rollback() # Rollback any changes if the check itself failed. delete_tag handles its own.
        return False # Not deleted

@router.get("/tags/document/{document_id}")
async def get_document_tags(
    document_id: int,
    db: Session = Depends(get_db)
):
    """获取文档的标签"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
        
        # 尝试获取标签
        try:
            tags = document.tags
            # 兼容处理：可能数据库中没有新增字段
            result_tags = []
            for tag in tags:
                tag_dict = {
                    "id": tag.id,
                    "name": tag.name,
                    "color": tag.color,
                    "description": tag.description
                }
                # 尝试获取新增字段，如果不存在则设为默认值
                try:
                    tag_dict["tag_type"] = tag.tag_type if hasattr(tag, 'tag_type') else "general"
                    tag_dict["importance"] = tag.importance if hasattr(tag, 'importance') else 0.5
                    tag_dict["related_content"] = tag.related_content if hasattr(tag, 'related_content') else None
                except:
                    pass
                result_tags.append(tag_dict)
            return {"tags": result_tags}
        except Exception as tag_error:
            # 如果是列不存在的错误，返回基本信息
            logger.error(f"获取标签详情时出错: {str(tag_error)}")
            # 使用直接SQL查询获取基本标签信息
            from sqlalchemy import text
            try:
                result = db.execute(text(f"""
                    SELECT t.id, t.name, t.color, t.description
                    FROM tags t
                    JOIN document_tags dt ON t.id = dt.tag_id
                    WHERE dt.document_id = {document_id}
                """))
                tags = []
                for row in result:
                    tags.append({
                        "id": row[0],
                        "name": row[1],
                        "color": row[2] or "#1890ff",
                        "description": row[3] or ""
                    })
                return {"tags": tags}
            except Exception as sql_error:
                logger.error(f"SQL查询标签失败: {str(sql_error)}")
                return {"tags": []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文档标签失败: {str(e)}")

@router.post("/tags/document/{document_id}")
async def add_tags_to_document(
    document_id: int,
    request_data: Any = Body(...),
    db: Session = Depends(get_db)
):
    """为文档添加标签"""
    try:
        # 检查请求数据格式，支持两种：
        # 1. 直接的标签ID数组：[1, 2, 3]
        # 2. 包含tag_ids键的对象：{"tag_ids": [1, 2, 3]}
        if isinstance(request_data, list):
            tag_ids = request_data
        elif isinstance(request_data, dict) and "tag_ids" in request_data:
            tag_ids = request_data["tag_ids"]
        else:
            logger.error(f"请求格式错误: {request_data}")
            raise HTTPException(status_code=400, detail="请求格式错误，期望标签ID数组或包含tag_ids键的对象")
        
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
        
        # 获取所有指定的标签
        tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
        if len(tags) != len(tag_ids):
            found_ids = [tag.id for tag in tags]
            missing_ids = [id for id in tag_ids if id not in found_ids]
            raise HTTPException(status_code=404, detail=f"标签ID {missing_ids} 不存在")
        
        # 添加标签到文档
        document.tags = tags
        db.commit()
        
        return {"success": True, "message": f"已为文档添加 {len(tags)} 个标签"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"为文档添加标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"为文档添加标签失败: {str(e)}")

@router.post("/tags/analyze-document/{document_id}")
async def analyze_document_for_tags(
    document_id: int,
    db: Session = Depends(get_db)
):
    """使用TF-IDF和大模型分析文档内容，自动生成标签并添加到文档"""
    try:
        # 查找文档
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
            
        # 获取文档所有块的内容
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        if not chunks:
            raise HTTPException(status_code=400, detail=f"文档没有可分析的内容块")
        
        # 收集所有内容
        all_content = [chunk.content for chunk in chunks if chunk.content]
        if not all_content:
            raise HTTPException(status_code=400, detail=f"文档内容为空")
        
        # 随机抽取一些内容块作为样本
        import random
        content_samples = random.sample(all_content, min(5, len(all_content)))
        
        # 步骤1: TF-IDF提取关键词
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # 将所有文本合并为一个文档
            full_document = " ".join(all_content)
            
            # 创建TF-IDF向量化器
            vectorizer = TfidfVectorizer(max_features=50, stop_words='english')
            
            # 对单个文档进行分析
            tfidf_matrix = vectorizer.fit_transform([full_document])
            
            # 获取特征名称(词汇)
            feature_names = vectorizer.get_feature_names_out()
            
            # 获取词汇的TF-IDF分数
            tfidf_scores = tfidf_matrix.toarray()[0]
            
            # 将词汇和它们的分数组合
            word_scores = list(zip(feature_names, tfidf_scores))
            
            # 按分数从高到低排序
            word_scores.sort(key=lambda x: x[1], reverse=True)
            
            # 提取分数最高的30个关键词
            top_keywords = [word for word, score in word_scores[:30]]
            
        except Exception as e:
            logger.error(f"TF-IDF关键词提取失败: {str(e)}")
            top_keywords = []
        
        # 使用所有关键词，交给大模型处理
        combined_keywords = top_keywords
        
        # 步骤2: 获取根标签作为提示
        root_tags = db.query(Tag).filter(Tag.hierarchy_level == "root").all()
        root_tag_prompts = []
        
        # 为每个根标签类型准备提示
        for root_tag in root_tags:
            tag_type_description = ""
            if root_tag.tag_type == "domain":
                tag_type_description = "技术领域或主题"
            elif root_tag.tag_type == "concept":
                tag_type_description = "概念类型"
            elif root_tag.tag_type == "entity":
                tag_type_description = "实体类别"
            elif root_tag.tag_type == "relation":
                tag_type_description = "关系类型"
            elif root_tag.tag_type == "action":
                tag_type_description = "操作类型"
            
            root_tag_prompts.append(f"{root_tag.name}({tag_type_description}, ID:{root_tag.id})")
        
        # 步骤3: 调用LLM生成结构化标签，包含根标签信息
        analysis_prompt = f"""
        请对以下文档内容进行深入分析，提取细粒度的具体特征作为标签，并生成详细摘要。
        
        文档关键词: {', '.join(combined_keywords[:30])}
        
        文档内容样本:
        {' '.join(content_samples[:3])}
        
        本系统有以下几个标签根类别:
        {', '.join(root_tag_prompts)}
        
        在分析时，请考虑关键词中提及的概念，并基于以下任务生成标签:
        1. 将每个生成的标签分配给上述根类别中的一个，确保类型匹配
        2. 为每个标签提供详细描述，解释其在文档中的意义
        3. 为每个标签评估重要性，范围从0到1
        
        请以JSON格式返回以下信息:
        {{
          "summary": "文档的详细摘要，描述主要内容和用途",
          "tags": [
            {{
              "name": "标签名称",
              "description": "标签描述",
              "parent_id": 根类别标签的ID,
              "importance": 0.8,
              "color": "可选的颜色代码"
            }},
            // 更多标签...
          ]
        }}
        
        示例格式:
        {{
          "summary": "这是一份关于数据库优化的技术文档，主要讨论了索引设计和查询优化策略...",
          "tags": [
            {{
              "name": "MySQL索引",
              "description": "讨论MySQL索引的创建和优化",
              "parent_id": 2,
              "importance": 0.9
            }},
            {{
              "name": "查询性能",
              "description": "分析和提高SQL查询性能的方法",
              "parent_id": 3,
              "importance": 0.8
            }}
          ]
        }}
        """
        
        analysis_result = await llm_client.generate(analysis_prompt)
        
        # 解析JSON结果
        try:
            # 确保在这个作用域中导入re模块
            import re as regex_module
            # 查找JSON部分
            json_match = regex_module.search(r'```json\s*([\s\S]*?)\s*```', analysis_result)
            if json_match:
                analysis_json = json.loads(json_match.group(1))
            else:
                # 尝试直接解析整个文本作为JSON
                analysis_json = json.loads(analysis_result)
        except Exception as e:
            logger.error(f"解析LLM返回的JSON失败: {str(e)}，原始返回: {analysis_result}")
            raise HTTPException(status_code=500, detail=f"解析AI分析结果失败")
        
        # 提取文档摘要
        summary = analysis_json.get("summary", "无摘要信息")
        
        # 提取并创建标签
        new_tags = []
        existing_tags = []
        
        for tag_data in analysis_json.get("tags", []):
            tag_name = tag_data.get("name")
            if not tag_name:
                continue
                
            # 检查是否已存在相同标签
            existing_tag = db.query(Tag).filter(Tag.name == tag_name).first()
            
            if existing_tag:
                existing_tags.append(existing_tag)
                logger.info(f"使用已存在的标签: {tag_name}")
            else:
                # 创建新标签
                tag_description = tag_data.get("description", "")
                tag_importance = float(tag_data.get("importance", 0.5))
                tag_color = tag_data.get("color")
                parent_id = tag_data.get("parent_id")
                
                # 检查parent_id是否有效
                hierarchy_level = "leaf"  # 默认为叶标签
                if parent_id:
                    parent_tag = db.query(Tag).filter(Tag.id == parent_id).first()
                    if parent_tag:
                        # 根据父标签层级确定当前标签层级
                        if parent_tag.hierarchy_level == "root":
                            hierarchy_level = "branch"
                        elif parent_tag.hierarchy_level == "branch":
                            hierarchy_level = "leaf"
                
                new_tag = Tag(
                    name=tag_name,
                    description=tag_description,
                    importance=tag_importance,
                    parent_id=parent_id if parent_id else None,
                    hierarchy_level=hierarchy_level
                )
                
                # 如果提供了颜色，使用提供的颜色
                if tag_color:
                    new_tag.color = tag_color
                
                db.add(new_tag)
                db.flush()  # 获取ID但不提交事务
                
                new_tags.append(new_tag)
                logger.info(f"创建新标签: {tag_name}")
        
        # 将所有标签关联到文档
        all_tags = new_tags + existing_tags
        for tag in all_tags:
            if tag not in document.tags:
                document.tags.append(tag)
        
        # 为文档块添加标签
        for chunk in chunks:
            for tag in all_tags:
                if tag not in chunk.tags:
                    chunk.tags.append(tag)
        
        # 更新文档摘要
        if summary and hasattr(document, 'summary'):
            document.summary = summary
        
        # 提交所有更改
        db.commit()
        
        # 返回结果
        return {
            "success": True,
            "message": f"已完成文档分析并添加{len(new_tags)}个新标签和{len(existing_tags)}个已有标签",
            "document_id": document_id,
            "summary": summary,
            "new_tags": [{"id": tag.id, "name": tag.name, "color": tag.color} for tag in new_tags],
            "existing_tags": [{"id": tag.id, "name": tag.name, "color": tag.color} for tag in existing_tags],
            "keywords": combined_keywords[:30]
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"文档标签分析失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文档标签分析失败: {str(e)}")

@router.put("/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    name: str = Body(None),
    color: str = Body(None),
    description: Optional[str] = Body(None),
    parent_id: Optional[int] = Body(None),
    tag_type: Optional[str] = Body(None),
    importance: Optional[float] = Body(None),
    related_content: Optional[str] = Body(None),
    hierarchy_level: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """更新标签信息"""
    try:
        # 查找要更新的标签
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")
        
        # 如果指定了父标签，检查是否存在
        if parent_id:
            parent_tag = db.query(Tag).filter(Tag.id == parent_id).first()
            if not parent_tag:
                raise HTTPException(status_code=404, detail=f"父标签ID {parent_id} 不存在")
            
            # 避免循环引用：不能将标签设为自己的子标签
            if parent_id == tag_id:
                raise HTTPException(status_code=400, detail="不能将标签设为自己的父标签")
        
        # 更新标签信息
        if name is not None:
            tag.name = name
        if color is not None:
            tag.color = color
        if description is not None:
            tag.description = description
        if parent_id is not None:
            tag.parent_id = parent_id
        
        # 处理层级设置
        if hierarchy_level is not None:
            # 如果设置为root标签，移除父标签
            if hierarchy_level == "root":
                tag.parent_id = None
            tag.hierarchy_level = hierarchy_level
        
        # 尝试更新可选的新字段
        try:
            if tag_type is not None and hasattr(tag, 'tag_type'):
                tag.tag_type = tag_type
            if importance is not None and hasattr(tag, 'importance'):
                tag.importance = importance
            if related_content is not None and hasattr(tag, 'related_content'):
                tag.related_content = related_content
        except Exception as field_error:
            logger.warning(f"更新标签高级字段时出错: {str(field_error)}")
        
        db.commit()
        db.refresh(tag)
        
        # 构建返回结果
        result = {
            "id": tag.id,
            "name": tag.name,
            "color": tag.color,
            "description": tag.description,
            "parent_id": tag.parent_id,
            "hierarchy_level": tag.hierarchy_level
        }
        
        # 尝试添加新字段
        try:
            if hasattr(tag, 'tag_type'):
                result["tag_type"] = tag.tag_type
            if hasattr(tag, 'importance'):
                result["importance"] = tag.importance
            if hasattr(tag, 'related_content'):
                result["related_content"] = tag.related_content
        except:
            pass
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新标签失败: {str(e)}")

@router.get("/tags/{tag_id}/documents")
async def get_tag_documents(
    tag_id: str,
    db: Session = Depends(get_db)
):
    """获取标签关联的所有文档"""
    try:
        # 处理tag_id格式，如果是形如"tag_123"的格式，提取数字部分
        if isinstance(tag_id, str) and tag_id.startswith("tag_"):
            try:
                numeric_id = int(tag_id.split("_")[1])
            except (IndexError, ValueError):
                raise HTTPException(status_code=422, detail=f"无效的标签ID格式: {tag_id}")
        else:
            try:
                numeric_id = int(tag_id)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"无效的标签ID格式: {tag_id}")
                
        # 查找标签
        tag = db.query(Tag).filter(Tag.id == numeric_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")
            
        # 查找与该标签相关联的所有文档
        documents_query = db.query(Document).join(
            document_tags,
            Document.id == document_tags.c.document_id
        ).filter(
            document_tags.c.tag_id == numeric_id
        )
        
        documents = documents_query.all()
        
        # 格式化结果
        result = []
        for doc in documents:
            result.append({
                "id": doc.id,
                "source": doc.source,
                "document_type": doc.document_type,
                "chunks_count": doc.chunks_count or 0,
                "knowledge_base_id": doc.knowledge_base_id if hasattr(doc, 'knowledge_base_id') else None
            })
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取标签 {tag_id} 相关文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取标签相关文档失败: {str(e)}")

@router.get("/graph/tag-relations/{knowledge_base_id}")
async def get_tag_relations_graph(
    knowledge_base_id: int,
    db: Session = Depends(get_db)
):
    """获取标签关系网络，用于可视化知识图谱"""
    try:
        # 检查知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"知识库ID {knowledge_base_id} 不存在")
        
        # 查询与该知识库相关的文档IDs
        documents = db.query(Document).filter(Document.knowledge_base_id == knowledge_base_id).all()
        if not documents:
            logger.info(f"知识库 {knowledge_base_id} 没有关联的文档")
            return {"nodes": [], "links": []}
            
        doc_ids = [doc.id for doc in documents]
        
        # 获取与这些文档关联的标签IDs
        from sqlalchemy import text
        tag_ids_query = f"""
            SELECT DISTINCT tag_id 
            FROM document_tags 
            WHERE document_id IN ({','.join(str(id) for id in doc_ids)})
        """
        result = db.execute(text(tag_ids_query))
        tag_ids = [row[0] for row in result]
        
        if not tag_ids:
            logger.info(f"知识库 {knowledge_base_id} 的文档没有关联的标签")
            return {"nodes": [], "links": []}
        
        # 获取这些标签的完整信息
        tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
        if not tags:
            return {"nodes": [], "links": []}
        
        tags_by_id = {tag.id: tag for tag in tags}
        
        # 准备节点数据
        nodes = []
        node_ids_set = set()  # 跟踪实际添加到图中的节点ID
        
        # 添加根标签节点
        root_tags = [tag for tag in tags if tag.hierarchy_level == "root"]
        for tag in root_tags:
            node_id = f"tag_{tag.id}"
            nodes.append({
                "id": node_id,
                "label": tag.name,
                "type": "TAG",
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level,
                "color": tag.color,
                "size": 15,  # 根标签显示大一些
                "shape": "star",  # 使用星形
                "description": tag.description or ""
            })
            node_ids_set.add(node_id)
        
        # 添加分支标签节点
        branch_tags = [tag for tag in tags if tag.hierarchy_level == "branch"]
        for tag in branch_tags:
            node_id = f"tag_{tag.id}"
            nodes.append({
                "id": node_id,
                "label": tag.name,
                "type": "TAG",
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level,
                "color": tag.color,
                "size": 10,  # 分支标签中等大小
                "shape": "triangle",  # 使用三角形
                "description": tag.description or ""
            })
            node_ids_set.add(node_id)
        
        # 添加叶标签节点
        leaf_tags = [tag for tag in tags if tag.hierarchy_level == "leaf" or tag.hierarchy_level is None]
        for tag in leaf_tags:
            node_id = f"tag_{tag.id}"
            nodes.append({
                "id": node_id,
                "label": tag.name,
                "type": "TAG",
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level or "leaf",
                "color": tag.color,
                "size": 7,  # 叶标签稍微大一点，便于查看
                "shape": "circle",  # 使用圆形
                "description": tag.description or ""
            })
            node_ids_set.add(node_id)
        
        logger.info(f"为知识库 {knowledge_base_id} 创建了 {len(nodes)} 个标签节点")
        
        # 准备连接数据
        links = []
        
        # 添加父子关系连接 - 首先检查标签是否存在于当前图中
        # 先添加根标签到分支标签的连接
        for tag in branch_tags:
            if tag.parent_id:
                source_id = f"tag_{tag.parent_id}"
                target_id = f"tag_{tag.id}"
                # 验证源节点和目标节点都存在
                if source_id in node_ids_set and target_id in node_ids_set:
                    links.append({
                        "source": source_id,
                        "target": target_id,
                        "type": "PARENT_OF",
                        "label": "包含",
                        "value": 2,  # 增大显示权重
                        "color": "#1890ff",  # 父子关系使用明显的蓝色
                        "dashed": False,  # 实线
                        "width": 2  # 较粗的线
                    })
                else:
                    logger.warning(f"跳过无效的父子关系链接: {source_id} -> {target_id}, 节点不存在")
        
        # 再添加分支标签到叶标签的连接
        for tag in leaf_tags:
            if tag.parent_id:
                source_id = f"tag_{tag.parent_id}"
                target_id = f"tag_{tag.id}"
                # 验证源节点和目标节点都存在
                if source_id in node_ids_set and target_id in node_ids_set:
                    links.append({
                        "source": source_id,
                        "target": target_id,
                        "type": "PARENT_OF",
                        "label": "包含",
                        "value": 1.5,  # 增大显示权重
                        "color": "#1890ff",  # 父子关系使用明显的蓝色
                        "dashed": False,  # 实线
                        "width": 1.5  # 较粗的线
                    })
                else:
                    logger.warning(f"跳过无效的父子关系链接: {source_id} -> {target_id}, 节点不存在")
        
        # 添加TagDependency关系连接 - 只包含当前图中存在的标签
        tag_dependencies = db.query(TagDependency).filter(
            (TagDependency.source_tag_id.in_(tag_ids)) & 
            (TagDependency.target_tag_id.in_(tag_ids))
        ).all()
        
        for dep in tag_dependencies:
            source_id = f"tag_{dep.source_tag_id}"
            target_id = f"tag_{dep.target_tag_id}"
            # 验证源节点和目标节点都存在
            if source_id in node_ids_set and target_id in node_ids_set:
                links.append({
                    "source": source_id,
                    "target": target_id,
                    "type": dep.relationship_type,
                    "label": dep.relationship_type.replace("_", " ").lower(),
                    "value": 0.8,
                    "color": "#ff7a45",  # 依赖关系使用橙色
                    "dashed": True,  # 虚线
                    "width": 1  # 正常线宽
                })
            else:
                logger.warning(f"跳过无效的标签依赖关系链接: {source_id} -> {target_id}, 节点不存在")
        
        # 添加共现关系连接 - 只在有文档的情况下
        if tag_ids and doc_ids:
            try:
                # 将列表转换为逗号分隔的字符串
                tag_ids_str = ','.join(str(id) for id in tag_ids)
                doc_ids_str = ','.join(str(id) for id in doc_ids)
                
                # 构建不使用参数绑定的SQL查询
                cooccurrence_query = f"""
                SELECT t1.tag_id as tag1_id, t2.tag_id as tag2_id, COUNT(*) as count
                FROM document_tags t1
                JOIN document_tags t2 ON t1.document_id = t2.document_id AND t1.tag_id < t2.tag_id
                WHERE t1.tag_id IN ({tag_ids_str}) AND t2.tag_id IN ({tag_ids_str})
                AND t1.document_id IN ({doc_ids_str}) AND t2.document_id IN ({doc_ids_str})
                GROUP BY t1.tag_id, t2.tag_id
                HAVING COUNT(*) > 1
                """
                
                cooccurrence_results = db.execute(text(cooccurrence_query)).fetchall()
                
                for row in cooccurrence_results:
                    tag1_id, tag2_id, count = row
                    source_id = f"tag_{tag1_id}"
                    target_id = f"tag_{tag2_id}"
                    
                    # 验证节点存在
                    if source_id not in node_ids_set or target_id not in node_ids_set:
                        logger.warning(f"跳过无效的共现关系链接: {source_id} -> {target_id}, 节点不存在")
                        continue
                    
                    # 检查是否已有显式的父子关系或依赖关系
                    has_direct_relation = False
                    for link in links:
                        if (link["source"] == source_id and link["target"] == target_id) or \
                           (link["source"] == target_id and link["target"] == source_id):
                            has_direct_relation = True
                            break
                    
                    if not has_direct_relation:
                        # 计算连接强度 - 基于共现次数的对数，避免数值过大
                        import math
                        strength = 0.3 + 0.2 * math.log(1 + count) 
                        
                        links.append({
                            "source": source_id,
                            "target": target_id,
                            "type": "CO_OCCURS",
                            "label": "共现",
                            "value": min(0.7, strength),  # 限制最大值
                            "color": "#d9d9d9",  # 浅灰色
                            "dashed": True,  # 虚线
                            "width": 0.5,  # 细线
                            "count": count
                        })
            except Exception as e:
                logger.warning(f"计算标签共现关系时出错: {str(e)}")
                # 错误不影响其他部分的图数据显示
        
        logger.info(f"为知识库 {knowledge_base_id} 创建了 {len(links)} 个标签关系链接")
        return {
            "nodes": nodes,
            "links": links
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取标签关系图失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取标签关系图失败: {str(e)}")

@router.post("/tag-dependencies")
async def create_tag_dependency(
    source_tag_id: int = Body(...),
    target_tag_id: int = Body(...),
    relationship_type: str = Body(...),
    description: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """创建标签之间的依赖关系"""
    try:
        # 验证标签是否存在
        source_tag = db.query(Tag).filter(Tag.id == source_tag_id).first()
        if not source_tag:
            raise HTTPException(status_code=404, detail=f"源标签ID {source_tag_id} 不存在")
        
        target_tag = db.query(Tag).filter(Tag.id == target_tag_id).first()
        if not target_tag:
            raise HTTPException(status_code=404, detail=f"目标标签ID {target_tag_id} 不存在")
        
        # 检查关系是否已存在
        existing = db.query(TagDependency).filter(
            TagDependency.source_tag_id == source_tag_id,
            TagDependency.target_tag_id == target_tag_id
        ).first()
        
        if existing:
            # 更新现有关系
            existing.relationship_type = relationship_type
            existing.description = description
            db.commit()
            return {
                "id": existing.id,
                "source_tag_id": existing.source_tag_id,
                "target_tag_id": existing.target_tag_id,
                "relationship_type": existing.relationship_type,
                "description": existing.description,
                "updated": True
            }
        
        # 创建新关系
        dependency = TagDependency(
            source_tag_id=source_tag_id,
            target_tag_id=target_tag_id,
            relationship_type=relationship_type,
            description=description
        )
        
        db.add(dependency)
        db.commit()
        db.refresh(dependency)
        
        return {
            "id": dependency.id,
            "source_tag_id": dependency.source_tag_id,
            "target_tag_id": dependency.target_tag_id,
            "relationship_type": dependency.relationship_type,
            "description": dependency.description,
            "created": True
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"创建标签依赖关系失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建标签依赖关系失败: {str(e)}")

@router.delete("/tag-dependencies/{dependency_id}")
async def delete_tag_dependency(
    dependency_id: int,
    db: Session = Depends(get_db)
):
    """删除标签依赖关系"""
    try:
        dependency = db.query(TagDependency).filter(TagDependency.id == dependency_id).first()
        if not dependency:
            raise HTTPException(status_code=404, detail=f"依赖关系ID {dependency_id} 不存在")
        
        db.delete(dependency)
        db.commit()
        
        return {
            "success": True,
            "message": f"已删除标签依赖关系 {dependency_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除标签依赖关系失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除标签依赖关系失败: {str(e)}")

@router.get("/diagnose/kb/{knowledge_base_id}")
async def diagnose_knowledge_base(knowledge_base_id: int, db: Session = Depends(get_db)):
    """诊断功能：检查知识库的文档、标签和向量存储状态"""
    try:
        # 检查知识库是否存在
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"知识库ID {knowledge_base_id} 不存在")
            
        # 1. 获取知识库的基本信息
        kb_info = {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "created_at": kb.created_at.isoformat() if kb.created_at else None
        }
        
        # 2. 获取知识库关联的文档
        documents = db.query(Document).filter(Document.knowledge_base_id == knowledge_base_id).all()
        doc_ids = [doc.id for doc in documents]
        doc_info = [
            {
                "id": doc.id,
                "source": doc.source,
                "document_type": doc.document_type,
                "status": doc.status,
                "added_at": doc.added_at.isoformat() if doc.added_at else None
            }
            for doc in documents
        ]
        
        # 3. 获取文档关联的标签
        all_tag_ids = set()
        doc_tag_info = {}
        
        for doc_id in doc_ids:
            # 获取文档直接关联的标签
            doc_tags_query = f"""
                SELECT tag_id 
                FROM document_tags 
                WHERE document_id = {doc_id}
            """
            result = db.execute(text(doc_tags_query))
            doc_tag_ids = [row[0] for row in result]
            all_tag_ids.update(doc_tag_ids)
            
            # 保存到信息字典
            doc_tag_info[doc_id] = {
                "tag_count": len(doc_tag_ids),
                "tag_ids": doc_tag_ids
            }
        
        # 获取所有标签的信息
        tags = db.query(Tag).filter(Tag.id.in_(all_tag_ids)) if all_tag_ids else []
        tag_info = {
            tag.id: {
                "id": tag.id,
                "name": tag.name,
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level
            }
            for tag in tags
        }
        
        # 4. 检查向量存储
        from vector_store import VectorStore
        vector_store = VectorStore(knowledge_base_id=knowledge_base_id)
        
        try:
            # 获取向量存储中的示例文档
            vs_docs = await vector_store.get_all_documents(limit=5)
            
            # 收集有效标签键
            vs_tag_keys = set()
            for doc in vs_docs:
                if "tag_keys" in doc and doc["tag_keys"]:
                    vs_tag_keys.update(doc["tag_keys"])
            
            vs_info = {
                "document_count": len(vs_docs),
                "sample_documents": vs_docs,
                "tag_keys": list(vs_tag_keys),
                "has_proper_tag_format": any(key.startswith("tag_") for key in vs_tag_keys)
            }
            
        except Exception as e:
            vs_info = {
                "error": str(e),
                "status": "无法访问向量存储"
            }
        
        # 5. 返回综合诊断
        return {
            "knowledge_base": kb_info,
            "documents": {
                "count": len(documents),
                "items": doc_info
            },
            "tags": {
                "count": len(tag_info),
                "items": list(tag_info.values())
            },
            "document_tags": doc_tag_info,
            "vector_store": vs_info,
            "diagnosis": {
                "has_documents": len(documents) > 0,
                "has_tags": len(tag_info) > 0,
                "has_vector_docs": vs_info.get("document_count", 0) > 0,
                "tag_format_correct": vs_info.get("has_proper_tag_format", False),
                "suggestions": [
                    "请检查文档是否有标签" if len(tag_info) == 0 else None,
                    "请检查向量存储是否有文档" if vs_info.get("document_count", 0) == 0 else None,
                    "请检查标签格式是否正确" if not vs_info.get("has_proper_tag_format", False) else None
                ]
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"知识库诊断失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"知识库诊断失败: {str(e)}")

@router.get("/diagnose/tag/{tag_id}")
async def diagnose_tag(tag_id: int, db: Session = Depends(get_db)):
    """诊断功能：检查标签的关联状态，包括文档关系、父子关系等"""
    try:
        # 检查标签是否存在
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")
            
        # 获取标签基本信息
        tag_info = {
            "id": tag.id,
            "name": tag.name,
            "color": tag.color,
            "description": tag.description,
            "parent_id": tag.parent_id,
            "hierarchy_level": tag.hierarchy_level,
            "tag_type": tag.tag_type,
            "is_system": tag.is_system if hasattr(tag, 'is_system') else None
        }
        
        # 获取父标签信息
        parent_info = None
        if tag.parent_id:
            parent_tag = db.query(Tag).filter(Tag.id == tag.parent_id).first()
            if parent_tag:
                parent_info = {
                    "id": parent_tag.id,
                    "name": parent_tag.name,
                    "hierarchy_level": parent_tag.hierarchy_level
                }
        
        # 获取子标签信息
        child_tags = db.query(Tag).filter(Tag.parent_id == tag_id).all()
        child_info = []
        for child in child_tags:
            child_info.append({
                "id": child.id,
                "name": child.name,
                "hierarchy_level": child.hierarchy_level
            })
            
        # 获取关联的文档数量
        from sqlalchemy import func, text
        doc_count_query = text(f"""
            SELECT COUNT(DISTINCT document_id) 
            FROM document_tags 
            WHERE tag_id = {tag_id}
        """)
        doc_count_result = db.execute(doc_count_query).scalar() or 0
        
        # 获取关联的文档块数量
        chunk_count_query = text(f"""
            SELECT COUNT(DISTINCT document_chunk_id) 
            FROM document_chunk_tags 
            WHERE tag_id = {tag_id}
        """)
        chunk_count_result = db.execute(chunk_count_query).scalar() or 0
        
        # 获取向量存储中的标签使用情况
        from vector_store import VectorStore
        vs_diagnostic = {
            "status": "unavailable",
            "message": "向量存储诊断未实现"
        }
        
        return {
            "tag": tag_info,
            "parent": parent_info,
            "children": {
                "count": len(child_info),
                "items": child_info
            },
            "documents": {
                "count": doc_count_result,
                "chunk_count": chunk_count_result
            },
            "vector_store": vs_diagnostic,
            "diagnosis": {
                "has_documents": doc_count_result > 0,
                "has_chunks": chunk_count_result > 0,
                "is_orphan": parent_info is None and tag.hierarchy_level != "root",
                "has_children": len(child_info) > 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标签诊断失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"标签诊断失败: {str(e)}")

@router.get("/tags/deletable")
async def get_all_deletable_tags(db: Session = Depends(get_db)):
    """
    获取所有可以安全删除的标签
    
    返回没有关联文档且不是父标签的所有标签，包括root标签
    """
    try:
        # 尝试从缓存获取数据
        cached_result = get_cached_data("deletable_tags")
        if cached_result:
            logger.info("使用缓存的可删除标签数据")
            return cached_result
            
        # 缓存未命中，执行数据库查询
        logger.info("缓存未命中，从数据库查询可删除标签")
        
        # 1. 获取所有标签
        tags = db.query(Tag).all()
        
        result = []
        for tag in tags:
            # 2. 检查是否有关联文档
            doc_count = db.query(document_tags).filter(document_tags.c.tag_id == tag.id).count()
            has_documents = doc_count > 0
            
            # 3. 检查是否有子标签
            child_count = db.query(Tag).filter(Tag.parent_id == tag.id).count()
            has_children = child_count > 0
            
            # 5. 如果没有关联文档且不是父标签，则添加到结果中
            if not has_documents and not has_children:
                result.append({
                    "id": tag.id,
                    "name": tag.name,
                    "color": tag.color,
                    "description": tag.description,
                    "hierarchy_level": tag.hierarchy_level
                })
        
        # 计算结果并缓存
        response = {"deletable_tags": result, "count": len(result)}
        set_cached_data("deletable_tags", response, ttl=5)  # 缓存5秒
        
        return response
    except Exception as e:
        logger.error(f"获取可删除标签列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取可删除标签列表失败: {str(e)}") 