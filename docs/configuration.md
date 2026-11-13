# 配置参考

所有配置都可以通过环境变量设置，也可以写进 `backend/.env`（模板见 `backend/.env.example`）。变量统一以 `TAGRAG_` 开头。

> `.env` 文件只加载 `TAGRAG_` 开头的变量。如果要把 Claude 的 Key 写进 `.env`，请用 `TAGRAG_ANTHROPIC_API_KEY`；`ANTHROPIC_API_KEY` 只在作为系统环境变量设置时才生效。

## 存储与安全

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TAGRAG_DATA_DIR` | `./data` | 数据目录，存放 SQLite 数据库和上传的原始文件 |
| `TAGRAG_DATABASE_URL` | `sqlite:///{DATA_DIR}/tagrag.db` | 生产环境建议用 PostgreSQL，例如 `postgresql+psycopg://user:pass@host/db` |
| `TAGRAG_API_KEYS` | 空 | 逗号分隔。为空时不校验（只适合本地开发） |
| `TAGRAG_CORS_ORIGINS` | `*` | 允许跨域访问的前端来源 |
| `TAGRAG_MAX_UPLOAD_MB` | `50` | 单个上传文件的大小上限 |
| `TAGRAG_WEB_DIR` | 空 | 指向 `frontend/build` 后，由后端直接提供前端页面，只需一个端口 |

## LLM

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TAGRAG_LLM_PROVIDER` | `claude` | `claude`：Anthropic 官方 SDK；`openai`：OpenAI 兼容服务 |
| `TAGRAG_ANTHROPIC_API_KEY` | 空 | 为空时按 SDK 默认顺序查找凭证：`ANTHROPIC_API_KEY` → `ANTHROPIC_AUTH_TOKEN` → `ant auth login` 的配置 |
| `TAGRAG_ANTHROPIC_BASE_URL` | 空 | 自定义 Anthropic API 地址 |
| `TAGRAG_CLAUDE_MODEL` | `claude-opus-5-5` | Claude 模型 |
| `TAGRAG_CLAUDE_EFFORT` | `medium` | 作答的思考深度：`low` / `medium` / `high` / `xhigh` / `max` |
| `TAGRAG_TAGGING_EFFORT` | `low` | 打标的思考深度 |
| `TAGRAG_LLM_BASE_URL` / `TAGRAG_LLM_API_KEY` / `TAGRAG_LLM_MODEL` | OpenAI | 仅在 `provider=openai` 时使用 |
| `TAGRAG_LLM_TIMEOUT` | `60` | 请求超时（秒） |

## Embedding

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TAGRAG_EMBEDDING_PROVIDER` | `hash` | `voyage`（Anthropic 推荐）/ `local`（sentence-transformers）/ `openai` / `hash`（只用于离线测试） |
| `TAGRAG_EMBEDDING_MODEL` | `text-embedding-3-small` | 例如 `voyage-3.5`、`BAAI/bge-m3`。Voyage 的模型名请以官网的当前列表为准 |
| `TAGRAG_EMBEDDING_API_KEY` / `TAGRAG_EMBEDDING_BASE_URL` | 空 | `openai` 模式下为空时，复用 LLM 的设置 |
| `TAGRAG_EMBEDDING_BATCH_SIZE` | `64` | |

> 更换 embedding 模型后，已入库文档的向量维度会不一致。请对每篇文档执行「重新解析与索引」。

## 切块与打标

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TAGRAG_CHUNK_TOKENS` | `450` | 片段目标长度（近似 token 数） |
| `TAGRAG_CHUNK_OVERLAP_TOKENS` | `60` | 相邻片段的重叠 |
| `TAGRAG_TAGGING_MODE` | `auto` | `auto`：有 LLM 时用 LLM，否则用向量 + 关键词；`llm`；`embedding` |
| `TAGRAG_TAGGING_BATCH_SIZE` | `6` | 每次请求 LLM 打标的片段数 |
| `TAGRAG_TAG_EMBEDDING_THRESHOLD` | `0.45` | 向量打标的相似度阈值 |
| `TAGRAG_MAX_TAGS_PER_CHUNK` | `5` | 每个片段最多保留的标签数 |
| `TAGRAG_CANDIDATE_AUTO_PROMOTE` | `0` | 候选标签被提议多少次后自动启用；`0` 表示必须人工审核 |

## 检索

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TAGRAG_DENSE_TOP_K` / `TAGRAG_SPARSE_TOP_K` | `50` | 稠密 / BM25 各自召回的数量 |
| `TAGRAG_RRF_K` | `60` | RRF 融合常数 |
| `TAGRAG_QUERY_TAG_THRESHOLD` | `0.5` | 问题与标签匹配的相似度阈值 |
| `TAGRAG_MAX_QUERY_TAGS` | `5` | 每个问题最多匹配的标签数 |
| `TAGRAG_TAG_BOOST` | `0.35` | 标签加权强度；`0` 表示关闭 |
| `TAGRAG_HIERARCHY_DECAY` | `0.5` | 标签层级每相隔一层的衰减系数 |
| `TAGRAG_MMR_LAMBDA` | `0.75` | 相关性与多样性的权衡，越大越偏向相关性 |
| `TAGRAG_FINAL_TOP_K` | `8` | 最终返回的片段数 |
| `TAGRAG_CONTEXT_TOKEN_BUDGET` | `3000` | 交给 LLM 的上下文 token 上限 |
| `TAGRAG_MIN_RELEVANCE` | `0` | 融合分数低于此值的片段会被丢弃 |
