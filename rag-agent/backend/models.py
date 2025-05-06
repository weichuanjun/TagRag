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

# 代码仓库模型
class CodeRepository(Base):
    """代码仓库信息"""
    __tablename__ = 'repositories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    path = Column(String(255), nullable=False)
    last_analyzed = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # 关系
    files = relationship("CodeFile", back_populates="repository", cascade="all, delete-orphan")
    components = relationship("CodeComponent", back_populates="repository", cascade="all, delete-orphan")

# 代码文件模型
class CodeFile(Base):
    """代码文件信息"""
    __tablename__ = 'files'
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey('repositories.id'))
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
    repository_id = Column(Integer, ForeignKey('repositories.id'))
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
    repository_id = Column(Integer, ForeignKey('repositories.id'))
    result_summary = Column(Text)
    used_llm = Column(Boolean, default=False)

# 组件查询关联表
component_queries = Table(
    'component_queries', Base.metadata,
    Column('component_id', Integer, ForeignKey('components.id')),
    Column('query_id', Integer, ForeignKey('user_queries.id'))
)

# 创建数据库表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 如果直接运行此模块，创建数据库表
if __name__ == "__main__":
    create_tables()
    print("数据库表已创建。") 