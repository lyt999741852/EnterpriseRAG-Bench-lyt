# Conan448 vs BGE：同一 DPV4 50 题证据漏斗诊断

本次是已完成 50 题运行的离线诊断，不修改 pipeline、不使用结果回流检索。仅在运行结束后用题目的 `expected_doc_ids` 和 `answer_facts` 统计各阶段命中，用于判断 Conan 是否有必要替换 BGE。

## 文档级漏斗

| 首个损失层 | BGE+DPV4 | Conan448+DPV4 |
|---|---:|---:|
| raw miss（所有原始 view 均未命中） | 8 | 11 |
| rerank drop | 1 | 3 |
| PageIndex/selector drop | 4 | 4 |
| citation/selector drop | 3 | 1 |
| fully successful | 22 | 19 |

其中 semantic 题的 raw miss：BGE 4 题，Conan 5 题；Conan 另有 1 个 semantic rerank drop 和 1 个 semantic PageIndex/selector drop。Conan 的典型 raw miss 是 qst_0184、qst_0231、qst_0251、qst_0291、qst_0298；这些题正是当前语义检索短板。

## 事实级漏斗

| 阶段 | BGE 支持事实数 | Conan 支持事实数 |
|---|---:|---:|
| raw views | 169 | 167 |
| pre-rerank | 164 | 159 |
| post-rerank | 150 | 152 |
| final_before_generation | 142 | 130 |
| submitted | 122 | 125 |

Conan 在 post-rerank 的事实数略高 2 个，但在最终生成上下文前少 12 个。这说明 Conan 不是完全没有补召回能力，而是其分区/候选进入 PageIndex 或 selector 后的稳定保留较差；最终答案的 correctness 持平，不能反推证据漏斗更优。

## 对“高维 + 更好切块应当更好”的判断

高维和 overlap 只增加表示容量与边界连续性，不保证问题与企业文本在该向量空间中的相似度排序更好。当前证据表明：

1. Conan 与 BGE 的 rerank 后 top-30 文档平均只重叠 7.72 个，确实形成了不同候选集合。
2. Conan 的 document recall 64.78% 低于 BGE 的 70.39%，semantic recall 50% 低于 BGE 的 66.67%。
3. Conan 448/32 的 overlap 带来更多相邻/分区候选，但不一定带来目标事实；`collapse_recursive_partitions=true` 只能减少分区稀释，不能修复 embedding 排序不足。
4. 当前端到端 correctness 都是 68%，主要因为 DPV4 改写、PageIndex 文档级扩展和生成器能够补偿部分检索损失，而不是 Conan 检索本身已优于 BGE。

## 与历史 Conan 低分的关系

历史 Conan/Qwen V3 P0 的 correctness/combined/recall 为 53%/48.42/53.11，早期 Q3-A/Q3-B 50 题 combined 为 37.41/36.41。本轮使用 DPV4 做改写、路由、生成和 judge，且题集、现行 PageIndex/multi-view/rerank 配置不同；BGE 的独立 LLM 交换也显示 DPV4 会显著提升 recall。因此旧低分中同时包含 LLM/路由/评分尺度影响，不能全部归因于 Conan embedding。

## 决策

- 若目标是当前端到端 50 题 correctness，Conan 可以达到 BGE+DPV4 的持平水平，但没有形成净收益。
- 若目标是提升核心 semantic 检索，当前数据不支持切换 Conan；它的 raw miss、最终上下文事实覆盖和 recall 仍较差。
- Conan 的必要性只值得在“受控 query embedding + ES 候选召回”实验中继续验证：冻结改写、路由、PageIndex 和生成上下文，单独比较 BGE/Conan 的 target rank/Recall@K。只有 Conan 在该隔离实验中稳定提高 raw/pre-rerank 命中，才有理由投入切块或全量主线迁移。
