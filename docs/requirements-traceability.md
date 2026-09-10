# DeadCodex 需求追踪矩阵

## 追踪目的

本矩阵把课程项目方案中的 DeadCodex 工作项映射到代码、测试和交付文档，用于迭代验收和答辩检查。

| 文档工作项 | 实现 | 验证 | 状态 |
|---|---|---|---|
| AST 解析与核心能力 | `parser.py`、`collector.py` | 原测试、`test_architecture.py` | 完成 |
| Symbol 与 Module Model | `model.py`、`project.py`、`scope.py` | `test_project.py` | 完成 |
| Finding Model | `model.py` 中 `Finding` | `test_reporters.py` | 完成 |
| Analyzer 接口与管线 | `pipeline.py` | `test_pipeline.py` | 完成 |
| Import Resolver | `resolver.py` | `test_resolver.py` | 完成 |
| 跨文件引用 | `resolver.py` | `test_references.py` | 完成 |
| Call Graph | `callgraph.py` | `test_callgraph.py` | 完成 |
| DFS/BFS Reachability | `callgraph.py` | `test_project_reachability.py` | 完成 |
| Framework Adapter 协议 | `adapters.py` | `test_adapters.py` | 完成 |
| Flask Adapter | `FlaskAdapter` | Adapter 与 CLI 测试 | 完成 |
| FastAPI Adapter | `FastAPIAdapter` | Adapter、CLI、Demo 测试 | 完成 |
| CLI 与 Config | `core.py`、`config.py` | `test_config.py`、`test_script.py` | 完成 |
| Console Report | `ConsoleReporter` | `test_report.py` | 完成 |
| JSON Report | `JsonReporter` | `test_reporters.py`、Demo 测试 | 完成 |
| HTML Report | `HtmlReporter` | `test_reporters.py` | 完成 |
| Baseline | `baseline.py` | `test_baseline.py` | 完成 |
| GitHub Actions | `.github/workflows/ci.yml` | `test_delivery.py` | 完成 |
| Demo | `examples/demo_project` | `test_delivery.py` | 完成 |
| 架构文档 | `docs/architecture.md` | 人工评审 | 完成 |
| 课程报告 | `docs/course-report.md` | 人工评审 | 完成 |
| 答辩材料 | `docs/defense-outline.md` | 人工演练 | 完成 |
| 六人协作规范 | `docs/team-workflow.md` | 团队评审 | 完成 |

## 第一版范围排除

动态 import、全面精确的 `getattr`、Monkey Patch、完整多态、复杂继承、Django 全框架支持、IDE 插件和 Web SaaS 按原方案明确不进入第一版，因此不标记为未完成需求。
