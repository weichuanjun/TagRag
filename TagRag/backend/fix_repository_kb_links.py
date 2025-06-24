"""
修复代码库和知识库之间的关联
并确保代码检索使用正确的向量数据库路径
"""
import logging
import sys
import os
import asyncio
from sqlalchemy.orm import Session

# 将项目根目录添加到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入所需模块
from .models import get_db, CodeRepository, KnowledgeBase
from utils.vectorize_repo import vectorize_repository

async def fix_repositories():
    """修复代码库和知识库之间的关联，并重新向量化所有代码库"""
    db = next(get_db())
    
    try:
        # 获取所有代码库
        repositories = db.query(CodeRepository).all()
        logger.info(f"找到 {len(repositories)} 个代码库")
        
        # 获取默认知识库，如果没有则创建一个
        default_kb = db.query(KnowledgeBase).filter(KnowledgeBase.name == "默认知识库").first()
        if not default_kb:
            from datetime import datetime
            default_kb = KnowledgeBase(
                name="默认知识库",
                description="系统默认知识库",
                created_at=datetime.utcnow()
            )
            db.add(default_kb)
            db.flush()
            logger.info(f"创建默认知识库: ID={default_kb.id}")
        
        # 修复每个代码库
        for repo in repositories:
            # 确保每个代码库都有知识库关联
            if not repo.knowledge_base_id:
                repo.knowledge_base_id = default_kb.id
                logger.info(f"关联代码库 {repo.id} ({repo.name}) 到默认知识库 {default_kb.id}")
                db.commit()
            
            # 重新向量化代码库
            logger.info(f"开始重新向量化代码库: {repo.id} ({repo.name}), 知识库ID: {repo.knowledge_base_id}")
            await vectorize_repository(repo.id, repo.knowledge_base_id)
        
        logger.info("所有代码库修复完成")
        
    except Exception as e:
        logger.error(f"修复代码库时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    logger.info("开始修复代码库...")
    asyncio.run(fix_repositories())
    logger.info("修复完成") 