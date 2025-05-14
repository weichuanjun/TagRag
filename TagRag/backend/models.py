from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey, DateTime, JSON, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
import datetime
import os
from sqlalchemy import event # For custom event listeners if needed later

# 创建数据库目录
os.makedirs("data/db", exist_ok=True)

# 数据库URL
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/db/tagrag.db")

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
    
    # 向量化状态
    vectorized = Column(Boolean, default=False)
    last_vectorized = Column(DateTime, nullable=True)
    
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

# 标签模型
class Tag(Base):
    """标签模型，用于对文档和代码进行分类"""
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True, unique=True) # Ensure tag names are unique
    color = Column(String, default="#1890ff")
    description = Column(String, nullable=True)
    tag_type = Column(String, default="general") 
    importance = Column(Float, default=0.5)
    related_content = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    
    # 添加标签层级类型，用于区分一级、二级、三级标签
    hierarchy_level = Column(String, default="leaf")  # root(根标签), branch(分支标签), leaf(叶标签)
    # 是否为固定/系统预设标签
    is_system = Column(Boolean, default=False)
    
    # 关系定义
    parent = relationship("Tag", remote_side=[id], back_populates="children")
    children = relationship("Tag", back_populates="parent", remote_side=[parent_id])
    
    # Relationships for TagDependency
    # Tags that this tag depends on (A depends on B, B is a dependency_of A)
    dependencies = relationship(
        "TagDependency", 
        foreign_keys="TagDependency.source_tag_id", 
        back_populates="source_tag",
        cascade="all, delete-orphan"
    )
    # Tags that depend on this tag (B is depended_on_by A, A is a dependent_on B)
    dependents = relationship(
        "TagDependency", 
        foreign_keys="TagDependency.target_tag_id", 
        back_populates="target_tag",
        cascade="all, delete-orphan"
    )

# New TagDependency model
class TagDependency(Base):
    __tablename__ = "tag_dependencies"
    id = Column(Integer, primary_key=True, index=True)
    # The tag that has a dependency
    source_tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)
    # The tag that is depended upon
    target_tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)
    # Type of dependency, e.g., "REQUIRES", "RELATES_TO", "PART_OF", "CONFLICTS_WITH"
    relationship_type = Column(String, nullable=False, default="RELATES_TO") 
    weight = Column(Float, default=0.5) # Strength or importance of the dependency
    description = Column(String, nullable=True) # Optional description of the dependency
    created_at = Column(DateTime, default=datetime.datetime.now)

    source_tag = relationship("Tag", foreign_keys=[source_tag_id], back_populates="dependencies")
    target_tag = relationship("Tag", foreign_keys=[target_tag_id], back_populates="dependents")

# 文档-标签关联表
document_tags = Table(
    'document_tags', Base.metadata,
    Column('document_id', Integer, ForeignKey('documents.id', ondelete="CASCADE")),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete="CASCADE"))
)

# 文档块-标签关联表 
document_chunk_tags = Table(
    'document_chunk_tags', Base.metadata,
    Column('chunk_id', Integer, ForeignKey('document_chunks.id', ondelete="CASCADE")),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete="CASCADE"))
)

# 文档模型
class Document(Base):
    """文档模型，表示一个上传的文档"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, nullable=False, index=True)
    source = Column(String, nullable=True) # Original filename or source identifier
    document_type = Column(String, nullable=True)
    chunks_count = Column(Integer, default=0)
    added_at = Column(DateTime, default=datetime.datetime.now)
    processed_at = Column(DateTime, nullable=True) # Time when processing finished or failed
    status = Column(String, default="pending") # e.g., pending, processing, processed, error_loading, error_processing, error_vector_store
    error_message = Column(Text, nullable=True) # Store error messages if processing fails
    
    # 添加知识库外键
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    
    # 添加代码库外键（可选）
    repository_id = Column(Integer, ForeignKey("code_repositories.id", ondelete="SET NULL"), nullable=True)
    
    # 关联关系
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=document_tags, backref="documents")

# 文档块模型
class DocumentChunk(Base):
    """文档块模型"""
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    content = Column(Text)
    chunk_index = Column(Integer)
    
    # Dedicated columns for T-CUS relevant fields
    token_count = Column(Integer, nullable=True)
    structural_type = Column(String(100), nullable=True) # Max length for structural type string
    
    chunk_metadata = Column(Text) # JSON format for other, less queried metadata
    page = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    summary = Column(Text, nullable=True)
    
    document = relationship("Document", back_populates="chunks")
    tags = relationship("Tag", secondary=document_chunk_tags, backref="chunks")

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

# 删除并重建数据库表 - 添加仅处理Documents表的功能
def rebuild_document_tables():
    """仅重建与Document相关的表，保留其他表"""
    # 删除Document相关表
    Document.__table__.drop(engine, checkfirst=True)
    DocumentChunk.__table__.drop(engine, checkfirst=True)
    
    # 重新创建表
    Document.__table__.create(engine)
    DocumentChunk.__table__.create(engine)
    
    print("文档相关表格已重建完成。")

# 如果直接运行此模块，创建数据库表
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rebuild_docs":
        rebuild_document_tables()
    else:
        create_tables()
        print("数据库表已创建。") 