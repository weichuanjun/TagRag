"""
配置文件
"""
import os
from typing import Dict, Any
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_DIR = os.path.join(DATA_DIR, "db")
VECTOR_DB_DIR = os.path.join(DATA_DIR, "vector_db")

# 确保目录存在
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

# 数据库URL
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(DB_DIR, 'code_analysis.db')}")

# OpenAI配置
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    print("警告: 未设置OPENAI_API_KEY环境变量")

# LLM模型设置
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")

# AutoGen配置
def get_autogen_config() -> Dict[str, Any]:
    """获取AutoGen配置"""
    return {
        "config_list": [
            {
                "model": LLM_MODEL,
                "api_key": OPENAI_API_KEY,
            }
        ],
        "temperature": 0.2,
        "request_timeout": 120
    }

# 默认Agent提示词
AGENT_PROMPTS = {
    "retrieval_agent": """你是一个专门负责文档检索的智能体。你的任务是基于用户的问题，确定需要从知识库中检索哪些信息，并提供详细的检索结果。请注意提供完整的上下文，并确保信息来源的准确性。""",
    
    "analyst_agent": """你是一个专门负责分析和综合信息的智能体。你的任务是根据提供的检索结果，分析信息并生成一个全面、准确的答案。请确保你的回答逻辑清晰，考虑所有相关信息，并在必要时承认信息的局限性。""",
    
    "response_agent": """你是一个专门负责生成最终回答的智能体。你的目标是基于已有的分析结果，生成一个清晰、准确且对用户友好的回答。确保你的回答语言自然、条理清晰，并加入适当的引用来源。避免使用过于技术性的语言，除非用户问题本身是技术性的。""",
    
    "code_agent": """你是一个专门负责代码分析的智能体。你的任务是分析提供的代码片段、函数调用关系或系统架构，并提供清晰的技术解释。你应该理解代码的功能、结构和潜在问题。在回答中，请考虑代码质量、性能影响和最佳实践。"""
}

# 文档处理设置
DEFAULT_CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))
MAX_THREADS = int(os.environ.get("MAX_THREADS", "4")) 