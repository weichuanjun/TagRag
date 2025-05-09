from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import logging
import re

from models import get_db, Tag, Document, DocumentChunk, document_tags, document_chunk_tags, KnowledgeBase
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
    """使用混合方法分析文档内容，自动生成标签和分段摘要
    流程：TF-IDF粗提关键词 -> KeyBERT精提语义关键词 -> 构造GPT Prompt -> LLM生成结构化标签
    """
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
        
        # 获取文档的所有文本块
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        if not chunks:
            raise HTTPException(status_code=404, detail=f"文档没有可分析的内容块")
        
        # 汇总所有文档内容用于关键词提取
        all_content = []
        content_samples = []
        for chunk in chunks:
            try:
                chunk_content = chunk.content
                all_content.append(chunk_content)
                # 每块最多取500个字符作为样本
                if len(content_samples) < 10:  # 最多使用前10个块
                    content_samples.append(chunk_content[:500])
            except Exception as e:
                logger.warning(f"处理文档块 {chunk.id} 时出错: {str(e)}")
        
        if not all_content:
            raise HTTPException(status_code=400, detail="无法提取有效的文档内容")
        
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
            tfidf_keywords = [word for word, score in word_scores[:30]]
            logger.info(f"TF-IDF提取的关键词: {tfidf_keywords}")
            
        except Exception as e:
            logger.warning(f"TF-IDF关键词提取失败: {str(e)}")
            tfidf_keywords = []
        
        # 不再使用KeyBERT，直接使用TF-IDF关键词
        combined_keywords = tfidf_keywords
        
        if not combined_keywords and len(all_content) > 0:
            # 如果关键词提取失败但有内容，使用简单词频作为备选
            from collections import Counter
            import re
            
            # 简单分词 - 针对中英文混合文本
            words = re.findall(r'\b\w+\b|[\u4e00-\u9fa5]+', " ".join(all_content))
            word_counts = Counter(words)
            combined_keywords = [word for word, _ in word_counts.most_common(30)]
        
        # 步骤2: 构造GPT Prompt（带关键词，并让LLM筛选有语义的关键词）
        analysis_prompt = f"""
        请对以下文档内容进行深入分析，提取细粒度的具体特征作为标签，并生成详细摘要。
        
        下面是TF-IDF算法提取的关键词: {', '.join(combined_keywords)}
        
        请先筛选上面关键词列表，去除没有语义意义的词汇，保留有实际含义的术语、概念和实体。
        
        文档内容样本:
        {' '.join(content_samples[:3])}
        
        在分析时，优先考虑关键词中提及的概念，并关注以下方面：
        1. 文档中的主要实体(Entity)：人物、组织、产品、技术组件等
        2. 实体间的关系(Relation)：依赖、包含、属于、使用等
        3. 文档中描述的动作(Action)：调用、配置、创建、查询等
        4. 文档涉及的属性(Property)：状态、特性、参数、字段等
        5. 文档的具体用途和主题(Topic)
        
        请以JSON格式返回以下信息:
        1. 筛选后的关键词(filtered_keywords)：有实际语义的关键词列表
        2. 文档摘要(summary)：详细描述文档的主要内容和用途
        3. 关键实体(entities)：提取3-5个最重要的实体，包含名称和描述
        4. 标签列表(tags)，每个标签应包含:
           - 名称(name)：具体、有辨识度的标签名
           - 描述(description)：对该标签对应内容的详细解释
           - 类型(type)："实体"、"关系"、"动作"、"属性"、"主题"等
           - 重要性(importance)：0-1之间的数字
           - 相关内容(related_content)：与此标签直接相关的内容片段
           - 相关标签(related_tags)：与此标签相关联的其他标签名称(可选)
        
        示例格式：
        ```json
        {{
          "filtered_keywords": ["订单系统", "API", "支付", "用户认证", "数据库"],
          "summary": "这是一个订单管理系统API文档，主要描述了订单创建、查询和支付的接口规范...",
          "entities": [
            {{"name": "订单系统", "description": "处理电商平台订单流程的核心系统"}},
            {{"name": "支付模块", "description": "负责订单支付处理的功能模块"}}
          ],
          "tags": [
            {{
              "name": "订单创建API", 
              "description": "用于创建新订单的POST接口",
              "type": "动作",
              "importance": 0.9,
              "related_content": "POST /api/orders 接口用于创建新订单",
              "related_tags": ["订单系统", "用户认证"]
            }},
            {{
              "name": "订单-用户关系", 
              "description": "订单与用户的从属关系",
              "type": "关系",
              "importance": 0.8,
              "related_content": "订单必须关联到有效的用户ID",
              "related_tags": ["用户系统", "订单实体"]
            }}
          ]
        }}
        ```
        仅返回JSON格式结果，不要添加其它内容。确保标签信息具体且详细，避免过于宽泛的分类。
        """
        
        # 步骤3: 调用LLM生成结构化标签
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
        
        # 提取分析结果
        summary = analysis_json.get("summary", "")
        tags_data = analysis_json.get("tags", [])
        entities_data = analysis_json.get("entities", [])
        
        # 将实体也添加为标签
        for entity in entities_data:
            if "name" in entity and entity["name"]:
                tags_data.append({
                    "name": entity["name"],
                    "description": entity.get("description", ""),
                    "type": "实体",
                    "importance": 0.9,
                    "related_content": ""
                })
        
        # 处理标签
        created_tags = []
        tag_name_to_obj = {}  # 用于建立标签名到标签对象的映射
        
        # 第一步：创建或更新所有标签
        for tag_data in tags_data:
            tag_name = tag_data.get("name")
            if not tag_name:
                continue
                
            tag_desc = tag_data.get("description", "")
            tag_type = tag_data.get("type", "general")
            importance = tag_data.get("importance", 0.5)
            related_content = tag_data.get("related_content", "")
            
            # 检查标签是否已存在
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                # 创建新标签
                tag_dict = {
                    "name": tag_name,
                    "description": tag_desc,
                    "color": "#1890ff",  # 默认颜色
                }
                
                # 根据标签类型设置不同颜色
                if tag_type == "实体":
                    tag_dict["color"] = "#722ed1"  # 紫色
                elif tag_type == "关系":
                    tag_dict["color"] = "#13c2c2"  # 青色
                elif tag_type == "动作":
                    tag_dict["color"] = "#52c41a"  # 绿色
                elif tag_type == "属性":
                    tag_dict["color"] = "#faad14"  # 黄色
                elif tag_type == "主题":
                    tag_dict["color"] = "#1890ff"  # 蓝色
                
                # 尝试添加新字段
                try:
                    tag_obj = Tag()
                    if hasattr(tag_obj, 'tag_type'):
                        tag_dict["tag_type"] = tag_type
                    if hasattr(tag_obj, 'importance'):
                        tag_dict["importance"] = importance
                    if hasattr(tag_obj, 'related_content'):
                        tag_dict["related_content"] = related_content
                except:
                    pass
                
                # 创建标签
                try:
                    tag = Tag(**tag_dict)
                    db.add(tag)
                    db.commit()
                    db.refresh(tag)
                except Exception as e:
                    logger.error(f"创建标签失败: {str(e)}")
                    db.rollback()
                    # 简化标签创建
                    tag = Tag(
                        name=tag_name,
                        description=tag_desc,
                        color=tag_dict["color"]
                    )
                    db.add(tag)
                    db.commit()
                    db.refresh(tag)
            else:
                # 更新已有标签
                try:
                    if not tag.description or len(tag.description) < len(tag_desc):
                        tag.description = tag_desc
                    
                    # 尝试更新新字段
                    if hasattr(tag, 'tag_type') and tag_type != "general":
                        tag.tag_type = tag_type
                    if hasattr(tag, 'importance') and importance > 0:
                        tag.importance = max(tag.importance, importance)  # 取较高的重要性
                    if hasattr(tag, 'related_content') and related_content:
                        tag.related_content = related_content
                    
                    db.commit()
                    db.refresh(tag)
                except Exception as e:
                    logger.error(f"更新标签失败: {str(e)}")
                    db.rollback()
            
            created_tags.append(tag)
            tag_name_to_obj[tag_name] = tag
        
        # 第二步：创建标签间的关系（如果模型支持）
        try:
            for tag_data in tags_data:
                tag_name = tag_data.get("name")
                related_tags = tag_data.get("related_tags", [])
                
                if not tag_name or not related_tags or tag_name not in tag_name_to_obj:
                    continue
                
                current_tag = tag_name_to_obj[tag_name]
                
                for related_tag_name in related_tags:
                    if related_tag_name in tag_name_to_obj:
                        related_tag = tag_name_to_obj[related_tag_name]
                        
                        # 如果是"关系"类型的标签，尝试设置父子关系
                        if tag_data.get("type") == "关系" and hasattr(related_tag, 'parent_id'):
                            # 将related_tag设为current_tag的子标签
                            related_tag.parent_id = current_tag.id
                            db.commit()
        except Exception as e:
            logger.warning(f"创建标签关系时出错: {str(e)}")
        
        # 将标签关联到文档
        document.tags = created_tags
        db.commit()
        
        # 构建返回结果
        result_tags = []
        for tag in created_tags:
            tag_dict = {
                "id": tag.id,
                "name": tag.name,
                "description": tag.description,
                "color": tag.color
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
        
        # 返回结果 - 增加筛选后的关键词
        return {
            "success": True,
            "summary": summary,
            "keywords": analysis_json.get("filtered_keywords", combined_keywords[:20]),
            "tags": result_tags
        }
    except Exception as e:
        logger.error(f"分析文档失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"处理文档失败: {str(e)}")

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