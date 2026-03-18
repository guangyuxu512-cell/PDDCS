> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 拼多多监听模式：DOM 轮询

参考 [拼多多网页客服自动化方案（Playwright + DOM轮询）](https://www.notion.so/Playwright-DOM-2238b89fe82f45f799d6e92131bf0b2f?pvs=21) 的测试结论：

## 4.1 为什么选 DOM 轮询（不是 WebSocket 拦截、不是 MutationObserver）

- 拼多多使用 **微前端（single-spa）+ Vue 虚拟 DOM**，MutationObserver 可能漏消息
- WebSocket 传输 **二进制 Protobuf**，解析成本高且随时可能变协议
- DOM 轮询**最稳定**：每次直接读取页面上渲染好的消息，不依赖底层传输协议

## 4.2 DOM 选择器（存放在 platforms.yaml，禁止硬编码）

```yaml
# config/platforms.yaml
pdd:
  engine: playwright
  chat_url: "https://mms.pinduoduo.com/vodka/im"
  poll_interval: 3            # 秒
  selectors:
    message_container: ".merchantMessage"
    message_text: ".msg-content-box"
    message_content: ".msg-content"
    message_index_attr: "index"
    buyer_item: ".buyer-item"
    seller_item: ".seller-item"
    robot_item: ".robot-item"
    input_box: "textarea, [contenteditable='true'], .chat-input"
    send_button: "button:has-text('发送'), [class*='send-btn']"
    file_input: "input[type='file']"
    unread_badge: ".unread-count"
    session_list: ".session-list .session-item"
```

## 4.3 监听核心逻辑

```python
# adapters/pdd.py 核心轮询逻辑
async def read_latest_messages(self, count: int = 20) -> list[StandardMessage]:
    """DOM 轮询扫描，返回新消息。选择器全部从 config 读取。"""
    selectors = self._platform_config["selectors"]
    raw_messages = await self._page.evaluate(f"""
        () => {{
            const result = [];
            document.querySelectorAll('{selectors["message_container"]}').forEach(el => {{
                const textEl = el.querySelector('{selectors["message_text"]}');
                const contentEl = el.querySelector('{selectors["message_content"]}');
                const text = textEl?.innerText?.trim();
                const index = contentEl?.getAttribute('{selectors["message_index_attr"]}') || '';
                const isBuyer = !!el.querySelector('{selectors["buyer_item"]}');
                if (text) result.push( text, index, isBuyer, timestamp: Date.now() );
            }});
            return result;
        }}
    """)
    # 去重逻辑：index + text 做 key，已知消息跳过
    ...
```

**规则**：

- 所有 CSS 选择器**必须**从 `platforms.yaml` 读取
- 拼多多页面在**微前端子上下文**中，Playwright evaluate 默认在 `top` 执行，如果选择器找不到元素，需要切换到正确的 `frame`
- 去重用 `index` 属性 + 文本内容做复合 key
- 弹窗扫描器：定时检查并关闭拼多多常见弹窗（选择器也在 yaml 配置）

## 4.4 消息去重

拼多多轮询在生产环境必须做**处理前去重**，避免 DOM 重绘、页面回流或轮询间隔抖动导致同一条消息被重复消费。

### 唯一 ID 生成规则

- 每条抓取到的消息基于 `(shop_id + buyer_id + message_text + timestamp_10s_bucket)` 生成 SHA256 hash
- `timestamp_10s_bucket` 指按 10 秒分桶后的时间戳，用于吸收同一条消息在短时间内被重复抓到的抖动
- 该 hash 作为消息唯一 ID，进入后续队列、LLM、发送链路前先做存在性检查

### Redis 去重策略

- 使用 Redis `SET` 存储已处理消息 ID
- key 建议按店铺隔离，例如 `cs:dedupe:{shop_id}`
- 每条消息 ID 写入后设置 TTL 为 600 秒
- 轮询时先检查 Redis 中是否已存在该 ID，存在则直接跳过，不再进入处理链路

### 参考实现

```python
import hashlib


def 生成消息唯一ID(shop_id: str, buyer_id: str, message_text: str, timestamp_ms: int) -> str:
    timestamp_10s_bucket = timestamp_ms // 10_000
    raw = f"{shop_id}:{buyer_id}:{message_text}:{timestamp_10s_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def 应处理消息(redis_client: Redis, shop_id: str, message_id: str) -> bool:
    redis_key = f"cs:dedupe:{shop_id}"
    exists = await redis_client.sismember(redis_key, message_id)
    if exists:
        return False

    await redis_client.sadd(redis_key, message_id)
    await redis_client.expire(redis_key, 600)
    return True
```

### 规则

- 去重检查必须发生在消息进入业务处理链路之前
- Redis 去重命中时要记录 debug 日志，便于排查页面抖动和重复轮询
- 所有平台适配器都必须复用同一套 Redis 去重策略，不能只在拼多多适配器里做临时实现
