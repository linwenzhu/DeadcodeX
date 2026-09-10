# DeadCodex 课程项目报告

## 项目摘要

DeadCodex 1.0 是在 Vulture 2.16 基础上完成的项目级 Python 死代码分析工具。本项目保留原有 AST 遍历、定义收集、名称使用分析和不可达代码检测能力，同时将集中在 `core.py` 中的职责拆分为模型、解析、收集、项目加载、解析器、调用图、框架适配、报告和基线模块。在不改变兼容分析行为的前提下，系统增加了跨文件限定名解析、项目调用图、入口可达性、Flask 和 FastAPI 隐式入口、JSON 与 HTML 报告、Baseline 和 CI。

项目的主要结论是：常见 Python 项目可以在保留 Vulture 低成本名称分析的同时，通过显式项目模式获得更精确的跨文件结果。对于动态调用、猴子补丁和复杂多态，系统采用保守策略，不把无法证明的调用直接判定为死代码。

## 一 项目背景与目标

原始 Vulture 的核心判断可以概括为“已定义名称减去已使用名称”。这种方法简单、快速，但同名函数、跨文件导入和框架隐式调用容易造成误判。本项目采用“半迁移、半重构、增加项目级能力”的路线，目标包括：

- 保持原 CLI 和公共 API 尽量兼容；
- 拆分解析、AST 收集、模型、分析和报告职责；
- 为符号增加稳定的模块级限定名；
- 解析常见绝对导入、相对导入和别名；
- 构建跨模块调用图并从入口点执行 BFS；
- 识别 Flask 和 FastAPI 装饰器入口；
- 提供 Console、JSON、HTML 和 Baseline；
- 建立自动测试、wheel 安装测试和 GitHub Actions 质量门禁。

## 二 需求分析

### 功能需求

| 编号 | 需求 | 验收方式 |
|---|---|---|
| FR01 | 扫描文件和目录中的 Python 源码 | 原 Vulture 扫描测试通过 |
| FR02 | 收集函数、异步函数、类、方法、变量、导入、调用和装饰器 | AST 单元测试 |
| FR03 | 为项目符号生成限定名 | 项目与作用域测试 |
| FR04 | 解析常见 import、from import 和 alias | Resolver 测试 |
| FR05 | 构建跨文件 Call Graph | Call Graph 测试 |
| FR06 | 从一个或多个入口点计算可达性 | Reachability 测试 |
| FR07 | 识别 Flask 和 FastAPI 隐式入口 | Adapter 与 CLI 测试 |
| FR08 | 输出文本、JSON 和 HTML 报告 | Reporter 测试 |
| FR09 | 生成并应用 Baseline | Baseline 端到端测试 |
| FR10 | 支持配置文件和命令行组合 | Config 测试 |

### 非功能需求

- 兼容性：无新增选项时继续执行原名称级算法。
- 可维护性：模型、收集、解析、报告和框架规则相互隔离。
- 可扩展性：框架入口通过 `EntryPointProvider` 协议扩展。
- 可测试性：每个模块具有独立测试，并通过安装后 wheel 测试。
- 安全性：HTML 内容转义；Baseline 文件严格校验版本和结构。
- 可解释性：可查询入口到目标符号的一条确定性调用路径。

## 三 系统架构

```text
Source Paths
    |
    v
ProjectLoader -> ProjectModel / ModuleModel / Scope
    |
    v
PythonParser -> ScopeCollector + AstCollector
    |
    v
Qualified Items + Imports + References + Calls
    |
    v
ImportResolver -> ReferenceResolver -> CallGraphBuilder
                                         |
EntryPointProvider ----------------------+
                                         v
                               ReachabilityAnalyzer
                                         |
                                         v
                       Console / JSON / HTML / Baseline
```

`DeadCodex` 是公共分析门面和 CLI 协调器。各分析模块不直接负责输出，Reporter 只消费统一的 `Finding` 模型。框架 Adapter 只贡献入口点，不修改核心引用解析结果。

## 四 核心设计

### 项目模型与限定名

每个文件对应 `ModuleModel`，包含模块限定名、路径、作用域树、导入绑定、引用和调用点。定义项继续使用兼容的 `Item`，并增加 `qualified_name` 与 `decorators`。例如两个文件中的 `run` 分别表示为 `a.run` 和 `b.run`。

### Import Resolver

Import Resolver 支持 `import x`、`import x as y`、`from x import y`、`from x import y as z`、相对导入、星号导入和包重导出。解析状态包括 resolved、external、unresolved、ambiguous 和 pending，避免把未知情况误认为唯一目标。

### Call Graph 与 Reachability

Collector 为每个调用保存调用者作用域、被调用表达式、文件和行号。引用解析完成后，Call Graph Builder 将唯一的项目内函数、方法或类目标转成调用边。Reachability Analyzer 从显式入口和框架入口执行 BFS，记录可达节点、不可达 callable、无效入口和前驱关系。

### Framework Adapter

`EntryPointProvider` 定义入口发现协议。`DecoratorEntryPointAdapter` 支持通配模式，`FlaskAdapter` 和 `FastAPIAdapter` 提供常用 HTTP、route、api_route 和 websocket 装饰器集合。它们把处理函数作为调用图根节点，从而减少框架隐式调用造成的误报。

### Reporter 与 Baseline

`Finding` 是稳定的报告数据模型。Console Reporter 保持原文本格式；JSON Reporter 输出带版本号的机器可读结构；HTML Reporter 输出无需外部资源的独立页面并转义动态内容。Baseline 使用类型、项目相对路径和限定名生成 SHA-256 指纹，定义移动行号后仍可匹配。

## 五 兼容性与范围控制

默认执行 `deadcodex PATH` 时仍使用原名称级算法。项目模式只有在使用 `--entry-point`、`--entry-point-decorator` 或 `--framework` 后启用。无法解析或有歧义的调用名称采用保守处理，不用于确认同名 callable 为死代码。

按照课程范围，第一版不支持动态 import、全面精确的 `getattr`、Monkey Patch、复杂继承与完整多态分析、Django 全框架语义、IDE 插件或 Web SaaS。这些是明确的范围排除，不影响第一版验收。

## 六 测试与质量保证

测试分为原行为回归、架构边界、项目加载、Import Resolver、引用解析、Call Graph、Reachability、Framework Adapter、Reporter、Baseline、CLI 和 Demo 集成测试。质量门禁包括：

- pytest 全量测试；
- pytest-cov 覆盖率报告；
- Ruff 静态检查；
- Ruff 格式检查；
- tox 构建 wheel、安装 wheel 后执行测试；
- GitHub Actions 多 Python 版本矩阵。

本地使用 Python 3.12 的最终验收结果为 377 个测试通过、无跳过项，单次完整测试的代码覆盖率为 94%。Ruff 检查、格式检查和 wheel 构建安装测试均通过。

## 七 六人分工

| 成员 | 端到端任务包 | 主要交付物 | 估算 |
|---|---|---|---:|
| A | 解析与 AST 信息采集 | Parser、Collector、扫描错误处理、原行为回归 | 34 h |
| B | 领域模型与分析基础 | Model、Project、Scope、Analysis、Pipeline | 34 h |
| C | 导入与引用解析 | ImportResolver、ReferenceResolver、歧义与外部状态 | 34 h |
| D | 控制流、调用图与项目可达性 | 语句不可达、CallGraph、BFS、路径解释 | 34 h |
| E | 配置、CLI 与框架入口 | Config、命令行、通用装饰器、Flask、FastAPI | 34 h |
| F | 报告、Baseline 与可交付工程 | Reporter、Baseline、打包、CI、集成验收 | 34 h |

六人统一按 34 小时估算，且每人的任务都包括实现、对应测试、模块文档和一次交叉审查。`core.py` 按方法分配给 A/B/C/D/E/F，不由单人包揽；F 只组织全量验收，测试失败和覆盖率缺口仍由对应模块负责人修复。具体代码阅读清单、方法所有权、测试文件和验收标准见 [team-workload-plan.md](team-workload-plan.md)。

## 八 风险与应对

- Python 动态性：使用显式状态和保守回退，不声称未知调用已解析。
- 同名符号：使用模块和作用域限定名，不只比较短名称。
- 框架误报：Adapter 只在用户选择框架或装饰器模式时启用。
- 重构回归：默认路径持续运行原始测试和项目自扫描测试。
- 报告兼容：Console Reporter 复用原 `Item.get_report()` 格式。
- 基线失效：普通定义的指纹不包含行号，降低代码移动影响。

## 九 演示与运行

```bash
python -m deadcodex examples/demo_project --framework fastapi
python -m deadcodex examples/demo_project --framework fastapi --format json
python -m deadcodex examples/demo_project --framework fastapi \
  --format html --output report.html
python -m deadcodex examples/demo_project --framework fastapi \
  --baseline baseline.json --update-baseline
```

示例中的 FastAPI 路由函数被识别为入口，其调用的序列化函数可达，未被调用的旧函数被报告。

## 十 项目总结

本项目完成了从名称级扫描器到可选项目级静态分析工具的架构升级。它没有尝试解决 Python 静态分析中的全部动态问题，而是通过限定名、显式解析状态、调用图、可达性和框架入口，在可控范围内提高结果精度。默认兼容、模块边界、自动测试、报告、Baseline、CI 和 Demo 共同构成了一套可运行、可验证、可继续扩展的课程项目成果。
