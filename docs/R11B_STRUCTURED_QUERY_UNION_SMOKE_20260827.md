# R11.B：结构化 Semantic 表示 + 原题候选 union Smoke

日期：2026-08-27
性质：隔离检索实验；未修改主分支源码，远端临时 patch 已 apply/rollback，并通过 `py_compile`。

## 目的

验证一个通用候选覆盖变量：由题干生成一条不含答案的结构化表示，分别做 BM25 与 dense 检索，以低权重与原题候选 union；显式保留原题候选作为托底。该实验不预设答案、不读取 `expected_doc_ids`，也不锁定额外文档。

## 实验分两轮

首轮 `pageindex_r11b_structured_query_smoke_20260827` 只对 `semantic/unknown` 类型启用 structured view，结果发现 5 个核心 raw-miss 中只有 1 个被路由为 semantic，无法回答通用召回问题；首轮同时出现控制题 `qst_0272` 的生成回退，因此不作为主结论。

复测 `pageindex_r11b_structured_query_smoke_r2_20260827` 对 `semantic/basic/constrained/unknown` 全部启用同一变量，覆盖 5 个核心 raw-miss 与 4 个控制题：

`qst_0116`、`qst_0184`、`qst_0231`、`qst_0251`、`qst_0298`、`qst_0093`、`qst_0211`、`qst_0272`、`qst_0356`。

## 官方 no-correction 结果

| 指标 | R11.B r2 | 同题 AB50 基线 | 变化 |
|---|---:|---:|---:|
| correctness | 22.22%（2/9） | 22.22%（2/9） | 0 |
| completeness | 33.33% | 38.89% | -5.56 pp |
| combined | 22.22 | 22.22 | 0 |
| document recall | 13.89% | 25.00% | -11.11 pp |
| invalid extra docs | 0.67 | 0.67 | 0 |

逐题上，`qst_0211` 保持正确，`qst_0298` 由 50% completeness 变为 100%，但 `qst_0272` 由基线正确回退为拒答；总体 correctness 未净增，且完整性/召回下降。

## raw candidate 证据

| 核心 raw-miss | structured/raw views | pre-rerank | 结论 |
|---|---:|---:|---|
| `qst_0116` | 目标文档进入（structured dense 文档序位约 29） | 丢失 | 表示有局部信号，但低权重 RRF 未保留 |
| `qst_0184` | 未进入 | 未进入 | 表示未解决 |
| `qst_0231` | 未进入 | 未进入 | 表示未解决 |
| `qst_0251` | 未进入 | 未进入 | 表示未解决 |
| `qst_0298` | 未进入 | 未进入 | 表示未解决 |

因此，route-independent structured 表示仅恢复 1/5 raw views、0/5 pre-rerank，不能证明该表示能普遍修复 raw-miss。它还增加了每题一次 LLM 表示调用和两次检索，运行约 14 分钟完成 9 题，成本/收益不匹配。

## 失败归因

1. 首轮说明：把 structured view 绑定单一 LLM 题型会漏掉 basic/constrained/unknown 的语义 raw-miss；路由正确性不能作为候选覆盖前提。
2. r2 说明：即使 route-independent，结构化表示的 BM25/dense 命中仍很弱；唯一命中的 `qst_0116` 在 RRF 前被丢掉，说明当前低权重 fusion 是第二个阻断点。
3. r2 的最终文档集合与 AB50 基线大部分相同，故本变量没有形成稳定的检索增益；控制题的答案差异还受生成模型方差影响，不能据此宣称提升。

## 结论与后续

R11.B **未通过，不合流，不运行 AB50/F500**。保留首轮作为“路由门控不足”的诊断，r2 作为 route-independent 主结果。

下一步 R11.C 只做一个更窄的变量：当原题 keyword/dense 两路低置信或低一致时，才启用一条 structured query，并从其 top-N 中保留极少量候选进入 reranker；原题候选始终保留，且每文档/总 chunk 有硬上限。先对同一 5+4 题 smoke，门槛是至少恢复 raw/pre-rerank 目标且控制题无回退；不再无条件给所有题增加 structured LLM 调用。

机器产物：

- `outputs/pageindex_r11b_structured_query_smoke_20260827/`
- `outputs/pageindex_r11b_structured_query_smoke_r2_20260827/`
