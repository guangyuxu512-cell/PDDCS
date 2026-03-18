> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 模块开发规范

## engines/ — 底层引擎

- 所有引擎继承 `EngineBase`（ABC），实现 `launch_instance`、`close_instance`、`get_handle`、`is_alive`
- `playwright_engine.py`：**一个 Browser 实例 + N 个 Context**（不是 N 个 Browser）
- 使用**本地 Chrome**（`executable_path` 从 ENV 读取），禁止用 Playwright 自带 Chromium
- 每个 Context 注入 `stealth.js` 防检测
- 引擎**不处理业务逻辑**，只提供操作句柄

## adapters/ — 平台适配器

- 所有适配器实现 `protocol.py` 中的 `CustomerServiceAdapter` Protocol
- 输出统一 `StandardMessage` 数据结构
- **所有 CSS 选择器从 platforms.yaml 读取**，代码中禁止硬编码选择器字符串
- 拼多多监听模式：**DOM 轮询**（非 WebSocket 拦截，非 MutationObserver）
- 新增平台只需：写适配器 + 在 `factory.py` 注册

## ai/ — AI 层

- 禁止引入 LangChain / LlamaIndex / Agent Chain
- `llm_client.py`：重试 + 超时 + 降级，配置全从 ENV 读取
- `escalation_check.py`：纯关键词匹配，调 LLM **之前**执行
- LLM API 兼容 OpenAI chat/completions 格式

## services/ — 核心服务

- `cs_scheduler.py`：每店铺 3 协程（监听 / 处理 / 发送），互不阻塞
- `message_queue.py`：Redis List，key 格式 `cs:{inbox|outbox|escalation}:{shop_id}`
- `session_memory.py`：Redis 热存（N 轮，TTL 从 ENV 读）+ SQLite 冷存
- `knowledge_loader.py`：读 `${KNOWLEDGE_BASE_PATH}/global/` + `shops/{shop_id}/`
- 并发：每店铺 `asyncio.Semaphore(ENV.MAX_LLM_CONCURRENCY_PER_SHOP)` 限制 LLM 并发

## backend/ — FastAPI

- `dependencies.py`：统一注入 settings、redis、db session
- `middleware.py`：全局异常捕获 → `{"code": 5xxx, "msg": ...}`
- CORS origins 从 ENV 读取
- 所有路由返回统一 `{"code": 0, "msg": "success", "data": {...}}`

## frontend/ — Vue3

- `VITE_API_BASE_URL` 从 `.env` 读取
- API 请求封装在 `src/api/`，统一拦截响应
- WebSocket 封装在 `src/utils/ws.ts`，支持自动重连 + 心跳
