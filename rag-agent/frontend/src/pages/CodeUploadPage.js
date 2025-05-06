import React, { useState } from 'react';
import { Form, Input, Button, Upload, message, Alert, Card, Typography, Steps, Divider } from 'antd';
import { UploadOutlined, GithubOutlined, InfoCircleOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;
const { Step } = Steps;

const CodeUploadPage = () => {
    const [repoUrl, setRepoUrl] = useState('');
    const [loading, setLoading] = useState(false);
    const [uploadSuccess, setUploadSuccess] = useState(false);
    const [uploadedPath, setUploadedPath] = useState('');

    const handleRepoUrlChange = (e) => {
        setRepoUrl(e.target.value);
    };

    const handleSubmit = async () => {
        if (!repoUrl) {
            message.error('请输入Git仓库URL');
            return;
        }

        setLoading(true);
        try {
            const response = await axios.post('/upload/code', {
                repo_url: repoUrl
            });

            if (response.data.status === '正在分析代码，请稍候') {
                setUploadSuccess(true);
                setUploadedPath(response.data.code_path);
                message.success('代码已上传，正在分析中');
            } else {
                message.warning('代码上传成功，但分析可能未完成');
            }
        } catch (error) {
            console.error('上传代码库失败:', error);
            message.error('上传代码库失败，请重试');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <Title level={4}>代码分析</Title>
            <Divider />

            <Card style={{ marginBottom: 24 }}>
                <Title level={5}>如何使用代码分析功能</Title>
                <Steps direction="vertical" size="small" current={-1}>
                    <Step
                        title="上传代码"
                        description="输入Git仓库URL，系统将克隆并分析代码库。"
                        icon={<GithubOutlined />}
                    />
                    <Step
                        title="开启代码分析"
                        description="在聊天页面启用代码分析开关。"
                        icon={<InfoCircleOutlined />}
                    />
                    <Step
                        title="提问"
                        description="询问关于代码的问题，例如某个字段的用途、影响范围等。"
                    />
                </Steps>

                <Alert
                    style={{ marginTop: 16 }}
                    message="代码分析小提示"
                    description={
                        <div>
                            <Paragraph>您可以问这些问题:</Paragraph>
                            <ul>
                                <li>"models.py中的用户字段有哪些？"</li>
                                <li>"配置文件在哪里？"</li>
                                <li>"数据库连接如何设置？"</li>
                                <li>"用户认证流程是怎样的？"</li>
                            </ul>
                        </div>
                    }
                    type="info"
                    showIcon
                />
            </Card>

            <Form layout="vertical">
                <Form.Item
                    label="Git仓库URL"
                    extra="输入GitHub、GitLab或任何Git仓库的URL，系统将克隆并分析代码"
                >
                    <Input
                        placeholder="例如：https://github.com/username/repo"
                        value={repoUrl}
                        onChange={handleRepoUrlChange}
                        prefix={<GithubOutlined />}
                    />
                </Form.Item>

                <Form.Item>
                    <Button
                        type="primary"
                        onClick={handleSubmit}
                        loading={loading}
                        icon={<UploadOutlined />}
                    >
                        上传代码库
                    </Button>
                </Form.Item>
            </Form>

            {uploadSuccess && (
                <Alert
                    message="代码库上传成功"
                    description={
                        <div>
                            <p>代码库已成功上传并正在分析中，路径为：{uploadedPath}</p>
                            <p>分析完成后，您可以在聊天页面启用"代码分析"开关，然后提问关于此代码库的问题。</p>
                        </div>
                    }
                    type="success"
                    showIcon
                />
            )}
        </div>
    );
};

export default CodeUploadPage; 