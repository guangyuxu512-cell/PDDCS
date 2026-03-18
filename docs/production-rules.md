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

## 9.4 发送频率限制

- 每条 AI 回复发送前必须增加 random delay，默认范围 2-5 秒，模拟人工打字速度
- delay 范围不能写死，必须从 `config/platforms.yaml` 读取 `reply_delay_min_ms` 与 `reply_delay_max_ms`
- 同一店铺同一时刻只允许一个发送操作，使用 `asyncio.Lock` per shop 串行化发送链路
- random delay 应发生在最终发送前，避免多个协程提前 sleep 后同时出队

```python
# services/cs_scheduler.py
shop_send_lock = self._shop_send_locks[shop_id]
delay_min = platform_config["reply_delay_min_ms"]
delay_max = platform_config["reply_delay_max_ms"]

async with shop_send_lock:
    delay_ms = random.randint(delay_min, delay_max)
    await asyncio.wait_for(asyncio.sleep(delay_ms / 1000), timeout=(delay_max / 1000) + 1)
    await asyncio.wait_for(adapter.send_text(reply_text), timeout=15)
```

## 9.5 优雅启停

```python
# backend/main.py / services/cs_scheduler.py
loop = asyncio.get_running_loop()
loop.add_signal_handler(signal.SIGTERM, scheduler.request_shutdown)
loop.add_signal_handler(signal.SIGINT, scheduler.request_shutdown)
```

- 必须注册 `SIGTERM` / `SIGINT` 信号处理
- 收到信号后按顺序执行：
  1. 设置 shutdown flag
  2. 各店铺协程停止接收新消息
  3. 等待当前处理中的消息完成，最长 30 秒超时
  4. 关闭所有 `BrowserContext`
  5. 关闭 `Browser`
  6. 关闭 Redis 连接
  7. 正常退出
- 若 30 秒超时仍有消息未完成，必须强制退出，并在日志中记录未完成的消息 ID
- 优雅停机期间不得再派发新的 LLM 请求和发送动作

## 9.6 监控告警

- `health_monitor` 每 60 秒检查一次：
  - 各店铺 `BrowserContext` 是否存活
  - Cookie 是否有效
  - Redis 是否可达
  - 最近 5 分钟是否有消息处理
- 异常时通过 webhook 推送通知，webhook URL 从 `.env` 的 `ALERT_WEBHOOK_URL` 读取
- 连续 3 次健康检查失败才告警，避免瞬时抖动和误报
- 告警内容至少包含 `shop_id`、异常类型、失败次数、最近一条消息时间和恢复建议

## 9.7 并发边界

- 单机最大店铺数默认 10，通过 `.env` 中的 `MAX_SHOPS` 配置
- 超过上限时拒绝启动新店铺，API 返回错误码 `1001`
- 每店铺内存预估：`1 BrowserContext ≈ 150-300MB`
- 10 店铺场景建议预留 `3-4GB RAM`，同时为 Redis、FastAPI 和桌面自动化进程保留额外余量
- 当店铺数接近上限时，应优先告警而不是继续扩容单进程负载

## 9.8 日志规范

```python
# 格式：[时间] [级别] [shop_id] [模块] 消息
logger.info(f"[{shop_id}] [monitor] 检测到新消息: {text[:50]}")
logger.error(f"[{shop_id}] [llm] LLM 调用失败: {error}", exc_info=True)
```

- 日志级别从 `ENV.LOG_LEVEL` 读取
- 生产环境：`INFO`，输出到文件 + stdout
- 开发环境：`DEBUG`，仅 stdout
- 敏感信息（API Key、Cookie）禁止出现在日志中

## 9.9 安全规则

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
