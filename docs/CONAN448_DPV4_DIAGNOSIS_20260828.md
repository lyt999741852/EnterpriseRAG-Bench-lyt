# Conan 与 BGE 结果差异诊断

## 先给结论

本轮 Conan 与 BGE 的 `correctness` 持平，不等于 Conan 检索已经追平 BGE。更合理的解释是：DPV4 同时改善了查询改写、answer-intent、路由和答案生成，PageIndex 又能对部分候选做文档级补偿，因此把 Conan 的检索劣势部分掩盖了；真正的证据召回仍然偏弱。

## 本轮到底用了哪些模型

| 环节 | 模型/服务 |
|---|---|
| 查询改写、answer-intent、question router | `deepseek-v4-flash`（10.72.100.29:18380/v1） |
| 最终答案生成 | `deepseek-v4-flash` |
| no-correction 评分 judge | `deepseek-v4-flash` |
| 查询/索引 embedding | Conan `embedding`（10.72.55.209:7993/v1，1792 维） |
| reranker | 10.72.55.209:7992/v1 的 `bge-reranker-v2-m3` |

因此本轮不是“只替换向量库”：embedding、索引切块/分区契约发生了变化，但 DPV4 也参与了检索前的改写和路由。BGE 对照和 Conan 本轮使用同一 DPV4 生成器、同一 DPV4 judge、同一 50 题和 no-correction，适合做当前端到端对照。

## 当前 BGE 对照与 Conan 对照

| 指标 | BGE+DPV4 | Conan448+DPV4 | 变化 |
|---|---:|---:|---:|
| correctness | 68.00% | 68.00% | 0 |
| completeness | 71.37% | 68.06% | -3.31 pp |
| combined | 62.13 | 62.89 | +0.76 |
| document recall | 70.39% | 64.78% | -5.61 pp |
| invalid extra docs | 0.17 | 0.13 | -0.04 |

离线 trace 进一步显示：两套系统 rerank 后 top-30 文档平均只重叠约 7.72 个，最终生成上下文平均只重叠约 0.82 个文档；也就是说，向量模型确实改变了候选集合，而不是“实际上用了同一批证据”。Conan 的 PageIndex 最终 chunk 平均数为 4.80，BGE 为 4.64；Conan 的 coverage-false 题为 17/50，BGE 为 16/50，missing facets 总数 29 对 23，均未显示 Conan 的证据覆盖更好。

分题型上，Conan semantic correctness/recall 为 50/50%，BGE 为 58.33/66.67%；project-related recall 为 23.61%，BGE 为 39.58%。Conan 只在 intra-document reasoning（100% 对 75%）等小分桶上出现局部收益。

## 为什么旧 Conan 明显更差

历史记录中的 Conan/Qwen V3 P0（分层 100）为 correctness 53%、combined 48.42、recall 53.11；关闭递归分区归并为 52/47.42/50.98，扩大候选池为 55/50.72/54.31。早期 50 题 Q3-A/Q3-B 甚至只有 combined 37.41/36.41。

旧结果不能直接与本轮 68/62.89 横向归因，至少有三项变化：

1. 旧结果使用 Qwen/Lark 参与改写、路由、PageIndex 和生成；本轮全链路改为 DPV4。BGE 的单独 LLM 交换实验显示，BGE 在同样 50 题上由 Qwen 生成基线的 correctness 64% 提升到 DPV4 的 68%，recall 由 60.87% 提升到 70.39%。
2. 旧记录中的评分 judge 主要是 Qwen/Lark，而本轮使用 DPV4 judge。交叉评分已显示 judge 本身可造成约 6–9 个百分点的尺度差异，因此旧 Conan 的 53% 不能直接当作“纯 embedding 损失”。
3. 旧 Q3-A/B 与 V3 P0 的题集、索引版本和参数批次不同；本轮固定使用当前 BGE 对照的同一 50 题，并启用现行 multi-view、rewrite/intent、rerank、PageIndex 和分区折叠。

所以“旧 Conan 更差、当前 Conan 持平”的主要原因不是 Conan 突然变成了更好的 embedding，而是更强/不同的 DPV4 全链路把输出端的损失补回了一部分，且评测尺度也改变了。

## 逐题证据

当前两套 DPV4 运行共有 12 题 correctness 翻转：6 题由错变对、6 题由对变错，净变化为零。Conan 改善了 qst_0022、qst_0116、qst_0241、qst_0322、qst_0362、qst_0480；回退了 qst_0082、qst_0112、qst_0272、qst_0291、qst_0341、qst_0413。semantic 题的回退多表现为“无证据而拒答”，与 recall 下降一致；这不是提示词风格的小差异，而是候选/最终证据链问题。

## 诊断判断

- **已改善的部分**：DPV4 的改写/意图查询、PageIndex 文档级补偿、当前分区折叠和 reranker 共同避免了旧 Conan 的大幅端到端崩溃。
- **未改善的核心**：Conan semantic/project-related 的目标文档进入候选和最终上下文的稳定性仍低于 BGE；低 invalid extra 不能抵消 recall 损失。
- **不能下的结论**：不能据此说 Conan embedding 优于 BGE，也不能把 68% 外推到 500 题；本轮只证明 Conan 在 DPV4 全链路下可以达到与 BGE 相同的 50 题 correctness。

## 后续实验优先级

1. 用两套 route trace 做 raw-miss 对齐：同题比较 BM25、dense、RRF、rerank、PageIndex admission、selector 和 generation 前的目标文档是否存在。
2. 对 semantic 失败题优先做“目标文档未进原始候选”与“已进候选但被 rerank/selector 丢弃”的二分统计。
3. 若只想评估 embedding 本身，冻结一套已有的改写/路由/最终证据轨迹，只替换 query embedding 与索引；否则继续把结果称为端到端 Conan 对照，不把收益归因到 embedding 单一因素。
