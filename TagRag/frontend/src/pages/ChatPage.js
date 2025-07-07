import React, { useState, useEffect, useRef, useContext } from 'react';
import { Input, Button, Spin, Select, Switch, Typography, Space } from 'antd';
import ReactMarkdown from 'react-markdown';
import { AuthContext } from '../context/AuthContext';

const { TextArea } = Input;
const { Title } = Typography;
const { Option } = Select;

// A new component to display processing information
const ProcessingInfoDisplay = ({ processingInfos }) => {
    if (!processingInfos || processingInfos.length === 0) {
        return null;
    }

    return (
        <div style={{
            padding: '10px 20px',
            borderTop: '1px solid #f0f0f0',
            borderBottom: '1px solid #f0f0f0',
            background: '#fafafa',
            maxHeight: '150px',
            overflowY: 'auto',
            flexShrink: 0
        }}>
            <Title level={5}>Processing Details:</Title>
            {processingInfos.map((info, index) => (
                <div key={index}>
                    <p style={{ margin: 0, fontWeight: 'bold' }}>{info.agent}: <span style={{ color: info.success ? 'green' : 'red' }}>{info.success ? 'Success' : 'Failure'}</span></p>
                    <p style={{ fontSize: '12px', margin: 0 }}>{info.details}</p>
                </div>
            ))}
        </div>
    );
};


const ChatPage = () => {
    const { token } = useContext(AuthContext);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKb, setSelectedKb] = useState(null);
    const [kbLoading, setKbLoading] = useState(false);
    const [isRag, setIsRag] = useState(true);
    const [processingInfos, setProcessingInfos] = useState([]);

    const messagesEndRef = useRef(null);
    const chatContainerRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    const handleScroll = () => {
        // Logic for handling scroll can be added here if needed
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        const fetchKnowledgeBases = async () => {
            setKbLoading(true);
            try {
                const response = await fetch('http://localhost:8000/knowledge-bases', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    setKnowledgeBases(data);
                    if (data.length > 0) {
                        setSelectedKb(data[0].id);
                    }
                }
            } catch (error) {
                console.error("Failed to fetch knowledge bases:", error);
            }
            setKbLoading(false);
        };
        fetchKnowledgeBases();
    }, [token]);

    const handleKbChange = (value) => {
        setSelectedKb(value);
    };

    const clearMessages = () => {
        setMessages([]);
        setProcessingInfos([]);
    }

    const handleSend = async () => {
        if (input.trim() && !isLoading) {
            const userMessage = { text: input, sender: 'user' };
            setMessages(prev => [...prev, userMessage]);
            setInput('');
            setIsLoading(true);
            setProcessingInfos([]);

            try {
                const response = await fetch('http://localhost:8000/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        message: input,
                        knowledge_base_id: selectedKb,
                        use_rag: isRag
                    }),
                });

                if (response.ok) {
                    const data = await response.json();
                    const botMessage = { text: data.answer, sender: 'bot' };
                    setMessages(prev => [...prev, botMessage]);
                    if (data.processing_info) {
                        setProcessingInfos(data.processing_info);
                    }
                } else {
                    const errorData = await response.json();
                    const errorMessage = { text: `Error: ${errorData.detail || 'Failed to get response'}`, sender: 'bot' };
                    setMessages(prev => [...prev, errorMessage]);
                }
            } catch (error) {
                const errorMessage = { text: `Error: ${error.message}`, sender: 'bot' };
                setMessages(prev => [...prev, errorMessage]);
            } finally {
                setIsLoading(false);
            }
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative', background: '#fff' }}>
            {/* Header with settings */}
            <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0', flexShrink: 0, background: '#fff' }}>
                <Title level={4} style={{ marginBottom: 16 }}>智能问答</Title>
                <Space wrap>
                    <Select
                        loading={kbLoading}
                        value={selectedKb}
                        style={{ width: 200 }}
                        onChange={handleKbChange}
                        placeholder="选择知识库"
                    >
                        {knowledgeBases.map(kb => <Option key={kb.id} value={kb.id}>{kb.name}</Option>)}
                    </Select>
                    <Switch
                        checked={isRag}
                        onChange={setIsRag}
                        checkedChildren="RAG"
                        unCheckedChildren="普通"
                    />
                    <Button
                        type="primary"
                        danger
                        onClick={() => {
                            if (window.confirm('确定要清除所有聊天记录吗?')) {
                                clearMessages();
                            }
                        }}
                    >
                        清除聊天记录
                    </Button>
                </Space>
            </div>

            {/* Chat messages area */}
            <div
                ref={chatContainerRef}
                onScroll={handleScroll}
                style={{
                    flexGrow: 1,
                    overflowY: 'auto',
                    padding: '20px',
                    backgroundColor: '#f9f9f9',
                }}
            >
                {messages.map((msg, index) => (
                    <div key={index} style={{ marginBottom: '15px', display: 'flex', justifyContent: msg.sender === 'user' ? 'flex-end' : 'flex-start' }}>
                        <div style={{
                            maxWidth: '70%',
                            padding: '10px 15px',
                            borderRadius: '20px',
                            backgroundColor: msg.sender === 'user' ? '#0084ff' : '#e4e6eb',
                            color: msg.sender === 'user' ? 'white' : 'black',
                            boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
                            wordBreak: 'break-word',
                        }}>
                            {msg.isLoading ? <Spin /> : <ReactMarkdown>{msg.text}</ReactMarkdown>}
                        </div>
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            {/* Processing Info Display */}
            <ProcessingInfoDisplay processingInfos={processingInfos} />

            {/* Input area */}
            <div style={{ padding: '16px', borderTop: '1px solid #f0f0f0', flexShrink: 0, background: '#fff', display: 'flex', alignItems: 'center' }}>
                <TextArea
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onPressEnter={handleSend}
                    rows={1}
                    autoSize={{ minRows: 1, maxRows: 5 }}
                    placeholder="在这里输入你的问题..."
                    disabled={isLoading}
                    style={{ flexGrow: 1, marginRight: '16px' }}
                />
                <Button onClick={handleSend} type="primary" loading={isLoading} size="large">
                    发送
                </Button>
            </div>
        </div>
    );
};

export default ChatPage; 