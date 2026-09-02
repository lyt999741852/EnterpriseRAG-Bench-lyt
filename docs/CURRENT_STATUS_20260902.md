# EnterpriseRAG-Bench 当前状态

更新时间：2026-09-02（Asia/Shanghai）  
证据口径：除明确说明外，使用官方 `metrics_based_eval --no-correction`。该口径
用于可重复的内部对照，不能与不同题集、生成模型或 judge 的结果直接排序。

## 当前候选主线

**BGE-small 384d + BM25/dense hybrid RRF + remote reranker (120 → 30) +
PageIndex + bounded fail-open evidence admission（O4.P3）**。

当前最完整的候选结果为 2026-09-02 的 F500：correctness **64.00%**、
completeness **67.63%**、combined **58.88**、document recall **64.49%**。
它相对上一轮 DPV4 F500 参考线（62.80 / 64.25 / 57.01 / 60.29）均有提升，
但无效额外文档从 0.23 升至 0.34，仍需独立复核后再冻结为正式主线。
详见 [F500 O4.P3 记录](F500_BGE_DPV4_O4P3_20260902.md)。

## 冻结边界

- 保持原始语料、BGE-small 索引、`fixed-v2` 切块、BM25/dense 基线候选、rerank 输入上限和 `--no-correction` 口径不变。
- 每个实验只改变一个机制；使用独立 YAML、`pipeline.name`、输出目录和 PageIndex cache。
- 在线链路只使用题目文本；真实题型、gold 文档、参考答案和评分结果仅用于离线诊断。
- Conan/Qwen 索引保留为研究资产，不替代 BGE 主线，除非在同题、同 judge、同成本约束下证明稳定净收益。

## 已确认的设计决策

| 决策 | 证据 | 当前处理 |
|---|---|---|
| 保留 remote reranker | 分层 50 题 combined 54.66 → 58.74，recall 58.39% → 66.19% | 保留 |
| 保留 PageIndex | 选择性跳过出现明显整体回退 | 保留 |
| 不全量启用多视图 | 同题对照回退 | 只作为受控、追加式候选试验 |
| 不替换为 Conan | 同题 DPV4 对照 recall 低 5.61pp，索引成本更高 | 不合流 |
| O4.P3 evidence admission | F500 combined 57.01 → 58.88，recall +4.20pp | 候选主线，待独立复核 |

完整对照与适用限制见 [有效实验测试汇总](VALID_EXPERIMENT_TEST_SUMMARY_20260901.md)。

## 下一步

1. 固定 O4.P3 配置、题集与输出，完成独立 judge 或重复 F500 复核，并审计额外引用文档。
2. 按 raw-miss → pre-rerank → admission → generation 的顺序处理 Semantic、Project-related、Completeness；不要用 prompt 掩盖召回问题。
3. 对通过小样本门禁的候选，先跑 AB50/AB150 回归，再决定是否运行 F500。

详细任务顺序与放行门槛见 [优化路线](OPTIMIZATION_ROADMAP_20260902.md)。
