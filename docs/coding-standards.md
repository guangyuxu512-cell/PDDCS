> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 编码规范

## Python 后端

- Python 3.11+，全面 `async/await`
- 类型注解 100% 覆盖：`def func(x: str) -> dict[str, Any]:`
- 日志：`loguru`
- 配置：`pydantic-settings` 加载 `.env`，`pyyaml` 加载 YAML
- 数据模型：`pydantic.BaseModel`（API 层）/ `dataclass`（内部服务层）
- 依赖管理：`pyproject.toml`（Poetry 或 uv）
- Linting：`ruff`（替代 flake8 + black + isort）
- 类型检查：`mypy --strict`
- 每个模块有 `__init__.py` 导出公共接口
- 每个 `await` 必须有超时：`asyncio.wait_for(coro, timeout=N)`

## Vue3 前端

- Vue3 + Composition API + `<script setup>`
- TypeScript 严格模式
- PascalCase 组件命名
- API 请求封装在 `src/api/`
- 环境变量通过 `import.meta.env.VITE_XXX` 读取
- scoped CSS 或 UnoCSS

## Git 规范

- commit：`feat(adapters): 新增千牛适配器` / `fix(ai): LLM 超时重试`
- 分支：`main` 稳定 / `dev` 开发 / `feat/*` 功能
- PR 必须通过 `make lint` + `make test`
