import axios from 'axios';

// 开发环境走 CRA proxy；生产环境通过 REACT_APP_API_BASE_URL 指定后端地址
export const API_BASE = process.env.REACT_APP_API_BASE_URL || '';

function authHeaders() {
    const h = {};
    const key = localStorage.getItem('tagrag_api_key');
    const groups = localStorage.getItem('tagrag_user_groups');
    if (key) h['X-API-Key'] = key;
    if (groups) h['X-User-Groups'] = groups;
    return h;
}

export const api = axios.create({ baseURL: API_BASE });
api.interceptors.request.use((cfg) => {
    cfg.headers = { ...cfg.headers, ...authHeaders() };
    return cfg;
});

export function errMsg(e) {
    const d = e?.response?.data?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => x.msg).join('; ');
    return e?.message || '请求失败';
}

/**
 * 流式问答（SSE over fetch）。handlers: { onMeta, onDelta, onDone, onError }
 */
export async function streamChat(kbId, body, handlers, signal) {
    const resp = await fetch(`${API_BASE}/api/kbs/${kbId}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body),
        signal,
    });
    if (!resp.ok) {
        let detail = resp.statusText;
        try { detail = (await resp.json()).detail || detail; } catch (_) { /* ignore */ }
        throw new Error(detail);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
            const raw = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            let event = 'message';
            let data = '';
            raw.split('\n').forEach((line) => {
                if (line.startsWith('event:')) event = line.slice(6).trim();
                else if (line.startsWith('data:')) data += line.slice(5).trim();
            });
            const payload = data ? JSON.parse(data) : {};
            if (event === 'meta') handlers.onMeta?.(payload);
            else if (event === 'delta') handlers.onDelta?.(payload.text);
            else if (event === 'done') handlers.onDone?.(payload);
            else if (event === 'error') handlers.onError?.(payload.message);
        }
    }
}
