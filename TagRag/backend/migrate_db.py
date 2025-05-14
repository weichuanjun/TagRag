"""
数据库迁移脚本，用于更新表结构
"""
import logging
import sqlite3
import os
import sys

# 添加当前目录到路径，以便导入其他模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_vectorized_columns():
    """向code_repositories表添加vectorized和last_vectorized列"""
    try:
        # 获取数据库文件路径
        db_path = "data/db/tagrag.db"
        
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查vectorized列是否存在
        cursor.execute("PRAGMA table_info(code_repositories)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "vectorized" not in columns:
            logger.info("添加vectorized列到code_repositories表")
            cursor.execute("ALTER TABLE code_repositories ADD COLUMN vectorized BOOLEAN DEFAULT 0")
        else:
            logger.info("vectorized列已存在")
            
        if "last_vectorized" not in columns:
            logger.info("添加last_vectorized列到code_repositories表")
            cursor.execute("ALTER TABLE code_repositories ADD COLUMN last_vectorized TIMESTAMP")
        else:
            logger.info("last_vectorized列已存在")
            
        # 提交更改
        conn.commit()
        logger.info("数据库迁移完成")
            
    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}")
        raise e
    finally:
        # 关闭连接
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    logger.info("开始数据库迁移...")
    add_vectorized_columns()
    logger.info("数据库迁移完成") 