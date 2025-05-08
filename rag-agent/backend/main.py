import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import json
import shutil

# 确保数据目录存在
os.makedirs("data/db", exist_ok=True)
os.makedirs("data/vector_db", exist_ok=True)

# 导入配置模块
from config import VECTOR_DB_DIR

# 导入原有功能模块
from vector_store import VectorStore
from document_processor import DocumentProcessor
from agent_manager import AgentManager
from models import create_tables, get_db, CodeRepository, KnowledgeBase

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
    use_code_analysis: bool = False
    prompt_configs: Optional[Dict[str, str]] = None

# 文档上传请求模型
class DocumentUploadRequest(BaseModel):
    file_path: str
    repository_id: Optional[int] = None
    knowledge_base_id: Optional[int] = None
    chunk_size: int = 1000

# 用于清理缓存的工具函数
def get_vector_store(repository_id: int = None) -> VectorStore:
    """从缓存获取向量存储实例，如果不存在则创建"""
    if repository_id is None:
        return default_vector_store
        
    cache_key = f"repo_{repository_id}"
    if cache_key not in vector_store_cache:
        logger.info(f"创建新的向量存储实例: {cache_key}")
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
        repo_vector_store = get_vector_store(request.repository_id)
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
    """获取已处理的文档列表，可选择按代码库筛选"""
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

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    """处理用户问题，支持基于特定知识库的问答"""
    try:
        # 记录请求参数
        logger.info(f"收到问题请求: {request.query}")
        logger.info(f"知识库ID: {request.knowledge_base_id}")
        logger.info(f"是否使用代码分析: {request.use_code_analysis}")
        logger.info(f"提示词配置: {request.prompt_configs}")
        
        # 获取知识库ID
        knowledge_base_id = request.knowledge_base_id
        
        # 查询知识库中的代码库
        repository_id = None
        if knowledge_base_id:
            db = next(get_db())
            try:
                # 查找知识库中的第一个代码库
                repo = db.query(CodeRepository).filter(
                    CodeRepository.knowledge_base_id == knowledge_base_id
                ).first()
                if repo:
                    repository_id = repo.id
                    logger.info(f"找到知识库 {knowledge_base_id} 中的代码库 {repository_id}")
            except Exception as e:
                logger.error(f"查询知识库代码库时出错: {str(e)}")
        
        # 使用指定代码库的向量存储或默认存储
        vector_store = get_vector_store(repository_id)
        if repository_id:
            logger.info(f"使用代码库 {repository_id} 的向量存储回答问题")
        
        # 初始化代码分析器（如果开启了代码分析）
        code_analyzer = None
        if request.use_code_analysis and repository_id:
            from analysis_service import CodeAnalysisService
            from sqlalchemy.orm import Session
            
            # 创建数据库会话
            db_session = next(get_db())
            try:
                # 创建代码分析服务
                code_analyzer = CodeAnalysisService(db_session)
                logger.info(f"已创建代码分析服务，用于分析代码库")
                
                # 预先检查字段列表，确保服务正常工作
                try:
                    all_fields = await code_analyzer.get_all_fields(repository_id)
                    logger.info(f"代码分析服务正常工作，找到 {len(all_fields)} 个字段")
                except Exception as e:
                    logger.error(f"检查代码分析服务时出错: {str(e)}")
            except Exception as e:
                logger.error(f"创建代码分析服务失败: {str(e)}")
                # 即使创建失败也继续（不使用代码分析）
        
        # 使用智能体生成回答
        answer = await agent_manager.generate_answer(
            request.query, 
            request.use_code_analysis,
            code_analyzer,
            vector_store,
            repository_id,
            knowledge_base_id,
            request.prompt_configs
        )
        
        # 获取思考过程
        thinking_process = agent_manager.get_thinking_process()
        
        return {
            "answer": answer,
            "thinking_process": thinking_process
        }
    except Exception as e:
        logger.error(f"生成回答时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成回答失败: {str(e)}")

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
        repo_vector_store = get_vector_store(repository_id)
        repo_document_processor = DocumentProcessor(repo_vector_store)
        
        # 处理文档
        result = await repo_document_processor.process_document(
            temp_file_path, 
            repository_id,
            db,
            chunk_size,
            knowledge_base_id
        )
        
        # 返回结果，添加文件保存路径
        result["file_path"] = temp_file_path
        result["saved_as"] = os.path.basename(temp_file_path)
        
        return result
    except Exception as e:
        logger.error(f"处理上传文件时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理上传文件失败: {str(e)}")

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

# 主函数
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 