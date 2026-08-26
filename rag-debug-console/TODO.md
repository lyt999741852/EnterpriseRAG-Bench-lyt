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
| M1 | RAG 调试 API 契约与版本模式 | DONE | question-only 契约、`pinned`/`live`、版本指纹、mock 服务 | `b7aa7f2` / 6 项 `backend/tests` 通过 |
| M2 | 500 题题库与单题联调 UI | DONE | 分类侧栏、快捷填入、对话、轨迹和异常状态 | `b7aa7f2` / 8 题样例 + 可验证的安全导入器 |
| M3 | 批量调度与运行历史 | DONE | daily-50/full-500、队列、资源锁、取消、独立产物目录 | `f347a32` / 8 项测试通过 |
| M4 | 指标与结果钻取 | DONE | 即时指标、官方 Judge 指标、分题型聚合与失败定位 | 待本次模块提交 / 9 项测试通过 |
| M5 | 隔离验收与发布 | IN PROGRESS | 不触碰现有 RAG 目录、端到端验证、文档与 PR | 发布预检已完成；等待独立服务 URL 与版本 |

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

```text
日期：2026-08-26
模块：M5
状态：IN PROGRESS
变更范围：独立发布服务预检脚本、部署隔离检查表与真实联调验收手册。
验证命令与结果：`python -m unittest discover -s backend/tests -v`（10 项通过）。
运行 ID（如适用）：无
提交 SHA：待创建
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：真实预检仍需要独立发布服务的 URL、已发布版本 ID 和无 gold 冒烟问题。
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
提交 SHA：b7aa7f2
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
提交 SHA：b7aa7f2
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：默认仍为 8 条安全样例；启动前用导入器生成 500 题副本即可自动切换。
```

```text
日期：2026-08-26
模块：M3
状态：DONE
变更范围：daily-50.v1 清单、独立 mock 队列、资源锁、取消、运行文件与批量前端页面。
验证命令与结果：`python -m unittest discover -s backend/tests -v`（8 项通过）。
运行 ID（如适用）：无
提交 SHA：待创建
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：daily-50 已确认采用多轮均衡题集；真实 RAG/评测调用仍属于 M4/M5。
```

```text
日期：2026-08-26
模块：M4
状态：DONE
变更范围：独立发布 RAG 服务 HTTP 适配器、版本契约校验、指标展示与服务模式提示。
验证命令与结果：`python -m unittest discover -s backend/tests -v`（9 项通过）；`node --check frontend/app.js`（通过）。
运行 ID（如适用）：无
提交 SHA：待创建
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：没有设置 `RAG_DEBUG_API_URL` 时使用 mock；真实 RAG 与 Judge 指标等待 M5 联调。
```

```text
日期：2026-08-26
模块：M5
状态：BLOCKED
变更范围：尚未进行真实 RAG 或 Judge 调用。
验证命令与结果：不适用。
运行 ID（如适用）：无
提交 SHA：待创建
远端分支 / PR：https://github.com/lyt999741852/EnterpriseRAG-Bench-lyt/pull/1
备注或阻塞原因：需要一个按 `/debug/versions`、`/debug/answer` 契约独立发布的 RAG 服务，以及与当前优化任务协调的资源锁。
```
