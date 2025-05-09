import React, { useState, useEffect } from 'react';
import { Table, Card, Button, Typography, Tag, Space, Modal, Form, Input, message, Tooltip, Popconfirm, Select, Divider, List, Empty } from 'antd';
import { PlusOutlined, DeleteOutlined, TagOutlined, EditOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const colorOptions = [
    "#1890ff", "#52c41a", "#faad14", "#f5222d", "#722ed1", "#13c2c2", "#eb2f96"
];

const TagManagementPage = () => {
    const [tags, setTags] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingTag, setEditingTag] = useState(null);
    const [form] = Form.useForm();
    const [parentTags, setParentTags] = useState([]);
    const [selectedColor, setSelectedColor] = useState("#1890ff");

    // 文档和分块相关状态
    const [tagDocumentsMap, setTagDocumentsMap] = useState({});
    const [loadingDocuments, setLoadingDocuments] = useState({});
    const [isChunkModalVisible, setIsChunkModalVisible] = useState(false);
    const [selectedDocForChunks, setSelectedDocForChunks] = useState(null);
    const [selectedDocChunks, setSelectedDocChunks] = useState([]);
    const [chunksLoading, setChunksLoading] = useState(false);

    // 获取标签列表
    const fetchTags = async () => {
        setLoading(true);
        try {
            const response = await axios.get('/tags');
            const tagList = response.data.tags || [];
            setTags(tagList);
            setParentTags(tagList.filter(tag => !tag.parent_id));

            // 获取每个标签关联的文档
            tagList.forEach(tag => {
                fetchTagDocuments(tag.id);
            });
        } catch (error) {
            console.error('获取标签列表失败:', error);
            message.error('获取标签列表失败');
        } finally {
            setLoading(false);
        }
    };

    // 组件加载时获取标签列表
    useEffect(() => {
        fetchTags();
    }, []);

    // 打开添加标签模态框
    const showAddModal = () => {
        setEditingTag(null);
        form.resetFields();
        setSelectedColor("#1890ff");
        setModalVisible(true);
    };

    // 打开编辑标签模态框
    const showEditModal = (tag) => {
        setEditingTag(tag);
        form.setFieldsValue({
            name: tag.name,
            description: tag.description,
            parent_id: tag.parent_id,
        });
        setSelectedColor(tag.color || "#1890ff");
        setModalVisible(true);
    };

    // 处理模态框取消
    const handleCancel = () => {
        setModalVisible(false);
    };

    // 处理标签添加/编辑提交
    const handleSubmit = async () => {
        try {
            const values = await form.validateFields();
            values.color = selectedColor;

            if (editingTag) {
                await axios.put(`/tags/${editingTag.id}`, values);
                message.success('标签更新成功');
            } else {
                await axios.post('/tags', values);
                message.success('标签添加成功');
            }

            setModalVisible(false);
            fetchTags();
        } catch (error) {
            console.error('提交标签失败:', error);
            message.error('提交标签失败');
        }
    };

    // 处理标签删除
    const handleDelete = async (tagId) => {
        try {
            await axios.delete(`/tags/${tagId}`);
            message.success('标签删除成功');
            fetchTags();

            // 清除已删除标签的文档数据
            setTagDocumentsMap(prev => {
                const updated = { ...prev };
                delete updated[tagId];
                return updated;
            });
        } catch (error) {
            console.error('删除标签失败:', error);
            message.error('删除标签失败');
        }
    };

    // 获取标签关联的文档列表
    const fetchTagDocuments = async (tagId) => {
        if (!tagId) return;

        setLoadingDocuments(prev => ({ ...prev, [tagId]: true }));
        try {
            const response = await axios.get(`/tags/${tagId}/documents`);
            const documents = response.data.documents || [];

            setTagDocumentsMap(prev => ({
                ...prev,
                [tagId]: documents
            }));
        } catch (error) {
            console.error(`获取标签 ${tagId} 的关联文档失败:`, error);
            message.error('获取标签关联文档失败');
        } finally {
            setLoadingDocuments(prev => ({ ...prev, [tagId]: false }));
        }
    };

    // 获取选定文档的块信息
    const fetchChunksForSelectedDoc = async (documentId) => {
        if (!documentId) return;
        setChunksLoading(true);
        setSelectedDocChunks([]);
        try {
            const response = await axios.get(`/documents/${documentId}/chunks`);
            setSelectedDocChunks(response.data || []);
        } catch (error) {
            console.error(`获取文档 ${documentId} 的块信息失败:`, error);
            message.error('获取文档分块信息失败');
        } finally {
            setChunksLoading(false);
        }
    };

    // 查看文档块分布
    const handleViewChunks = (document) => {
        setSelectedDocForChunks(document);
        setIsChunkModalVisible(true);
        fetchChunksForSelectedDoc(document.id);
    };

    // 处理文档块模态框取消
    const handleCancelChunkModal = () => {
        setIsChunkModalVisible(false);
        setSelectedDocForChunks(null);
        setSelectedDocChunks([]);
    };

    // 渲染文档块的标签
    const renderChunkTagsInModal = (metadata) => {
        const tagIds = [];
        if (metadata) {
            for (const key in metadata) {
                if (key.startsWith('tag_') && metadata[key] === true) {
                    const tagId = parseInt(key.substring(4), 10);
                    if (!isNaN(tagId)) {
                        tagIds.push(tagId);
                    }
                }
            }
        }

        return (
            <div>
                {tagIds.length > 0 ? (
                    tagIds.map(tagId => {
                        const tagObj = tags.find(t => t.id === tagId);
                        return tagObj ? (
                            <Tag key={tagId} color={tagObj.color} style={{ marginBottom: '4px' }}>
                                {tagObj.name}
                            </Tag>
                        ) : (
                            <Tag key={tagId}>ID: {tagId}</Tag>
                        );
                    })
                ) : (
                    <span>无标签</span>
                )}
            </div>
        );
    };

    // 渲染标签关联的文档
    const renderTagDocuments = (tagId) => {
        const documents = tagDocumentsMap[tagId] || [];
        const isLoading = loadingDocuments[tagId];

        if (isLoading) {
            return <Text type="secondary">加载文档中...</Text>;
        }

        if (documents.length === 0) {
            return <Text type="secondary">无关联文档</Text>;
        }

        return (
            <Space wrap>
                {documents.map(doc => (
                    <Tag
                        key={doc.id}
                        style={{ cursor: 'pointer', margin: '0 4px 4px 0' }}
                        onClick={() => handleViewChunks(doc)}
                    >
                        {doc.source || '未知文件'} ({doc.chunks_count || 0})
                    </Tag>
                ))}
            </Space>
        );
    };

    // 主表格列定义
    const columns = [
        {
            title: '标签',
            dataIndex: 'name',
            key: 'name',
            width: '15%',
            render: (text, record) => (
                <Tag color={record.color || '#1890ff'} style={{ fontSize: '14px', padding: '2px 8px' }}>
                    {text}
                </Tag>
            ),
        },
        {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
            width: '20%',
            ellipsis: true,
        },
        {
            title: '关联文档',
            key: 'documents',
            render: (_, record) => renderTagDocuments(record.id),
        },
        {
            title: '操作',
            key: 'action',
            width: '10%',
            render: (_, record) => (
                <Space size="middle">
                    <Tooltip title="编辑标签">
                        <Button
                            type="text"
                            icon={<EditOutlined />}
                            onClick={() => showEditModal(record)}
                        />
                    </Tooltip>
                    <Popconfirm
                        title="确定要删除这个标签吗？"
                        onConfirm={() => handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Tooltip title="删除标签">
                            <Button
                                type="text"
                                danger
                                icon={<DeleteOutlined />}
                            />
                        </Tooltip>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            <Title level={4}>标签管理</Title>
            <Text type="secondary">
                管理系统中的标签，用于对文档和代码进行分类
            </Text>

            <Card style={{ marginTop: 16 }}
                extra={
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={showAddModal}
                    >
                        添加标签
                    </Button>
                }>
                <Table
                    columns={columns}
                    dataSource={tags}
                    rowKey="id"
                    loading={loading}
                    pagination={false}
                />
            </Card>

            {/* 添加/编辑标签模态框 */}
            <Modal
                title={editingTag ? "编辑标签" : "添加标签"}
                open={modalVisible}
                onOk={handleSubmit}
                onCancel={handleCancel}
                okText="保存"
                cancelText="取消"
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="name"
                        label="标签名称"
                        rules={[{ required: true, message: '请输入标签名称' }]}
                    >
                        <Input prefix={<TagOutlined />} placeholder="输入标签名称" />
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="描述"
                    >
                        <Input.TextArea placeholder="标签描述（可选）" />
                    </Form.Item>

                    <Form.Item
                        name="parent_id"
                        label="父标签"
                    >
                        <Select placeholder="选择父标签（可选）" allowClear>
                            {parentTags.map(tag => (
                                <Option key={tag.id} value={tag.id}>
                                    <Tag color={tag.color}>{tag.name}</Tag>
                                </Option>
                            ))}
                        </Select>
                    </Form.Item>

                    <Form.Item label="标签颜色">
                        <div style={{ display: 'flex', gap: '8px' }}>
                            {colorOptions.map(color => (
                                <div
                                    key={color}
                                    onClick={() => setSelectedColor(color)}
                                    style={{
                                        width: '24px',
                                        height: '24px',
                                        borderRadius: '4px',
                                        backgroundColor: color,
                                        cursor: 'pointer',
                                        border: selectedColor === color ? '2px solid #000' : '1px solid #d9d9d9'
                                    }}
                                />
                            ))}
                        </div>
                    </Form.Item>
                </Form>
            </Modal>

            {/* 文档块模态框 */}
            <Modal
                title={`文档块详情: ${selectedDocForChunks?.source || ''}`}
                open={isChunkModalVisible}
                onCancel={handleCancelChunkModal}
                footer={[
                    <Button key="close" onClick={handleCancelChunkModal}>
                        关闭
                    </Button>
                ]}
                width={900}
            >
                {chunksLoading ? (
                    <div style={{ textAlign: 'center', padding: '20px' }}>
                        <Text>加载中...</Text>
                    </div>
                ) : (
                    <div>
                        <Text type="secondary" style={{ display: 'block', marginBottom: '15px' }}>
                            文档共有 {selectedDocChunks.length} 个块
                        </Text>
                        <List
                            itemLayout="vertical"
                            dataSource={selectedDocChunks}
                            renderItem={(chunk, index) => (
                                <List.Item key={`${chunk.id}_${index}`}>
                                    <Card
                                        size="small"
                                        title={`块 ${chunk.chunk_index + 1} (ID: ${chunk.id})`}
                                        extra={
                                            <span>
                                                <Text type="secondary">
                                                    {chunk.token_count} 个token |
                                                    类型: {chunk.structural_type || '未知'}
                                                </Text>
                                            </span>
                                        }
                                    >
                                        <div style={{ maxHeight: '200px', overflow: 'auto', marginBottom: '10px' }}>
                                            <Paragraph ellipsis={{ rows: 5, expandable: true }}>
                                                {chunk.content}
                                            </Paragraph>
                                        </div>
                                        <Divider style={{ margin: '8px 0' }} />
                                        <div>
                                            <Text strong>块标签:</Text>
                                            <div style={{ marginTop: '5px' }}>
                                                {renderChunkTagsInModal(chunk.metadata)}
                                            </div>
                                        </div>
                                    </Card>
                                </List.Item>
                            )}
                        />
                    </div>
                )}
            </Modal>
        </div>
    );
};

export default TagManagementPage; 