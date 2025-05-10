import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import json
import shutil
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
import datetime

# 确保数据目录存在
os.makedirs("data/db", exist_ok=True)
os.makedirs("data/vector_db", exist_ok=True)

# 导入配置模块
from config import VECTOR_DB_DIR

# 导入原有功能模块
from vector_store import VectorStore
from document_processor import DocumentProcessor
from agent_manager import AgentManager, TagRAGChatResponse
from models import create_tables, get_db, CodeRepository, KnowledgeBase, Document as DBDocument, DocumentChunk, Tag as DBTag, document_tags, TagDependency

# 导入新增的代码分析模块
from code_analysis_routes import router as code_analysis_router
# 导入知识库管理模块
from knowledge_base_routes import router as knowledge_base_router
# 导入Agent Prompt管理模块
from agent_prompt_routes import router as agent_prompt_router
# 导入图可视化模块
from graph_visualizer import router as graph_router
# 导入标签管理模块
from tag_routes import router as tag_router

# 导入必要的模块以处理文档分析
from tag_routes import llm_client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)

logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(title="RAG Agent API", description="基于AutoGen的多智能体RAG系统")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化组件
default_vector_store = VectorStore()
document_processor = DocumentProcessor(default_vector_store)
agent_manager = AgentManager(default_vector_store)

# 创建向量存储缓存
# 以仓库ID为键，VectorStore实例为值
vector_store_cache = {}

# 添加代码分析路由
app.include_router(code_analysis_router)
# 添加知识库管理路由
app.include_router(knowledge_base_router)
# 添加Agent Prompt管理路由
app.include_router(agent_prompt_router)
# 添加图可视化路由
app.include_router(graph_router)
# 添加标签管理路由
app.include_router(tag_router)

# 确保数据库和表已创建
create_tables()

# 问答请求模型
class QuestionRequest(BaseModel):
    query: str
    knowledge_base_id: Optional[int] = None
    use_code_analysis: bool = False # Relevant for original flow
    use_tag_rag: bool = False # New flag to select TagRAG flow
    prompt_configs: Optional[Dict[str, str]] = None

# TagRAG 请求模型 (与 QuestionRequest 相同，但默认 use_tag_rag=True)
class TagRAGRequest(BaseModel):
    query: str
    knowledge_base_id: Optional[int] = None
    use_code_analysis: bool = False
    prompt_configs: Optional[Dict[str, str]] = None

# 文档上传请求模型
class DocumentUploadRequest(BaseModel):
    file_path: str
    repository_id: Optional[int] = None
    knowledge_base_id: Optional[int] = None
    chunk_size: int = 1000

# 用于清理缓存的工具函数
def get_vector_store(repository_id: int = None, knowledge_base_id: int = None) -> VectorStore:
    """从缓存获取向量存储实例，如果不存在则创建
    
    优先使用 knowledge_base_id 来确定集合，如果没有提供，则使用 repository_id
    """
    # 决定使用哪个ID和缓存键
    if knowledge_base_id is not None:
        effective_id = knowledge_base_id
        cache_key = f"kb_{knowledge_base_id}"
        logger.info(f"使用knowledge_base_id={knowledge_base_id}作为主要标识符")
    elif repository_id is not None:
        effective_id = repository_id
        cache_key = f"repo_{repository_id}"
        logger.info(f"使用repository_id={repository_id}作为主要标识符")
    else:
        logger.info("没有提供knowledge_base_id或repository_id，使用默认向量存储")
        return default_vector_store
    
    # 检查缓存
    if cache_key not in vector_store_cache:
        logger.info(f"创建新的向量存储实例: {cache_key}")
        if knowledge_base_id is not None:
            vector_store_cache[cache_key] = VectorStore(knowledge_base_id=knowledge_base_id)
        else:
            vector_store_cache[cache_key] = VectorStore(repository_id=repository_id)
    else:
        logger.info(f"使用缓存的向量存储实例: {cache_key}")
    
    return vector_store_cache[cache_key]

# API端点
@app.get("/")
async def read_root():
    # 添加调试信息，打印所有路由
    routes_info = []
    for route in app.routes:
        route_info = {"path": route.path, "methods": list(route.methods) if hasattr(route, "methods") else None}
        routes_info.append(route_info)
    
    return {
        "message": "欢迎使用RAG Agent API",
        "routes": routes_info
    }

@app.post("/upload-document")
async def upload_document(request: DocumentUploadRequest, db = Depends(get_db)):
    """上传文档并处理，关联到特定代码库或知识库"""
    try:
        # 检查代码库是否存在（如果指定了）
        if request.repository_id:
            repository = db.query(CodeRepository).filter(CodeRepository.id == request.repository_id).first()
            if not repository:
                raise HTTPException(status_code=404, detail=f"找不到ID为{request.repository_id}的代码库")
        
        # 检查知识库是否存在（如果指定了）
        if request.knowledge_base_id:
            knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == request.knowledge_base_id).first()
            if not knowledge_base:
                raise HTTPException(status_code=404, detail=f"找不到ID为{request.knowledge_base_id}的知识库")
        
        # 获取向量存储实例
        repo_vector_store = get_vector_store(request.repository_id, request.knowledge_base_id)
        repo_document_processor = DocumentProcessor(repo_vector_store)
        
        # 处理文档
        result = await repo_document_processor.process_document(
            request.file_path, 
            request.repository_id,
            db,
            request.chunk_size,
            request.knowledge_base_id
        )
        return result
    except Exception as e:
        logger.error(f"处理文档时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理文档失败: {str(e)}")

@app.get("/documents")
async def get_documents(repository_id: Optional[int] = None, db = Depends(get_db)):
    """获取文档列表，可选择按代码库筛选"""
    try:
        # 如果指定了代码库，使用特定的向量存储
        if repository_id:
            vector_store = get_vector_store(repository_id)
            docs = await vector_store.get_document_list(repository_id)
        else:
            # 查询所有代码库的文档
            docs = await default_vector_store.get_document_list()
        return {"documents": docs}
    except Exception as e:
        logger.error(f"获取文档列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")

@app.post("/chat/tag-rag")
async def tag_rag_chat(request: TagRAGRequest, db: Session = Depends(get_db)):
    """专用于TagRAG流程的问答接口，直接将请求转发到主要的ask接口并强制启用TagRAG"""
    try:
        logger.info(f"[/chat/tag-rag] Received query: '{request.query[:50]}...' for KB ID: {request.knowledge_base_id}")
        
        # 创建一个等价的 QuestionRequest 对象，但强制 use_tag_rag=True
        question_req = QuestionRequest(
            query=request.query,
            knowledge_base_id=request.knowledge_base_id,
            use_code_analysis=request.use_code_analysis,
            use_tag_rag=True,  # 强制启用 TagRAG
            prompt_configs=request.prompt_configs
        )
        
        # 调用主要的 ask_question 功能
        return await ask_question(question_req, db)
    except Exception as e:
        logger.error(f"[/chat/tag-rag] Error: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=500, detail=f"TagRAG处理错误: {str(e)}")

@app.post("/ask")
async def ask_question(request: QuestionRequest, db: Session = Depends(get_db)):
    """处理用户问题，支持基于特定知识库的问答，并可选TagRAG流程"""
    try:
        logger.info(f"Received query: '{request.query[:50]}...' for KB ID: {request.knowledge_base_id}")
        logger.info(f"Using TagRAG: {request.use_tag_rag}, Use Code Analysis: {request.use_code_analysis}")
        
        knowledge_base_id = request.knowledge_base_id
        repository_id = None
        
        # 仅一次查询知识库信息
        if knowledge_base_id:
            kb_entry = db.query(KnowledgeBase).options(joinedload(KnowledgeBase.repositories)).filter(KnowledgeBase.id == knowledge_base_id).first()
            if kb_entry and kb_entry.repositories:
                repository_id = kb_entry.repositories[0].id 
                logger.info(f"Found repository_id {repository_id} for KB {knowledge_base_id}")
            else:
                logger.warning(f"No specific repository found for KB ID {knowledge_base_id}. Will use KB ID directly without repository.")
        
        # 使用修改后的 get_vector_store 函数，同时传递 repository_id 和 knowledge_base_id
        vector_store_for_query = get_vector_store(repository_id=repository_id, knowledge_base_id=knowledge_base_id)
        
        if not vector_store_for_query:
             logger.error(f"Could not get VectorStore for effective ID: {repository_id} (derived from KB ID: {knowledge_base_id})")
             raise HTTPException(status_code=500, detail="Failed to initialize vector store for the query.")

        # 为每个请求创建一个新的 AgentManager 实例，确保使用正确的 VectorStore 和 DB session
        current_agent_manager = AgentManager(vector_store=vector_store_for_query, db_session_factory=get_db, db=db)
        
        if request.use_tag_rag:
            if not knowledge_base_id: # TagRAG 必须有知识库ID
                logger.error("TagRAG flow initiated without a knowledge_base_id.")
                raise HTTPException(status_code=400, detail="Knowledge Base ID is required for TagRAG flow.")

            logger.info("Using TagRAG flow in /ask endpoint...")
            try:
                tag_rag_response: TagRAGChatResponse = await current_agent_manager.generate_answer_tag_rag(
                    user_query=request.query,
                    vector_store_for_query=vector_store_for_query,
                    knowledge_base_id=knowledge_base_id,
                    prompt_configs=request.prompt_configs
                )
                return tag_rag_response 
            except HTTPException as http_exc:
                raise http_exc
            except Exception as tag_rag_err:
                 logger.error(f"Error during TagRAG processing in /ask: {tag_rag_err}", exc_info=True)
                 # 在抛出前记录更详细的上下文
                 thinking_process_on_error = current_agent_manager.get_thinking_process()
                 error_detail_with_context = {
                     "error_message": f"Error in TagRAG processing: {str(tag_rag_err)}",
                     "query": request.query,
                     "kb_id": knowledge_base_id,
                     "thinking_process_trace": thinking_process_on_error[-5:] # Log last 5 steps
                 }
                 logger.error(f"TagRAG Error Context: {json.dumps(error_detail_with_context, indent=2, ensure_ascii=False)}")
                 raise HTTPException(status_code=500, detail=f"Error in TagRAG processing: {str(tag_rag_err)}")
        else:
            # --- Original Flow --- 
            logger.info("Using Original flow in /ask endpoint...")
            code_analyzer = None
            if request.use_code_analysis:
                if repository_id is None and knowledge_base_id: # 如果只有 kb_id, 尝试用它作为 repo_id
                     logger.info(f"Original flow with code analysis: No specific repository_id, using knowledge_base_id {knowledge_base_id} as potential repo_id.")
                     actual_repo_id_for_code_analysis = knowledge_base_id
                elif repository_id:
                     actual_repo_id_for_code_analysis = repository_id
                else: # Code analysis needs a repository context
                    logger.warning("Code analysis requested but no repository_id or knowledge_base_id provided that maps to a repository.")
                    actual_repo_id_for_code_analysis = None # Code analysis will likely be skipped or fail

                if actual_repo_id_for_code_analysis:
                    logger.info(f"Initializing CodeAnalysisService for repository {actual_repo_id_for_code_analysis} (Original Flow)")
                    try:
                        from analysis_service import CodeAnalysisService
                        code_analyzer = CodeAnalysisService(db)
                    except ImportError:
                         logger.error("CodeAnalysisService not found or import failed.")
                         raise HTTPException(status_code=501, detail="Code analysis feature is configured but service is unavailable.")
                    except Exception as code_init_err:
                        logger.error(f"Failed to initialize CodeAnalysisService: {code_init_err}", exc_info=True)
                        raise HTTPException(status_code=500, detail=f"Failed to initialize code analysis: {code_init_err}")
            
            try:
                answer_str = await current_agent_manager.generate_answer_original(
                    user_query=request.query, 
                    use_code_analysis=request.use_code_analysis,
                    code_analyzer=code_analyzer,
                    vector_store=vector_store_for_query, 
                    repository_id=repository_id, 
                    knowledge_base_id=knowledge_base_id,
                    prompt_configs=request.prompt_configs
                )
                thinking_process_original = current_agent_manager.get_thinking_process()
                return {"answer": answer_str, "thinking_process": thinking_process_original}
            except Exception as original_flow_err:
                logger.error(f"Error during Original flow processing in /ask: {original_flow_err}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error in Original flow processing: {str(original_flow_err)}")

    except HTTPException as http_exc:
        raise http_exc 
    except Exception as e:
        logger.error(f"Unhandled error in /ask endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/code-fields")
async def get_code_fields(repository_id: Optional[int] = None):
    """获取代码字段列表"""
    try:
        from analysis_service import CodeAnalysisService
        
        # 创建数据库会话
        db_session = next(get_db())
        code_analyzer = CodeAnalysisService(db_session)
        
        fields = await code_analyzer.get_all_fields(repository_id)
        return {"fields": fields}
    except Exception as e:
        logger.error(f"获取代码字段时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码字段失败: {str(e)}")

@app.get("/field-impact")
async def get_field_impact(field_name: str, repository_id: Optional[int] = None):
    """获取字段影响"""
    try:
        from analysis_service import CodeAnalysisService
        
        # 创建数据库会话
        db_session = next(get_db())
        code_analyzer = CodeAnalysisService(db_session)
        
        impact = await code_analyzer.get_field_impact(field_name, repository_id)
        return {"impact": impact}
    except Exception as e:
        logger.error(f"获取字段影响时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取字段影响失败: {str(e)}")

@app.post("/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    repository_id: Optional[int] = Form(None),
    knowledge_base_id: Optional[int] = Form(None),
    chunk_size: int = Form(1000),
    db = Depends(get_db)
):
    """上传文件并处理，关联到特定代码库或知识库"""
    try:
        # 检查代码库是否存在（如果指定了）
        if repository_id:
            repository = db.query(CodeRepository).filter(CodeRepository.id == repository_id).first()
            if not repository:
                raise HTTPException(status_code=404, detail=f"找不到ID为{repository_id}的代码库")
        
        # 检查知识库是否存在（如果指定了）
        if knowledge_base_id:
            knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
            if not knowledge_base:
                raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
        
        # 创建临时文件保存上传的内容
        import tempfile
        
        # 保存上传的文件
        file_extension = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            # 复制上传的文件内容到临时文件
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        
        logger.info(f"已保存上传文件到临时路径: {temp_file_path}")
        
        # 获取向量存储实例
        repo_vector_store = get_vector_store(repository_id, knowledge_base_id)
        repo_document_processor = DocumentProcessor(repo_vector_store)
        
        # 处理文档
        result = await repo_document_processor.process_document(
            temp_file_path, 
            repository_id,
            db,
            chunk_size,
            knowledge_base_id,
            original_filename=file.filename
        )
        
        # 返回结果，添加文件保存路径
        result["file_path"] = temp_file_path
        result["saved_as"] = os.path.basename(temp_file_path)
        
        return result
    except HTTPException as http_exc:
        logger.error(f"HTTP exception during file upload: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        from fastapi import HTTPException as FastAPIHTTPExceptionForUpload
        logger.error(f"处理上传文件时出错: {str(e)} ({type(e).__name__})", exc_info=True)
        raise FastAPIHTTPExceptionForUpload(status_code=500, detail=f"处理上传文件失败: {str(e)}")

# 中间件用于请求日志
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"请求: {request.method} {request.url}")
    response = await call_next(request)
    return response

@app.post("/analyze-doc-test/{document_id}")
async def analyze_doc_test(document_id: int, db = Depends(get_db)):
    """用于测试的文档分析路由"""
    logger.info(f"测试路由：分析文档ID {document_id}")
    try:
        # 查找文档
        from models import Document, DocumentChunk
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"文档ID {document_id} 不存在")
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
            
        # 获取文档的所有文本块
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        if not chunks:
            logger.error(f"文档没有可分析的内容块")
            raise HTTPException(status_code=404, detail=f"文档没有可分析的内容块")
        
        # 简化处理，返回文档信息
        return {
            "success": True,
            "message": "测试路由可以访问",
            "document_id": document_id,
            "chunks_count": len(chunks)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试路由错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"测试路由错误: {str(e)}")

@app.get("/debug/routes")
async def get_routes():
    """返回所有已注册的路由详情，帮助调试"""
    routes_info = []
    for route in app.routes:
        route_info = {
            "path": route.path,
            "name": route.name if hasattr(route, "name") else None,
            "methods": list(route.methods) if hasattr(route, "methods") else None,
            "endpoint": str(route.endpoint) if hasattr(route, "endpoint") else None,
            "endpoint_name": route.endpoint.__name__ if hasattr(route, "endpoint") and hasattr(route.endpoint, "__name__") else None
        }
        routes_info.append(route_info)
    
    # 特别关注与文档分析相关的路由
    analyze_routes = [r for r in routes_info if "analyze" in r.get("path", "")]
    
    return {
        "total_routes": len(routes_info),
        "analyze_routes": analyze_routes,
        "all_routes": routes_info
    }

@app.post("/direct/analyze-document/{document_id}")
async def direct_analyze_document(document_id: int, db = Depends(get_db)):
    """直接在main.py中实现的文档分析功能"""
    logger.info(f"直接分析路由：处理文档ID {document_id}")
    
    try:
        from models import Document, DocumentChunk, Tag
        import json
        import re
        
        # 查找文档
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"文档ID {document_id} 不存在")
            raise HTTPException(status_code=404, detail=f"文档ID {document_id} 不存在")
        
        # 获取文档的所有文本块
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        if not chunks:
            logger.error(f"文档没有可分析的内容块")
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
            logger.error("无法提取有效的文档内容样本")
            raise HTTPException(status_code=400, detail="无法提取有效的文档内容样本")
        
        # 构建分析提示
        analysis_prompt = f"""
        请对以下文档内容进行简短分析，提取最重要的标签。
        
        文档内容样本:
        {' '.join(content_samples[:2])}
        
        请以JSON格式返回以下信息:
        1. 摘要：简短描述文档内容
        2. 标签列表：3-5个关键标签，包含名称和描述
        
        示例格式：
        ```json
        {{
          "summary": "这是关于X的文档...",
          "tags": [
            {{ "name": "标签1", "description": "描述1" }},
            {{ "name": "标签2", "description": "描述2" }}
          ]
        }}
        ```
        """
        
        # 调用LLM进行分析
        analysis_result = await llm_client.generate(analysis_prompt)
        logger.info(f"LLM返回结果长度: {len(analysis_result)}")
        
        # 解析JSON结果
        try:
            # 查找JSON部分
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', analysis_result)
            if json_match:
                analysis_json = json.loads(json_match.group(1))
                logger.info("成功从markdown代码块解析JSON")
            else:
                # 尝试直接解析整个文本作为JSON
                analysis_json = json.loads(analysis_result)
                logger.info("成功直接解析JSON")
        except Exception as e:
            logger.error(f"解析LLM返回的JSON失败: {str(e)}，原始返回: {analysis_result}")
            raise HTTPException(status_code=500, detail=f"解析AI分析结果失败: {str(e)}")
        
        # 提取分析结果
        summary = analysis_json.get("summary", "")
        tags_data = analysis_json.get("tags", [])
        
        # 处理标签
        created_tags = []
        for tag_data in tags_data:
            tag_name = tag_data.get("name")
            tag_desc = tag_data.get("description", "")
            
            # 检查标签是否已存在
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                # 创建新标签
                tag = Tag(
                    name=tag_name,
                    description=tag_desc,
                    color="#1890ff"  # 默认颜色
                )
                db.add(tag)
                db.commit()
                db.refresh(tag)
                logger.info(f"创建了新标签: {tag_name}")
            
            created_tags.append(tag)
        
        # 将标签关联到文档
        document.tags = created_tags
        db.commit()
        logger.info(f"成功关联 {len(created_tags)} 个标签到文档")
        
        # 返回结果
        return {
            "success": True,
            "summary": summary,
            "tags": [{"id": tag.id, "name": tag.name, "description": tag.description} for tag in created_tags]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"直接分析文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"直接分析文档失败: {str(e)}")

# --- New/Enhanced Document Management Endpoints --- 

# Pydantic models for Tag response (if not already defined globally or in tag_routes)
class TagResponseSchema(BaseModel):
    id: int
    name: str
    color: Optional[str] = None
    description: Optional[str] = None
    # Add other fields if needed, like parent_id, etc.

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: int
    path: Optional[str] = None
    source: Optional[str] = None
    document_type: Optional[str] = None
    chunks_count: int = 0
    added_at: Optional[datetime.datetime] = None
    processed_at: Optional[datetime.datetime] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    knowledge_base_id: Optional[int] = None
    knowledge_base_name: Optional[str] = None # New field
    repository_id: Optional[int] = None
    tags: List[TagResponseSchema] = []

    class Config:
        from_attributes = True

@app.get("/documents/list", response_model=List[DocumentResponse])
async def list_all_documents(db: Session = Depends(get_db)):
    """获取所有已处理文档的列表，包含标签和知识库名称。"""
    try:
        logger.info("Fetching all documents with their tags and knowledge base names.")
        # Use joinedload to efficiently fetch related tags and knowledge_base
        db_documents = db.query(DBDocument).options(
            joinedload(DBDocument.tags),
            joinedload(DBDocument.knowledge_base) # Eager load knowledge_base
        ).order_by(desc(DBDocument.processed_at)).all()
        
        response_documents = []
        for doc in db_documents:
            tags_response = [TagResponseSchema.from_orm(tag) for tag in doc.tags]
            kb_name = doc.knowledge_base.name if doc.knowledge_base else None
            
            response_documents.append(
                DocumentResponse(
                    id=doc.id,
                    path=doc.path,
                    source=doc.source,
                    document_type=doc.document_type,
                    chunks_count=doc.chunks_count,
                    added_at=doc.added_at,
                    processed_at=doc.processed_at,
                    status=doc.status,
                    error_message=doc.error_message,
                    knowledge_base_id=doc.knowledge_base_id,
                    knowledge_base_name=kb_name, # Include KB name
                    repository_id=doc.repository_id,
                    tags=tags_response
                )
            )
        logger.info(f"Successfully fetched {len(response_documents)} documents.")
        return response_documents
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")

@app.get("/documents/{document_id}/chunks", response_model=List[Dict[str, Any]]) # Add response model
async def get_document_chunks(document_id: int, db: Session = Depends(get_db)):
    """获取指定文档的所有块信息"""
    try:
        # 检查文档是否存在
        db_document = db.query(DBDocument).filter(DBDocument.id == document_id).first()
        if not db_document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found.")

        # 查询该文档的所有块，按索引排序
        db_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index).all()
        
        result_chunks = []
        for chunk in db_chunks:
            metadata = {}
            try:
                # 尝试解析存储的 JSON 元数据
                metadata = json.loads(chunk.chunk_metadata or "{}")
            except json.JSONDecodeError:
                logger.warning(f"Could not decode chunk_metadata JSON for chunk {chunk.id} of document {document_id}")
            
            # 确保关键信息存在，即使JSON解析失败或元数据不完整
            result_chunks.append({
                "id": chunk.id, # Chunk ID itself
                "chunk_index": chunk.chunk_index,
                "content": chunk.content, # The full content of the chunk
                "token_count": chunk.token_count if chunk.token_count is not None else metadata.get('token_count'), # Prefer dedicated column
                "structural_type": chunk.structural_type or metadata.get('structural_type'), # Prefer dedicated column
                "metadata": metadata # Include the full metadata dictionary as well
            })
        return result_chunks
    except HTTPException: # Re-raise validation errors
        raise
    except Exception as e:
        logger.error(f"Error getting chunks for document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get document chunks")

@app.delete("/documents/{document_id}", status_code=200, response_model=Dict[str, Any]) # Add response model
async def delete_document_endpoint(document_id: int, db: Session = Depends(get_db)):
    """
    删除文档及其块、向量嵌入和标签关联。
    """
    try:
        logger.info(f"Attempting to delete document with ID: {document_id}")

        db_document = db.query(DBDocument).filter(DBDocument.id == document_id).first()
        if not db_document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found.")

        repository_id = db_document.repository_id # Needed for specific vector store
        original_file_path = db_document.path # Store path for optional file deletion later

        # 1. Delete associated chunks from DocumentChunk table
        num_chunks_deleted = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(synchronize_session=False)
        logger.info(f"Deleted {num_chunks_deleted} chunks from database for document_id: {document_id}")

        # 2. Clear many-to-many relationship with Tags before deleting the document
        try:
            if hasattr(db_document, 'tags') and db_document.tags:
                db_document.tags.clear() 
                db.flush() # Ensure the clear operation is sent to DB before deleting the document itself
                logger.info(f"Cleared tag associations for document_id: {document_id}")
            else:
                logger.info(f"Document {document_id} had no tags to clear or relationship missing.")
        except Exception as e_clear_tags:
            # Log error but proceed with deletion, association table might be cleared by cascade anyway
            logger.error(f"Error explicitly clearing tags for document {document_id}: {e_clear_tags}")
            # db.rollback() # Might not want to rollback just for this?

        # 3. Delete document from DBDocument table (assuming cascade delete handles document_tags)
        db.delete(db_document)
        logger.info(f"Deleted document record from database for document_id: {document_id}")
        
        # Commit DB changes (chunks deletion, tag association clearing, document deletion)
        db.commit() 

        # 4. Delete from Vector Store
        try:
            vector_store_instance = get_vector_store(repository_id) 
            if vector_store_instance and hasattr(vector_store_instance, 'collection') and vector_store_instance.collection:
                collection_name = vector_store_instance.collection.name
                logger.info(f"Attempting to delete vectors from ChromaDB collection '{collection_name}' using filter: {{\"document_id\": {document_id}}}")
                vector_store_instance.collection.delete(where={"document_id": document_id})
                logger.info(f"ChromaDB delete call completed for document_id: {document_id} in collection '{collection_name}'")
            elif vector_store_instance:
                logger.warning(f"Vector store instance for repo_id {repository_id} found, but no valid 'collection'? Skipping vector deletion for doc_id: {document_id}")
            else:
                logger.warning(f"Could not get vector store instance for repo_id: {repository_id}. Skipping vector deletion for doc_id: {document_id}")
        except Exception as e_vs_delete:
            logger.error(f"Error deleting vectors for document_id {document_id}: {e_vs_delete}", exc_info=True)

        # 5. (Optional) Delete the original file from the filesystem
        # Consider security implications and configuration options before enabling this.
        # should_delete_file = False # Get from config or request parameter
        # if should_delete_file and original_file_path and os.path.exists(original_file_path):
        #     try:
        #         os.remove(original_file_path)
        #         logger.info(f"Deleted original file: {original_file_path}")
        #     except Exception as e_file_delete:
        #         logger.error(f"Error deleting original file {original_file_path}: {e_file_delete}")
        
        return {"status": "success", "message": f"Document ID {document_id} and its associated data have been deleted."} # Return dict for response_model

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting document_id {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

class DocumentTagUpdatePayload(BaseModel):
    tag_names: List[str]
    default_tag_type: Optional[str] = "manual"
    default_tag_color: Optional[str] = "#3498db" # A default blue color for manual tags

@app.post("/documents/{document_id}/tags", status_code=200, response_model=Dict[str, Any])
async def update_document_tags_api(
    document_id: int,
    payload: DocumentTagUpdatePayload,
    db: Session = Depends(get_db),
    # vector_store_instance: VectorStore = Depends(get_vector_store) # Assuming get_vector_store is defined
    # For now, let's instantiate VectorStore directly if get_vector_store is not ready
):
    """
    Updates the tags for a specific document. 
    Replaces existing tags with the new list of tags provided.
    Creates new tags if they don't exist.
    Updates corresponding chunks in the vector store.
    """
    db_document = db.query(DBDocument).filter(DBDocument.id == document_id).first()
    if not db_document:
        raise HTTPException(status_code=404, detail="Document not found")

    current_document_db_tags = []
    for tag_name in payload.tag_names:
        tag_name_cleaned = tag_name.strip()[:255]
        if not tag_name_cleaned:
            continue
        
        db_tag = db.query(DBTag).filter(DBTag.name.ilike(tag_name_cleaned)).first()
        if not db_tag:
            db_tag = DBTag(
                name=tag_name_cleaned,
                tag_type=payload.default_tag_type,
                description=f"{payload.default_tag_type.capitalize()} tag: {tag_name_cleaned}",
                color=payload.default_tag_color
            )
            db.add(db_tag)
            db.commit() # Commit each new tag to get its ID for immediate use or refresh
            db.refresh(db_tag)
            logger.info(f"Created new tag '{db_tag.name}' with type '{db_tag.tag_type}' and ID {db_tag.id}")
        elif db_tag.tag_type != "manual" and payload.default_tag_type == "manual":
            # If an existing LLM tag is now manually confirmed/added, 
            # we might want to update its type or ensure its importance.
            # For now, just ensuring it is associated is key.
            # Optionally, update its type if it was, for example, 'llm-generated'
            # db_tag.tag_type = "manual" # Uncomment if overriding type is desired
            # db.commit()
            # db.refresh(db_tag)
            logger.info(f"Tag '{db_tag.name}' (ID {db_tag.id}) already exists with type '{db_tag.tag_type}'. Associating as manual.")
            pass

        current_document_db_tags.append(db_tag)
    
    # Replace existing tags for the document
    db_document.tags = current_document_db_tags
    db.commit()
    db.refresh(db_document) # Refresh to get the updated tags list on the document object
    logger.info(f"Updated tags in DB for document ID {document_id}. New tags: {[t.name for t in db_document.tags]}")

    # Now, update the vector store
    # Initialize VectorStore using the repository_id from the document
    # Assuming repository_id corresponds to knowledge_base_id or a similar concept for collection scoping
    repo_id_for_vs = str(db_document.repository_id) if db_document.repository_id is not None else "default"
    # Fallback if knowledge_base_id is the true repository identifier for vector store collections
    if hasattr(db_document, 'knowledge_base_id') and db_document.knowledge_base_id is not None:
        repo_id_for_vs = str(db_document.knowledge_base_id)
    
    # Handle case where vector store might not be per-repository but global, or uses a specific naming scheme
    # Based on logs, it seems VectorStore(repository_id="default") or similar is used when no specific repo is given.
    # Let's assume the Document's knowledge_base_id (if present) or repository_id is the key.
    # If these are None, we might fall back to a global/default vector store configuration.
    # The current VectorStore init seems to be `VectorStore(repository_id=...)` which might map to a dir or collection.
    # If db_document.repository_id can be None, we need a fallback for VectorStore initialization.

    # Simplified VectorStore instantiation based on prior context
    # If your VectorStore class handles repository_id=None by using a default, this is fine.
    # Otherwise, ensure repo_id_for_vs is always a valid identifier for your VectorStore setup.
    vector_store_instance = VectorStore(repository_id=repo_id_for_vs)
    
    all_final_tag_ids = [tag.id for tag in db_document.tags if tag.id is not None] # Ensure IDs are not None
    
    logger.info(f"Calling update_tags_for_document_chunks for doc_id {document_id} with tag_ids: {all_final_tag_ids} for VS repo: {repo_id_for_vs}")
    vs_update_result = await vector_store_instance.update_tags_for_document_chunks(document_id, all_final_tag_ids)
    
    if vs_update_result.get("status") == "error":
        logger.error(f"Failed to update tags in vector store for document {document_id}: {vs_update_result.get('message')}")
        # Potentially raise an HTTPException or return a specific error response
        # For now, we'll still return the document data but log the error.
        # raise HTTPException(status_code=500, detail=f"Failed to update tags in vector store: {vs_update_result.get('message')}")

    # Prepare response - reuse existing schema if possible
    # DocumentWithTagsResponse needs: id, source, document_type, created_at, updated_at, status, chunks_count, error_message, knowledge_base_name, tags
    kb_name = db.query(KnowledgeBase.name).filter(KnowledgeBase.id == db_document.knowledge_base_id).scalar_one_or_none() if db_document.knowledge_base_id else None
    
    # Manually construct the response to match DocumentWithTagsResponse fields
    response_tags = [
        TagResponseSchema(id=tag.id, name=tag.name, description=tag.description, color=tag.color, tag_type=tag.tag_type)
        for tag in db_document.tags
    ]

    return {
        "id": db_document.id,
        "source": db_document.source,
        "document_type": db_document.document_type,
        "created_at": db_document.added_at,
        "updated_at": db_document.processed_at,
        "status": db_document.status,
        "chunks_count": db_document.chunks_count,
        "error_message": db_document.error_message,
        "knowledge_base_name": kb_name,
        "tags": response_tags
    }

# 主函数
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 