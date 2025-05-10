import React, { useState, useEffect } from 'react';
import { Table, Card, Button, Typography, Tag, Space, Modal, Spin, message } from 'antd';
import {
    FileOutlined,
    ReloadOutlined,
    DeleteOutlined,
    FileExcelOutlined,
    FilePdfOutlined,
    FileTextOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

const DocumentsPage = () => {
    const [documents, setDocuments] = useState([]);
    const [loading, setLoading] = useState(false);
    const [deleteModalVisible, setDeleteModalVisible] = useState(false);
    const [selectedDocument, setSelectedDocument] = useState(null);

    // 获取文档列表
    const fetchDocuments = async () => {
        setLoading(true);

        try {
            const response = await axios.get('/documents');
            setDocuments(response.data.documents || []);
        } catch (error) {
            console.error('Error fetching documents:', error);
            message.error('获取文档列表失败');
        } finally {
            setLoading(false);
        }
    };

    // 组件加载时获取文档列表
    useEffect(() => {
        fetchDocuments();
    }, []);

    // 获取文件图标
    const getFileIcon = (fileName) => {
        const extension = fileName.split('.').pop().toLowerCase();

        if (extension === 'xlsx' || extension === 'xls') {
            return <FileExcelOutlined style={{ fontSize: 18, color: '#52c41a' }} />;
        } else if (extension === 'pdf') {
            return <FilePdfOutlined style={{ fontSize: 18, color: '#ff4d4f' }} />;
        } else if (extension === 'txt') {
            return <FileTextOutlined style={{ fontSize: 18, color: '#faad14' }} />;
        } else {
            return <FileOutlined style={{ fontSize: 18, color: '#1890ff' }} />;
        }
    };

    // 获取文件类型标签
    const getFileTypeTag = (fileName) => {
        const extension = fileName.split('.').pop().toLowerCase();

        switch (extension) {
            case 'xlsx':
            case 'xls':
                return <Tag color="green">Excel</Tag>;
            case 'pdf':
                return <Tag color="red">PDF</Tag>;
            case 'txt':
                return <Tag color="gold">TXT</Tag>;
            case 'csv':
                return <Tag color="purple">CSV</Tag>;
            default:
                return <Tag color="blue">{extension.toUpperCase()}</Tag>;
        }
    };

    // 显示删除确认对话框
    const showDeleteModal = (document) => {
        setSelectedDocument(document);
        setDeleteModalVisible(true);
    };

    // 删除文档
    const handleDeleteDocument = async () => {
        if (!selectedDocument) return;

        try {
            await axios.delete(`/documents/${selectedDocument.id}`);
            message.success(`文档 ${selectedDocument.id} 已删除`);
            fetchDocuments();
        } catch (error) {
            console.error('Error deleting document:', error);
            message.error('删除文档失败');
        } finally {
            setDeleteModalVisible(false);
            setSelectedDocument(null);
        }
    };

    // 表格列定义
    const columns = [
        {
            title: '文件名',
            dataIndex: 'id',
            key: 'id',
            render: (text) => (
                <Space>
                    {getFileIcon(text)}
                    <Text>{text}</Text>
                </Space>
            )
        },
        {
            title: '类型',
            dataIndex: 'id',
            key: 'type',
            render: (text) => getFileTypeTag(text)
        },
        {
            title: '路径',
            dataIndex: 'path',
            key: 'path',
            ellipsis: true
        },
        {
            title: '块数量',
            dataIndex: 'chunks_count',
            key: 'chunks_count',
            sorter: (a, b) => a.chunks_count - b.chunks_count
        },
        {
            title: '添加时间',
            dataIndex: 'added_at',
            key: 'added_at',
            sorter: (a, b) => new Date(a.added_at) - new Date(b.added_at)
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Space size="middle">
                    <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => showDeleteModal(record)}
                    >
                        删除
                    </Button>
                </Space>
            )
        }
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Title level={4}>文档库管理</Title>
                <Button
                    icon={<ReloadOutlined />}
                    onClick={fetchDocuments}
                    loading={loading}
                >
                    刷新
                </Button>
            </div>

            <Card>
                <Table
                    columns={columns}
                    dataSource={documents}
                    rowKey="id"
                    loading={loading}
                    pagination={{
                        defaultPageSize: 10,
                        showSizeChanger: true,
                        pageSizeOptions: ['10', '20', '50'],
                        showTotal: (total) => `共 ${total} 条记录`
                    }}
                />
            </Card>

            <Modal
                title="删除文档"
                open={deleteModalVisible}
                onOk={handleDeleteDocument}
                onCancel={() => setDeleteModalVisible(false)}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
            >
                <p>确定要删除文档 <strong>{selectedDocument?.id}</strong> 吗？此操作不可恢复。</p>
            </Modal>
        </div>
    );
};

export default DocumentsPage; 