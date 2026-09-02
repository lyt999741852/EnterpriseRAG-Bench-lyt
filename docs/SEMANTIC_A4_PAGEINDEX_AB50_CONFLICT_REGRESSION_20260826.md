# A4 PageIndex ON AB50 conflict-contract 回归（2026-08-26）

## 目的与配置

- 在已通过的 A3.4 conflict contract 上接回冻结 PageIndex ON AB50 主链。
- 配置：`configs/eval_pageindex_ab50_semantic_conflict_contract_r2_20260826.yaml`。
- 运行名：`pageindex_ab50_semantic_conflict_contract_r2_20260826`。
- PageIndex 使用既有 warm cache；BGE ES、reranker、LLM 均为只读/环境变量认证。
- `question_parallelism=2`。并发 4 曾出现 reranker 连接阻塞，因此未采用更高并发。
- 运行期补丁在评分前已回滚，并通过 `python -m py_compile src/generator.py` 验证。

## 完整性与评分

AB50 pipeline 完成 50/50，未跳题；simple metrics 为 recall 63.9、平均额外文档 0.2。官方 no-correction 评分如下：

| 指标 | PageIndex ON 基线 `r3_on` | conflict contract `r2` | 变化 |
|---|---:|---:|---:|
| correctness | 64.00% | 64.00% | 0.00 pp |
| completeness | 65.15% | 65.81% | +0.66 pp |
| combined | **59.34** | **59.01** | **-0.33** |
| document recall | 61.76% | 63.89% | +2.13 pp |
| invalid extra docs | 0.17 | 0.19 | +0.02 |

运行产物（远端，未纳入 Git）：

- `outputs/pageindex_ab50_semantic_conflict_contract_r2_20260826/answers.jsonl`
- `outputs/pageindex_ab50_semantic_conflict_contract_r2_20260826/route_trace.jsonl`
- `outputs/pageindex_ab50_semantic_conflict_contract_r2_20260826/results.json`
- `outputs/pageindex_ab50_semantic_conflict_contract_r2_20260826/simple_metrics.json`

## 逐题差异审计

- `qst_0272`：`False/0%/0%` → `True/100%/100%`，确认 conflict contract 恢复了 selector drop。
- `qst_0236`：正确性保持，完整性 `100%` → `83.33%`。
- `qst_0298`：`True/100%` → `False/50%`；新答案加入“证据只说明 HSM 组件、不说明总工期”的限定语，官方判为不正确。该项是实际答案回归，不是额外文档指标问题。
- `qst_0432`：正确性/完整性/召回保持，仅 invalid extra docs `0` → `1`。按打榜口径，额外文档只作诊断，不单独阻断。

## 结论与门禁

A4/B4 本轮 **未通过**：虽然 recall 与平均 completeness 上升，combined 低于冻结基线且出现 qst_0298 正确性回归。故不启动 `pageindex_full500_conflict_contract_20260826`（F500），避免把未通过变量扩散到 500 题。

## 后续计划（三项测试结果）

1. **已完成**：PageIndex ON AB50 conflict-contract 回归与官方 no-correction 评分。
2. **门禁停止**：500 题全量候选未运行；待修复 qst_0298 类“冲突证据导致过度限定”后再申请。
3. **下一轮优化**：保留 A3.4 诊断结论，但在生成层增加冲突证据的答案约束/裁剪（不锁定额外文档），先用 qst_0298、qst_0236 及 qst_0272 做小型回归，再重复 AB50；只有 correctness 不下降且 combined ≥59.34 才进入 F500。
