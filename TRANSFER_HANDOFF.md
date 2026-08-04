# EnterpriseRAG-Bench 转移交接文档

> 创建日期: 2026-07-31
> 用途: 从公司电脑转移到个人电脑，确保新环境能快速理解项目全貌并继续工作
> 阅读顺序: 本文 → `PROGRESS.md` → `ENTERPRISE_RAG_BENCH_HANDOFF.md`（如需更深的技术细节）

---

## 一、项目是什么

**EnterpriseRAG-Bench** 是一个 RAG（检索增强生成）打榜任务。

- 官方数据集: https://github.com/onyx-dot-app/EnterpriseRAG-Bench
- 官方榜单: https://onyx.app/enterpriserag-bench
- 论文: https://arxiv.org/abs/2605.05253

任务目标：基于官方提供的 **511,962 份企业文档**（9 种数据源）和 **500 道评测题**（10 种题型），搭建自研 RAG 框架，按官方评分规则不断优化，争取上榜。

**官方评分公式**: `主分数 = Correctness × Completeness`（0~100 分，500 题等权平均）

---

## 二、当前进度总览

| 里程碑 | 状态 | 说明 |
|---|---|---|
| 数据集调研与统计 | ✅ 完成 | 文档分布、题型、评分规则全部摸清 |
| 自研 RAG 管线框架 | ✅ 完成 | index→retrieve→generate→evaluate 全流程 |
| 全量 ES 索引 | ✅ 完成 | 928,534 chunks，部署在公司服务器 |
| 安全整改 | ✅ 完成 | API Key 改环境变量 |
| 50 题门禁评测 | ✅ 完成 | 综合分 **70.1**（当前最优 v2） |
| 8 题型诊断 | ✅ 完成 | 发现非 basic 题型需专项优化 |
| **500 题全量评测** | ⬜ **未启动** | 配置就绪，需 SSH 到服务器手动运行 |
| 官方排行榜提交 | ⬜ 未开始 | 需冻结 500 题基线后联系官方 |

---

## 三、当前最优成绩（50 题 v2 召回保护）

| 指标 | 原基线 | v1 高精度 | **v2 召回保护** |
|---|---:|---:|---:|
| 正确率 | 66.0% | 68.0% | **72.0%** |
| 完整性 | 76.32% | 70.80% | **75.87%** |
| **综合分** | 64.2 | 65.7 | **70.1** |
| 文档召回 | 86.0% | 72.0% | **88.0%** |
| 无效附加文档 | 6.74 | 0.44 | 3.06 |

---

## 四、架构概览

```
问题 → ES BM25 Top-100 + BGE Dense Top-100 → 加权 RRF 融合（dense_weight=0.3）
     → 子项/硬约束分析
     → direct / supporting / reject 三级证据分级
     → 子项覆盖合并 + Top-2 召回锚点（最多6篇）
     → Qwen 3.5-27B (lark) 生成草稿
     → 逐句事实核验
     → 最终答案 + document_ids
```

关键组件:
| 组件 | 具体实现 |
|---|---|
| 检索 | Elasticsearch 8.19.12，BM25 + Dense kNN + RRF |
| Embedding | `BAAI/bge-small-en-v1.5`（384 维，MIT 协议） |
| LLM | Qwen 3.5-27B，内网地址 `http://10.72.100.35:7777/v1`，api_key=`lark` |
| 切块 | fixed-v2，512 字符，无 overlap，无父子文档 |
| 证据筛选 | tiered_v2 + fact_verification |
| PageIndex | 当前关闭（诊断显示对非 basic 题型过于保守） |

---

## 五、服务器环境（重要！）

500 题评测需要在服务器上运行，**不是本地运行**。

| 项目 | 值 |
|---|---|
| 服务器 IP | `10.72.100.29` |
| SSH 用户/密码 | `root` / 见口头交接 |
| 操作系统 | Linux（Ubuntu） |
| Python | Anaconda, Python 3.10.14 |
| GPU | 4× NVIDIA A800 80GB PCIe |
| 应用目录 | `/opt/enterprise-rag-bench/app` |
| ES 地址 | `http://127.0.0.1:9200`（服务器本地） |
| Qwen LLM | `http://10.72.100.35:7777/v1`（内网另一台机器） |
| PageIndex | `/opt/enterprise-rag-bench/PageIndex` |
| ES 索引 | `enterprise-rag-bge-small-v1`（928,534 chunks，已建好） |

**服务器上已有的依赖**: torch 2.4.1, sentence-transformers 3.2.0, rank-bm25 0.2.2, elasticsearch 9.4.1, PyYAML 6.0.2

---

## 六、如何启动 500 题评测

SSH 登录服务器后执行：

```bash
cd /opt/enterprise-rag-bench/app
export LARK_API_KEY=lark
python3 -m src.pipeline configs/eval_500_es_qwen_v2.yaml
```

预计耗时：~4-6 小时（生成 + 官方评分）。支持中断恢复（`resume: true`）。

输出目录：`outputs/eval_500_es_qwen_v2/`
- `answers.jsonl` — 500 题答案
- `results.json` — 官方评分结果
- `simple_metrics.json` — 简单召回指标
- `validation.json` — 格式校验

---

## 七、打包内容说明

ZIP 包**包含**：
- `src/` — 全部 Python 源代码（12 个模块）
- `configs/` — 全部 YAML 配置文件（~20 个）
- `outputs/` — 所有历史评测结果（~14 组实验）
- `tests/` — 单元测试
- `deploy/` — 部署脚本和打包工具
- `questions.jsonl` — 500 题问题集（含标准答案，仅用于评测）
- `extra_questions.jsonl` — 额外 metadata 问题
- `requirements.txt` — 依赖清单
- 所有 `*.md` 报告文档
- `run_*.bat` / `run_*.ps1` — 本地运行脚本
- `docker-compose.yml` — ES Docker 配置
- `ENTERPRISE_RAG_ARCHITECTURE_FLOW_V3K.png` — 架构图

ZIP 包**排除**（太大，可重新获取）：
| 目录 | 原因 |
|---|---|
| `corpus/` | 2.5GB 原始文档，服务器上已有完整副本 |
| `confluence/` | 语料子集 |
| `demo_corpus/` | 演示数据 |
| `slice_inspect/` | 检查数据 |
| `.index_cache/` | 可重建的缓存索引 |
| `.git/` | 版本控制 |
| `github_slice_*.zip` | 原始数据压缩包 |

---

## 八、关键文件快速索引

### 必读文档（按顺序）
| 文件 | 内容 |
|---|---|
| `TRANSFER_HANDOFF.md` | 本文，转移交接总览 |
| `PROGRESS.md` | 持续更新的进度跟踪 |
| `ENTERPRISE_RAG_BENCH_HANDOFF.md` | 完整技术交接记录（810行，含所有已确定方案） |
| `WORK_PLAN.md` | 原始工作计划和阶段定义 |

### 各阶段报告
| 文件 | 日期 | 内容 |
|---|---|---|
| `PHASE2_ES_REPORT.md` | 07-28 | ES 索引初步搭建 |
| `PHASE3_ES_REPORT.md` | 07-29 | 全量索引完成（928,534 chunks） |
| `PHASE4_EVAL_REPORT.md` | 07-29 | 10/50 题基线评测（综合分 64.2） |
| `PHASE4_EVIDENCE_V2_REPORT.md` | 07-30 | v2 召回保护（综合分 70.1） |
| `DIAGNOSTIC8_V3K_REPORT.md` | 07-30 | 8 题型诊断（非 basic 全失败） |
| `PAGEINDEX_PRECISION_V3_REPORT.md` | 07-30 | PageIndex 精度测试 |

### 源代码核心模块
| 文件 | 功能 |
|---|---|
| `src/pipeline.py` | 主入口：index→retrieve→generate→evaluate |
| `src/indexer.py` | 文档加载、切块、索引构建 |
| `src/embedder.py` | Embedding 生成（sentence-transformers） |
| `src/retriever.py` | BM25 / Dense / Hybrid 检索（本地 FAISS） |
| `src/elasticsearch_backend.py` | ES 后端（索引写入、混合检索） |
| `src/generator.py` | LLM 答案生成 + tiered 证据筛选 + 事实核验 |
| `src/llm.py` | LLM 客户端（openai_compatible 协议） |
| `src/pageindex_router.py` | PageIndex 混合路由（1427行，复杂逻辑） |
| `src/evaluator.py` | 官方评测封装 + 答案校验 |

### 配置文件
| 文件 | 用途 |
|---|---|
| `configs/eval_500_es_qwen_v2.yaml` | **500 题正式评测配置（待运行）** |
| `configs/eval_50_es_qwen_evidence_v2.yaml` | 50 题 v2 配置（当前最优） |
| `configs/full_es_qwen.yaml` | 全量索引配置 |
| `configs/eval_pageindex_*.yaml` | PageIndex 相关实验配置 |

---

## 九、已识别的瓶颈与下一步优化方向

### 当前瓶颈
1. **非 basic 题型表现差** — 8 题型诊断中 5 类（semantic/constrained/conflicting/completeness/high_level）全部 0%
2. **切块过于简单** — 固定 512 字符无 overlap，无父子文档
3. **检索层漏召回** — 6 题 Top-10 候选中完全没有金标文档
4. **同模型自评偏差** — Qwen 同时生成和评分，不等于独立裁判
5. **无效附加文档** — v2 的 3.06 偏高，需平衡去噪和召回

### 推荐优化顺序（按预期收益）
1. 先跑 500 题拿到完整诊断基线
2. 按 10 种题型分组分析薄弱点
3. 非 basic 题型路由优化（利用已有的 PageIndex 架构）
4. 父子文档切块（320/64 child + 整篇 parent）
5. Cross-Encoder 重排序（当前关闭）
6. Embedding 升级（bge-base 768维 或 e5-base-v2）
7. 独立裁判模型评测

---

## 十、注意事项

1. **`questions.jsonl` 绝不能进入 RAG 索引** — 这是答案泄漏，会导致评测无效
2. **被 Windows Defender 隔离的文件** `dsid_bc8604e6...` 不影响评测（不在 500 题 gold 中）
3. **服务器 ES 索引已建好** — 不需要重建，直接可以检索
4. **GPU 2 被 llama-server 占满** — 500 题配置已改为 `cuda:1`
5. **官方榜单提交** — 发邮件给 `joachim@onyx.app`，需提供复现材料
6. **安全提醒** — 不要在代码中硬编码 API Key，始终用环境变量

---

## 十一、新环境快速上手

### 本地（个人电脑）
```bash
# 1. 解压 ZIP
# 2. 安装依赖
pip install -r requirements.txt
# 3. 本地测试（需要 ES 和 LLM 可达）
python -m src.pipeline configs/default.yaml
```

### 服务器（500 题评测）
```bash
# SSH 到服务器
ssh root@10.72.100.29

# 进入项目目录
cd /opt/enterprise-rag-bench/app

# 如果需要更新代码，可以从本地 scp 同步
# scp -r src/ configs/ root@10.72.100.29:/opt/enterprise-rag-bench/app/

# 运行 500 题评测
export LARK_API_KEY=lark
python3 -m src.pipeline configs/eval_500_es_qwen_v2.yaml
```

### 新 AI 会话开场提示
```
请完整读取 D:\EnterpriseRAG-Bench\TRANSFER_HANDOFF.md 和 PROGRESS.md，
了解项目全貌和当前进度。然后检查 configs/eval_500_es_qwen_v2.yaml
确认 500 题评测配置。当前优先任务是启动 500 题全量评测。
服务器: 10.72.100.29 (SSH)，应用目录: /opt/enterprise-rag-bench/app
```
