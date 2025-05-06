import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
    UploadOutlined,
    MessageOutlined,
    FolderOutlined,
    CodeOutlined,
} from '@ant-design/icons';

// 页面组件
import ChatPage from './pages/ChatPage';
import FileUploadPage from './pages/FileUploadPage';
import CodeUploadPage from './pages/CodeUploadPage';
import DocumentsPage from './pages/DocumentsPage';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

function App() {
    return (
        <Layout style={{ height: '100vh' }}>
            <Header style={{ padding: '0 20px', background: '#001529' }}>
                <div style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
                    <Title level={3} style={{ margin: 0, color: 'white' }}>
                        RAG Agent
                    </Title>
                </div>
            </Header>
            <Layout>
                <Sider width={200} style={{ background: '#fff' }}>
                    <Menu
                        mode="inline"
                        defaultSelectedKeys={['chat']}
                        style={{ height: '100%', borderRight: 0 }}
                    >
                        <Menu.Item key="chat" icon={<MessageOutlined />}>
                            <Link to="/">聊天</Link>
                        </Menu.Item>
                        <Menu.Item key="upload" icon={<UploadOutlined />}>
                            <Link to="/upload">上传文件</Link>
                        </Menu.Item>
                        <Menu.Item key="code" icon={<CodeOutlined />}>
                            <Link to="/code">代码分析</Link>
                        </Menu.Item>
                        <Menu.Item key="documents" icon={<FolderOutlined />}>
                            <Link to="/documents">文档库</Link>
                        </Menu.Item>
                    </Menu>
                </Sider>
                <Layout style={{ padding: '0 24px 24px' }}>
                    <Content
                        style={{
                            padding: 24,
                            margin: 0,
                            minHeight: 280,
                            background: '#fff',
                            borderRadius: '4px',
                            overflow: 'auto'
                        }}
                    >
                        <Routes>
                            <Route path="/" element={<ChatPage />} />
                            <Route path="/upload" element={<FileUploadPage />} />
                            <Route path="/code" element={<CodeUploadPage />} />
                            <Route path="/documents" element={<DocumentsPage />} />
                        </Routes>
                    </Content>
                </Layout>
            </Layout>
        </Layout>
    );
}

export default App; 