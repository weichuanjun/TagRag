import React, { useCallback, useEffect, useState } from 'react';
import { Badge, Button, Card, Drawer, Empty, Form, Input, Modal, Popconfirm, Select, Space, Statistic, Table, Tag,
    Tooltip, Typography, Upload, message } from 'antd';
import { DeleteOutlined, EditOutlined, InboxOutlined, ReloadOutlined, EyeOutlined } from '@ant-design/icons';
import { api, errMsg } from '../api';

const { Text, Paragraph } = Typography;

const STATUS = {
    pending: { status: 'default', text: '排队中' },
    processing: { status: 'processing', text: '处理中' },
    ready: { status: 'success', text: '可检索' },
    failed: { status: 'error', text: '失败' },
};

export default function DocumentsPage({ kb, onChanged }) {
    const [docs, setDocs] = useState([]);
    const [tags, setTags] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const [uploadTags, setUploadTags] = useState([]);
    const [uploadAcl, setUploadAcl] = useState('');
    const [chunksDoc, setChunksDoc] = useState(null);
    const [chunks, setChunks] = useState([]);
    const [editing, setEditing] = useState(null);
    const [form] = Form.useForm();

    const load = useCallback(async () => {
        if (!kb) return;
        setLoading(true);
        try {
            const [d, t, s] = await Promise.all([
                api.get(`/api/kbs/${kb.id}/documents`),
                api.get(`/api/kbs/${kb.id}/tags`, { params: { status: 'active' } }),
                api.get(`/api/kbs/${kb.id}/stats`),
            ]);
            setDocs(d.data);
            setTags(t.data);
            setStats(s.data);
        } catch (e) {
            message.error(errMsg(e));
        } finally {
            setLoading(false);
        }
    }, [kb]);

    useEffect(() => { load(); }, [load]);

    // 有文档在处理时自动轮询
    useEffect(() => {
        if (!docs.some((d) => d.status === 'pending' || d.status === 'processing')) return undefined;
        const t = setTimeout(load, 2000);
        return () => clearTimeout(t);
    }, [docs, load]);

    if (!kb) return <Card><Empty description="请先在顶部创建或选择一个知识库" /></Card>;

    const customUpload = async ({ file, onSuccess, onError }) => {
        const fd = new FormData();
        fd.append('files', file);
        if (uploadTags.length) fd.append('tag_ids', uploadTags.join(','));
        if (uploadAcl.trim()) fd.append('acl_groups', uploadAcl.trim());
        try {
            const { data } = await api.post(`/api/kbs/${kb.id}/documents`, fd);
            const r = data[0];
            if (r.error) throw new Error(r.error);
            if (r.duplicate) message.info(`${file.name} 内容已存在，已跳过`);
            onSuccess(r);
            load();
            onChanged?.();
        } catch (e) {
            message.error(`${file.name}：${errMsg(e)}`);
            onError(e);
        }
    };

    const showChunks = async (doc) => {
        setChunksDoc(doc);
        try {
            const { data } = await api.get(`/api/kbs/${kb.id}/documents/${doc.id}/chunks`);
            setChunks(data);
        } catch (e) {
            message.error(errMsg(e));
        }
    };

    const saveDoc = async () => {
        const v = form.getFieldsValue();
        try {
            await api.patch(`/api/kbs/${kb.id}/documents/${editing.id}`, {
                tag_ids: v.tag_ids || [],
                acl_groups: (v.acl_groups || '').split(',').map((s) => s.trim()).filter(Boolean),
            });
            message.success('已更新');
            setEditing(null);
            load();
        } catch (e) {
            message.error(errMsg(e));
        }
    };

    const tagOptions = tags.map((t) => ({ value: t.id, label: `${t.name}（${t.facet}）` }));

    const columns = [
        { title: '文件', dataIndex: 'filename', render: (v, r) => (
            <Space direction="vertical" size={0}>
                <Text strong>{v}</Text>
                {r.error && <Text type="danger" style={{ fontSize: 12 }}>{r.error}</Text>}
            </Space>
        ) },
        { title: '状态', dataIndex: 'status', width: 100, render: (v) => <Badge {...STATUS[v]} /> },
        { title: '片段', dataIndex: 'chunk_count', width: 70 },
        { title: '标签', dataIndex: 'tags', render: (ts) => (
            <Space size={2} wrap>
                {ts.map((t) => (
                    <Tooltip key={t.id} title={t.source === 'manual' ? '人工指定（继承到全部片段）' : '由片段标签聚合'}>
                        <Tag color={t.source === 'manual' ? 'blue' : undefined}>{t.name}</Tag>
                    </Tooltip>
                ))}
            </Space>
        ) },
        { title: '权限', dataIndex: 'acl_groups', width: 120,
            render: (g) => (g.length ? g.map((x) => <Tag key={x} color="orange">{x}</Tag>) : <Text type="secondary">公开</Text>) },
        { title: '操作', width: 170, render: (_, r) => (
            <Space size={0}>
                <Tooltip title="查看片段与标签"><Button type="text" icon={<EyeOutlined />} onClick={() => showChunks(r)} /></Tooltip>
                <Tooltip title="编辑标签/权限"><Button type="text" icon={<EditOutlined />} onClick={() => {
                    setEditing(r);
                    form.setFieldsValue({
                        tag_ids: r.tags.filter((t) => t.source === 'manual').map((t) => t.id),
                        acl_groups: r.acl_groups.join(','),
                    });
                }} /></Tooltip>
                <Tooltip title="重新解析与索引"><Button type="text" icon={<ReloadOutlined />} onClick={async () => {
                    await api.post(`/api/kbs/${kb.id}/documents/${r.id}/reindex`); load();
                }} /></Tooltip>
                <Popconfirm title="删除该文档及其索引？" onConfirm={async () => {
                    await api.delete(`/api/kbs/${kb.id}/documents/${r.id}`); load(); onChanged?.();
                }}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm>
            </Space>
        ) },
    ];

    return (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Card>
                <Space size={48} wrap>
                    <Statistic title="文档" value={kb.documents} />
                    <Statistic title="片段" value={kb.chunks} />
                    <Statistic title="标签 / 待审核" value={`${kb.tags} / ${kb.candidate_tags}`} />
                    {stats && <Statistic title="问答次数" value={stats.queries} />}
                    {stats && <Statistic title="无结果问题" value={stats.queries_without_sources} />}
                    {stats && <Statistic title="👍 / 👎" value={`${stats.thumbs_up} / ${stats.thumbs_down}`} />}
                </Space>
            </Card>

            <Card title="上传文档">
                <Space wrap style={{ marginBottom: 12 }}>
                    <Select mode="multiple" allowClear placeholder="为本批文档指定标签（可选，如部门）" style={{ minWidth: 320 }}
                        value={uploadTags} onChange={setUploadTags} options={tagOptions} optionFilterProp="label" />
                    <Input placeholder="可访问用户组，逗号分隔（空=公开）" style={{ width: 280 }}
                        value={uploadAcl} onChange={(e) => setUploadAcl(e.target.value)} />
                </Space>
                <Upload.Dragger multiple customRequest={customUpload} showUploadList={{ showRemoveIcon: false }}
                    accept=".pdf,.docx,.md,.markdown,.txt,.html,.htm,.csv,.xlsx">
                    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                    <p>点击或拖拽文件到此处上传</p>
                    <p style={{ color: '#999' }}>支持 PDF、Word、Markdown、TXT、HTML、CSV、Excel；相同内容自动去重</p>
                </Upload.Dragger>
            </Card>

            <Card title="文档列表" extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}>
                <Table rowKey="id" loading={loading} dataSource={docs} columns={columns} pagination={{ pageSize: 20 }} />
            </Card>

            <Drawer width={720} open={!!chunksDoc} onClose={() => setChunksDoc(null)} title={chunksDoc?.filename}>
                {chunks.map((c) => (
                    <Card key={c.id} size="small" style={{ marginBottom: 12 }}
                        title={<Text type="secondary">#{c.ordinal + 1} {c.heading_path}</Text>}
                        extra={<Text type="secondary">{c.token_count} tokens</Text>}>
                        <Paragraph ellipsis={{ rows: 6, expandable: true }} style={{ whiteSpace: 'pre-wrap' }}>{c.text}</Paragraph>
                        <Space size={4} wrap>
                            {c.tags.map((t) => (
                                <Tooltip key={t.id} title={`来源：${t.source} · 置信度 ${t.confidence}`}>
                                    <Tag color={t.status === 'active' ? 'green' : 'default'}>{t.name}</Tag>
                                </Tooltip>
                            ))}
                        </Space>
                    </Card>
                ))}
            </Drawer>

            <Modal title={`编辑：${editing?.filename || ''}`} open={!!editing} onOk={saveDoc} onCancel={() => setEditing(null)}>
                <Form form={form} layout="vertical">
                    <Form.Item name="tag_ids" label="人工标签" extra="会继承到该文档的全部片段，并可作为检索过滤条件">
                        <Select mode="multiple" options={tagOptions} optionFilterProp="label" />
                    </Form.Item>
                    <Form.Item name="acl_groups" label="可访问用户组" extra="逗号分隔，留空表示知识库内公开">
                        <Input />
                    </Form.Item>
                </Form>
            </Modal>
        </Space>
    );
}
