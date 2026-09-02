# 项目移交清单

更新时间：2026-09-02（Asia/Shanghai）  
目的：整理本项目可复现的有效代码、配置和实验结论，形成范围明确的移交材料。

## 建议纳入移交材料的范围

| 类别 | 路径 | 说明 |
|---|---|---|
| 核心实现 | `src/`、`tests/`、`requirements.txt` | 可运行 RAG 与自动化测试 |
| 可复现配置 | `configs/`、`configs/snapshots/` | 每个有效实验的 YAML 与冻结快照 |
| 自动化脚本 | `scripts/diag/`、经审查的 `scripts/remote/` | 先确认没有凭据、内网敏感路径或破坏性操作 |
| 当前文档 | `README.md`、`CURRENT_STATUS.md`、`docs/`（不含 `docs/archive/restricted/`） | 入口、结果、路线与原始报告 |
| 精简实验产物 | 对应 F500/AB50/AB150 的 `results.json`、评分 JSON、题集清单、必要 trace 摘要 | 支撑文档结论，不上传全量缓存 |

## 代码副本的归属

| 路径 | 定位 | 移交处理 |
|---|---|---|
| `src/`、`tests/`、`configs/` | 本项目的唯一主实现与复现实验配置 | 作为唯一主代码与配置来源 |
| `bge500_rag_pageindex_core/` | BGE500 精简代码包；内容与主实现重叠 | 作为一次性移交包；不要和 `src/` 并列维护两份主代码 |
| `conan_rag/` | 已隔离的 Conan 研究快照 | 仅在需要保留可运行研究分支时纳入；不可替代 BGE 主线 |
| `portable_rag/` | 通用轻量 RAG 示例 | 独立示例，不纳入主线实验结论 |
| `rag-debug-console/` | 独立调试控制台应用 | 如由本项目维护，作为独立子目录说明；否则与主线材料分开 |

## 不应纳入移交包的内容

- `.env`、API key、token、明文账号密码，及包含这些信息的历史资料。
- `docs/archive/restricted/`：本地审计用，不纳入移交范围。
- `corpus/`、`questions.jsonl`、`extra_questions.jsonl`、`.index_cache/`、`.pageindex_cache/`、大体积 outputs、压缩包（`.zip`、`.7z`）和本地临时目录。
- 未经脱敏的服务器地址、内部服务拓扑、访问脚本和日志。

## 交接包应包含的最小证据链

1. [当前状态](CURRENT_STATUS_20260902.md) 与 [有效实验测试汇总](VALID_EXPERIMENT_TEST_SUMMARY_20260901.md)。
2. F500 配置快照、[O4.P3 结果](F500_BGE_DPV4_O4P3_20260902.md) 和对应官方评分 JSON。
3. 单变量决策证据：reranker、PageIndex、BGE/Conan 的同题对照。
4. [复现清单](F500_BGE_DPV4_O4P3_REPRO_20260902.md)、依赖版本、运行环境要求和已知限制。

## 移交前检查

1. 逐项核对上述范围，确保每份结果都有配置、输出位置和对应报告。
2. 扫描并脱敏 API key、password、secret、token，以及内部服务地址和访问日志。
3. 运行与本次移交代码对应的自动化测试，并记录命令和结果。
4. 排除缓存、语料、题集、压缩包、临时目录和受限历史材料。

当前自动扫描仍命中大量潜在凭据赋值（多数可能只是环境变量名）；在逐项人工确认或
完成脱敏前，不应移交 `configs/`、`scripts/`、旧报告和远程运行脚本。
