# RAG 联调控制台

独立的可视化联调应用。它不修改、运行或写入仓库现有的 RAG 代码和产物；仅通过版本化、只读的 HTTP 调试 API 使用已发布的 RAG 服务。

## 运行模式

- `pinned`：指定已发布 RAG 版本，供 daily-50 与 full-500 可重复评测。
- `live`：调用用户选择的最新已发布 RAG 服务，供单题联调；每次运行也保存版本指纹。

详细边界、接口和开发顺序见 [开发设计](docs/DEVELOPMENT_DESIGN.md)，实现状态与提交追踪见 [TODO](TODO.md)。
