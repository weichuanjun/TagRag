"""
重建数据库脚本，用于解决模型变更问题
"""
import os
import sys
from models import Base, engine, create_tables, KnowledgeBase

def rebuild_database():
    """删除并重建数据库"""
    # 数据库文件路径
    db_path = "data/db/code_analysis.db"
    
    print("开始重建数据库...")
    
    # 检查文件是否存在
    if os.path.exists(db_path):
        print(f"删除现有数据库文件: {db_path}")
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"删除数据库文件失败: {str(e)}")
            return False
    
    # 重新创建表
    print("创建新的数据库表...")
    Base.metadata.create_all(bind=engine)
    
    # 创建一个默认知识库
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        default_kb = KnowledgeBase(
            name="默认知识库",
            description="系统默认创建的知识库"
        )
        session.add(default_kb)
        session.commit()
        print(f"已创建默认知识库，ID: {default_kb.id}")
    
    print("数据库重建完成！")
    return True

if __name__ == "__main__":
    success = rebuild_database()
    sys.exit(0 if success else 1) 