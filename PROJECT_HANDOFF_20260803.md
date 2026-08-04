# EnterpriseRAG-Bench 项目交接记录

更新时间：2026-08-03（Asia/Shanghai）

## 1. 项目背景与目标

本项目针对 EnterpriseRAG-Bench 企业级 RAG 评测，目标是在官方 500 道问题、约 51 万份 TXT 语料上，同时优化两项核心指标：

1. 答案正确性（出现实质性错误时，该题可能直接判错）。
2. 答案完整性（遗漏问题要求的任一关键事实会扣分）。

检索来源数量不是每题固定值。不同题型可能需要一个文档、多个文档或多个文档内的多个片段；但“多召回”不能以引入错误证据为代价。

## 2. 数据、服务器与模型

- 服务器：`10.72.100.29`，root。凭据不写入本文件，沿用会话中已提供的凭据。
- 应用目录：`/opt/enterprise-rag-bench/app`。
- 语料规模：约 511,957 个父文档，928,534 个文本 chunk。
- Elasticsearch 索引：`enterprise-rag-bge-small-v1`；当前索引完整，最近多次启动均为 `new=0`，只是扫描复用，没有重建向量。
- 向量模型：`BAAI/bge-small-en-v1.5`，384 维，运行环境 `/root/anaconda3/envs/yb_embedding/bin/python`。
- 大语言模型：Qwen 兼容 API，地址 `http://10.72.100.35:7777/v1`，模型名 `lark`，仅用于查询分解、PageIndex 选择、答案生成与核验；没有把 Qwen 当作嵌入模型。
- 官方评测环境：`/opt/enterprise-rag-bench/official_eval_venv/bin/python`，官方源码目录 `/opt/enterprise-rag-bench/app/EnterpriseRAG-Bench`。

## 3. 当前架构

处理链路如下：

1. 根据 `question_type` 路由问题：basic、semantic、constrained、conflicting_info、completeness、high_level、info_not_found 等。
2. Elasticsearch hybrid 检索负责全库高召回（BM25/向量融合），不负责最终证据裁决。
3. 对需要结构理解的题型，LLM 先拆分 facets、硬约束、风险维度和查询词。
4. PageIndex 使用官方 Markdown 树解析器，按文件和节点导航，并支持一到两跳检索。
5. 节点选择与节点审计：检查实体、时间、区域、版本、数量、终态/提案关系。
6. 对最终态问题做文件级 authority 过滤；对通过审计的文件可受控扩展全文，不能任意混回未审计 ES 文档。
7. `precision_v3` 证据选择器进行最终片段裁剪。
8. 生成答案后依次做事实核验、最终答案审计和来源 ID 裁剪。
9. 使用官方 `metrics_based_eval` 计算 correctness、completeness、recall、extra docs。

## 4. 已完成工作

### 4.1 数据与基础设施

- 已完成 51 万语料的全量切分、manifest 和 ES 向量库构建。
- 已确认次日继续工作不需要重新构建索引；只要不删除 ES 数据目录、索引或 manifest，流水线会复用现有索引。
- 已建立 PageIndex 树缓存，缓存按内容 fingerprint 保存，不依赖重新构建全库。

### 4.2 版本与实验

#### v3k precision-first（已验证）

- 原两道代表性题：correctness 100%、completeness 95%、combined 95、recall 100%、extra docs 0。
- 诊断 8 题：correctness 37.5%、completeness 46.73%、combined 37.5、recall 33.33%、extra docs 0。
- 主要问题：semantic、constrained、conflicting_info、completeness、high_level 过度拒答。

#### v4 balanced10（当前最重要的可比较基线）

配置：`configs/eval_pageindex_balanced10_v4.yaml`；服务器输出：`outputs/pageindex_balanced10_v4_20260731`。

官方 10 题结果：

| 指标 | v4 结果 |
|---|---:|
| correctness | 80.0% |
| completeness | 77.33% |
| combined | 77.33 |
| recall | 72.92% |
| average invalid extra docs | 0.12 |

已确认的改善：

- constrained：命中唯一正确的 SEV-2 postmortem，答案正确且来源正确。
- conflicting_info：能回答最新 60/140/260 QPS、150 并发，correctness 通过，但仍只保留了最新文档，旧版本来源召回不足。
- project_related 与原有基础题大体保持正确。

仍存在的问题：

- semantic：答案曾正确回答 2–4 周，但选中了同一主题的错误/后续合作伙伴文档，出现 extra doc。
- completeness：曾因“缺少精确短语”拒答；放宽后又可能把 outbound notice、follow-up 或背景文档当成新 intake。
- high_level：可能把支持职能、owner、子团队误列为一级部门，或过度保守拒答。

#### v4.1 / v4.2 / v4.3（实验分支，不作为最佳版本）

- v4.1 10 题官方结果：correctness 70.0%、completeness 86.33%、combined 70.0、recall 72.92%、extra docs 0.5。完整性提高，但错文档和基线回归，不接受为发布版本。
- v4.3 6 题定向回归：简单召回 40%、invalid docs 0.2，尚未进行官方 6 题评分。最终答案中 semantic、project_related 仍可能拒答，high_level 仍不稳定。
- v4.3 服务器输出：`outputs/pageindex_balanced6_v43_20260731`。
- 当前服务器代码是实验性 v4.3 代码；新会话应先运行测试和小样本确认，不要直接开展 500 题。

## 5. 当前代码与配置文件

- `src/pageindex_router.py`：EvidencePlanner、ES+PageIndex 路由、facets、节点审计、authority 过滤、题型专属策略。
- `src/generator.py`：precision_v3 证据选择、题型规则、事实核验、最终来源审计。
- `src/pipeline.py`：问题读取、检索、路由、生成、checkpoint 和评测。
- `tests/test_core.py`：当前本地/服务器均已通过 39 项测试。
- `configs/eval_pageindex_smoke_v3.yaml`：v3k 原两题基线。
- `configs/eval_pageindex_diagnostic8_v3k.yaml`：8 题诊断。
- `configs/eval_pageindex_balanced10_v4.yaml`：最佳可比较 10 题版本。
- `configs/eval_pageindex_balanced10_v41.yaml`：失败的 v4.1 实验版本。
- `configs/eval_pageindex_balanced6_v42.yaml`、`configs/eval_pageindex_balanced6_v43.yaml`：定向实验版本。

## 6. 已定位的关键问题

### 6.1 Semantic 题

同一实体可能有原始会议/通话记录和后续内部更新文档。问题若问“intro call 中被告知什么”，不能按最新文档优先，应按事件来源优先：

- call/meeting/transcript：优先 Fireflies 等直接转录。
- email：优先 Gmail 原始邮件。
- ticket/issue：优先 Jira/Linear 原始工单。

v4.3 已加入事件来源筛选，但 PageIndex 节点选择仍可能拒绝直接通话；下一步应在“直接事件来源已唯一收窄”后读取一个受控的完整事件文档，再经过生成器事实核验。

### 6.2 Project / 最终态题

Jira 最终票据、Gmail exception request、Confluence SLO 可能同时出现。节点审计只看局部节点时，容易把 Gmail proposal 当成 applied action。v4.3 已尝试先做文件级 authority 过滤，再做节点审计；需用 qst_0341 单题复测，确认 Jira 最终票据没有被拒绝。

### 6.3 Conflicting_info 题

“latest”不等于“正式批准”。应保留同一实体的最新 projection，并在有明确旧版本时保留旧版本作为对照；不能把 trial observation 当成旧 sizing assumption。当前 qst_0416 的最新值已正确，但旧文档召回仍不足。

### 6.4 Completeness 题

应统计独立 intake artifact，而不是所有提到主题的文档：

- 不计 outbound customer notice。
- 不把 follow-up 当作新的报告。
- 语义等价的 issue 可以计入，即使标题没有完整复述短语。
- Confluence intake/process 文档可能是聚合证据，不能因为不是工单就直接排除。

最终回答若只问“哪个渠道最多”，应只输出获胜渠道；不要把不必要的每文档编号、近似短语和背景计数写进答案。

### 6.5 High-level 题

应综合多个文件，但只保留一级部门：不能把 owner、子团队、通用 core function、Finance/Legal/IT/Procurement 等普通支持职能自动提升为一级部门。不能回退到裸 ES 前几条；只能使用 PageIndex 预选的有界文件集，再交给最终事实审计。

### 6.6 输出字符规范化

Qwen 输出中出现过 `2每4`、`3每5`、`≧` 等字符异常。下一步应在答案最终审计前增加安全的确定性归一化（例如 `每` 在数字区间中转为 `–`，不改变正文语义），并保留原始答案用于审计。

## 7. 新会话建议的任务顺序

### P0：先恢复可比较基线

1. 不删除任何 ES 索引、manifest 或 PageIndex cache。
2. 运行 `python -m unittest tests.test_core`，确认 39 项通过。
3. 保留 v4 结果作为主要对照；不要把 v4.1/v4.3 的简单指标当作官方结论。
4. 对当前 v4.3 代码只做单题实验，避免再次消耗 500 题预算。

### P1：完成三条高收益修复

1. qst_0298：直接事件来源 full-document fallback，验证命中 Fireflies 原始通话和 2–4 周；不得回退到裸 ES。
2. qst_0341：复测 authority-before-node-audit，确保 Jira applied record + Confluence SLO 进入最终上下文，拒绝 Gmail proposal。
3. qst_0432：完善 intake artifact 去重与 source-path 过滤；答案只输出 `Jira`，来源由最终审计裁剪。

### P2：解决 high_level 与 conflict

1. qst_0480 使用 PageIndex 预选文件的 scoped synthesis，要求输出一级部门短名单，不允许无依据拒答或扩展支持职能。
2. qst_0416 增加同实体前一版本文档配对，检查 recall 是否从 50% 提升，同时不引入第三个错误版本。

### P3：回归与放大

1. 先对 qst_0298、qst_0341、qst_0416、qst_0432、qst_0480 做 5 题定向实验。
2. 再合并原两题，做 10 题官方评分，与 v4 的 80%/77.33/72.92/0.12 对比。
3. 只有 10 题 correctness 不下降且 extra docs 不明显上升，才做 50 题。
4. 50 题稳定后，再按 9 类题型分层抽样做 500 题；不要直接覆盖历史结果。

## 8. 常用命令

本地测试：

```powershell
python -m unittest tests.test_core
```

服务器运行环境需要组合 `PYTHONPATH`：

```bash
export PYTHONPATH=/opt/enterprise-rag-bench/app:/opt/enterprise-rag-bench/venv/lib/python3.10/site-packages
export HF_HOME=/opt/enterprise-rag-bench/model_cache
export CUDA_VISIBLE_DEVICES=2
export LARK_API_KEY=internal-placeholder
cd /opt/enterprise-rag-bench/app
/root/anaconda3/envs/yb_embedding/bin/python -m unittest tests.test_core
```

官方评测入口：

```bash
cd /opt/enterprise-rag-bench/app/EnterpriseRAG-Bench
/opt/enterprise-rag-bench/official_eval_venv/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file /opt/enterprise-rag-bench/app/questions.jsonl \
  --answers-file <output-dir>/answers.jsonl \
  --results-file <output-dir>/results.json \
  --parallelism 2 --no-correction --resume
```

## 9. 交接结论

项目的全量语料和 ES 向量库已经完成并可复用；PageIndex+ES 双路架构已经运行起来。当前最可信的量化成果是 v4 的 10 题官方结果，而不是最新仍在调整的 v4.3。后续工作的核心原则是：对 semantic、project、conflict、completeness、high_level 分别建立“事件来源、文件终态、独立 artifact、一级部门、版本配对”的约束；每次只放宽一个环节，并用官方 correctness、completeness、recall、extra docs 四项一起验收。
