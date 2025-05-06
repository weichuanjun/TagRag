import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
import aiofiles
import time
import json
from pydantic import BaseModel

# 设置tokenizers环境变量，避免警告
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from document_processor import DocumentProcessor
from vector_store import VectorStore
from agent_manager import AgentManager
from code_analyzer import CodeAnalyzer

# 导入配置
from config import UPLOADS_DIR, VECTOR_DB_DIR, CODE_ANALYSIS_DIR

# 初始化应用
app = FastAPI(title="RAG Agent API", description="基于AutoGen的智能检索问答系统")

# 允许CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该设置具体的源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保上传目录存在
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)
os.makedirs(CODE_ANALYSIS_DIR, exist_ok=True)

# 挂载静态文件
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# 初始化处理器
document_processor = DocumentProcessor()
vector_store = VectorStore()
agent_manager = AgentManager(vector_store)
code_analyzer = CodeAnalyzer(CODE_ANALYSIS_DIR)

# 模型类
class Question(BaseModel):
    query: str
    use_code_analysis: bool = False

class CodeUpload(BaseModel):
    repo_url: Optional[str] = None
    local_path: Optional[str] = None

# 路由
@app.get("/")
async def root():
    return {"message": "RAG Agent API 正在运行"}

@app.post("/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    try:
        # 生成唯一文件名
        timestamp = int(time.time())
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{timestamp}{file_extension}"
        file_path = os.path.join(UPLOADS_DIR, unique_filename)
        
        # 保存上传文件
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
        
        # 在后台处理文档
        if background_tasks:
            background_tasks.add_task(
                document_processor.process_file,
                file_path, 
                vector_store
            )
        
        return {
            "filename": file.filename,
            "saved_as": unique_filename,
            "status": "正在处理文档，请稍候",
            "file_path": file_path
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload/code")
async def upload_code(code_upload: CodeUpload, background_tasks: BackgroundTasks):
    try:
        if code_upload.repo_url:
            # 如果提供了Git仓库URL，克隆仓库
            repo_path = os.path.join(CODE_ANALYSIS_DIR, f"repo_{int(time.time())}")
            os.system(f"git clone {code_upload.repo_url} {repo_path}")
            code_path = repo_path
        elif code_upload.local_path:
            # 如果提供了本地路径，使用它
            code_path = code_upload.local_path
        else:
            raise HTTPException(status_code=400, detail="必须提供repo_url或local_path")
        
        # 在后台分析代码
        background_tasks.add_task(
            code_analyzer.analyze_code,
            code_path
        )
        
        return {
            "status": "正在分析代码，请稍候",
            "code_path": code_path
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def ask_question(question: Question):
    try:
        # 使用多智能体系统回答问题
        answer = await agent_manager.generate_answer(
            question.query,
            use_code_analysis=question.use_code_analysis,
            code_analyzer=code_analyzer if question.use_code_analysis else None
        )
        
        # 获取思考过程
        thinking_process = agent_manager.get_thinking_process()
        
        return {
            "query": question.query,
            "answer": answer,
            "thinking_process": thinking_process
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents")
async def list_documents():
    """获取已处理的文档列表"""
    try:
        doc_list = await vector_store.get_document_list()
        return {
            "documents": doc_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加删除文档的功能
@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """删除文档"""
    try:
        # 从元数据中删除
        if document_id in vector_store.document_metadata["documents"]:
            del vector_store.document_metadata["documents"][document_id]
            vector_store._save_metadata()
            
            # 实际情况下可能还需要从向量数据库中删除相关向量
            # 这里简化处理，假设下次重建集合
            
            return {"status": "success", "message": f"文档 {document_id} 已删除"}
        else:
            raise HTTPException(status_code=404, detail=f"文档 {document_id} 不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加获取思考过程的端点
@app.get("/thinking-process")
async def get_thinking_process():
    """获取最后一次智能体思考过程"""
    try:
        thinking_process = agent_manager.get_thinking_process()
        return {
            "thinking_process": thinking_process
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 