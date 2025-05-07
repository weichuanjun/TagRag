"""
数据库重建脚本

用于重新创建所有数据库表，清除旧数据
"""

import os
import shutil
import logging
from models import create_tables

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def rebuild_database():
    """重建数据库"""
    try:
        # 确保目录存在
        os.makedirs("data/db", exist_ok=True)
        os.makedirs("data/vector_db", exist_ok=True)
        
        # 数据库文件路径
        db_path = "data/db/code_analysis.db"
        
        # 删除现有数据库文件
        if os.path.exists(db_path):
            os.remove(db_path)
            logger.info(f"已删除旧数据库文件: {db_path}")
        
        # 清除向量存储
        vector_db_dir = "data/vector_db"
        if os.path.exists(vector_db_dir) and os.path.isdir(vector_db_dir):
            # 不删除目录本身，只删除内容
            for item in os.listdir(vector_db_dir):
                item_path = os.path.join(vector_db_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
            logger.info(f"已清除向量存储目录内容: {vector_db_dir}")
        
        # 创建新数据库表
        create_tables()
        logger.info("已重新创建所有数据库表")
        
        # 创建默认知识库
        create_default_knowledge_base()
        
        # 创建默认Agent Prompt
        create_default_prompts()
        
        return True
    except Exception as e:
        logger.error(f"重建数据库时出错: {str(e)}")
        return False

def create_default_knowledge_base():
    """创建默认知识库"""
    try:
        from sqlalchemy.orm import Session
        from models import KnowledgeBase, SessionLocal
        
        # 创建会话
        db = SessionLocal()
        
        # 检查是否已有知识库
        existing = db.query(KnowledgeBase).first()
        if not existing:
            # 创建默认知识库
            default_kb = KnowledgeBase(
                name="默认知识库",
                description="系统自动创建的默认知识库"
            )
            db.add(default_kb)
            db.commit()
            logger.info(f"已创建默认知识库: {default_kb.name}")
        else:
            logger.info("已存在知识库，跳过创建默认知识库")
    except Exception as e:
        logger.error(f"创建默认知识库时出错: {str(e)}")
    finally:
        # 关闭会话
        db.close()

def create_default_prompts():
    """创建默认的Agent提示词"""
    try:
        from sqlalchemy.orm import Session
        from models import AgentPrompt, SessionLocal
        
        # 创建会话
        db = SessionLocal()
        
        # 定义默认提示词
        default_prompts = [
            {
                "name": "默认检索代理",
                "description": "用于从知识库检索相关信息的代理",
                "agent_type": "retrieval_agent",
                "is_default": True,
                "prompt_template": "你是一个专门负责文档检索的智能体。你的任务是基于用户的问题，确定需要从知识库中检索哪些信息，并提供详细的检索结果。请注意提供完整的上下文，并确保信息来源的准确性。"
            },
            {
                "name": "默认分析代理",
                "description": "用于分析信息并综合答案的代理",
                "agent_type": "analyst_agent",
                "is_default": True,
                "prompt_template": "你是一个专门负责分析和综合信息的智能体。你的任务是根据提供的检索结果，分析信息并生成一个全面、准确的答案。请确保你的回答逻辑清晰，考虑所有相关信息，并在必要时承认信息的局限性。"
            },
            {
                "name": "默认响应代理",
                "description": "用于生成最终用户回答的代理",
                "agent_type": "response_agent",
                "is_default": True,
                "prompt_template": "你是一个专门负责生成最终回答的智能体。你的目标是基于已有的分析结果，生成一个清晰、准确且对用户友好的回答。确保你的回答语言自然、条理清晰，并加入适当的引用来源。避免使用过于技术性的语言，除非用户问题本身是技术性的。"
            },
            {
                "name": "默认代码分析代理",
                "description": "用于分析代码的代理",
                "agent_type": "code_agent",
                "is_default": True,
                "prompt_template": "你是一个专门负责代码分析的智能体。你的任务是分析提供的代码片段、函数调用关系或系统架构，并提供清晰的技术解释。你应该理解代码的功能、结构和潜在问题。在回答中，请考虑代码质量、性能影响和最佳实践。"
            }
        ]
        
        # 检查并添加默认提示词
        for prompt_data in default_prompts:
            # 检查是否已存在相同类型的默认提示词
            existing = db.query(AgentPrompt).filter(
                AgentPrompt.agent_type == prompt_data["agent_type"],
                AgentPrompt.is_default == True,
                AgentPrompt.knowledge_base_id == None  # 全局默认提示词
            ).first()
            
            if not existing:
                # 创建新提示词
                prompt = AgentPrompt(**prompt_data)
                db.add(prompt)
        
        # 提交事务
        db.commit()
        logger.info("已创建默认Agent提示词")
    except Exception as e:
        logger.error(f"创建默认提示词时出错: {str(e)}")
    finally:
        # 关闭会话
        db.close()

if __name__ == "__main__":
    logger.info("开始重建数据库...")
    success = rebuild_database()
    if success:
        logger.info("数据库重建成功!")
    else:
        logger.error("数据库重建失败!") 