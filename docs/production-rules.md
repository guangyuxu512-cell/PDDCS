> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 高并发与生产级规则

## 9.1 性能基线

- 单机支撑 ≤ 20 店铺（`MAX_SHOPS_PER_INSTANCE` 从 ENV 配置）
- 每店铺 LLM 并发 ≤ 5（`MAX_LLM_CONCURRENCY_PER_SHOP`）
- DOM 轮询间隔 ≥ 3 秒（Web），≥ 5 秒（桌面 UIA）
- LLM 超时 15 秒，重试 3 次
- Redis 连接池 ≤ 20（`REDIS_MAX_CONNECTIONS`）

## 9.2 资源隔离

- 每店铺 3 个独立协程，`asyncio.TaskGroup` 管理生命周期
- 一个店铺崩溃不影响其他（`return_exceptions=True`）
- BrowserContext 隔离：Cookie / Cache / LocalStorage 完全独立
- Redis 队列按 `shop_id` 隔离

## 9.3 内存管理

- 已知消息 set 定期清理（保留最近 500 条，避免内存泄漏）
- SQLite WAL 模式（并发读写性能）
- Playwright Page 定期 `page.reload()` 防止内存泄漏（每 4 小时）

## 9.4 优雅启停

```python
# backend/main.py lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await redis_pool.connect()
    await engine_manager.start()
    yield
    # 关闭
    await scheduler.stop_all()       # 等待所有协程结束
    await engine_manager.close_all() # 关闭所有浏览器
    await redis_pool.disconnect()
```

## 9.5 日志规范

```python
# 格式：[时间] [级别] [shop_id] [模块] 消息
logger.info(f"[{shop_id}] [monitor] 检测到新消息: {text[:50]}")
logger.error(f"[{shop_id}] [llm] LLM 调用失败: {error}", exc_info=True)
```

- 日志级别从 `ENV.LOG_LEVEL` 读取
- 生产环境：`INFO`，输出到文件 + stdout
- 开发环境：`DEBUG`，仅 stdout
- 敏感信息（API Key、Cookie）禁止出现在日志中

## 9.6 安全规则

- `.env` 文件**必须**在 `.gitignore` 中
- API Key 在日志中显示为 `sk-***xxx`（只露最后 3 位）
- Cookie 文件存储目录权限 `600`
- SQLite 中的 `llm_api_key` 字段加密存储（Fernet 对称加密）
- 前端不存储任何敏感信息，所有密钥操作通过后端 API

## 12. 降级与容错

```
主 LLM → 备用 LLM → 规则引擎匹配 → 兜底话术 + 转人工
```

- 引擎崩溃：60 秒检测，自动重启
- 登录失效：30 分钟检测，自动重登，失败通知
- 协程挂掉：30 秒检测，自动重启
- Redis 断连：自动重连（redis-py 内建）
- 消息积压 > 阈值：告警（阈值从 ENV 读取）
