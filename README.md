# RAG Agent 智能检索问答系统

基于AutoGen的多智能体RAG（检索增强生成）系统，支持文档上传、代码分析和智能问答。

## 功能特点

- **多格式文档处理**：支持Markdown、Excel等多种格式文件上传和处理
- **智能文档检索**：使用向量数据库存储文档内容，支持语义化检索
- **代码库分析**：支持分析代码库，理解代码结构和依赖关系
- **多智能体协作**：基于AutoGen的多智能体系统，协同工作生成更全面的回答
- **可视化思考过程**：展示AI的思考过程，提高透明度

## 技术栈

### 后端
- FastAPI
- LangChain
- PyAutoGen
- ChromaDB (向量数据库)
- OpenAI API (或本地Ollama模型)

### 前端
- React
- Ant Design
- Axios

## 安装指南

### 后端设置

1. 进入后端目录：
```bash
cd rag-agent/backend
```

2. 创建并激活虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 创建.env文件，配置环境变量：
```
# OpenAI配置
USE_OPENAI=true
OPENAI_API_KEY=你的OpenAI API密钥
OPENAI_MODEL=gpt-3.5-turbo

# 或使用Ollama (本地模型)
# USE_OPENAI=false
# OLLAMA_HOST=http://localhost:11434
# OLLAMA_MODEL=llama3.1:8b

# 嵌入模型配置
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# 温度设置
TEMPERATURE=0.7
```

5. 启动后端服务：
```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 前端设置

1. 进入前端目录：
```bash
cd rag-agent/frontend
```

2. 安装依赖：
```bash
npm install
```

3. 启动前端服务：
```bash
npm start
```

## 使用说明

1. 访问 http://localhost:3000 打开应用
2. 上传文档或代码库
3. 在聊天界面提问，获取基于上传内容的智能回答
