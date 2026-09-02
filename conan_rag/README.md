# Conan RAG 独立测试目录

这是从当前主工程完整复制出的 Conan 实验代码快照，包含离线切割、ES 检索、题型路由、PageIndex、生成、评测和测试代码。后续可只修改本目录，不影响正在运行的 BGE 测试。

## 隔离边界

- 代码：使用本目录 `src/`，不导入父目录的 `src/`。
- 配置：只接受本目录 `configs/` 下的配置。
- 输出：写入本目录 `outputs/`。
- PageIndex 缓存：写入本目录 `.pageindex_cache/`。
- Conan ES 索引、语料和问题集：当前通过 `../` 只读复用父目录已有资源，避免复制大体积数据。
- 启动器强制要求 `read_existing_index: true`、`overwrite_index: false`，并检查索引名和实验名包含 `conan` 或 `qwen3`。

这能隔离代码、配置、缓存和答案结果，但不能隔离远程 LLM、Embedding、Reranker、Elasticsearch 服务的并发负载。若比较延迟或吞吐量，不应与 BGE 同时压测；若只比较答案质量，可以并行，但应记录服务负载。

## 运行

在本目录创建虚拟环境并安装依赖：

```powershell
cd D:\EnterpriseRAG-Bench\conan_rag
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

复制 `.env.example` 为 `.env` 并填写环境变量；安全启动器会自动加载它。随后在 `configs/eval_conan_next.yaml` 中重新接入模型 API、ES 地址和数据集。PageIndex 属于外部依赖，还需把 `pageindex.home` 改为新电脑上的 PageIndex 源码目录。先做无网络安全检查：

```powershell
python -m src.conan_runner configs/eval_conan_next.yaml --check
```

确认后运行：

```powershell
.\scripts\run_conan.ps1
```

Linux/macOS 可运行 `bash scripts/run_conan.sh`。

## 新实验约定

1. 复制 `configs/eval_conan_next.yaml`，配置文件必须直接放在 `configs/` 下。
2. 修改 `pipeline.name`，名称中保留 `conan` 或 `qwen3`，以生成独立输出目录。
3. 同时修改 `pageindex.cache_dir`，避免不同实验共用路由缓存。
4. 保持 `pipeline.read_existing_index: true` 和 `pipeline.overwrite_index: false`。确需重建 Conan 索引时，单独建立离线建库配置和新索引名，不要绕过在线启动器。

`history_*.yaml` 是已完成 Conan 轮次的复现实验配置；`eval_pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817.yaml` 是提取时的 R2 配置快照；`eval_conan_next.yaml` 是后续适配入口。

## 迁移到其他电脑

复制整个 `conan_rag/`。如果同时复制语料、问题集和本地 manifest，请按新位置修改配置中的 `corpus_dir`、`questions_file`、`index_dir` 和 `pageindex.manifest_path`；如果连接远程 ES，只需保证 Conan 索引名存在。API 密钥只通过环境变量提供。
