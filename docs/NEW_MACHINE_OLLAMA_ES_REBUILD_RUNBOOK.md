# EnterpriseRAG-Bench 新电脑构建与测评运行手册

本文用于在另一台具备 GPU、磁盘空间和 Docker 的电脑上快速复现任务：下载数据集，完成文档切块，在本机 Ollama 上批量生成向量，写入本机 Docker Elasticsearch，并进行检索与官方 RAG 测评。

## 1. 数据集与项目地址

官方项目：

- GitHub：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench>
- 最新 Release：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench/releases/latest>
- Hugging Face：<https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench>
- 官方评测代码：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench/tree/main/answer_evaluation>
- 方法说明：<https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/main/methodology.md>

推荐下载内容：

```text
all_documents.zip       全量文档
questions.jsonl          核心 500 题
extra_questions.jsonl    额外 100 题，元数据相关，不计入官方排行榜
```

Release 同时提供按来源切分的压缩包：`<source_type>_slice_<slice_number>.zip`，每个压缩包最多约 5,000 个文档。网络不稳定时优先使用切片包并逐个校验。

示例：

```bash
git clone https://github.com/onyx-dot-app/EnterpriseRAG-Bench.git
cd EnterpriseRAG-Bench

# 方式 A：从 Release 下载全量包
gh release download --repo onyx-dot-app/EnterpriseRAG-Bench \
  --pattern 'all_documents.zip'
unzip all_documents.zip -d corpus

# 方式 B：从 Hugging Face 下载数据集
# 具体文件名以数据集页面当前版本为准
huggingface-cli download onyx-dot-app/EnterpriseRAG-Bench \
  --repo-type dataset --local-dir data/official
```

如果新电脑不能使用 `gh` 或 `huggingface-cli`，直接在浏览器打开 Release 页面下载即可。不要把数据集放进 Git；仓库默认忽略大型压缩包。

## 2. 数据集信息

官方数据集模拟公司 “Redwood Inference”，用于企业内部知识检索和 RAG 评估。官方描述约有 50 万文档、500 个核心问题，包含企业场景中的近重复、过期信息、错误归档和互相冲突的信息。

主要来源及大致规模：

| 来源 | 约文档数 | 内容 |
|---|---:|---|
| Slack | 275,000 | 内部频道和团队讨论 |
| Gmail | 120,000 | 管理、销售、领导和个人邮件线程 |
| Linear | 35,000 | 工程、产品和设计项目任务 |
| Google Drive | 25,000 | 共享文件和协作文档 |
| HubSpot | 15,000 | 销售 CRM 记录 |
| Fireflies | 10,000 | 会议转录 |
| GitHub | 8,000 | Pull Request 和评论 |
| Jira | 6,000 | 支持工单 |
| Confluence | 5,000 | Wiki、运行手册和结构化文档 |

本项目当前实际使用的清洗后语料约为：

```text
原始 TXT 文档：约 511,961
去重/修正后文档：约 511,957
当前 448+32 切块缓存：1,075,100 个原始 chunk
```

解压后应检查：

```bash
find corpus/all_documents -type f | wc -l
du -sh corpus/all_documents
wc -l questions.jsonl
```

## 3. 任务目标

目标不是只生成向量，而是建立一个可复现的本地 RAG 基线：

```text
TXT 文档
  -> 固定规则切块
  -> Ollama embedding
  -> Docker Elasticsearch
  -> BM25 + Dense + RRF 混合检索
  -> 可选 PageIndex / 证据选择
  -> LLM 生成答案
  -> 官方评测
```

至少需要保存以下信息，以保证文本、向量和原文可对齐：

```text
_id / chunk_id
doc_id
source_type
text
chunk_index
char_start
char_end
embedding_model
embedding
```

同一索引内不能混用不同 embedding 模型。更换 Ollama 模型或模型版本时，必须创建新索引，并让查询侧使用同一模型。

## 4. 新电脑的推荐资源布局

建议目录：

```text
EnterpriseRAG-Bench/
├── corpus/all_documents/       原始 TXT
├── .index_cache/               manifest、chunks、checkpoint
├── deploy/elasticsearch/       Docker ES 编排
├── models/                     可选本地模型缓存
└── outputs/                    日志和评测结果
```

建议至少预留：

```text
数据集和切块缓存：10 GB+
Ollama 模型：5–10 GB+
ES 数据：建议 300 GB 以上
ES heap：8–16 GB，按机器内存调整
```

1792 维向量会显著增加 ES 存储量；如果使用 768/1024 维模型，存储和索引压力会下降，但检索空间已经改变，必须独立评测。

## 5. Docker Elasticsearch

仓库已有：`deploy/elasticsearch/docker-compose.yml`。新电脑启动：

```bash
cd EnterpriseRAG-Bench/deploy/elasticsearch
docker compose up -d
curl http://127.0.0.1:9200/_cluster/health
```

当前 compose 使用 Elasticsearch 8.x 单节点和 named volume。全量任务建议将数据目录显式绑定到容量充足的磁盘，并根据机器内存调整：

```yaml
environment:
  - discovery.type=single-node
  - xpack.security.enabled=false
  - ES_JAVA_OPTS=-Xms8g -Xmx8g
volumes:
  - /srv/enterprise-rag-es/data:/usr/share/elasticsearch/data
```

Linux 主机还应检查：

```bash
sudo sysctl -w vm.max_map_count=262144
```

本机 ES 8.x 可使用 `dense_vector` 原生 KNN。若改用 ES 7.x，当前代码需要使用 `script_score + cosineSimilarity`，不能直接照搬 KNN 查询。

## 6. Ollama 模型选择

推荐先测试：

```text
qwen3-embedding:4b   多语言、代码和企业检索的平衡方案
```

可选对照：

```text
qwen3-embedding:0.6b  更快、更省显存，效果需要验证
qwen3-embedding:8b    更重，可能有更好的语义效果，但吞吐更低
bge-m3                 多语言方案，适合独立对照索引
nomic-embed-text       轻量、速度快，适合快速基线
```

官方 Ollama 模型页面：

- <https://ollama.com/library/qwen3-embedding>
- <https://ollama.com/library/bge-m3>
- <https://ollama.com/library/nomic-embed-text>

GPU 电脑上的安装方式：

```bash
ollama pull qwen3-embedding:4b
OLLAMA_MODELS=/srv/ollama/models ollama serve
curl http://127.0.0.1:11434/api/tags
```

如果需要固定使用某一张 GPU，应通过服务管理器或启动环境设置 GPU 可见性；不要抢占已有在线推理服务的 GPU。

先做单条和 batch 冒烟：

```bash
curl http://127.0.0.1:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-embedding:4b","input":["hello","enterprise retrieval test"]}'
```

记录返回向量维度。配置使用 `dimension: 0` 自动探测，不要凭模型名称硬编码维度。

## 7. 切块策略

### 推荐首版

为了和当前实验可比，首版使用：

```yaml
chunking:
  method: fixed
  version: ollama-qwen3-448-32-v1
  chunk_size: 448
  chunk_overlap: 32
```

Ollama 本地 embedding 不受当前 Conan 的 512-token 总请求限制，因此可以使用真正的 batch，不需要“单条请求 + 8 并发”这种补救策略。

### 可选对照

如果首版希望减少 chunk 数，可以额外测试：

```text
512+32
512+0
448+32
```

每个模型/切块组合必须使用独立索引。例如：

```text
enterprise-rag-ollama-qwen3-4b-448-32-v1
enterprise-rag-ollama-qwen3-4b-512-32-v1
```

不要覆盖已有索引，也不要把不同模型的向量写到同一 index。

## 8. 推荐配置模板

创建 `configs/rebuild_ollama_qwen3_4b.yaml`：

```yaml
corpus_dir: "corpus/all_documents"
questions_file: "questions.jsonl"
output_dir: "outputs"
index_dir: ".index_cache/ollama_qwen3_4b_448_32"
index_backend: "elasticsearch"

chunking:
  method: "fixed"
  version: "ollama-qwen3-448-32-v1"
  manifest_enabled: true
  chunk_size: 448
  chunk_overlap: 32

embedding:
  provider: "ollama"
  model_name: "qwen3-embedding:4b"
  api_base: "http://127.0.0.1:11434"
  device: "cuda"
  batch_size: 32
  dimension: 0

elasticsearch:
  url: "http://127.0.0.1:9200"
  index_name: "enterprise-rag-ollama-qwen3-4b-448-32-v1"
  alias_name: "enterprise-rag-ollama-qwen3-4b"
  bulk_size: 512
  request_timeout: 180
  shards: 8
  replicas: 0
  dense_mode: "knn"
  embedding_concurrency: 1
  embedding_group_size: 32
  embedding_request_batch_size: 32

pipeline:
  name: "ollama_qwen3_4b_448_32"
  overwrite_index: false
  resume: true
```

说明：Ollama backend 使用 `/api/embed` 批量提交；`batch_size` 从 32 开始，确认显存和吞吐后再测试 64/128。不要一开始同时叠加多进程和大 batch，避免 GPU 内存抖动。

## 9. 构建步骤

先做小样本：

```bash
python -m unittest discover -s tests -v
python -m src.build_es_index configs/rebuild_ollama_qwen3_4b.yaml
```

正式构建前建议把配置中的 `pipeline.max_index_chunks` 临时设为 1,000 或 10,000，确认：

1. Ollama 返回向量维度稳定；
2. ES mapping 的 `embedding.dims` 正确；
3. `text`、`chunk_id`、`doc_id` 和向量一一对应；
4. ES `_count` 增长；
5. 10–100 个问题的 Recall@30 没有异常；
6. 进程中断后 checkpoint 能继续。

确认后删除测试索引或换用新的正式索引名，再去掉 `max_index_chunks`：

```bash
nohup python -u -m src.build_es_index \
  configs/rebuild_ollama_qwen3_4b.yaml \
  > outputs/build_ollama_qwen3_4b.log 2>&1 &
```

监控：

```bash
tail -f outputs/build_ollama_qwen3_4b.log
cat .index_cache/ollama_qwen3_4b_448_32/es_build_progress.json
curl http://127.0.0.1:9200/enterprise-rag-ollama-qwen3-4b-448-32-v1/_count
```

## 10. 测评规则

核心 `questions.jsonl` 有 500 题，官方分为 10 类：

| 类型 | 数量 | 主要考察 |
|---|---:|---|
| Basic | 175 | 单文档直接检索 |
| Semantic | 125 | 低关键词重合的语义检索 |
| Intra-Document Reasoning | 40 | 同一长文档远距离信息组合 |
| Project Related | 40 | 单项目跨文档聚合 |
| Constrained | 30 | 带限定条件的文档筛选 |
| Conflicting Info | 20 | 冲突信息识别和完整回答 |
| Completeness | 20 | 找齐全部相关文档 |
| Miscellaneous | 20 | 非规整、边缘文档检索 |
| High Level | 10 | 语料级综合问题，无单一 gold 文档 |
| Info Not Found | 20 | 正确识别语料中没有答案 |

额外 100 题位于 `extra_questions.jsonl`，依赖元数据，不计入官方核心排行榜。

主要指标：

- `correctness`：答案事实是否正确；
- `completeness`：是否覆盖回答所需信息；
- `document recall`：检索结果命中 gold 文档的比例；
- `invalid extra docs`：引入的无关/错误额外文档；
- `combined_correctness_completeness_score`：官方综合分。

评测注意：问题中的 gold 文档、答案和元数据只能用于离线评估，不能传入检索器或生成器。正式评测使用官方 `metrics_based_eval.py`，保留 `--no-correction`，避免评测器改写金标准。

仓库内 pipeline 的基本入口：

```bash
python -m src.pipeline configs/<evaluation-config>.yaml
```

官方答案评测的核心参数：

```bash
python -m src.scripts.answer_evaluation.metrics_based_eval \
  --answers-file outputs/<run>/answers.jsonl \
  --results-file outputs/<run>/results.json \
  --parallelism 8 \
  --no-correction \
  --resume
```

## 11. 新电脑的验收顺序

按以下顺序推进，任何一步失败都不要直接开始全量构建：

```text
1. 数据集下载、解压、文件数校验
2. Docker ES 启动、健康检查
3. Ollama 模型拉取、/api/tags 检查
4. 单条 embedding 请求，确认维度
5. 100 条文本 batch 性能测试
6. 1,000 条 chunk 小索引
7. 10/50 题 Recall 和 ES 查询测试
8. 正式全量切块、embedding、入库
9. 500 题官方测评
10. 保存配置、模型名、模型 digest、ES mapping 和结果文件
```

最终交付至少保存：

```text
configs/rebuild_ollama_*.yaml
.index_cache/*/meta.json
.index_cache/*/manifest.sqlite3
.index_cache/*/chunks.jsonl
outputs/build_*.log
outputs/*/results.json
ES index mapping
Ollama model name and digest
```

## 12. 与当前 Conan 分支的边界

当前 Conan 分支使用 1792 维向量；新电脑的 Ollama 分支必须使用新索引、新 alias 和新查询模型。推荐命名：

```text
enterprise-rag-ollama-qwen3-4b-448-32-v1
```

只有在召回、官方 correctness/completeness 和稳定性均完成对比后，才考虑把新分支作为主要索引。任何模型切换都不能直接复用旧模型的向量，也不能只比较 embedding 速度而不比较召回。

