import React, { useState, useEffect, useCallback } from 'react';
import { Upload, Button, message, Card, Typography, Space, List, Spin, Select, InputNumber, Row, Col, Input, Modal, Tag, Table, Popconfirm, Divider } from 'antd';
import { InboxOutlined, FileOutlined, FileExcelOutlined, FilePdfOutlined, DatabaseOutlined, RobotOutlined, TagOutlined, EyeOutlined, DeleteOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Dragger } = Upload;
const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const FileUploadPage = () => {
    const [uploading, setUploading] = useState(false);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [kbLoading, setKbLoading] = useState(false);
    const [chunkSize, setChunkSize] = useState(1000);
    const [draggerKey, setDraggerKey] = useState(0);

    // States for document list, tags, and chunk modal
    const [documents, setDocuments] = useState([]);
    const [tagsMap, setTagsMap] = useState({});
    const [loadingDocuments, setLoadingDocuments] = useState(false);
    const [isChunkModalVisible, setIsChunkModalVisible] = useState(false);
    const [selectedDocForChunks, setSelectedDocForChunks] = useState(null);
    const [selectedDocChunks, setSelectedDocChunks] = useState([]);
    const [chunksLoading, setChunksLoading] = useState(false);

    // States for existing manual tag editing modal
    const [allTags, setAllTags] = useState([]);
    const [tagsLoading, setTagsLoading] = useState(false);
    const [selectedDocumentIdForTagging, setSelectedDocumentIdForTagging] = useState(null);
    const [tagModalVisible, setTagModalVisible] = useState(false);
    const [currentSelectedTagsForDoc, setCurrentSelectedTagsForDoc] = useState([]);

    // 获取所有标签用于映射ID到名称及手动打标签的下拉列表
    const fetchAllTags = useCallback(async () => {
        setTagsLoading(true);
        try {
            const response = await axios.get('/tags');
            const tagsData = response.data?.tags || [];
            const map = tagsData.reduce((acc, tag) => {
                acc[tag.id] = tag;
                return acc;
            }, {});
            setTagsMap(map);
            setAllTags(tagsData);
        } catch (error) {
            console.error('获取所有标签列表失败:', error);
            message.error('获取所有标签列表失败');
        } finally {
            setTagsLoading(false);
        }
    }, []);

    // 获取文档列表 (replaces loadUploadedFiles)
    const fetchDocuments = useCallback(async () => {
        setLoadingDocuments(true);
        try {
            const response = await fetch('http://localhost:8000/documents/list');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // 更新数据源，确保每个文档对象都有 key 和 tags (即使是空数组)
            const formattedData = data.map(doc => ({
                ...doc,
                key: doc.id, // Ensure key is set to document id
                tags: doc.tags || [], // Ensure tags is an array
            }));
            setDocuments(formattedData);
        } catch (error) {
            message.error(`获取文档列表失败: ${error.message}`);
            console.error("获取文档列表失败:", error);
        } finally {
            setLoadingDocuments(false);
        }
    }, []);

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

    // 删除文档
    const handleDeleteDocument = async (documentId) => {
        try {
            await axios.delete(`/documents/${documentId}`);
            message.success(`文档 ID ${documentId} 已成功删除`);
            fetchDocuments();
        } catch (error) {
            console.error(`删除文档 ${documentId} 失败:`, error);
            message.error('删除文档失败');
        }
    };

    // 组件加载时获取知识库列表、所有标签和文档列表
    useEffect(() => {
        fetchKnowledgeBases();
        fetchAllTags();
        fetchDocuments();
    }, [fetchDocuments, fetchAllTags]);

    // 获取知识库列表
    const fetchKnowledgeBases = async () => {
        setKbLoading(true);
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data || []);
            if (response.data && response.data.length > 0 && !selectedKnowledgeBase) {
                setSelectedKnowledgeBase(response.data[0].id);
            }
        } catch (error) {
            console.error('获取知识库列表失败:', error);
            message.error('获取知识库列表失败');
        } finally {
            setKbLoading(false);
        }
    };

    // 上传前检查
    const beforeUpload = (file) => {
        if (!selectedKnowledgeBase) {
            message.error('请先选择知识库！');
            return Upload.LIST_IGNORE;
        }
        const allowedTypes = ['text/plain', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel', 'application/pdf', 'text/csv', 'text/markdown', '.html', '.htm', '.pptx', '.ppt', '.docx'];
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        const isAllowed = allowedTypes.includes(file.type) || allowedTypes.includes(fileExtension);
        if (!isAllowed) {
            message.error('不支持的文件类型!');
            return Upload.LIST_IGNORE;
        }
        const isLt10M = file.size / 1024 / 1024 < 20;
        if (!isLt10M) {
            message.error('文件必须小于 20MB！');
            return Upload.LIST_IGNORE;
        }
        return true;
    };

    // 自定义上传
    const customUpload = async ({ file, onSuccess, onError }) => {
        if (!selectedKnowledgeBase) {
            message.error('请先选择知识库！');
            onError(new Error('未选择知识库'));
            return;
        }
        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);
        formData.append('knowledge_base_id', selectedKnowledgeBase);
        formData.append('chunk_size', chunkSize);

        try {
            const response = await axios.post('/upload/file', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            message.success(`${file.name} 上传成功！后端处理中...`);
            if (onSuccess) onSuccess(response.data, file);
            fetchDocuments();
            setDraggerKey(prevKey => prevKey + 1);
        } catch (error) {
            message.error(`${file.name} 上传失败: ${error.response?.data?.detail || error.message}`);
            if (onError) onError(error);
        } finally {
            setUploading(false);
        }
    };

    // --- 块信息模态框相关 --- 
    const handleViewChunks = (document) => {
        setSelectedDocForChunks(document);
        setIsChunkModalVisible(true);
        fetchChunksForSelectedDoc(document.id);
    };
    const handleCancelChunkModal = () => {
        setIsChunkModalVisible(false);
        setSelectedDocForChunks(null);
        setSelectedDocChunks([]);
    };

    // --- 手动编辑文档标签相关 (复用并调整您已有的逻辑) ---
    const openTagModal = (document) => {
        setSelectedDocumentIdForTagging(document.id);
        setCurrentSelectedTagsForDoc(document.tags ? document.tags.map(tag => tag.id) : []);
        setTagModalVisible(true);
    };

    const handleTagChangeForModal = (selectedTagIds) => {
        setCurrentSelectedTagsForDoc(selectedTagIds);
    };

    const saveDocumentTags = async () => {
        if (!selectedDocumentIdForTagging) return;
        setTagsLoading(true);
        try {
            await axios.post(`/tags/document/${selectedDocumentIdForTagging}`, { tag_ids: currentSelectedTagsForDoc });
            message.success('文档标签更新成功!');
            setTagModalVisible(false);
            fetchDocuments();
        } catch (error) {
            message.error('更新文档标签失败: ' + (error.response?.data?.detail || error.message));
        } finally {
            setTagsLoading(false);
        }
    };

    // 表格列定义 (新的)
    const documentTableColumns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
            width: 60,
            sorter: (a, b) => a.id - b.id,
            defaultSortOrder: 'descend'
        },
        {
            title: '文件名',
            dataIndex: 'source',
            key: 'source',
            width: 240,
            ellipsis: false,
            render: (text) => (
                <div style={{
                    fontSize: '12px',
                    lineHeight: '1.4',
                    wordBreak: 'break-all',
                    wordWrap: 'break-word'
                }}>
                    {text}
                </div>
            )
        },
        {
            title: '标签',
            key: 'tags',
            dataIndex: 'tags',
            render: (tagsArray, record) => (
                <Space size={[0, 4]} wrap>
                    {Array.isArray(tagsArray) && tagsArray.length > 0 ?
                        tagsArray.map(tag => (
                            <Tag color={tag.color || 'blue'} key={tag.id}>
                                {tag.name}
                            </Tag>
                        ))
                        : <Text type="secondary" italic>无标签</Text>
                    }
                    <Button
                        icon={<TagOutlined />}
                        size="small"
                        type="text"
                        onClick={() => openTagModal(record)}
                    />
                </Space>
            ),
        },
        {
            title: '知识库',
            dataIndex: 'knowledge_base_name',
            key: 'knowledge_base_name',
            width: 120,
            render: (name) => name || 'N/A',
        },
        {
            title: '状态与时间',
            key: 'statusTime',
            width: 150,
            render: (_, record) => (
                <Space direction="vertical" size="small">
                    <Tag color={record.status === 'processed' ? 'green' : 'blue'}>
                        {record.status || 'N/A'}
                    </Tag>
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                        {record.processed_at ? new Date(record.processed_at).toLocaleString() : 'N/A'}
                    </Text>
                </Space>
            )
        },
        {
            title: '操作',
            key: 'actions',
            width: 80,
            align: 'center',
            render: (_, record) => (
                <Space>
                    <Button type="text" icon={<EyeOutlined />} onClick={() => handleViewChunks(record)} />
                    <Popconfirm
                        title={`确定删除文档 "${record.source}"?`}
                        onConfirm={() => handleDeleteDocument(record.id)}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                    >
                        <Button type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    // 渲染块的标签 (用于模态框)
    const renderChunkTagsInModal = (metadata) => {
        const tagIds = metadata?.tag_ids || [];
        if (!tagIds || tagIds.length === 0) return <Text type="secondary">无继承标签</Text>;
        return (
            <Space size={[0, 4]} wrap>
                {tagIds.map(tagId => {
                    const tagInfo = tagsMap[tagId];
                    return (
                        <Tag key={tagId} color={tagInfo?.color || '#8c8c8c'} icon={<TagOutlined />}>
                            {tagInfo?.name || `Tag ID: ${tagId}`}
                        </Tag>
                    );
                })}
            </Space>
        );
    };

    return (
        <div style={{ padding: '20px' }}>
            <Row gutter={[16, 16]}>
                <Col xs={24} md={24}>
                    <Card style={{ borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                        <Row gutter={16} align="middle">
                            <Col xs={24} md={16}>
                                <Select
                                    style={{ width: '100%' }}
                                    placeholder="选择知识库"
                                    value={selectedKnowledgeBase}
                                    onChange={setSelectedKnowledgeBase}
                                    loading={kbLoading}
                                >
                                    {knowledgeBases.map(kb => <Option key={kb.id} value={kb.id}>{kb.name}</Option>)}
                                </Select>
                            </Col>
                            <Col xs={24} md={8}>
                                <InputNumber addonBefore="分块大小" min={100} max={5000} value={chunkSize} onChange={setChunkSize} style={{ width: '100%' }} />
                            </Col>
                        </Row>
                        <div style={{ marginTop: '16px', minHeight: '120px', maxHeight: '180px' }}>
                            <Dragger
                                key={draggerKey}
                                name="file"
                                multiple={true}
                                beforeUpload={beforeUpload}
                                customRequest={customUpload}
                                showUploadList={true}
                                disabled={uploading || !selectedKnowledgeBase}
                                style={{
                                    padding: '10px 0',
                                    borderRadius: '8px',
                                    background: '#f9fafc'
                                }}
                                height={140}
                            >
                                <p className="ant-upload-drag-icon"><InboxOutlined style={{ color: '#4267B2', fontSize: '32px' }} /></p>
                                <p className="ant-upload-text" style={{ fontSize: '16px', fontWeight: '500', color: '#333' }}>点击或拖拽文件到此区域上传</p>
                                <p className="ant-upload-hint" style={{ padding: '0 40px', color: '#888', fontSize: '13px' }}>支持TXT, PDF, Excel, Markdown等</p>
                            </Dragger>
                            {uploading && <Spin tip="上传处理中..." style={{ display: 'block', marginTop: '10px' }} />}
                        </div>
                    </Card>
                </Col>
            </Row>

            <Divider style={{ margin: '24px 0 16px 0' }}>已处理文档列表</Divider>

            <div style={{ padding: '0 10px' }}>
                <Table
                    columns={documentTableColumns}
                    dataSource={documents}
                    loading={loadingDocuments}
                    rowKey="id"
                    bordered
                    size="small"
                    style={{
                        marginTop: 20,
                        borderRadius: '8px',
                        overflow: 'hidden',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
                    }}
                    title={() => (
                        <div style={{ padding: '8px 0' }}>
                            <Button
                                onClick={fetchDocuments}
                                loading={loadingDocuments}
                                type="primary"
                                size="small"
                                style={{ borderRadius: '4px' }}
                            >
                                刷新列表
                            </Button>
                        </div>
                    )}
                    scroll={{ x: 1000 }}
                    pagination={{
                        size: 'small',
                        showSizeChanger: true,
                        showTotal: (total) => `共 ${total} 条记录`
                    }}
                />
            </div>

            {/* 分块信息模态框 */}
            <Modal
                title={`文档分块详情: ${selectedDocForChunks?.source || 'N/A'}`}
                visible={isChunkModalVisible}
                onCancel={handleCancelChunkModal}
                footer={[<Button key="back" onClick={handleCancelChunkModal}>关闭</Button>]}
                width="80%"
                destroyOnClose
                bodyStyle={{ padding: '12px' }}
            >
                {chunksLoading ? (
                    <div style={{ textAlign: 'center', padding: '50px' }}><Spin tip="加载分块信息..." /></div>
                ) : (
                    <List
                        itemLayout="vertical"
                        size="small"
                        dataSource={selectedDocChunks}
                        pagination={{ pageSize: 5, size: 'small' }}
                        renderItem={(chunk) => (
                            <List.Item key={chunk.chunk_index} style={{ background: '#f7f9fc', marginBottom: '8px', padding: '12px', borderRadius: '8px' }}>
                                <List.Item.Meta
                                    title={<Text strong>块 {chunk.chunk_index}</Text>}
                                    description={
                                        <Row gutter={[8, 8]}>
                                            <Col span={24} md={12}>
                                                <Space>
                                                    <Tag color="cyan">Token: {chunk.token_count || 'N/A'}</Tag>
                                                    <Tag color="purple">类型: {chunk.structural_type || 'N/A'}</Tag>
                                                </Space>
                                            </Col>
                                            <Col span={24} md={12}>
                                                <Space align="start">
                                                    <TagOutlined style={{ marginTop: '4px' }} />
                                                    {renderChunkTagsInModal(chunk.metadata)}
                                                </Space>
                                            </Col>
                                        </Row>
                                    }
                                />
                                <Paragraph
                                    ellipsis={{ rows: 4, expandable: true, symbol: '展开' }}
                                    style={{
                                        maxHeight: '150px',
                                        overflowY: 'auto',
                                        background: '#fff',
                                        padding: '12px',
                                        border: '1px solid #eee',
                                        borderRadius: '6px',
                                        marginTop: '8px'
                                    }}
                                >
                                    {chunk.content}
                                </Paragraph>
                            </List.Item>
                        )}
                    />
                )}
            </Modal>

            {/* 手动编辑标签模态框 */}
            <Modal
                title={`编辑标签`}
                visible={tagModalVisible}
                onOk={saveDocumentTags}
                onCancel={() => setTagModalVisible(false)}
                confirmLoading={tagsLoading}
                width={500}
            >
                <Space direction="vertical" style={{ width: '100%' }}>
                    <Text type="secondary">为文档选择标签：</Text>
                    <Select
                        mode="multiple"
                        allowClear
                        style={{ width: '100%' }}
                        placeholder="选择或搜索标签"
                        value={currentSelectedTagsForDoc}
                        onChange={handleTagChangeForModal}
                        loading={tagsLoading}
                        optionFilterProp="children"
                        filterOption={(input, option) =>
                            option.children.toLowerCase().includes(input.toLowerCase())
                        }
                    >
                        {allTags.map(tag => (
                            <Option key={tag.id} value={tag.id}>{tag.name}</Option>
                        ))}
                    </Select>
                    <div style={{ marginTop: '12px' }}>
                        <Text type="secondary">已选择 {currentSelectedTagsForDoc.length} 个标签</Text>
                    </div>
                </Space>
            </Modal>

        </div>
    );
};

export default FileUploadPage;