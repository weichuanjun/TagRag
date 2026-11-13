# REST API

服务启动后，可以在 `http://localhost:8000/docs` 查看自动生成的交互式文档（OpenAPI）。

## 通用请求头

| 请求头 | 说明 |
|---|---|
| `X-API-Key` | 设置了 `TAGRAG_API_KEYS` 时必填 |
| `X-User-Id` | 用户标识，写入审计日志（应由网关注入） |
| `X-User-Groups` | 逗号分隔的用户组，用于文档 ACL；包含 `admin` 的调用方才能执行管理操作（应由网关注入） |
| `X-Agent-Id` | 以 Agent 身份调用时填写，审计日志中记为 `agent:<id>` |

## 知识库

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/kbs` | 列表，附文档数、片段数、标签数等统计 |
| POST | `/api/kbs` | 创建：`{name, description?}` |
| GET / PUT / DELETE | `/api/kbs/{kb}` | 查看 / 修改 / 删除（删除时会一并删除文档和文件） |
| POST | `/api/kbs/{kb}/retag` | 全库重新打标（后台执行） |
| GET | `/api/kbs/{kb}/stats` | 问答次数、赞 / 踩数、平均耗时、无根拠的问题数、入库失败的文档数 |

## 文档

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/kbs/{kb}/documents` | 上传（multipart）：`files`（可以多个）、`tag_ids`（逗号分隔）、`acl_groups`（逗号分隔） |
| GET | `/api/kbs/{kb}/documents?status=&tag_id=` | 列表（只返回调用者有权限看到的文档） |
| GET | `/api/kbs/{kb}/documents/{id}` | 详情 |
| GET | `/api/kbs/{kb}/documents/{id}/chunks` | 全部片段及其标签（含置信度和来源） |
| GET | `/api/kbs/{kb}/documents/{id}/context?chunk_id=&window=1` | 某个片段及其前后的片段 |
| PATCH | `/api/kbs/{kb}/documents/{id}` | 修改人工标签 `tag_ids` 和访问权限 `acl_groups` |
| POST | `/api/kbs/{kb}/documents/{id}/reindex` | 重新解析、向量化并打标 |
| DELETE | `/api/kbs/{kb}/documents/{id}` | 删除 |

## 标签体系

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/kbs/{kb}/tags?status=&facet=` | 列表，附每个标签的片段数 |
| POST | `/api/kbs/{kb}/tags` | 新建：`{name, facet, description, aliases[], parent_id, status}` |
| POST | `/api/kbs/{kb}/tags/import` | 批量导入：`[{name, facet, parent(名称), aliases[], description}]` |
| POST | `/api/kbs/{kb}/tags/suggest` | 冷启动：根据已入库内容建议标签，结果进入候选池 |
| PATCH | `/api/kbs/{kb}/tags/{id}` | 修改（会检查名称冲突和父子循环） |
| POST | `/api/kbs/{kb}/tags/{id}/approve` | 审核通过 |
| POST | `/api/kbs/{kb}/tags/{id}/merge/{target}` | 把当前标签合并到目标标签：片段关联迁移过去，原名称变成别名 |
| DELETE | `/api/kbs/{kb}/tags/{id}` | 删除（子标签上移一级） |

## 检索与问答

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/kbs/{kb}/search` | 只检索不生成：`{query, top_k?, filter_tag_ids[], use_tags}`。返回 `sufficiency`、`query_tags`、各路分数明细、`log_id` |
| POST | `/api/kbs/{kb}/chat` | 问答：在检索参数的基础上加 `history[]`。返回 `answer`、`sources`、`cited`、`log_id` |
| POST | `/api/kbs/{kb}/chat/stream` | 流式问答（SSE），事件顺序为 `meta` → `delta`… → `done`，出错时发 `error` |
| POST | `/api/feedback/{log_id}` | 反馈：`{rating: 1 \| -1, comment?}` |
| GET | `/api/health` | 健康检查：当前 LLM、是否已配置凭证、embedding 提供方 |
