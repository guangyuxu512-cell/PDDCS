> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 配置管理（零硬编码）

## 2.1 ENV 分层

```
project/
├── .env                    # 本地开发默认（Git 忽略）
├── .env.example            # 模板（提交到 Git，所有字段有注释）
├── .env.production         # 生产环境
├── .env.test               # 沙箱测试环境
└── config/
    ├── settings.yaml       # 业务配置（轮询间隔、LLM 参数等）
    ├── platforms.yaml      # 平台特定配置（选择器、URL 等）
    └── escalation_rules.yaml  # 转人工规则
```

## 2.2 .env.example（必须包含所有可配项）

```bash
# ============ 运行环境 ============
APP_ENV=development                    # development | production | test
DEBUG=true
LOG_LEVEL=DEBUG                        # DEBUG | INFO | WARNING | ERROR

# ============ 服务端口 ============
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=3000
CORS_ORIGINS=["http://localhost:3000"]  # JSON 数组

# ============ 浏览器引擎 ============
CHROME_EXECUTABLE_PATH=C:/Program Files/Google/Chrome/Application/chrome.exe
CHROME_HEADLESS=false                  # 生产环境 true
CHROME_ARGS=["--disable-blink-features=AutomationControlled","--disable-infobars"]
BROWSER_DATA_BASE_DIR=./data/browsers  # 每店铺子目录 {shop_id}/

# ============ 防检测 ============
STEALTH_ENABLED=true
STEALTH_WEBGL_VENDOR=Google Inc. (NVIDIA)
STEALTH_RENDERER=ANGLE (NVIDIA GeForce GTX 1660)
STEALTH_USER_AGENT=                    # 留空用随机 UA
STEALTH_TIMEZONE=Asia/Shanghai
STEALTH_LOCALE=zh-CN

# ============ Redis ============
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=20

# ============ SQLite / 数据库 ============
DATABASE_URL=sqlite+aiosqlite:///data/db/main.db

# ============ LLM 全局默认 ============
LLM_API_URL=https://api.deepseek.com/v1/chat/completions
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=200
LLM_TIMEOUT=15
LLM_MAX_RETRIES=3
LLM_BACKUP_API_URL=                    # 备用 LLM（可选）
LLM_BACKUP_API_KEY=
LLM_BACKUP_MODEL=

# ============ 知识库 ============
KNOWLEDGE_BASE_PATH=./knowledge

# ============ 并发控制 ============
MAX_LLM_CONCURRENCY_PER_SHOP=5         # 每店铺 LLM 并发数
MAX_SHOPS_PER_INSTANCE=20              # 单机最大店铺数

# ============ 监控 ============
HEALTH_ENGINE_CHECK_INTERVAL=60
HEALTH_LOGIN_CHECK_INTERVAL=1800
HEALTH_COROUTINE_CHECK_INTERVAL=30
HEALTH_LLM_CHECK_INTERVAL=300
HEALTH_QUEUE_ALERT_THRESHOLD=50

# ============ 图片存储 ============
IMAGE_STORAGE_PATH=./data/images

# ============ 通知 ============
WECOM_WEBHOOK_URL=                     # 企业微信告警（可选）
DINGTALK_WEBHOOK_URL=                  # 钉钉告警（可选）
```

## 2.3 配置加载架构

```python
# config/settings.py — pydantic-settings 统一加载
from pydantic_settings import BaseSettings
from pydantic import Field

class AppSettings(BaseSettings):
    app_env: str = Field("development", env="APP_ENV")
    debug: bool = Field(True, env="DEBUG")
    chrome_executable_path: str = Field(..., env="CHROME_EXECUTABLE_PATH")
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    llm_api_url: str = Field(..., env="LLM_API_URL")
    # ... 所有 ENV 字段

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = AppSettings()
```

**规则**：

- 代码中只能 `from config.settings import settings` 然后 `settings.xxx`
- **禁止**在代码中写死 URL、Key、路径、间隔等任何可变值
- YAML 配置用于**业务规则**（选择器、轮询间隔、转人工规则），ENV 用于**基础设施**（端口、密钥、路径）
- YAML 中的值也可以引用 ENV 变量：`${KNOWLEDGE_BASE_PATH}`
