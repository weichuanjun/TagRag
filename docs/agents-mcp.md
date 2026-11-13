# 给 Agent 用：MCP 接口

TagRAG 自带一个 MCP 服务器（`backend/app/mcp_server.py`），让 Claude Code、Claude Desktop 和自建的 Claude Agent 把知识库当作**受治理的根拠来源**来调用。

MCP 服务器只是 TagRAG REST API 的一个薄客户端，所以：
- Agent 看到的结果和人在 Web 界面看到的一致；
- Agent 受同一套 API Key、用户组 ACL 约束；
- 每次调用都以 `agent:<id>` 记入审计日志。

## 与 Harness 的对应关系

| Harness 关注点 | TagRAG 中的实现 |
|---|---|
| 根拠（Evidence） | `search_evidence` 返回带编号的片段 E1、E2…，附来源文档、章节路径、标签 |
| 范围与权限 | `TAGRAG_AGENT_GROUPS` 决定 Agent 能看到哪些文档；`scopes` 参数按标签限定检索范围 |
| 停止 / 移交 | `sufficiency=none` 时，工具会明确告诉 Agent 不要凭常识作答 |
| 可纠错 | 未知 scope、知识库不存在等预期内的错误，消息会原样返回给 Agent，便于它自己纠正 |
| 审计 | `audit_log_id` 对应 `query_logs` 里的记录 |
| 人工治理 | 标签体系由人维护：候选标签需要审核，合并后原名称变成别名 |

## 工具

| 工具 | 参数 | 返回 |
|---|---|---|
| `list_knowledge_bases` | — | Agent 可访问的知识库及文档数 |
| `list_scopes` | `kb?` | 按维度分组的标签体系（名称、说明、别名、父标签、片段数） |
| `search_evidence` | `query`, `kb?`, `scopes?`, `top_k=6` | `sufficiency`、`guidance`、`query_tags`、`evidence[]`（`ref` / `source` / `section` / `text` / `tags` / `score` / `document_id` / `chunk_id`）、`audit_log_id` |
| `read_context` | `document_id`, `chunk_id`, `window=1`, `kb?` | 目标片段及前后各 `window` 个片段 |

所有工具都标注为只读（`readOnlyHint`）、幂等。

`search_evidence` 返回示例：

```json
{
  "knowledge_base": "演示：公司制度库",
  "sufficiency": "sufficient",
  "guidance": "Answer only from this evidence and cite it as [E1], [E2].",
  "query_tags": [],
  "evidence": [{
    "ref": "E1",
    "source": "差旅报销制度.md",
    "section": "差旅报销制度 > 住宿标准",
    "text": "一线城市（北京、上海、广州、深圳）住宿费每晚不超过600元……",
    "tags": ["报销"],
    "score": 1.0,
    "document_id": 1,
    "chunk_id": 2
  }],
  "audit_log_id": 2
}
```

## 配置

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `TAGRAG_URL` | TagRAG 后端地址 | `http://localhost:8000` |
| `TAGRAG_API_KEY` | 后端开启 API Key 时需要 | — |
| `TAGRAG_AGENT_ID` | Agent 名称，写入审计日志 | `claude` |
| `TAGRAG_AGENT_GROUPS` | Agent 所属用户组（逗号分隔），**按最小权限配置** | 不设置时：开发模式不限制，生产模式只能看公开文档 |
| `TAGRAG_KB` | 默认知识库（ID 或名称） | 只有一个知识库时自动选中它 |

## 接入 Claude Code

在 `backend/` 目录执行：

```bash
claude mcp add tagrag \
  --env TAGRAG_URL=http://localhost:8000 \
  --env TAGRAG_AGENT_ID=claude-code \
  --env TAGRAG_AGENT_GROUPS=staff \
  -- python -m app.mcp_server
```

## 接入 Claude Desktop

在 `claude_desktop_config.json` 中添加（把 `cwd` 换成你本机的路径）：

```json
{
  "mcpServers": {
    "tagrag": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/path/to/TagRag/backend",
      "env": {
        "TAGRAG_URL": "http://localhost:8000",
        "TAGRAG_AGENT_ID": "claude-desktop",
        "TAGRAG_AGENT_GROUPS": "staff"
      }
    }
  }
}
```

## 给 Agent 的使用约定

MCP 服务器在初始化时会把以下约定作为 `instructions` 下发给 Agent：

- 回答内部制度、流程、产品、文档相关的问题之前，先调用 `search_evidence`；只依据返回的根拠作答，并用 [E1] 这样的编号标注。
- `sufficiency` 为 `none` 时，说明知识库里没有依据，不要凭常识作答；为 `weak` 时谨慎作答，引用原文，或者调整查询和范围后再检索。
- 用 `list_scopes` 查看标签体系，把标签名作为 `scopes` 传入，可以把检索限定在某个部门、产品或主题。
- 需要细节时，先用 `read_context` 读取根拠前后的原文。

## 测试

`backend/tests/test_mcp.py` 会启动真实的后端进程，通过 stdio 拉起 MCP 服务器并调用全部工具，覆盖以下场景：
- 用户组隔离：`staff` 组的 Agent 看不到仅限 `finance` 组的文档；
- 未知 scope 的错误消息能原样返回给 Agent；
- 上下文展开。
