> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 沙箱测试环境

## 7.1 测试分层

```
tests/
├── unit/          → pytest，纯逻辑测试，mock 所有外部依赖
├── integration/   → pytest，使用真实 Redis（docker-compose 启动）
├── sandbox/       → 模拟拼多多页面 + 模拟 LLM，端到端验证
└── e2e/           → 完整流程（需要真实浏览器，CI 中可选跳过）
```

## 7.2 沙箱测试模式

```python
# tests/sandbox/mock_pdd_page.html
# 模拟拼多多客服页面的 DOM 结构，用于测试适配器
# 包含 .merchantMessage、.buyer-item、.msg-content-box 等元素
# Playwright 加载本地 HTML，测试消息检测 + 发送逻辑

# tests/sandbox/mock_server.py
# FastAPI mock 服务，模拟 LLM API 响应
# 固定返回预设回复，测试 prompt 拼装 + 回复流程
```

## 7.3 ENV 测试隔离

```bash
# .env.test
APP_ENV=test
REDIS_URL=redis://localhost:6379/1       # 用 db=1 隔离
DATABASE_URL=sqlite+aiosqlite:///:memory:  # 内存数据库
LLM_API_URL=http://localhost:9999/v1/chat/completions  # mock server
CHROME_HEADLESS=true
STEALTH_ENABLED=false                     # 测试环境关闭防检测
```

## 7.4 Makefile 命令

```makefile
dev:        uvicorn backend.main:app --reload --env-file .env
test:       APP_ENV=test pytest tests/unit tests/integration -v
sandbox:    APP_ENV=test python -m tests.sandbox.mock_server & pytest tests/sandbox -v
lint:       ruff check . && mypy .
format:     ruff format .
migrate:    python scripts/migrate_db.py
```
