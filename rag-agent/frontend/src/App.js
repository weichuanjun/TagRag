import React from 'react';
import { Routes, Route, Link, Navigate } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { MessageOutlined, CodeOutlined, FileOutlined } from '@ant-design/icons';

// 导入页面组件
import ChatPage from './pages/ChatPage';
import FileUploadPage from './pages/FileUploadPage';
import CodeAnalysisPage from './pages/CodeAnalysisPage';  // 保留代码分析页面

const { Header, Content, Footer, Sider } = Layout;

function App() {
    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider
                breakpoint="lg"
                collapsedWidth="0"
            >
                <div className="logo" style={{ height: '32px', margin: '16px', background: 'rgba(255, 255, 255, 0.2)' }} />
                <Menu theme="dark" defaultSelectedKeys={['1']} mode="inline">
                    <Menu.Item key="1" icon={<MessageOutlined />}>
                        <Link to="/chat">智能问答</Link>
                    </Menu.Item>
                    <Menu.Item key="2" icon={<FileOutlined />}>
                        <Link to="/upload">文档上传</Link>
                    </Menu.Item>
                    <Menu.Item key="3" icon={<CodeOutlined />}>
                        <Link to="/code-analysis">代码分析</Link>
                    </Menu.Item>
                </Menu>
            </Sider>
            <Layout className="site-layout">
                <Header className="site-layout-background" style={{ padding: 0, background: '#fff' }} />
                <Content style={{ margin: '0 16px' }}>
                    <div className="site-layout-background" style={{ padding: 24, minHeight: 360 }}>
                        <Routes>
                            <Route path="/chat" element={<ChatPage />} />
                            <Route path="/upload" element={<FileUploadPage />} />
                            <Route path="/code-analysis" element={<CodeAnalysisPage />} />
                            <Route path="/" element={<Navigate to="/chat" replace />} />
                        </Routes>
                    </div>
                </Content>
                <Footer style={{ textAlign: 'center' }}>RAG Agent ©2023</Footer>
            </Layout>
        </Layout>
    );
}

export default App; 