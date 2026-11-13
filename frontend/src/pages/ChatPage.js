import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Button, Card, Collapse, Empty, Input, Select, Space, Switch, Tag, Tooltip, Typography, message } from 'antd';
import { DislikeOutlined, LikeOutlined, SendOutlined, StopOutlined, ClearOutlined } from '@ant-design/icons';
import { api, errMsg, streamChat } from '../api';

const { Text } = Typography;

// 把 [1] 形式的引用转成可点击的角标
function withCitations(text, n) {
    return (text || '').replace(/\[(\d+)\]/g, (m, d) => (Number(d) >= 1 && Number(d) <= n ? `[${d}](#cite-${d})` : m));
}

function Answer({ msg, onCite }) {
    const components = {
        a: ({ href, children }) => {
            if (href && href.startsWith('#cite-')) {
                const i = Number(href.slice(6));
                return <span className="cite" onClick={() => onCite(i)}>{i}</span>;
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
        },
    };
    return (
        <div className="markdown">
            <ReactMarkdown components={components}>{withCitations(msg.content, msg.sources?.length || 0)}</ReactMarkdown>
        </div>
    );
}

function Sources({ msg, activeKey, setActiveKey }) {
    if (!msg.sources?.length) return null;
    return (
        <Collapse size="small" ghost activeKey={activeKey} onChange={setActiveKey} style={{ marginTop: 8 }}
            items={msg.sources.map((s) => ({
                key: String(s.index),
                label: (
                    <Space size={4} wrap>
                        <span className="cite">{s.index}</span>
                        <Text strong>{s.filename}</Text>
                        {s.heading_path && <Text type="secondary">› {s.heading_path}</Text>}
                        {msg.cited?.includes(s.index) && <Tag color="blue">已引用</Tag>}
                    </Space>
                ),
                extra: (
                    <Tooltip title={`语义 ${s.dense} · BM25 排名 ${s.sparse_rank ?? '-'} · 标签分 ${s.tag_score}`}>
                        <Text type="secondary" style={{ fontSize: 12 }}>{s.score.toFixed(3)}</Text>
                    </Tooltip>
                ),
                children: (
                    <>
                        <div className="source-text">{s.text}</div>
                        <Space size={4} wrap style={{ marginTop: 6 }}>
                            {s.tags.map((t) => <Tag key={t} color={s.matched_tags.includes(t) ? 'green' : undefined}>{t}</Tag>)}
                        </Space>
                    </>
                ),
            }))} />
    );
}

export default function ChatPage({ kb }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [tags, setTags] = useState([]);
    const [filterTags, setFilterTags] = useState([]);
    const [useTags, setUseTags] = useState(true);
    const [openSources, setOpenSources] = useState({});
    const abortRef = useRef(null);
    const bottomRef = useRef(null);

    useEffect(() => {
        setMessages([]);
        setFilterTags([]);
        if (!kb) return;
        api.get(`/api/kbs/${kb.id}/tags`, { params: { status: 'active' } })
            .then(({ data }) => setTags(data)).catch(() => setTags([]));
    }, [kb]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

    const update = (id, patch) => setMessages((ms) => ms.map((m) => (m.id === id ? { ...m, ...patch(m) } : m)));

    const send = async () => {
        const q = input.trim();
        if (!q || !kb || loading) return;
        const history = messages.filter((m) => m.content).map((m) => ({ role: m.role, content: m.content }));
        const id = Date.now();
        setMessages((ms) => [...ms, { id: id - 1, role: 'user', content: q }, { id, role: 'assistant', content: '', pending: true }]);
        setInput('');
        setLoading(true);
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        try {
            await streamChat(kb.id, { query: q, history, filter_tag_ids: filterTags, use_tags: useTags }, {
                onMeta: (meta) => update(id, () => ({ sources: meta.sources, queryTags: meta.query_tags })),
                onDelta: (t) => update(id, (m) => ({ content: m.content + t, pending: false })),
                onDone: (d) => update(id, () => ({ logId: d.log_id, cited: d.cited, pending: false })),
                onError: (e) => message.error(e),
            }, ctrl.signal);
        } catch (e) {
            if (e.name !== 'AbortError') {
                message.error(errMsg(e));
                update(id, (m) => ({ content: m.content || `出错了：${e.message}`, pending: false }));
            }
        } finally {
            update(id, () => ({ pending: false }));
            setLoading(false);
        }
    };

    const feedback = async (m, rating) => {
        try {
            await api.post(`/api/feedback/${m.logId}`, { rating });
            update(m.id, () => ({ rating }));
        } catch (e) {
            message.error(errMsg(e));
        }
    };

    if (!kb) return <Card><Empty description="请先在顶部创建或选择一个知识库" /></Card>;

    const facets = [...new Set(tags.map((t) => t.facet))];

    return (
        <Card bodyStyle={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 130px)', padding: 16 }}>
            <Space wrap style={{ marginBottom: 8 }}>
                <Select mode="multiple" allowClear placeholder="按标签限定范围（可选，含子标签）" style={{ minWidth: 320 }}
                    value={filterTags} onChange={setFilterTags} optionFilterProp="label"
                    options={facets.map((f) => ({
                        label: f, options: tags.filter((t) => t.facet === f).map((t) => ({ value: t.id, label: t.name })),
                    }))} />
                <Tooltip title="关闭后为纯混合检索（向量+BM25），便于对比标签带来的效果">
                    <Space size={4}><Switch size="small" checked={useTags} onChange={setUseTags} /><Text>标签增强</Text></Space>
                </Tooltip>
                <Button size="small" icon={<ClearOutlined />} onClick={() => setMessages([])}>清空对话</Button>
            </Space>

            <div className="chat-scroll">
                {!messages.length && <Empty style={{ marginTop: 80 }} description={`向「${kb.name}」提问`} />}
                {messages.map((m) => (m.role === 'user' ? (
                    <div key={m.id} className="msg-user">{m.content}</div>
                ) : (
                    <div key={m.id} className="msg-ai">
                        {m.queryTags?.length > 0 && (
                            <Space size={4} wrap style={{ marginBottom: 6 }}>
                                <Text type="secondary" style={{ fontSize: 12 }}>识别标签</Text>
                                {m.queryTags.map((t) => <Tag key={t.id} color="purple">{t.name}</Tag>)}
                            </Space>
                        )}
                        {m.pending && !m.content ? <Text type="secondary">检索并生成中…</Text> : (
                            <Answer msg={m} onCite={(i) => setOpenSources((o) => ({ ...o, [m.id]: [String(i)] }))} />
                        )}
                        <Sources msg={m} activeKey={openSources[m.id]}
                            setActiveKey={(k) => setOpenSources((o) => ({ ...o, [m.id]: k }))} />
                        {m.logId && (
                            <Space style={{ marginTop: 6 }}>
                                <Button size="small" type={m.rating === 1 ? 'primary' : 'text'} icon={<LikeOutlined />} onClick={() => feedback(m, 1)} />
                                <Button size="small" type={m.rating === -1 ? 'primary' : 'text'} danger={m.rating === -1} icon={<DislikeOutlined />} onClick={() => feedback(m, -1)} />
                            </Space>
                        )}
                    </div>
                )))}
                <div ref={bottomRef} />
            </div>

            <Space.Compact style={{ width: '100%' }}>
                <Input.TextArea value={input} onChange={(e) => setInput(e.target.value)} autoSize={{ minRows: 1, maxRows: 5 }}
                    placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                    onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send(); } }} />
                {loading ? (
                    <Button danger icon={<StopOutlined />} onClick={() => abortRef.current?.abort()}>停止</Button>
                ) : (
                    <Button type="primary" icon={<SendOutlined />} onClick={send}>发送</Button>
                )}
            </Space.Compact>
        </Card>
    );
}
