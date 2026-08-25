# Semantic A3.3 q182 prompt 对齐离线审计

## 结论

A3.3 已完成。`qst_0182` 基线与 A3.2 失败 runtime 的 final candidate 集合完全一致，30 个 chunk 的顺序和 SHA-256 均一致；回归不是检索、rerank 或候选排序变化。

根因是 A3.2 初版远端应用脚本在模板末尾少追加一个换行，导致 runtime selector prompt 与 A3.1 selector-only 复放 prompt 字节不一致。对同一 q182 输入，新契约复放 5/5 accepted；将 runtime 追加字节修正为完全一致后，q182 单题端到端恢复 recall 100%、extra 0。

## 证据

- 基线 S1 与失败 runtime：`final_before_generation.chunk_ids` 都是 30 个，顺序逐项相同；候选 SHA-256 相同。
- 基线 q182 使用修正后的 selector-only 新契约复放 5 次：`accepted` 5/5，响应稳定。
- 首次 runtime 六题中 q182 曾拒答；这是应用脚本 prompt 字节差异的中间结果，不作为最终 A3.2 评分。
- 修正末尾换行后 q182 单题端到端：目标文档引用恢复，recall 100%，extra 0。
- 修正末尾换行后六题端到端：q176、q272 和 q182 目标引用均恢复；q177 保持；q220/q260 保持拒答；平均 recall 66.7%，extra 0。

## 处置

- 已将应用脚本固定为与 selector-only 复放一致的模板末尾字节。
- 每次实验结束均回滚远端 `src/generator.py`，并核验备份文件已清理。
- 不修改本地既存 `src/generator.py`；A3.4 重新使用独立、可回滚的 runtime 配置。
