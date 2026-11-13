import React, { useCallback, useEffect, useState } from 'react';
import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Select, Space, Button, Modal, Input, Form, message, Typography } from 'antd';
import { MessageOutlined, FileTextOutlined, TagsOutlined, SettingOutlined, PlusOutlined } from '@ant-design/icons';
import { api, errMsg } from './api';
import ChatPage from './pages/ChatPage';
import DocumentsPage from './pages/DocumentsPage';
import TagsPage from './pages/TagsPage';

const { Header, Content, Sider } = Layout;

export default function App() {
    const location = useLocation();
    const [kbs, setKbs] = useState([]);
    const [kbId, setKbId] = useState(() => Number(localStorage.getItem('tagrag_kb')) || null);
    const [creating, setCreating] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [form] = Form.useForm();
    const [settingsForm] = Form.useForm();

    const loadKbs = useCallback(async () => {
        try {
            const { data } = await api.get('/api/kbs');
            setKbs(data);
            if (data.length && !data.find((k) => k.id === kbId)) setKbId(data[0].id);
        } catch (e) {
            message.error(`加载知识库失败：${errMsg(e)}`);
        }
    }, [kbId]);

    useEffect(() => { loadKbs(); }, [loadKbs]);
    useEffect(() => { if (kbId) localStorage.setItem('tagrag_kb', String(kbId)); }, [kbId]);

    const createKb = async () => {
        const values = await form.validateFields();
        try {
            const { data } = await api.post('/api/kbs', values);
            message.success('已创建');
            setCreating(false);
            form.resetFields();
            setKbId(data.id);
            loadKbs();
        } catch (e) {
            message.error(errMsg(e));
        }
    };

    const saveSettings = () => {
        const v = settingsForm.getFieldsValue();
        ['api_key', 'user_groups'].forEach((k) => {
            if (v[k]) localStorage.setItem(`tagrag_${k}`, v[k]);
            else localStorage.removeItem(`tagrag_${k}`);
        });
        setSettingsOpen(false);
        loadKbs();
    };

    const kb = kbs.find((k) => k.id === kbId);
    const selected = location.pathname.split('/')[1] || 'chat';

    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider breakpoint="lg" collapsedWidth="0" theme="dark">
                <div style={{ color: '#fff', fontSize: 20, fontWeight: 700, padding: '18px 24px' }}>TagRAG</div>
                <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={[
                    { key: 'chat', icon: <MessageOutlined />, label: <Link to="/chat">智能问答</Link> },
                    { key: 'documents', icon: <FileTextOutlined />, label: <Link to="/documents">文档管理</Link> },
                    { key: 'tags', icon: <TagsOutlined />, label: <Link to="/tags">标签体系</Link> },
                ]} />
            </Sider>
            <Layout>
                <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center',
                    justifyContent: 'space-between', borderBottom: '1px solid #f0f0f0' }}>
                    <Space>
                        <Typography.Text type="secondary">知识库</Typography.Text>
                        <Select style={{ minWidth: 220 }} value={kbId} onChange={setKbId} placeholder="请先创建知识库"
                            options={kbs.map((k) => ({ value: k.id, label: `${k.name}（${k.documents} 文档）` }))} />
                        <Button icon={<PlusOutlined />} onClick={() => setCreating(true)}>新建</Button>
                    </Space>
                    <Button type="text" icon={<SettingOutlined />} onClick={() => {
                        settingsForm.setFieldsValue({
                            api_key: localStorage.getItem('tagrag_api_key') || '',
                            user_groups: localStorage.getItem('tagrag_user_groups') || '',
                        });
                        setSettingsOpen(true);
                    }}>访问设置</Button>
                </Header>
                <Content style={{ margin: 16 }}>
                    <Routes>
                        <Route path="/chat" element={<ChatPage kb={kb} />} />
                        <Route path="/documents" element={<DocumentsPage kb={kb} onChanged={loadKbs} />} />
                        <Route path="/tags" element={<TagsPage kb={kb} onChanged={loadKbs} />} />
                        <Route path="*" element={<Navigate to="/chat" replace />} />
                    </Routes>
                </Content>
            </Layout>

            <Modal title="新建知识库" open={creating} onOk={createKb} onCancel={() => setCreating(false)}>
                <Form form={form} layout="vertical">
                    <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
                </Form>
            </Modal>
            <Modal title="访问设置" open={settingsOpen} onOk={saveSettings} onCancel={() => setSettingsOpen(false)}>
                <Form form={settingsForm} layout="vertical">
                    <Form.Item name="api_key" label="API Key" extra="后端配置了 TAGRAG_API_KEYS 时需要">
                        <Input.Password />
                    </Form.Item>
                    <Form.Item name="user_groups" label="用户组（逗号分隔）"
                        extra="用于文档权限过滤；生产环境应由网关/SSO 注入，含 admin 才能管理">
                        <Input placeholder="admin" />
                    </Form.Item>
                </Form>
            </Modal>
        </Layout>
    );
}
