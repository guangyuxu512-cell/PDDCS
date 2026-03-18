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
