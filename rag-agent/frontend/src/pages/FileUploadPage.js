import React, { useState, useEffect } from 'react';
import { Upload, Button, message, Card, Typography, Space, List, Spin, Select, InputNumber, Row, Col, Input, Modal, Tag } from 'antd';
import { InboxOutlined, FileOutlined, FileExcelOutlined, FilePdfOutlined, DatabaseOutlined, RobotOutlined, TagOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Dragger } = Upload;
const { Title, Text } = Typography;
const { Option } = Select;

const FileUploadPage = () => {
    const [uploading, setUploading] = useState(false);
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [kbLoading, setKbLoading] = useState(false);
    const [chunkSize, setChunkSize] = useState(1000);
    const [localFilePath, setLocalFilePath] = useState('');
    const [tags, setTags] = useState([]);
    const [tagsLoading, setTagsLoading] = useState(false);
    const [selectedDocumentId, setSelectedDocumentId] = useState(null);
    const [tagModalVisible, setTagModalVisible] = useState(false);
    const [selectedTags, setSelectedTags] = useState([]);
    const [analyzeLoading, setAnalyzeLoading] = useState(false);

    // 获取知识库列表
    const fetchKnowledgeBases = async () => {
        setKbLoading(true);
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data || []);
            if (response.data && response.data.length > 0) {
                setSelectedKnowledgeBase(response.data[0].id);
            }
        } catch (error) {
            console.error('获取知识库列表失败:', error);
            message.error('获取知识库列表失败');
        } finally {
            setKbLoading(false);
        }
    };

    // 加载标签列表
    const fetchTags = async () => {
        setTagsLoading(true);
        try {
            const response = await axios.get('/tags');
            setTags(response.data.tags || []);
        } catch (error) {
            console.error('获取标签列表失败:', error);
        } finally {
            setTagsLoading(false);
        }
    };

    // 加载已上传的文件
    const loadUploadedFiles = async () => {
        try {
            if (selectedKnowledgeBase) {
                // 获取知识库中的文档
                const response = await axios.get(`/knowledge-bases/${selectedKnowledgeBase}/documents`);
                const docs = response.data || [];

                // 获取每个文档的标签
                const docsWithTags = await Promise.all(docs.map(async (doc) => {
                    try {
                        const tagsResponse = await axios.get(`/tags/document/${doc.id}`);
                        return {
                            ...doc,
                            uid: doc.id,
                            name: doc.name,
                            status: 'done',
                            url: doc.path,
                            knowledge_base_id: selectedKnowledgeBase,
                            chunks_count: doc.chunks_count,
                            added_at: doc.added_at,
                            tags: tagsResponse.data.tags || []
                        };
                    } catch (error) {
                        console.error(`获取文档 ${doc.id} 的标签失败:`, error);
                        return {
                            ...doc,
                            uid: doc.id,
                            name: doc.name,
                            status: 'done',
                            url: doc.path,
                            knowledge_base_id: selectedKnowledgeBase,
                            chunks_count: doc.chunks_count,
                            added_at: doc.added_at,
                            tags: []
                        };
                    }
                }));

                setUploadedFiles(docsWithTags);
            } else {
                // 获取所有文档
                const response = await axios.get('/documents');
                const docs = response.data.documents || [];

                // 转换格式
                const files = docs.map(doc => ({
                    uid: doc.id,
                    name: doc.id,
                    status: 'done',
                    url: doc.path,
                    chunks_count: doc.chunks_count,
                    added_at: doc.added_at,
                    tags: []
                }));

                setUploadedFiles(files);
            }
        } catch (error) {
            console.error('Error loading documents:', error);
            message.error('加载文档列表失败');
        }
    };

    // 组件加载时获取知识库列表和标签列表
    useEffect(() => {
        fetchKnowledgeBases();
        fetchTags();
        loadUploadedFiles();
    }, []);  // eslint-disable-line react-hooks/exhaustive-deps

    // 当选择的知识库变化时，重新加载文档列表
    useEffect(() => {
        if (selectedKnowledgeBase) {
            // 添加少量延迟，避免频繁重复请求
            const timer = setTimeout(() => {
                loadUploadedFiles();
            }, 300);

            return () => clearTimeout(timer);
        }
    }, [selectedKnowledgeBase]);

    // 自定义文件图标
    const getFileIcon = (fileName) => {
        const extension = fileName.split('.').pop().toLowerCase();

        if (extension === 'xlsx' || extension === 'xls') {
            return <FileExcelOutlined style={{ fontSize: 24, color: '#52c41a' }} />;
        } else if (extension === 'pdf') {
            return <FilePdfOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />;
        } else {
            return <FileOutlined style={{ fontSize: 24, color: '#1890ff' }} />;
        }
    };

    // 处理上传前的逻辑
    const beforeUpload = (file) => {
        // 检查是否选择了知识库
        if (!selectedKnowledgeBase) {
            message.error('请先选择知识库！');
            return false;
        }

        // 检查文件类型
        const allowedTypes = [
            'text/plain',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'application/pdf',
            'text/csv',
            'text/markdown'
        ];

        const isAllowedType = allowedTypes.includes(file.type);
        if (!isAllowedType) {
            message.error('仅支持上传 TXT, Markdown, Excel, PDF 和 CSV 文件！');
        }

        // 检查文件大小
        const isLt10M = file.size / 1024 / 1024 < 10;
        if (!isLt10M) {
            message.error('文件必须小于 10MB！');
        }

        return isAllowedType && isLt10M;
    };

    // 处理自定义上传
    const customUpload = async ({ file, onSuccess, onError }) => {
        if (!selectedKnowledgeBase) {
            message.error('请先选择知识库！');
            return;
        }

        setUploading(true);

        const formData = new FormData();
        formData.append('file', file);
        formData.append('knowledge_base_id', selectedKnowledgeBase);
        formData.append('chunk_size', chunkSize);

        try {
            const response = await axios.post('/upload/file', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });

            message.success(`${file.name} 上传成功！`);

            // 添加到已上传文件列表
            setUploadedFiles(prev => [...prev, {
                uid: response.data.saved_as,
                name: file.name,
                status: 'done',
                url: response.data.file_path,
                knowledge_base_id: selectedKnowledgeBase
            }]);

            if (onSuccess) {
                onSuccess(response, file);
            }

            // 刷新文件列表
            loadUploadedFiles();
        } catch (error) {
            message.error(`${file.name} 上传失败：${error.message}`);
            if (onError) {
                onError(error);
            }
        } finally {
            setUploading(false);
        }
    };

    // 处理本地文件路径上传
    const handleLocalFileUpload = async () => {
        if (!selectedKnowledgeBase) {
            message.error('请先选择知识库！');
            return;
        }

        if (!localFilePath.trim()) {
            message.error('请输入本地文件路径！');
            return;
        }

        setUploading(true);

        try {
            const response = await axios.post('/upload-document', {
                file_path: localFilePath,
                knowledge_base_id: selectedKnowledgeBase,
                chunk_size: chunkSize
            });

            message.success(`文件上传成功！已处理 ${response.data.chunks_count} 个文本块`);

            // 刷新文件列表
            loadUploadedFiles();
        } catch (error) {
            console.error('上传失败:', error);
            message.error(`上传失败：${error.response?.data?.detail || error.message}`);
        } finally {
            setUploading(false);
        }
    };

    // 打开标签选择对话框
    const openTagModal = (documentId) => {
        setSelectedDocumentId(documentId);

        // 找到当前文档的标签
        const document = uploadedFiles.find(file => file.uid === documentId);
        if (document && document.tags) {
            setSelectedTags(document.tags.map(tag => tag.id));
        } else {
            setSelectedTags([]);
        }

        setTagModalVisible(true);
    };

    // 处理标签选择变更
    const handleTagChange = (tagIds) => {
        setSelectedTags(tagIds);
    };

    // 保存文档标签
    const saveDocumentTags = async () => {
        try {
            await axios.post(`/tags/document/${selectedDocumentId}`, selectedTags);

            message.success('标签保存成功');
            setTagModalVisible(false);

            // 重新加载文档列表以获取更新的标签
            loadUploadedFiles();
        } catch (error) {
            console.error('保存标签失败:', error);
            message.error('保存标签失败');
        }
    };

    // 使用AI分析文档内容，提取标签
    const analyzeDocument = async (documentId) => {
        setAnalyzeLoading(true);
        setSelectedDocumentId(documentId);
        try {
            const response = await axios.post(`/tags/analyze-document/${documentId}`);

            if (response.data.success) {
                message.success('AI分析成功');
                // 重新加载文档列表以获取更新的标签
                loadUploadedFiles();
                // 同时更新标签列表，因为可能创建了新标签
                fetchTags();
            } else {
                message.error('AI分析失败');
            }
        } catch (error) {
            console.error('AI分析文档失败:', error);
            message.error('AI分析文档失败');
        } finally {
            setAnalyzeLoading(false);
        }
    };

    // 备用的AI分析方法，使用测试路由
    const analyzeDocumentAlt = async (documentId) => {
        setAnalyzeLoading(true);
        setSelectedDocumentId(documentId);
        try {
            console.log(`尝试使用备用路由分析文档ID: ${documentId}`);
            const response = await axios.post(`/analyze-doc-test/${documentId}`);

            if (response.data.success) {
                message.success('测试路由访问成功');
                console.log('测试路由结果:', response.data);

                // 尝试通过原始路由进行完整分析
                try {
                    const fullResponse = await axios.post(`/tags/analyze-document/${documentId}`);
                    if (fullResponse.data.success) {
                        message.success('AI分析成功');
                        // 重新加载文档列表以获取更新的标签
                        loadUploadedFiles();
                        // 同时更新标签列表，因为可能创建了新标签
                        fetchTags();
                    }
                } catch (fullError) {
                    console.error('原始分析路由仍然失败:', fullError);
                    message.error('原始分析路由仍然失败, 但测试路由可以访问');
                }
            } else {
                message.error('测试路由分析失败');
            }
        } catch (error) {
            console.error('测试路由分析失败:', error);
            message.error(`测试路由分析失败: ${error.message}`);
        } finally {
            setAnalyzeLoading(false);
        }
    };

    // 直接分析文档的方法，完全绕过路由器实现
    const analyzeDocumentDirect = async (documentId) => {
        setAnalyzeLoading(true);
        setSelectedDocumentId(documentId);
        try {
            console.log(`使用直接分析路由处理文档ID: ${documentId}`);
            const response = await axios.post(`/direct/analyze-document/${documentId}`);

            if (response.data.success) {
                message.success('文档直接分析成功');
                console.log('直接分析结果:', response.data);

                // 重新加载文档列表以获取更新的标签
                loadUploadedFiles();
                // 同时更新标签列表，因为可能创建了新标签
                fetchTags();
            } else {
                message.error('直接分析失败');
            }
        } catch (error) {
            console.error('直接分析文档失败:', error);
            message.error(`直接分析文档失败: ${error.message}`);
        } finally {
            setAnalyzeLoading(false);
        }
    };

    // 尝试所有分析方法
    const analyzeDocumentAll = async (documentId) => {
        // 首先尝试直接分析
        try {
            await analyzeDocumentDirect(documentId);
            return;
        } catch (error) {
            console.error('直接分析失败，尝试下一种方法...');
        }

        // 然后尝试测试路由
        try {
            await analyzeDocumentAlt(documentId);
            return;
        } catch (error) {
            console.error('测试路由分析失败，尝试下一种方法...');
        }

        // 最后尝试原始方法
        try {
            await analyzeDocument(documentId);
        } catch (error) {
            console.error('所有分析方法都失败了');
            message.error('所有分析方法都失败了');
        }
    };

    return (
        <div>
            <Title level={4}>上传文档</Title>
            <Text type="secondary">
                支持上传 TXT, Markdown, Excel, PDF 和 CSV 文件，上传后系统会自动处理并添加到知识库
            </Text>

            <Card style={{ marginTop: 16 }}>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={12}>
                        <Space>
                            <Text strong>选择知识库:</Text>
                            <Select
                                style={{ width: 200 }}
                                loading={kbLoading}
                                value={selectedKnowledgeBase}
                                onChange={setSelectedKnowledgeBase}
                                placeholder="选择知识库"
                            >
                                {knowledgeBases.map(kb => (
                                    <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                                ))}
                            </Select>
                        </Space>
                    </Col>
                    <Col span={12}>
                        <Space>
                            <Text strong>文本块大小:</Text>
                            <InputNumber
                                min={200}
                                max={2000}
                                defaultValue={1000}
                                onChange={value => setChunkSize(value)}
                            />
                        </Space>
                    </Col>
                </Row>

                <Dragger
                    name="file"
                    multiple={false}
                    beforeUpload={beforeUpload}
                    customRequest={customUpload}
                    showUploadList={false}
                    disabled={uploading || !selectedKnowledgeBase}
                >
                    <p className="ant-upload-drag-icon">
                        <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
                    <p className="ant-upload-hint">
                        单次上传一个文件，支持 Excel 自动转换为 Markdown 格式
                    </p>
                    {uploading && (
                        <div style={{ marginTop: 16 }}>
                            <Spin tip="上传处理中..." />
                        </div>
                    )}
                </Dragger>

                <div style={{ marginTop: 16 }}>
                    <Row gutter={16}>
                        <Col span={18}>
                            <Input
                                placeholder="输入本地文件路径，例如：/path/to/your/file.txt"
                                value={localFilePath}
                                onChange={e => setLocalFilePath(e.target.value)}
                                disabled={uploading}
                            />
                        </Col>
                        <Col span={6}>
                            <Button
                                type="primary"
                                onClick={handleLocalFileUpload}
                                loading={uploading}
                                disabled={!selectedKnowledgeBase}
                                block
                            >
                                上传本地文件
                            </Button>
                        </Col>
                    </Row>
                </div>
            </Card>

            <Card title="已上传文档" style={{ marginTop: 24 }} extra={
                <Button type="primary" onClick={loadUploadedFiles}>刷新</Button>
            }>
                {uploadedFiles.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <Text type="secondary">暂无已上传文档</Text>
                    </div>
                ) : (
                    <List
                        itemLayout="horizontal"
                        dataSource={uploadedFiles}
                        renderItem={item => (
                            <List.Item
                                actions={[
                                    <Button type="link" onClick={() => openTagModal(item.uid)} icon={<TagOutlined />}>
                                        管理标签
                                    </Button>,
                                    <Button
                                        type="link"
                                        onClick={() => analyzeDocumentAll(item.uid)}
                                        icon={<RobotOutlined />}
                                        loading={analyzeLoading && selectedDocumentId === item.uid}
                                    >
                                        AI分析(所有方法)
                                    </Button>
                                ]}
                            >
                                <List.Item.Meta
                                    avatar={getFileIcon(item.name)}
                                    title={item.name}
                                    description={
                                        <>
                                            <div>块数量: {item.chunks_count || '未知'} | 上传于: {item.added_at || new Date().toLocaleString()}</div>
                                            <div style={{ marginTop: 8 }}>
                                                {(item.tags && item.tags.length > 0) ? (
                                                    <Space size={[0, 4]} wrap>
                                                        {item.tags.map(tag => (
                                                            <Tag color={tag.color} key={tag.id}>{tag.name}</Tag>
                                                        ))}
                                                    </Space>
                                                ) : (
                                                    <Text type="secondary">无标签</Text>
                                                )}
                                            </div>
                                        </>
                                    }
                                />
                            </List.Item>
                        )}
                    />
                )}
            </Card>

            <Modal
                title="管理文档标签"
                open={tagModalVisible}
                onCancel={() => setTagModalVisible(false)}
                onOk={saveDocumentTags}
                okText="保存"
                cancelText="取消"
            >
                <div style={{ marginBottom: 16 }}>
                    <Text type="secondary">为文档选择适合的标签，或使用AI自动分析生成标签</Text>
                </div>
                <Select
                    mode="multiple"
                    style={{ width: '100%' }}
                    placeholder="请选择标签"
                    value={selectedTags}
                    onChange={handleTagChange}
                    loading={tagsLoading}
                    optionLabelProp="label"
                >
                    {tags.map(tag => (
                        <Option key={tag.id} value={tag.id} label={tag.name}>
                            <Tag color={tag.color}>{tag.name}</Tag>
                            {tag.description && <span style={{ marginLeft: 8, fontSize: '12px', color: '#999' }}>{tag.description}</span>}
                        </Option>
                    ))}
                </Select>
                <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <Button
                        type="primary"
                        icon={<RobotOutlined />}
                        onClick={() => {
                            setTagModalVisible(false);
                            analyzeDocumentAll(selectedDocumentId);
                        }}
                        loading={analyzeLoading}
                    >
                        使用AI分析生成标签(所有方法)
                    </Button>
                </div>
            </Modal>
        </div>
    );
};

export default FileUploadPage; 