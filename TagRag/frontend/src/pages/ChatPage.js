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

// 新增一个实时处理信息显示组件
const ProcessingInfoDisplay = ({ processingInfos }) => {
    if (!processingInfos || processingInfos.length === 0) {
        return null;
    }

    // 只显示最新的3条信息
    const displayInfos = processingInfos.slice(0, 3);

    return (
        <div style={{
            position: 'absolute',
            bottom: '76px', // 位于输入框上方，稍微调整位置
            left: '50%',
            transform: 'translateX(-50%)',
            width: '85%',
            maxWidth: '800px',
            padding: '12px 16px',
            backgroundColor: 'rgba(247, 249, 252, 0.95)',
            borderRadius: '12px',
            boxShadow: '0 3px 10px rgba(0, 0, 0, 0.08)',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(230, 235, 245, 0.9)',
            zIndex: 100,
            transition: 'all 0.3s ease-in-out',
            opacity: 0.95
        }}>
            <div style={{ textAlign: 'center', marginBottom: '8px' }}>
                <Text type="secondary" style={{ fontSize: '12px', fontWeight: '500', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span className="dot-flashing" style={{ marginRight: '8px' }}></span>
                    处理中...
                </Text>
            </div>
            {displayInfos.map((info, index) => (
                <div
                    key={index}
                    className="processing-info-item"
                    style={{
                        fontSize: '12px',
                        lineHeight: '1.5',
                        padding: '4px 0',
                        color: '#444',
                        borderTop: index > 0 ? '1px dashed #eaeef5' : 'none',
                        marginTop: index > 0 ? '3px' : 0,
                        opacity: 1 - (index * 0.2), // 通过透明度创建层次感
                        transition: 'all 0.3s ease-in-out',
                    }}
                >
                    {info}
                </div>
            ))}
        </div>
    );
};

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

    // 简化处理信息状态
    const [processingInfos, setProcessingInfos] = useState([]);
    const [processingInfoTimer, setProcessingInfoTimer] = useState(null);

    // 添加临时消息ID状态，用于在收到最终回复时替换
    const [tempMessageId, setTempMessageId] = useState(null);

    // 添加WebSocket连接状态
    const [wsConnection, setWsConnection] = useState(null);

    // 添加用户滚动监听状态
    const [userScrolled, setUserScrolled] = useState(false);
    const chatContainerRef = useRef(null);

    // 设置一个状态标记是否应该滚动
    const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

    // 跟踪用户是否正在手动滚动
    const [userScrolling, setUserScrolling] = useState(false);
    let scrollTimeout;

    const handleScrollStart = () => {
        setUserScrolling(true);
        clearTimeout(scrollTimeout);
    };

    const handleScrollEnd = () => {
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
            setUserScrolling(false);
        }, 1000); // 1秒后认为用户停止滚动
    };

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
        console.log('ChatPage: fetchKnowledgeBases CALLED');
        setKbLoading(true);
        try {
            const response = await axios.get('/knowledge-bases', {
                headers: {
                    'ngrok-skip-browser-warning': 'true'
                }
            });
            console.log('Response from /knowledge-bases (ChatPage):', response.data);
            if (Array.isArray(response.data)) {
                setKnowledgeBases(response.data);
                console.log('ChatPage: setKnowledgeBases with ARRAY:', response.data);
                // setSelectedKnowledgeBase 的逻辑最好在另一个 useEffect 中处理，监听 knowledgeBases 的变化
                // if (response.data.length > 0 && !selectedKnowledgeBase) {
                // setSelectedKnowledgeBase(response.data[0].id);
                // }
            } else {
                console.error('Error: /knowledge-bases (ChatPage) did not return an array:', response.data);
                setKnowledgeBases([]);
                console.log('ChatPage: setKnowledgeBases with EMPTY ARRAY due to non-array response.');
                message.error('获取知识库列表失败: 响应格式不正确');
            }
        } catch (error) {
            console.error('获取知识库列表失败:', error);
            message.error('获取知识库列表失败');
            setKnowledgeBases([]);
            console.log('ChatPage: setKnowledgeBases with EMPTY ARRAY due to CATCH.');
        } finally {
            setKbLoading(false);
        }
    };

    // 获取代码仓库列表
    const fetchRepositories = async () => {
        setRepoLoading(true);
        try {
            const response = await axios.get('/code/repositories', {
                headers: {
                    'ngrok-skip-browser-warning': 'true'
                }
            });
            setRepositories(response.data || []);
            if (response.data && response.data.length > 0) {
                // setSelectedRepository(response.data[0].id); // 自动选择逻辑也最好移到useEffect
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

    // 修改：当 knowledgeBases 加载或变化时，处理 selectedKnowledgeBase
    useEffect(() => {
        if (knowledgeBases.length > 0 && !selectedKnowledgeBase) {
            setSelectedKnowledgeBase(knowledgeBases[0].id);
            console.log(`ChatPage: Auto-selected first KB: ${knowledgeBases[0].id}`);
        }
        // 如果 selectedKnowledgeBase 存在但已不在新的 knowledgeBases 列表中，也需要处理
        else if (selectedKnowledgeBase && knowledgeBases.length > 0 && !knowledgeBases.find(kb => kb.id === selectedKnowledgeBase)) {
            setSelectedKnowledgeBase(knowledgeBases[0].id); // 或者设为null，让用户重新选择
            console.log(`ChatPage: Selected KB ${selectedKnowledgeBase} not found in new list, auto-selected first KB: ${knowledgeBases[0].id}`);
        }
        else if (knowledgeBases.length === 0 && selectedKnowledgeBase) {
            setSelectedKnowledgeBase(null); // 如果知识库列表为空，清空选择
            console.log('ChatPage: Knowledge bases list is empty, clearing selected KB.');
        }
    }, [knowledgeBases, selectedKnowledgeBase]);

    // 修改：当 repositories 加载或变化时，处理 selectedRepository (如果需要自动选择)
    useEffect(() => {
        if (repositories.length > 0 && !selectedRepository) {
            setSelectedRepository(repositories[0].id);
            console.log(`ChatPage: Auto-selected first Repository: ${repositories[0].id}`);
        }
        // ... (类似上面对 knowledgeBases 的无效选择处理) ...
    }, [repositories, selectedRepository]);

    // 当知识库变化时，加载对应的提示词
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchAgentPromptsForKnowledgeBase(selectedKnowledgeBase);
            const selectedKbName = knowledgeBases.find(kb => kb.id === selectedKnowledgeBase)?.name || 'Unknown';
            message.info(`已切换到知识库: ${selectedKbName}`);
            console.log(`已切换到知识库ID: ${selectedKnowledgeBase}`);
        }
    }, [selectedKnowledgeBase]); // 移除了 knowledgeBases 依赖，因为上面的useEffect已经处理了它与selectedKnowledgeBase的关系

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

    // 处理滚动事件
    const handleScroll = () => {
        if (chatContainerRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
            // 检查是否接近底部 - 增加了50px的判断空间，避免过于敏感
            const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
            setShouldAutoScroll(isAtBottom);
        }
    };

    // 滚动到底部的函数 - 仅当消息添加且用户在底部时执行
    const scrollToBottom = (force = false) => {
        if ((shouldAutoScroll || force) && messagesEndRef.current && !userScrolling) {
            messagesEndRef.current.scrollIntoView({
                behavior: 'smooth',
                block: 'end'
            });
        }
    };

    // 在useEffect中添加滚动事件监听
    useEffect(() => {
        const chatContainer = chatContainerRef.current;
        if (chatContainer) {
            chatContainer.addEventListener('scroll', handleScroll);
            chatContainer.addEventListener('touchstart', handleScrollStart);
            chatContainer.addEventListener('mousedown', handleScrollStart);
            chatContainer.addEventListener('touchend', handleScrollEnd);
            chatContainer.addEventListener('mouseup', handleScrollEnd);
        }

        return () => {
            if (chatContainer) {
                chatContainer.removeEventListener('scroll', handleScroll);
                chatContainer.removeEventListener('touchstart', handleScrollStart);
                chatContainer.removeEventListener('mousedown', handleScrollStart);
                chatContainer.removeEventListener('touchend', handleScrollEnd);
                chatContainer.removeEventListener('mouseup', handleScrollEnd);
            }
            clearTimeout(scrollTimeout);
        };
    }, []);

    // 仅当消息更新且shouldAutoScroll为true时滚动到底部
    useEffect(() => {
        if (messages.length > 0) {
            // 检查最后一条消息是否来自系统或AI，以及是否是新添加的
            const lastMsg = messages[messages.length - 1];
            const isNewMessage = lastMsg && (lastMsg.sender === 'system' || lastMsg.sender === 'ai') && !userScrolling;

            if (isNewMessage) {
                scrollToBottom();
            }
        }
    }, [messages, shouldAutoScroll]);

    // 初始化WebSocket连接
    const initWebSocket = () => {
        // 为了保持简单，我们暂时使用模拟的信息
        // 实际中，应该连接后端WebSocket，例如：
        // const ws = new WebSocket('ws://localhost:8000/ws/processing-info');
        // setWsConnection(ws);
        // ws.onmessage = (event) => {
        //     const data = JSON.parse(event.data);
        //     if (data.type === 'processing_info') {
        //         setProcessingInfos(prev => [data.message, ...prev.slice(0, 2)]);
        //     }
        // };
        // 
        // return ws;
    };

    // 组件加载时初始化WebSocket
    useEffect(() => {
        // 实际使用中取消这行注释来连接WebSocket
        // const ws = initWebSocket();

        // 当组件卸载时关闭WebSocket连接
        return () => {
            if (wsConnection) {
                wsConnection.close();
            }
        };
    }, []);

    // 增加新的解析函数，从thinking_process提取更有意义的信息
    const extractStructuredLogs = (thinkingProcess) => {
        if (!thinkingProcess || !Array.isArray(thinkingProcess) || thinkingProcess.length === 0) {
            return [];
        }

        // 提取关键信息的正则模式
        const patterns = {
            tq: /T\(q\)|查询标签|标签生成|QueryTagGeneratorAgent/i,
            tags: /标签.*(创建|存在|识别|匹配)|生成.*标签|标签过滤器|TagFilterAgent/i,
            tcus: /T-CUS|评分|ExcerptAgent|分数/i,
            retrieval: /(检索|搜索|查询|获取).*(结果|块|文档)|ContextAssemblerAgent/i
        };

        // 对日志进行分类并提取重要信息
        return thinkingProcess
            .filter(log => {
                const content = (log.step_info || log.info || JSON.stringify(log));
                // 只保留包含关键信息的日志
                return Object.values(patterns).some(pattern => pattern.test(content));
            })
            .map(log => {
                const content = (log.step_info || log.info || JSON.stringify(log));
                // 识别日志类型
                let type = "信息";
                let icon = "📋";

                if (patterns.tq.test(content)) {
                    type = "查询标签分析";
                    icon = "🏷️";
                } else if (patterns.tags.test(content)) {
                    type = "标签匹配";
                    icon = "🔍";
                } else if (patterns.tcus.test(content)) {
                    type = "相关性评分";
                    icon = "⭐";
                } else if (patterns.retrieval.test(content)) {
                    type = "内容检索";
                    icon = "📚";
                }

                // 提取代理名称
                const agent = log.agent || "";

                return {
                    type,
                    icon,
                    agent,
                    content,
                    timestamp: new Date().toISOString()
                };
            }).reverse(); // 最新的在前面
    };

    // 更新发送消息函数
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

        // 添加用户消息
        setMessages(prev => [...prev, userMessage]);

        // 添加一个系统处理消息（显示正在处理）
        const processingMessage = {
            content: "正在处理您的请求...",
            sender: 'system',
            timestamp: new Date().toISOString(),
            processingInfos: useTagRag
                ? [{ tag: "系统", text: "正在分析您的查询...", type: "system" }]
                : [{ tag: "检索", text: "正在检索相关内容...", type: "retrieval" }],
            isProcessing: true
        };

        // 将处理消息添加到聊天流中
        setMessages(prev => [...prev, processingMessage]);
        // 记录临时消息ID用于后续更新
        const msgIndex = messages.length + 1; // +1 因为我们刚刚添加了用户消息
        setTempMessageId(msgIndex);

        // 添加新消息后主动滚动到底部
        setTimeout(() => scrollToBottom(true), 100);

        setInput('');
        setLoading(true);

        // 根据不同模式设置不同的处理信息
        const defaultProcessingInfos = useTagRag
            ? [
                { tag: "T(q)", text: "生成查询标签中，分析用户问题语义..." },
                { tag: "TAG-MATCH", text: "准备执行标签匹配，查找相关知识" },
                { tag: "T-CUS", text: "相关性评分系统初始化" }
            ]
            : [
                { tag: "检索", text: "正在检索相关内容..." },
                { tag: "分析", text: "处理查询结果..." },
                { tag: "生成", text: "生成回答中..." }
            ];

        // 先更新一次初始信息
        setMessages(prev => {
            const newMessages = [...prev];
            if (newMessages[msgIndex]) {
                newMessages[msgIndex] = {
                    ...newMessages[msgIndex],
                    processingInfos: defaultProcessingInfos.map(info => ({ ...info, type: info.tag === "T(q)" ? "tq-step" : info.tag === "TAG-MATCH" ? "tag-match" : info.tag === "T-CUS" ? "tcus-step" : "retrieval" }))
                };
            }
            return newMessages;
        });

        // 更新处理信息数组，展示关键技术步骤（根据模式区分）
        const processingMessages = useTagRag
            ? [
                {
                    type: "tq-step",
                    tag: "T(q)",
                    text: "提取查询关键概念，生成语义标签"
                },
                {
                    type: "tq-step",
                    tag: "T(q)",
                    text: "分析查询意图，完成语义向量化"
                },
                {
                    type: "tag-match",
                    tag: "TAG-MATCH",
                    text: "执行标签匹配，筛选相关知识"
                },
                {
                    type: "tag-match",
                    tag: "TAG-MATCH",
                    text: "检索相关知识段落，准备评分"
                },
                {
                    type: "tcus-step",
                    tag: "T-CUS",
                    text: "计算语义相关度评分，排序结果"
                },
                {
                    type: "tcus-step",
                    tag: "T-CUS",
                    text: "优选高相关性内容块，组织上下文"
                },
                {
                    type: "retrieval",
                    tag: "GEN",
                    text: "整合检索内容，生成回答结构"
                }
            ]
            : [
                {
                    type: "retrieval",
                    tag: "检索",
                    text: "从知识库搜索相关内容"
                },
                {
                    type: "retrieval",
                    tag: "检索",
                    text: "提取关键信息段落"
                },
                {
                    type: "analysis",
                    tag: "分析",
                    text: "分析检索到的内容"
                },
                {
                    type: "analysis",
                    tag: "分析",
                    text: "处理查询相关内容"
                },
                {
                    type: "generation",
                    tag: "生成",
                    text: "生成最终回答"
                },
                {
                    type: "generation",
                    tag: "生成",
                    text: "整合信息，构建回答"
                }
            ];

        // 更新定时器部分
        const timer = setInterval(() => {
            const randomMessageObj = processingMessages[Math.floor(Math.random() * processingMessages.length)];

            // 更新处理消息中的处理信息
            setMessages(prev => {
                const newMessages = [...prev];
                if (newMessages[msgIndex]) {
                    // 确保显示三行，结构统一
                    const updatedProcessingInfos = [
                        randomMessageObj,
                        ...(newMessages[msgIndex].processingInfos || []).slice(0, 2)
                    ];

                    newMessages[msgIndex] = {
                        ...newMessages[msgIndex],
                        processingInfos: updatedProcessingInfos
                    };
                }
                return newMessages;
            });
        }, 1500);

        setProcessingInfoTimer(timer);

        try {
            // 用于获取实际后台日志的函数
            const fetchProcessingLogs = async (requestId) => {
                try {
                    // 实际项目中，这里应该调用后端API获取处理日志
                    const logsResponse = await axios.get(`/thinking-process/${requestId}`, {
                        headers: {
                            'ngrok-skip-browser-warning': 'true'
                        }
                    });
                    if (logsResponse.data && logsResponse.data.logs) {
                        setMessages(prev => {
                            const newMessages = [...prev];
                            if (newMessages[msgIndex]) {
                                newMessages[msgIndex] = {
                                    ...newMessages[msgIndex],
                                    processingInfos: logsResponse.data.logs.slice(0, 3)
                                };
                            }
                            return newMessages;
                        });
                    }
                } catch (error) {
                    console.error('获取处理日志失败:', error);
                }
            };

            const promptConfigs = {};
            if (agentPrompts.length > 0) {
                agentPrompts.forEach(prompt => {
                    if (prompt.is_default) {
                        promptConfigs[prompt.agent_type] = prompt.prompt_template;
                    }
                });
            }

            const payload = {
                query: userMessage.content,
                knowledge_base_id: selectedKnowledgeBase,
                use_code_analysis: useCodeAnalysis,
                use_tag_rag: useTagRag,
                use_code_retrieval: useCodeRetrieval,
                repository_id: useCodeRetrieval ? selectedRepository : null,
                prompt_configs: promptConfigs
            };

            const endpoint = useTagRag ? '/chat/tag-rag' : '/ask';

            // 向后端发送请求
            const response = await axios.post(endpoint, payload, {
                headers: {
                    'ngrok-skip-browser-warning': 'true'
                }
            });

            // 添加调试输出，帮助诊断问题
            console.log("API Response Data:", response.data);
            console.log("Response Data Keys:", Object.keys(response.data));
            console.log("Current Mode:", useTagRag ? "TagRAG" : "Standard RAG");
            console.log("API Endpoint:", endpoint);

            // 检查所有顶级响应字段的类型和值
            Object.keys(response.data).forEach(key => {
                console.log(`响应字段 [${key}] 类型:`, typeof response.data[key], `值:`, response.data[key]);
            });

            // 从API响应中智能提取回答内容
            let answerContent = "无回答内容";

            // 针对不同模式和API返回格式进行内容提取
            if (useTagRag) {
                // TagRAG模式下的标准字段提取
                answerContent = response.data.answer || response.data.response || response.data.content || response.data.text || answerContent;
                console.log("TagRAG模式，直接提取字段:", answerContent !== "无回答内容" ? "成功" : "失败");
            } else {
                // 非TagRAG模式下的特殊处理
                if (response.data.answer) {
                    console.log("非TagRAG模式，直接提取answer字段");
                    answerContent = response.data.answer;
                } else if (response.data.retrieval_agent_response) {
                    // 如果存在retrieval_agent_response字段
                    let rawResponse = response.data.retrieval_agent_response;
                    console.log("原始retrieval_agent_response:", rawResponse);

                    // 简化提取逻辑
                    const directExtract = rawResponse
                        .split(/### 整理检索到的信息/i)[1]
                        .split(/\-{16}/)[0]
                        .trim();

                    if (directExtract && directExtract.length > 10) {
                        console.log("简化提取成功");
                        answerContent = directExtract;
                    } else {
                        // 使用原有的复杂处理逻辑

                        // 尝试提取实际回答部分，根据日志中观察到的格式
                        // 在非TagRAG模式下，尝试直接提取最后一个回答部分
                        const fullContentPattern = /([\s\S]*?)\>{5,}.*TERMINATING RUN/;
                        const fullContentMatch = rawResponse.match(fullContentPattern);

                        if (fullContentMatch && fullContentMatch[1]) {
                            console.log("提取完整的响应内容前的部分");
                            rawResponse = fullContentMatch[1].trim();

                            // 现在尝试提取最后一个回复部分
                            const parts = rawResponse.split(/\-{16,}/);
                            if (parts.length > 1) {
                                const lastPart = parts[parts.length - 2]; // 取最后一个分隔符前的内容
                                console.log("提取到最后一个回复部分");

                                // 从这个部分中提取实际的回复内容
                                const agentMatchInLastPart = lastPart.match(/\w+(?:_\w+)* \(to .*?\):\s*([\s\S]*)/i);
                                if (agentMatchInLastPart && agentMatchInLastPart[1]) {
                                    console.log("在最后部分找到代理回复");
                                    answerContent = agentMatchInLastPart[1].trim();
                                    // 已成功提取，继续后续清理
                                } else {
                                    // 如果没有找到代理回复，就使用整个最后部分
                                    answerContent = lastPart.trim();
                                }
                            }
                        } else {
                            // 使用原有的代码尝试处理
                            answerContent = rawResponse;
                            // ... 原有的处理代码 ...
                        }

                        // 预处理响应内容，删除多余的分隔符和系统信息
                        answerContent = answerContent
                            .replace(/>{16,}\s*TERMINATING RUN.*?(?=\w+\s*\(to|\Z)/gs, '') // 移除终止运行信息
                            .replace(/>{5,}.*?(?=\w+\s*\(to|\Z)/gs, '') // 移除其他系统控制信息
                            .trim();

                        console.log("预处理后的响应:", answerContent);

                        // 尝试从其中提取纯文本内容
                        const contentMatch = answerContent.match(/TagRAG_AnswerAgent \(to 用户代理\):\s*([\s\S]*?)(?:-{16}|$)/);
                        if (contentMatch && contentMatch[1]) {
                            console.log("使用TagRAG_AnswerAgent模式成功匹配");
                            answerContent = contentMatch[1].trim();
                        } else {
                            // 尝试匹配retrieval_agent格式 (注意大小写区别)
                            let retrievalMatch = answerContent.match(/retrieval_agent \(to 用户代理\):\s*([\s\S]*?)(?:-{16}|$)/i);
                            if (retrievalMatch && retrievalMatch[1]) {
                                console.log("使用retrieval_agent模式成功匹配");
                                answerContent = retrievalMatch[1].trim();
                            } else {
                                // 尝试匹配其他可能的类似格式
                                retrievalMatch = answerContent.match(/用户代理 \(to 用户代理\):\s*([\s\S]*?)(?:-{16}|$)/i);
                                if (retrievalMatch && retrievalMatch[1]) {
                                    console.log("使用用户代理模式成功匹配");
                                    answerContent = retrievalMatch[1].trim();
                                } else {
                                    // 最后尝试一个更宽松的模式
                                    const anyAgentMatch = answerContent.match(/\w+(?:_\w+)* \(to .*?\):\s*([\s\S]*?)(?:-{16}|$)/i);
                                    if (anyAgentMatch && anyAgentMatch[1]) {
                                        console.log("使用通用代理模式成功匹配:", anyAgentMatch[0].split(' ')[0]);
                                        answerContent = anyAgentMatch[1].trim();
                                    } else {
                                        console.log("所有模式均匹配失败，使用整个响应内容");
                                        // 如果所有模式都失败，尝试提取主要内容部分
                                        const mainContentMatch = answerContent.match(/###.*?\n([\s\S]+?)(?:###|\Z)/);
                                        if (mainContentMatch && mainContentMatch[1]) {
                                            console.log("提取主要内容部分");
                                            answerContent = mainContentMatch[1].trim();
                                        } else {
                                            // 从日志中看到的特殊格式，直接处理
                                            const specialFormat1 = answerContent.match(/用户问题分析[\s\S]*?整理检索到的信息([\s\S]*?)(?:-{16}|$)/i);
                                            if (specialFormat1 && specialFormat1[1]) {
                                                console.log("匹配到特殊格式1");
                                                answerContent = specialFormat1[1].trim();
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 清理回答内容中的可能存在的其他格式问题
                        answerContent = answerContent
                            .replace(/-{16,}/g, '') // 移除分隔线
                            .replace(/\n{3,}/g, '\n\n') // 压缩多个空行
                            .trim();
                    }
                }
            }

            console.log("提取的最终回答内容:", answerContent);

            // 如果仍然是"无回答内容"，尝试显示关键内部字段
            if (answerContent === "无回答内容" && response.data) {
                // 尝试从任何可能包含内容的字段中提取
                for (const key of Object.keys(response.data)) {
                    const value = response.data[key];
                    if (typeof value === 'string' && value.length > 50 && key !== 'thinking_process') {
                        console.log(`从字段 ${key} 中提取备用内容`);
                        answerContent = value;
                        break;
                    }
                }
            }

            // 恢复处理从不同API端点返回的数据格式逻辑
            let thinkingProcessForMessage = [];
            let referenced_tags = [];
            let referenced_excerpts = [];
            let code_snippets = [];

            // 处理从不同API端点返回的数据格式
            if (response.data) {
                // 处理思考过程
                if (response.data.thinking_process) {
                    thinkingProcessForMessage = response.data.thinking_process;

                    // 提取结构化日志处理同前
                    if (thinkingProcessForMessage.length > 0) {
                        const structuredLogs = extractStructuredLogs(thinkingProcessForMessage);
                        if (structuredLogs.length > 0) {
                            // 更新处理信息显示
                            setMessages(prev => {
                                const newMessages = [...prev];
                                if (newMessages[msgIndex]) {
                                    // 格式化日志信息，保留技术标签，限制为3条
                                    const formattedLogs = structuredLogs.slice(0, 3).map(log => {
                                        // 根据类型提供合适的标签和自然描述
                                        let tag, text, type;

                                        switch (log.type) {
                                            case "查询标签分析":
                                                tag = "T(q)";
                                                text = "分析查询语义，提取核心概念";
                                                type = "tq-step";
                                                break;
                                            case "标签匹配":
                                                tag = "TAG-MATCH";
                                                text = "执行标签匹配，搜索相关内容";
                                                type = "tag-match";
                                                break;
                                            case "相关性评分":
                                                tag = "T-CUS";
                                                text = "计算内容相关性评分";
                                                type = "tcus-step";
                                                break;
                                            case "内容检索":
                                                tag = "RETRIEVAL";
                                                text = "从知识库提取相关信息";
                                                type = "retrieval";
                                                break;
                                            default:
                                                tag = "INFO";
                                                text = log.content.length > 40 ? log.content.substring(0, 40) + '...' : log.content;
                                                type = "";
                                        }

                                        return { tag, text, type };
                                    });

                                    newMessages[msgIndex] = {
                                        ...newMessages[msgIndex],
                                        processingInfos: formattedLogs
                                    };
                                }
                                return newMessages;
                            });
                        }
                    }
                }

                // 处理标签和引用
                referenced_tags = response.data.referenced_tags || [];
                referenced_excerpts = response.data.referenced_excerpts || [];
                code_snippets = response.data.code_snippets || [];

                // 处理非TagRAG模式下的引用信息 - 检查可能的字段名
                if (!useTagRag && referenced_excerpts.length === 0) {
                    console.log("非TagRAG模式，检查可能的引用字段");

                    // 尝试所有可能的引用字段名称
                    if (response.data.sources && Array.isArray(response.data.sources)) {
                        console.log("Found sources field:", response.data.sources);
                        referenced_excerpts = response.data.sources.map((source, index) => ({
                            chunk_id: `src-${index}`,
                            document_source: source.document_name || source.title || source.filename || "文档",
                            content: source.content || source.text || source.passage || source.context || "",
                            score: source.relevance_score || source.score || null
                        }));
                    } else if (response.data.context && Array.isArray(response.data.context)) {
                        console.log("Found context field:", response.data.context);
                        referenced_excerpts = response.data.context.map((ctx, index) => ({
                            chunk_id: `ctx-${index}`,
                            document_source: ctx.source || ctx.document || "上下文",
                            content: ctx.text || ctx.content || ctx,
                            score: null
                        }));
                    } else if (response.data.documents && Array.isArray(response.data.documents)) {
                        console.log("Found documents field:", response.data.documents);
                        referenced_excerpts = response.data.documents.map((doc, index) => ({
                            chunk_id: `doc-${index}`,
                            document_source: doc.title || doc.name || doc.source || "文档",
                            content: doc.content || doc.text || "",
                            score: doc.score || null
                        }));
                    }

                    console.log("Processed referenced_excerpts:", referenced_excerpts);
                }

                // 处理其他可能的返回格式
                if (!useTagRag && response.data.retrieval_agent_response && referenced_excerpts.length === 0) {
                    console.log("尝试从retrieval_agent_response提取引用信息");

                    // 提取方法1: 通过检索结果评估部分
                    let match = response.data.retrieval_agent_response.match(/检索结果评估:([\s\S]*?)整理检索到的信息/);
                    if (match && match[1]) {
                        const extractedText = match[1].trim();
                        console.log("从retrieval_agent_response提取的引用信息(方法1):", extractedText);

                        // 创建一个引用文档
                        referenced_excerpts.push({
                            chunk_id: 'extract-1',
                            document_source: '检索结果摘要',
                            content: extractedText,
                            score: null
                        });
                    }

                    // 提取方法2: 通过检索文档部分
                    match = response.data.retrieval_agent_response.match(/文档\s*\d+:([\s\S]*?)(?:文档\s*\d+:|相关度得分|来源:|$)/g);
                    if (match && match.length > 0) {
                        console.log("从retrieval_agent_response提取的引用信息(方法2):", match);

                        match.forEach((docText, idx) => {
                            // 提取内容、来源和相关度
                            const contentMatch = docText.match(/内容:\s*([\s\S]*?)(?:来源:|$)/);
                            const sourceMatch = docText.match(/来源:\s*([\s\S]*?)(?:相关度得分:|$)/);
                            const scoreMatch = docText.match(/相关度得分:\s*([\d\.]+)/);

                            if (contentMatch && contentMatch[1]) {
                                referenced_excerpts.push({
                                    chunk_id: `doc-${idx}`,
                                    document_source: sourceMatch && sourceMatch[1] ? sourceMatch[1].trim() : `文档${idx + 1}`,
                                    content: contentMatch[1].trim(),
                                    score: scoreMatch && scoreMatch[1] ? parseFloat(scoreMatch[1]) : null
                                });
                            }
                        });
                    }
                }
            }

            setThinkingProcess(prev => ({ ...prev, [msgIndex + 1]: thinkingProcessForMessage }));

            const aiMessage = {
                content: answerContent,
                sender: 'ai',
                timestamp: new Date().toISOString(),
                hasThinkingProcess: thinkingProcessForMessage && thinkingProcessForMessage.length > 0,
                referenced_tags: referenced_tags,
                referenced_excerpts: referenced_excerpts,
                code_snippets: code_snippets
            };

            console.log("生成的AI消息：", aiMessage);

            // 清除任何处理定时器
            if (processingInfoTimer) {
                clearInterval(processingInfoTimer);
                setProcessingInfoTimer(null);
            }

            // 用AI回答替换临时处理消息
            setMessages(prev => {
                const newMessages = [...prev];
                if (msgIndex < newMessages.length) {
                    newMessages[msgIndex] = aiMessage;
                    return newMessages;
                } else {
                    return [...prev, aiMessage];
                }
            });

            // 重置临时消息ID
            setTempMessageId(null);
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

            // 清除任何处理定时器
            if (processingInfoTimer) {
                clearInterval(processingInfoTimer);
                setProcessingInfoTimer(null);
            }

            // 用错误消息替换临时处理消息
            setMessages(prev => {
                const newMessages = [...prev];
                if (msgIndex < newMessages.length) {
                    newMessages[msgIndex] = errorMessage;
                    return newMessages;
                } else {
                    return [...prev, errorMessage];
                }
            });

            // 重置临时消息ID
            setTempMessageId(null);
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

    // 组件卸载时清理定时器
    useEffect(() => {
        return () => {
            if (processingInfoTimer) {
                clearInterval(processingInfoTimer);
            }
        };
    }, [processingInfoTimer]);

    console.log('ChatPage: RENDERING with knowledgeBases:', knowledgeBases, 'Is Array?', Array.isArray(knowledgeBases));

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
                        {Array.isArray(knowledgeBases) && knowledgeBases.map(kb => (
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
                            {Array.isArray(repositories) && repositories.map(repo => (
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
            <div
                style={{
                    flexGrow: 1,
                    overflowY: 'auto',
                    padding: '16px 20px',
                    background: '#f7f9fc'
                }}
                ref={chatContainerRef}
                onScroll={handleScroll}
            >
                {messages.map((msg, index) => (
                    <div
                        key={index}
                        className={msg.sender === 'system' ? 'system-message-appear' : ''}
                        style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: msg.sender === 'user'
                                ? 'flex-end'
                                : 'flex-start', // 所有非用户消息都靠左
                            marginBottom: '20px',
                            width: '100%'
                        }}
                    >
                        <div style={{
                            display: 'flex',
                            maxWidth: msg.sender === 'system' ? '70%' : '80%',
                            width: msg.sender === 'system' ? 'auto' : 'auto'
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
                            {msg.sender === 'system' && (
                                <div style={{
                                    width: '28px',
                                    height: '28px',
                                    borderRadius: '50%',
                                    backgroundColor: '#8c8c8c',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    marginRight: '10px',
                                    fontSize: '14px',
                                    color: 'white',
                                    fontWeight: 'bold',
                                    flexShrink: 0,
                                    minWidth: '28px'
                                }} className="pulse">
                                    S
                                </div>
                            )}
                            <div
                                style={{
                                    padding: msg.sender === 'system' ? '12px 16px' : '14px 18px',
                                    borderRadius: msg.sender === 'user'
                                        ? '18px 18px 0 18px'
                                        : msg.sender === 'system'
                                            ? '16px'
                                            : '18px 18px 18px 0',
                                    backgroundColor: msg.sender === 'user'
                                        ? '#4267B2'
                                        : msg.sender === 'system'
                                            ? 'rgba(240, 242, 245, 0.95)'
                                            : 'white',
                                    color: msg.sender === 'user' ? 'white' : '#333',
                                    boxShadow: msg.sender === 'system' ? '0 2px 10px rgba(0, 0, 0, 0.06)' : '0 2px 8px rgba(0, 0, 0, 0.08)',
                                    wordWrap: 'break-word',
                                    marginBottom: '4px',
                                    flexGrow: 1,
                                    overflow: 'hidden',
                                    width: msg.sender === 'system' ? 'auto' : 'auto',
                                    transition: 'all 0.3s ease'
                                }}
                            >
                                {/* 修改系统消息的样式，移除加载图标，根据模式显示不同的标题和标签 */}
                                {msg.sender === 'system' && msg.isProcessing ? (
                                    <div className="system-message-content">
                                        <div className="processing-title">
                                            <Text strong style={{ fontSize: '13px', color: '#4267B2' }}>处理中</Text>
                                            {useTagRag && <span className="tech-badge">TagRAG</span>}
                                        </div>
                                        <div className="processing-info-container">
                                            {msg.processingInfos && msg.processingInfos.slice(0, 3).map((info, infoIndex) => {
                                                // 设置CSS类，按照消息类型
                                                let cssClass = `processing-info-item ${info.type || ''}`;

                                                return (
                                                    <div
                                                        key={infoIndex}
                                                        className={cssClass}
                                                        style={{
                                                            opacity: 1 - (infoIndex * 0.15)
                                                        }}
                                                    >
                                                        <span className="tag-label">{info.tag}</span>
                                                        <span className="process-description">{info.text}</span>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                ) : (
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
                                )}
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

                        {/* 修改时间戳对齐方式 */}
                        <div style={{
                            fontSize: '11px',
                            color: '#9aa0a6',
                            marginTop: '4px',
                            marginLeft: msg.sender === 'ai' || msg.sender === 'system' ? '48px' : '0',
                            marginRight: msg.sender === 'user' ? '48px' : '0',
                            alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start' // 与消息对齐
                        }}>
                            {new Date(msg.timestamp).toLocaleTimeString()}
                        </div>

                        {/* 其他内容如引用标签、引用文本等 */}
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

                        {/* 思考过程折叠面板 */}
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