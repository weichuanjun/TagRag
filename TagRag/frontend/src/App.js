import React from 'react';
import { Routes, Route, Link, Navigate } from 'react-router-dom';
import { Layout, Menu, ConfigProvider, theme, Typography } from 'antd';
import {
    MessageOutlined,
    CodeOutlined,
    FileOutlined,
    DatabaseOutlined,
    RobotOutlined,
    ShareAltOutlined,
    TagsOutlined,  // 添加标签图标
    UploadOutlined,
    WechatOutlined,
    ApartmentOutlined,
    SettingOutlined,
    ExperimentOutlined
    // FileTextOutlined // 移除图标
} from '@ant-design/icons';
import axios from 'axios'; // 导入axios

// 导入页面组件
import ChatPage from './pages/ChatPage';
import FileUploadPage from './pages/FileUploadPage';
import CodeAnalysisPage from './pages/CodeAnalysisPage';  // 保留代码分析页面
import KnowledgeBasePage from './pages/KnowledgeBasePage';  // 新增知识库管理页面
import AgentPromptPage from './pages/AgentPromptPage';  // 新增Agent提示词管理页面
import GraphVisualizerPage from './pages/GraphVisualizerPage';  // 新增图可视化页面
import TagManagementPage from './pages/TagManagementPage';  // 新增标签管理页面
// import ManageDocuments from './pages/ManageDocuments'; // 移除导入

// 配置 Axios baseURL
// 使用REACT_APP_API_BASE_URL环境变量，如果未设置，则默认为 docker-compose 中的后端服务地址
// 对于浏览器访问场景，默认应为 localhost
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';
axios.defaults.baseURL = API_BASE_URL;
console.log(`API Base URL set to: ${API_BASE_URL}`); // 用于调试

const { Content, Footer, Sider } = Layout;
const { Title } = Typography;

function App() {
    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider
                breakpoint="lg"
                collapsedWidth="0"
            >
                <div style={{
                    padding: '16px 24px',
                    textAlign: 'center'
                }}>
                    <Title
                        level={4}
                        style={{
                            margin: 0,
                            color: 'white',
                            fontWeight: 'bold',
                            fontFamily: 'Helvetica, Arial, sans-serif'
                        }}
                    >
                        TagRAG
                    </Title>
                </div>
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
                    <Menu.Item key="4" icon={<DatabaseOutlined />}>
                        <Link to="/knowledge-bases">知识库管理</Link>
                    </Menu.Item>
                    <Menu.Item key="5" icon={<RobotOutlined />}>
                        <Link to="/agent-prompt">Agent提示词</Link>
                    </Menu.Item>
                    <Menu.Item key="6" icon={<ShareAltOutlined />}>
                        <Link to="/graph-view">知识图谱</Link>
                    </Menu.Item>
                    <Menu.Item key="7" icon={<TagsOutlined />}>
                        <Link to="/tags">标签管理</Link>
                    </Menu.Item>
                    {/* Remove menu item for document management */}
                    {/* <Menu.Item key="8" icon={<FileTextOutlined />}>
                        <Link to="/documents">文档管理</Link>
                    </Menu.Item> */}
                </Menu>
            </Sider>
            <Layout className="site-layout">
                <Content style={{ margin: '0 16px' }}>
                    <div className="site-layout-background" style={{ padding: 24, minHeight: 360 }}>
                        <Routes>
                            <Route path="/chat" element={<ChatPage />} />
                            <Route path="/upload" element={<FileUploadPage />} />
                            <Route path="/code-analysis" element={<CodeAnalysisPage />} />
                            <Route path="/knowledge-bases" element={<KnowledgeBasePage />} />
                            <Route path="/agent-prompt" element={<AgentPromptPage />} />
                            <Route path="/graph-view" element={<GraphVisualizerPage />} />
                            <Route path="/tags" element={<TagManagementPage />} />
                            {/* Remove route for document management */}
                            {/* <Route path="/documents" element={<ManageDocuments />} /> */}
                            <Route path="/" element={<Navigate to="/chat" replace />} />
                        </Routes>
                    </div>
                </Content>
                <Footer style={{ textAlign: 'center' }}>TagRAG ©2025 WEICHUANJUN</Footer>
            </Layout>
        </Layout>
    );
}

export default App; 