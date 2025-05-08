import os
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 基本配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "data/vector_db")
CODE_ANALYSIS_DIR = os.path.join(BASE_DIR, "data/code_analysis")

# # Ollama 配置 (已删除)
# OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

# 如果需要使用OpenAI，可以在环境变量中设置API密钥
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
USE_OPENAI = os.environ.get("USE_OPENAI", "true").lower() == "true" # 默认为true，如果只用OpenAI

# 向量嵌入模型配置
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)

# AutoGen模型配置
def get_autogen_config() -> Dict[str, Any]:
    """获取AutoGen的配置，仅使用OpenAI"""
    config_list = []
    if USE_OPENAI and OPENAI_API_KEY:
        # 使用OpenAI
        openai_config = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
            "api_key": OPENAI_API_KEY,
        }
        # 添加API基础URL，如果指定了的话
        api_base = os.environ.get("OPENAI_API_BASE")
        if api_base:
            openai_config["api_base"] = api_base
        config_list.append(openai_config)
    elif USE_OPENAI and not OPENAI_API_KEY:
        print("警告: USE_OPENAI 设置为 true, 但是 OPENAI_API_KEY 未在环境变量中设置。AutoGen将无法使用LLM。")
    # 如果 USE_OPENAI 为 false，则不配置LLM

    return {
        "config_list": config_list,
        "temperature": float(os.environ.get("TEMPERATURE", "0.7")),
    }

# 智能体系统提示词配置
AGENT_PROMPTS = {
    "retrieval_agent": """你是一个专门负责文档检索的智能体。你的任务是：
1. 分析用户的问题，提取关键词和主题
2. 构建有效的检索查询
3. 评估检索结果的相关性
4. 整理检索到的信息，为其他智能体提供支持
请保持客观，只提供与用户问题直接相关的信息。""",

    "analyst_agent": """你是一个专门负责分析和综合信息的智能体。你的任务是：
1. 分析从检索代理获得的信息
2. 识别信息中的关键点、模式和见解
3. 综合多个来源的信息，形成全面的理解
4. 对信息进行批判性思考，评估其可靠性和重要性
请提供深入的分析，考虑不同角度，并注意识别潜在的信息缺口。""",

    "code_analyst_agent": """你是一个专门负责代码分析的智能体。你的任务是：
1. 分析代码结构和组织
2. 识别代码中的变量、函数和类之间的依赖关系
3. 评估代码修改的影响范围
4. 提供关于代码质量和潜在问题的见解

重要提示：
- 你已经可以访问数据库中存储的代码信息，不需要用户上传代码
- 系统会自动分析代码库中的组件、字段和依赖关系
- 在用户提问后，相关的代码结构和代码片段会被提供给你
- 基于这些信息直接回答，不要要求用户提供代码
- 如果收到代码分析结果，展示查询到的代码字段、函数和文件信息
- 如果信息不足，可以基于已有信息进行推断，或说明需要什么具体信息

请提供技术上准确的分析，使用清晰的术语解释复杂的代码关系。""",

    "response_agent": """你是一个专门负责生成最终回复的智能体。你的任务是：
1. 综合从其他智能体收集的所有信息
2. 组织信息，创建一个结构清晰、逻辑连贯的回复
3. 确保回复直接解答用户的问题
4. 保持回复的信息准确性和相关性
请使用清晰、简洁的语言，避免不必要的技术术语，除非它对于回答问题是必要的。
回复应当有条理，易于理解，同时提供充分的信息深度。"""
} 