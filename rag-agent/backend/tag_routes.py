from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import logging
import re

from models import get_db, Tag, Document, DocumentChunk, document_tags, document_chunk_tags, KnowledgeBase, TagDependency
from config import get_autogen_config

router = APIRouter(prefix="", tags=["tags-management"])
logger = logging.getLogger(__name__)

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
async def get_all_tags(db: Session = Depends(get_db)):
    """获取所有标签"""
    try:
        tags = db.query(Tag).all()
        return {"tags": [{"id": tag.id, "name": tag.name, "color": tag.color, "description": tag.description, "parent_id": tag.parent_id} for tag in tags]}
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
    db: Session = Depends(get_db)
):
    """创建新标签"""
    try:
        # 检查是否已存在同名标签
        existing_tag = db.query(Tag).filter(Tag.name == name).first()
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
        elif hierarchy_level == "root":
            # 如果没有父标签且标记为根标签，检查是否已存在同类型的根标签
            existing_root = db.query(Tag).filter(
                Tag.hierarchy_level == "root",
                Tag.tag_type == tag_type
            ).first()
            if existing_root:
                logger.warning(f"已存在同类型的根标签: {existing_root.name}。将使用现有根标签作为父标签。")
                parent_id = existing_root.id
                hierarchy_level = "branch"
        
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
            is_system=is_system
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

@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db)
):
    """删除标签，并处理其在文档和块中的关联"""
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")

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
        
        # 4. 将所有子标签的parent_id设为null
        db.query(Tag).filter(Tag.parent_id == tag_id).update(
            {Tag.parent_id: None}, synchronize_session=False
        )
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
            "parent_id": tag.parent_id
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
    tag_id: int,
    db: Session = Depends(get_db)
):
    """获取标签关联的所有文档"""
    try:
        # 查找标签
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail=f"标签ID {tag_id} 不存在")
        
        # 获取与该标签关联的所有文档
        documents = db.query(Document)\
            .join(document_tags, Document.id == document_tags.c.document_id)\
            .filter(document_tags.c.tag_id == tag_id)\
            .all()
        
        # 构建响应数据
        result_documents = []
        for doc in documents:
            # 获取知识库名称
            kb_name = None
            if doc.knowledge_base_id:
                kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == doc.knowledge_base_id).first()
                if kb:
                    kb_name = kb.name
            
            result_documents.append({
                "id": doc.id,
                "source": doc.source,
                "document_type": doc.document_type,
                "status": doc.status,
                "chunks_count": doc.chunks_count,
                "added_at": doc.added_at,
                "processed_at": doc.processed_at,
                "knowledge_base_id": doc.knowledge_base_id,
                "knowledge_base_name": kb_name
            })
        
        return {"documents": result_documents}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取标签关联文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取标签关联文档失败: {str(e)}")

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
        
        # 获取所有标签 - 不再仅仅获取关联到文档的标签
        tags = db.query(Tag).all()
        if not tags:
            return {"nodes": [], "links": []}
        
        tags_by_id = {tag.id: tag for tag in tags}
        tag_ids = list(tags_by_id.keys())
        
        # 获取文档ID用于后面的共现关系计算
        documents = db.query(Document).filter(Document.knowledge_base_id == knowledge_base_id).all()
        doc_ids = [doc.id for doc in documents] if documents else []
        
        # 准备节点数据
        nodes = []
        
        # 添加根标签节点
        root_tags = [tag for tag in tags if tag.hierarchy_level == "root"]
        for tag in root_tags:
            nodes.append({
                "id": f"tag_{tag.id}",
                "label": tag.name,
                "type": "TAG",
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level,
                "color": tag.color,
                "size": 15,  # 根标签显示大一些
                "shape": "star",  # 使用星形
                "description": tag.description or ""
            })
        
        # 添加分支标签节点
        branch_tags = [tag for tag in tags if tag.hierarchy_level == "branch"]
        for tag in branch_tags:
            nodes.append({
                "id": f"tag_{tag.id}",
                "label": tag.name,
                "type": "TAG",
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level,
                "color": tag.color,
                "size": 10,  # 分支标签中等大小
                "shape": "triangle",  # 使用三角形
                "description": tag.description or ""
            })
        
        # 添加叶标签节点
        leaf_tags = [tag for tag in tags if tag.hierarchy_level == "leaf" or tag.hierarchy_level is None]
        for tag in leaf_tags:
            nodes.append({
                "id": f"tag_{tag.id}",
                "label": tag.name,
                "type": "TAG",
                "tag_type": tag.tag_type,
                "hierarchy_level": tag.hierarchy_level or "leaf",
                "color": tag.color,
                "size": 7,  # 叶标签稍微大一点，便于查看
                "shape": "circle",  # 使用圆形
                "description": tag.description or ""
            })
        
        # 准备连接数据
        links = []
        
        # 添加父子关系连接
        # 先添加根标签到分支标签的连接
        for tag in branch_tags:
            if tag.parent_id:
                links.append({
                    "source": f"tag_{tag.parent_id}",
                    "target": f"tag_{tag.id}",
                    "type": "PARENT_OF",
                    "label": "包含",
                    "value": 2,  # 增大显示权重
                    "color": "#1890ff",  # 父子关系使用明显的蓝色
                    "dashed": False,  # 实线
                    "width": 2  # 较粗的线
                })
        
        # 再添加分支标签到叶标签的连接
        for tag in leaf_tags:
            if tag.parent_id:
                links.append({
                    "source": f"tag_{tag.parent_id}",
                    "target": f"tag_{tag.id}",
                    "type": "PARENT_OF",
                    "label": "包含",
                    "value": 1.5,  # 增大显示权重
                    "color": "#1890ff",  # 父子关系使用明显的蓝色
                    "dashed": False,  # 实线
                    "width": 1.5  # 较粗的线
                })
        
        # 添加TagDependency关系连接
        tag_dependencies = db.query(TagDependency).all()
        
        for dep in tag_dependencies:
            if dep.source_tag_id in tags_by_id and dep.target_tag_id in tags_by_id:
                links.append({
                    "source": f"tag_{dep.source_tag_id}",
                    "target": f"tag_{dep.target_tag_id}",
                    "type": dep.relationship_type,
                    "label": dep.relationship_type.replace("_", " ").lower(),
                    "value": 0.8,
                    "color": "#ff7a45",  # 依赖关系使用橙色
                    "dashed": True,  # 虚线
                    "width": 1  # 正常线宽
                })
        
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
                    
                    # 检查是否已有显式的父子关系或依赖关系
                    has_direct_relation = False
                    for link in links:
                        if (link["source"] == f"tag_{tag1_id}" and link["target"] == f"tag_{tag2_id}") or \
                           (link["source"] == f"tag_{tag2_id}" and link["target"] == f"tag_{tag1_id}"):
                            has_direct_relation = True
                            break
                    
                    if not has_direct_relation:
                        # 计算连接强度 - 基于共现次数的对数，避免数值过大
                        import math
                        strength = 0.3 + 0.2 * math.log(1 + count) 
                        
                        links.append({
                            "source": f"tag_{tag1_id}",
                            "target": f"tag_{tag2_id}",
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