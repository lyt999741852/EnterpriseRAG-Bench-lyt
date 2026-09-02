# S3：无 PageIndex 的固定四路混合检索 + 覆盖反思计划

日期：2026-09-02  
状态：设计完成，尚未改主链、尚未启动测试

## 目标与动机

当前路由器先判断题型，再决定 query view、候选预算、PageIndex 参数和证据策略。这条链路存在两个风险：

1. 题型误判会同时改变检索和后处理，错误会被放大；
2. PageIndex 多个预算和 selector 规则叠加后，单题行为难以解释和复现。

S3 将路由从“先分类再选择策略”改为“所有问题走同一套召回，使用证据覆盖检查决定是否补召回”。本实验不使用 PageIndex，不使用题型标签，不让反思器替换原始候选。

## 固定主链

### 1. 四路固定混合召回

每道题都执行四路 query，不做题型路由：

| lane | 查询表示 | 作用 |
|---|---|---|
| L1 | 原题 | 保留原始实体、日期、数字和限定条件，是不可删除的托底 |
| L2 | 词法视图 | 从原题抽取实体、产品、版本、日期、指标和动作，服务 BM25 精确命中 |
| L3 | 语义视图 | 生成保留硬约束的自然语言语义查询，服务低关键词重合问题 |
| L4 | 分面/答案意图视图 | 将多子句问题拆成“需要哪些事实/关系/时间点”，不生成答案 |

每一路都同时执行 BM25+dense，结果 append-only 合并；L1 前段始终保留。建议初始窗口为每路 top-120，RRF 后取 240，rerank 输入仍固定 120，避免此前 rerank 240 超时问题。

四路视图由统一模板生成，必须保留原题中的实体、数值、日期、版本、地域和 finality 约束；解析失败时只使用 L1/L2，不清空候选。

### 2. 证据覆盖检查

初次 rerank 后，由结构化 coverage checker 检查“问题需要什么”和“候选 chunk 已覆盖什么”，只输出 JSON，不回答问题：

```json
{
  "sufficient": false,
  "facets": [{"id": "f1", "need": "...", "covered": true, "evidence": [1, 4]}],
  "missing_facets": ["..."],
  "conflicts": ["..."],
  "next_queries": ["..."]
}
```

checker 必须逐项标出证据 chunk 编号；不得凭记忆补事实，不得把“未检索到”直接判为“文档不存在”。

### 3. 最多三轮反思检索

- 第 0 轮：四路固定混合召回、RRF、rerank 120。
- 第 1–3 轮：仅针对 `missing_facets` 或未解决冲突生成补召回 query；每轮仍执行 BM25+dense，新增候选 append-only。
- 每轮新增候选上限建议 40 个、每文档最多 4 个 chunk；上下文最终上限 16 个 chunk，允许多文档，不设 strict selector drop。
- 满足 `sufficient=true`、连续一轮无新增有效证据、query 重复或达到 3 轮时停止。
- 最终答案只使用通过 coverage checker 保留的证据；selector 使用 O4.P3 的 bounded fail-open 参数，作为可复现基线。

## 实验分层

### S3.0：无 PageIndex 静态对照（只读）

四路召回但不反思，测 raw/pre-rerank/final document recall@30/120/240/500/1000，确认去掉 PageIndex 后损失发生在哪一层。

### S3.1：单轮 coverage rescue

在 S3.0 上增加最多 1 轮覆盖反思，先跑 20 题分层 smoke（Semantic、Project、Completeness、Conflict、Basic 控制题均包含）。

### S3.2：三轮 agentic 回归

仅当 S3.1 的 Semantic/Project/Completeness 召回有净增益且控制题无回退，再扩大到 AB50；AB50 通过后才跑 F500。三轮不是默认全跑，提前满足覆盖条件就停止。

## 评测与放行门槛

必须同时记录：

- raw、pre-rerank、final document recall；
- 每题反思轮数、checker 判定、缺失 facet 恢复数、重复 query 数；
- correctness、completeness、combined、invalid extra docs；
- 平均延迟、LLM 调用次数、rerank 超时/失败数。

放行条件：

1. Semantic 125 的 Recall@240 或最终 recall 有稳定净增益；
2. Project/Completeness 不下降；
3. Basic、Constrained、InfoNotFound 等控制题 correctness 不下降；
4. 三轮反思平均调用数可控，rerank 无 broken pipe/timeout；
5. 相比 O4.P3 F500 基线 `combined >= 58.88` 且 correctness `>= 64.00%`。

未达标时保留 S3 诊断，不替换当前 O4.P3 基线。通过后再考虑将 PageIndex 作为少量高难题的可选 fallback，而不是主路由依赖。

