# 可迁移 RAG 核心包

这是从当前 EnterpriseRAG-Bench 主链路提取的轻量运行包，保留两部分：

- 离线切割：扫描 `data/corpus/<source_type>/*.txt`，生成 chunk、manifest、BM25，按配置可额外生成 FAISS 向量索引。
- 在线问答：读取 questions JSONL，执行 BM25/Dense/Hybrid 检索、可选本地 rerank、证据裁剪，并调用 OpenAI-compatible `/v1/chat/completions` 生成答案。

## 目录约定

```text
portable_rag/
  configs/config.yaml       # 只改这里的模型、API、数据路径
  data/corpus/<source>/*.txt
  data/questions.jsonl
  data/index_cache/         # 自动生成，可删除后重建
  outputs/<run_name>/
  src/
```

问题集每行至少需要 `question_id` 和 `question`。如果要计算简单文档召回率，可额外提供 `expected_doc_ids`；`source_types` 仅用于筛选。

## 迁移到另一台电脑

1. 复制整个 `portable_rag` 目录，不要复制旧的 `data/index_cache`，除非新机器的模型、切块参数和数据完全一致。
2. 安装 Python 3.10+，进入该目录安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 放入数据：每个来源一个子目录，文件扩展名为 `.txt`；把问题集命名为 `data/questions.jsonl`。
4. 在 `configs/config.yaml` 中重新填写 embedding 和 LLM 的 `api_base`、`model_name`、`api_key_env`。API key 只通过环境变量传入：

   ```powershell
   $env:LLM_API_KEY = "你的聊天模型密钥"
   $env:EMBEDDING_API_KEY = "你的向量模型密钥"
   ```

## 运行

只做离线切割和索引：

```powershell
python -m src.run configs/config.yaml --mode index
```

执行在线问答和简单分析：

```powershell
python -m src.run configs/config.yaml --mode qa
```

首次运行也可以直接执行两步：

```powershell
python -m src.run configs/config.yaml --mode all
```

结果在 `outputs/<pipeline.name>/`：

- `answers.jsonl`：标准答案输出，含 `question_id`、`answer`、`document_ids`。
- `retrieval_trace.jsonl`：每道题的检索 chunk 和分数，便于分析。
- `simple_metrics.json`：使用 `expected_doc_ids` 计算的文档召回和额外文档数。
- `validation.json`：输出格式检查。

## 接入不同模型

- 只想先验证切块和关键词检索：保持 `retrieval.method: bm25`，embedding 配置不会被调用，但 LLM 仍需可用才能回答。
- 使用远程向量 API：设置 `retrieval.method: hybrid` 或 `dense`，`embedding.provider: openai_compatible`，接口需兼容 `POST {api_base}/embeddings`。
- 使用 Ollama：将 embedding provider 改为 `ollama`，例如 `api_base: http://localhost:11434`。
- 使用本地 embedding：改为 `sentence_transformers` 或 `fastembed`，并填写本地/可下载模型名。
- 聊天模型接口需兼容 `POST {api_base}/chat/completions`，返回 `choices[0].message.content`。如果供应商字段不同，修改 `src/llm.py` 的 `OpenAICompatibleClient` 即可。

## 切块策略

`fixed` 是最容易迁移和复现的默认方案，按 whitespace token 窗口切分并保存字符偏移；`hierarchical` 需要本机有 BGE tokenizer 缓存；`langchain_conan_recursive` 还需要 tokenizer API 或本地 tokenizer。修改 `chunk_size`、`chunk_overlap`、切块方法或 embedding 后，建议删除 `data/index_cache`，让 manifest 指纹触发全量重建。

本包有意未携带当前项目的超大语料、索引缓存、Elasticsearch、PageIndex vendor 和官方 judge；这些属于环境/数据层。需要完整 ES/PageIndex 评测时，继续使用上级项目的 `src/pipeline.py` 和对应配置。
