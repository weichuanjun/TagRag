# 部署与运行

## 本地（单端口，推荐）

```bash
make install        # 安装后端与前端依赖
make serve          # 构建前端，后端在 http://localhost:8000 同时提供页面和 API
make seed           # 另开一个终端：导入演示知识库
```

数据保存在仓库根目录的 `data/`。要换位置，设置 `TAGRAG_DATA_DIR`。

## 本地开发（热重载）

```bash
make dev                       # 后端 :8000，修改代码后自动重载
cd frontend && npm start       # 前端开发服务器 :3000，/api 请求会代理到 :8000
```

## Docker Compose

```bash
cp backend/.env.example backend/.env    # 填写 Claude 和 embedding 的配置
make docker                             # 打开 http://localhost:8080
```

- 前端是 nginx 托管的静态页面，`/api/` 由 nginx 转发到后端；已关闭代理缓冲，流式输出不会被积压。
- 数据挂载到宿主机的 `./data`。
- 在 `frontend/nginx.conf` 里可以由 SSO 网关注入 `X-User-Id` / `X-User-Groups`，并且必须丢弃客户端自带的这两个请求头。

## 云端开发环境（claude.ai/code）

仓库已经可以直接在云端会话中运行：

```bash
make install && make serve
```

服务起来后，在会话中把 8000 端口作为预览打开即可。Claude 凭证请在环境设置中添加 `ANTHROPIC_API_KEY`，下次启动会话时生效。

## 上线前检查清单

- [ ] 设置 `TAGRAG_API_KEYS`，并由网关注入用户身份
- [ ] 数据库改用 PostgreSQL（`TAGRAG_DATABASE_URL`），并定期备份 `data/files`
- [ ] embedding 改用 `voyage` 或 `local`（**不要**在生产环境使用 `hash`）
- [ ] 把 `TAGRAG_CORS_ORIGINS` 收紧到实际使用的前端域名
- [ ] 用自己的问题集跑一遍 `backend/scripts/evaluate.py`，确认检索质量
- [ ] 给每个 Agent 单独配置 `TAGRAG_AGENT_ID` 和最小权限的 `TAGRAG_AGENT_GROUPS`
