> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 目录结构（生产级）

```
project/
├── .env                           # 本地开发配置（Git 忽略）
├── .env.example                   # 配置模板（提交到 Git）
├── .env.production                # 生产环境配置
├── .env.test                      # 沙箱测试环境配置
├── pyproject.toml                 # 依赖管理（Poetry / uv）
├── Makefile                       # 常用命令：make dev / make test / make lint
├── docker-compose.yaml            # 本地开发 Redis + 前端
│
├── config/                        # 业务配置（YAML，可热更新）
│   ├── settings.py                # pydantic-settings 加载 .env
│   ├── platforms.yaml             # 平台配置（选择器、URL、轮询间隔）
│   ├── escalation_rules.yaml      # 转人工规则
│   └── user_agents.yaml           # UA 池（每店铺绑定一个 UA）
│
├── engines/                       # 底层引擎（抽象层）
│   ├── __init__.py
│   ├── base.py                    # EngineBase ABC
│   ├── playwright_engine.py       # Web 引擎（本地 Chrome + 多 Context）
│   ├── uia_engine.py              # 桌面引擎（UIAutomation）
│   └── stealth.js                 # 浏览器防检测注入脚本
│
├── adapters/                      # 平台适配器（Protocol 抽象层）
│   ├── __init__.py
│   ├── protocol.py                # CustomerServiceAdapter Protocol + StandardMessage
│   ├── pdd.py                     # 拼多多适配器（DOM 轮询）
│   ├── douyin_desktop.py          # 抖店适配器（UIA）
│   ├── qianniu.py                 # 千牛适配器（UIA）
│   └── factory.py                 # AdapterFactory
│
├── ai/                            # AI 层（单 LLM）
│   ├── __init__.py
│   ├── llm_client.py              # LLM HTTP 封装（重试 + 超时 + 降级）
│   ├── prompt_builder.py          # system prompt 拼装
│   └── escalation_check.py        # 转人工关键词前置检测
│
├── services/                      # 核心业务服务
│   ├── __init__.py
│   ├── message_queue.py           # Redis 消息队列
│   ├── session_memory.py          # 会话记忆（Redis + SQLite）
│   ├── cs_scheduler.py            # 客服调度器（每店铺 3 协程）
│   ├── shop_registry.py           # 店铺注册表
│   ├── escalation.py              # 人工转接
│   ├── health_monitor.py          # 健康监控 + 自动恢复
│   └── knowledge_loader.py        # MD 知识库加载
│
├── auth/                          # 登录与凭证
│   ├── __init__.py
│   ├── cookie_manager.py          # Cookie 健康检查
│   ├── login_pdd.py               # 拼多多登录
│   ├── login_douyin.py            # 抖店登录
│   └── login_qianniu.py           # 千牛登录
│
├── backend/                       # FastAPI 后端
│   ├── __init__.py
│   ├── main.py                    # 启动入口 + lifespan
│   ├── dependencies.py            # FastAPI 依赖注入（settings, redis, db）
│   ├── middleware.py              # 日志 + 异常捕获中间件
│   ├── api/
│   │   ├── __init__.py
│   │   ├── shop.py
│   │   ├── customer_service.py
│   │   ├── escalation.py
│   │   ├── knowledge.py
│   │   ├── settings.py
│   │   ├── dashboard.py
│   │   └── auth.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── shop.py
│   │   ├── session.py
│   │   └── settings.py
│   └── websocket/
│       ├── __init__.py
│       ├── logs.py
│       └── chat_monitor.py
│
├── frontend/                      # Vue3 前端
│   ├── .env                       # 前端 ENV（VITE_API_BASE_URL 等）
│   ├── .env.production
│   └── src/
│       ├── api/                   # API 封装层
│       ├── views/
│       │   ├── Dashboard.vue
│       │   ├── ShopManage.vue
│       │   ├── ChatMonitor.vue
│       │   ├── KnowledgeBase.vue
│       │   ├── EscalationQueue.vue
│       │   └── Settings.vue
│       ├── components/
│       │   ├── ShopCard.vue
│       │   ├── MarkdownEditor.vue
│       │   └── ChatBubble.vue
│       └── utils/
│           └── ws.ts              # WebSocket 封装（自动重连）
│
├── knowledge/                     # 知识库 MD 文件
│   ├── global/
│   └── shops/{shop_id}/
│
├── data/                          # 持久化数据（Git 忽略）
│   ├── browsers/{shop_id}/        # 每店铺浏览器数据目录
│   ├── cookies/
│   ├── images/
│   └── db/main.db
│
├── tests/                         # 测试
│   ├── conftest.py                # pytest fixtures（mock Redis, mock LLM）
│   ├── unit/                      # 单元测试
│   │   ├── test_escalation_check.py
│   │   ├── test_prompt_builder.py
│   │   ├── test_message_queue.py
│   │   └── test_rule_matching.py
│   ├── integration/               # 集成测试
│   │   ├── test_pdd_adapter.py    # 使用 sandbox 模式
│   │   └── test_scheduler.py
│   ├── sandbox/                   # 沙箱测试环境
│   │   ├── mock_pdd_page.html     # 模拟拼多多客服页面 DOM
│   │   ├── mock_server.py         # 模拟 LLM API 响应
│   │   └── README.md
│   └── e2e/                       # 端到端测试
│       └── test_full_flow.py
│
├── scripts/                       # 运维脚本
│   ├── save_cookies.py            # 首次登录保存 Cookie
│   ├── health_check.py            # 手动健康检查
│   └── migrate_db.py             # 数据库迁移
│
└── docs/
    └── AGENTS.md                  # 本文件（复制到仓库根目录）
```
