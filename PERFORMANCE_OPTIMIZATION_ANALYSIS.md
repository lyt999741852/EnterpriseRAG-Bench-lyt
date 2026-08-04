# EnterpriseRAG-Bench 全链路性能与实验效率优化分析

> 分析日期：2026-07-29  
> 分析范围：文档预处理、切块、Embedding、Elasticsearch 入库、检索、生成、评估和实验迭代工作流  
> 结论性质：基于当前仓库代码审计、本机实测、现有 GPU/Elasticsearch Canary 报告及官方技术文档

## 1. 执行摘要

当前系统的 **首次全量建库速度并不异常**。现有 10,000 chunk Canary 的 Embedding 与 Elasticsearch 入库总吞吐为 **248.65 chunks/s**，线性外推后，全量约 100 万～128 万 chunks 的向量化与入库时间大约为 **67～86 分钟**。考虑文档读取、切块、索引合并和运行波动，首次全量构建控制在 **1～2 小时**属于可接受范围。

真正影响个人任务效率的是：当前实验工作流没有做到“只重算受参数影响的阶段”。调整 Prompt、生成参数、top-k、RRF 权重或评估并发时，程序仍可能触发以下无关工作：

- 扫描全部 511,961 个小文件；
- 加载完整 `chunks.jsonl`；
- 对 Elasticsearch 中全部 chunk ID 做存在性检查；
- 因为完整配置指纹变化而放弃复用已生成答案；
- 将建库、检索、生成和评估耦合在同一次运行中。

因此，最高优先级不是立刻更换更大的 Embedding 模型或升级 GPU，而是：

1. 将流水线拆分为可独立运行、独立缓存的阶段；
2. 为每个阶段建立最小依赖指纹；
3. 使用不可变、版本化的 Elasticsearch 实验索引；
4. 已完成索引的检索实验直接连接 Elasticsearch，不再读取原始语料；
5. 使用 10k → 5万/10万 → 全量的实验漏斗，避免每个候选方案都全量建库。

完成这些改造后，日常实验应从“几十分钟到一小时”下降为“几秒到几分钟”；全量重建只在候选方案冻结后执行。

---

## 2. 当前数据规模与已知配置

### 2.1 语料规模

| 指标 | 当前值 |
|---|---:|
| 文档数 | 511,961 |
| 数据源 | 9 类 |
| 文本总大小 | 2,473,624,226 bytes，约 2.47 GB |
| GitHub Canary 文档数 | 8,052 |
| GitHub Canary 生成 chunks | 14,335 |
| 全量预计 chunks | 约 100 万～128 万 |

全量上界来自历史部分运行：约 155,000 个文档已产生约 388,000 个 chunks，即约 2.5 chunks/doc；按这个比例外推约为 128 万 chunks。实际值仍需由完整预处理报告确认。

### 2.2 当前正式方案

当前 `configs/full_es_qwen.yaml` 的主要设置：

```yaml
chunking:
  version: fixed-v2
  chunk_size: 512
  chunk_overlap: 0

embedding:
  provider: sentence_transformers
  model_name: BAAI/bge-small-en-v1.5
  device: cuda
  batch_size: 256
  dimension: 384

elasticsearch:
  index_name: enterprise-rag-bge-small-v1
  bulk_size: 256
```

Elasticsearch 当前资源限制：

| 项目 | 配置 |
|---|---:|
| Elasticsearch | 8.19.12 |
| CPU 上限 | 8 cores |
| JVM Heap | 8 GiB |
| 容器内存上限 | 16 GiB |
| Primary shards | 1 |
| Replicas | 0 |
| Refresh interval | 30s |
| 向量索引 | `int8_hnsw`（由 ES 8.19.12 选择） |

仓库中没有记录 GPU 型号、显存、服务器总内存、磁盘类型和磁盘吞吐，因此目前不能精确判断 GPU、JSON 序列化、HTTP Bulk 或 HNSW 构建中的哪一项占主导。

---

## 3. 已实测结果与全量外推

### 3.1 本机语料签名扫描

当前 `_dataset_signature()` 会对全部 `.txt` 文件递归执行 `stat()`。本次直接调用项目实现的实测结果：

```text
txt_count:        511,961
total_size:       2,473,624,226 bytes
stat_failures:    0
elapsed_seconds:  61.653
```

也就是说，即使没有任何文档变化，每次需要验证缓存时，也可能先消耗约 1 分钟扫描小文件。这个过程是文件系统元数据瓶颈，GPU 无法加速。

### 3.2 GPU Embedding 与 ES 入库 Canary

现有 `PHASE2_ES_REPORT.md` 记录：

| 指标 | 结果 |
|---|---:|
| 新向量 | 10,000 |
| 失败文档 | 0 |
| Embedding + Bulk 总耗时 | 40.217 秒 |
| 综合吞吐 | 248.65 chunks/s |
| ES Primary Store | 约 108.1 MiB |
| 完整重跑存在性检查 | 0.598 秒 |

### 3.3 全量时间和空间估算

按现有综合吞吐做线性外推：

| 预计 chunks | Embedding + 入库时间 | Primary Store 估算 |
|---:|---:|---:|
| 1,000,000 | 约 67.0 分钟 | 约 10.6 GiB |
| 1,280,000 | 约 85.8 分钟 | 约 13.5 GiB |

该估算不包含：

- 51 万文件读取；
- 文本切块和 chunk checkpoint 写入；
- 首次加载模型；
- Elasticsearch segment merge；
- 完成后的 refresh；
- 网络和共享服务器负载波动；
- HNSW 随数据量增长可能产生的非线性影响。

因此，首次全量构建的合理预期应设置为 **1～2 小时**，并通过完整运行补充真实分阶段报告。

---

## 4. 当前链路为什么让实验显得过慢

### 4.1 各阶段耦合在同一入口

当前 `src.pipeline` 的执行顺序是：

```text
读取问题
→ 构建或加载 Indexer
→ 检查/写入 Elasticsearch
→ 检索
→ 生成
→ 评估
```

这意味着即使只想调整 Prompt 或 RRF 权重，也仍要经过索引初始化路径。对于已经冻结的 ES 索引，检索和生成本来只需要：

```text
加载查询 Embedding 模型
→ 连接 Elasticsearch alias
→ 检索
→ 生成
```

不应再次访问原始语料和完整 chunk 文件。

### 4.2 运行指纹包含完整配置

当前答案恢复指纹使用：

```python
payload = {"config": cfg, "question_ids": question_ids}
```

结果是修改以下无关参数也可能让答案缓存失效：

- evaluation parallelism；
- evaluation timeout；
- checkpoint interval；
- 输出目录或运行名称；
- 不影响生成内容的执行参数。

正确做法是为各阶段建立独立最小指纹，而不是一个完整配置指纹控制所有缓存。

### 4.3 数据签名每次扫描 51 万文件

当前缓存校验通过：

```text
文件数量 + 总大小 + 最大 mtime + 数据源列表
```

获得签名，但计算它需要遍历所有文件。项目已经存在 `.stage/full_corpus/manifest.json`，其中包含归档哈希和各数据源文件数，可以将其作为不可变 `corpus_snapshot_id`。

日常实验只应读取该 manifest；只有显式执行 ingest 或 refresh-corpus 时才重新扫描文件。

### 4.4 ES 重跑会检查所有 chunk ID

当前 `index_chunks()` 对每个 bulk 执行：

```text
_mget 检查已存在 ID
→ 对缺失文本做 Embedding
→ _bulk 写入
```

在 10k Canary 中非常快，但 100 万 chunks、bulk 256 时会产生约 3,907 次串行 `_mget` HTTP 往返。若索引已经被标记为完整，这些检查没有必要。

应改为：

- 索引元数据记录 `building / complete / failed`；
- 完整索引直接跳过整个摄取阶段；
- 中断恢复只检查最后未完成的 shard；
- 每个 shard 保存最后成功 batch 和 chunk 数；
- 必要时用 shard checkpoint，而不是对整个索引做全量 `_mget`。

### 4.5 当前实验索引存在错误复用风险

当前 ES 索引名称固定为：

```text
enterprise-rag-bge-small-v1
```

Chunk ID 包含 `chunker_version`，但不直接包含 `chunk_size`、`overlap`、模型 revision 或 normalization 设置。如果只改变 chunk size 而没有同步修改 version，或者换成另一个同为 384 维的模型，旧 ID 可能被判定为已存在并跳过。

这不仅是性能问题，也是实验正确性问题。

---

## 5. 推荐的目标架构

### 5.1 阶段解耦

推荐拆分成以下独立阶段：

```text
Corpus Snapshot
    ↓
Document Manifest
    ↓
Chunk Snapshot
    ↓
Embedding Snapshot
    ↓
Elasticsearch Index
    ↓
Retrieval Results
    ↓
Generated Answers
    ↓
Evaluation Results
```

每个阶段应支持：

- 单独执行；
- 单独恢复；
- 单独清理；
- 独立输入/输出指纹；
- 输出结构化耗时和资源报告；
- 只在上游有效输入变化时失效。

### 5.2 各阶段最小指纹

| 阶段 | 指纹必须包含 |
|---|---|
| Corpus | 归档 SHA256、文件数、数据版本 |
| Chunk | corpus snapshot、预处理版本、tokenizer、chunk size、overlap、数据源策略 |
| Embedding | chunk snapshot、模型、revision、query/document 模式、normalize、dtype、维度 |
| ES Index | embedding snapshot、mapping、vector similarity、HNSW/quantization、shard 数 |
| Retrieval | index ID、BM25/dense/hybrid、top-k、candidate-k、RRF、过滤、reranker |
| Generation | retrieval result ID、Prompt 版本、LLM 模型、temperature、context 策略 |
| Evaluation | answers ID、Judge 模型、评估器版本、评估参数 |

批大小、worker 数、进度日志间隔等只影响执行性能、不影响产物内容的参数，不应导致结果缓存失效。

### 5.3 不可变 ES 索引与 Alias

推荐索引命名示例：

```text
enterprise-rag__fixed384x64-v1__bge-small-en-v1.5-5c38ec7__cosine__384d
```

索引创建后视为不可变：

- 新切块策略建立新索引；
- 新 Embedding 模型建立新索引；
- 完成验证后切换 alias；
- 不在旧索引中原地混合不同实验向量；
- Alias 只指向当前正式候选。

---

## 6. 最优实验漏斗

“最优方案不是几次就能找到”是正常的，因此必须减少每次候选验证的成本，而不是让所有候选都跑全量。

### Level 1：10k 性能 Canary

用途：

- 测 batch size；
- 测 dtype；
- 测 GPU 利用率和显存；
- 测 bulk size 和上传并发；
- 测中断恢复；
- 测 ES 映射和文档完整性。

该层不用于决定最终召回质量，因为 10k GitHub-only 不能代表全部 9 类数据源。

### Level 2：5万～10万分层开发索引

必须满足：

- 覆盖全部 9 类数据源；
- 按真实数据源比例或设定合理分层比例；
- 强制包含开发题的 gold 文档；
- 加入足够多的困难干扰文档；
- 固定 50 题左右的分层开发题集；
- 报告 Recall@5、Recall@10、MRR、各题型召回和查询延迟。

这一层用于比较：

- chunk size/overlap；
- source-aware chunking；
- bge-small/base/E5；
- query instruction；
- BM25/Dense 权重；
- RRF candidate-k；
- reranker；
- 父子文档扩展。

### Level 3：全量候选验证

只允许开发集最好的 1～2 个方案进入全量：

```text
10题冒烟
→ 50题分层验证
→ 500题生成
→ 官方评估
```

禁止为每个小参数组合建立全量索引。

---

## 7. 文档预处理与切块优化

### 7.1 使用真实 tokenizer

当前 `chunk_size: 512` 实际按空白词计数，不是 BGE tokenizer token。`bge-small-en-v1.5` 最大序列长度为 512 subword tokens，因此代码、URL、JSON、Markdown 和长单词可能使一个“512词”chunk 远超模型输入上限，并被静默截断。

建议候选：

| 方案 | Child chunk | Overlap | 用途 |
|---|---:|---:|---|
| A | 320 tokens | 48 | 更细粒度、减少截断 |
| B | 384 tokens | 64 | 首选平衡候选 |
| C | 512 tokens | 0 | 保留现有基线 |

最终值必须由项目开发集 Recall 决定，不应直接根据通用经验冻结。

### 7.2 数据源感知切块

建议逐步引入：

- GitHub：标题、PR 描述、diff、review comment 分段；
- Gmail：主题、发件人、日期、线程消息分段，去除重复引用；
- Slack：按线程或话题聚合，保留频道、发言人、时间；
- Jira/Linear：字段化 issue + comment；
- Confluence/Drive：按标题层级和段落；
- Fireflies：按时间段和发言人；
- HubSpot：按公司、联系人、交易记录字段。

第一版不必一次完成所有格式。先实现通用父子切块，再针对低召回数据源改进。

### 7.3 避免无意义尾块

带 overlap 的固定步长切块可能产生只有几个 token 的最后尾块。建议在到达文档末尾后立即停止，或将过短尾部合并到前一个 chunk，并记录最小 chunk token 数。

### 7.4 分片格式

建议每个 chunk shard 为 20,000～50,000 chunks：

- 原子写入；
- shard 完成后写 checkpoint；
- 中断只重做最后未完成 shard；
- 可考虑 Parquet/Arrow 替代超大的 JSONL，以提高加载速度和减少 Python 对象开销；
- 检索服务不应加载完整 shard，ES `_source` 已能返回所需文本。

---

## 8. Embedding 优化

### 8.1 当前模型是否需要更换

`BAAI/bge-small-en-v1.5` 适合作为首个可信全量基线：

- 384 维，存储成本低；
- 现有吞吐已经可用；
- 英文检索能力明显强于极轻量 MiniLM 基线；
- 模型 revision 已冻结，复现性良好。

不建议在尚未修正 query instruction、tokenizer 切块和实验缓存前直接升级大模型，因为届时无法区分收益来自模型还是链路修复。

开发索引阶段只建议比较：

1. `bge-small-en-v1.5`；
2. `bge-base-en-v1.5`；
3. `e5-base-v2`。

`bge-base` 从 384 维变为 768 维，向量存储和相似度计算成本显著增加；只有本项目 Recall/最终得分提升足够大时才值得全量采用。

### 8.2 Query instruction

BGE 官方对短查询检索长文档建议在 query 前增加：

```text
Represent this sentence for searching relevant passages: 
```

文档 Embedding 不加 instruction。当前代码对查询和文档使用相同 `encode()`，应将其拆成 `encode_query()` 和 `encode_documents()`。虽然 v1.5 无 instruction 也能工作，但该设置应在模型 A/B 前固定。

### 8.3 GPU 推理优化

建议按顺序测试：

1. FP32 基线；
2. FP16；
3. GPU 支持良好时测试 BF16；
4. 兼容时测试 SDPA/Flash Attention；
5. 按 token 长度分桶，减少 padding；
6. batch size 依次测试 `128/256/512/1024`；
7. 记录吞吐、显存峰值、GPU 利用率和向量一致性。

批量最好按总 token 数控制，而不仅是文本条数。不同数据源长度差异很大，固定条数 batch 容易造成显存波动和 padding 浪费。

### 8.4 多 GPU

多 GPU 不是当前第一优先级。只有单 GPU 流水线已能持续满载后再引入：

- 按确定性 shard 分配 GPU；
- 每张 GPU 独立生成 embedding shard；
- 主进程或独立 uploader 负责 ES Bulk；
- 禁止多个 GPU 对同一 chunk 重复写入；
- shard 输出包含模型和数据指纹。

---

## 9. Elasticsearch 入库优化

### 9.1 将 Embedding 与 Bulk 做成流水线

当前流程严格串行：

```text
检查 batch ID
→ GPU Embedding
→ Python 转 list/JSON
→ HTTP Bulk
→ 等待 ES 完成
→ 下一批
```

这会造成 GPU 在上传时空闲、Elasticsearch 在 Embedding 时空闲。推荐：

```text
Reader/Chunker
    ↓
GPU Embedding Producer
    ↓ bounded queue
2～4 Bulk Upload Workers
    ↓
Elasticsearch
```

队列必须有界，避免向量和文本无限堆积在内存中。

### 9.2 Bulk 大小

当前 `bulk_size: 256`。按 Canary 的 ES 存储量粗略估算，每个 chunk 平均约 11 KB；因此：

| Bulk 条数 | 粗略请求量 |
|---:|---:|
| 256 | 约 2.8 MB |
| 512 | 约 5.5 MB |
| 1024 | 约 11 MB |
| 2000 | 约 21～22 MB |

建议测试 `256/512/1024/2000`，选择吞吐平台期中较小的值。Bulk 不应无限增大；并发 worker 遇到 HTTP 429 时需随机指数退避。

### 9.3 Refresh 与 Replica

初次全量导入时：

```text
refresh_interval = -1
number_of_replicas = 0
```

完成后：

```text
恢复 refresh_interval
执行一次 refresh
验证 count、mapping、抽样检索
标记 index complete
切换 alias
```

当前 replica=0 已正确；`refresh_interval=30s` 可以进一步在全量导入期间改为 `-1`。

### 9.4 Shard 数

预计单索引约 11～14 GiB，一个 primary shard 仍在合理范围。不要仅为了初次入库速度盲目增加 shard。只有在完整压测显示：

- 单 shard CPU 已饱和；
- Bulk 并发无法继续提升；
- 查询并发需要扩展；

才比较 1 shard 与 2 shards。

### 9.5 存在性检查与恢复

推荐 ES 索引元数据：

```json
{
  "artifact_fingerprint": "...",
  "status": "building|complete|failed",
  "expected_chunks": 1280000,
  "indexed_chunks": 640000,
  "last_completed_shard": 15,
  "model_revision": "...",
  "chunk_snapshot": "..."
}
```

索引为 complete 且指纹匹配时直接跳过。只有 building/failed 状态才执行恢复检查。

---

## 10. 服务器资源建议

### 10.1 当前配置评价

当前 8 GB heap / 16 GB 容器对单个约 14 GB Primary Index 可以先使用：

- 单 shard 的默认 indexing buffer 已基本足够；
- 增大 heap 未必提升写入速度；
- 保留足够文件系统 page cache 比把全部内存分给 JVM 更重要；
- SSD/NVMe 和并行 Bulk 往往比继续增加 heap 更有效。

### 10.2 建议配置档位

| 使用场景 | 主机内存建议 | ES 容器 | Heap | 磁盘 |
|---|---:|---:|---:|---|
| 单个正式索引、低并发 | ≥32 GB | 16～24 GB | 8～12 GB | 本地 NVMe |
| 同时保留 2～3 个实验索引 | ≥64 GB | 24～32 GB | 12～16 GB | ≥100 GB 可用 NVMe |
| 高并发检索或多个长期索引 | 需实测规划 | 32 GB+ | 不超过约一半内存 | 独立高速盘/多节点 |

这些是容量规划建议，不应在缺少主机硬件数据时直接修改生产限制。

### 10.3 必须补采集的硬件指标

```text
nvidia-smi
lscpu
free -h
lsblk -o NAME,TYPE,SIZE,ROTA,MOUNTPOINT,MODEL
df -h
docker stats --no-stream
curl localhost:9200/_nodes/stats
```

至少记录：

- GPU 型号、显存和利用率；
- CPU 型号、物理核/逻辑核；
- 主机总内存和可用内存；
- 磁盘是否 NVMe、剩余空间和 IOPS；
- ES heap、page cache、merge time、indexing pressure；
- Bulk 429、平均/尾部延迟；
- 单独 Embedding 与单独 Bulk 的吞吐。

---

## 11. 分阶段性能指标

当前 40.217 秒只覆盖“Embedding + Bulk”合并时间，无法判断优化方向。每次基准应输出：

```json
{
  "corpus_scan_seconds": 0,
  "document_read_seconds": 0,
  "chunking_seconds": 0,
  "chunk_write_seconds": 0,
  "model_load_seconds": 0,
  "embedding_seconds": 0,
  "serialization_seconds": 0,
  "mget_seconds": 0,
  "bulk_request_seconds": 0,
  "refresh_seconds": 0,
  "total_seconds": 0,
  "embedding_chunks_per_second": 0,
  "indexing_chunks_per_second": 0,
  "gpu_peak_memory_mb": 0,
  "es_rejected_requests": 0
}
```

只有获得这些数据后，才能判断下一步应优化 GPU、Python 序列化、网络还是 Elasticsearch。

---

## 12. 参数变化时应该重跑什么

| 参数变化 | 预处理 | 切块 | Embedding | ES 入库 | 检索 | 生成 | 评估 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prompt | 否 | 否 | 否 | 否 | 可复用 | 是 | 是 |
| LLM 模型/temperature | 否 | 否 | 否 | 否 | 可复用 | 是 | 是 |
| top-k/RRF/candidate-k | 否 | 否 | 否 | 否 | 是 | 是 | 是 |
| reranker | 否 | 否 | 否 | 否 | 是 | 是 | 是 |
| Query instruction | 否 | 否 | 仅查询侧 | 否 | 是 | 是 | 是 |
| Embedding 模型 | 否 | 否 | 是 | 新索引 | 是 | 是 | 是 |
| normalize/dimension | 否 | 否 | 是 | 新索引 | 是 | 是 | 是 |
| chunk size/overlap | 否 | 是 | 是 | 新索引 | 是 | 是 | 是 |
| 数据源预处理策略 | 是 | 是 | 是 | 新索引 | 是 | 是 | 是 |
| Evaluation 并发/Judge | 否 | 否 | 否 | 否 | 否 | 否 | 是 |

这张表应成为缓存失效规则和任务调度规则的直接依据。

---

## 13. 推荐实施顺序

### P0：先消除不必要重算

1. 新增 `index-only / retrieve-only / generate-only / evaluate-only` 运行模式；
2. ES 检索模式不再构造全量 Indexer；
3. 使用 staged archive manifest 作为 corpus snapshot；
4. 拆分 chunk、embedding、index、retrieval、generation、evaluation 指纹；
5. 为 ES 索引增加 artifact fingerprint 和 complete 状态；
6. 使用版本化索引名和 alias；
7. 修正答案 resume 只依赖生成阶段输入。

预期收益：日常检索/生成实验由几十分钟下降到秒级或分钟级。

### P1：提升单次全量摄取吞吐

1. 增加分阶段计时；
2. 测试 FP16/BF16；
3. 测试 batch 128/256/512/1024；
4. Embedding 与 Bulk 流水线并行；
5. Bulk 测试 256/512/1024/2000；
6. 全量导入期间 refresh=-1；
7. shard checkpoint 替代完整 `_mget`；
8. 记录并处理 429/backoff。

预期收益：在确认瓶颈后争取提高综合吞吐，但不预设固定倍数。

### P2：提高检索质量

1. 使用真实 tokenizer；
2. 加入 BGE query instruction A/B；
3. 比较 320/48、384/64、512/0；
4. 建立 5万～10万分层开发索引；
5. 固定 bge-small 基线后比较 bge-base/E5；
6. 比较 RRF、reranker、父子扩展；
7. 按题型和数据源报告 Recall，而不是只看总分。

### P3：服务器容量与部署

1. 补充 GPU/CPU/RAM/NVMe 信息；
2. 采集 ES node stats；
3. 根据同时保留索引数决定是否增加容器内存；
4. 评估索引 snapshot/归档和过期实验索引清理策略；
5. 只有压测证明单 shard 是瓶颈时再调整 shard 数。

---

## 14. 验收标准

### 实验效率

- 修改 Prompt 不访问 corpus，不检查 ES 全部 ID；
- 修改 RRF/top-k 不重新 Embedding；
- 修改 evaluation 配置不重新生成答案；
- complete 索引启动检索时不加载完整 chunks；
- 每个阶段可独立恢复和复用。

### 正确性

- 任意关键切块/模型变化自动产生新 artifact ID；
- 不同模型或切块策略不会写入同一不可变索引；
- ES count 等于成功 chunks 数；
- 每个向量记录模型 revision 和 chunk snapshot；
- Alias 只在完整验证后切换；
- 查询 instruction 和文档编码策略被纳入指纹。

### 性能

- 10k 报告同时给出 embedding-only 和 bulk-only 吞吐；
- GPU 利用率、显存峰值和 ES 429 可观测；
- 全量构建可从 shard checkpoint 恢复；
- 重跑 complete 索引只做常数级元数据校验；
- 500 题检索延迟报告包含 P50/P95/P99。

---

## 15. 最终建议

当前 `bge-small-en-v1.5 + GPU + Elasticsearch int8_hnsw` 可以继续作为首个正式基线，不需要因为一次全量构建约 1～2 小时就立即换模型或扩服务器。

最值得投入的优化顺序是：

```text
阶段解耦
→ 精细缓存指纹
→ 不可变索引与快速检索模式
→ 分层开发索引
→ 分阶段性能观测
→ GPU/ES 流水线并行
→ tokenizer 与检索质量优化
→ 最后再决定大模型和服务器扩容
```

换句话说，应优化的是“需要尝试很多次时，每次只付必要成本”的能力，而不是只追求一次全量建库的极限速度。

---

## 参考资料

### 仓库内证据

- `PHASE2_ES_REPORT.md`：10k Canary 吞吐、存储和重跑结果；
- `configs/full_es_qwen.yaml`：正式 Embedding、Bulk 和索引配置；
- `src/indexer.py`：语料签名、预处理、切块和缓存实现；
- `src/elasticsearch_backend.py`：串行 `_mget → embed → bulk` 实现；
- `src/pipeline.py`：全流程耦合和完整配置运行指纹；
- `deploy/elasticsearch/docker-compose.server.yml`：ES heap、CPU 和容器限制；
- `.stage/full_corpus/manifest.json`：完整语料归档和文件计数。

### 官方资料

- BGE 模型卡：<https://huggingface.co/BAAI/bge-small-en>
- Sentence Transformers 推理加速：<https://sbert.net/docs/sentence_transformer/usage/efficiency.html>
- Elasticsearch Indexing Speed：<https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/indexing-speed>
- Elasticsearch kNN 调优：<https://www.elastic.co/guide/en/elasticsearch/reference/8.19/tune-knn-search.html>
