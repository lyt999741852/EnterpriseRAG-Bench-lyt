# 第一版 BGE-small 向量数据库构建信息

> 本文仅记录第一版已经完成并投入测试的 BGE-small 向量数据库，不包含其他向量库或后续模型建设。

## 1. 构建结论

第一版向量库已经完成全量构建，使用 `BAAI/bge-small-en-v1.5`，共处理约 51 万个英文 TXT 文档，最终形成约 92.85 万个 Chunk。

该版本的特点是构建速度快、资源消耗低，适合作为 ES 全库高召回基础，但对长文档深层证据、多跳问题和 Completeness 题型的支持有限。

## 2. 语料规模

| 项目 | 数量 |
|---|---:|
| 原始 TXT 文件 | 约 511,961 个 |
| 去重后文档 | 约 511,957 个 |
| 初始 Chunk 数量 | 约 928,528 个 |
| 重复 `doc_id` 修复后 | 约 928,534 个 |

主要来源系统：

```text
Confluence
Fireflies
GitHub
Gmail
Google Drive
HubSpot
Jira
Linear
Slack
```

## 3. BGE-small 模型配置

```yaml
provider: sentence_transformers
model_name: BAAI/bge-small-en-v1.5
revision: 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
device: cuda
batch_size: 256
dimension: 384
```

### 模型职责

- 将文档 Chunk 转换为 384 维向量；
- 将用户问题转换为查询向量；
- 提供 ES KNN 语义检索能力。

模型不负责生成最终答案、版本判断、冲突判断或官方评分，这些由 Qwen、证据筛选器、PageIndex 和事实核验模块完成。

### 适用性分析

优点：

- 向量维度低，ES 存储压力较小；
- 本地 GPU 推理速度较快；
- 对普通英文技术文档和语义检索适配较好；
- 适合 51 万文档规模的初始检索基线。

局限：

- 复杂 Semantic 题的语义理解能力有限；
- 对版本号、数字、代码和 URL 的精确处理有限；
- 长文档中的深层证据不一定能直接召回；
- 不能单独完成复杂多跳推理。

## 4. 切块策略

```yaml
method: fixed
version: fixed-v2
chunk_size: 512
chunk_overlap: 0
```

实际按照空白符 Token 进行固定长度切分，不是严格按照模型子词 Token 进行切分。

### 优点

- 实现简单；
- 构建速度快；
- 普通英文 TXT 文档切块较均匀；
- 大部分 Chunk 能接近 BGE-small 的输入窗口；
- 没有重叠文本，向量库规模相对可控。

### 已知问题

- 空白符 Token 数和模型实际子词 Token 数不完全一致；
- 代码、URL 和长单词密集文本可能超过模型真实窗口；
- 超长文本可能在模型端被截断；
- `overlap=0` 可能使一个完整事实被拆到两个 Chunk；
- 长文档的背景、决策和最终应用记录可能被分散。

这些问题是后续 Semantic、Project 和 Completeness 题型召回不足的底层原因之一。

## 5. ES 向量库配置

```yaml
url: http://127.0.0.1:9200
index_name: enterprise-rag-bge-small-v1
alias_name: enterprise-rag-bge-small
bulk_size: 256
request_timeout: 180
```

```text
ES 版本：8.19.12
Shard：1
Replica：0
refresh_interval：30s
向量相似度：cosine
向量索引：int8_hnsw
m：16
ef_construction：100
```

主要字段：

```text
chunk_id        keyword
doc_id          keyword
source_type     keyword
text            text
chunk_index     integer
char_start      integer
char_end        integer
embedding_model keyword
embedding       dense_vector(384)
```

## 6. 构建批处理与恢复能力

```text
Embedding batch：256
ES bulk batch：256
```

写入过程使用确定性 `chunk_id`，具有以下能力：

- 已存在的 Chunk 自动跳过；
- 中断后可以继续写入；
- 每批次更新进度；
- 重复执行不会重复创建相同 Chunk；
- ES 已写入的数据不会因进程停止自动丢失。

## 7. 构建耗时

### Canary 测试

```text
处理 Chunk：14,335
实际写入：10,000
耗时：40.217 秒
平均速度：248.65 Chunk/s
```

相同任务再次执行时，由于 Chunk 已存在，耗时约 0.598 秒。

### 全量构建

```text
初始已有 Canary：10,000 Chunk
新增写入：约 918,528 Chunk
写入失败：0
ES 实际索引耗时：3533.992 秒
```

换算为：

```text
ES 写入耗时：约 58 分 54 秒
全流程墙钟时间：约 1 小时 3 分 54 秒
平均新增写入速度：约 259.91 Chunk/s
```

全流程时间包含模型加载、语料扫描、切块、Embedding、ES 写入和刷新等步骤，因此比单独统计的 ES 写入时间更长。

之后进行了少量重复 `doc_id` 修复，最终索引规模约为 928,534 个 Chunk。

## 8. 第一版向量库的定位

第一版向量库适合作为：

```text
ES 全库高召回基础
```

不适合单独承担：

```text
长文档深层证据定位
复杂多跳推理
跨文档完整性统计
版本冲突判断
最终答案事实审计
```

实际 RAG 架构需要配合：

```text
BM25 + BGE KNN
    ↓
RRF 融合
    ↓
PageIndex 文档树导航
    ↓
证据筛选
    ↓
Qwen 生成
    ↓
事实核验与最终审计
```

## 9. 后续分析时需要记住的关键点

1. 第一版使用的是服务器本地 GPU 上的 BGE-small，不是远程 Embedding API。
2. BGE-small 向量维度为 384，已有 ES 向量必须使用同一模型空间查询。
3. 当前切块为 512、无 overlap，速度快但对长文档和跨段证据不够理想。
4. 全量构建实际约 58 分 54 秒，整体墙钟时间约 1 小时 3 分 54 秒。
5. 已写入 ES 的 Chunk 使用确定性 ID，可支持中断后的幂等恢复。
6. 如果迁移测试服务器，不需要重新构建该向量库，只要新服务器能够访问 ES，并使用相同的 BGE-small 模型即可。
7. 如果迁移 PageIndex，还需要复制原始 TXT、manifest 和 PageIndex 缓存。

