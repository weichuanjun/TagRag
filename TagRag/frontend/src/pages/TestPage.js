import React, { useState, useEffect } from 'react';
import { Button, Card, Typography, Space, message } from 'antd';
import axios from 'axios';

const { Title, Text } = Typography;

const TestPage = () => {
    const [testResults, setTestResults] = useState([]);
    const [loading, setLoading] = useState(false);

    const runTest = async (testName, testFunction) => {
        setLoading(true);
        try {
            const result = await testFunction();
            setTestResults(prev => [...prev, { name: testName, success: true, data: result }]);
            message.success(`${testName} 测试成功`);
        } catch (error) {
            console.error(`${testName} 测试失败:`, error);
            setTestResults(prev => [...prev, {
                name: testName,
                success: false,
                error: error.message || error.toString()
            }]);
            message.error(`${testName} 测试失败: ${error.message}`);
        }
        setLoading(false);
    };

    const testBackendConnection = async () => {
        const response = await axios.get('/');
        return response.data;
    };

    const testRepositoriesAPI = async () => {
        const response = await axios.get('/code/repositories');
        return response.data;
    };

    const testKnowledgeBasesAPI = async () => {
        const response = await axios.get('/knowledge-bases');
        return response.data;
    };

    const runAllTests = async () => {
        setTestResults([]);
        await runTest('后端连接测试', testBackendConnection);
        await runTest('代码仓库API测试', testRepositoriesAPI);
        await runTest('知识库API测试', testKnowledgeBasesAPI);
    };

    return (
        <div style={{ padding: '20px' }}>
            <Title level={2}>前端API连接测试</Title>
            <Space direction="vertical" style={{ width: '100%' }}>
                <Button
                    type="primary"
                    onClick={runAllTests}
                    loading={loading}
                    size="large"
                >
                    运行所有测试
                </Button>

                <Button
                    onClick={() => runTest('后端连接测试', testBackendConnection)}
                    loading={loading}
                >
                    测试后端连接
                </Button>

                <Button
                    onClick={() => runTest('代码仓库API测试', testRepositoriesAPI)}
                    loading={loading}
                >
                    测试代码仓库API
                </Button>

                <Button
                    onClick={() => runTest('知识库API测试', testKnowledgeBasesAPI)}
                    loading={loading}
                >
                    测试知识库API
                </Button>
            </Space>

            <div style={{ marginTop: '20px' }}>
                <Title level={3}>测试结果</Title>
                {testResults.map((result, index) => (
                    <Card
                        key={index}
                        style={{ marginBottom: '10px' }}
                        size="small"
                    >
                        <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                        }}>
                            <Text strong>{result.name}</Text>
                            <Text type={result.success ? 'success' : 'danger'}>
                                {result.success ? '✓ 成功' : '✗ 失败'}
                            </Text>
                        </div>
                        {result.success && (
                            <div style={{ marginTop: '10px' }}>
                                <Text type="secondary">响应数据:</Text>
                                <pre style={{
                                    background: '#f5f5f5',
                                    padding: '10px',
                                    borderRadius: '4px',
                                    fontSize: '12px',
                                    maxHeight: '200px',
                                    overflow: 'auto'
                                }}>
                                    {JSON.stringify(result.data, null, 2)}
                                </pre>
                            </div>
                        )}
                        {!result.success && (
                            <div style={{ marginTop: '10px' }}>
                                <Text type="danger">错误信息:</Text>
                                <pre style={{
                                    background: '#fff2f0',
                                    padding: '10px',
                                    borderRadius: '4px',
                                    fontSize: '12px',
                                    border: '1px solid #ffccc7'
                                }}>
                                    {result.error}
                                </pre>
                            </div>
                        )}
                    </Card>
                ))}
            </div>
        </div>
    );
};

export default TestPage; 