# 向量库重构任务交接文档

> 生成日期：2026-08-06
> 用途：新会话执行向量库重构任务的唯一入口。完整实验历史见 `docs/archive/ledgers/OPTIMIZATION_TRACE.md`，基础设施说明见 `docs/INFRA_RESOURCES_GUIDE.md`。
> 背景：RAG 框架已定（ES + PageIndex + 证据选择 + Qwen 生成），多轮测试完成，当前唯一主线任务是**向量库重构**（切块 + 向量化 + 入库 + 检索适配）。

---

## 一、公司资源清单（构建/评测用）

### 模型 API（全部实测可用）
| 服务 | 地址 | 模型 | 密钥（环境变量） | 关键限制 |
|---|---|---|---|---|
| Embedding | `http://10.72.55.209:7993/v1` | Conan-embedding-v1 | `EMBEDDING_API_KEY=123456` | 1792 维；输入 ≤512 tokens（建议 ≤448）；batch 512 |
| LLM | `http://10.72.100.35:7777/v1` | lark = Qwen3.5-27B-AWQ | `LARK_API_KEY=lark` | max_model_len 80000；输出建议 4096~8192；vLLM 支持并发批处理 |
| Rerank | `http://10.72.55.209:7992` | bge-reranker-v2-m3 | 同 embedding | `POST /v1/rerank`；**代码未接入**（暂不开） |

### 向量库
| 库 | 地址 | 版本 | 用途 |
|---|---|---|---|
| **目标库（mentor 杨瑞兴授权）** | `http://10.72.100.29:31920` | **ES 7.17.8** | 重构后的新向量库。K8s NodePort → 172.16.186.245；可用磁盘 7.7TB、heap 12GB；集群已有 9884 个业务索引（janusgraph/rag-kb），**建索引用 `enterprise-rag-*` 前缀，不碰他人索引** |
| 自建库（备用） | 服务器 10.72.100.29 Docker `127.0.0.1:9200`（外部 SSH 隧道） | ES 8.19.12 | 代码零改动可用的兜底方案；如需改用 url + knn 原版 |
| 升级中（等待） | `http://10.72.55.201:31920` | 7.14 → 升级中 | mentor 正在升级；**若升级到 8.x，可切回原生 knn**（保留切换开关） |

### 服务器与集群
| 资源 | 信息 |
|---|---|
| GPU 服务器 | 10.72.100.29（a800server，K8s master 节点；SSH root / XAznv@(2018)），应用目录 `/opt/enterprise-rag-bench/app`，4×80GB GPU 当前被 sentosa 占满、377GB 内存、系统盘剩 160GB |
| K8s 集群 | `https://10.72.55.201:6443`（v1.23.17，匿名可读）；Dashboard `https://10.72.55.201:31070`（证书警告键入 `thisisunsafe`）；集群内另有 Milvus（ClusterIP 不可达）、ECK operator |

## 二、新库构建细节

### 1. 切块策略（fixed-v3，固定切块 + overlap）
- 修正第一版 fixed-v2（512/overlap=0 无边界信息）的问题；Conan 上限 512，**每 chunk ≤448 tokens**（跨 tokenizer 兼容校验）
- 候选参数（阶段 1 用 1000 文档小样本 × 3 组对比后定）：
  - A：384 + 64 overlap（与 hierarchical-v1 同尺寸）
  - B：256 + 32 overlap（更细粒度，chunk 数约 350 万）
  - C：448 + 32 overlap（单块上下文最大，约 200 万 chunks）
- 预期全量规模：约 225~350 万 chunks（取决于参数）

### 2. 向量化
- 走 Conan API（1792 维），`provider: openai_compatible`，`device: cpu`（无 GPU 依赖）
- **吞吐优化（必须先做）**：[elasticsearch_backend.py](file://d:\EnterpriseRAG-Bench\src\elasticsearch_backend.py) 的 `_encode_batch_with_split` 硬编码 `batch_limit = min(bulk_size, 32)` → 提到 **512**；并发 4~8 路 API 请求（可线程池）；目标 200~500 chunks/s，全量 2~4 小时
- 构建位置：本机（切块+向量化均可本机 CPU）或服务器；**写入目标 ES = `http://10.72.100.29:31920`**

### 3. 索引设计（ES 7.17.8 兼容）
- 索引名：`enterprise-rag-fixed-v1`（版本化命名，旧索引不删）
- mapping：`text`(text，BM25) + `dense_vector`(dims=1792, index=true, similarity=cosine) + doc_id/chunk_id/source_type/chunk_index 等元数据（沿用现有 `_metadata_properties`）
- **`number_of_shards: 16~32`**（script_score 全扫靠分片并行提速的关键）、`number_of_replicas: 0`、`refresh_interval: 30s`
- 断点续跑：`es_build_progress.json` 检查点 + 确定性 chunk_id 幂等（现有机制保留）

### 4. 构建命令与配置
- 新建配置 `configs/rebuild_fixed_v3.yaml`（复制 `full_es_qwen3_emb.yaml` 改：chunking 参数、elasticsearch.url、index_name、pipeline.name）
- 本机跑：`python -m src.build_es_index configs/rebuild_fixed_v3.yaml`
- 注意：若目标库不可写（权限/前缀冲突），先与 mentor 确认；备选切 `http://127.0.0.1:9200`（隧道）

## 三、混合检索 KNN 替换（ES 7.17.8 适配）

### 1. 检索 API 替换
- 现状：[dense_search](file://d:\EnterpriseRAG-Bench\src\elasticsearch_backend.py) 使用 `knn` 查询参数（8.0+），**7.17.8 必报错**
- 替换为 `script_score + cosineSimilarity`：

```json
POST /enterprise-rag-fixed-v1/_search
{ "size": 30, "_source": ["chunk_id","doc_id","source_type","text","chunk_index"],
  "query": { "script_score": {
      "query": { "match_all": {} },
      "script": { "source": "cosineSimilarity(params.qv, 'embedding') + 1.0",
                  "params": { "qv": [<1792维向量>] } } } } }
```

- 改动集中在 `dense_search` 一个方法；`bm25_search`、`retrieve_hybrid`（RRF 融合）、`retrieve_bm25` 全部不动
- 建议加配置开关（如 `elasticsearch.dense_mode: script_score|knn`），等 55.201 升级到 8.x 后可一键切回

### 2. 性能预期
- 16~32 分片并行全扫：225 万条 × 1792 维 → **1~3 秒/查询**
- 评测 `evaluation.parallelism: 16` 并发跑题：检索延迟被并发吸收，500 题检索总耗时约 3~5 分钟
- 若实测不可接受 → 退路：两阶段（BM25 粗排 top-500 + script_score 向量精排，毫秒级）

### 3. 检索配置修改点
- `configs/eval_*.yaml`：`elasticsearch.url` → `http://10.72.100.29:31920`；`retrieval` 保持 `hybrid + rrf`
- 评测环境：服务器 base conda + `LLM_PROVIDER=openai LLM_API_BASE=http://10.72.100.35:7777/v1 LLM_API_KEY=lark LLM_MODEL_NAME=lark`

## 四、其他补充

### 1. 任务执行顺序（阶段化，每阶段验证后再进下一阶段）
1. **阶段 1**：fixed-v3 切块实现（参数化）+ 1000 文档小样本 × 3 组参数建小索引，10 题验证 recall（本机即可）
2. **阶段 2**：构建吞吐优化（batch 512 + 并发），代码改完先单测（项目有 tests/test_core.py）
3. **阶段 3**：全量构建到目标库（断点监控 es_build_progress.json）
4. **阶段 4**：50 题分层评测（与 V5.2/P1 基线对比：correctness/completeness/recall/extra docs）
5. **阶段 5**：500 题正式评测（parallelism 16，约 30~40 分钟）
6. 验证通过后淘汰旧索引（`enterprise-rag-qwen3-emb-v1` 当前仅 2 万条，可随时清理）

### 2. 环境与已知坑
- 评测必须用服务器 base conda 环境（embedding_test 无 openai 包会假失败得 0 分）
- PowerShell 下 curl POST JSON 引号转义会坏请求 → 用 python requests
- 服务器 GPU 已满（sentosa 占用），**不要规划本地 GPU 推理**；embedding 走 API
- pageindex：本机跑需从服务器拉 `/opt/enterprise-rag-bench/PageIndex`（或先关 pageindex 纯 ES 评测）；服务器上直接可用
- 语料：本机 `corpus/all_documents`（51 万文档）与服务器副本一致；questions.jsonl 500 题 + extra 50 题
- 目录规范：临时脚本放 `scripts/`，报告放 `docs/`，根目录只留 README/CURRENT_STATUS/OPTIMIZATION_TRACE

### 3. 决策记录（已确认）
- 向量库 = mentor 授权 `10.72.100.29:31920`（ES 7.17.8），构建侧零改动 + 检索 script_score 适配
- embedding = 现有 Conan API（1792 维），不占服务器 GPU
- 切块 = 固定切块 + overlap（参数待小样本定）
- 55.201 升级到 8.x 后：切回 knn，其余不变

### 4. 2026-08-06 决策变更与执行状态（以 CURRENT_STATUS.md 为准）

- **切块参数直接定稿**：448 + 32 overlap（version `hierarchical-v1-448`），**不做阶段 1 三组小样本对比、不做阶段 2 吞吐优化**（用户决策）。
- **目标库 = 31920**（此前实际误写入自建库 127.0.0.1:9200 的 2 万条作废不删）。
- **新索引**：`enterprise-rag-qwen3-emb-v2`，16 shards，1792 维 dense_vector（index=true, cosine）。
- **script_score 适配已完成**（原“待办”）：`ElasticsearchConfig` 新增 `dense_mode: script_score|knn`（默认 knn）与 `shards` 参数；`dense_search` 按模式分支；单测 53/53 通过；冒烟验证 31920 上 script_score 检索正常、原生 knn 报 400。
- **构建方式**：`scripts/start/_run_build_v2_daemon.sh`（setsid 脱离会话 + 自动重启，上限 30 次），日志 `outputs/build_qwen3_emb_v2_20260806.log`。
- 旧的 `_run_q3emb50_automation.sh` 已废弃（它等待的是 v1 索引且目标写自建库）；50 题评测待 v2 完成后用 `eval_pageindex_balanced50_q3emb.yaml`（已指向 v2/31920，`dense_mode: script_score`）另行启动。
