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
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60, sorter: (a, b) => a.id - b.id, defaultSortOrder: 'descend' },
        { title: '文件名', dataIndex: 'source', key: 'source', ellipsis: true },
        {
            title: '知识库',
            dataIndex: 'knowledge_base_name',
            key: 'knowledge_base_name',
            render: (name) => name || 'N/A',
        },
        {
            title: '标签',
            key: 'tags',
            dataIndex: 'tags',
            render: (tagsArray, record) => (
                <Space direction="vertical" style={{ width: '100%' }}>
                    <div>
                        {Array.isArray(tagsArray) && tagsArray.length > 0 ?
                            tagsArray.map(tag => (
                                <Tag color={tag.color || 'blue'} key={tag.id} style={{ marginBottom: '4px' }}>
                                    {tag.name}
                                </Tag>
                            ))
                            : <Text type="secondary" italic>无标签</Text>
                        }
                    </div>
                    {record && record.id && (
                        <Button
                            icon={<TagOutlined />}
                            size="small"
                            onClick={() => openTagModal(record)}
                            style={{ marginTop: '4px' }}
                        >
                            编辑标签
                        </Button>
                    )}
                </Space>
            ),
        },
        { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
        { title: '处理时间', dataIndex: 'processed_at', key: 'processed_at', render: (text) => text ? new Date(text).toLocaleString() : 'N/A', width: 150 },
        {
            title: '操作',
            key: 'actions',
            width: 220,
            render: (text, record) => (
                <Space>
                    <Button icon={<EyeOutlined />} onClick={() => handleViewChunks(record)}>查看分块</Button>
                    <Popconfirm
                        title={`确定删除文档 "${record.source}"?`}
                        onConfirm={() => handleDeleteDocument(record.id)}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                    >
                        <Button danger icon={<DeleteOutlined />}>删除</Button>
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
            <Title level={4}>文档上传与管理</Title>
            <Row gutter={[16, 16]}>
                <Col xs={24} md={24}>
                    <Card title="通过文件上传">
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Select
                                style={{ width: '100%' }}
                                placeholder="选择知识库"
                                value={selectedKnowledgeBase}
                                onChange={setSelectedKnowledgeBase}
                                loading={kbLoading}
                            >
                                {knowledgeBases.map(kb => <Option key={kb.id} value={kb.id}>{kb.name}</Option>)}
                            </Select>
                            <InputNumber addonBefore="分块大小" min={100} max={5000} value={chunkSize} onChange={setChunkSize} style={{ width: '100%' }} />
                            <Dragger
                                key={draggerKey}
                                name="file"
                                multiple={true}
                                beforeUpload={beforeUpload}
                                customRequest={customUpload}
                                showUploadList={true}
                                disabled={uploading || !selectedKnowledgeBase}
                            >
                                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                                <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
                                <p className="ant-upload-hint">支持单个或批量上传。支持TXT, PDF, Excel, Markdown等。</p>
                            </Dragger>
                            {uploading && <Spin tip="上传处理中..." style={{ display: 'block', marginTop: '10px' }} />}
                        </Space>
                    </Card>
                </Col>
            </Row>

            <Divider>已处理文档列表</Divider>

            <Table
                columns={documentTableColumns}
                dataSource={documents}
                loading={loadingDocuments}
                rowKey="id"
                bordered
                size="small"
                style={{ marginTop: 20 }}
                title={() => <Button onClick={fetchDocuments} loading={loadingDocuments}>刷新列表</Button>}
            />

            {/* 分块信息模态框 */}
            <Modal
                title={`文档分块详情: ${selectedDocForChunks?.source || 'N/A'} (ID: ${selectedDocForChunks?.id})`}
                visible={isChunkModalVisible}
                onCancel={handleCancelChunkModal}
                footer={[<Button key="back" onClick={handleCancelChunkModal}>关闭</Button>]}
                width="85%"
                destroyOnClose
            >
                {chunksLoading ? (
                    <div style={{ textAlign: 'center', padding: '50px' }}><Spin tip="加载分块信息..." /></div>
                ) : (
                    <List
                        itemLayout="vertical"
                        size="small"
                        dataSource={selectedDocChunks}
                        pagination={{ pageSize: 3, size: 'small' }}
                        renderItem={(chunk) => (
                            <List.Item key={chunk.chunk_index} style={{ background: '#fafafa', marginBottom: '8px', padding: '12px', borderRadius: '4px' }}>
                                <List.Item.Meta
                                    title={<Text strong>块 {chunk.chunk_index} (Chunk ID: {chunk.id})</Text>}
                                    description={
                                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                                            <Space wrap>
                                                <Text type="secondary">Token数: {chunk.token_count || 'N/A'}</Text>
                                                <Text type="secondary">结构类型: {chunk.structural_type || 'N/A'}</Text>
                                            </Space>
                                            <div><Text strong style={{ marginRight: 8 }}>标签:</Text>{renderChunkTagsInModal(chunk.metadata)}</div>
                                        </Space>
                                    }
                                />
                                <Paragraph ellipsis={{ rows: 4, expandable: true, symbol: '展开' }} style={{ maxHeight: '150px', overflowY: 'auto', background: '#fff', padding: '8px', border: '1px solid #eee' }}>
                                    {chunk.content}
                                </Paragraph>
                            </List.Item>
                        )}
                    />
                )}
            </Modal>

            {/* 手动编辑标签模态框 (复用您现有的) */}
            <Modal
                title={`编辑文档 #${selectedDocumentIdForTagging} 的标签`}
                visible={tagModalVisible}
                onOk={saveDocumentTags}
                onCancel={() => setTagModalVisible(false)}
                confirmLoading={tagsLoading}
            >
                <Select
                    mode="multiple"
                    allowClear
                    style={{ width: '100%' }}
                    placeholder="选择或搜索标签"
                    value={currentSelectedTagsForDoc}
                    onChange={handleTagChangeForModal}
                    loading={tagsLoading}
                    filterOption={(input, option) =>
                        option.children.toLowerCase().includes(input.toLowerCase())
                    }
                >
                    {allTags.map(tag => (
                        <Option key={tag.id} value={tag.id}>{tag.name}</Option>
                    ))}
                </Select>
            </Modal>

        </div>
    );
};

export default FileUploadPage;