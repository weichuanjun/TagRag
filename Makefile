# TagRAG 常用命令。数据默认存放在仓库根目录的 data/。
ROOT := $(abspath .)
export TAGRAG_DATA_DIR ?= $(ROOT)/data
PORT ?= 8000

.PHONY: help install web serve dev seed test mcp docker

help:  ## 列出所有命令
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

install:  ## 安装后端与前端依赖
	pip install -r backend/requirements-dev.txt
	cd frontend && npm ci --no-audit --no-fund

web:  ## 构建前端
	cd frontend && npm run build

serve: web  ## 构建前端，并在单端口启动完整系统 (http://localhost:8000)
	cd backend && TAGRAG_WEB_DIR=$(ROOT)/frontend/build uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

dev:  ## 开发模式：后端热重载（前端另开终端执行 cd frontend && npm start）
	cd backend && uvicorn app.main:app --reload --port $(PORT)

seed:  ## 导入演示知识库（需先启动服务）
	cd backend && python scripts/seed_demo.py --base http://localhost:$(PORT)

test:  ## 运行后端测试（离线，无需 API Key）
	cd backend && python -m pytest -q

mcp:  ## 以 stdio 启动 MCP 服务器（供 Claude 调试）
	cd backend && python -m app.mcp_server

docker:  ## 用 Docker Compose 启动 (http://localhost:8080)
	docker compose up -d --build
