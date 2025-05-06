import os
import json
import autogen
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import asyncio

# 导入配置文件
from config import get_autogen_config, AGENT_PROMPTS

class AgentManager:
    """AutoGen智能体管理器，负责协调多个智能体生成回答"""
    
    def __init__(self, vector_store):
        self.vector_store = vector_store
        
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
    
    def _init_agents(self):
        """初始化智能体"""
        # 用户代理（代表用户发起请求）
        self.user_proxy = autogen.UserProxyAgent(
            name="用户代理",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
            code_execution_config={"use_docker": False},
            max_consecutive_auto_reply=self.max_consecutive_auto_reply,
        )
        
        # 检索代理（负责检索文档）
        self.retrieval_agent = autogen.AssistantAgent(
            name="检索代理",
            llm_config=self.llm_config,
            system_message=AGENT_PROMPTS["retrieval_agent"],
            max_consecutive_auto_reply=self.max_consecutive_auto_reply,
        )
        
        # 分析代理（分析检索到的信息）
        self.analyst_agent = autogen.AssistantAgent(
            name="分析代理",
            llm_config=self.llm_config,
            system_message=AGENT_PROMPTS["analyst_agent"],
            max_consecutive_auto_reply=self.max_consecutive_auto_reply,
        )
        
        # 代码分析代理（分析代码）
        self.code_analyst_agent = autogen.AssistantAgent(
            name="代码分析代理",
            llm_config=self.llm_config,
            system_message=AGENT_PROMPTS["code_analyst_agent"],
            max_consecutive_auto_reply=self.max_consecutive_auto_reply,
        )
        
        # 回复生成代理（综合所有信息生成最终回复）
        self.response_agent = autogen.AssistantAgent(
            name="回复生成代理",
            llm_config=self.llm_config,
            system_message=AGENT_PROMPTS["response_agent"],
            max_consecutive_auto_reply=self.max_consecutive_auto_reply,
        )
    
    def _extract_chat_history(self):
        """从所有代理的聊天记录中提取思考过程"""
        self.thinking_process = []
        
        # 获取检索代理对话
        if hasattr(self.retrieval_agent, 'chat_messages') and self.user_proxy in self.retrieval_agent.chat_messages:
            for message in self.retrieval_agent.chat_messages[self.user_proxy]:
                self.thinking_process.append({
                    "sender": "检索代理",
                    "recipient": "用户代理",
                    "content": message.get("content", ""),
                    "timestamp": asyncio.get_event_loop().time()
                })
        
        # 获取分析代理对话
        if hasattr(self.analyst_agent, 'chat_messages') and self.user_proxy in self.analyst_agent.chat_messages:
            for message in self.analyst_agent.chat_messages[self.user_proxy]:
                self.thinking_process.append({
                    "sender": "分析代理",
                    "recipient": "用户代理",
                    "content": message.get("content", ""),
                    "timestamp": asyncio.get_event_loop().time()
                })
        
        # 获取代码分析代理对话
        if hasattr(self.code_analyst_agent, 'chat_messages') and self.user_proxy in self.code_analyst_agent.chat_messages:
            for message in self.code_analyst_agent.chat_messages[self.user_proxy]:
                self.thinking_process.append({
                    "sender": "代码分析代理",
                    "recipient": "用户代理",
                    "content": message.get("content", ""),
                    "timestamp": asyncio.get_event_loop().time()
                })
        
        # 获取回复生成代理对话
        if hasattr(self.response_agent, 'chat_messages') and self.user_proxy in self.response_agent.chat_messages:
            for message in self.response_agent.chat_messages[self.user_proxy]:
                self.thinking_process.append({
                    "sender": "回复生成代理",
                    "recipient": "用户代理",
                    "content": message.get("content", ""),
                    "timestamp": asyncio.get_event_loop().time()
                })
        
        # 获取用户代理的发送消息
        agents = [self.retrieval_agent, self.analyst_agent, self.code_analyst_agent, self.response_agent]
        for agent in agents:
            if hasattr(self.user_proxy, 'chat_messages') and agent in self.user_proxy.chat_messages:
                for message in self.user_proxy.chat_messages[agent]:
                    self.thinking_process.append({
                        "sender": "用户代理",
                        "recipient": agent.name,
                        "content": message.get("content", ""),
                        "timestamp": asyncio.get_event_loop().time()
                    })
    
    def get_thinking_process(self):
        """获取智能体思考过程"""
        return self.thinking_process
    
    def clear_thinking_process(self):
        """清空思考过程"""
        self.thinking_process = []
    
    async def generate_answer(self, 
                       query: str, 
                       use_code_analysis: bool = False, 
                       code_analyzer = None,
                       vector_store = None,
                       repository_id: Optional[int] = None,
                       knowledge_base_id: Optional[int] = None) -> str:
        """生成对用户问题的回答
        
        Args:
            query: 用户查询
            use_code_analysis: 是否使用代码分析
            code_analyzer: 代码分析器实例
            vector_store: 向量存储实例
            repository_id: 代码库ID
            knowledge_base_id: 知识库ID
            
        Returns:
            str: 生成的回答
        """
        try:
            # 清空之前的思考过程
            self.clear_thinking_process()
            
            # 1. 从向量存储中检索相关文档
            # 使用正确的 vector_store 实例（它内部已经绑定了 repo_id，如果适用）
            current_vector_store = vector_store or self.vector_store
            retrieval_results = await current_vector_store.search(query, k=5)
            
            # 2. 准备检索结果
            retrieval_context = ""
            for i, result in enumerate(retrieval_results):
                retrieval_context += f"文档 {i+1}:\n"
                retrieval_context += f"内容: {result['content']}\n"
                retrieval_context += f"来源: {result['metadata'].get('source', '未知')}\n"
                if 'sheet_name' in result['metadata']:
                    retrieval_context += f"工作表: {result['metadata']['sheet_name']}\n"
                retrieval_context += f"相关度得分: {result['score']}\n\n"
            
            # 3. 准备代码分析结果（如果启用且有 repo_id）
            code_analysis_context = ""
            code_repo_context = ""
            if use_code_analysis and code_analyzer and repository_id is not None:
                # 使用传入的 repository_id
                try:
                    # 获取字段信息
                    all_fields_list = await code_analyzer.get_all_fields(repository_id)
                    all_fields_map = {f['name']: f for f in all_fields_list}
                    all_field_names = list(all_fields_map.keys())
                    
                    # 分词，获取查询中的关键词
                    words = query.split()
                    
                    # 去重，避免重复分析
                    analyzed_fields = set()
                    impact_summary = ""
                    
                    # 直接匹配查询词和字段名
                    for word in words:
                        if len(word) > 2 and word in all_field_names and word not in analyzed_fields:
                            field_impact = await code_analyzer.get_field_impact(word, repository_id)
                            if field_impact and 'used_by' in field_impact:
                                impact_summary += f"### 字段 '{word}' 的影响分析:\n"
                                impact_summary += f"字段信息: 类型={field_impact['field']['type']}, 文件={field_impact['field']['file_path']}\n"
                                impact_summary += f"被以下组件使用 ({field_impact['usage_count']} 次):\n"
                                for usage in field_impact['used_by'][:5]: # Limit displayed usages
                                    impact_summary += f"- {usage['name']} ({usage['type']}) in {usage['file_path']}\n"
                                if field_impact['usage_count'] > 5:
                                    impact_summary += f"... 等等 ({field_impact['usage_count'] - 5} 更多)\n"
                                impact_summary += "\n"
                                analyzed_fields.add(word)
                    
                    # 部分匹配
                    for field_name in all_field_names:
                        if len(field_name) > 5 and field_name not in analyzed_fields:
                            for word in words:
                                if len(word) > 3 and word.lower() in field_name.lower():
                                    field_impact = await code_analyzer.get_field_impact(field_name, repository_id)
                                    if field_impact and 'used_by' in field_impact:
                                        impact_summary += f"### 相关字段 '{field_name}' 的影响分析:\n"
                                        impact_summary += f"字段信息: 类型={field_impact['field']['type']}, 文件={field_impact['field']['file_path']}\n"
                                        impact_summary += f"被以下组件使用 ({field_impact['usage_count']} 次):\n"
                                        for usage in field_impact['used_by'][:3]: # Limit displayed usages
                                            impact_summary += f"- {usage['name']} ({usage['type']}) in {usage['file_path']}\n"
                                        if field_impact['usage_count'] > 3:
                                            impact_summary += f"... 等等 ({field_impact['usage_count'] - 3} 更多)\n"
                                        impact_summary += "\n"
                                        analyzed_fields.add(field_name)
                                        break # Found a match for this field, move to next field
                    
                    # 如果没有找到任何相关字段，提供一般信息
                    if not impact_summary:
                        impact_summary += "未在查询中找到直接相关的代码字段。\n"
                        # 提供一些最常用的字段作为参考
                        if all_fields_list:
                            impact_summary += "代码库中的常用字段可能包括:\n"
                            # 可以基于字段出现的频率等提供更有用的信息，这里仅列出前几个
                            for field_info in all_fields_list[:5]:
                                impact_summary += f"- {field_info['name']} ({field_info.get('data_type', field_info['type'])}) in {field_info['file_path']}\n"
                            impact_summary += "\n"
                    
                    code_analysis_context = impact_summary

                    # 获取额外的代码库上下文信息
                    try:
                        repo_structure = await code_analyzer.get_repository_structure(repository_id)
                        if repo_structure:
                            code_repo_context += f"### 代码库结构 (部分):\n"
                            # 简单的文本表示，避免过长
                            def format_structure(node, indent=0):
                                prefix = "  " * indent
                                line = f"{prefix}- {node['name']} ({node['type']})\n"
                                if node['type'] == 'directory' and 'children' in node:
                                    for child in node['children'][:5]: # Limit displayed children per dir
                                        line += format_structure(child, indent + 1)
                                    if len(node['children']) > 5:
                                        line += f"{prefix}  - ... ({len(node['children']) - 5} more)\n"
                                return line
                            code_repo_context += format_structure(repo_structure)
                            code_repo_context += "\n"
                        
                        repo_summary = await code_analyzer.get_repository_summary(repository_id)
                        if repo_summary:
                            code_repo_context += f"### 代码库摘要:\n"
                            if "statistics" in repo_summary:
                                stats = repo_summary["statistics"]
                                code_repo_context += f"文件总数: {stats.get('total_files', 'N/A')}, 组件总数: {stats.get('total_components', 'N/A')}\n"
                            if "important_components" in repo_summary and repo_summary["important_components"]:
                                code_repo_context += "主要组件:\n"
                                for comp in repo_summary["important_components"][:3]:
                                    code_repo_context += f"- {comp['name']} ({comp['type']}) in {comp['file']}\n"
                            code_repo_context += "\n"

                        # 获取与查询相关的代码组件
                        components = await code_analyzer.search_components(
                            repository_id, # 使用传入的 repository_id
                            query,
                            limit=3 # 限制结果数量
                        )
                        if components:
                            code_repo_context += "### 相关代码组件:\n"
                            for i, comp in enumerate(components):
                                code_repo_context += f"{i+1}. {comp['name']} ({comp['type']}) in {comp['file_path']}\n"
                                if comp.get('code_preview'):
                                    code_repo_context += f"   预览:\n```\n{comp['code_preview']}\n```\n"
                            code_repo_context += "\n"

                    except Exception as e:
                        # 这个 except 对应获取附加上下文的 try
                        code_repo_context += f"获取代码库附加上下文时出错: {str(e)}\n"

                except Exception as e:
                    # 这个 except 对应最外层的 try (获取字段和影响分析)
                    code_analysis_context = f"准备代码分析上下文时出错: {str(e)}\n"
                    # 记录更详细的错误日志
                    import logging
                    import traceback
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error during code analysis context preparation: {traceback.format_exc()}")

            elif use_code_analysis and repository_id is None:
                 code_analysis_context = "代码分析已启用，但未选择代码库。请先选择一个代码库。\n"

            # 4. 创建工作记忆（对话历史） - 这部分现在可能不需要了，因为信息直接传递给agent
            # chat_history = [] # 移除旧的 chat_history 逻辑
            
            # 5. 构建传递给智能体的消息内容
            initial_message_content = f"用户问题: {query}\n\n"
            if retrieval_context:
                initial_message_content += f"检索到的相关文档:\n{retrieval_context}\n"
            if code_analysis_context:
                 initial_message_content += f"代码分析结果:\n{code_analysis_context}\n"
            if code_repo_context:
                 initial_message_content += f"代码库附加上下文:\n{code_repo_context}\n"

            # 6. 恢复顺序调用智能体的流程
            
            # 清理代理状态
            self.user_proxy.reset()
            self.retrieval_agent.reset()
            self.analyst_agent.reset()
            self.code_analyst_agent.reset()
            self.response_agent.reset()

            # a. 用户代理 -> 检索代理
            retrieval_message = "\n用户问题: " + query + "\n\n"
            retrieval_message += "请分析问题并确定需要检索哪些信息。\n"
            # 使用普通拼接而不是 f-string 表达式
            if retrieval_context:
                retrieval_message += "相关文档上下文:\n" + retrieval_context + "\n"
            retrieval_message += "分析完成后回复 \"TERMINATE\"。"

            self.user_proxy.initiate_chat(
                self.retrieval_agent,
                message=retrieval_message,
                max_turns=2, # 限制轮次，避免不必要的对话
            )
            retrieval_reply = self.user_proxy.last_message(self.retrieval_agent)["content"]
            # retrieval_reply = self.retrieval_agent.last_message(self.user_proxy)["content"] # 或者用这个，取决于谁最后发言


            # b. 用户代理 -> 分析代理
            analysis_message = "\n用户问题: " + query + "\n\n"
            analysis_message += "检索代理的分析/结果:\n" + retrieval_reply + "\n\n"
            analysis_message += "请分析这些信息，找出关键洞见和模式。分析完成后回复 \"TERMINATE\"。"

            self.user_proxy.initiate_chat(
                self.analyst_agent,
                message=analysis_message,
                max_turns=2,
            )
            analysis_reply = self.user_proxy.last_message(self.analyst_agent)["content"]
            # analysis_reply = self.analyst_agent.last_message(self.user_proxy)["content"]

            # c. 用户代理 -> 代码分析代理 (如果启用)
            code_analysis_reply = ""
            if use_code_analysis and (code_analysis_context or code_repo_context):
                code_message = "\n用户问题: " + query + "\n\n"
                code_message += "代码分析上下文:\n" + code_analysis_context + "\n"
                if code_repo_context:
                    code_message += code_repo_context + "\n"
                code_message += "请分析提供的代码信息，回答用户关于代码的问题或评估影响。\n"
                code_message += "记住，你可以访问数据库中的代码，不需要用户提供额外代码。\n"
                code_message += "分析完成后回复 \"TERMINATE\"。"

                self.user_proxy.initiate_chat(
                    self.code_analyst_agent,
                    message=code_message,
                    max_turns=2,
                )
                code_analysis_reply = self.user_proxy.last_message(self.code_analyst_agent)["content"]
                # code_analysis_reply = self.code_analyst_agent.last_message(self.user_proxy)["content"]

            # d. 用户代理 -> 回复生成代理
            response_message = "\n用户问题: " + query + "\n\n"
            response_message += "检索代理的分析:\n" + retrieval_reply + "\n\n"
            response_message += "信息分析:\n" + analysis_reply + "\n\n"
            if code_analysis_reply:
                response_message += "代码分析:\n" + code_analysis_reply + "\n\n"
            response_message += "请综合以上所有信息，生成一个全面、准确、有条理的回复来解答用户的问题。\n"
            response_message += "完成后回复 \"TERMINATE\"。"

            self.user_proxy.initiate_chat(
                self.response_agent,
                message=response_message,
                max_turns=2,
            )
            final_reply = self.user_proxy.last_message(self.response_agent)["content"]
            # final_reply = self.response_agent.last_message(self.user_proxy)["content"]

            # 清理掉可能的TERMINATE标记
            if "TERMINATE" in final_reply:
                final_reply = final_reply.replace("TERMINATE", "").strip()
            
            # 收集所有对话历史作为思考过程
            self._extract_chat_history() # 使用旧的提取方法
            
            return final_reply
            
        except Exception as e:
            # 这个 except 对应 generate_answer 方法最外层的 try
            print(f"生成回答时出错: {str(e)}")
            import traceback
            traceback.print_exc() # 打印详细错误信息
            return f"抱歉，处理您的问题时出现了错误: {str(e)}" 