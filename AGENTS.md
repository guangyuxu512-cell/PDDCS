# AGENTS.md — 多平台电商智能客服自动化系统

> 本文件是 Codex / Cursor / AI 编码助手的唯一入口。遵守铁律，按需阅读子文档。

## 0. 铁律（违反即打回）

1. **零硬编码** — 所有可变值必须来自 `.env` 或 `config/*.yaml`
2. **单 LLM，禁止多 Agent** — 不引入 LangChain / LlamaIndex / Agent Chain
3. **本地 Chrome** — 不用 Playwright 自带 Chromium，用 `executable_path=ENV`
4. **一 Browser 多 Context** — 每店铺一个 BrowserContext，共享一个 Browser 实例
5. **Protocol / ABC 抽象层** — 禁止在业务代码中直接 import 具体实现类
6. **完整类型注解** — 所有公共函数必须 `def func(x: str) -> dict[str, Any]:`
7. **禁止全局可变状态** — 依赖注入，不用模块级全局变量
8. **所有 await 必须有超时** — 禁止无超时的异步操作
9. **消息去重** — 所有适配器必须在处理前做 Redis 去重检查
10. **密码 / Cookie 禁止明文存储** — 必须使用 `backend/core/crypto.py` 加密后写入数据库，接口只返回 `hasPassword` / `cookieFingerprint`

## 1. 项目简介

多平台电商智能客服自动化系统，支持拼多多（Web）、抖店（桌面）、千牛（桌面）。24 小时无人值守，单 LLM 架构，事件驱动，多店铺并发。

技术栈：Python 3.11+ / FastAPI / asyncio / Playwright（连接本地 Chrome）/ pywinauto / UIAutomation / Redis / SQLite / Vue3 + Vite + TypeScript + Element Plus / python-dotenv + pydantic-settings + YAML

## 2. 文档路由（按需阅读）

| 当你要做什么 | 阅读哪个文档 |
|---|---|
| 修改 `.env`、配置加载、pydantic-settings | `docs/config-management.md` |
| 浏览器引擎、Chrome 启动、BrowserContext、防检测 `stealth.js` | `docs/browser-engine.md` |
| 拼多多客服监听、DOM 轮询、CSS 选择器 | `docs/pdd-monitor.md` |
| 查看或调整目录结构 | `docs/directory-structure.md` |
| 开发 `engines/`、`adapters/`、`ai/`、`services/`、`backend/`、`frontend/` 模块 | `docs/module-dev-spec.md` |
| 性能优化、并发控制、日志、安全、优雅启停、降级容错 | `docs/production-rules.md` |
| 写测试、沙箱环境、mock、Makefile 测试命令 | `docs/testing.md` |
| Python、Vue3、Git 编码风格 | `docs/coding-standards.md` |
| 新增一个平台（如京东、快手） | `docs/new-platform-checklist.md` |
| 架构设计疑问与常见选型解释 | `docs/faq.md` |

## 3. 关键设计决策（速查）

- **平台识别**：`config/platforms.yaml` 配置字段，非运行时检测
- **API 约定**：统一响应 `{"code": 0, "msg": "success", "data": {...}}`
- **错误码**：`0` 成功 / `1xxx` 业务 / `2xxx` 认证 / `3xxx` AI / `5xxx` 系统
- **AI Key**：全局默认 `.env` + 店铺可覆盖（SQLite `shops.llm_api_key`、`shops.llm_model`）
- **知识库**：纯 MD 文件 `knowledge/global/` + `knowledge/shops/{shop_id}/`，不用向量库
- **降级链路**：主 LLM → 备用 LLM → 规则引擎匹配 → 兜底话术 + 转人工

需要细节时，按上面的路由表进入 `docs/` 子文档，不在主文件堆叠长篇规则。
