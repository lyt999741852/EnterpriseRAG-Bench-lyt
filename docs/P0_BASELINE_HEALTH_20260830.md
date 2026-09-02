# P0：当前主线基线与资源健康确认

日期：2026-08-30  
范围：保持当前 EnterpriseRAG 语料、BGE-small 384 维索引、现有 RAG 配置和 DPV4，不启动新 embedding、不停止 vLLM。

## 检查结果

| 项目 | 结果 | 判断 |
|---|---|---|
| 主线 Elasticsearch | `127.0.0.1:9200`，cluster `yellow`；4 个主分片全部 active，1 个副本未分配 | 单节点副本状态，不影响只读检索 |
| BGE-small 索引 | `enterprise-rag-bge-small-v1` count **928,534** | 索引可读，规模与冻结基线一致 |
| manifest | `.index_cache/full_es_bge_small/manifest.sqlite3` 存在，约 187 MiB | 可复用 |
| remote reranker | 认证后 HTTP 200 | 可用 |
| remote embedding | 认证后 HTTP 200 | 可用；继续用于现有链路 |
| DPV4 当前请求 | running `0`、waiting `0`、KV cache `0` | 检查时刻空闲，但服务仍持有显存 |
| A800 GPU | 4 卡各占用约 77.99 GiB，余量约 3.19 GiB，GPU 利用率 0% | 不适合新增 GPU embedding |
| PageIndex cache | 现有最佳实验 cache 目录存在，约 1064 个文件 | 可复用 |
| AB50 输出目录 | 现有最佳实验输出目录存在 | 未覆盖或清理 |

## 资源决策

1. 不停止 DPV4。当前没有活动请求，但 vLLM 已预留模型和 KV cache 显存；释放 GPU 必须停止/迁移整个 4 卡 Tensor Parallel 服务。
2. 不在 A800 上并行启动 BGE-M3/BGE-large。剩余显存不足以保证加载稳定性，并可能影响后续 DPV4 请求。
3. 不重建 BGE-small 索引，不切换 Conan/BGE-M3 数据层；后续检索实验继续复用当前索引。
4. ES 的 `yellow` 来源是单节点副本未分配，主分片和查询均正常；本轮只读评测可继续。若进入生产写入或重建，再单独处理副本策略。

## P0 结论

P0 **通过（允许进入 P1）**。主线只读评测所需的索引、manifest、远程模型服务和 PageIndex 资产均可用；GPU 资源结论为“保持 DPV4，不新增本地 embedding”。下一步进入 P1：对完整 AB50 做检索漏斗复核，不改变线上行为。

验证脚本：`scripts/remote/_p0_health_20260830b.sh`。
