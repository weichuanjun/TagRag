import React, { useState, useEffect, useCallback } from 'react';
import { Table, Card, Button, Typography, Tag, Space, Modal, Form, Input, message, Tooltip, Popconfirm, Select, Divider, List, Empty, Badge, Checkbox } from 'antd';
import { PlusOutlined, DeleteOutlined, TagOutlined, EditOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
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
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKB, setSelectedKB] = useState(null);
    const [tagDeleteStatus, setTagDeleteStatus] = useState({});
    const [batchDeleteLoading, setBatchDeleteLoading] = useState(false);
    const [deletableTagsCount, setDeletableTagsCount] = useState(0);
    const [isRootTag, setIsRootTag] = useState(false);
    const [pageSize, setPageSize] = useState(10);

    // 文档和分块相关状态
    const [tagDocumentsMap, setTagDocumentsMap] = useState({});
    const [loadingDocuments, setLoadingDocuments] = useState({});
    const [isChunkModalVisible, setIsChunkModalVisible] = useState(false);
    const [selectedDocForChunks, setSelectedDocForChunks] = useState(null);
    const [selectedDocChunks, setSelectedDocChunks] = useState([]);
    const [chunksLoading, setChunksLoading] = useState(false);

    // 获取标签关联的文档列表 - 移到了fetchTags前面
    const fetchTagDocuments = useCallback(async (tagId) => {
        if (!tagId) return;

        setLoadingDocuments(prev => ({ ...prev, [tagId]: true }));
        try {
            const response = await axios.get(`/tags/${tagId}/documents`);
            // 修正这里的数据获取方式，API直接返回文档数组
            const documents = Array.isArray(response.data) ? response.data : [];

            setTagDocumentsMap(prev => ({
                ...prev,
                [tagId]: documents
            }));

            // 文档信息更新后，重新检查标签是否可删除
            checkTagDeletable(tagId);
        } catch (error) {
            console.error(`获取标签 ${tagId} 的关联文档失败:`, error);
            message.error('获取标签关联文档失败');
        } finally {
            setLoadingDocuments(prev => ({ ...prev, [tagId]: false }));
        }
    }, []);

    // 检查标签是否可以安全删除并缓存结果
    const checkTagDeletable = useCallback(async (tagId) => {
        try {
            const response = await axios.get(`/tags/${tagId}/can-delete`);
            setTagDeleteStatus(prev => ({
                ...prev,
                [tagId]: response.data.can_delete
            }));

            return response.data.can_delete;
        } catch (error) {
            console.error(`检查标签 ${tagId} 是否可安全删除时出错:`, error);
            setTagDeleteStatus(prev => ({
                ...prev,
                [tagId]: false
            }));
            return false;
        }
    }, []);

    // 获取可安全删除的标签数量
    const fetchDeletableTagsCount = useCallback(async () => {
        try {
            const response = await axios.get('/tags/deletable');
            setDeletableTagsCount(response.data.count || 0);
            return response.data.count || 0;
        } catch (error) {
            console.error('获取可删除标签数量失败:', error);
            return 0;
        }
    }, []);

    // 获取标签列表
    const fetchTags = useCallback(async () => {
        setLoading(true);
        try {
            // 构建请求URL，如果选择了知识库则添加过滤参数
            let url = '/tags';
            if (selectedKB) {
                url += `?knowledge_base_id=${selectedKB}`;
            }
            const response = await axios.get(url);
            const tagList = response.data.tags || [];

            setTags(tagList);
            setParentTags(tagList.filter(tag => !tag.parent_id));

            // 清空之前的文档映射
            setTagDocumentsMap({});

            // 获取每个标签关联的文档
            tagList.forEach(tag => {
                fetchTagDocuments(tag.id);
            });

            // 重置标签删除状态
            const newDeleteStatus = {};
            // 为每个标签初始化可删除状态为未知（null）
            tagList.forEach(tag => {
                newDeleteStatus[tag.id] = null;
            });
            setTagDeleteStatus(newDeleteStatus);

            // 只对所有标签进行一次批量检查
            const tagsToCheck = tagList.slice(0, 5); // 限制只检查前5个标签，避免大量请求
            tagsToCheck.forEach(tag => {
                checkTagDeletable(tag.id);
            });

            // 获取可删除标签的数量 - 只调用一次
            fetchDeletableTagsCount();
        } catch (error) {
            console.error('获取标签列表失败:', error);
            message.error('获取标签列表失败');
        } finally {
            setLoading(false);
        }
    }, [selectedKB, fetchTagDocuments, fetchDeletableTagsCount, checkTagDeletable]);

    // 判断标签是否可以安全删除（从缓存状态获取）
    const canSafelyDeleteTag = (tagId) => {
        // 所有标签都可以删除
        return true;
    };

    // 批量安全删除标签
    const handleBatchSafeDelete = async () => {
        try {
            setBatchDeleteLoading(true);

            // 获取所有可删除的标签
            const response = await axios.get('/tags/deletable');
            const deletableTags = response.data.deletable_tags || [];

            if (deletableTags.length === 0) {
                message.info('没有可以安全删除的标签');
                setBatchDeleteLoading(false);
                return;
            }

            // 确认框
            Modal.confirm({
                title: '批量安全删除标签',
                content: (
                    <div>
                        <p>确定要删除以下 {deletableTags.length} 个无关联文档且非父标签的标签吗？此操作不可撤销。</p>
                        <div style={{ maxHeight: '200px', overflow: 'auto', marginTop: '10px' }}>
                            {deletableTags.map(tag => (
                                <Tag key={tag.id} color={tag.color} style={{ margin: '2px' }}>
                                    {tag.name}
                                    {tag.hierarchy_level === 'root' && <span> (ROOT)</span>}
                                </Tag>
                            ))}
                        </div>
                    </div>
                ),
                okText: '确定删除',
                cancelText: '取消',
                okButtonProps: { danger: true },
                width: 500,
                onOk: async () => {
                    try {
                        // 逐个删除标签
                        let successCount = 0;
                        for (const tag of deletableTags) {
                            try {
                                await axios.delete(`/tags/${tag.id}?force=true`);
                                successCount++;
                            } catch (err) {
                                console.error(`删除标签 ${tag.id} (${tag.name}) 失败:`, err);
                            }
                        }

                        message.success(`成功删除 ${successCount} 个标签`);
                        // 重新加载标签列表
                        fetchTags();
                    } catch (error) {
                        message.error('批量删除标签失败: ' + error.message);
                    } finally {
                        setBatchDeleteLoading(false);
                    }
                },
                onCancel: () => {
                    setBatchDeleteLoading(false);
                }
            });
        } catch (error) {
            console.error('批量删除标签失败:', error);
            message.error('批量删除标签失败: ' + error.message);
            setBatchDeleteLoading(false);
        }
    };

    // 加载知识库列表
    const fetchKnowledgeBases = async () => {
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data || []);
        } catch (error) {
            console.error('获取知识库列表失败:', error);
            message.error('获取知识库列表失败');
        }
    };

    // 组件加载时获取标签列表和知识库列表
    useEffect(() => {
        fetchKnowledgeBases();
        fetchTags();

        // 定时获取可删除标签数量，每30秒更新一次
        const deletableTagsTimer = setInterval(() => {
            fetchDeletableTagsCount();
        }, 30000); // 30秒

        return () => {
            clearInterval(deletableTagsTimer);
        };
    }, [fetchTags, fetchDeletableTagsCount]);

    // 当选择的知识库变化时，重新获取标签
    useEffect(() => {
        fetchTags();
    }, [fetchTags]);

    // 打开添加标签模态框
    const showAddModal = () => {
        setEditingTag(null);
        form.resetFields();
        setSelectedColor("#1890ff");
        setIsRootTag(false);
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
        setIsRootTag(tag.hierarchy_level === 'root');
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

            // 根据是否为根标签设置层级
            if (isRootTag) {
                values.hierarchy_level = "root";
                // 根标签没有父标签
                values.parent_id = null;
            } else {
                values.hierarchy_level = "leaf"; // 默认为叶子标签
            }

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
            // 获取标签信息用于提示
            const tagInfo = tags.find(t => t.id === tagId);
            if (!tagInfo) {
                message.error('标签不存在');
                return;
            }

            // 检查标签状态
            const response = await axios.get(`/tags/${tagId}/can-delete`);
            const { has_documents, has_children, document_count } = response.data;

            // 构建确认信息
            let confirmMessage = `确定要删除标签 "${tagInfo.name}" 吗？`;
            let confirmDescription = '';

            if (has_documents) {
                confirmDescription += `此标签关联了 ${document_count} 个文档，删除后将解除关联。`;
            }

            if (has_children) {
                confirmDescription += `此标签有子标签，删除后子标签将失去父标签关系。`;
            }

            if (tagInfo.hierarchy_level === 'root') {
                confirmDescription += `这是一个根(ROOT)标签，删除可能会影响标签体系结构。`;
            }

            // 显示确认对话框
            Modal.confirm({
                title: confirmMessage,
                content: confirmDescription,
                okText: '确定删除',
                cancelText: '取消',
                okButtonProps: { danger: true },
                onOk: async () => {
                    try {
                        // 使用force=true参数强制删除
                        await axios.delete(`/tags/${tagId}?force=true`);
                        message.success('标签删除成功');
                        fetchTags();

                        // 清除已删除标签的文档数据
                        setTagDocumentsMap(prev => {
                            const updated = { ...prev };
                            delete updated[tagId];
                            return updated;
                        });
                    } catch (err) {
                        console.error('删除标签失败:', err);
                        message.error('删除标签失败: ' + (err.response?.data?.detail || err.message));
                    }
                }
            });
        } catch (error) {
            console.error('删除标签失败:', error);
            message.error('删除标签失败: ' + (error.response?.data?.detail || error.message));
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
            sorter: (a, b) => a.name.localeCompare(b.name),
            render: (text, record) => (
                <Tag color={record.color || '#1890ff'} style={{ fontSize: '14px', padding: '2px 8px' }}>
                    {text}
                    {record.hierarchy_level === 'root' && (
                        <Badge
                            count="ROOT"
                            style={{
                                backgroundColor: '#52c41a',
                                fontSize: '10px',
                                marginLeft: '5px',
                                transform: 'scale(0.8)'
                            }}
                        />
                    )}
                </Tag>
            ),
        },
        {
            title: '父标签',
            key: 'parent',
            width: '15%',
            sorter: (a, b) => {
                const parentA = tags.find(tag => tag.id === a.parent_id);
                const parentB = tags.find(tag => tag.id === b.parent_id);
                return (parentA?.name || '').localeCompare(parentB?.name || '');
            },
            render: (_, record) => {
                if (!record.parent_id) return <Text type="secondary">无</Text>;

                const parentTag = tags.find(tag => tag.id === record.parent_id);
                if (!parentTag) return <Text type="secondary">未知 (ID: {record.parent_id})</Text>;

                return (
                    <Tag color={parentTag.color || '#1890ff'}>
                        {parentTag.name}
                    </Tag>
                );
            }
        },
        {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
            width: '20%',
            ellipsis: true,
            sorter: (a, b) => (a.description || '').localeCompare(b.description || ''),
            render: (text, record) => (
                <>
                    {text || ''}
                    {record.hierarchy_level === 'root' && (
                        <Tag color="green" style={{ marginLeft: 4 }}>ROOT标签</Tag>
                    )}
                </>
            )
        },
        {
            title: '关联文档',
            key: 'documents',
            sorter: (a, b) => (tagDocumentsMap[a.id]?.length || 0) - (tagDocumentsMap[b.id]?.length || 0),
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
                    <Tooltip title="删除标签">
                        <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => handleDelete(record.id)}
                        />
                    </Tooltip>
                </Space>
            ),
        },
    ];

    return (
        <div>
            <Card
                style={{ marginTop: 16 }}
                title="标签管理"
                extra={
                    <Space>
                        <Select
                            placeholder="选择知识库"
                            style={{ width: 200 }}
                            allowClear
                            onChange={value => setSelectedKB(value)}
                            value={selectedKB}
                        >
                            {knowledgeBases.map(kb => (
                                <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                            ))}
                        </Select>
                        <Button
                            type="primary"
                            icon={<PlusOutlined />}
                            onClick={showAddModal}
                        >
                            添加标签
                        </Button>
                        <Button
                            type="primary"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={handleBatchSafeDelete}
                            loading={batchDeleteLoading}
                            disabled={deletableTagsCount === 0}
                        >
                            批量安全删除 ({deletableTagsCount})
                        </Button>
                    </Space>
                }
            >
                <Table
                    columns={columns}
                    dataSource={tags}
                    rowKey="id"
                    loading={loading}
                    pagination={{
                        pageSize: pageSize,
                        showSizeChanger: true,
                        pageSizeOptions: ['10', '20', '50', '100'],
                        onShowSizeChange: (current, size) => {
                            setPageSize(size);
                        },
                        showTotal: (total) => `共 ${total} 个标签`
                    }}
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
                        name="is_root_tag"
                        valuePropName="checked"
                    >
                        <Checkbox
                            checked={isRootTag}
                            onChange={(e) => setIsRootTag(e.target.checked)}
                        >
                            设为根标签（Root Tag）
                        </Checkbox>
                    </Form.Item>

                    <Form.Item
                        name="parent_id"
                        label="父标签"
                        style={{ display: isRootTag ? 'none' : 'block' }}
                    >
                        <Select
                            placeholder="选择父标签（可选）"
                            allowClear
                            disabled={isRootTag}
                        >
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