import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Spin, Switch, Typography, Space, Divider, message, Collapse, Tag, Select, Tooltip } from 'antd';
import { SendOutlined, CodeOutlined, InfoCircleOutlined, DatabaseOutlined, TagsOutlined as AntTagsOutlined, SnippetsOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import axios from 'axios';

const { TextArea } = Input;
const { Title, Text } = Typography;
const { Panel } = Collapse;
const { Option } = Select;

// 聊天缓存的键名
const CHAT_CACHE_KEY = 'rag_agent_chat_cache';

// --- Helper Components for Referenced Data ---
const ReferencedTags = ({ tags }) => {
    if (!tags || tags.length === 0) {
        return null;
    }
    return (
        <div style={{ marginTop: '10px', marginBottom: '5px' }}>
            <Text strong><AntTagsOutlined /> 引用的标签: </Text>
            {tags.map(tag => (
                <Tag key={tag.id} color="blue" style={{ margin: '2px' }}>
                    {tag.name}
                </Tag>
            ))}
        </div>
    );
};

const ReferencedExcerpts = ({ excerpts }) => {
    if (!excerpts || excerpts.length === 0) {
        return null;
    }
    return (
        <div style={{ marginTop: '10px', marginBottom: '10px' }}>
            <Text strong><SnippetsOutlined /> 引用的文档片段: </Text>
            <Collapse accordion size="small" bordered={false} style={{ marginTop: '5px' }}>
                {excerpts.map((excerpt, index) => (
                    <Panel
                        header={
                            <Tooltip title={excerpt.content || '无内容'}>
                                <Text ellipsis style={{ maxWidth: 'calc(100% - 30px)' }}>
                                    {`片段 ${index + 1}: ${excerpt.document_source || '未知来源'} (相关性: ${excerpt.score !== null && typeof excerpt.score !== 'undefined' ? excerpt.score.toFixed(2) : 'N/A'})`}
                                </Text>
                            </Tooltip>
                        }
                        key={excerpt.chunk_id || `excerpt-${index}`}
                        style={{ fontSize: '12px' }}
                    >
                        <div style={{ maxHeight: '150px', overflowY: 'auto', paddingRight: '10px' }}>
                            <ReactMarkdown>{excerpt.content || '无内容'}</ReactMarkdown>
                        </div>
                        {excerpt.page_number && <Text type="secondary" style={{ fontSize: '11px' }}>页码: {excerpt.page_number}</Text>}
                    </Panel>
                ))}
            </Collapse>
        </div>
    );
};
// --- End Helper Components ---

const ChatPage = () => {
    // 从localStorage加载缓存的聊天记录
    const loadCachedMessages = () => {
        try {
            const cachedData = localStorage.getItem(CHAT_CACHE_KEY);
            if (cachedData) {
                const parsedData = JSON.parse(cachedData);
                // Ensure all messages have the new fields, defaulting if not present
                return (parsedData.messages || []).map(msg => ({
                    ...msg,
                    referenced_tags: msg.referenced_tags || [],
                    referenced_excerpts: msg.referenced_excerpts || []
                }));
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
    const [useTagRag, setUseTagRag] = useState(true); // Default to true for TagRAG
    const [thinkingProcess, setThinkingProcess] = useState({}); // Store thinking process per message index
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [kbLoading, setKbLoading] = useState(false);
    const [agentPrompts, setAgentPrompts] = useState([]);
    const messagesEndRef = useRef(null);

    // 缓存聊天记录到localStorage
    useEffect(() => {
        try {
            const cacheData = {
                messages, // messages now include referenced_tags and referenced_excerpts
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
        } else if (knowledgeBases.length > 0 && !selectedKnowledgeBase) {
            // Auto-select first KB if none selected and KBs are loaded
            setSelectedKnowledgeBase(knowledgeBases[0].id);
        }
    }, [selectedKnowledgeBase, knowledgeBases]);

    // 清除聊天记录
    const clearChatHistory = () => {
        setMessages([]);
        setThinkingProcess({}); // Clear all thinking processes
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
        if (!selectedKnowledgeBase) {
            message.error('请先选择一个知识库！');
            return;
        }

        const userMessage = {
            content: input,
            sender: 'user',
            timestamp: new Date().toISOString()
        };

        const currentMessageIndex = messages.length; // Index for the upcoming AI message

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setLoading(true);
        // setThinkingProcess([]); // Clear only the general thinking process, or manage per message

        try {
            const promptConfigs = {};
            if (agentPrompts.length > 0) {
                agentPrompts.forEach(prompt => {
                    if (prompt.is_default) {
                        promptConfigs[prompt.agent_type] = prompt.prompt_template;
                    }
                });
            }
            console.log('使用的提示词配置:', promptConfigs);

            const payload = {
                query: userMessage.content, // Use content from userMessage for consistency
                knowledge_base_id: selectedKnowledgeBase,
                use_code_analysis: useCodeAnalysis,
                use_tag_rag: useTagRag,
                prompt_configs: promptConfigs
            };

            // Use /chat/tag-rag if useTagRag is true, otherwise /ask (or your general endpoint)
            const endpoint = useTagRag ? '/chat/tag-rag' : '/ask';
            console.log(`Sending to endpoint: ${endpoint} with payload:`, payload);

            const response = await axios.post(endpoint, payload);

            let thinkingProcessForMessage = [];
            if (response.data.thinking_process) {
                thinkingProcessForMessage = response.data.thinking_process;
            }
            setThinkingProcess(prev => ({ ...prev, [currentMessageIndex + 1]: thinkingProcessForMessage }));


            const aiMessage = {
                content: response.data.answer,
                sender: 'ai',
                timestamp: new Date().toISOString(),
                hasThinkingProcess: thinkingProcessForMessage && thinkingProcessForMessage.length > 0,
                // Add new fields from TagRAGChatResponse
                referenced_tags: response.data.referenced_tags || [],
                referenced_excerpts: response.data.referenced_excerpts || []
            };

            setMessages(prev => [...prev, aiMessage]);
        } catch (error) {
            console.error('Error sending message:', error);
            message.error('发送消息失败，请重试');
            const errorMessage = {
                content: '抱歉，发生了错误，无法获取回答。请检查后端服务是否运行或查看控制台错误。',
                sender: 'ai',
                timestamp: new Date().toISOString(),
                referenced_tags: [],
                referenced_excerpts: []
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
    const renderThinkingProcess = (processArray, messageKey) => {
        if (!processArray || processArray.length === 0) return null;
        // ... (rest of renderThinkingProcess logic remains largely the same but operates on processArray) ...
        // For brevity, assuming the internal mapping logic of renderThinkingProcess is correct
        // and can operate on the 'processArray' passed to it.
        // Ensure unique keys for Collapse Panels if multiple thinking processes are on page.
        return (
            <Collapse.Panel header="查看思考过程" key={`tp-${messageKey}`}>
                <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', fontSize: '12px' }}>
                    {processArray.map((step, idx) => {
                        // ... (logic to format each step, as previously designed) ...
                        // simplified for this diff
                        return <div key={idx} style={{ color: step.error ? 'red' : 'inherit', marginBottom: '5px', paddingBottom: '5px', borderBottom: '1px dashed #eee' }}>
                            <strong>{step.agent || step.task || step.operation || 'Log'}:</strong> {step.step_info || step.info || step.error || step.warning || JSON.stringify(step)}
                            {step.details && <div style={{ fontSize: '11px', color: '#777' }}>Details: {typeof step.details === 'object' ? JSON.stringify(step.details) : step.details}</div>}
                            {/* Add more detailed rendering for specific keys if needed */}
                        </div>;
                    })}
                </pre>
            </Collapse.Panel>
        );
    };

    return (
        <div style={{
            display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)', // Adjust based on your Layout
            border: '1px solid #d9d9d9', borderRadius: '4px', padding: '20px'
        }}>

            {/* Header Section */}
            <div style={{ marginBottom: '20px', paddingBottom: '20px', borderBottom: '1px solid #f0f0f0' }}>
                <Title level={4} style={{ margin: 0 }}>智能问答</Title>
                <Space wrap style={{ marginTop: '10px' }}>
                    <Tooltip title="选择一个知识库进行问答">
                        <Select
                            loading={kbLoading}
                            value={selectedKnowledgeBase}
                            style={{ width: 200 }}
                            onChange={setSelectedKnowledgeBase}
                            placeholder="选择知识库"
                        >
                            {knowledgeBases.map(kb => (
                                <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                            ))}
                        </Select>
                    </Tooltip>
                    <Switch
                        checkedChildren={<><CodeOutlined /> 代码分析</>}
                        unCheckedChildren={<><CodeOutlined /> 代码分析</>}
                        checked={useCodeAnalysis}
                        onChange={setUseCodeAnalysis}
                        disabled={useTagRag} // Disable if TagRAG is active
                    />
                    <Switch
                        checkedChildren={<><AntTagsOutlined /> TagRAG</>}
                        unCheckedChildren={<><AntTagsOutlined /> TagRAG</>}
                        checked={useTagRag}
                        onChange={(checked) => {
                            setUseTagRag(checked);
                            if (checked) setUseCodeAnalysis(false); // Ensure code analysis is off if TagRAG is on
                        }}
                    />
                    <Button onClick={clearChatHistory} danger>清除聊天记录</Button>
                </Space>
            </div>

            {/* Chat Messages Area */}
            <div style={{ flexGrow: 1, overflowY: 'auto', marginBottom: '20px', paddingRight: '10px' }}>
                {messages.map((msg, index) => (
                    <div
                        key={index}
                        style={{
                            marginBottom: '15px',
                            textAlign: msg.sender === 'user' ? 'right' : 'left',
                        }}
                    >
                        <div
                            style={{
                                display: 'inline-block',
                                padding: '10px 15px',
                                borderRadius: '15px',
                                backgroundColor: msg.sender === 'user' ? '#1890ff' : '#f0f0f0',
                                color: msg.sender === 'user' ? 'white' : 'black',
                                maxWidth: '70%',
                                wordWrap: 'break-word',
                            }}
                        >
                            <ReactMarkdown
                                components={{
                                    // Customize rendering if needed, e.g., for code blocks
                                    code({ node, inline, className, children, ...props }) {
                                        const match = /language-(\\w+)/.exec(className || '')
                                        return !inline && match ? (
                                            // Add syntax highlighting here if you want
                                            <pre style={{ background: '#2d2d2d', color: '#f8f8f2', padding: '10px', borderRadius: '5px', overflowX: 'auto' }} {...props}>{String(children).replace(/\\n$/, '')}</pre>
                                        ) : (
                                            <code className={className} {...props}>
                                                {children}
                                            </code>
                                        )
                                    }
                                }}
                            >
                                {msg.content}
                            </ReactMarkdown>
                        </div>
                        <div style={{ fontSize: '11px', color: '#aaa', marginTop: '3px' }}>
                            {new Date(msg.timestamp).toLocaleTimeString()}
                        </div>

                        {/* Render Referenced Tags and Excerpts for AI messages */}
                        {msg.sender === 'ai' && (
                            <div style={{
                                textAlign: 'left', // Ensure these are left-aligned under AI message
                                maxWidth: '70%', // Match message width
                                marginLeft: msg.sender === 'user' ? 'auto' : '0', // Align with AI bubble
                                marginRight: msg.sender === 'user' ? '0' : 'auto' // Align with AI bubble
                            }}>
                                <ReferencedTags tags={msg.referenced_tags} />
                                <ReferencedExcerpts excerpts={msg.referenced_excerpts} />
                            </div>
                        )}

                        {/* Thinking Process Collapse for AI messages */}
                        {msg.sender === 'ai' && msg.hasThinkingProcess && thinkingProcess[index] && (
                            <Collapse ghost style={{
                                maxWidth: '70%', marginTop: '5px',
                                marginLeft: msg.sender === 'user' ? 'auto' : '0',
                                marginRight: msg.sender === 'user' ? '0' : 'auto'
                            }}>
                                {renderThinkingProcess(thinkingProcess[index], `msg-${index}`)}
                            </Collapse>
                        )}
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div style={{ display: 'flex', borderTop: '1px solid #f0f0f0', paddingTop: '15px' }}>
                <TextArea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="输入您的问题..."
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    style={{ marginRight: '10px' }}
                    disabled={loading}
                />
                <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={sendMessage}
                    loading={loading}
                    disabled={!selectedKnowledgeBase && kbLoading}
                >
                    发送
                </Button>
            </div>
        </div>
    );
};

export default ChatPage; 