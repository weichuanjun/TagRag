# RAG Agent - 智能检索问答系统

基于AutoGen框架和向量数据库的智能检索问答系统，支持文档处理和代码分析。

## 功能特点

- **多格式文档处理**：支持TXT、Excel、PDF、CSV等格式
- **Excel转Markdown**：自动将Excel文件转换为Markdown格式存储
- **代码库分析**：识别代码库中的字段引用关系
- **多智能体协作**：基于AutoGen框架的多智能体协作系统
- **语义检索**：使用向量数据库进行高效语义检索
- **影响分析**：分析代码修改的影响范围

## 技术栈

### 后端

- Python 3.8+
- FastAPI
- LangChain
- AutoGen
- Chroma DB (向量数据库)
- OpenAI API

### 前端

- React
- Ant Design
- Axios
- React Router
- React Markdown

## 安装说明

### 前提条件

- Python 3.8+
- Node.js 14+
- OpenAI API密钥

### 安装步骤

1. 克隆代码库

```bash
git clone https://github.com/yourusername/rag-agent.git
cd rag-agent
```

2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

3. 安装前端依赖

```bash
cd ../frontend
npm install
```

4. 设置环境变量

```bash
# 后端目录下创建.env文件
OPENAI_API_KEY=your_openai_api_key
```

## 使用方法

1. 启动后端服务

```bash
cd backend
uvicorn main:app --reload
```

2. 启动前端开发服务器

```bash
cd ../frontend
npm start
```

3. 访问应用

浏览器打开 [http://localhost:3000](http://localhost:3000)

## 使用流程

1. **上传文档**：通过"上传文件"页面上传文档
2. **分析代码**：通过"代码分析"页面上传代码库
3. **问答交互**：在聊天界面输入问题，系统会基于上传的文档和代码库进行智能回答
4. **查看文档库**：通过"文档库"页面管理已上传的文档

## 架构设计

系统基于RAG (Retrieval Augmented Generation) 架构，包含以下核心组件：

1. **文档处理器**：负责处理不同格式的文档，并进行分块处理
2. **向量存储**：使用ChromaDB存储文档的向量表示
3. **代码分析器**：分析代码库中的字段引用关系
4. **多智能体系统**：基于AutoGen的多智能体协作系统，包含：
   - 用户代理
   - 检索代理
   - 分析代理
   - 代码分析代理
   - 回复生成代理

## 许可证

MIT License 