import React, { useState, useEffect } from 'react';
import {
    Table, Button, Card, Modal, Form, Input, Select, message,
    Tabs, Typography, Divider, Space, Switch, Tooltip, Popconfirm,
    Row, Col, Tag
} from 'antd';
import {
    PlusOutlined, EditOutlined, DeleteOutlined, ExclamationCircleOutlined,
    RobotOutlined, DatabaseOutlined, InfoCircleOutlined, CopyOutlined,
    CheckCircleOutlined, StarOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;
const { TabPane } = Tabs;

const AgentPromptPage = () => {
    // 状态变量
    const [agentPrompts, setAgentPrompts] = useState([]);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [agentTypes, setAgentTypes] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingPrompt, setEditingPrompt] = useState(null);
    const [form] = Form.useForm();
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [selectedAgentType, setSelectedAgentType] = useState(null);

    // 初始加载数据
    useEffect(() => {
        fetchKnowledgeBases();
        fetchAgentTypes();
        fetchAgentPrompts();
    }, []);

    // 当过滤条件变化时重新加载数据
    useEffect(() => {
        fetchAgentPrompts();
    }, [selectedKnowledgeBase, selectedAgentType]);

    // 获取知识库列表
    const fetchKnowledgeBases = async () => {
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data);
        } catch (error) {
            message.error('加载知识库失败');
            console.error(error);
        }
    };

    // 获取Agent类型
    const fetchAgentTypes = async () => {
        try {
            const response = await axios.get('/agent-prompts/agent-types');
            setAgentTypes(response.data.agent_types);
        } catch (error) {
            message.error('加载Agent类型失败');
            console.error(error);
            // 设置一些默认类型
            setAgentTypes(['retrieval_agent', 'analyst_agent', 'code_analyst_agent', 'response_agent']);
        }
    };

    // 获取Agent提示词
    const fetchAgentPrompts = async () => {
        setLoading(true);
        try {
            const params = {};
            if (selectedKnowledgeBase) {
                params.knowledge_base_id = selectedKnowledgeBase;
            }
            if (selectedAgentType) {
                params.agent_type = selectedAgentType;
            }

            const response = await axios.get('/agent-prompts', { params });
            setAgentPrompts(response.data);
        } catch (error) {
            message.error('加载Agent提示词失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    // 打开创建模态框
    const handleCreate = () => {
        setEditingPrompt(null);
        form.resetFields();
        setModalVisible(true);
    };

    // 打开编辑模态框
    const handleEdit = (prompt) => {
        setEditingPrompt(prompt);
        form.setFieldsValue({
            name: prompt.name,
            description: prompt.description,
            agent_type: prompt.agent_type,
            prompt_template: prompt.prompt_template,
            is_default: prompt.is_default,
            knowledge_base_id: prompt.knowledge_base_id || null
        });
        setModalVisible(true);
    };

    // 复制提示词
    const handleClone = (prompt) => {
        const newPrompt = {
            ...prompt,
            name: `${prompt.name} (复制)`,
            is_default: false,
        };
        delete newPrompt.id;
        delete newPrompt.created_at;
        delete newPrompt.updated_at;

        setEditingPrompt(null);
        form.setFieldsValue(newPrompt);
        setModalVisible(true);
    };

    // 删除提示词
    const handleDelete = async (promptId) => {
        try {
            await axios.delete(`/agent-prompts/${promptId}`);
            message.success('删除成功');
            fetchAgentPrompts();
        } catch (error) {
            message.error('删除失败');
            console.error(error);
        }
    };

    // 提交表单
    const handleSubmit = async () => {
        try {
            const values = await form.validateFields();

            if (editingPrompt) {
                // 更新提示词
                await axios.put(`/agent-prompts/${editingPrompt.id}`, values);
                message.success('更新成功');
            } else {
                // 创建提示词
                await axios.post('/agent-prompts', values);
                message.success('创建成功');
            }

            setModalVisible(false);
            fetchAgentPrompts();
        } catch (error) {
            console.error('提交表单失败:', error);
            message.error('保存失败');
        }
    };

    // 表格列配置
    const columns = [
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            render: (text, record) => (
                <Space>
                    {text}
                    {record.is_default && (
                        <Tag color="gold" icon={<StarOutlined />}>默认</Tag>
                    )}
                </Space>
            ),
        },
        {
            title: 'Agent类型',
            dataIndex: 'agent_type',
            key: 'agent_type',
            render: (text) => (
                <Tag color="blue">{text}</Tag>
            ),
        },
        {
            title: '知识库',
            dataIndex: 'knowledge_base_id',
            key: 'knowledge_base_id',
            render: (kbId) => {
                if (!kbId) {
                    return <Tag color="green">通用</Tag>;
                }
                const kb = knowledgeBases.find(kb => kb.id === kbId);
                return kb ? kb.name : `知识库 ${kbId}`;
            },
        },
        {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
        },
        {
            title: '提示词模板',
            dataIndex: 'prompt_template',
            key: 'prompt_template',
            ellipsis: true,
            render: (text) => <Text ellipsis={{ tooltip: text }}>{text.substring(0, 50)}...</Text>,
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Space size="small">
                    <Button
                        type="primary"
                        icon={<EditOutlined />}
                        size="small"
                        onClick={() => handleEdit(record)}
                    >
                        编辑
                    </Button>
                    <Button
                        icon={<CopyOutlined />}
                        size="small"
                        onClick={() => handleClone(record)}
                    >
                        复制
                    </Button>
                    <Popconfirm
                        title="确定要删除此提示词吗？"
                        onConfirm={() => handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Button
                            danger
                            icon={<DeleteOutlined />}
                            size="small"
                            disabled={record.is_default} // 禁止删除默认提示词
                        >
                            删除
                        </Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div className="agent-prompt-page">
            <Card>
                <Title level={4}>
                    <RobotOutlined /> Agent提示词管理
                </Title>
                <Text>在这里管理不同知识库和不同Agent类型的提示词，为您的AI助手定制个性化行为。</Text>

                <Divider />

                <div style={{ marginBottom: 16 }}>
                    <Space wrap>
                        <Select
                            style={{ width: 200 }}
                            placeholder="选择知识库"
                            allowClear
                            value={selectedKnowledgeBase}
                            onChange={setSelectedKnowledgeBase}
                            optionFilterProp="children"
                        >
                            {knowledgeBases.map(kb => (
                                <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                            ))}
                        </Select>

                        <Select
                            style={{ width: 180 }}
                            placeholder="选择Agent类型"
                            allowClear
                            value={selectedAgentType}
                            onChange={setSelectedAgentType}
                            optionFilterProp="children"
                        >
                            {agentTypes.map(type => (
                                <Option key={type} value={type}>{type}</Option>
                            ))}
                        </Select>

                        <Button
                            type="primary"
                            icon={<PlusOutlined />}
                            onClick={handleCreate}
                        >
                            新建提示词
                        </Button>
                    </Space>
                </div>

                <Table
                    columns={columns}
                    dataSource={agentPrompts}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10 }}
                    expandable={{
                        expandedRowRender: record => (
                            <div style={{ padding: '0 20px' }}>
                                <Card title="提示词内容" bordered={false} size="small">
                                    <div style={{
                                        whiteSpace: 'pre-wrap',
                                        background: '#f5f5f5',
                                        padding: 16,
                                        borderRadius: 4,
                                        maxHeight: 300,
                                        overflow: 'auto'
                                    }}>
                                        {record.prompt_template}
                                    </div>
                                </Card>
                            </div>
                        ),
                    }}
                />
            </Card>

            {/* 创建/编辑模态框 */}
            <Modal
                title={editingPrompt ? "编辑Agent提示词" : "创建Agent提示词"}
                open={modalVisible}
                onOk={handleSubmit}
                onCancel={() => setModalVisible(false)}
                width={800}
                destroyOnClose
            >
                <Form
                    form={form}
                    layout="vertical"
                    initialValues={{
                        is_default: false,
                        knowledge_base_id: null,
                    }}
                >
                    <Row gutter={16}>
                        <Col span={16}>
                            <Form.Item
                                name="name"
                                label="名称"
                                rules={[{ required: true, message: '请输入提示词名称' }]}
                            >
                                <Input placeholder="输入提示词名称" />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item
                                name="agent_type"
                                label="Agent类型"
                                rules={[{ required: true, message: '请选择Agent类型' }]}
                            >
                                <Select placeholder="选择Agent类型">
                                    {agentTypes.map(type => (
                                        <Option key={type} value={type}>{type}</Option>
                                    ))}
                                </Select>
                            </Form.Item>
                        </Col>
                    </Row>

                    <Row gutter={16}>
                        <Col span={16}>
                            <Form.Item
                                name="description"
                                label="描述"
                            >
                                <Input placeholder="输入提示词描述" />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item
                                name="knowledge_base_id"
                                label="关联知识库"
                                tooltip="不选择则为通用提示词，适用于所有知识库"
                            >
                                <Select placeholder="选择关联的知识库" allowClear>
                                    {knowledgeBases.map(kb => (
                                        <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                                    ))}
                                </Select>
                            </Form.Item>
                        </Col>
                    </Row>

                    <Form.Item
                        name="prompt_template"
                        label="提示词模板"
                        rules={[{ required: true, message: '请输入提示词模板' }]}
                    >
                        <TextArea
                            placeholder="输入提示词模板内容"
                            autoSize={{ minRows: 10, maxRows: 20 }}
                        />
                    </Form.Item>

                    <Form.Item
                        name="is_default"
                        label="设为默认"
                        valuePropName="checked"
                        tooltip="设为默认后，此类型的其他提示词将不再是默认"
                    >
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default AgentPromptPage; 