import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import json

# 导入原有功能模块
from vector_store import VectorStore
from document_processor import DocumentProcessor
from agent_manager import AgentManager
from code_analyzer import CodeAnalyzer

# 导入新增的代码分析模块
from models import create_tables, get_db
from code_analysis_routes import router as code_analysis_router

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
vector_store = VectorStore()
document_processor = DocumentProcessor(vector_store)
code_analyzer_path = os.path.join(os.path.dirname(__file__), "data/code_analysis")
os.makedirs(code_analyzer_path, exist_ok=True)
code_analyzer = CodeAnalyzer(code_analyzer_path)
agent_manager = AgentManager(vector_store)

# 添加代码分析路由
app.include_router(code_analysis_router)

# 确保数据库和表已创建
create_tables()

# 问答请求模型
class QuestionRequest(BaseModel):
    query: str
    use_code_analysis: bool = False

# API端点
@app.get("/")
async def read_root():
    return {"message": "欢迎使用RAG Agent API"}

@app.post("/upload-document")
async def upload_document(file_path: str, chunk_size: int = 1000):
    """上传文档并处理"""
    try:
        result = await document_processor.process_document(file_path, chunk_size)
        return result
    except Exception as e:
        logger.error(f"处理文档时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理文档失败: {str(e)}")

@app.post("/upload-code")
async def upload_code(repo_path: str):
    """分析代码库"""
    try:
        result = await code_analyzer.analyze_code(repo_path)
        return result
    except Exception as e:
        logger.error(f"分析代码时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析代码失败: {str(e)}")

@app.get("/documents")
async def get_documents():
    """获取已处理的文档列表"""
    try:
        docs = await vector_store.get_document_list()
        return docs
    except Exception as e:
        logger.error(f"获取文档列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    """处理用户问题"""
    try:
        # 使用智能体生成回答
        answer = await agent_manager.generate_answer(
            request.query, 
            request.use_code_analysis,
            code_analyzer if request.use_code_analysis else None
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
async def get_code_fields():
    """获取代码字段列表"""
    try:
        fields = await code_analyzer.get_all_fields()
        return {"fields": fields}
    except Exception as e:
        logger.error(f"获取代码字段时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码字段失败: {str(e)}")

@app.get("/field-impact")
async def get_field_impact(field_name: str):
    """获取字段影响"""
    try:
        impact = await code_analyzer.get_field_impact(field_name)
        return {"impact": impact}
    except Exception as e:
        logger.error(f"获取字段影响时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取字段影响失败: {str(e)}")

# 中间件用于请求日志
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"请求: {request.method} {request.url}")
    response = await call_next(request)
    return response

# 主函数
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 