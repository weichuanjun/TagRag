import React, { useState, useEffect } from 'react';
import { Button, Card, Typography, Space, message, Select } from 'antd';
import axios from 'axios';

const { Title, Text } = Typography;
const { Option } = Select;

const DebugPage = () => {
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [loading, setLoading] = useState(false);
    const [apiStatus, setApiStatus] = useState({});

    const testAPI = async (endpoint, name) => {
        setLoading(true);
        try {
            const response = await axios.get(endpoint);
            setApiStatus(prev => ({
                ...prev,
                [name]: { success: true, data: response.data }
            }));
            message.success(`${name} API 测试成功`);
            return response.data;
        } catch (error) {
            console.error(`${name} API 测试失败:`, error);
            setApiStatus(prev => ({
                ...prev,
                [name]: { success: false, error: error.message }
            }));
            message.error(`${name} API 测试失败: ${error.message}`);
            return null;
        } finally {
            setLoading(false);
        }
    };

    const fetchKnowledgeBases = async () => {
        const data = await testAPI('/knowledge-bases', '知识库API');
        if (data) {
            setKnowledgeBases(data);
            if (data.length > 0) {
                setSelectedKnowledgeBase(data[0].id);
            }
        }
    };

    useEffect(() => {
        fetchKnowledgeBases();
    }, []);

    return (
        <div style={{ padding: '20px' }}>
            <Title level={2}>调试页面</Title>

            <Space direction="vertical" style={{ width: '100%' }}>
                <Card title="API 状态" size="small">
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Button
                            onClick={() => testAPI('/', '根API')}
                            loading={loading}
                        >
                            测试根API
                        </Button>

                        <Button
                            onClick={() => testAPI('/knowledge-bases', '知识库API')}
                            loading={loading}
                        >
                            测试知识库API
                        </Button>

                        <Button
                            onClick={() => testAPI('/code/repositories', '代码仓库API')}
                            loading={loading}
                        >
                            测试代码仓库API
                        </Button>
                    </Space>
                </Card>

                <Card title="API 响应" size="small">
                    {Object.entries(apiStatus).map(([name, status]) => (
                        <div key={name} style={{ marginBottom: '10px' }}>
                            <Text strong>{name}: </Text>
                            <Text type={status.success ? 'success' : 'danger'}>
                                {status.success ? '成功' : '失败'}
                            </Text>
                            {status.success && (
                                <pre style={{
                                    background: '#f5f5f5',
                                    padding: '10px',
                                    borderRadius: '4px',
                                    fontSize: '12px',
                                    maxHeight: '200px',
                                    overflow: 'auto'
                                }}>
                                    {JSON.stringify(status.data, null, 2)}
                                </pre>
                            )}
                            {!status.success && (
                                <Text type="danger">{status.error}</Text>
                            )}
                        </div>
                    ))}
                </Card>

                <Card title="知识库选择测试" size="small">
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <div>
                            <Text strong>知识库列表: </Text>
                            <Text>{knowledgeBases.length} 个知识库</Text>
                        </div>

                        <Select
                            style={{ width: 200 }}
                            value={selectedKnowledgeBase}
                            onChange={setSelectedKnowledgeBase}
                            placeholder="选择知识库"
                            loading={loading}
                        >
                            {knowledgeBases.map(kb => (
                                <Option key={kb.id} value={kb.id}>
                                    {kb.name} (ID: {kb.id})
                                </Option>
                            ))}
                        </Select>

                        <div>
                            <Text strong>当前选择: </Text>
                            <Text>{selectedKnowledgeBase || '无'}</Text>
                        </div>
                    </Space>
                </Card>

                <Card title="环境信息" size="small">
                    <div>
                        <Text strong>当前域名: </Text>
                        <Text>{window.location.hostname}</Text>
                    </div>
                    <div>
                        <Text strong>当前端口: </Text>
                        <Text>{window.location.port}</Text>
                    </div>
                    <div>
                        <Text strong>API Base URL: </Text>
                        <Text>{axios.defaults.baseURL || '未设置'}</Text>
                    </div>
                </Card>
            </Space>
        </div>
    );
};

export default DebugPage; 