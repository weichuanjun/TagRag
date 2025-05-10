import os
import json
import autogen
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
import asyncio
import logging
import math
import datetime

# 导入VectorStore 和数据库模型
from vector_store import VectorStore
from models import Tag as TagModel, get_db
from models import Tag as DBTag # Ensure DBTag is imported
from sqlalchemy.orm import Session # Ensure Session is imported for type hinting if needed

# 导入配置文件和新的服务
from config import (
    get_autogen_config,
    AGENT_PROMPTS,
    TAG_FILTER_RETRIEVAL_K,
    CONTEXT_TOKEN_LIMIT,
    T_CUS_EMBEDDING_MODEL # Needed for embedding instance in TagRAG
)
from scoring_service import calculate_t_cus_score, greedy_token_constrained_selection, TagGraphAccessor
from tag_routes import LLMClient
from langchain_community.embeddings import HuggingFaceEmbeddings # Moved import up

# --- Pydantic Models for API Response ---
class ReferencedTagInfo(BaseModel):
    id: int
    name: str
    tag_type: Optional[str] = None # 从 generated_tags_tq 获取

class ReferencedExcerptInfo(BaseModel):
    document_id: Optional[int] = None
    document_source: Optional[str] = None # 从块元数据获取 'source'
    chunk_id: Optional[str] = None # 例如 f"{document_id}_{chunk_index}"
    content: str
    page_number: Optional[int] = None # 从块元数据获取
    score: Optional[float] = None # T-CUS score (如果可用)
    # token_count: Optional[int] = None # 从块元数据获取 (如果需要)
    # chunk_index: Optional[int] = None # 从块元数据获取 (如果需要构建 chunk_id)

# 添加代码片段信息类
class CodeSnippetInfo(BaseModel):
    component_id: Optional[int] = None
    file_path: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    code: str
    signature: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    score: Optional[float] = None
    repository_id: Optional[int] = None

class TagRAGChatResponse(BaseModel):
    answer: str
    thinking_process: List[Dict[str, Any]]
    referenced_tags: List[ReferencedTagInfo]
    referenced_excerpts: List[ReferencedExcerptInfo]
    code_snippets: List[CodeSnippetInfo] = [] # 添加代码片段字段
    user_query: str # 回传用户原始查询
    knowledge_base_id: Optional[int] = None # 回传知识库ID
# --- End Pydantic Models ---

logger = logging.getLogger(__name__)

class AgentManager:
    """AutoGen智能体管理器，负责协调多个智能体生成回答"""
    
    def __init__(self, vector_store: VectorStore, db_session_factory=get_db, db: Optional[Session] = None):
        self.vector_store = vector_store
        self.db_session_factory = db_session_factory
        self.db = db # Store db session
        
        # 配置路径
        os.makedirs("data/agent_configs", exist_ok=True)
        
        # 从配置文件获取LLM模型设置
        self.llm_config = get_autogen_config()
        
        # 添加最大轮次限制，防止无限循环
        self.max_consecutive_auto_reply = 2
        
        # 初始化智能体
        self._init_agents()
        
        # 存储思考过程
        self.thinking_process = []
        self.llm_client = LLMClient()
        try:
            self.embedding_instance = HuggingFaceEmbeddings(model_name=T_CUS_EMBEDDING_MODEL)
        except Exception as e:
             logger.error(f"Failed to initialize default embedding model {T_CUS_EMBEDDING_MODEL}: {e}")
             self.embedding_instance = None # Handle potential init failure
    
    def log_thinking_process(self, step_info: str, agent_name: str, level: str = "INFO", status: Optional[str] = None, **kwargs):
        """Helper method to log steps in the thinking process."""
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "agent": agent_name,
            "step_info": step_info,
            "level": level,
            **kwargs
        }
        if status:
            log_entry["status"] = status
        
        self.thinking_process.append(log_entry)
        # Also log to standard logger for real-time visibility if needed
        logger.log(getattr(logging, level.upper(), logging.INFO), f"ThinkingProcess - {agent_name}: {step_info}")
    
    def _init_agents(self, use_code_analysis=False, prompt_configs=None):
        """初始化智能体"""
        # 用户代理（代表用户发起请求）
        self.user_proxy = autogen.UserProxyAgent(
            name="用户代理",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
            code_execution_config=False,
            max_consecutive_auto_reply=self.max_consecutive_auto_reply,
        )
        
        # 智能体配置
        def get_agent_config(name, system_message, config=None, llm_config=None):
            """获取智能体配置"""
            return {
                "name": name,
                "system_message": system_message,
                "human_input_mode": "NEVER",
                "max_consecutive_auto_reply": self.max_consecutive_auto_reply,
                "llm_config": llm_config or self.llm_config,
                **(config or {})
            }

        # 创建智能体
        retrieval_system = AGENT_PROMPTS.get("retrieval_agent", "Retrieval agent prompt missing.")
        if prompt_configs and "retrieval_agent" in prompt_configs:
            retrieval_system = prompt_configs["retrieval_agent"]
        self.retrieval_agent = autogen.AssistantAgent(
            **get_agent_config("retrieval_agent", retrieval_system)
        )
        
        analyst_system = AGENT_PROMPTS.get("analyst_agent", "Analyst agent prompt missing.")
        if prompt_configs and "analyst_agent" in prompt_configs:
            analyst_system = prompt_configs["analyst_agent"]
        self.analyst_agent = autogen.AssistantAgent(
            **get_agent_config("analyst_agent", analyst_system)
        )
        
        # 如果开启了代码分析
        code_analyst_system = AGENT_PROMPTS.get("code_analyst_agent", "Code analyst agent prompt missing.")
        if prompt_configs and "code_analyst_agent" in prompt_configs:
            code_analyst_system = prompt_configs["code_analyst_agent"]
        self.code_analyst_agent = autogen.AssistantAgent(
            **get_agent_config("code_analyst_agent", code_analyst_system)
        )
        
        response_system = AGENT_PROMPTS.get("response_agent", "Response agent prompt missing.")
        if prompt_configs and "response_agent" in prompt_configs:
            response_system = prompt_configs["response_agent"]
        self.final_answer_agent = autogen.AssistantAgent(
            **get_agent_config("TagRAG_AnswerAgent", response_system)
        )
    
    def _extract_chat_history(self):
        """从所有代理的聊天记录中提取思考过程"""
        self.thinking_process = []
        
        all_agents = [self.retrieval_agent, self.analyst_agent, self.code_analyst_agent, self.final_answer_agent]
        
        for agent in all_agents:
            if hasattr(agent, 'chat_messages') and self.user_proxy in agent.chat_messages:
                for message_list in agent.chat_messages[self.user_proxy]:
                    for message in message_list if isinstance(message_list, list) else [message_list]:
                        if isinstance(message, dict):
                            self.thinking_process.append({
                                "sender": agent.name,
                                "recipient": self.user_proxy.name,
                                "content": message.get("content", ""),
                                "timestamp": asyncio.get_event_loop().time()
                            })
            
            if hasattr(self.user_proxy, 'chat_messages') and agent in self.user_proxy.chat_messages:
                 for message_list in self.user_proxy.chat_messages[agent]:
                    for message in message_list if isinstance(message_list, list) else [message_list]:
                        if isinstance(message, dict):
                            self.thinking_process.append({
                                "sender": self.user_proxy.name,
                                "recipient": agent.name,
                                "content": message.get("content", ""),
                                "timestamp": asyncio.get_event_loop().time()
                            })
        
        return self.thinking_process
    
    def get_thinking_process(self):
        """获取智能体思考过程"""
        return self.thinking_process
    
    def clear_thinking_process(self):
        """清空思考过程"""
        self.thinking_process = []
        self.user_proxy.reset()
        agents_to_reset = [self.retrieval_agent, self.analyst_agent, self.code_analyst_agent, self.final_answer_agent]
        for agent in agents_to_reset:
            if agent: agent.reset()
    
    async def _get_query_tags_tq(self, user_query: str, knowledge_base_id: Optional[int] = None) -> List[Dict[str, Any]]:
        self.log_thinking_process("开始生成查询标签 T(q)", "QueryTagGeneratorAgent", user_query=user_query)
        
        # Step 1: Get existing system tags (T(system))
        system_tags_str = "无可用系统标签"
        system_tag_names_for_prompt = [] # Store just names for the prompt

        if self.db:
            try:
                all_db_tags = self.db.query(DBTag.name).all() # Query only names
                if all_db_tags:
                    system_tag_names_for_prompt = [tag_name for (tag_name,) in all_db_tags]
                    if system_tag_names_for_prompt:
                        system_tags_str = "\\\\n- " + "\\\\n- ".join(system_tag_names_for_prompt)
                        self.log_thinking_process(f"Found {len(system_tag_names_for_prompt)} system tags to consider for T(q) prompt.", "QueryTagGeneratorAgent", system_tags_count=len(system_tag_names_for_prompt))
                    else:
                        self.log_thinking_process("No system tag names found in DB for T(q) prompt.", "QueryTagGeneratorAgent")
                else:
                    self.log_thinking_process("DB query for tags returned no results for T(q) prompt.", "QueryTagGeneratorAgent")

            except Exception as e_db_tags:
                self.log_thinking_process(f"Error fetching system tags for T(q) prompt: {e_db_tags}", "QueryTagGeneratorAgent", level="ERROR", error_details=str(e_db_tags))
        else:
            self.log_thinking_process("DB session not available, cannot fetch system tags for T(q) prompt.", "QueryTagGeneratorAgent", level="WARNING")

        prompt_template_tq = ("""用户查询: \"{user_query}\"

基于以下【可用系统标签参考列表】，请仔细分析用户查询的核心意图和潜在上下文。你的目标是生成一系列最相关的标签，这些标签应具备以下特点：
1.  **全面性与大局观**: 从不同维度和层级思考，确保标签能捕捉用户查询的多个方面，并反映其核心概念及可能的上下文关联。如果查询涉及多个主题，请为各主要方面提供标签。
2.  **高质量与精准性**: 每个标签都应具有高信息量，力求精准。
3.  **优先与创新并存**:
    *   如果【可用系统标签参考列表】中有与查询意图高度匹配的标签，请优先使用它们。
    *   即使存在部分相似的已有标签，如果你认为有更精确、更全面或更能体现大局观的新标签能够描述查询意图，请大胆生成新标签。我们鼓励生成能提升后续检索效果和知识关联性的新标签。
4.  **数量适宜**: 生成的标签数量不必过多，但要确保关键概念得到覆盖。通常建议3-7个标签。
5.  **相关性**: 所有标签必须与用户查询内容紧密相关。

请以JSON字符串列表的格式返回结果。例如：[\"选择的标签A\", \"新生成的标签B\", \"另一个层面的标签C\"]。

【可用系统标签参考列表】:
{system_tags_str}

请仅返回有效的JSON字符串列表。
""")
        prompt = prompt_template_tq.format(user_query=user_query, system_tags_str=system_tags_str)
        
        if not self.llm_client:
            self.log_thinking_process("LLMClient not initialized.", "QueryTagGeneratorAgent", level="ERROR")
            return []
            
        llm_response_str = await self.llm_client.generate(prompt)
        self.log_thinking_process(f"LLM原始返回: '{llm_response_str[:100]}...'", "QueryTagGeneratorAgent")

        generated_tags_tq: List[Dict[str, Any]] = [] # Final list of {'id': int, 'name': str, 'tag_type': str}
        tag_names_from_llm: List[str] = []

        if llm_response_str:
            try:
                cleaned_response = llm_response_str.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[len("```json"):].strip()
                elif cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[len("```"):].strip()
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-len("```"):].strip()
                
                parsed_llm_output = json.loads(cleaned_response)
                
                if isinstance(parsed_llm_output, list) and all(isinstance(tag_name, str) for tag_name in parsed_llm_output):
                    tag_names_from_llm = parsed_llm_output
                elif isinstance(parsed_llm_output, dict) and "tags" in parsed_llm_output and isinstance(parsed_llm_output["tags"], list):
                    tag_names_from_llm = parsed_llm_output["tags"]
                else:
                    self.log_thinking_process(f"LLM T(q) response format unexpected: {parsed_llm_output}", "QueryTagGeneratorAgent", level="WARNING")

                if tag_names_from_llm and self.db:
                    for tag_name_raw in tag_names_from_llm:
                        tag_name = tag_name_raw.strip()
                        if not tag_name: continue

                        tag_orm_instance = self.db.query(DBTag).filter(DBTag.name.ilike(tag_name)).first()
                        tag_type_for_response = "existing_system_tag"
                        if not tag_orm_instance:
                            # Create new tag if it doesn't exist
                            self.log_thinking_process(f"T(q)中出现新标签 '{tag_name}'，将为其创建记录。", "QueryTagGeneratorAgent", new_tag_name=tag_name)
                            tag_orm_instance = DBTag(
                                name=tag_name, 
                                description=f"LLM为查询 '{user_query[:50]}...' 生成的标签", 
                                tag_type="llm_query_generated" # Specific type for LLM generated for a query
                            )
                            try:
                                self.db.add(tag_orm_instance)
                                self.db.commit()
                                self.db.refresh(tag_orm_instance)
                                self.log_thinking_process(f"T(q)中识别到新创标签: '{tag_orm_instance.name}' (ID: {tag_orm_instance.id})", "QueryTagGeneratorAgent")
                                tag_type_for_response = "newly_created_for_query"
                            except Exception as e_create_tag:
                                self.log_thinking_process(f"为T(q)创建新标签 '{tag_name}' 失败: {e_create_tag}", "QueryTagGeneratorAgent", level="ERROR")
                                self.db.rollback()
                                continue # Skip this tag if creation failed
                        else:
                            tag_type_for_response = tag_orm_instance.tag_type or "existing_system_tag" # Use existing type if available
                            self.log_thinking_process(f"T(q)中识别到已存在系统标签: '{tag_orm_instance.name}' (ID: {tag_orm_instance.id})", "QueryTagGeneratorAgent")
                        
                        generated_tags_tq.append({
                            "id": tag_orm_instance.id, 
                            "name": tag_orm_instance.name,
                            "tag_type": tag_type_for_response 
                        })
            except json.JSONDecodeError:
                self.log_thinking_process(f"LLM T(q) response is not valid JSON", "QueryTagGeneratorAgent", level="ERROR")
            except Exception as e_parse:
                 self.log_thinking_process(f"解析或处理LLM T(q)响应时出错: {e_parse}", "QueryTagGeneratorAgent", level="ERROR")
        else:
            self.log_thinking_process("LLM T(q) response was empty.", "QueryTagGeneratorAgent", level="WARNING")

        self.log_thinking_process(f"完成T(q)生成。共生成 {len(generated_tags_tq)} 个标签。", "QueryTagGeneratorAgent", status="Completed")
        return generated_tags_tq

    async def generate_answer_tag_rag(
        self, 
        user_query: str,
        vector_store_for_query: VectorStore,
        knowledge_base_id: Optional[int] = None,
        prompt_configs: Optional[Dict[str, str]] = None,
        use_code_retrieval: bool = False, # 新增参数控制是否启用代码检索
        repository_id: Optional[int] = None # 新增参数指定代码库
    ) -> TagRAGChatResponse:
        """生成对用户问题的回答并使用TagRAG框架"""
        self.clear_thinking_process()
        self.log_thinking_process("TagRAG流程开始", "SystemCoordinator", user_query=user_query, kb_id=knowledge_base_id)

        final_referenced_tags_info: List[ReferencedTagInfo] = []
        final_referenced_excerpts_info: List[ReferencedExcerptInfo] = []
        final_answer = "抱歉，我无法处理您的请求。"
        generated_tags_tq_list_of_dicts: List[Dict[str, Any]] = []
        code_snippets: List[CodeSnippetInfo] = [] # 添加代码片段收集

        tag_graph_accessor = None
        original_self_db = self.db
        db_session_created_here = False
        db_session = None

        try:
            if self.db:
                db_session = self.db
            else:
                db_session = next(self.db_session_factory())
                self.db = db_session
                db_session_created_here = True
            
            tag_graph_accessor = TagGraphAccessor(db_session=db_session)

            generated_tags_tq_list_of_dicts = await self._get_query_tags_tq(user_query, knowledge_base_id)
            
            final_referenced_tags_info.clear()
            for tag_dict in generated_tags_tq_list_of_dicts:
                if isinstance(tag_dict, dict) and 'id' in tag_dict and 'name' in tag_dict:
                    final_referenced_tags_info.append(ReferencedTagInfo(
                        id=tag_dict['id'], 
                        name=tag_dict['name'], 
                        tag_type=tag_dict.get('tag_type')
                    ))
                else:
                    self.log_thinking_process(f"Skipping malformed tag_dict in T(q) list: {tag_dict}", "SystemCoordinator", level="WARNING")

            query_tag_ids_for_filtering = [tag.id for tag in final_referenced_tags_info] # Use .id from Pydantic model
            query_tag_names_for_logging = [tag.name for tag in final_referenced_tags_info]
            self.log_thinking_process(
                f"使用标签ID进行过滤: {query_tag_ids_for_filtering} (名称: {query_tag_names_for_logging})",
                "SystemCoordinator"
            )

            metadata_filter_for_tags = {}
            relevant_tag_ids = [tag.id for tag in final_referenced_tags_info]
            if relevant_tag_ids:
                # 使用OR逻辑关联标签：拥有任何一个标签的文档块都会被检索
                for tag_id in relevant_tag_ids:
                    metadata_filter_for_tags[f"tag_{tag_id}"] = True
                
                self.log_thinking_process(f"使用标签过滤器: {metadata_filter_for_tags}", "TagFilterAgent")
            else:
                self.log_thinking_process("没有找到相关标签，将使用普通的向量搜索", "TagFilterAgent")
            
            # 使用标签过滤器在向量存储中检索文档块
            # 先诊断知识库搜索状态
            try:
                # 尝试获取一些示例文档以诊断知识库存储状态
                diagnostic_docs = await vector_store_for_query.get_all_documents(limit=3)
                if diagnostic_docs:
                    tag_keys = []
                    for doc in diagnostic_docs:
                        # 收集所有标签键
                        doc_tag_keys = [k for k in doc.get("metadata", {}) if k.startswith("tag_")]
                        tag_keys.extend(doc_tag_keys)
                    
                    if tag_keys:
                        self.log_thinking_process(
                            f"诊断信息: 知识库中的文档有 {len(set(tag_keys))} 个不同的标签键",
                            "TagFilterAgent", status="Diagnostic", level="INFO"
                        )
                    else:
                        self.log_thinking_process(
                            "诊断警告: 知识库中的文档没有标签键",
                            "TagFilterAgent", status="DiagnosticWarning", level="WARN"
                        )
                else:
                    self.log_thinking_process(
                        f"诊断警告: 知识库 {knowledge_base_id} 中没有找到任何文档",
                        "TagFilterAgent", status="DiagnosticWarning", level="WARN"
                    )
            except Exception as e:
                self.log_thinking_process(
                    f"诊断错误: {str(e)}",
                    "TagFilterAgent", status="DiagnosticError", level="ERROR"
                )
            
            # 执行搜索
            candidate_chunks_raw = await vector_store_for_query.search(
                query=user_query, 
                k=TAG_FILTER_RETRIEVAL_K, 
                knowledge_base_id=knowledge_base_id, 
                metadata_filter=metadata_filter_for_tags if metadata_filter_for_tags else None
            )
            self.log_thinking_process(f"检索到 {len(candidate_chunks_raw)} 个原始候选块。", "TagFilterAgent", status="Completed")

            # 如果标签过滤没有找到任何块，退化到当前知识库的普通向量搜索
            if len(candidate_chunks_raw) == 0 and metadata_filter_for_tags:
                self.log_thinking_process("标签过滤没有找到文档块，退化到当前知识库的普通向量搜索模式。", "TagFilterAgent", status="Fallback")
                candidate_chunks_raw = await vector_store_for_query.search(
                    query=user_query, 
                    k=TAG_FILTER_RETRIEVAL_K, 
                    knowledge_base_id=knowledge_base_id,  # 仍然限制在当前知识库
                    metadata_filter=None  # 不使用标签过滤器
                )
                self.log_thinking_process(f"在无标签过滤模式下检索到 {len(candidate_chunks_raw)} 个原始候选块。", "TagFilterAgent", status="FallbackCompleted")
            
            # 如果仍然没有结果，记录错误并继续后续步骤
            if len(candidate_chunks_raw) == 0:
                self.log_thinking_process("无法找到与查询相关的文档块 - 可能需要上传更多相关内容到知识库。", "TagFilterAgent", status="NoResults")
                no_documents_found = True  # 标记没有找到文档
            else:
                no_documents_found = False

            scored_chunks: List[Dict[str, Any]] = []
            if candidate_chunks_raw:
                self.log_thinking_process(f"开始对 {len(candidate_chunks_raw)} 个候选块进行 T-CUS 评分。", "ExcerptAgent")
                query_embedding = None
                if self.embedding_instance:
                    try:
                        query_embedding = self.embedding_instance.embed_query(user_query)
                    except Exception as e_embed_query:
                        self.log_thinking_process(f"生成查询嵌入时出错: {e_embed_query}", "ExcerptAgent", level="ERROR")
                else:
                    self.log_thinking_process("嵌入模型实例不可用，无法生成查询嵌入。", "ExcerptAgent", level="ERROR")

                if query_embedding:
                    for i_chunk, chunk_dict_from_search in enumerate(candidate_chunks_raw):
                        chunk_text = chunk_dict_from_search.get("text", "")
                        chunk_metadata = chunk_dict_from_search.get("metadata", {})
                        if not chunk_text: 
                            self.log_thinking_process(f"块 {i_chunk} 内容为空，跳过评分。", "ExcerptAgent", level="WARNING")
                            continue

                        source_file = chunk_metadata.get('source', '未知文件')
                        chunk_idx_from_meta = chunk_metadata.get('chunk_index', i_chunk)
                        
                        # Log processing of chunk (can be detailed here or briefer)
                        self.log_thinking_process(f"处理块 {i_chunk+1}/{len(candidate_chunks_raw)}: 文件='{source_file}'", "ExcerptAgent")
                        
                        try:
                            score = await calculate_t_cus_score(
                                query_embedding=query_embedding,
                                chunk_content=chunk_text, 
                                chunk_metadata=chunk_metadata, # Pass full metadata
                                semantic_similarity_score=chunk_dict_from_search.get('score', 0.0), 
                                embedding_model_instance=self.embedding_instance, 
                                tag_graph_accessor=tag_graph_accessor, 
                                query_tags_tq_ids=query_tag_ids_for_filtering, 
                                chunk_embedding=chunk_dict_from_search.get('embedding') 
                            )
                            scored_chunks.append({
                                "content": chunk_text,
                                "metadata": chunk_metadata, # Keep original metadata from search
                                "score": score, # This is the T-CUS score
                                "token_count": chunk_metadata.get("token_count", len(chunk_text.split())) # Use from meta or estimate
                            })
                            self.log_thinking_process(f"评分完成: 文件='{source_file}', T-CUS分数={score:.4f}", "ExcerptAgent")
                        except Exception as score_err:
                            self.log_thinking_process(f"评分块时出错 (文件='{source_file}'): {score_err}", "ExcerptAgent", level="ERROR")
            self.log_thinking_process(f"完成对候选块的评分。共评分 {len(scored_chunks)} 个块。", "ExcerptAgent", status="Completed")

            selected_context_for_llm = ""
            selected_chunk_data_objects_for_api: List[Dict[str, Any]] = [] 
            final_referenced_excerpts_info.clear()

            self.log_thinking_process(f"开始选择上下文。已评分块数量: {len(scored_chunks)}, Token上限: {CONTEXT_TOKEN_LIMIT}", "ContextAssemblerAgent")
            try:
                if scored_chunks:
                    selected_context_for_llm, selected_chunk_data_objects_for_api = greedy_token_constrained_selection(
                        scored_chunks, 
                        CONTEXT_TOKEN_LIMIT
                    )
                    self.log_thinking_process(
                        f"上下文组装完成。共选定 {len(selected_chunk_data_objects_for_api)} 个块。",
                        "ContextAssemblerAgent", 
                        status="Completed"
                    )
                    
                    for i, sel_chunk_data in enumerate(selected_chunk_data_objects_for_api): # Added enumerate for unique pseudo ID
                        meta = sel_chunk_data.get("metadata", {})
                        
                        doc_id_val = meta.get("document_id")
                        doc_id = int(doc_id_val) if doc_id_val is not None else None
                        
                        chunk_idx_val = meta.get("chunk_index")
                        chunk_idx = int(chunk_idx_val) if chunk_idx_val is not None else None

                        page_num_val = meta.get("page_number") or meta.get("page")
                        page_num = int(page_num_val) if page_num_val is not None else None

                        score_val = sel_chunk_data.get("score") # This is the T-CUS score from scored_chunks
                        score_float = float(score_val) if score_val is not None else None

                        chunk_id_str = meta.get("id") # Prefer 'id' from metadata if it's the ChromaDB chunk ID
                        if not chunk_id_str and doc_id is not None and chunk_idx is not None:
                            chunk_id_str = f"{doc_id}_{chunk_idx}"
                        if not chunk_id_str:
                            content_preview = sel_chunk_data.get("content", "")[:20]
                            chunk_id_str = f"pseudo_{hash(content_preview)}_{i}" # Use enumerate index 'i'

                        final_referenced_excerpts_info.append(ReferencedExcerptInfo(
                            document_id=doc_id,
                            document_source=meta.get("source", "未知来源"),
                            chunk_id=chunk_id_str,
                            content=sel_chunk_data.get("content", ""),
                            page_number=page_num,
                            score=score_float 
                        ))
                else:
                    self.log_thinking_process("没有已评分的块可供组装上下文。", "ContextAssemblerAgent", level="WARNING")
            except Exception as e_context:
                self.log_thinking_process(f"组装上下文时出错: {e_context}", "ContextAssemblerAgent", level="ERROR")

            # 如果启用了代码检索，添加代码检索功能
            if use_code_retrieval and repository_id and self.db:
                self.log_thinking_process("开始检索相关代码", "CodeRetrievalAgent")
                try:
                    # 创建代码检索服务
                    from code_retrieval_service import CodeRetrievalService
                    code_service = CodeRetrievalService(self.db)
                    
                    # 提取代码关键词
                    code_keywords = await code_service.extract_code_keywords(user_query)
                    if code_keywords:
                        self.log_thinking_process(f"提取到的代码关键词: {', '.join(code_keywords)}", "CodeRetrievalAgent")
                        
                        # 构建代码专用查询
                        code_query = " ".join(code_keywords)
                        
                        # 检索代码片段
                        code_results = await code_service.retrieve_code_by_query(
                            query=code_query,
                            repository_id=repository_id,
                            top_k=3  # 限制返回的代码片段数量
                        )
                        
                        # 将检索到的代码添加到上下文
                        if code_results:
                            code_context = "\n\n以下是与查询可能相关的代码片段:\n\n"
                            for i, snippet in enumerate(code_results):
                                code_context += f"代码片段 {i+1} - {snippet.get('name', '未命名')} ({snippet.get('file_path', '未知文件')}):\n```\n{snippet.get('code', '// 代码不可用')}\n```\n\n"
                                
                                # 将代码片段添加到结果列表
                                code_snippets.append(CodeSnippetInfo(
                                    component_id=snippet.get("id"),
                                    file_path=snippet.get("file_path"),
                                    name=snippet.get("name"),
                                    type=snippet.get("type"),
                                    code=snippet.get("code"),
                                    signature=snippet.get("signature"),
                                    start_line=snippet.get("start_line"),
                                    end_line=snippet.get("end_line"),
                                    score=snippet.get("similarity_score"),
                                    repository_id=repository_id
                                ))
                            
                            # 添加代码上下文到选定的上下文
                            selected_context_for_llm += "\n\n" + code_context
                            self.log_thinking_process(f"检索到 {len(code_results)} 个相关代码片段", "CodeRetrievalAgent")
                    else:
                        self.log_thinking_process("未能从查询中提取到代码关键词", "CodeRetrievalAgent")
                except Exception as e:
                    self.log_thinking_process(f"代码检索失败: {str(e)}", "CodeRetrievalAgent", level="ERROR")

            self.log_thinking_process("开始生成最终答案。", "TagRAG_AnswerAgent")
            
            final_answer_agent_prompt_template = ("""你是一个专业的AI助手，负责根据提供的上下文信息和用户查询，生成一份全面、深入且易于理解的回答。

用户的查询是: \"{user_query}\"

以下是经过筛选和排序的相关上下文信息，每个信息片段都尽可能标记了其来源（例如，文档ID，块索引，或文件名）：
--- BEGIN CONTEXT ---
{selected_context_for_llm}
--- END CONTEXT ---

请遵循以下指引来构建你的回答：
1.  **核心任务**: 清晰、准确、完整地回答用户查询。
2.  **深入分析与综合**: 不要简单罗列信息。你需要理解、分析并综合上下文中的信息，形成连贯且有逻辑的答案。如果信息来自多个片段，请努力将它们融合成一个整体性的观点或描述。
3.  **明确引用来源**: 当你的回答直接或间接依赖于上下文中的特定信息时，必须在相应句子或段落的末尾明确标注引用来源。使用方括号，例如：\"系统支持用户权限管理 [来源: 文档A_chunk2]\" 或 \"根据文档B第3页所述 [来源: 文档B_page3]\"。如果上下文中提供了具体的文档名、ID或块信息，请尽量使用它们。
4.  **展示推理过程**: 对于非直接陈述性的结论，或者当答案是基于多个信息点综合推断得出时，请简要阐述你的推理逻辑。例如：\"由于上下文片段1指出X，并且片段2显示Y与X相关，因此我们可以推断Z [来源: 片段1, 片段2]\"。
5.  **全局性与结构化**: 从全局视角组织你的回答，确保逻辑清晰，结构合理。可以使用小标题、列表等形式使回答更易读。
6.  **专业语气与客观性**: 使用专业、客观的语言。避免主观臆断或没有依据的推测。
7.  **处理信息不足**: 如果提供的上下文信息不足以完全或准确地回答用户查询的某个方面，请明确指出信息缺失，并可以建议用户提供更具体的问题或说明当前答案的局限性。例如："关于XX的具体实现细节，当前上下文未提供足够信息 [信息来源局限]。"
8.  **灵活性与相关性**: 根据上下文信息与用户查询的相关度，调整回答的详细程度。对于高度相关的信息，应详细阐述；对于相关度较低但仍有参考价值的信息，可简要提及。
9.  **避免生硬的直接答案**: 你的回答应该是一段经过思考和组织的论述，而不仅仅是一个词或一个短句的答案。
10. **如果有代码片段**: 如果上下文中包含代码片段，仔细分析代码并在回答中引用关键部分，解释其功能和作用。

请现在开始生成你的专业回答。
""")
            final_answer_agent_prompt = final_answer_agent_prompt_template.format(
                user_query=user_query,
                selected_context_for_llm=(selected_context_for_llm if selected_context_for_llm and selected_context_for_llm.strip() 
                                        else "当前未找到与查询直接相关的上下文信息。请基于您的通用知识回答，并明确指出这是通用知识。")
            )

            if self.final_answer_agent and self.user_proxy and self.llm_client: 
                final_answer = await self.llm_client.generate(final_answer_agent_prompt)
            else:
                final_answer = "Final Answer Agent, User Proxy 或 LLMClient 未初始化。"
                self.log_thinking_process("FinalAnswerAgent, UserProxy 或 LLMClient 未初始化。", "TagRAG_AnswerAgent", level="ERROR")
            
            self.log_thinking_process(f"生成的最终答案 (前100字符): '{final_answer[:100]}...'", "TagRAG_AnswerAgent", status="Completed")

        except Exception as e:
            self.log_thinking_process(f"TagRAG流程中发生意外错误: {e}", "SystemCoordinator", level="CRITICAL")
            final_answer = f"处理您的请求时发生内部错误: {str(e)}"
        finally:
            if db_session_created_here and db_session: 
                try:
                    db_session.close()
                except Exception as e_db_close:
                    logger.error(f"Error closing DB session created in generate_answer_tag_rag: {e_db_close}", exc_info=True)
            self.db = original_self_db 

        return TagRAGChatResponse(
            answer=final_answer,
            thinking_process=self.get_thinking_process(),
            referenced_tags=final_referenced_tags_info, 
            referenced_excerpts=final_referenced_excerpts_info,
            code_snippets=code_snippets, # 添加代码片段到响应
            user_query=user_query,
            knowledge_base_id=knowledge_base_id
        )

    async def generate_answer_original(
        self, 
        user_query: str,
        use_code_analysis: bool = False,
        code_analyzer: Any = None,
        vector_store: Optional[VectorStore] = None,
        repository_id: Optional[int] = None,
        knowledge_base_id: Optional[int] = None,
        prompt_configs: Optional[Dict[str, str]] = None,
        use_code_retrieval: bool = False  # 新增参数，控制是否启用代码检索
    ) -> str:
        """生成对用户问题的回答 (保留的原有逻辑)
        """
        self.clear_thinking_process()
        self.thinking_process.append({"operation": "generate_answer_original", "user_query": user_query, "use_code_analysis": use_code_analysis, "kb_id": knowledge_base_id, "repo_id": repository_id, "use_code_retrieval": use_code_retrieval })

        try:
            current_vector_store = vector_store or self.vector_store
            retrieval_results = await current_vector_store.search(user_query, k=5, knowledge_base_id=knowledge_base_id)
            self.thinking_process.append({"task": "OriginalRetrieval", "retrieved_count": len(retrieval_results)})
            
            retrieval_context = ""
            for i, result in enumerate(retrieval_results):
                retrieval_context += f"文档 {i+1}:\n"
                # 添加键存在性检查，避免KeyError
                content = result.get('content', result.get('text', '无内容'))
                retrieval_context += f"内容: {content}\n"
                
                # 确保metadata存在
                metadata = result.get('metadata', {})
                retrieval_context += f"来源: {metadata.get('source', '未知')}\n"
                if metadata.get('sheet_name'):
                    retrieval_context += f"工作表: {metadata['sheet_name']}\n"
                retrieval_context += f"相关度得分: {result.get('score', 'N/A')}\n"
                if metadata.get('knowledge_base_id'):
                    retrieval_context += f"知识库ID: {metadata['knowledge_base_id']}\n"
                retrieval_context += "\n"
            
            code_analysis_context = ""
            code_snippets = []
            if use_code_analysis and code_analyzer and repository_id is not None:
                code_analysis_context = "[Code analysis context from original flow]\n"
                self.thinking_process.append({"task": "OriginalCodeAnalysis", "status": "Generated"})
            
            # 添加代码检索功能
            if use_code_retrieval and repository_id is not None and self.db:
                self.log_thinking_process("开始检索相关代码", "CodeRetrievalAgent")
                try:
                    # 创建代码检索服务
                    from code_retrieval_service import CodeRetrievalService
                    code_service = CodeRetrievalService(self.db)
                    
                    # 提取代码关键词
                    code_keywords = await code_service.extract_code_keywords(user_query)
                    if code_keywords:
                        self.log_thinking_process(f"提取到的代码关键词: {', '.join(code_keywords)}", "CodeRetrievalAgent")
                        
                        # 构建代码专用查询
                        code_query = " ".join(code_keywords)
                        
                        # 检索代码片段
                        code_results = await code_service.retrieve_code_by_query(
                            query=code_query,
                            repository_id=repository_id,
                            top_k=3  # 限制返回的代码片段数量
                        )
                        
                        # 将检索到的代码添加到上下文
                        if code_results:
                            code_analysis_context += "\n代码检索结果:\n"
                            for i, snippet in enumerate(code_results):
                                code_analysis_context += f"代码片段 {i+1} - {snippet.get('name', '未命名')} ({snippet.get('file_path', '未知文件')}):\n"
                                code_analysis_context += f"```\n{snippet.get('code', '// 代码不可用')}\n```\n\n"
                                
                                # 添加到代码片段列表，用于前端显示
                                code_snippets.append(CodeSnippetInfo(
                                    component_id=snippet.get("id"),
                                    file_path=snippet.get("file_path"),
                                    name=snippet.get("name"),
                                    type=snippet.get("type"),
                                    code=snippet.get("code"),
                                    signature=snippet.get("signature"),
                                    start_line=snippet.get("start_line"),
                                    end_line=snippet.get("end_line"),
                                    score=snippet.get("similarity_score"),
                                    repository_id=repository_id
                                ))
                            
                            self.log_thinking_process(f"检索到 {len(code_results)} 个相关代码片段", "CodeRetrievalAgent")
                    else:
                        self.log_thinking_process("未能从查询中提取到代码关键词", "CodeRetrievalAgent")
                        
                except Exception as e:
                    self.log_thinking_process(f"代码检索失败: {str(e)}", "CodeRetrievalAgent", level="ERROR")

            initial_message = f"User Query: {user_query}\n\nRetrieved Context:\n{retrieval_context}"
            if code_analysis_context:
                initial_message += f"\nCode Analysis Context:\n{code_analysis_context}"

            if prompt_configs:
                 self._init_agents(use_code_analysis, prompt_configs)

            if use_code_analysis or use_code_retrieval:  # 修改逻辑，当启用代码检索时也使用完整的代理组
                groupchat = autogen.GroupChat(
                    agents=[self.user_proxy, self.retrieval_agent, self.analyst_agent, self.code_analyst_agent, self.final_answer_agent],
                    messages=[],
                    max_round=5
                )
                manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=self.llm_config)
                self.user_proxy.initiate_chat(
                    manager,
                    message=initial_message,
                    clear_history=True
                )
            else:
                self.user_proxy.initiate_chat(
                    self.retrieval_agent, 
                    message=initial_message, 
                    clear_history=True, 
                    max_turns=1
                )
                self.user_proxy.initiate_chat(
                    self.final_answer_agent,
                    message=self.user_proxy.last_message(self.retrieval_agent).get("content", initial_message),
                    clear_history=True,
                    max_turns=1
                )

            answer = self.user_proxy.last_message(self.final_answer_agent if use_code_analysis or use_code_retrieval else self.final_answer_agent).get("content", "Sorry, I could not generate an answer (original flow).")
            self.thinking_process.append({"task": "OriginalAnswerGeneration", "final_answer_length": len(answer)})
            
            # 如果启用了代码检索，返回代码片段信息
            if use_code_retrieval and code_snippets:
                self.thinking_process.append({"task": "CodeRetrieval", "snippets_count": len(code_snippets)})
                # 仅返回答案和思考过程，让main.py处理代码片段
                return answer
            else:
                return answer

        except Exception as e:
            logger.error(f"Error in original generate_answer: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.thinking_process.append({"error": "Original generate_answer failed", "details": str(e)})
            return f"An error occurred in original flow: {str(e)}" 