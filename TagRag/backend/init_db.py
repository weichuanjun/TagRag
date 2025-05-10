"""
数据库初始化脚本，用于创建表结构和初始化数据
"""
import logging
import os
import sys
from datetime import datetime

# 添加当前目录到路径，以便导入其他模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入模型和数据库连接
from models import Base, engine, KnowledgeBase, Document, Tag, CodeRepository, get_db
from sqlalchemy.orm import Session

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_database():
    """初始化数据库、创建表并添加初始数据"""
    try:
        # 创建所有表
        logger.info("创建数据库表...")
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建完成")
        
        # 获取数据库会话
        db = next(get_db())
        
        # 初始化知识库
        init_knowledge_bases(db)
        
        # 提交事务
        db.commit()
        logger.info("数据库初始化完成")
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        raise e

def init_knowledge_bases(db: Session):
    """初始化知识库记录"""
    # 检查是否已存在知识库
    existing_kb = db.query(KnowledgeBase).first()
    if existing_kb:
        logger.info(f"已存在知识库，跳过初始化")
        return
    
    # 创建默认知识库
    default_kb = KnowledgeBase(
        name="默认知识库",
        description="系统默认知识库",
        created_at=datetime.utcnow()
    )
    db.add(default_kb)
    db.flush()
    
    logger.info(f"创建默认知识库, ID={default_kb.id}")

if __name__ == "__main__":
    logger.info("开始初始化数据库...")
    init_database()
    logger.info("数据库初始化完成") 