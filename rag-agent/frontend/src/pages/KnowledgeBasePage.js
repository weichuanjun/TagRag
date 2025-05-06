import React, { useState, useEffect } from 'react';
import { Card, Button, Table, Space, Modal, Form, Input, Typography, Tabs, Popconfirm, message, Spin, Tag } from 'antd';
import { PlusOutlined, DeleteOutlined, FolderOutlined, FileOutlined, CodeOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

const KnowledgeBasePage = () => {
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [form] = Form.useForm();
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [repos, setRepos] = useState([]);
    const [documents, setDocuments] = useState([]);
    const [detailsLoading, setDetailsLoading] = useState(false);
    const [detailsVisible, setDetailsVisible] = useState(false);

    // 获取知识库列表
    const fetchKnowledgeBases = async () => {
        setLoading(true);
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data);
        } catch (error) {
            console.error('获取知识库列表失败:', error);
            message.error('获取知识库列表失败');
        } finally {
            setLoading(false);
        }
    };

    // 获取知识库详情
    const fetchKnowledgeBaseDetails = async (id) => {
        setDetailsLoading(true);
        try {
            // 获取代码库
            const repoResponse = await axios.get(`/knowledge-bases/${id}/repositories`);
            setRepos(repoResponse.data || []);

            // 获取文档
            const docResponse = await axios.get(`/knowledge-bases/${id}/documents`);
            setDocuments(docResponse.data || []);

            setSelectedKnowledgeBase(knowledgeBases.find(kb => kb.id === id));
            setDetailsVisible(true);
        } catch (error) {
            console.error('获取知识库详情失败:', error);
            message.error('获取知识库详情失败');
        } finally {
            setDetailsLoading(false);
        }
    };

    // 创建知识库
    const createKnowledgeBase = async (values) => {
        try {
            await axios.post('/knowledge-bases', {
                name: values.name,
                description: values.description
            });
            message.success('知识库创建成功');
            setModalVisible(false);
            form.resetFields();
            fetchKnowledgeBases();
        } catch (error) {
            console.error('创建知识库失败:', error);
            message.error('创建知识库失败');
        }
    };

    // 删除知识库
    const deleteKnowledgeBase = async (id) => {
        try {
            await axios.delete(`/knowledge-bases/${id}`);
            message.success('知识库已删除');
            fetchKnowledgeBases();
        } catch (error) {
            console.error('删除知识库失败:', error);
            message.error('删除知识库失败');
        }
    };

    // 组件加载时获取知识库列表
    useEffect(() => {
        fetchKnowledgeBases();
    }, []);

    // 表格列定义 - 知识库列表
    const columns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
        },
        {
            title: '知识库名称',
            dataIndex: 'name',
            key: 'name',
        },
        {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
        },
        {
            title: '创建时间',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (text) => new Date(text).toLocaleString()
        },
        {
            title: '代码库数量',
            dataIndex: 'repository_count',
            key: 'repository_count',
            sorter: (a, b) => a.repository_count - b.repository_count
        },
        {
            title: '文档数量',
            dataIndex: 'document_count',
            key: 'document_count',
            sorter: (a, b) => a.document_count - b.document_count
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Space size="middle">
                    <Button type="primary" onClick={() => fetchKnowledgeBaseDetails(record.id)}>
                        查看详情
                    </Button>
                    <Popconfirm
                        title="确定要删除这个知识库吗？"
                        description="删除后将无法恢复，同时会删除其包含的所有代码库和文档！"
                        icon={<ExclamationCircleOutlined style={{ color: 'red' }} />}
                        onConfirm={() => deleteKnowledgeBase(record.id)}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                    >
                        <Button danger type="text">删除</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    // 表格列定义 - 代码库列表
    const repoColumns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
        },
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            render: (text) => (
                <Space>
                    <CodeOutlined />
                    <Text>{text}</Text>
                </Space>
            )
        },
        {
            title: '路径',
            dataIndex: 'path',
            key: 'path',
            ellipsis: true,
        },
        {
            title: '添加时间',
            dataIndex: 'added_at',
            key: 'added_at',
            render: (text) => new Date(text).toLocaleString()
        },
        {
            title: '组件数量',
            dataIndex: 'component_count',
            key: 'component_count',
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            render: (status) => (
                <Tag color={status === 'analyzed' ? 'green' : 'blue'}>
                    {status === 'analyzed' ? '已分析' : '待分析'}
                </Tag>
            )
        }
    ];

    // 表格列定义 - 文档列表
    const documentColumns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
        },
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            render: (text) => (
                <Space>
                    <FileOutlined />
                    <Text>{text}</Text>
                </Space>
            )
        },
        {
            title: '路径',
            dataIndex: 'path',
            key: 'path',
            ellipsis: true,
        },
        {
            title: '添加时间',
            dataIndex: 'added_at',
            key: 'added_at',
            render: (text) => new Date(text).toLocaleString()
        },
        {
            title: '文本块数量',
            dataIndex: 'chunks_count',
            key: 'chunks_count',
        }
    ];

    return (
        <div className="knowledge-base-page">
            <Card
                title={<Title level={4}>知识库管理</Title>}
                extra={
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => setModalVisible(true)}
                    >
                        新建知识库
                    </Button>
                }
            >
                <Table
                    columns={columns}
                    dataSource={knowledgeBases}
                    rowKey="id"
                    loading={loading}
                    pagination={{
                        defaultPageSize: 10,
                        showSizeChanger: true,
                        pageSizeOptions: ['10', '20', '50'],
                    }}
                />
            </Card>

            {/* 创建知识库的表单对话框 */}
            <Modal
                title="新建知识库"
                open={modalVisible}
                onCancel={() => setModalVisible(false)}
                footer={null}
            >
                <Form
                    form={form}
                    layout="vertical"
                    onFinish={createKnowledgeBase}
                >
                    <Form.Item
                        name="name"
                        label="知识库名称"
                        rules={[{ required: true, message: '请输入知识库名称' }]}
                    >
                        <Input placeholder="例如：项目A知识库" />
                    </Form.Item>
                    <Form.Item
                        name="description"
                        label="描述"
                    >
                        <Input.TextArea placeholder="对此知识库的简要描述..." />
                    </Form.Item>
                    <Form.Item>
                        <Space>
                            <Button type="primary" htmlType="submit">
                                创建
                            </Button>
                            <Button onClick={() => setModalVisible(false)}>
                                取消
                            </Button>
                        </Space>
                    </Form.Item>
                </Form>
            </Modal>

            {/* 知识库详情对话框 */}
            <Modal
                title={selectedKnowledgeBase ? `知识库详情: ${selectedKnowledgeBase.name}` : '知识库详情'}
                open={detailsVisible}
                onCancel={() => setDetailsVisible(false)}
                width={800}
                footer={[
                    <Button key="back" onClick={() => setDetailsVisible(false)}>
                        关闭
                    </Button>
                ]}
            >
                {detailsLoading ? (
                    <div style={{ textAlign: 'center', padding: '20px' }}>
                        <Spin tip="加载中..." />
                    </div>
                ) : (
                    <Tabs defaultActiveKey="1">
                        <TabPane tab="代码库" key="1">
                            <Table
                                columns={repoColumns}
                                dataSource={repos}
                                rowKey="id"
                                pagination={{ pageSize: 5 }}
                            />
                        </TabPane>
                        <TabPane tab="文档" key="2">
                            <Table
                                columns={documentColumns}
                                dataSource={documents}
                                rowKey="id"
                                pagination={{ pageSize: 5 }}
                            />
                        </TabPane>
                    </Tabs>
                )}
            </Modal>
        </div>
    );
};

export default KnowledgeBasePage; 