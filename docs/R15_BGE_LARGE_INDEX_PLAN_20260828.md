# R15：BGE-large 全库索引方案与执行状态

## 参数设计

- 模型：`bge-large-en-v1.5`，1024 维，最大输入约 512 tokens。
- chunk：`fixed-v2`，`chunk_size=448`、`chunk_overlap=32`。
  - 448 为模型上限留出特殊 token/长度漂移余量；
  - 32 token overlap 覆盖边界语义，同时避免 64/128 overlap 带来的大幅 chunk 膨胀；
  - 与现有 Conan 448/32 具备可比性，BGE-small 512/0 保持为基线。
- 语料：511,961 个文档，切出 1,075,100 chunks，切块失败 0。
- 目标 ES：`http://10.72.55.201:31920`（ES 7.14.0，3 节点，green）。
- 新索引：`enterprise-rag-bge-large-en-v1-448-32`，8 shards、0 replicas；构建期 `refresh_interval=-1`、异步 translog，完成后恢复 30s/request。

## 加速策略

目标主机 4×A800 被 DPV4 占用，不能抢占。因此采用 CPU 多进程：4 个模型 worker、每个 16 个 Torch/BLAS 线程，每批 128 chunks，每窗口 512 chunks，批量 `_bulk` 写入。线程基准显示单进程 32 线程约 3.12 chunks/s；4×16 实测约 3.6 chunks/s，优于单进程但全库仍约 83 小时。8×8 实测约 4.0 chunks/s，仍约 74 小时，故没有继续长期占用 CPU。

## 当前状态

- 448/32 切块缓存已完整生成：1,075,100 chunks、0 failures。
- 目标 ES 新索引已创建，mapping 为 1024 维 dense_vector，8 shards/0 replicas。
- 已写入 2,048 条向量后暂停；断点文件：
  `.index_cache/full_es_bge_large_en_v1_448_32/parallel_progress.json`。
- 现有 BGE-small、Conan 索引和 DPV4 服务未修改。

## 继续条件

在当前 CPU 资源下继续没有时效性。应提供可用的 BGE-large GPU 推理资源或独立 embedding 服务后，从上述断点续跑；完成后再做真实全库 Recall@30/120/240/1000，未通过 raw-recall 门槛前不启动完整 RAG 50 题。
