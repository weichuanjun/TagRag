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
                       code_analyzer = None) -> str:
        """生成对用户问题的回答"""
        try:
            # 清空之前的思考过程
            self.clear_thinking_process()
            
            # 1. 从向量存储中检索相关文档
            retrieval_results = await self.vector_store.search(query, k=5)
            
            # 2. 准备检索结果
            retrieval_context = ""
            for i, result in enumerate(retrieval_results):
                retrieval_context += f"文档 {i+1}:\n"
                retrieval_context += f"内容: {result['content']}\n"
                retrieval_context += f"来源: {result['metadata'].get('source', '未知')}\n"
                if 'sheet_name' in result['metadata']:
                    retrieval_context += f"工作表: {result['metadata']['sheet_name']}\n"
                retrieval_context += f"相关度得分: {result['score']}\n\n"
            
            # 3. 准备代码分析结果（如果启用）
            code_analysis_context = ""
            if use_code_analysis and code_analyzer:
                # 首先获取所有字段，检查哪些与查询相关
                all_fields = await code_analyzer.get_all_fields()
                
                # 分词，获取查询中的关键词
                words = query.split()
                
                # 去重，避免重复分析
                analyzed_fields = set()
                
                # 直接匹配
                for word in words:
                    if len(word) > 2:  # 忽略太短的词
                        # 直接检查是否是字段
                        if word in all_fields and word not in analyzed_fields:
                            impact_results = await code_analyzer.get_field_impact(word)
                            if impact_results:
                                code_analysis_context += f"### 字段 '{word}' 的影响分析:\n"
                                for impact in impact_results:
                                    code_analysis_context += f"- 文件: {impact['file_path']}\n"
                                    code_analysis_context += f"  行号: {impact['line_number']}\n"
                                    if impact.get('match_type') == 'partial':
                                        code_analysis_context += f"  匹配字段: {impact.get('field_name', word)}\n"
                                code_analysis_context += "\n"
                                analyzed_fields.add(word)
                
                # 部分匹配
                for field in all_fields:
                    # 检查查询中是否包含字段名的一部分，但仅限于较长的字段
                    if len(field) > 5 and field not in analyzed_fields:
                        for word in words:
                            if len(word) > 3 and word.lower() in field.lower():
                                impact_results = await code_analyzer.get_field_impact(field)
                                if impact_results:
                                    code_analysis_context += f"### 相关字段 '{field}' 的影响分析:\n"
                                    for impact in impact_results[:5]:  # 限制结果数
                                        code_analysis_context += f"- 文件: {impact['file_path']}\n"
                                        code_analysis_context += f"  行号: {impact['line_number']}\n"
                                    code_analysis_context += "\n"
                                    analyzed_fields.add(field)
                                    break  # 已分析过此字段，跳出内层循环
                
                # 如果没有找到任何相关字段，尝试根据查询找出最相关的字段
                if not code_analysis_context:
                    # 按字段出现频率排序，取前10个
                    fields_with_counts = []
                    for field in all_fields:
                        impact_results = await code_analyzer.get_field_impact(field)
                        fields_with_counts.append((field, len(impact_results)))
                    
                    # 排序并取前10个最常出现的字段
                    top_fields = sorted(fields_with_counts, key=lambda x: x[1], reverse=True)[:10]
                    
                    code_analysis_context += "### 代码库中的主要字段：\n"
                    for field, count in top_fields:
                        code_analysis_context += f"- {field} (出现 {count} 次)\n"
                    code_analysis_context += "\n请使用这些字段名称进行更精确的查询。\n\n"
            
            # 4. 创建工作记忆（对话历史）
            chat_history = []
            
            # 5. 添加用户问题
            chat_history.append({
                "role": "user",
                "content": query
            })
            
            # 6. 添加检索结果
            if retrieval_context:
                chat_history.append({
                    "role": "system",
                    "content": f"以下是从相关文档中检索到的信息:\n\n{retrieval_context}"
                })
            
            # 7. 添加代码分析结果（如果有）
            if code_analysis_context:
                chat_history.append({
                    "role": "system",
                    "content": f"以下是代码分析结果:\n\n{code_analysis_context}"
                })
            
            # 8. 使用AutoGen进行多智能体协作，加入互动次数限制
            # 初始化聊天
            self.user_proxy.initiate_chat(
                self.retrieval_agent,
                message=f"""
                用户问题: {query}
                
                检索到的相关文档:
                {retrieval_context}
                
                {'代码分析结果:' if code_analysis_context else ''}
                {code_analysis_context if code_analysis_context else ''}
                
                请分析这些信息，提取与问题相关的要点。分析完成后回复"TERMINATE"结束对话。
                """,
                max_turns=3,  # 限制最大对话轮次
            )
            
            # 获取检索代理的回复
            retrieval_reply = self.retrieval_agent.chat_messages[self.user_proxy][-1]["content"]
            
            # 将检索分析传递给分析代理
            self.user_proxy.initiate_chat(
                self.analyst_agent,
                message=f"""
                用户问题: {query}
                
                检索代理的分析:
                {retrieval_reply}
                
                请深入分析这些信息，找出关键洞见和模式。分析完成后回复"TERMINATE"结束对话。
                """,
                max_turns=3,  # 限制最大对话轮次
            )
            
            # 获取分析代理的回复
            analysis_reply = self.analyst_agent.chat_messages[self.user_proxy][-1]["content"]
            
            # 如果启用了代码分析，则使用代码分析代理
            code_analysis_reply = ""
            if use_code_analysis and code_analysis_context:
                self.user_proxy.initiate_chat(
                    self.code_analyst_agent,
                    message=f"""
                    用户问题: {query}
                    
                    代码分析结果:
                    {code_analysis_context}
                    
                    请分析这些代码引用，确定修改相关字段可能产生的影响。分析完成后回复"TERMINATE"结束对话。
                    """,
                    max_turns=3,  # 限制最大对话轮次
                )
                
                # 获取代码分析代理的回复
                code_analysis_reply = self.code_analyst_agent.chat_messages[self.user_proxy][-1]["content"]
            
            # 将所有分析传递给回复生成代理
            self.user_proxy.initiate_chat(
                self.response_agent,
                message=f"""
                用户问题: {query}
                
                检索代理的分析:
                {retrieval_reply}
                
                信息分析:
                {analysis_reply}
                
                {'代码分析:' if code_analysis_reply else ''}
                {code_analysis_reply if code_analysis_reply else ''}
                
                请生成一个全面、准确、有条理的回复来解答用户的问题。完成后回复"TERMINATE"结束对话。
                """,
                max_turns=3,  # 限制最大对话轮次
            )
            
            # 获取最终回复
            final_reply = self.response_agent.chat_messages[self.user_proxy][-1]["content"]
            
            # 清理掉可能的TERMINATE标记
            if "TERMINATE" in final_reply:
                final_reply = final_reply.replace("TERMINATE", "").strip()
            
            # 收集所有对话历史作为思考过程
            self._extract_chat_history()
            
            return final_reply
            
        except Exception as e:
            print(f"生成回答时出错: {str(e)}")
            return f"抱歉，处理您的问题时出现了错误: {str(e)}" 