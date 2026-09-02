# 索引质量验证：BGE-small / Conan

日期：2026-08-31

## 范围与方法

针对 O0 的 46 道有效 raw-miss（涉及 61 个 gold 文档），只读检查 BGE-small 与 Conan 的 ES mapping、索引健康、目标文档/ chunk 覆盖、文本字段、chunk 元数据和抽样向量。没有重建索引、写入 ES 或调用生成模型。

机器可读结果：`/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/index_quality_validation_20260831.json`

## 结果

| 指标 | BGE-small | Conan |
|---|---:|---:|
| ES health | green，1 primary | green，16 primary |
| 全库文档数 | 928,534 | 3,030,317 |
| 目标 gold 文档存在 | 61/61 | 61/61 |
| 目标 chunks | 120 | 393 |
| 空 text | 0 | 0 |
| 缺失 embedding | 0 | 0 |
| chunk index gap | 0 个文档 | 0 个文档 |
| 向量维度 | 384/384 | 1792/1792 |
| 零向量 | 0 | 0 |
| 向量范数中位数 | 1.000000 | 1.000000 |

BGE mapping 为 `dense_vector(384)`、cosine、`int8_hnsw`；Conan 为 `dense_vector(1792)`，实际 kNN/script-score 查询可用。两库目标 chunk 的 `embedding_model` 均一致，没有混入其他模型向量。

## 发现的问题

1. **标题字段没有实际值。** BGE mapping 虽声明了 `title`，但全库 928,534 条均不存在 title 值；Conan mapping 没有 title 字段。目标样本中 BGE 120/120、Conan 393/393 均缺 title。当前索引实际只存了 `text`、`doc_id`、`chunk_id` 等字段。
2. **BGE chunk 偏长且无 overlap。** 目标 chunk 文本长度中位数约 3,242 字符，`chunk_overlap=0`；Conan 中位数约 1,003 字符，使用 448/32 的递归切块。两者没有空 chunk 或 chunk 序号断裂，但 BGE 缺少标题/父级上下文拼接，可能削弱语义向量对章节语境的表达。
3. **没有发现灾难性入库错误。** O3.3 的 preprocess、manifest、bulk 和 ES health 均正常；本轮也未发现维度错配、零向量、空文本或目标文档缺失。

## 诊断结论

- 当前 dense 命中率低不能归因于“索引没有建完整”或“向量损坏”；更符合查询与 chunk 表征不匹配。
- 标题/父级上下文缺失是已确认的索引质量缺口，尤其会影响章节型、项目型和语义题；但它尚未被单变量证明是 46 题 dense raw-miss 的唯一原因。
- BGE 的 `both_miss` 仍应优先做小规模重切块验证；直接换 Conan 没有证据支持，因为 Conan 的向量完整性正常但 Semantic dense 命中更低。

## 下一步实验

1. 从 61 个 gold 文档构建小型对照索引：A 为当前 `text`/512/0，B 为“标题或路径 + 父级标题 + text”/400–512/64–96；保持 BGE-small 模型不变。
2. 对 46 题测 Recall@30/120/240/1000，并同时检查 BM25 命中和控制题，不接入 LLM。
3. 若 B 方案 dense Recall@240/1000 有稳定净增益，再决定是否重建全量 BGE；否则回到通用 query 表达和候选并集策略。
4. 新索引 schema 应显式保留 `title`/`section_path` 等元数据，并确保 embedding 文本与查询侧使用同一字段拼接规范。
