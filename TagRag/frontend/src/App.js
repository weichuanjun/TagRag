import React, { useContext } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, Outlet, useLocation, Navigate, useNavigate } from 'react-router-dom';
import { Layout, Menu, Button, message } from 'antd';
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
import { AuthProvider, AuthContext } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import RequireAuth from './components/RequireAuth';

// Import all pages
import ChatPage from './pages/ChatPage';
import FileUploadPage from './pages/FileUploadPage';
import DocumentsPage from './pages/DocumentsPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import TagManagementPage from './pages/TagManagementPage';
import GraphVisualizerPage from './pages/GraphVisualizerPage';
import CodeAnalysisPage from './pages/CodeAnalysisPage';
import DebugPage from './pages/DebugPage';

const { Header, Content, Sider } = Layout;

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
        <Layout style={{ height: '100vh' }}>
            <Sider style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <div className="logo" style={{
                    height: '64px',
                    margin: '16px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'rgba(255, 255, 255, 0.2)',
                    color: 'white',
                    fontSize: '20px',
                    fontWeight: 'bold',
                }}>
                    TagRAG
                </div>
                <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]} style={{ flex: '1 1 auto', overflow: 'hidden auto' }}>
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
                <div style={{ padding: '16px', textAlign: 'center' }}>
                    <Button type="primary" danger icon={<LogoutOutlined />} onClick={handleLogout} style={{ width: '100%' }}>
                        退出登录
                    </Button>
                </div>
            </Sider>
            <Layout style={{ display: 'flex', flexDirection: 'column' }}>
                <Header style={{ background: '#fff', padding: '0 16px', borderBottom: '1px solid #f0f0f0' }}>
                    <h1>TagRAG 智能分析系统</h1>
                </Header>
                <Content style={{ margin: '16px', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <div style={{ padding: 24, background: '#fff', flex: '1 1 auto', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                        <Outlet />
                    </div>
                </Content>
            </Layout>
        </Layout>
    );
};


function App() {
    return (
        <AuthProvider>
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
        </AuthProvider>
    );
}

export default App; 