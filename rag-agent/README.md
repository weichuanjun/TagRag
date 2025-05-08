# RAG-Agent 知识检索与智能问答系统

RAG-Agent是一个结合了检索增强生成(RAG)和多智能体(Multi-Agent)的知识管理与智能问答系统。系统支持多种文档格式的上传、知识库管理、图形化知识浏览和智能问答。

## 主要功能

- **文档管理**：支持多种格式文档(PDF, DOCX, TXT, CSV, Excel等)的上传和管理
- **知识库管理**：创建多个知识库，进行分类组织
- **智能问答**：基于AutoGen框架的多智能体系统，提供精准问答
- **代码分析**：支持代码库的上传与分析
- **知识图谱**：以图形化方式展示知识点之间的关联
- **提示词管理**：自定义不同Agent的提示词，调整智能体行为

## 系统架构

### 后端
- FastAPI框架
- SQLite数据库存储结构化数据
- Chroma向量数据库存储嵌入向量
- NetworkX图库实现知识图谱
- LangChain处理文档和检索
- AutoGen实现多智能体协作

### 前端
- React框架
- Ant Design UI组件库
- D3/Force Graph实现图形可视化

## 安装指南

### 环境要求
- Python 3.9+
- Node.js 16+
- npm 8+

### 后端安装

1. 克隆仓库
   ```bash
   git clone https://github.com/yourusername/rag-agent.git
   cd rag-agent
   ```

2. 创建并激活虚拟环境
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate  # Windows
   ```

3. 安装依赖
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. 初始化数据库
   ```bash
   python rebuild_db.py
   ```

5. 启动后端服务
   ```bash
   python main.py
   ```
   服务将在 http://localhost:8000 运行

### 前端安装

1. 安装依赖
   ```bash
   cd ../frontend
   npm install
   ```

2. 启动前端服务
   ```bash
   npm start
   ```
   前端将在 http://localhost:3000 运行

## 使用指南

### 创建知识库

1. 从侧边栏导航到"知识库管理"
2. 点击"创建知识库"按钮
3. 输入知识库名称和描述，点击确认

### 上传文档

1. 从侧边栏导航到"文档上传"
2. 选择目标知识库
3. 拖拽文件或点击上传区域选择文件
4. 等待文档处理完成

### 智能问答

1. 从侧边栏导航到"智能问答"
2. 选择要查询的知识库
3. 在输入框中输入问题
4. 等待系统生成回答

### 查看知识图谱

1. 从侧边栏导航到"知识图谱可视化"
2. 选择知识库
3. 浏览图形化的知识关联
4. 使用搜索功能查找特定实体

### 自定义Agent提示词

1. 从侧边栏导航到"Agent提示词管理"
2. 点击"创建提示词"按钮
3. 选择Agent类型，输入名称、描述和提示词模板
4. 可选择是否设为默认

## 许可证

MIT License 