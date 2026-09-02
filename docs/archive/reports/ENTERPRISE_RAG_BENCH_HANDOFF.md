# EnterpriseRAG-Bench 调研与项目交接记录

> 更新时间：2026-07-28  
> 工作目录：`D:\EnterpriseRAG-Bench`  
> 用途：在新的对话中读取本文件，继续 EnterpriseRAG-Bench 全量 RAG 测试系统的开发、运行和优化。  
> 安全说明：本文不记录任何 API Key。项目脚本中曾发现明文 Key，必须撤销并更换。

---

## 1. 用户目标与当前策略

用户是企业实习生，负责调研适合组内自研 RAG 系统的企业级测试数据集。目前选择并研究：

- GitHub：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench>
- 官方页面：<https://onyx.app/enterpriserag-bench>
- 论文：<https://arxiv.org/abs/2605.05253>

自研 RAG 系统流程包括：

```text
文档预处理
→ 切块
→ 向量化入库
→ 多级检索
→ 重排序
→ 提示词工程
→ LLM生成答案
→ 官方评测
```

总体策略已经确定：

1. 先用最小标准跑通“数据集到官方评分”的完整闭环；
2. 冻结首个可信全量基线；
3. 再根据数据源风格、题型和评分权重优化切块、检索和生成；
4. 最终生成官方格式 JSONL，并尝试提交排行榜。

---

## 2. 数据集总体规模

语料模拟一家名为 Redwood Inference 的 AI 模型推理企业。

本地压缩包和数据集曾核实：

| 项目 | 数量 |
|---|---:|
| 官方文档总数 | 511,962 |
| 数据源数量 | 9 |
| 文档格式 | 全部为 `.txt` |
| 解压后文本总量 | 约 2.47 GB |
| 压缩包大小 | 约 1.26 GB |
| 文档大小中位数 | 约 4,295 bytes |
| 文档平均大小 | 约 4,833 bytes |
| 文档 P95 | 约 9,015 bytes |
| 核心评测问题 | 500 |
| 额外 metadata 问题 | 100，不进入官方榜单 |

官方完整语料的来源分布：

| 数据源 | 文档数 | 占比 | 风格 |
|---|---:|---:|---|
| Slack | 285,605 | 55.8% | 频道对话、消息线程、代码和日志、不断更新的决定 |
| Gmail | 121,390 | 23.7% | 邮件头、回复链、承诺、价格、日期、附件提及 |
| Linear | 35,308 | 6.9% | Issue、状态、优先级、负责人、验收条件、评论 |
| Google Drive | 25,108 | 4.9% | PRD、计划、报告、草稿、标题、列表和 Markdown 表格 |
| HubSpot | 15,017 | 2.9% | CRM 公司、交易、阶段、负责人、金额和活动记录 |
| Fireflies | 10,173 | 2.0% | 会议标题、参会人、时间戳转录、行动项；无音频 |
| GitHub | 8,052 | 1.6% | PR、review、代码块、日志和配置；不是完整代码仓库 |
| Jira | 6,120 | 1.2% | 工单、严重度、状态、复现、评论、解决方案 |
| Confluence | 5,189 | 1.0% | Wiki、Runbook、ADR、政策、标题、列表、表格、代码块 |

### 文档内容形态

- 没有原生 PDF、DOCX、XLSX、PPTX、PNG、JPG、SVG；
- 有 Markdown/ASCII 表格、标题、项目符号、编号列表、代码围栏、日志、命令和字段记录；
- 文本中可能提到截图、附件、图表和 Dashboard，但没有实际二进制对象；
- 不是多模态、OCR 或复杂版面评测集；
- 有少量乱码、字面量 `\n`、格式漂移和合成数据噪声。

根目录的 `questions.jsonl` 包含标准答案，绝不能进入 RAG 索引，否则构成答案泄漏。

---

## 3. 十类核心问题

`questions.jsonl` 每题包含：

```text
question_id
question_type
source_types
question
expected_doc_ids
gold_answer
answer_facts
```

实际500题分布：

| 题型 | 数量 | 官方总分权重 | 标准证据文档 |
|---|---:|---:|---|
| Basic | 175 | 35% | 固定1篇 |
| Semantic | 125 | 25% | 固定1篇 |
| Intra-document reasoning | 40 | 8% | 固定1篇 |
| Project-related | 40 | 8% | 2～9篇，平均4.22 |
| Constrained | 30 | 6% | 1～2篇，平均1.43 |
| Conflicting info | 20 | 4% | 固定2篇 |
| Completeness | 20 | 4% | 2～10篇，平均6.5 |
| Miscellaneous | 20 | 4% | 固定1篇 |
| Info not found | 20 | 4% | 0篇 |
| High level | 10 | 2% | 0篇固定 gold 文档 |

重要结论：

- Basic + Semantic 共300题，占60%；
- 再加 Intra-document 和 Miscellaneous，单文档型问题共360题，占72%；
- 第一阶段优先提高单文档命中和事实提取，收益最大；
- `expected_doc_ids` 是官方最小标准证据集，不是系统必须恰好召回的文档数；
- 替代有效文档可能存在；
- 最终提交不超过10个、去重后的父文档 `dsid`；
- 不提交初始召回100个候选，也不提交内部 chunk ID。

正式运行 RAG 时只能把 `question` 传入系统。以下字段只能用于离线统计或评测，不能传给检索器/生成器：

```text
question_type
source_types
expected_doc_ids
gold_answer
answer_facts
```

---

## 4. 十类题型代表性示例（已抽取）

此前已经从每类抽取一题并分析答案形式：

| 题型 | 示例问题内容摘要 | 答案形式 |
|---|---|---|
| Basic | Acme 的 P1/P2 支持响应时间 | 精确短答：P1 4小时，P2 8个工作小时 |
| Semantic | 合作伙伴电话涉及的多个截止时间 | 列出日期与对应事项 |
| Intra-document | 哪些团队签字及对应工单号 | 同一文档内组合多个事实 |
| Project-related | Smart Routing fallback 与终止 503 的处理和客服解释 | 多文档综合、结构化说明 |
| Constrained | 2026年3月 SSE TCP RST、重复心跳、根因和 PR | 满足日期/系统等限制后的精确事实 |
| Conflicting info | ClearEdge 最终 SHA256 和执行时间 | 区分旧信息和最新生效信息 |
| Completeness | 除当前客户外哪些客户出现 JSON Schema timeout | 枚举完整列表，不遗漏 |
| Miscellaneous | 植物浇水周期 | 简单自然语言短答 |
| High level | Redwood 如何实现可靠性和优雅降级 | 跨语料高层总结 |
| Info not found | observability-pack 的 Slack 归属频道 | 明确回答语料中找不到，不编造 |

---

## 5. 官方评分规则

官方给出四个指标：

1. **Correctness**：LLM 对答案整体正确与否进行二元判断；
2. **Completeness**：答案覆盖了多少 `answer_facts`，0～100%；
3. **Document Recall**：提交的文档中覆盖了多少标准文档，论文口径接近 Recall@10；
4. **Invalid Extra Documents**：提交文档中既不是 gold、也没有被判为有效替代证据的数量。

### 榜单主分数

每题主分数为：

```text
Correctness × Completeness
```

等价于：

```text
如果 Correctness = True：该题得 Completeness 分
如果 Correctness = False：该题得 0 分
```

500题等权平均，官方显示范围是0～100，不是0～1。例如68.2相当于归一化后的0.682。

代码中的汇总字段是：

```text
combined_correctness_completeness_score
```

### 为什么 Document Recall 和 Invalid Documents 不进入主分

- gold 文档集合可能不完整，存在替代有效证据；
- 30题没有固定 `expected_doc_ids`；
- 不同系统可能采用不同但合理的证据路径；
- Invalid Documents 是计数，与0～100的答案质量分量纲不同；
- 因此召回和额外文档主要作为诊断指标。

注意区分：

- **Completeness 指标**：所有题都计算答案事实覆盖程度；
- **Completeness 题型**：十类题型中的一种，共20题。

官方榜单对同一数据版本使用固定初始 gold set，不追溯重评。为了与榜单接近，本地评测应使用 `--no-correction`。

---

## 6. RAG运行和答案提交格式

每题输出一行 JSONL：

```json
{"question_id":"qst_0001","answer":"...","document_ids":["dsid_abc","dsid_def"]}
```

要求：

- 文件不是 JSON 数组；
- 每行是一个独立 JSON 对象；
- 正好覆盖500个不同 `question_id`；
- `document_ids` 使用父文档 `dsid`；
- 同题去重，最多10个；
- 保留真正用于最终回答的证据，不是初始候选；
- `info_not_found` 应明确拒答，不能编造。

建议先跑10题冒烟，再跑500题。

此前核实的官方评测命令口径：

```powershell
$env:LLM_PROVIDER="openai"
$env:LLM_API_KEY="从安全环境读取"
$env:LLM_MODEL_NAME="gpt-5.4"

python -m src.scripts.answer_evaluation.metrics_based_eval `
  --answers-file answer_evaluation/my_rag_answers.jsonl `
  --questions-file questions.jsonl `
  --results-file answer_evaluation/results.json `
  --parallelism 8 `
  --no-correction
```

评测远不止500次 LLM 调用：每题还会进行整体正确性判断、逐 `answer_fact` 判断以及其他处理。

---

## 7. 排行榜提交方式

当前没有自助上传入口。官方说明是通过邮件联系：

```text
joachim@onyx.app
```

开放源代码系统需要提供复现指南、脚本或 Notebook；闭源系统需要提供官方可访问的 Sandbox 或 API Endpoint，以便复测。

建议提交材料：

- `answers.jsonl`；
- `results.json`；
- 数据集版本；
- 代码版本/Commit；
- 文档预处理和切块配置；
- Embedding、检索、重排序和生成模型；
- Top-K 和提示词；
- Judge 模型版本；
- 延迟与成本；
- 完整复现说明。

榜单主要展示系统/产品名，而不是个人姓名。个人并没有被规则排除，可以用项目名并标注 Independent。知名框架较多主要因为榜单早期以维护者基线测试为主，同时全量评测成本、人工复核和复现要求形成了门槛。

---

## 8. 当前本地项目进度

工作区已有自研流水线：

```text
src/indexer.py
src/embedder.py
src/retriever.py
src/generator.py
src/evaluator.py
src/pipeline.py
configs/*.yaml
run_*.bat / run_*.ps1
```

已有输出：

| 实验 | 题数 | 简单 Document Recall | 平均额外文档 |
|---|---:|---:|---:|
| baseline_bm25 | 60 | 58.2% | 8.7 |
| baseline_dense | 60 | 45.9% | 8.9 |
| baseline_hybrid | 60 | 61.8% | 8.7 |
| baseline_full（旧结果，不可信） | 500 | 16.1% | 8.8 |

重要说明：

- `source_filter: ["github"]` 的当前实现是“问题涉及 GitHub 即选入”，所以得到60题，不是严格的39道 GitHub-only；
- 其中一些题还需要其他来源，因此这三组分数只能作为流水线验证；
- 没有发现官方 `results.json`，所以尚未获得官方 Correctness、Completeness 和主分；
- 旧 `baseline_full` 不能视为完整语料的正式结果。

### 当前阶段判断

| 工作项 | 状态 |
|---|---|
| 数据集调研 | 已完成 |
| 文档和题型统计 | 已完成 |
| 子集检索/生成流水线 | 已跑通 |
| 全量语料索引 | 未完成 |
| 可信全量500题生成 | 未完成 |
| 官方 GPT-5.4 评测 | 未完成 |
| 排行榜提交 | 未开始 |

---

## 9. 全量索引失败的根因

失败文件：

```text
dsid_bc8604e62eec448d9a9c1b07eb003975__safety-onboard-edge-stressor-corpus-v1.txt
```

Windows Defender 日志显示：

```text
检测名称：Backdoor:PHP/Perhetshell.B!dha
动作：隔离
时间：2026-07-24 18:06
```

实际过程：

1. `Path.rglob()` 枚举到文件；
2. Python 准备读取；
3. Defender 在读取时隔离文件；
4. `read_text()` 抛出 `OSError: [Errno 22] Invalid argument`；
5. `indexer.py` 未捕获异常，整个任务退出。

当前本地文档总数为511,961，比官方少1篇。该 `dsid` 没有出现在核心500题或额外100题的 `expected_doc_ids` 中，因此当前评测可安全跳过，不建议在宿主机恢复被识别为严重威胁的文件。

失败时日志大约读取了15.5万文档和38.8万 chunks，但当前代码到全部索引完成后才保存缓存，所以：

```text
可复用文档加载进度：0
已生成向量：0
```

这次实际上失败在“读取和切块”，还没有进入 Embedding。

---

## 10. 当前索引架构存在的问题

当前顺序：

```text
读取全部文档到内存
→ 保存所有Chunk对象
→ 对所有Chunk进行BM25分词
→ 一次性建立全部待Embedding文本列表
→ 一次性生成完整向量矩阵
→ 添加到FAISS
→ 最后保存缓存
```

主要问题：

1. 单个异常文件导致整个任务终止；
2. 全部 chunks 和文本长期驻留内存；
3. `rank_bm25` 为全部文本构建 Python token 列表，内存开销大；
4. Embedding 一次性返回完整 NumPy 矩阵；
5. 失败后不能从文档、分片或批次恢复；
6. 缓存只检查 `_meta.json` 是否存在，不验证语料、模型和切块配置；
7. 全量缓存实际在 `corpus\.index_cache`，但 `run_full.bat` 删除的是项目根目录 `.index_cache`；
8. `configs/full.yaml` 设置 `overwrite_index: true`，成功后再次运行也会重建；
9. 当前 Hybrid 的 Min-Max 分数融合对百万级数据不够稳，建议换 RRF；
10. 本地 `evaluator.py` 使用 `--output-dir` 调用评测器，与已核实的官方 `--results-file` 口径不一致。

按现有日志估计，全量可能超过100万个 chunks。384维 float32 向量本身约需1.5～2 GB，但 Python 文本、BM25 token、对象和重复矩阵可能将总内存推到数十 GB。

---

## 11. 已确定的新索引架构

不应继续使用“一次性全内存构建”。改造为：

```text
原始文档
→ manifest
→ chunk shards
→ embedding shards / 增量upsert
→ 持久化关键词与向量索引
→ 检索和生成
```

### Manifest

建议 SQLite 或 Parquet，记录：

```text
doc_id
source_type
file_path
file_size
mtime
content_hash
status
error_message
```

状态：

```text
pending / chunked / embedded / indexed / failed / skipped
```

### Chunk分片

- 每个 shard 约20,000～50,000 chunks；
- Embedding batch 约128～512；
- 向量库 upsert batch 约500～2,000；
- Chunk ID 必须确定性生成，例如：

```text
{doc_id}__{chunker_version}__chunk0001
```

每个 shard 完成后原子保存并写 checkpoint。中断后只重做最后未完成的 shard。

### 配置指纹

缓存必须包含：

```text
dataset fingerprint
chunker version
embedding model + revision
vector dimension
normalization setting
source preprocessing version
```

任何关键配置变化，都应建立新索引，不能错误复用旧缓存。

---

## 12. GPU计划

GPU主要加速：

- Dense Embedding；
- Cross-Encoder Reranker；
- 可选的本地答案生成。

GPU不能解决：

- 51万小文件读取；
- 文本切块；
- Defender隔离；
- Python版 BM25 内存；
- 缓存和断点恢复。

当前 `full.yaml` 使用 FastEmbed，项目实现偏 CPU，`device: cpu` 对该实现没有实际 GPU 切换效果。

GPU服务器第一版建议使用：

```yaml
embedding:
  provider: "sentence_transformers"
  model_name: "BAAI/bge-small-en-v1.5"
  device: "cuda"
  batch_size: 256
```

先取10,000个代表性 chunks 测试：

- chunks/s；
- 显存峰值；
- GPU利用率；
- 最大稳定 batch；
- 中断恢复；
- 全量预计时间。

多GPU可按 shard 分配，每张卡独立处理确定性分片。

---

## 13. 切块和父子检索方案

由于文档中位数约4.3KB，大部分文档并不长，不应全部机械切成大量碎片。

推荐通用 V1：

| 文档长度 | 处理方式 |
|---|---|
| ≤800 tokens | 整篇同时作为 child 和 parent |
| 800～2,400 tokens | 320～384 token child，64 overlap；整篇作为 parent |
| >2,400 tokens | 按章节生成1,200～1,800 token parent，再切320～384 token child |

使用模型 tokenizer 计算 token，不再使用简单 `text.split()`。

检索和生成关系：

```text
Child：用于BM25和Embedding召回
Parent：用于重排序后扩展上下文
dsid：用于官方document_ids提交
```

每个 child 前保留可检索元数据：

```text
Source
Title/Subject
Date
Section
Content
```

不能加入 `question_type`、`source_types` 等答案侧信息。

数据源适配：

| 来源 | 切块方式 |
|---|---|
| Jira / Linear / HubSpot | 短结构化记录尽量整篇；字段不能拆散 |
| Gmail | 按邮件线程和回复边界；保留 Subject/From/To/Date |
| Slack | 按连续对话窗口；保留频道、发言人和时间 |
| Fireflies | 按议题或连续发言；保留发言人和时间戳 |
| Confluence / Drive | 按标题和章节；表格不从中间切断 |
| GitHub | 按PR描述、review、代码块；不截断代码围栏 |

检索时限制每个 `doc_id` 最多保留若干 child，防止一个长文档占满 Top-K。

---

## 14. 推荐检索架构

该数据集企业名、工单号、哈希、日期和内部缩写很多。官方基线中 BM25 也明显强于纯向量，因此推荐 Hybrid：

```text
BM25 Top 100
+ Dense Top 100
→ RRF融合
→ 按doc_id控制重复child
→ Rerank Top 30～50
→ 父文档/邻近chunk扩展
→ 最终5～10个父文档
→ LLM生成答案
```

Basic 主要依赖精确事实和关键词；Semantic 主要依赖语义召回；Intra-document 需要命中 child 后扩展同一父文档或相邻 chunks。

第一阶段应优先优化 Basic + Semantic，因为占总题量60%。

---

## 15. 免费Embedding模型选型

Ollama 是模型运行服务，不是 Embedding 模型本身。BGE、E5、GTE、Nomic 等都可以直接通过 SentenceTransformers 在 GPU 上运行。

当前建议候选：

| 模型 | 维度 | 许可证 | 用途 |
|---|---:|---|---|
| `all-MiniLM-L6-v2` | 384 | Apache 2.0 | 极轻量速度基线 |
| `bge-small-en-v1.5` | 384 | MIT | 首个全量基线 |
| `bge-base-en-v1.5` | 768 | MIT | GPU质量平衡候选 |
| `e5-base-v2` | 768 | MIT | 不同模型路线A/B |
| `gte-base` | 768 | MIT | 英文通用检索A/B |
| `nomic-embed-text-v1.5` | 可截断 | Apache 2.0 | 长上下文/可变维度 |
| `mxbai-embed-large-v1` | 可截断 | Apache 2.0 | 更高质量但更慢 |

`bge-small-en-v1.5` 本身就是英文模型，不会因为 BAAI 是中国机构而影响英语适用性。

不同模型必须使用正确前缀：

```text
E5：query: / passage:
Nomic：search_query: / search_document:
Mixedbread查询：Represent this sentence for searching relevant passages:
```

首轮只建议比较：

1. `bge-small-en-v1.5`；
2. `bge-base-en-v1.5`；
3. `e5-base-v2`。

固定切块和检索参数，以 Recall@5、Recall@10、MRR、Basic/Semantic Recall、索引大小和速度决定模型。

---

## 16. Elasticsearch / OpenSearch 决策

对本项目，Elasticsearch 或 OpenSearch 比内存版 `rank_bm25 + FAISS` 更适合，原因：

- 持久化索引；
- Bulk 增量写入；
- `_id` 幂等 upsert；
- 原生 BM25；
- `dense_vector` / kNN；
- 元数据过滤；
- RRF Hybrid；
- 分片、复制、恢复和监控。

推荐两个索引：

### `rag_documents`

```json
{
  "doc_id": "dsid_xxx",
  "source_type": "gmail",
  "path": "...",
  "title": "...",
  "full_text": "..."
}
```

### `rag_chunks`

```json
{
  "chunk_id": "dsid_xxx__v1__chunk0001",
  "doc_id": "dsid_xxx",
  "source_type": "gmail",
  "title": "...",
  "text": "...",
  "chunk_index": 1,
  "embedding": [0.1, 0.2]
}
```

推荐由 GPU SentenceTransformers 生成向量，然后通过 Bulk API 写入 ES/OpenSearch。不要第一版就依赖数据库内部模型推理。

### Elasticsearch许可证

- 自建默认 Basic License 不过期；
- 当前功能表包含 Vector Search 和 RRF；
- 默认发行版主要受 Elastic License 2.0 约束；
- 免费部分源码增加了 AGPLv3 选项；
- 内部评测一般可免费使用；
- 商业分发、托管服务和源码修改应让企业法务确认。

### OpenSearch许可证

- 全组件 Apache 2.0；
- 支持 BM25、向量和 Hybrid Search；
- 如果企业要求许可证简单、宽松，优先 OpenSearch。

当前建议：

```text
团队熟悉ES、仅内部评测：Elasticsearch Basic
需要Apache 2.0或准备开源/产品化：OpenSearch
```

---

## 17. 安全问题

此前在多个 `run_*.bat` 中发现明文 DeepSeek API Key。Key 的具体值不得再次输出或记录。

必须：

1. 在服务商控制台撤销旧 Key；
2. 生成新 Key；
3. 删除 `.bat` 中的明文；
4. 从环境变量或 Secret Manager 读取；
5. `.env` 加入 `.gitignore`；
6. 日志禁止打印 Key；
7. 对项目目录执行一次 secret scan。

仅删除脚本内容不够，旧 Key 必须在服务商侧失效。

---

## 18. 后续里程碑和验收标准

### M0：安全整改

- 旧 Key 撤销；
- 代码和脚本无明文密钥；
- 缺少环境变量时清晰报错；
- 日志无密钥。

### M1：可恢复数据摄取

- Manifest 统计成功文档511,961；
- 异常文件1个，记录并跳过；
- 手动中断后可恢复；
- 不重复生成 chunks。

### M2：GPU增量向量化

- 10,000 chunks 基准通过；
- 记录吞吐、显存、预计全量时间；
- 中断后从最近批次恢复；
- 向量数与成功 chunks 数一致；
- 重跑不重复写入。

### M3：切块和检索基线

比较：

```text
A：固定512，无父子
B：320/64 + 整篇父文档
C：数据源感知父子切块
```

固定模型和检索参数，比较 Recall@5、Recall@10、MRR、各题型召回、重复父文档数和查询延迟。

### M4：完整生成和官方评测

```text
10题冒烟
→ 50题分层样本
→ 500题生成
→ JSONL校验
→ GPT-5.4官方评测
```

同时报告：

- 官方500题加权主分；
- 十类分题型分数；
- 十类宏平均；
- Document Recall；
- Invalid Extra Documents；
- 索引时间、检索延迟和资源成本。

---

## 19. 下一步建议执行顺序

```text
1. 撤销并更换泄露的API Key
2. 确定 Elasticsearch Basic 或 OpenSearch
3. 将 indexer 拆成 manifest / chunk / embed / index 四阶段
4. 增加异常文件跳过、失败清单和 checkpoint
5. 实现确定性 chunk_id 和幂等 Bulk upsert
6. 实现通用父子切块 V1
7. 在GPU服务器对10,000 chunks压测
8. 用 bge-small-en-v1.5 建立首个全量可恢复索引
9. 接入 BM25 + Dense + RRF + Rerank
10. 抽10题验证检索、父文档映射和生成
11. 跑500题并校验 answers.jsonl
12. 修正并接通官方GPT-5.4评测
13. 冻结首个可信基线
14. 再对 bge-base / E5 和切块方案做A/B测试
15. 整理复现材料并申请排行榜复测
```

当前最高优先级不是 Prompt 优化，而是：

```text
异常不中断
中断可恢复
重复执行不重复入库
模型和切块版本可追踪
密钥不进入代码和日志
```

---

## 20. 已使用的主要参考链接

### EnterpriseRAG-Bench

- GitHub：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench>
- Quickstart：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/main/quickstart.md>
- Methodology：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/main/methodology.md>
- 官方论文：<https://arxiv.org/abs/2605.05253>
- 官方榜单页：<https://onyx.app/enterpriserag-bench>
- Hugging Face Leaderboard：<https://huggingface.co/spaces/onyx-dot-app/EnterpriseRAG-Bench-Leaderboard>

### Embedding模型

- BGE Small English：<https://huggingface.co/BAAI/bge-small-en-v1.5>
- E5 Base v2：<https://huggingface.co/intfloat/e5-base-v2>
- GTE Base：<https://huggingface.co/thenlper/gte-base>
- all-MiniLM-L6-v2：<https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2>
- Nomic Embed v1.5：<https://huggingface.co/nomic-ai/nomic-embed-text-v1.5>
- Mixedbread Embed Large：<https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1>

### Elasticsearch / OpenSearch

- Elasticsearch Vector Search：<https://www.elastic.co/docs/solutions/search/vector>
- Elasticsearch Hybrid Search：<https://www.elastic.co/docs/solutions/search/hybrid-search>
- Elasticsearch许可证FAQ：<https://www.elastic.co/pricing/faq/licensing/>
- Elasticsearch订阅功能：<https://www.elastic.co/subscriptions>
- OpenSearch官方文档：<https://docs.opensearch.org/latest/about/>
- OpenSearch企业检索：<https://opensearch.org/enterprise-search/>

---

## 21. 新对话建议开场提示

可以在新对话中发送：

```text
请完整读取 D:\EnterpriseRAG-Bench\ENTERPRISE_RAG_BENCH_HANDOFF.md，
基于其中的项目现状和已确定技术方案继续工作。
先检查当前代码和配置，不要重复已经完成的数据集调研。
当前优先任务是安全整改，以及将全量索引改造成 manifest、分片切块、GPU增量向量化、持久化索引和断点恢复流程。
```

