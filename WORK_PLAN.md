# EnterpriseRAG-Bench 工作计划

> 创建日期: 2026-07-23
> 策略: 先以最小标准跑通全流程 → 再针对数据集和问题风格优化

---

## 一、数据集现状总览

| 维度 | 数值 |
|---|---|
| 完整数据集 | 511,962 份 TXT / 9 数据源 / ~2.47 GB |
| 现有本地数据 | `demo_corpus`: 8052 份(github only) / `slice_inspect`: 5000 份(github only) |
| `questions.jsonl` | **500 题**, 8 种题型, 9 种数据源 |
| `extra_questions.jsonl` | 额外问题集(含 metadata 题型) |

### 问题分布

| 题型 | 数量 | 特征 |
|---|---|---|
| basic | 175 | 短答案, 单文档, 事实匹配 |
| semantic | 125 | 关键词稀疏, 需要语义理解 |
| project_related | 40 | 多文档综合, 较长答案 |
| constrained | 30 | 严格约束(时间/地域/客户), 反幻觉 |
| completeness | 20 | 必须覆盖全部列表项 |
| info_not_found | 20 | 需明确回答"无法回答" |
| high_level | 10 | 无唯一标准文档 |
| miscellaneous | 80 | 办公闲聊等多样化问题 |

### Phase 1 可跑范围

demo_corpus 只有 github 数据, 因此:

| 范围 | 题数 | 说明 |
|---|---|---|
| github-only 问题 | **39 题** | `source_types: ["github"]`, 最干净的子集 |
| 所有含 github 的问题 | **60 题** | 部分是多数据源混合, 文档召回会偏低 |
| 全部 500 题 | 500 题 | 无意义, 非 github 题无法召回标准文档 |

> **Phase 1 建议**: 以 39 题 github-only 子集跑基线, 保证评测结果有意义。

---

## 二、Phase 1: 最小标准跑通全流程

### 目标
用一个最简单的 RAG 管线（固定 chunking + BM25/Embedding + 基础 prompt），对 39 题 github-only 子集，完成「索引 → 检索 → 生成 → 评测」的闭环。

### 2.1 搭建管线框架 — 1 天

```
EnterpriseRAG-Bench/
├── src/
│   ├── indexer.py        # 文档加载、chunking、索引构建
│   ├── retriever.py      # BM25 / Dense / Hybrid 检索
│   ├── generator.py      # LLM 回答生成
│   ├── evaluator.py      # 官方评测脚本封装 & 结果解析
│   └── pipeline.py       # 一键运行入口
├── configs/
│   └── default.yaml      # 管线参数配置
├── outputs/              # 结果 JSONL + 评测报告
├── data/
│   ├── questions.jsonl
│   └── demo_corpus/github/*.txt
└── WORK_PLAN.md
```

**最小化配置:**
- Chunk: 固定 512 tokens, 无 overlap
- Embedding: `all-MiniLM-L6-v2` (22M 参数, 384 维, CPU 可跑)
- LLM: 需确认可用的模型 (API key)

### 2.2 三条基线 — 1~2 天

| # | 基线 | 检索方式 | 验证点 |
|---|---|---|---|
| 1 | **BM25** | rank-bm25 (Python) | 关键词匹配能力 (github PR/代码术语) |
| 2 | **Dense** | FAISS flat index + MiniLM | 语义泛化能力 |
| 3 | **Hybrid+Reranker** | BM25 + Dense 融合 + cross-encoder 重排 | 综合最优 |

每条基线输出:
- `outputs/baseline_{name}/answers.jsonl` — 符合官方格式
- `outputs/baseline_{name}/results.json` — 四项指标分数

### 2.3 Phase 1 交付物清单

- [x] 数据分析完成 (问题覆盖、数据源分布)
- [ ] `run_pipeline.py` — 一键执行脚本
- [ ] BM25 基线评测报告
- [ ] Dense 基线评测报告
- [ ] Hybrid+Reranker 基线评测报告
- [ ] `requirements.txt` 依赖清单

---

## 三、Phase 2: 风格分析与针对性优化

### 3.1 数据集风格分析

9 种数据源的格式特征分析:

| 数据源 | 格式特点 | 潜在优化方向 |
|---|---|---|
| **github** | PR diff + review 评论 + Markdown | 代码块保留语法, 按 diff/review 分段 |
| **confluence** | Wiki 页面, 结构化 | 页面标题 + 更新日期元数据 |
| **gmail** | 邮件线程, 引用嵌套 | 按线程拆分, 保留 From/Date/Subject |
| **fireflies** | 会议转录, 多轮对话 | 按发言人分块, 时间戳对齐 |
| **jira** | 工单字段结构 | 字段解析(priority/status/assignee) |
| **linear** | 类似 Jira, 项目追踪 | 同上 + 项目/里程碑关联 |
| **slack** | 短消息, @提及, 频道 | 按话题聚合, 频道元数据 |
| **google_drive** | 文档/表格/概念草稿 | 文档标题 + 作者元数据 |
| **hubspot** | CRM 客户记录 | 公司名/联系人/交易阶段字段 |

### 3.2 问题风格分析

按题型分类制定策略:

| 题型 | 检索策略 | Prompt 策略 |
|---|---|---|
| basic | 标准检索, top-5 即可 | 简洁指令, 提取事实 |
| semantic | 混合检索更优 | 保留原文用词线索 |
| project_related | top-15 + 多跳检索 | 综合多个文档, 要求连贯 |
| constrained | 先过滤约束再检索 | 逐项验证约束, 禁止推断 |
| completeness | top-15, 全量召回 | 列举式回答, 逐项覆盖 |
| info_not_found | 置信度阈值判断 | 先判断可回答性, 不编造 |
| high_level | 全局/跨文档摘要 | 综合型回答, 不提具体文档 |
| conflicting | 时间感知排序 | 区分旧值/新值, 说明依据 |
| intra_document | 相邻 chunk 扩展 | 查找完整上下文 |
| metadata | 字段级别检索 | 精确匹配元数据字段 |

### 3.3 Phase 2 优化方向

1. **Chunking 分化**: 不同数据源用不同 chunking 策略
2. **元数据注入**: 将文件元数据(数据源类型、日期、作者)注入 chunk, 提升检索精度
3. **Prompt 模板分化**: 10 种题型用 10 套不同的 system prompt
4. **扩展完整数据集**: 解压全部 511,962 份文档, 跑完整 500 题
5. **文档扩展策略**: Intra-document 类问题自动扩展相邻 chunk 到父文档

---

## 四、风险与资源清单

### 需要确认的事项

1. **LLM API**: 用什么模型做回答生成? (GPT-4o / DeepSeek / 本地部署?)
   - 500 题 × 每次生成 ~500 tokens ≈ 25 万 output tokens
2. **评测 LLM**: 官方评测脚本需要 LLM-as-judge, 也需要 API
3. **完整数据集**: 是否需要现在就解压全部 ~2.5GB 数据?
4. **向量数据库**: FAISS flat 够不够? 还是需要更高效的索引?

### 技术风险

| 风险 | 应对 |
|---|---|
| LLM 调用成本 | 先只跑 39 题验证, 成本可控 |
| 官方评测脚本兼容性 | 直接 clone 官方仓库的 eval 脚本, 作为 submodule |
| chunk ID → parent doc ID 映射 | 索引阶段记录 chunk-doc 映射表 |
| 中英文混合 | 问题英文, 文档英文, 管线无语言障碍 |

---

## 五、执行顺序

```
Phase 1.1: 搭建管线框架
  └→ Phase 1.2: BM25 基线
      └→ Phase 1.3: Dense 基线
          └→ Phase 1.4: Hybrid+Reranker 基线
              └→ Phase 2.1: 数据集风格分析
                  └→ Phase 2.2: 问题风格分析
                      └→ Phase 2.3: 针对性优化 + 完整数据集评测
```

---

## 2026-07-28 实施更新

本轮已完成：

- [x] GitHub-only 严格筛选（39 题），并保留 `contains` 兼容模式
- [x] 答案原子 checkpoint、断点续跑、成功题复用、失败题重试
- [x] 提交 JSONL 结构和题目覆盖校验
- [x] Qwen thinking 关闭参数、输出上限和瞬时错误重试配置
- [x] SQLite manifest、文件级失败隔离、确定性 chunk ID
- [x] 预处理断点恢复和语料/配置/模型缓存指纹
- [x] FAISS 分批写入；Dense-only 跳过 BM25
- [x] Hybrid 默认使用 RRF
- [x] 可选 Cross-Encoder reranker 和相邻 chunk 扩展
- [x] 生成上下文与提交 `document_ids` 保持一致
- [x] 官方评测命令修正为 `--results-file`
- [x] 自动化测试、提交校验 CLI、Embedding 压测 CLI
- [x] 8,052 篇 GitHub 语料的新格式 BM25 索引实测通过

仍需外部资源：

- [ ] 在 GPU 服务器运行 10,000 chunks 压测
- [ ] 建立 511,961 篇可用语料的首个全量向量索引
- [ ] 启动并验证 Elasticsearch/OpenSearch 服务
- [ ] 获取官方评测代码并配置 Judge API
- [ ] 完成 10 → 50 → 500 题正式生成和评分
