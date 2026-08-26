# RAG 联调控制台：开发追踪

**分支：** `codex/rag-debug-console`  
**隔离规则：** 仅提交 `rag-debug-console/` 下的文件；禁止把当前 RAG 的任何未提交变更带入本分支的提交。

## 状态定义

- `TODO`：尚未开始；设计或依赖未满足。
- `IN PROGRESS`：正在修改；不得合并或推送为完成状态。
- `DONE`：实现、测试、验收完成，且已记录提交 SHA。
- `BLOCKED`：依赖外部决策、RAG 已发布 API 或资源锁。

## 模块清单

| ID | 模块 | 状态 | 完成条件 | 提交 / 验证 |
|---|---|---|---|---|
| M0 | 独立基座与追溯 | DONE | 独立根目录、忽略规则、README、任务追踪和边界检查 | `52f29a7` / `git diff --check -- rag-debug-console` |
| M1 | RAG 调试 API 契约与版本模式 | DONE | question-only 契约、`pinned`/`live`、版本指纹、mock 服务 | 待本次模块提交 / `backend/tests` |
| M2 | 500 题题库与单题联调 UI | DONE | 分类侧栏、快捷填入、对话、轨迹和异常状态 | 待本次模块提交 / 8 题样例 + 可验证的安全导入器 |
| M3 | 批量调度与运行历史 | TODO | daily-50/full-500、队列、资源锁、取消、独立产物目录 | — |
| M4 | 指标与结果钻取 | TODO | 即时指标、官方 Judge 指标、分题型聚合与失败定位 | — |
| M5 | 隔离验收与发布 | TODO | 不触碰现有 RAG 目录、端到端验证、文档与 PR | — |

## 每模块记录模板

```text
日期：
模块：M?
状态：TODO / IN PROGRESS / DONE / BLOCKED
变更范围：
验证命令与结果：
运行 ID（如适用）：
提交 SHA：
远端分支 / PR：
备注或阻塞原因：
```

## 当前记录

```text
日期：2026-08-26
模块：M0
状态：DONE
变更范围：创建开发设计与追溯文档；创建隔离开发分支。
验证命令与结果：`git diff --check -- rag-debug-console`（通过）。
运行 ID（如适用）：无
提交 SHA：52f29a7（设计与隔离基座）；下一提交回填 DONE 记录。
远端分支 / PR：待推送
备注或阻塞原因：不实施 RAG 调用；M1 等待已发布调试 API 契约。
```

```text
日期：2026-08-26
模块：M1
状态：DONE
变更范围：独立 Python HTTP API、版本化 mock RAG gateway、SQLite 运行记录、question-only 契约测试。
验证命令与结果：`python -m unittest discover -s backend/tests -v`（5 项通过）；`POST /api/chat-runs`（pinned 模式通过）。
运行 ID（如适用）：chat_9bd9386fdc11（本地 mock 验证）
提交 SHA：待创建
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：真实 gateway 等待 RAG 侧发布只读 API；本模块不导入现有 src/。
```

```text
日期：2026-08-26
模块：M2
状态：DONE
变更范围：静态前端（聊天、模式选择、题库浏览、轨迹和历史）与 gold-free 题库导入器。
验证命令与结果：后端契约与导入器测试通过；需由用户以显式路径导入本地 500 题副本。
运行 ID（如适用）：无
提交 SHA：待创建
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：默认仍为 8 条安全样例；启动前用导入器生成 500 题副本即可自动切换。
```
