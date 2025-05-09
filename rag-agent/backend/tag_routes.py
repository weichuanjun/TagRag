from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import logging
import re

from models import get_db, Tag, Document, DocumentChunk, document_tags, document_chunk_tags
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
        
        # 创建新标签
        tag = Tag(
            name=name,
            color=color,
            description=description,
            parent_id=parent_id,
            tag_type=tag_type,
            importance=importance,
            related_content=related_content
        )
        
        db.add(tag)
        db.commit()
        db.refresh(tag)
        
        return {"id": tag.id, "name": tag.name, "color": tag.color}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建标签失败: {str(e)}")

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
        # SQLAlchemy Table object does not have a direct 'delete' method that works like ORM delete.
        # We need to execute a delete statement.
        stmt_doc_tags = document_tags.delete().where(document_tags.c.tag_id == tag_id)
        db.execute(stmt_doc_tags)
        logger.info(f"已从 document_tags 中为 tag_id {tag_id} 删除关联")

        # 2. 从 document_chunk_tags 中删除关联
        stmt_chunk_tags = document_chunk_tags.delete().where(document_chunk_tags.c.tag_id == tag_id)
        db.execute(stmt_chunk_tags)
        logger.info(f"已从 document_chunk_tags 中为 tag_id {tag_id} 删除关联")
        
        # 3. 删除标签自身
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
    """使用AI分析文档内容，自动生成标签和分段摘要"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
        
        # 获取文档的所有文本块
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        if not chunks:
            raise HTTPException(status_code=404, detail=f"文档没有可分析的内容块")
        
        # 汇总内容（限制长度，避免超出API限制）
        content_samples = []
        for chunk in chunks[:10]:  # 最多使用前10个块
            try:
                content = chunk.content[:500]  # 每块最多取500个字符
                content_samples.append(content)
            except Exception as e:
                logger.warning(f"处理文档块 {chunk.id} 时出错: {str(e)}")
        
        if not content_samples:
            raise HTTPException(status_code=400, detail="无法提取有效的文档内容样本")
        
        # 构建分析提示
        analysis_prompt = f"""
        请对以下文档内容进行深入分析，提取细粒度的具体特征作为标签，并生成详细摘要。
        
        文档内容样本:
        {' '.join(content_samples[:3])}
        
        在分析时，请关注以下方面（如果存在）：
        1. 文档涉及的具体API或接口名称（例如：用户登录API、商品查询接口）
        2. 文档中提到的具体数据库表和字段（例如：user表、product_id字段）
        3. 文档中描述的业务流程或功能（例如：订单支付流程、用户注册验证）
        4. 文档涉及的技术堆栈或组件（例如：React、SpringBoot、MySQL）
        5. 文档的具体用途（API文档、架构设计、数据模型等）
        
        请以JSON格式返回以下信息:
        1. 文档摘要(summary)：详细描述文档的主要内容和用途
        2. 原始内容片段(content_samples)：提取3-5个最有代表性的原始内容片段
        3. 标签列表(tags)，每个标签应尽量具体且有意义，包含:
           - 名称(name)：具体、有辨识度的标签名
           - 描述(description)：对该标签对应内容的详细解释
           - 类型(type)：标签类型，如"API"、"字段"、"功能"、"技术"、"文档类型"等
           - 重要性(importance)：0-1之间的数字
           - 相关片段(related_content)：与此标签直接相关的原始内容片段
        
        示例格式：
        ```json
        {{
          "summary": "这是一个订单管理系统API文档，主要描述了订单创建、查询和支付的接口规范...",
          "content_samples": [
            "POST /api/orders 接口用于创建新订单，需要提供user_id和product_list参数",
            "订单状态(order_status)字段可选值：1-待支付，2-已支付，3-已发货，4-已完成",
            "订单表(orders)包含以下字段：id, user_id, total_amount, status, created_at"
          ],
          "tags": [
            {{
              "name": "订单创建API", 
              "description": "用于创建新订单的POST接口",
              "type": "API",
              "importance": 0.9,
              "related_content": "POST /api/orders 接口用于创建新订单，需要提供user_id和product_list参数"
            }},
            {{
              "name": "order_status字段", 
              "description": "订单状态字段，有多种状态值代表不同处理阶段",
              "type": "字段",
              "importance": 0.8,
              "related_content": "订单状态(order_status)字段可选值：1-待支付，2-已支付，3-已发货，4-已完成"
            }}
          ]
        }}
        ```
        仅返回JSON格式结果，不要添加其它内容。确保标签信息具体且详细，避免过于宽泛的分类。
        """
        
        # 调用LLM进行分析
        analysis_result = await llm_client.generate(analysis_prompt)
        
        # 解析JSON结果
        try:
            # 查找JSON部分
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', analysis_result)
            if json_match:
                analysis_json = json.loads(json_match.group(1))
            else:
                # 尝试直接解析整个文本作为JSON
                analysis_json = json.loads(analysis_result)
        except Exception as e:
            logger.error(f"解析LLM返回的JSON失败: {str(e)}，原始返回: {analysis_result}")
            raise HTTPException(status_code=500, detail=f"解析AI分析结果失败")
        
        # 提取分析结果
        summary = analysis_json.get("summary", "")
        tags_data = analysis_json.get("tags", [])
        content_excerpts = analysis_json.get("content_samples", [])
        
        # 处理标签
        created_tags = []
        for tag_data in tags_data:
            tag_name = tag_data.get("name")
            tag_desc = tag_data.get("description", "")
            tag_type = tag_data.get("type", "general")
            importance = tag_data.get("importance", 0.5)
            related_content = tag_data.get("related_content", "")
            
            # 检查标签是否已存在
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                try:
                    # 创建新标签，兼容处理各种可能的数据库结构
                    tag_dict = {
                        "name": tag_name,
                        "description": tag_desc,
                        "color": "#1890ff",  # 默认颜色
                    }
                    
                    # 尝试添加新字段，如果数据库不支持则忽略
                    try:
                        # 检查Tag对象是否有新增字段
                        tag_obj = Tag()
                        if hasattr(tag_obj, 'tag_type'):
                            tag_dict["tag_type"] = tag_type
                        if hasattr(tag_obj, 'importance'):
                            tag_dict["importance"] = importance
                        if hasattr(tag_obj, 'related_content'):
                            tag_dict["related_content"] = related_content
                    except:
                        # 忽略任何错误，确保基本功能正常
                        pass
                    
                    # 创建标签
                    tag = Tag(**tag_dict)
                    db.add(tag)
                    db.commit()
                    db.refresh(tag)
                except Exception as create_error:
                    logger.error(f"创建标签失败: {str(create_error)}")
                    # 尝试使用最小字段集创建
                    tag = Tag(
                        name=tag_name,
                        description=tag_desc,
                        color="#1890ff"
                    )
                    db.add(tag)
                    db.commit()
                    db.refresh(tag)
            else:
                # 更新已有标签的信息，注意兼容性
                try:
                    tag.description = tag_desc
                    # 尝试更新新字段
                    if hasattr(tag, 'tag_type'):
                        tag.tag_type = tag_type
                    if hasattr(tag, 'importance'):
                        tag.importance = importance
                    if hasattr(tag, 'related_content'):
                        tag.related_content = related_content
                    db.commit()
                    db.refresh(tag)
                except Exception as update_error:
                    logger.error(f"更新标签失败: {str(update_error)}")
                    # 忽略更新错误，保持原有标签
            
            created_tags.append(tag)
        
        # 将标签关联到文档
        document.tags = created_tags
        db.commit()
        
        # 构建返回结果，确保兼容性
        result_tags = []
        for tag in created_tags:
            tag_dict = {
                "id": tag.id,
                "name": tag.name,
                "description": tag.description
            }
            # 尝试添加新字段
            try:
                if hasattr(tag, 'tag_type'):
                    tag_dict["type"] = tag.tag_type
                if hasattr(tag, 'importance'):
                    tag_dict["importance"] = tag.importance
                if hasattr(tag, 'related_content'):
                    tag_dict["related_content"] = tag.related_content
            except:
                pass
            result_tags.append(tag_dict)
        
        # 返回结果
        return {
            "success": True,
            "summary": summary,
            "content_excerpts": content_excerpts,
            "tags": result_tags
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析文档失败: {str(e)}")

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