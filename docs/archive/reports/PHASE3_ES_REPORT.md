# 阶段三：全量 Elasticsearch 索引报告

完成时间：2026-07-29（Asia/Shanghai）  
目标服务器：`10.72.100.29`  
索引：`enterprise-rag-bge-small-v1`

## 最终结论

- 51 万语料已全部传输、校验、解压、分块、向量化并写入 Elasticsearch。
- 输入文件：511,961；唯一业务 `doc_id`：511,957；最终分块/ES 文档：928,534。
- 文件处理失败：0；ES 写入失败：0；集群状态：green。
- BM25、稠密 KNN、加权 RRF 混合召回均已通过端到端 Top-5 冒烟测试。
- 历史 500 题、16.1% 召回率结果未复用；阶段四将基于本索引重新评测。

## 数据完整性

上传采用 16 个分卷压缩包，总传输量 926,325,725 字节。客户端和服务器端均校验 SHA-256、压缩包内 `.txt` 数量；解压后文件总数为 511,961。

预处理发现 4 个业务 `doc_id` 被不同源文件复用，且内容不同。最终索引策略 `dataset-duplicate-path-v2` 对这些 ID 的所有分块统一加入确定性的路径哈希后缀，避免遍历顺序变化造成覆盖。精确校正时先备份旧记录，再删除 18 条过渡记录、写入 16 条最终记录；审计确认 16 条记录全部带 `__dup-` 消歧标识。

| 来源 | 最终分块数 |
| --- | ---: |
| slack | 405,171 |
| gmail | 293,504 |
| linear | 66,831 |
| google_drive | 60,934 |
| fireflies | 40,686 |
| hubspot | 19,021 |
| confluence | 15,866 |
| github | 14,335 |
| jira | 12,186 |
| **合计** | **928,534** |

## 模型与索引契约

- 嵌入模型：`BAAI/bge-small-en-v1.5`
- 固定 revision：`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`
- 运行设备：GPU 2（CUDA）
- 向量维度/相似度：384 / cosine
- ES 向量索引：`int8_hnsw`，`m=16`，`ef_construction=100`
- 分块：`fixed-v2`，512 字符，overlap 0
- Qwen/lark 仅用于后续生成和评分，不用于嵌入。

## 构建与复跑验证

全量任务从 13:58:32 运行至 15:02:26。首次全量写入在已有 10,000 条金丝雀记录的基础上新增 918,528 条，平均约 259.9 chunks/s。随后对同一数据集完整复跑：检查 928,528 条、写入 0、识别为已存在 928,528、失败 0，用时 36.879 秒，证明断点续跑/幂等机制有效。

修复 4 个重复业务 ID 后，最终报告为：检查 928,534、写入 16、已存在 928,518、失败 0；ES 最终计数严格为 928,534。

## 最终运行状态

- ES 8.19.12，单节点，主分片和副本状态正常，集群 green。
- ES 数据目录约 9.8 GiB；完整语料目录约 3.3 GiB；分块缓存约 2.8 GiB。
- 服务器根分区剩余约 200 GiB。
- 三路召回测试结果保存在服务器：`.index_cache/full_es_bge_small/retrieval_smoke.json`。

## 服务器产物

```text
/opt/enterprise-rag-bench/app
/opt/enterprise-rag-bench/app/corpus/all_documents
/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small
/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/es_build_report_final.json
/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/retrieval_smoke.json
/opt/enterprise-rag-bench/duplicate_docs_backup.json
/opt/enterprise-rag-bench/incoming/full_corpus
/opt/enterprise-rag-es/data
```

## 下一阶段

按 10 题预检、50 题小规模门禁、500 题正式评测三层推进。每一层分别保存检索命中、生成答案、评分明细、错误类型和运行参数；先验证问题集与参考证据映射，再启动 Qwen 推理，避免直接消耗完整 500 题成本。
