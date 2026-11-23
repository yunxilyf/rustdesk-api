## 变更说明

<!-- 这个 PR 做了什么、为什么；关联 issue 用 "Closes #123" -->

## 类型

- [ ] 修复（fix）
- [ ] 新功能（feat）
- [ ] 重构（refactor）
- [ ] 文档 / 构建 / 其他（docs/chore）

## 影响范围

- [ ] RustDesk 客户端 API（`/api/*`，必须保持契约兼容）
- [ ] 管理控制台（`/api/console/*`、`frontend/`）
- [ ] 数据库模型 / 迁移
- [ ] 部署 / 配置 / CI
- [ ] 仅文档

## 自检（详见 AGENTS.md）

- [ ] `ruff check` 通过
- [ ] `python manage.py check` 通过
- [ ] `api.tests` 全绿（仅维护者本地保留，不随仓库提交；外部 PR 以 ruff + check 为准）
- [ ] 客户端契约未破坏；如变更已同步 `docs/client_api_contract.md`
- [ ] 数据库改动包含新迁移文件，未修改历史迁移
- [ ] 配置改动同步 `.env.example` / `README` / `docs/deployment.md`
- [ ] 未提交密钥、数据库、日志、构建产物、测试文件
- [ ] 前端改动已 `npm --prefix frontend run build` 并人工确认

## 验证方式

<!-- 复现步骤、截图、请求示例；生产验证请注明环境 -->
