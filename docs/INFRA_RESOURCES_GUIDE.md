# 内网资源架构与地址解读指南

> 建立日期：2026-08-06
> 用途：理解公司内网（10.72.x.x）资源部署方式，快速识别各类服务地址，记录当前项目可用资源与归属。
> 维护者：EnterpriseRAG-Bench 项目

---

## 一、IP 网段解读

公司内网使用私有地址 `10.72.x.x`（RFC 1918），第三段划分不同区域/资源池：

| 网段 | 承载内容（项目实测） | 备注 |
|---|---|---|
| `10.72.55.x` | K8s 集群节点、模型 API（embedding/rerank） | AI 算力/平台区 |
| `10.72.100.x` | GPU 服务器、LLM API | 应用/GPU 服务器区 |
| `10.244.x.x` | K8s Pod 内部 IP | 外部不可达，随时漂移 |
| `172.16.x.x` | 虚拟机/内部转发网络 | 如 100.29:31920 转发的 ES |

不同网段之间通过公司内部路由互通，本机（办公网）可直接访问。

## 二、端口号分类

### 1. 标准服务端口（全球通用）
| 端口 | 服务 |
|---|---|
| 22 | SSH 远程登录 |
| 9200 / 9300 | Elasticsearch（HTTP / 节点间通信） |
| 19530 / 9091 | Milvus（gRPC / REST） |
| 5432 / 6379 | PostgreSQL / Redis |
| 6443 | K8s API server（标准） |

### 2. 应用自定义端口（8000-9999）
| 端口 | 服务 |
|---|---|
| 7777 | LLM API（vLLM） |
| 7992 / 7993 | Rerank / Embedding API（vLLM） |

### 3. K8s NodePort（30000-32767）—— 看到 3xxxx 端口基本可断定是 K8s 服务入口
| 地址 | 实际服务 |
|---|---|
| `10.72.55.201:6443` | K8s API server |
| `10.72.55.201:31070` | kubernetes-dashboard |
| `10.72.55.201:31920` | janusgraph 项目的 ES（7.14） |
| `10.72.55.201:30182` | janusgraph |
| `10.72.55.201:30942` | Cassandra |
| `10.72.55.201:31090` | Prometheus |

### NodePort 访问链路
```
你的电脑 → 节点IP:3xxxx(NodePort) → 集群内 Service → Pod(10.244.x.x:port)
```
NodePort 是稳定入口，Pod IP 会漂移。

## 三、当前项目资源清单

### 模型 API（单机 vLLM 部署，均实测可用）
| 服务 | 地址 | 模型 | 密钥方式 | 关键限制 |
|---|---|---|---|---|
| Embedding | `http://10.72.55.209:7993/v1` | Conan-embedding-v1 | 环境变量 `EMBEDDING_API_KEY=123456` | 1792 维；输入 ≤512 tokens（建议 ≤448） |
| Rerank | `http://10.72.55.209:7992` | bge-reranker-v2-m3 | 同上 | `POST /v1/rerank`；代码未接入（需开发） |
| LLM | `http://10.72.100.35:7777/v1` | lark = Qwen3.5-27B-AWQ | 环境变量 `LARK_API_KEY=lark` | max_model_len 80000；建议输出 max_tokens 4096~8192 |

### Elasticsearch（我们的项目库）
| 项 | 值 |
|---|---|
| 位置 | GPU 服务器 10.72.100.29 的 Docker 容器（enterprise-rag-es） |
| 版本 | 8.19.12 |
| 地址 | `http://127.0.0.1:9200`（仅本机 loopback，外部需 SSH 隧道：`ssh -L 9200:127.0.0.1:9200 root@10.72.100.29`） |
| 数据目录 | `/opt/enterprise-rag-es/data` |
| 索引 | `enterprise-rag-bge-small-v1`（384 维，旧）、`enterprise-rag-qwen3-emb-v1`（1792 维，2 万条，构建中断） |
| 兼容性 | ✅ 支持现有代码 `knn` 检索 API |

### K8s 集群
| 项 | 值 |
|---|---|
| API server | `https://10.72.55.201:6443`（v1.23.17，**匿名可读**：GET /api/v1/namespaces 免认证） |
| Dashboard | `https://10.72.55.201:31070`（证书警告页键入 `thisisunsafe` 绕过） |
| 已部署 | Milvus（milvus-release，19530/9091，仅 ClusterIP 外部不可达）、ECK operator（可声明式建 ES 8.x）、MinIO、Pulsar 等 |

### 其他 ES 实例（不可复用）
| 地址 | 版本 | 归属 | 不可用原因 |
|---|---|---|---|
| `10.72.55.201:31920` | 7.14.0 | janusgraph 项目 | 版本不支持 knn；业务集群 |
| `10.72.100.29:31920` | 7.17.8 | mentor 授权测试（172.16.186.245 虚拟机，9884 个业务索引含 rag-kb） | 版本不支持 knn（仅 script_score 暴力检索，225 万条不可行）；存储/查询受限 |

## 四、版本兼容性红线（重要）

现有 `src/elasticsearch_backend.py` 的 dense 检索使用 `knn` 查询参数，**仅 ES 8.0+ 支持**：

| ES 版本 | 兼容 knn API | int8 量化 | 结论 |
|---|---|---|---|
| 8.12+ | ✅ | ✅（int8_hnsw） | ✅ 推荐 |
| 8.0~8.11 | ✅ | ❌ | ✅ 可用 |
| 7.x | ❌ | ❌ | ❌ 不可用（数据可存、检索跑不了） |

## 五、向量库选型决策记录（2026-08-06）

1. `10.72.55.201:31920`（K8s janusgraph ES 7.14）→ **排除**（版本 + 他人业务）
2. `10.72.100.29:31920`（mentor 授权 ES 7.17.8）→ **暂缓**（knn 不兼容；仅适合 ≤10 万条小规模 script_score 测试）
3. `10.72.55.201:31920` 正在升级（mentor：55.201 升级中）→ **待确认升级后版本**，若为 8.x 则全量重建首选
4. 服务器 8.19.12（9200）→ **可用**（代码零改动）
5. 本机部署 ES 8.19（Docker Desktop）→ **推荐开发路径**（全流程本机化：切块 → Conan API 向量化 → 本机 ES → 评测）

## 六、快速判断技巧

| 看到 | 判断 |
|---|---|
| 3xxxx 端口 | K8s NodePort，集群内服务 |
| 22 / 9200 等标准端口 | 单机/容器直跑 |
| 10.244.x.x | K8s Pod，外部不可达 |
| 172.16.x.x | 虚拟机/内部网络 |
| 6443 | K8s API server |
| 健康接口（`/`、`/v1/models`、`/_cluster/health`） | 反查服务身份与版本 |
