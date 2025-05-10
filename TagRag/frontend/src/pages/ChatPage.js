import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Spin, Switch, Typography, Space, Divider, message, Collapse, Tag, Select, Tooltip } from 'antd';
import { SendOutlined, CodeOutlined, InfoCircleOutlined, DatabaseOutlined, TagsOutlined as AntTagsOutlined, SnippetsOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import axios from 'axios';
// 导入代码结果显示组件
import CodeRAGResults from './CodeRAGResults';

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
        <div style={{ marginTop: '8px', marginBottom: '4px', fontSize: '13px' }}>
            <Text strong style={{ fontSize: '13px' }}><AntTagsOutlined /> 引用的标签: </Text>
            {tags.map(tag => (
                <Tag key={tag.id} color="blue" style={{ margin: '2px', fontSize: '12px' }}>
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
        <div style={{ marginTop: '8px', marginBottom: '8px', fontSize: '13px' }}>
            <Text strong style={{ fontSize: '13px' }}><SnippetsOutlined /> 引用的文档片段: </Text>
            <Collapse accordion size="small" bordered={false} style={{ marginTop: '4px', fontSize: '12px' }}>
                {excerpts.map((excerpt, index) => (
                    <Panel
                        header={
                            <Tooltip title={excerpt.content || '无内容'}>
                                <Text ellipsis style={{ maxWidth: 'calc(100% - 30px)', fontSize: '12px' }}>
                                    {`片段 ${index + 1}: ${excerpt.document_source || '未知来源'} (相关性: ${excerpt.score !== null && typeof excerpt.score !== 'undefined' ? excerpt.score.toFixed(2) : 'N/A'})`}
                                </Text>
                            </Tooltip>
                        }
                        key={excerpt.chunk_id || `excerpt-${index}`}
                        style={{ fontSize: '12px' }}
                    >
                        <div style={{ maxHeight: '150px', overflowY: 'auto', paddingRight: '10px', fontSize: '12px' }}>
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
                    referenced_excerpts: msg.referenced_excerpts || [],
                    code_snippets: msg.code_snippets || [] // 确保代码片段字段存在
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
    const [useCodeRetrieval, setUseCodeRetrieval] = useState(false); // 新增状态：是否启用代码检索
    const [useTagRag, setUseTagRag] = useState(true); // Default to true for TagRAG
    const [thinkingProcess, setThinkingProcess] = useState({}); // Store thinking process per message index
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [kbLoading, setKbLoading] = useState(false);
    const [agentPrompts, setAgentPrompts] = useState([]);
    const [repositories, setRepositories] = useState([]); // 新增：代码仓库列表
    const [selectedRepository, setSelectedRepository] = useState(null); // 新增：选择的代码仓库
    const [repoLoading, setRepoLoading] = useState(false); // 新增：仓库加载状态
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

    // 获取代码仓库列表
    const fetchRepositories = async () => {
        setRepoLoading(true);
        try {
            const response = await axios.get('/code/repositories');
            setRepositories(response.data || []);
            if (response.data && response.data.length > 0) {
                setSelectedRepository(response.data[0].id);
            }
        } catch (error) {
            console.error('获取代码仓库列表失败:', error);
            message.error('获取代码仓库列表失败');
        } finally {
            setRepoLoading(false);
        }
    };

    // 组件加载时获取知识库和代码仓库列表
    useEffect(() => {
        fetchKnowledgeBases();
        fetchRepositories(); // 添加获取代码仓库的调用
    }, []);

    // 当知识库变化时，加载对应的提示词
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchAgentPromptsForKnowledgeBase(selectedKnowledgeBase);

            // 找出选中知识库的名称
            const selectedKbName = knowledgeBases.find(kb => kb.id === selectedKnowledgeBase)?.name || 'Unknown';

            // 使用非侵入式提示框而非系统消息
            message.info(`已切换到知识库: ${selectedKbName}`);

            console.log(`已切换到知识库ID: ${selectedKnowledgeBase}`);
        } else if (knowledgeBases.length > 0 && !selectedKnowledgeBase) {
            // Auto-select first KB if none selected and KBs are loaded
            setSelectedKnowledgeBase(knowledgeBases[0].id);
            console.log(`自动选择第一个知识库: ${knowledgeBases[0].id}`);
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
                use_code_retrieval: useCodeRetrieval, // 添加代码检索参数
                repository_id: useCodeRetrieval ? selectedRepository : null, // 仅在启用代码检索时传递仓库ID
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
                referenced_excerpts: response.data.referenced_excerpts || [],
                code_snippets: response.data.code_snippets || [] // 添加代码片段
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
                referenced_excerpts: [],
                code_snippets: []
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
        // This is a helper function that will be called when rendering a specific thinking process
        // and can operate on the 'processArray' passed to it.
        // Ensure unique keys for Collapse Panels if multiple thinking processes are on page.
        return (
            <Collapse.Panel header="查看思考过程" key={`tp-${messageKey}`} style={{ fontSize: '12px' }}>
                <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', fontSize: '11px' }}>
                    {processArray.map((step, idx) => {
                        // ... (logic to format each step, as previously designed) ...
                        // simplified for this diff
                        return <div key={idx} style={{ color: step.error ? 'red' : 'inherit', marginBottom: '4px', paddingBottom: '4px', borderBottom: '1px dashed #eee', fontSize: '11px' }}>
                            <strong>{step.agent || step.task || step.operation || 'Log'}:</strong> {step.step_info || step.info || step.error || step.warning || JSON.stringify(step)}
                            {step.details && <div style={{ fontSize: '10px', color: '#777' }}>Details: {typeof step.details === 'object' ? JSON.stringify(step.details) : step.details}</div>}
                            {/* Add more detailed rendering for specific keys if needed */}
                        </div>;
                    })}
                </pre>
            </Collapse.Panel>
        );
    };

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 64px)',
            borderRadius: '12px',
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)',
            padding: '0',
            overflow: 'hidden',
            background: '#fff'
        }}>

            {/* Header Section - 更现代的设计 */}
            <div style={{
                padding: '20px 24px',
                borderBottom: '1px solid #f0f0f0',
                background: 'linear-gradient(to right, #f7f9fc, #eef2f7)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap'
            }}>
                <Title level={4} style={{ margin: 0, color: '#4267B2', fontWeight: '600' }}>智能问答</Title>
                <Space wrap style={{ marginTop: '0' }}>
                    <Select
                        loading={kbLoading}
                        value={selectedKnowledgeBase}
                        style={{
                            width: 200,
                            borderRadius: '8px',
                            boxShadow: '0 2px 6px rgba(0, 0, 0, 0.03)'
                        }}
                        onChange={setSelectedKnowledgeBase}
                        placeholder="选择知识库"
                        dropdownStyle={{ borderRadius: '8px' }}
                    >
                        {knowledgeBases.map(kb => (
                            <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                        ))}
                    </Select>

                    {/* 添加代码仓库选择下拉框 */}
                    {useCodeRetrieval && (
                        <Select
                            loading={repoLoading}
                            value={selectedRepository}
                            style={{
                                width: 200,
                                borderRadius: '8px',
                                boxShadow: '0 2px 6px rgba(0, 0, 0, 0.03)'
                            }}
                            onChange={setSelectedRepository}
                            placeholder="选择代码仓库"
                            dropdownStyle={{ borderRadius: '8px' }}
                        >
                            {repositories.map(repo => (
                                <Option key={repo.id} value={repo.id}>{repo.name}</Option>
                            ))}
                        </Select>
                    )}

                    {/* 修改代码分析开关，使其独立于TagRAG */}
                    <Switch
                        checkedChildren={<><CodeOutlined /> 代码检索</>}
                        unCheckedChildren={<><CodeOutlined /> 代码检索</>}
                        checked={useCodeRetrieval}
                        onChange={(checked) => {
                            setUseCodeRetrieval(checked);
                            // 如果启用了代码检索但没有选择仓库，提示用户
                            if (checked && (!repositories.length || !selectedRepository)) {
                                message.warning('请确保选择了代码仓库');
                                // 首次打开时自动获取仓库列表
                                if (!repositories.length) {
                                    fetchRepositories();
                                }
                            }
                        }}
                    />

                    {/* 保留原有代码分析开关，但仅在非TagRAG模式下可用 */}
                    <Switch
                        checkedChildren={<><CodeOutlined /> 代码分析</>}
                        unCheckedChildren={<><CodeOutlined /> 代码分析</>}
                        checked={useCodeAnalysis}
                        onChange={setUseCodeAnalysis}
                        disabled={useTagRag}
                    />

                    <Switch
                        checkedChildren={<><AntTagsOutlined /> TagRAG</>}
                        unCheckedChildren={<><AntTagsOutlined /> TagRAG</>}
                        checked={useTagRag}
                        onChange={(checked) => {
                            setUseTagRag(checked);
                            if (checked) setUseCodeAnalysis(false);
                            // 代码检索功能与TagRAG模式独立
                        }}
                    />
                    <Button
                        onClick={clearChatHistory}
                        danger
                        style={{
                            borderRadius: '8px',
                            boxShadow: '0 2px 6px rgba(0, 0, 0, 0.03)'
                        }}
                    >
                        清除聊天记录
                    </Button>
                </Space>
            </div>

            {/* Chat Messages Area - 更现代的聊天气泡设计 */}
            <div style={{
                flexGrow: 1,
                overflowY: 'auto',
                padding: '16px 20px',
                background: '#f7f9fc'
            }}>
                {messages.map((msg, index) => (
                    <div
                        key={index}
                        style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                            marginBottom: '20px',
                            width: '100%'
                        }}
                    >
                        <div style={{
                            display: 'flex',
                            maxWidth: '80%',
                            width: 'auto'
                        }}>
                            {msg.sender === 'ai' && (
                                <div style={{
                                    width: '36px',
                                    height: '36px',
                                    borderRadius: '50%',
                                    backgroundColor: '#4267B2',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    marginRight: '12px',
                                    fontSize: '16px',
                                    color: 'white',
                                    fontWeight: 'bold',
                                    flexShrink: 0,
                                    minWidth: '36px'
                                }}>
                                    T
                                </div>
                            )}
                            <div
                                style={{
                                    padding: '14px 18px',
                                    borderRadius: msg.sender === 'user'
                                        ? '18px 18px 0 18px'
                                        : '18px 18px 18px 0',
                                    backgroundColor: msg.sender === 'user' ? '#4267B2' : 'white',
                                    color: msg.sender === 'user' ? 'white' : '#333',
                                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
                                    wordWrap: 'break-word',
                                    marginBottom: '4px',
                                    flexGrow: 1,
                                    overflow: 'hidden',
                                    width: 'auto'
                                }}
                            >
                                <ReactMarkdown
                                    components={{
                                        code({ node, inline, className, children, ...props }) {
                                            const match = /language-(\\w+)/.exec(className || '')
                                            return !inline && match ? (
                                                <pre style={{
                                                    background: '#2d2d2d',
                                                    color: '#f8f8f2',
                                                    padding: '10px',
                                                    borderRadius: '8px',
                                                    overflowX: 'auto',
                                                    marginTop: '8px',
                                                    marginBottom: '8px',
                                                    width: '100%',
                                                    fontSize: '13px'
                                                }} {...props}>
                                                    {String(children).replace(/\\n$/, '')}
                                                </pre>
                                            ) : (
                                                <code style={{
                                                    background: msg.sender === 'user' ? 'rgba(255,255,255,0.2)' : '#f0f2f5',
                                                    padding: '2px 4px',
                                                    borderRadius: '4px',
                                                    fontFamily: 'monospace',
                                                    wordBreak: 'break-word',
                                                    fontSize: '13px'
                                                }} className={className} {...props}>
                                                    {children}
                                                </code>
                                            )
                                        }
                                    }}
                                    className="markdown-content"
                                >
                                    {msg.content}
                                </ReactMarkdown>
                            </div>
                            {msg.sender === 'user' && (
                                <div style={{
                                    width: '36px',
                                    height: '36px',
                                    borderRadius: '50%',
                                    backgroundColor: '#6c757d',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    marginLeft: '12px',
                                    fontSize: '16px',
                                    color: 'white',
                                    fontWeight: 'bold',
                                    flexShrink: 0,
                                    minWidth: '36px'
                                }}>
                                    U
                                </div>
                            )}
                        </div>

                        <div style={{
                            fontSize: '11px',
                            color: '#9aa0a6',
                            marginTop: '4px',
                            marginLeft: msg.sender === 'ai' ? '48px' : '0',
                            marginRight: msg.sender === 'user' ? '48px' : '0'
                        }}>
                            {new Date(msg.timestamp).toLocaleTimeString()}
                        </div>

                        {/* Render Referenced Tags and Excerpts for AI messages */}
                        {msg.sender === 'ai' && (
                            <div style={{
                                maxWidth: '80%',
                                marginLeft: '48px',
                                marginTop: '6px',
                                fontSize: '13px'
                            }}>
                                <ReferencedTags tags={msg.referenced_tags} />
                                <ReferencedExcerpts excerpts={msg.referenced_excerpts} />
                                {/* 添加代码片段展示 */}
                                {msg.code_snippets && msg.code_snippets.length > 0 && (
                                    <CodeRAGResults codeSnippets={msg.code_snippets} />
                                )}
                            </div>
                        )}

                        {/* Thinking Process Collapse for AI messages */}
                        {msg.sender === 'ai' && msg.hasThinkingProcess && thinkingProcess[index] && (
                            <Collapse
                                ghost
                                style={{
                                    maxWidth: '80%',
                                    marginTop: '6px',
                                    marginLeft: '48px',
                                    borderRadius: '8px',
                                    overflow: 'hidden',
                                    fontSize: '13px'
                                }}
                            >
                                {renderThinkingProcess(thinkingProcess[index], `msg-${index}`)}
                            </Collapse>
                        )}
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            {/* Input Area - 更现代的输入框设计 */}
            <div style={{
                display: 'flex',
                borderTop: '1px solid #f0f0f0',
                padding: '12px 20px',
                background: 'white'
            }}>
                <TextArea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="输入您的问题..."
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    style={{
                        marginRight: '12px',
                        borderRadius: '18px',
                        padding: '10px 16px',
                        resize: 'none',
                        boxShadow: '0 2px 6px rgba(0, 0, 0, 0.05)',
                        border: '1px solid #e0e5eb',
                        fontSize: '14px'
                    }}
                    disabled={loading}
                />
                <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={sendMessage}
                    loading={loading}
                    disabled={!selectedKnowledgeBase && kbLoading}
                    style={{
                        borderRadius: '50%',
                        width: '48px',
                        height: '48px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 4px 12px rgba(66, 103, 178, 0.2)'
                    }}
                />
            </div>
        </div>
    );
};

export default ChatPage; 