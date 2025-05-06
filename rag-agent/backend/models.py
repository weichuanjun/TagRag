from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey, DateTime, JSON, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
import datetime
import os

# 创建数据库目录
os.makedirs("data/db", exist_ok=True)

# 数据库URL
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/db/code_analysis.db")

# 创建引擎
engine = create_engine(DATABASE_URL)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 依赖函数，用于FastAPI的Depends
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

Base = declarative_base()

# 知识库模型
class KnowledgeBase(Base):
    """知识库模型，用于组织管理多个代码库和文档"""
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    # 关联关系
    repositories = relationship("CodeRepository", back_populates="knowledge_base", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")

# 代码仓库模型
class CodeRepository(Base):
    """代码仓库模型，表示一个需要被分析的代码库"""
    __tablename__ = "code_repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    path = Column(String, nullable=False)
    url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    last_analyzed = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.datetime.now)
    
    # 分析状态: pending, in_progress, completed, failed
    status = Column(String, default="pending")
    
    # 添加知识库外键
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    knowledge_base = relationship("KnowledgeBase", back_populates="repositories")
    
    # 关联关系
    files = relationship("CodeFile", back_populates="repository", cascade="all, delete-orphan")
    components = relationship("CodeComponent", back_populates="repository", cascade="all, delete-orphan")
    queries = relationship("UserQuery", back_populates="repository")

# 代码文件模型
class CodeFile(Base):
    """代码文件信息"""
    __tablename__ = 'files'
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey('code_repositories.id'))
    file_path = Column(String(255), nullable=False)
    language = Column(String(50))
    last_modified = Column(DateTime)
    hash = Column(String(64))  # 存储文件哈希值用于检测变更
    
    # 关系
    repository = relationship("CodeRepository", back_populates="files")
    components = relationship("CodeComponent", back_populates="file", cascade="all, delete-orphan")

# 代码组件模型（函数/类/方法）
class CodeComponent(Base):
    """代码组件信息(函数/类/方法)"""
    __tablename__ = 'components'
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey('code_repositories.id'))
    file_id = Column(Integer, ForeignKey('files.id'))
    name = Column(String(100), nullable=False)
    type = Column(String(20))  # function, class, method
    start_line = Column(Integer)
    end_line = Column(Integer)
    complexity = Column(Float, default=1.0)  # 代码复杂度
    signature = Column(String(500))  # 函数/方法签名
    
    # 存储组件代码
    code = Column(Text)
    
    # 附加信息
    component_metadata = Column(JSON)  # 存储参数、返回值等信息
    llm_summary = Column(Text)  # 大模型生成的摘要
    importance_score = Column(Float, default=0.0)  # 重要性评分
    
    # 关系
    repository = relationship("CodeRepository", back_populates="components")
    file = relationship("CodeFile", back_populates="components")
    dependencies = relationship("ComponentDependency", 
                               foreign_keys="ComponentDependency.source_id", 
                               back_populates="source")
    dependents = relationship("ComponentDependency", 
                             foreign_keys="ComponentDependency.target_id", 
                             back_populates="target")
    queries = relationship("UserQuery", secondary="component_queries")

# 组件依赖关系模型
class ComponentDependency(Base):
    """组件间依赖关系"""
    __tablename__ = 'dependencies'
    
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('components.id'))
    target_id = Column(Integer, ForeignKey('components.id'))
    dependency_type = Column(String(50))  # call, import, inheritance, etc.
    weight = Column(Float, default=1.0)  # 依赖强度
    
    # 关系
    source = relationship("CodeComponent", foreign_keys=[source_id], back_populates="dependencies")
    target = relationship("CodeComponent", foreign_keys=[target_id], back_populates="dependents")

# 用户查询历史模型
class UserQuery(Base):
    """用户查询历史"""
    __tablename__ = 'user_queries'
    
    id = Column(Integer, primary_key=True)
    query_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    repository_id = Column(Integer, ForeignKey('code_repositories.id'))
    result_summary = Column(Text)
    used_llm = Column(Boolean, default=False)
    
    # 关系
    repository = relationship("CodeRepository", back_populates="queries")

# 组件查询关联表
component_queries = Table(
    'component_queries', Base.metadata,
    Column('component_id', Integer, ForeignKey('components.id')),
    Column('query_id', Integer, ForeignKey('user_queries.id'))
)

# 文档模型
class Document(Base):
    """文档模型，表示一个上传的文档"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, nullable=False, index=True)
    source = Column(String, nullable=True)
    document_type = Column(String, nullable=True)
    chunks_count = Column(Integer, default=0)
    added_at = Column(DateTime, default=datetime.datetime.now)
    
    # 添加知识库外键
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    
    # 关联关系
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

# 文档块模型
class DocumentChunk(Base):
    """文档分块，用于向量检索"""
    __tablename__ = 'document_chunks'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'))
    chunk_index = Column(Integer)
    content = Column(Text)
    chunk_metadata = Column(JSON)
    
    # 关系
    document = relationship("Document", back_populates="chunks")

# Agent Prompt模型
class AgentPrompt(Base):
    """Agent提示词模型，用于不同知识库的不同Agent定制"""
    __tablename__ = 'agent_prompts'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    agent_type = Column(String, nullable=False, index=True)  # chat, code_analysis, document_qa 等
    prompt_template = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    
    # 添加知识库外键 (可为空表示通用模板)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    knowledge_base = relationship("KnowledgeBase")

# 创建数据库表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 如果直接运行此模块，创建数据库表
if __name__ == "__main__":
    create_tables()
    print("数据库表已创建。") 