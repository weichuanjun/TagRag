import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Spin, Switch, Typography, Space, Divider, message, Collapse, Tag, Select, Tooltip } from 'antd';
import { SendOutlined, CodeOutlined, InfoCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import axios from 'axios';

const { TextArea } = Input;
const { Title, Text } = Typography;
const { Panel } = Collapse;
const { Option } = Select;

// 聊天缓存的键名
const CHAT_CACHE_KEY = 'rag_agent_chat_cache';

const ChatPage = () => {
    // 从localStorage加载缓存的聊天记录
    const loadCachedMessages = () => {
        try {
            const cachedData = localStorage.getItem(CHAT_CACHE_KEY);
            if (cachedData) {
                const parsedData = JSON.parse(cachedData);
                return parsedData.messages || [];
            }
        } catch (error) {
            console.error('加载聊天缓存失败:', error);
        }
        return [];
    };

    const [messages, setMessages] = useState(loadCachedMessages);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [useCodeAnalysis, setUseCodeAnalysis] = useState(false);
    const [thinkingProcess, setThinkingProcess] = useState([]);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [kbLoading, setKbLoading] = useState(false);
    const [agentPrompts, setAgentPrompts] = useState([]);
    const messagesEndRef = useRef(null);

    // 缓存聊天记录到localStorage
    useEffect(() => {
        try {
            const cacheData = {
                messages,
                lastUpdated: new Date().toISOString()
            };
            localStorage.setItem(CHAT_CACHE_KEY, JSON.stringify(cacheData));
        } catch (error) {
            console.error('缓存聊天记录失败:', error);
        }
    }, [messages]);

    // 获取知识库列表
    const fetchKnowledgeBases = async () => {
        setKbLoading(true);
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data || []);
            if (response.data && response.data.length > 0) {
                setSelectedKnowledgeBase(response.data[0].id);
            }
        } catch (error) {
            console.error('获取知识库列表失败:', error);
            message.error('获取知识库列表失败');
        } finally {
            setKbLoading(false);
        }
    };

    // 组件加载时获取知识库列表
    useEffect(() => {
        fetchKnowledgeBases();
    }, []);

    // 当知识库变化时，加载对应的提示词
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchAgentPromptsForKnowledgeBase(selectedKnowledgeBase);
        }
    }, [selectedKnowledgeBase]);

    // 清除聊天记录
    const clearChatHistory = () => {
        setMessages([]);
        setThinkingProcess([]);
        localStorage.removeItem(CHAT_CACHE_KEY);
        message.success('聊天记录已清除');
    };

    // 获取知识库的关联提示词
    const fetchAgentPromptsForKnowledgeBase = async (knowledgeBaseId) => {
        try {
            const response = await axios.get(`/agent-prompts/for-kb/${knowledgeBaseId}`);
            console.log('已加载知识库关联的提示词:', response.data);
            setAgentPrompts(response.data);
        } catch (error) {
            console.error('获取知识库提示词失败:', error);
        }
    };

    // 滚动到底部
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // 发送消息
    const sendMessage = async () => {
        if (!input.trim()) return;

        // 添加用户消息到聊天
        const userMessage = {
            content: input,
            sender: 'user',
            timestamp: new Date().toISOString()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setLoading(true);
        setThinkingProcess([]); // 清空上次的思考过程

        try {
            // 获取当前知识库相关的提示词
            const promptConfigs = {};
            if (agentPrompts.length > 0) {
                // 为每种Agent类型找到默认的提示词
                agentPrompts.forEach(prompt => {
                    if (prompt.is_default) {
                        promptConfigs[prompt.agent_type] = prompt.prompt_template;
                    }
                });
            }

            // 添加调试日志
            console.log('使用的提示词配置:', promptConfigs);

            // 发送请求到后端
            const response = await axios.post('/ask', {
                query: input,
                knowledge_base_id: selectedKnowledgeBase,
                use_code_analysis: useCodeAnalysis,
                prompt_configs: promptConfigs // 发送提示词配置
            });

            // 获取思考过程
            if (response.data.thinking_process) {
                setThinkingProcess(response.data.thinking_process);
            }

            // 添加AI回复到聊天
            const aiMessage = {
                content: response.data.answer,
                sender: 'ai',
                timestamp: new Date().toISOString(),
                hasThinkingProcess: response.data.thinking_process && response.data.thinking_process.length > 0
            };

            setMessages(prev => [...prev, aiMessage]);
        } catch (error) {
            console.error('Error sending message:', error);
            message.error('发送消息失败，请重试');

            // 添加错误消息
            const errorMessage = {
                content: '抱歉，发生了错误，无法获取回答。请稍后重试。',
                sender: 'ai',
                timestamp: new Date().toISOString()
            };

            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setLoading(false);
        }
    };

    // 处理输入框按键事件（回车发送）
    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    // 渲染思考过程
    const renderThinkingProcess = (index) => {
        if (!thinkingProcess || thinkingProcess.length === 0) return null;

        return (
            <Collapse
                ghost
                style={{
                    marginTop: '8px',
                    background: '#f9f9f9',
                    borderRadius: '4px',
                    border: '1px solid #eee'
                }}
            >
                <Panel
                    header={
                        <Space>
                            <InfoCircleOutlined />
                            <span>查看思考过程</span>
                            {useCodeAnalysis && <Tag color="blue">代码分析</Tag>}
                        </Space>
                    }
                    key="1"
                >
                    <div className="thinking-process" style={{ maxHeight: '400px', overflow: 'auto' }}>
                        {thinkingProcess.map((step, idx) => (
                            <div key={idx} style={{ marginBottom: '16px', padding: '8px', borderBottom: '1px solid #f0f0f0' }}>
                                <Text strong>{step.sender} → {step.recipient}:</Text>
                                <div style={{
                                    marginTop: '4px',
                                    whiteSpace: 'pre-wrap',
                                    background: '#f5f5f5',
                                    padding: '8px',
                                    borderRadius: '4px'
                                }}>
                                    <ReactMarkdown>{step.content}</ReactMarkdown>
                                </div>
                            </div>
                        ))}
                    </div>
                </Panel>
            </Collapse>
        );
    };

    return (
        <div className="chat-container">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Title level={4}>智能助手</Title>
                <Space>
                    <Text>选择知识库:</Text>
                    <Select
                        style={{ width: 200 }}
                        loading={kbLoading}
                        value={selectedKnowledgeBase}
                        onChange={setSelectedKnowledgeBase}
                        placeholder="选择知识库"
                    >
                        {knowledgeBases.map(kb => (
                            <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                        ))}
                    </Select>
                    <Text>启用代码分析</Text>
                    <Switch
                        checked={useCodeAnalysis}
                        onChange={setUseCodeAnalysis}
                        checkedChildren={<CodeOutlined />}
                    />
                    <Tooltip title="启用后，系统将分析知识库中的代码，您可以直接询问代码结构和功能">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                    </Tooltip>
                    <Button
                        danger
                        type="text"
                        onClick={clearChatHistory}
                        disabled={messages.length === 0}
                    >
                        清除记录
                    </Button>
                </Space>
            </div>

            <Divider />

            <div className="message-list" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {messages.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <Text type="secondary">发送消息开始对话</Text>
                    </div>
                ) : (
                    messages.map((msg, index) => (
                        <div key={index}>
                            <div
                                className={msg.sender === 'user' ? 'user-message' : 'ai-message'}
                                style={{
                                    padding: '12px 16px',
                                    borderRadius: '8px',
                                    maxWidth: '80%',
                                    alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                                    marginLeft: msg.sender === 'user' ? 'auto' : '0',
                                    backgroundColor: msg.sender === 'user' ? '#1890ff' : '#f5f5f5',
                                    color: msg.sender === 'user' ? 'white' : 'inherit',
                                }}
                            >
                                {msg.sender === 'user' ? (
                                    <div>{msg.content}</div>
                                ) : (
                                    <div className="markdown-content">
                                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                                    </div>
                                )}
                            </div>
                            {msg.sender === 'ai' && msg.hasThinkingProcess && renderThinkingProcess(index)}
                        </div>
                    ))
                )}

                {loading && (
                    <div style={{ display: 'flex', justifyContent: 'center', padding: '20px 0' }}>
                        <Spin tip="思考中..." />
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            <div className="message-input" style={{ marginTop: '20px' }}>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <TextArea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder="输入你的问题..."
                        autoSize={{ minRows: 1, maxRows: 4 }}
                        disabled={loading}
                    />
                    <Button
                        type="primary"
                        icon={<SendOutlined />}
                        onClick={sendMessage}
                        disabled={!input.trim() || loading}
                    />
                </div>
            </div>
        </div>
    );
};

export default ChatPage; 