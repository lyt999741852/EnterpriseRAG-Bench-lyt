# R12：BGE/Conan 原题 dense 检索隔离对照

## 目的

验证“Conan 448/32 + 1792 维 embedding 因为切块更好、维度更高，应当普遍优于 BGE”的假设。该实验固定当前 50 题，只使用原始问题文本生成 query vector，绕过 query rewrite、answer-intent、router、PageIndex、reranker、selector 和 LLM 生成；gold 文档 ID 仅在检索后用于离线 Recall@K。

## 配置

- BGE：`BAAI/bge-small-en-v1.5`，384 维，索引 `enterprise-rag-bge-small-v1`。
- Conan：服务 `embedding`，1792 维，索引 `enterprise-rag-qwen3-emb-v3-conan448`，448/32 chunk。
- 两套索引均只读；未重建、未写入 ES。
- 每题分别查询 dense top-1000，再统计 Recall@30/120/240/1000。

## 结果

| K | BGE 命中 | BGE Recall | Conan 命中 | Conan Recall |
|---:|---:|---:|---:|---:|
| 30 | 25/50 | 50% | 13/50 | 26% |
| 120 | 29/50 | 58% | 17/50 | 34% |
| 240 | 32/50 | 64% | 19/50 | 38% |
| 1000 | 37/50 | 74% | 26/50 | 52% |

直接原题召回下，Conan 在所有 K 都明显低于 BGE。BGE 命中而 Conan 未命中的题远多于反向情况：Recall@30 时 BGE-only 16 题、Conan-only 4 题；Recall@1000 时 BGE-only 14 题、Conan-only 3 题。逐题 rank 比较中，Conan 优于 BGE 仅 9 题，BGE 优于 Conan 27 题，14 题相同（主要是两者都未命中）。

## 与上一轮端到端结果的关系

上一轮 Conan+DPV4 与 BGE+DPV4 的 correctness 都为 68%，但 Conan document recall 为 64.78%，低于 BGE 的 70.39%。R12 进一步说明：在移除 DPV4 改写、PageIndex 和 rerank 补偿后，Conan 的原题 dense Recall@30 只有 26%，BGE 为 50%。因此端到端持平来自后处理/生成补偿和候选互补，不是 Conan dense 检索更强。

Conan 仍提供少量互补命中（Recall@30 约 4 个 BGE 未命中的题），所以若继续使用，应作为条件触发的低权重 shadow/union 召回源，而不应整体替代 BGE。

## 按题型的贴合度

原题 Recall@1000 的差异并非均匀：

| 题型 | BGE | Conan |
|---|---:|---:|
| basic (18) | 17/18 | 11/18 |
| semantic (12) | 5/12 | 1/12 |
| intra-document reasoning (4) | 4/4 | 3/4 |
| project-related (4) | 4/4 | 4/4 |
| constrained (3) | 2/3 | 3/3 |
| conflicting_info (2) | 2/2 | 1/2 |

Conan 的优势集中在 constrained 的少数题，project-related 在较大 K 下与 BGE 持平；对 semantic 和 basic 则明显不贴合。这说明 embedding 选择必须按当前语料与问题分布验证，不能依据维度或模型名称推断。

## 对高维和切块假设的结论

更高维度代表更大的表示空间，overlap 代表更连续的边界；二者都不保证问题—文档相似度排序更好。当前结果更可能受以下因素影响：

1. Conan embedding 与该企业语料/问题表达的对齐不足；
2. 448/32 递归分区产生相邻局部片段，目标事实被分散，单个 chunk 的 query 相似度下降；
3. 现有 rerank/PageIndex 对 Conan 分区的补偿只在部分题目有效，不能修复原始候选未进入 top-K 的情况。

## 决策

R12 不支持把 Conan 作为 BGE 的整体替代。若目标是提高当前榜单分数，优先保留 BGE 主线；若要利用 Conan，应只做受控 shadow union，并以增加 raw/pre-rerank 目标命中且控制题不回退为门槛。后续若要证明 Conan 的切块价值，应建立同一 embedding 下不同 chunk 方案的独立小索引，否则无法把“embedding 效果”和“切块效果”分开。

结果文件：[r12_direct_bge_conan_retrieval_50_20260828.json](../outputs/r12_direct_bge_conan_retrieval_50_20260828/r12_direct_bge_conan_retrieval_50_20260828.json)
