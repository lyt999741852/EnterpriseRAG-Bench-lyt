# RAG 联调控制台使用说明

## 启动

```powershell
cd D:\EnterpriseRAG-Bench\rag-debug-console
python -m backend.app.server --host 127.0.0.1 --port 8090
```

浏览器打开 `http://127.0.0.1:8090`。控制台自身的运行记录写入 `rag-debug-console/runtime/`，不会写入现有 RAG 的 `outputs/` 或缓存目录。

## 首次导入 500 题

控制台默认只有 8 条无敏感字段的演示题。使用下列命令生成自己的题库副本：

```powershell
python scripts/import_public_questions.py --source D:\EnterpriseRAG-Bench\questions.jsonl
```

该脚本只保留 `question_id`、`question` 和分类；gold answer、expected document IDs、answer facts 等字段不会写入控制台。导入后重启控制台，题库侧栏会自动使用 `data/questions.public.json`。

## 单题联调

1. 在左侧搜索或展开分类，点击题号会将题目填入输入框；也可直接手动输入。
2. 选择模式：
   - **当前联调版本（live）**：调用最新已发布的 RAG 调试服务版本，用于检查最新优化。
   - **固定版本（pinned）**：明确选择一个已发布版本，用于可复现比较。
3. 点击“发送并运行”。回答区显示回答、文档 ID、耗时和可展开的路由/检索/重排/PageIndex/证据轨迹。
4. 在“运行历史”中点击条目可重新查看其轨迹。每条记录都带 RAG 版本指纹。

当前提交中的 gateway 是 mock，以验证前后端契约和交互；接入真实 RAG 前，必须部署一个稳定的只读调试 API。控制台不会加载当前仓库中正在修改的 RAG 代码。

## 批量测试

- **日常 50 题**：固定使用 `daily-50.v1`，即长期参与多轮测试的均衡题集，来源为 `eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml`。
- **全量 500 题**：仅在成功导入恰好 500 条的公开题库副本后可启动。

批量任务默认使用 `pinned` 模式。启动后，控制台会锁定 `rag-evaluation`，同一时刻拒绝第二个批量任务；可在“批量测试”页刷新进度或取消任务。每个批量任务独立保存至 `runtime/batches/<run_id>/run.json`。

在 mock 阶段，进度仅验证队列、锁和取消逻辑，指标保持空值。真实 RAG 调试服务与评测 worker 发布后，才填充 Recall、Overall、Correctness、Completeness 和无效文档数。

## 安全与追溯

- 不要将 `runtime/`、`data/questions.public.json` 或任何 API 密钥提交到 Git。
- 每次正式对比优先使用 `pinned`，并记录运行 ID、RAG 版本、索引/配置指纹。
- 当前开发状态、测试结果和提交 SHA 维护在 [TODO](../TODO.md)。
