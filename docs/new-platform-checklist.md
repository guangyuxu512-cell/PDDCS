> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由

# 新增平台检查清单

- [ ]  `config/platforms.yaml` 添加平台配置
- [ ]  `adapters/` 新建适配器，实现 `CustomerServiceAdapter` Protocol
- [ ]  `factory.py` 注册
- [ ]  `auth/` 新建登录流程
- [ ]  `config/user_agents.yaml` 添加该平台 UA（如适用）
- [ ]  `tests/unit/` 适配器单元测试
- [ ]  `tests/sandbox/` 模拟页面（如 Web 平台）

**禁止**：修改 `services/`、`ai/`、`backend/api/` 中的业务代码。
