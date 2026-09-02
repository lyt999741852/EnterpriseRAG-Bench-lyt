# R14：BGE-large-en-v1.5 50 题检索筛选

日期：2026-08-28  
目的：在不改变 RAG 路由、rerank、PageIndex 和生成的前提下，检查更强英文 embedding 是否能改善现有 BGE-small 的候选排序。

## 资源与索引

- 模型：`BAAI/bge-large-en-v1.5`，本地目录 `/data06/embedding-models/bge-large-en-v1.5`，1024 维；使用同系列 BGE-small 的 tokenizer 文件离线补齐目录。
- 原 BGE-small：`enterprise-rag-bge-small-v1`，384 维，全库 928,534 chunks。
- 新独立候选索引：`enterprise-rag-bge-large-r14-candidates50-k40`，2,120 chunks，1024 维。
- 题集：沿用固定 50 题；chunking 仍为 fixed-v2、512/0。
- 候选构造：每题取 BGE-small 全库 top-40，再补入该题 `expected_doc_ids` 的全部 chunks，去重后形成候选并集。随后在每题自己的候选子集内分别计算 BGE-small/BGE-large 排名。

## 结果

| 指标（每题候选子集内） | BGE-small | BGE-large | 差值 |
|---|---:|---:|---:|
| Recall@30 | 56%（28/50） | **84%（42/50）** | **+28pp** |
| Recall@120 | 94%（47/50） | 94%（47/50） | 0pp |
| Recall@240 | 94%（47/50） | 94%（47/50） | 0pp |
| Recall@1000 | 94%（47/50） | 94%（47/50） | 0pp |

按题型的 Recall@30：

- semantic：BGE-small 3/12，BGE-large 9/12；
- basic：13/18 → 17/18；
- intra-document reasoning：3/4 → 4/4；
- project_related：2/4 → 3/4；
- completeness：1/2 → 2/2；
- constrained/conflicting_info：本轮均无变化。

## 解释与门槛

该实验说明 BGE-large 在**已进入候选池的文档之间**，尤其是 semantic 题，具有明显的细粒度排序优势；它不能证明 BGE-large 在全库中能找回 BGE-small 未进入 top-40 的文档，因为候选池显式补入了 gold chunks。

曾尝试按相同 512/0 切块构建全库 1024 维索引，预处理已完成 928,534 chunks，但 CPU 编码约 1.8 chunks/s，已停止以避免十几小时的无效占用；仅保留新索引目录中的断点/切块缓存和 256 条试写记录，未触及现有 BGE-small/Conan 索引。

因此本轮不启动完整 RAG 50 题：用户设定的“全库 raw recall 明显超过 BGE-small”门槛尚未被验证。下一步应在可用 GPU/高性能 embedding 服务上完成 BGE-large 全库索引，然后复跑原问题 dense Recall@30/120/240/1000；只有全库结果相对 BGE-small（此前 50%/58%/64%/74%）有明确提升，才进入完整 RAG 50 题。

原始结果：`outputs/r14_bgelarge_candidate50/result_perq_k40.json`（远程应用目录）。
