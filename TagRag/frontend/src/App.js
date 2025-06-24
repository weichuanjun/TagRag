import React, { useState, useContext } from 'react';
import { Routes, Route, Link, Navigate, useLocation, Outlet, useNavigate } from 'react-router-dom';
import { Layout, Menu, Button } from 'antd';
import {
    WechatOutlined,
    UploadOutlined,
    BookOutlined,
    TagsOutlined,
    ApartmentOutlined,
    CodeOutlined,
    BugOutlined,
    LogoutOutlined
} from '@ant-design/icons';
import axios from 'axios';
import './App.css';

// Import pages
import ChatPage from './pages/ChatPage';
import FileUploadPage from './pages/FileUploadPage';
import DocumentsPage from './pages/DocumentsPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import TagManagementPage from './pages/TagManagementPage';
import GraphVisualizerPage from './pages/GraphVisualizerPage';
import CodeAnalysisPage from './pages/CodeAnalysisPage';
import DebugPage from './pages/DebugPage';
import LoginPage from './pages/LoginPage';

// Import auth components
import RequireAuth from './components/RequireAuth';
import { AuthContext } from './context/AuthContext';

const { Header, Content, Sider } = Layout;

// Set Axios base URL
// NOTE: We keep this for non-proxied local development and direct deployment.
// The proxy in package.json is primarily for create-react-app's dev server.
axios.defaults.baseURL = 'http://localhost:8000';


const AppLayout = () => {
    const location = useLocation();
    const { logout } = useContext(AuthContext);
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    // Determine the selected key from the current path
    const selectedKey = location.pathname.split('/')[2] || 'chat';

    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider>
                <div className="logo" />
                <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]}>
                    <Menu.Item key="chat" icon={<WechatOutlined />}>
                        <Link to="/app/chat">智能问答</Link>
                    </Menu.Item>
                    <Menu.Item key="kb" icon={<BookOutlined />}>
                        <Link to="/app/kb">知识库管理</Link>
                    </Menu.Item>
                    <Menu.Item key="tags" icon={<TagsOutlined />}>
                        <Link to="/app/tags">标签管理</Link>
                    </Menu.Item>
                    <Menu.Item key="graph" icon={<ApartmentOutlined />}>
                        <Link to="/app/graph">知识图谱</Link>
                    </Menu.Item>
                    <Menu.Item key="code" icon={<CodeOutlined />}>
                        <Link to="/app/code">代码分析</Link>
                    </Menu.Item>
                    <Menu.Item key="upload" icon={<UploadOutlined />}>
                        <Link to="/app/upload">文件上传</Link>
                    </Menu.Item>
                    <Menu.Item key="documents" icon={<BookOutlined />}>
                        <Link to="/app/documents">文档列表</Link>
                    </Menu.Item>
                    <Menu.Item key="debug" icon={<BugOutlined />}>
                        <Link to="/app/debug">调试页面</Link>
                    </Menu.Item>
                </Menu>
                <div style={{ position: 'absolute', bottom: '20px', width: '100%', textAlign: 'center' }}>
                    <Button type="primary" danger icon={<LogoutOutlined />} onClick={handleLogout}>
                        退出登录
                    </Button>
                </div>
            </Sider>
            <Layout>
                <Header style={{ background: '#fff', padding: '0 16px' }}>
                    <h1>TagRAG 智能分析系统</h1>
                </Header>
                <Content style={{ margin: '16px' }}>
                    <div style={{ padding: 24, background: '#fff', minHeight: 'calc(100vh - 128px)' }}>
                        <Outlet />
                    </div>
                </Content>
            </Layout>
        </Layout>
    );
};


function App() {
    return (
        <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
                path="/app"
                element={
                    <RequireAuth>
                        <AppLayout />
                    </RequireAuth>
                }
            >
                <Route path="chat" element={<ChatPage />} />
                <Route path="upload" element={<FileUploadPage />} />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="kb" element={<KnowledgeBasePage />} />
                <Route path="tags" element={<TagManagementPage />} />
                <Route path="graph" element={<GraphVisualizerPage />} />
                <Route path="code" element={<CodeAnalysisPage />} />
                <Route path="debug" element={<DebugPage />} />
                {/* Default route for /app */}
                <Route index element={<Navigate to="chat" replace />} />
            </Route>
            {/* Redirect root to /app or /login */}
            <Route path="/" element={<Navigate to="/app" replace />} />
            {/* Catch-all for any other route */}
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

export default App; 