> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 浏览器引擎（核心改动）

## 3.1 架构：一个 Browser + N 个 Context

```
┌─────────────────────────────────────────────┐
│  本地 Chrome 进程（chrome.exe）              │
│  executable_path = ENV.CHROME_EXECUTABLE_PATH │
├─────────────────────────────────────────────┤
│  BrowserContext: shop_001                    │
│  user_data_dir: data/browsers/shop_001/      │
│  ├── Page: mms.pinduoduo.com/vodka/im       │
│  └── Cookie / LocalStorage 隔离             │
├─────────────────────────────────────────────┤
│  BrowserContext: shop_002                    │
│  user_data_dir: data/browsers/shop_002/      │
│  ├── Page: mms.pinduoduo.com/vodka/im       │
│  └── Cookie / LocalStorage 隔离             │
├─────────────────────────────────────────────┤
│  BrowserContext: shop_003                    │
│  ...                                         │
└─────────────────────────────────────────────┘
```

**关键决策**（参考 PDD_POM 项目）：

- **不用 Playwright 自带的 Chromium** — 用 `CHROME_EXECUTABLE_PATH` 指定本地 Chrome
- **一个 Browser 实例** — 通过 `browser.new_context()` 创建多个隔离上下文
- **每个 Context 有独立的 user_data_dir** — `data/browsers/{shop_id}/` 隔离 Cookie、缓存、指纹
- **persistent context** — Cookie 自动持久化，重启后无需重新登录

## 3.2 Playwright 引擎实现规范

```python
# engines/playwright_engine.py 关键逻辑
class PlaywrightEngine(EngineBase):
    def __init__(self, settings: AppSettings):
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}  # shop_id → context
        self._settings = settings

    async def _ensure_browser(self) -> Browser:
        """懒启动：第一次调用时启动本地 Chrome"""
        if self._browser is None or not self._browser.is_connected():
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch_persistent_context(
                user_data_dir="",  # 全局 browser，每个 context 单独目录
                executable_path=self._settings.chrome_executable_path,
                headless=self._settings.chrome_headless,
                args=self._settings.chrome_args + [
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            # 注入防检测脚本
            await self._inject_stealth()
        return self._browser

    async def launch_instance(self, shop_id: str, config: dict) -> None:
        """为一个店铺创建独立的 BrowserContext"""
        browser = await self._ensure_browser()
        user_data_dir = Path(self._settings.browser_data_base_dir) / shop_id
        user_data_dir.mkdir(parents=True, exist_ok=True)

        context = await browser.new_context(
            storage_state=str(user_data_dir / "state.json") if (user_data_dir / "state.json").exists() else None,
            viewport={"width": 1280, "height": 800},
            locale=self._settings.stealth_locale,
            timezone_id=self._settings.stealth_timezone,
            user_agent=self._get_user_agent(shop_id),
        )
        # 防检测注入
        await context.add_init_script(path="engines/stealth.js")
        self._contexts[shop_id] = context

    async def get_handle(self, shop_id: str) -> Page:
        """返回该店铺的 Page 对象"""
        context = self._contexts[shop_id]
        pages = context.pages
        return pages[0] if pages else await context.new_page()
```

## 3.3 防检测规范（stealth.js）

必须在 `engines/stealth.js` 中实现以下防检测措施：

```jsx
// engines/stealth.js — 每个 BrowserContext 初始化时注入

// 1. 隐藏 webdriver 标记
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. 覆盖 navigator.plugins（正常浏览器有 3-5 个插件）
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// 3. 覆盖 navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en'],
});

// 4. WebGL 指纹覆盖
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Google Inc. (NVIDIA)';     // VENDOR
    if (param === 37446) return 'ANGLE (NVIDIA GeForce)';   // RENDERER
    return getParameter.call(this, param);
};

// 5. Chrome runtime 模拟
window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };

// 6. permissions 覆盖
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// 7. Canvas 指纹噪声
const toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    const context = this.getContext('2d');
    if (context) {
        const imageData = context.getImageData(0, 0, this.width, this.height);
        for (let i = 0; i < imageData.data.length; i += 4) {
            imageData.data[i] ^= 1;  // 最低位翻转，视觉不可见
        }
        context.putImageData(imageData, 0, 0);
    }
    return toDataURL.call(this, type);
};
```

**规则**：

- stealth.js 从 `.env` 读取 `STEALTH_WEBGL_VENDOR`、`STEALTH_RENDERER` 等配置注入（通过 `prompt_builder` 模板化）
- 每个店铺的 User-Agent 不同（从 UA 池随机分配，固定绑定店铺，不每次随机）
- UA 池存放在 `config/user_agents.yaml`
- 禁止直接使用默认 Playwright UA（带 `HeadlessChrome` 标识）
