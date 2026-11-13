# TagRAG：基于受控标签体系的企业级 RAG

TagRAG 用一套**按知识库治理的标签体系（taxonomy）**来增强检索。标签由人定义、由机器自动打、由人审核，参与「召回 + 排序 + 过滤 + 权限」全流程，回答带可点击的来源引用。

> v2 是一次彻底重构。代码分析、代码检索、多 Agent（AutoGen）、知识图谱可视化、Agent 提示词管理、调试页等与 RAG 核心无关的功能都已移除，只保留并重做 RAG 核心。

---

## 一、旧版设计的问题

| # | 问题 | 后果 |
|---|------|------|
| 1 | **查询时让 LLM 生成标签，没有就新建** | 每次提问都可能往库里写新标签，标签越积越多。新标签没有关联任何文档，过滤时等于白查 |
| 2 | **标签打在文档级**，所有 chunk 继承同样的标签 | 一份 50 页的制度，每一段都带着「财务、人事、IT」，标签失去区分度 |
| 3 | **标签作硬过滤**（`tag_x == True` 的 OR），查不到再退回普通检索 | 标签一旦打错或漏打，召回直接归零；退回后标签也就不起作用了 |
| 4 | **T-CUS 评分有 bug** | ① 把 Chroma 返回的**距离**（越小越好）当**相似度**（越大越好）用，语义分完全反了；② 贪心选择读的是 `t_cus_score` 字段，实际写入的是 `score`，密度全为 0，选出的片段近乎随机；③ Jaccard 里出现 `union > 0`（集合和整数比较）会抛异常 |
| 5 | 标签是全局唯一的，不区分知识库 | 不同业务线的标签互相污染 |
| 6 | 一次问答要多次调用 LLM（AutoGen 多 Agent） | 慢、贵、不稳定，换来的效果收益却不明显 |
| 7 | 没有混合检索、权限控制、去重、增量更新、评测、反馈 | 达不到企业可用的程度 |

## 二、新设计

**核心原则：标签是受控词表，是检索的「软信号 + 显式过滤维度」，而不是 LLM 随手生成的字符串。**

```
                         ┌─────────── 入库 ───────────┐
 PDF/Word/MD/HTML/Excel → 结构化解析（保留标题路径）→ 结构感知切块
                        → 向量化（标题路径 + 正文）
                        → chunk 级打标：关键词/别名 + 向量相似 + LLM 多标签分类（只在受控词表内选）
                        → LLM 提议的新标签进入「候选池」，等人工审核
                        → 文档标签 = chunk 标签聚合 + 人工指定（如部门，继承到所有 chunk）

                         ┌─────────── 查询 ───────────┐
 问题 → 向量化 → 匹配标签 T(q)（关键词/别名 + 向量，不调用 LLM，不新建标签）
      → 三路召回：稠密向量 │ BM25 │ 标签通道（命中 T(q) 及其子标签的 chunk）
      → 加权 RRF 融合 → 标签加权（层级距离衰减 × 置信度）→ MMR 去冗余
      → 在 token 预算内组装上下文 → LLM 带编号引用作答（证据不足时明确拒答）
   * ACL 在召回之前过滤，没有权限的内容不会进入 LLM 上下文
   * 用户显式选择的标签作为硬过滤（自动包含子标签；同一维度内取 OR，不同维度之间取 AND）
```

### 关键改进

- **标签治理**：每个知识库一套独立的标签体系，标签带维度（主题/产品/部门/文档类型…）、层级、别名，状态分为 `active / candidate / deprecated` 三种。
  - 冷启动：「智能建议」根据已入库内容生成一批候选标签，审核通过后启用。
  - 日常运行：LLM 打标时可以提议新标签，但只进入候选池，经人工**通过、合并到已有标签（原名自动变成别名）或删除**后才生效。
  - 标签体系调整后，点「重新打标」即可，不需要重新上传或重新向量化。
- **chunk 级打标**：三路信号合并，每个标签记录置信度和来源（llm / keyword / embedding / inherited），可解释、可审计。
- **检索稳健**：标签作为一路独立召回加上排序加权。标签打错只会让该片段的排名变化，不会让召回归零。设置 `use_tags=false` 就能做 A/B 对比。
- **结构感知切块**：识别 Markdown 标题、Word 标题样式，以及中文编号标题（第一章、一、（一）、1.1）。切块不跨章节，表格按「列名: 值」展开。小章节合并时保留各自的子标题。
- **企业特性**：
  - 文档级 ACL：由网关注入 `X-User-Groups`，权限过滤在召回之前执行。
  - API Key 鉴权。
  - 按内容哈希去重。
  - 后台异步入库，服务重启后自动续跑未完成的任务。
  - SSE 流式输出。
  - 问答日志与 👍/👎 反馈，可以用来积累评测集。
  - 统计看板。
  - 检索评测脚本，对比 Hit@K 和 MRR。
- **模型无关**：LLM 和 Embedding 都走 OpenAI 兼容协议（OpenAI、Azure、DeepSeek、通义、智谱、vLLM、Ollama 均可）。Embedding 也可以用本地 sentence-transformers（推荐 `BAAI/bge-m3`、`bge-small-zh-v1.5`）。不配置 LLM 时，系统降级为抽取式回答，仍然可以完整运行。

## 三、快速开始

### Docker

```bash
cd TagRag
cp backend/.env.example backend/.env   # 填写 LLM / Embedding 配置
docker compose up -d --build
# 打开 http://localhost:8080
```

### 本地开发

```bash
# 后端
cd TagRag/backend
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000     # API 文档：http://localhost:8000/docs
pytest -q                                      # 测试（离线可运行，不需要 API Key）

# 前端
cd TagRag/frontend
npm install
npm start                                      # http://localhost:3000，/api 代理到 8000
```

### 推荐上手流程

1. 新建知识库，到「标签体系 → 批量导入」导入你们的标签。

   示例：

   ```json
   [{"name":"财务","facet":"department"},
    {"name":"报销","facet":"topic","parent":"财务","aliases":["差旅费"],"description":"费用报销制度与流程"}]
   ```

   如果还没有现成的标签，可以先上传文档，再点「智能建议」。
2. 上传文档时可以为整批文档指定标签（如部门）和可访问的用户组。
3. 在「文档管理 → 查看片段」里检查打标效果。调整标签体系后，点「重新打标」。
4. 在问答页提问。可以按标签限定范围，也可以关闭「标签增强」对比效果。

## 四、主要 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/kbs` | 知识库列表 / 创建 |
| POST | `/api/kbs/{kb}/documents` | 上传（multipart：`files`、`tag_ids`、`acl_groups`） |
| GET | `/api/kbs/{kb}/documents/{id}/chunks` | 查看片段及其标签 |
| PATCH | `/api/kbs/{kb}/documents/{id}` | 修改人工标签 / 权限 |
| GET/POST | `/api/kbs/{kb}/tags` | 标签列表 / 新建 |
| POST | `/api/kbs/{kb}/tags/import` | 批量导入标签体系 |
| POST | `/api/kbs/{kb}/tags/suggest` | 冷启动：自动建议标签（进入候选池） |
| POST | `/api/kbs/{kb}/tags/{id}/approve` | 审核通过 |
| POST | `/api/kbs/{kb}/tags/{id}/merge/{target}` | 合并标签 |
| POST | `/api/kbs/{kb}/retag` | 全库重新打标 |
| POST | `/api/kbs/{kb}/search` | 只检索，返回各路分数明细（调试 / 评测用） |
| POST | `/api/kbs/{kb}/chat` | 问答 |
| POST | `/api/kbs/{kb}/chat/stream` | 流式问答（SSE：`meta` → `delta` → `done`） |
| POST | `/api/feedback/{log_id}` | 👍/👎 反馈 |

### 认证与权限

- 设置 `TAGRAG_API_KEYS` 后，所有请求都需要带 `X-API-Key`。
- 用户组通过 `X-User-Groups` 传入，**应由网关或 SSO 注入**，并且必须丢弃客户端自己带的这个头。
- 包含 `admin` 组的用户才能执行管理操作，并可以查看全部文档。

## 五、调参与评测

常用参数见 `backend/.env.example`：`TAGRAG_TAG_BOOST`、`TAGRAG_FINAL_TOP_K`、`TAGRAG_CONTEXT_TOKEN_BUDGET`、`TAGRAG_QUERY_TAG_THRESHOLD`、`TAGRAG_CANDIDATE_AUTO_PROMOTE`。

```bash
# eval.jsonl 每行：{"query": "...", "expected_doc": "xx.pdf"} 或 {"query": "...", "expected_text": "关键原文"}
python backend/scripts/evaluate.py --kb 1 --data eval.jsonl --k 5
# 输出 hybrid+tags 和 hybrid 两种模式的 Hit@5 与 MRR，用来量化标签体系带来的收益
```

## 六、目录结构

```
TagRag/backend/app/
  config.py            # 全部配置（环境变量 TAGRAG_*）
  models.py            # 知识库 / 文档 / 片段 / 标签 / chunk 标签 / 问答日志
  ingestion/           # 解析(parsers) → 切块(chunker) → 入库流水线(pipeline)
  tagging/             # 标签体系治理(taxonomy) + 打标与查询标签匹配(tagger)
  retrieval/           # 内存索引(稠密 + BM25 + 标签倒排) + 三路召回融合检索(retriever)
  rag.py               # 带引用的生成 / 拒答 / 降级
  api/                 # REST 接口
TagRag/frontend/src/pages/  # 智能问答 / 文档管理 / 标签体系
```

## 七、规模与后续路线

- 当前索引是进程内的 numpy 矩阵 + BM25，适合单机**数十万片段**。超过这个规模，或需要多实例部署时，可以把 `retrieval/index.py` 换成 pgvector、Milvus、Qdrant 或 Elasticsearch，数据库换成 PostgreSQL（设置 `TAGRAG_DATABASE_URL` 即可）。
- 后台任务目前使用 FastAPI BackgroundTasks。大批量入库时，建议换成 Celery 或 RQ。
- 可选增强：
  - 用 Cross-Encoder 重排（bge-reranker）。
  - 对多轮对话中的问题做改写。
  - 扫描件 OCR。
  - 把 👎 反馈自动汇总成评测集。
