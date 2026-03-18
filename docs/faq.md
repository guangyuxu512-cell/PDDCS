> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 常见问题

> 当前仓库原始 `AGENTS.md` 没有独立的第 13 章 FAQ。本页基于现有章节中的设计决策、浏览器引擎说明和拼多多监听说明整理，供按需查阅。

## 为什么用本地 Chrome，不用 Playwright 自带的 Chromium？

项目要求通过 `CHROME_EXECUTABLE_PATH` 指向本地 Chrome，并结合 `connect_over_cdp()` 或 `launch(executable_path=ENV)` 使用真实浏览器环境。这样更贴近真实用户指纹，也方便复用本地登录态、Cookie 和既有浏览器能力。

## 为什么是一个 Browser 实例，每店铺一个 BrowserContext？

共享一个 Browser 进程可以降低资源占用，而 `BrowserContext` 又能隔离 Cookie、缓存、LocalStorage 和指纹配置。这样既满足多店铺并发，又避免为每个店铺拉起独立浏览器进程。

## 为什么拼多多选择 DOM 轮询，而不是 WebSocket 拦截或 MutationObserver？

现有结论是：拼多多使用微前端和 Vue 虚拟 DOM，`MutationObserver` 可能漏消息；WebSocket 又是二进制 Protobuf，协议变动风险高。DOM 轮询直接读取已经渲染到页面上的消息，稳定性最好。

## 为什么坚持单 LLM，不做多 Agent？

规则、知识和风控统一塞进 `system prompt`，一次调用生成回复，降低链路复杂度。转人工依赖关键词匹配前置处理，不再引入额外 Agent 编排框架。

## 为什么知识库直接用 Markdown，不上向量库？

项目默认知识规模较小，`knowledge/global/` 和 `knowledge/shops/{shop_id}/` 的 Markdown 内容通常可以直接装入现代大上下文模型，避免额外的向量库、索引同步和召回复杂度。

## 为什么平台识别放在配置里，而不是运行时自动检测？

平台与底层引擎的映射通过 `config/platforms.yaml` 明确声明，例如 `pdd -> playwright`、`douyin -> uia`。这样规则可审计、可配置，也更符合“零硬编码”和平台扩展的要求。
