import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Empty, Form, Input, Modal, Popconfirm, Select, Space, Table, Tabs, Tag, Typography,
    message } from 'antd';
import { BulbOutlined, CheckOutlined, DeleteOutlined, EditOutlined, ImportOutlined, MergeCellsOutlined, PlusOutlined,
    SyncOutlined } from '@ant-design/icons';
import { api, errMsg } from '../api';

const { Text } = Typography;

const FACETS = ['topic', 'product', 'department', 'doc_type', 'region'];

const IMPORT_EXAMPLE = JSON.stringify([
    { name: '财务', facet: 'department' },
    { name: '报销', facet: 'topic', parent: '财务', aliases: ['差旅费', '费用报销'], description: '费用报销相关制度与流程' },
    { name: '人力资源', facet: 'department', aliases: ['HR', '人事'] },
], null, 2);

function buildTree(tags) {
    const byId = Object.fromEntries(tags.map((t) => [t.id, { ...t, key: t.id, children: [] }]));
    const roots = [];
    Object.values(byId).forEach((t) => {
        if (t.parent_id && byId[t.parent_id]) byId[t.parent_id].children.push(t);
        else roots.push(t);
    });
    const clean = (n) => ({ ...n, children: n.children.length ? n.children.map(clean) : undefined });
    return roots.map(clean);
}

export default function TagsPage({ kb, onChanged }) {
    const [tags, setTags] = useState([]);
    const [loading, setLoading] = useState(false);
    const [editing, setEditing] = useState(null); // {} = 新建
    const [importOpen, setImportOpen] = useState(false);
    const [importText, setImportText] = useState(IMPORT_EXAMPLE);
    const [merging, setMerging] = useState(null);
    const [mergeTarget, setMergeTarget] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [expanded, setExpanded] = useState(null); // null = 全部展开
    const [form] = Form.useForm();

    const load = useCallback(async () => {
        if (!kb) return;
        setLoading(true);
        try {
            const { data } = await api.get(`/api/kbs/${kb.id}/tags`);
            setTags(data);
        } catch (e) {
            message.error(errMsg(e));
        } finally {
            setLoading(false);
        }
    }, [kb]);

    useEffect(() => { load(); }, [load]);

    const active = useMemo(() => tags.filter((t) => t.status === 'active'), [tags]);
    const candidates = useMemo(() => tags.filter((t) => t.status === 'candidate'), [tags]);
    const deprecated = useMemo(() => tags.filter((t) => t.status === 'deprecated'), [tags]);
    const byId = useMemo(() => Object.fromEntries(tags.map((t) => [t.id, t])), [tags]);

    if (!kb) return <Card><Empty description="请先在顶部创建或选择一个知识库" /></Card>;

    const call = async (fn, ok) => {
        try {
            await fn();
            if (ok) message.success(ok);
            setDirty(true);
            load();
            onChanged?.();
        } catch (e) {
            message.error(errMsg(e));
        }
    };

    const save = async () => {
        const v = await form.validateFields();
        const body = {
            ...v,
            aliases: (v.aliases || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        };
        if (editing.id) {
            if (!v.parent_id) body.clear_parent = true;
            await call(() => api.patch(`/api/kbs/${kb.id}/tags/${editing.id}`, body), '已保存');
        } else {
            await call(() => api.post(`/api/kbs/${kb.id}/tags`, body), '已创建');
        }
        setEditing(null);
    };

    const openEdit = (t) => {
        setEditing(t || {});
        form.setFieldsValue(t ? { ...t, aliases: (t.aliases || []).join('，') }
            : { name: '', facet: 'topic', description: '', aliases: '', parent_id: undefined });
    };

    const doImport = async () => {
        let items;
        try { items = JSON.parse(importText); } catch (e) { message.error('JSON 格式错误'); return; }
        await call(() => api.post(`/api/kbs/${kb.id}/tags/import`, items), `已导入 ${items.length} 个标签`);
        setImportOpen(false);
    };

    const actions = (t) => (
        <Space size={0}>
            {t.status !== 'active' && (
                <Button type="text" icon={<CheckOutlined />} title="通过"
                    onClick={() => call(() => api.post(`/api/kbs/${kb.id}/tags/${t.id}/approve`), '已启用')} />
            )}
            <Button type="text" icon={<EditOutlined />} title="编辑" onClick={() => openEdit(t)} />
            <Button type="text" icon={<MergeCellsOutlined />} title="合并到…" onClick={() => { setMerging(t); setMergeTarget(null); }} />
            <Popconfirm title="删除标签？子标签会上移一级" onConfirm={() => call(() => api.delete(`/api/kbs/${kb.id}/tags/${t.id}`), '已删除')}>
                <Button type="text" danger icon={<DeleteOutlined />} title="删除" />
            </Popconfirm>
        </Space>
    );

    const baseCols = [
        { title: '标签', dataIndex: 'name', render: (v, t) => (
            <Space direction="vertical" size={0}>
                <Text strong>{v}</Text>
                {t.parent_id && byId[t.parent_id] && byId[t.parent_id].facet !== t.facet && (
                    <Text type="secondary" style={{ fontSize: 12 }}>上级：{byId[t.parent_id].name}</Text>
                )}
                {t.description && <Text type="secondary" style={{ fontSize: 12 }}>{t.description}</Text>}
            </Space>
        ) },
        { title: '维度', dataIndex: 'facet', width: 110, render: (v) => <Tag>{v}</Tag> },
        { title: '别名', dataIndex: 'aliases', render: (a) => a.map((x) => <Tag key={x} bordered={false}>{x}</Tag>) },
        { title: '片段数', dataIndex: 'chunk_count', width: 80 },
    ];

    const facets = [...new Set(active.map((t) => t.facet))];
    const allKeys = [...facets.map((f) => `facet-${f}`), ...active.map((t) => t.id)];

    return (
        <Card
            title="标签体系"
            extra={(
                <Space wrap>
                    <Button icon={<PlusOutlined />} onClick={() => openEdit(null)}>新建标签</Button>
                    <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>批量导入</Button>
                    <Button icon={<BulbOutlined />} onClick={() => call(() => api.post(`/api/kbs/${kb.id}/tags/suggest`),
                        '已根据文档内容生成候选标签，请在「待审核」中处理')}>智能建议</Button>
                    <Button type={dirty ? 'primary' : 'default'} icon={<SyncOutlined />}
                        onClick={() => call(() => api.post(`/api/kbs/${kb.id}/retag`), '已开始后台重新打标').then(() => setDirty(false))}>
                        重新打标
                    </Button>
                </Space>
            )}
        >
            {dirty && (
                <Alert type="info" showIcon style={{ marginBottom: 12 }}
                    message="标签体系已变化。点击「重新打标」让已有文档按新的标签体系重新分类（不需重新上传）。" />
            )}
            <Tabs items={[
                {
                    key: 'active', label: `已启用 (${active.length})`,
                    children: (
                        <Table rowKey="id" loading={loading} pagination={false} size="middle"
                            dataSource={facets.map((f) => ({
                                key: `facet-${f}`, id: `facet-${f}`, name: f, facet: f, isFacet: true,
                                children: buildTree(active.filter((t) => t.facet === f)),
                            }))}
                            expandable={{
                                expandedRowKeys: expanded ?? allKeys,
                                onExpand: (open, rec) => setExpanded((prev) => {
                                    const cur = prev ?? allKeys;
                                    return open ? [...cur, rec.id] : cur.filter((k) => k !== rec.id);
                                }),
                            }}
                            columns={[...baseCols.map((c) => ({
                                ...c,
                                render: (v, r, i) => (r.isFacet ? (c.dataIndex === 'name' ? <Text type="secondary">维度：{v}</Text> : null)
                                    : (c.render ? c.render(v, r, i) : v)),
                            })), { title: '操作', width: 170, render: (_, r) => (r.isFacet ? null : actions(r)) }]} />
                    ),
                },
                {
                    key: 'candidate', label: `待审核 (${candidates.length})`,
                    children: (
                        <>
                            <Text type="secondary">由大模型在打标时提议、或「智能建议」生成的新标签。候选标签不参与检索，审核通过或合并到已有标签后生效。</Text>
                            <Table rowKey="id" loading={loading} dataSource={candidates} style={{ marginTop: 12 }}
                                columns={[...baseCols, { title: '提议次数', dataIndex: 'mention_count', width: 90,
                                    sorter: (a, b) => a.mention_count - b.mention_count, defaultSortOrder: 'descend' },
                                { title: '操作', width: 170, render: (_, r) => actions(r) }]} />
                        </>
                    ),
                },
                {
                    key: 'deprecated', label: `已停用 (${deprecated.length})`,
                    children: <Table rowKey="id" dataSource={deprecated}
                        columns={[...baseCols, { title: '操作', width: 170, render: (_, r) => actions(r) }]} />,
                },
            ]} />

            <Modal title={editing?.id ? '编辑标签' : '新建标签'} open={!!editing} onOk={save} onCancel={() => setEditing(null)}>
                <Form form={form} layout="vertical">
                    <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="facet" label="维度" extra="例如 topic 主题 / product 产品 / department 部门 / doc_type 文档类型">
                        <Select options={[...new Set([...FACETS, ...tags.map((t) => t.facet)])].map((f) => ({ value: f, label: f }))}
                            showSearch />
                    </Form.Item>
                    <Form.Item name="parent_id" label="父标签">
                        <Select allowClear showSearch optionFilterProp="label"
                            options={active.filter((t) => t.id !== editing?.id).map((t) => ({ value: t.id, label: `${t.name}（${t.facet}）` }))} />
                    </Form.Item>
                    <Form.Item name="aliases" label="别名 / 同义词" extra="逗号分隔。用户提问中出现别名也会命中该标签"><Input /></Form.Item>
                    <Form.Item name="description" label="说明" extra="说明越清楚，自动打标越准确"><Input.TextArea rows={2} /></Form.Item>
                    {editing?.id && (
                        <Form.Item name="status" label="状态">
                            <Select options={[{ value: 'active', label: '启用' }, { value: 'candidate', label: '待审核' },
                                { value: 'deprecated', label: '停用' }]} />
                        </Form.Item>
                    )}
                </Form>
            </Modal>

            <Modal title="批量导入标签体系" width={640} open={importOpen} onOk={doImport} onCancel={() => setImportOpen(false)}>
                <Text type="secondary">JSON 数组，parent 填写父标签名称；同名标签会被更新。</Text>
                <Input.TextArea rows={14} value={importText} onChange={(e) => setImportText(e.target.value)}
                    style={{ fontFamily: 'monospace', marginTop: 8 }} />
            </Modal>

            <Modal title={`合并「${merging?.name || ''}」`} open={!!merging} okButtonProps={{ disabled: !mergeTarget }}
                onCancel={() => setMerging(null)}
                onOk={async () => {
                    await call(() => api.post(`/api/kbs/${kb.id}/tags/${merging.id}/merge/${mergeTarget}`),
                        `已合并到「${byId[mergeTarget]?.name}」`);
                    setMerging(null);
                }}>
                <p>合并后，原标签的片段关联会迁移到目标标签，原名称成为目标标签的别名。</p>
                <Select style={{ width: '100%' }} showSearch optionFilterProp="label" value={mergeTarget} onChange={setMergeTarget}
                    options={active.filter((t) => t.id !== merging?.id).map((t) => ({ value: t.id, label: `${t.name}（${t.facet}）` }))} />
            </Modal>
        </Card>
    );
}
