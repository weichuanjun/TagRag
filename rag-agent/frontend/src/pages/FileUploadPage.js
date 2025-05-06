import React, { useState } from 'react';
import { Upload, Button, message, Card, Typography, Space, List, Spin } from 'antd';
import { UploadOutlined, InboxOutlined, FileOutlined, FileExcelOutlined, FilePdfOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Dragger } = Upload;
const { Title, Text } = Typography;

const FileUploadPage = () => {
    const [uploading, setUploading] = useState(false);
    const [uploadedFiles, setUploadedFiles] = useState([]);

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
        // 检查文件类型
        const allowedTypes = [
            'text/plain',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'application/pdf',
            'text/csv'
        ];

        const isAllowedType = allowedTypes.includes(file.type);
        if (!isAllowedType) {
            message.error('仅支持上传 TXT, Excel, PDF 和 CSV 文件！');
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
        setUploading(true);

        const formData = new FormData();
        formData.append('file', file);

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
                url: response.data.file_path
            }]);

            if (onSuccess) {
                onSuccess(response, file);
            }
        } catch (error) {
            message.error(`${file.name} 上传失败：${error.message}`);
            if (onError) {
                onError(error);
            }
        } finally {
            setUploading(false);
        }
    };

    // 加载已上传的文件
    const loadUploadedFiles = async () => {
        try {
            const response = await axios.get('/documents');

            // 转换格式
            const files = response.data.documents.map(doc => ({
                uid: doc.id,
                name: doc.id,
                status: 'done',
                url: doc.path
            }));

            setUploadedFiles(files);
        } catch (error) {
            console.error('Error loading documents:', error);
            message.error('加载文档列表失败');
        }
    };

    // 组件加载时获取文件列表
    React.useEffect(() => {
        loadUploadedFiles();
    }, []);

    return (
        <div>
            <Title level={4}>上传文档</Title>
            <Text type="secondary">
                支持上传 TXT, Excel, PDF 和 CSV 文件，上传后系统会自动处理并添加到知识库
            </Text>

            <Card style={{ marginTop: 16 }}>
                <Dragger
                    name="file"
                    multiple={false}
                    beforeUpload={beforeUpload}
                    customRequest={customUpload}
                    showUploadList={false}
                    disabled={uploading}
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
            </Card>

            <Card title="已上传文档" style={{ marginTop: 24 }}>
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
                                    <Button type="link" onClick={() => message.info('此功能尚未实现')}>
                                        查看
                                    </Button>
                                ]}
                            >
                                <List.Item.Meta
                                    avatar={getFileIcon(item.name)}
                                    title={item.name}
                                    description={`上传于 ${new Date().toLocaleString()}`}
                                />
                            </List.Item>
                        )}
                    />
                )}
            </Card>
        </div>
    );
};

export default FileUploadPage; 