import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import json
import shutil

# 导入原有功能模块
from vector_store import VectorStore
from document_processor import DocumentProcessor
from agent_manager import AgentManager
from models import create_tables, get_db, CodeRepository, KnowledgeBase

# 导入新增的代码分析模块
from code_analysis_routes import router as code_analysis_router
# 导入知识库管理模块
from knowledge_base_routes import router as knowledge_base_router

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

# 确保数据库和表已创建
create_tables()

# 问答请求模型
class QuestionRequest(BaseModel):
    query: str
    knowledge_base_id: Optional[int] = None
    use_code_analysis: bool = False

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
    return {"message": "欢迎使用RAG Agent API"}

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
            knowledge_base_id
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

# 主函数
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 