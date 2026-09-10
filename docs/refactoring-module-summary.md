# DeadCodex 第一版重构与模块说明

## 1. 文档目的

本文档总结本次 Vulture 二次开发完成的内容，并说明各个模块的职责、模块之间的协作关系、对外使用方式、测试情况以及当前版本边界。

本次工作不是重写 Vulture，也没有立即加入复杂的动态分析能力。重构的核心目标是：

1. 尽量保持 Vulture 原有行为和命令行兼容。
2. 将原本集中在 `core.py` 中的模型、解析、AST 收集、项目分析和报告职责分离。
3. 在分层架构上增加可选的项目级静态分析能力。
4. 为框架适配、报告扩展、基线管理和后续二次开发建立稳定接口。

## 2. 已完成内容概览

本次完成了以下工作：

- 将领域对象抽离到独立模型层。
- 将 Python 源代码解析与 AST 数据收集分离。
- 建立项目、模块、限定名和词法作用域模型。
- 收集导入、名称引用、属性引用和调用点。
- 实现项目内导入解析和引用解析。
- 构建项目内静态调用图。
- 实现从入口点出发的函数可达性分析。
- 支持显式入口点及基于装饰器的隐式入口点。
- 提供 Flask 和 FastAPI 路由入口适配器。
- 支持传统文本、JSON 和独立 HTML 报告。
- 支持基线生成与历史问题过滤。
- 扩充命令行及 `pyproject.toml` 配置。
- 保留原有名称级检测作为默认模式。
- 补充单元测试、集成测试、端到端演示和 CI 工作流。
- 编写架构、演示、课程报告、答辩和需求追踪文档。

## 3. 总体架构

```text
文件或目录
    |
    v
ProjectLoader ----------> ProjectModel / ModuleModel
    |                              |
    v                              v
源代码 -----------------> PythonParser ---------> ParsedModule
                                                   |
                          +------------------------+------------------+
                          |                                           |
                          v                                           v
                   ScopeCollector                                AstCollector
                          |                                           |
                          v                                           v
                    作用域树 Scope                       定义、引用、导入、调用点
                          |                                           |
                          +------------------------+------------------+
                                                   |
                                                   v
                                            ProjectAnalyzer
                                                   |
                    +------------------------------+------------------+
                    |                              |                  |
                    v                              v                  v
              ImportResolver              ReferenceResolver   CallGraphBuilder
                                                                     |
                                                                     v
                                                               CallGraph
                                                                     |
                   显式入口 / Flask / FastAPI / 自定义装饰器 --------+
                                                                     |
                                                                     v
                                                         ReachabilityAnalyzer
                                                                     |
                                                                     v
                                                        ReachabilityResult
                                                                     |
                  +-----------------------+--------------------------+--------+
                  |                       |                                   |
                  v                       v                                   v
             ConsoleReporter         JsonReporter                       HtmlReporter
                                          |
                                          v
                                       Baseline
```

`DeadCodex` 类仍然是兼容入口和总协调器，但具体分析职责已经下沉到独立模块。

## 4. 核心模块说明

### 4.1 `deadcodex/model.py`：领域模型

状态：重构并扩展。

该模块保存分析过程使用的稳定数据结构，避免解析、收集、解析引用和输出层互相依赖内部实现。

主要对象：

- `QualifiedName`：符号的点分限定名，例如 `package.service.run`，解决不同模块存在同名函数时无法区分的问题。
- `ScopeKind`：作用域类型，包括模块、类和函数。
- `ImportKind`：区分模块导入和符号导入。
- `UsageKind`：区分普通名称读取和属性读取。
- `ResolutionStatus`：统一表示 `pending`、`resolved`、`external`、`unresolved` 和 `ambiguous` 五种解析状态。
- `ImportBinding`：保存一个导入在当前模块绑定的名称、原始模块、别名、相对导入层级和解析结果。
- `UsageReference`：保存名称或属性的使用位置、所在作用域和解析目标。
- `CallSite`：保存一次函数或方法调用及其静态解析结果。
- `CallEdge`：表示已经确认的项目内调用边。
- `CallGraph`：保存全部调用点和已经解析的调用边。
- `ReachabilityResult`：保存入口点、可达符号、不可达符号以及入口点异常，并可解释一条可达路径。
- `Scope`：表示模块、类或函数的词法作用域树节点。
- `ModuleModel`：表示单个 Python 模块，保存模块名、文件路径、作用域、导入、引用和调用信息。
- `ProjectModel`：表示一次分析涉及的全部模块。
- `Item`：兼容原版 Vulture 的检测项模型，保存名称、类型、文件、行号、置信度等。
- `Finding`：面向报告层的稳定输出模型，可转换为 JSON 字典。

设计意义：

- 原版名称 `run` 可以升级为 `a.run`、`b.run`。
- 分析状态不再依靠零散集合隐式表达。
- 报告输出不需要直接了解 AST 节点。

### 4.2 `deadcodex/parser.py`：Python 解析层

状态：从核心流程中抽离。

主要对象：

- `PythonParser`：调用 Python AST 解析器，把源代码转换为 AST。
- `ParsedModule`：把 AST、文件名、源代码行、`noqa` 信息和解析错误封装在一起。

该模块只负责“把源代码变成可分析数据”，不判断代码是否未使用。语法错误和空字节等问题会被保存在解析结果中，再由上层统一处理。

### 4.3 `deadcodex/project.py`：项目与文件加载

状态：新增。

主要对象：

- `ProjectLoader.load()`：从文件和目录中发现 Python 模块。
- `module_from_path()`：根据路径建立模块模型。
- `read_module()`：读取模块源代码。
- `in_memory_module()`：为直接传入字符串的分析建立内存模块。

该模块负责：

- 发现目录下的 Python 文件。
- 识别包目录和 `__init__.py`。
- 推导项目源码根目录。
- 将文件路径转换为稳定的点分模块名。
- 计算多输入路径的共同项目根目录。

### 4.4 `deadcodex/scope.py`：词法作用域收集

状态：新增。

主要对象：`ScopeCollector`。

它独立遍历 AST，建立模块、类、函数和异步函数的嵌套作用域树，并记录每个 AST 节点所在的作用域。

例如：

```python
class Service:
    def run(self):
        pass
```

会形成类似下面的结构：

```text
module
└── Service
    └── Service.run
```

该作用域树是限定名、名称解析以及 `self.method()`、`cls.method()` 分析的基础。

### 4.5 `deadcodex/collector.py`：AST 信息收集

状态：从原 `core.py` 中抽离并扩展。

主要对象：`AstCollector`。

它继承 `ast.NodeVisitor`，负责遍历成功解析的 AST，并收集：

- 类、函数、方法和属性定义。
- 变量、参数和导入定义。
- 普通名称读取。
- 属性读取。
- 导入绑定关系。
- 函数和方法调用点。
- 装饰器名称。
- `__all__` 使用。
- 格式化字符串中的名称使用。
- 不可达代码片段。
- `noqa`、忽略名称、忽略装饰器和测试文件特殊规则。

收集器只记录事实，不负责跨模块解析目标，也不负责输出报告。

### 4.6 `deadcodex/analysis.py`：未使用代码判定

状态：从核心流程中抽离并扩展。

主要对象：`AnalysisResult`。

该模块保存累计分析结果，并提供两种判定方式：

- `get_unused_code()`：保留原版按短名称匹配的默认算法。
- `get_unused_code_qualified()`：使用限定名引用进行更精确的实验性判断。

安全策略：当某个引用无法可靠解析或存在歧义时，限定名分析会回退到原来的名称级保守逻辑，避免因为分析能力不足而错误删除代码。

### 4.7 `deadcodex/resolver.py`：导入和引用解析

状态：新增。

主要对象：

- `ImportResolver`：解析项目内导入。
- `ReferenceResolver`：解析普通名称和属性引用。

`ImportResolver` 支持：

- 绝对导入。
- 相对导入。
- `import ... as ...` 别名。
- `from ... import ...`。
- 星号导入的保守处理。
- 包导出和项目内模块定位。
- 区分项目内、外部、未解析和歧义目标。

`ReferenceResolver` 支持：

- 按词法作用域向上查找名称。
- 项目内导入别名引用。
- 模块属性访问。
- 静态类属性和方法访问。
- `self.xxx` 与 `cls.xxx` 的类内静态定位。
- Python 内置名称的外部状态识别。

该模块不执行代码，只基于 AST 和项目模型进行保守静态解析。

### 4.8 `deadcodex/callgraph.py`：调用图与项目可达性

状态：新增。

主要对象：

- `CallGraphBuilder`：将调用点和已解析引用组合成调用边。
- `ReachabilityAnalyzer`：从入口点遍历调用图。

`CallGraphBuilder` 只为唯一确定的项目内函数、方法和类建立边；外部调用、动态调用、未解析调用和歧义调用仍会保留为调用点，但不会伪造成确定的调用边。

`ReachabilityAnalyzer` 可以：

- 接受一个或多个限定名入口点。
- 找出从入口点可达的函数、方法和类。
- 找出项目内不可达的可调用符号。
- 安全处理递归调用。
- 识别不存在或具有歧义的入口点。
- 给出一条确定的“入口点到目标”调用路径。

### 4.9 `deadcodex/pipeline.py`：项目分析流水线

状态：新增。

主要对象：

- `Analyzer`：分析器协议，定义统一的 `analyze()` 接口。
- `ProjectAnalyzer`：项目级分析编排器。

它按照依赖顺序执行：

```text
导入解析 -> 引用解析 -> 调用图构建
```

这样 `core.py` 不再直接了解各分析步骤的内部细节，也方便下一阶段插入新分析过程。

### 4.10 `deadcodex/adapters.py`：框架入口适配

状态：新增。

主要对象：

- `EntryPointProvider`：入口点提供者协议。
- `FrameworkAdapter`：框架适配器协议。
- `DecoratorEntryPointAdapter`：通用装饰器匹配实现。
- `FlaskAdapter`：识别 Flask 应用和 Blueprint 路由函数。
- `FastAPIAdapter`：识别 FastAPI 应用和 Router 操作函数。
- `make_framework_adapter()`：根据配置创建适配器。

框架适配器不修改 AST 核心逻辑，只负责发现“由框架隐式调用”的入口函数，然后复用同一个项目可达性分析器。

当前识别的典型装饰器包括：

- Flask：`route`、`get`、`post`、`put`、`patch`、`delete` 等。
- FastAPI：上述 HTTP 方法以及 `api_route`、`websocket` 等。

同时支持用户通过装饰器通配模式接入其他简单框架。

### 4.11 `deadcodex/reporters.py`：报告输出

状态：新增。

主要对象：

- `Reporter`：统一报告协议。
- `ConsoleReporter`：原版文本格式。
- `JsonReporter`：带格式名和版本号的机器可读 JSON。
- `HtmlReporter`：不依赖外部资源的独立 HTML 页面。
- `make_reporter()`：报告器工厂。

文本报告继续调用原有 `Item.get_report()`，因此默认输出保持兼容。JSON 使用稳定的 `Finding` 字段；HTML 会转义文件名、符号名和消息，避免把分析内容直接作为 HTML 注入页面。

### 4.12 `deadcodex/baseline.py`：问题基线

状态：新增。

主要对象：

- `BaselineEntry`：一条已接受问题的稳定身份。
- `Baseline`：负责创建、读取、写入和过滤基线。

基线指纹基于：

- 问题类型。
- 项目相对路径。
- 限定符号名。

普通定义移动行号后仍可匹配原基线；没有限定符号名的不可达语句会保留行号以区分不同位置。基线 JSON 带有格式标识和版本号，错误或不兼容文件会明确拒绝。

### 4.13 `deadcodex/core.py`：兼容门面与总协调器

状态：大幅瘦身和重构，保留公共入口。

主要对象：`DeadCodex`。

当前职责集中在协调，而不是完成全部细节：

- 初始化解析器、加载器、收集器和各分析器。
- 扫描内存代码或项目文件。
- 处理读取错误和语法错误。
- 加载 Vulture 原有内置白名单。
- 触发导入、引用和调用图分析。
- 提供默认、限定名和项目入口三种结果 API。
- 组合显式入口和框架入口。
- 应用置信度、排序、基线和报告选项。
- 维持命令行退出码。

兼容内容：

- `DeadCodex` 仍通过 `AstCollector` 间接继承 `ast.NodeVisitor`。
- 原有默认名称级检测未被项目级分析替换。
- `Item`、`DEFAULT_CONFIDENCE` 和 `ERROR_CODES` 仍可从 `deadcodex.core` 导入。
- 原文本报告格式保持不变。

### 4.14 `deadcodex/config.py`：命令行和配置

状态：扩展。

在原有参数基础上增加：

- `--entry-point QUALIFIED_NAME`：指定项目入口，可重复使用。
- `--entry-point-decorator PATTERN`：通过装饰器模式发现入口。
- `--framework flask|fastapi`：启用框架入口适配器。
- `--format text|json|html`：选择报告格式。
- `--output PATH`：把报告写入文件。
- `--baseline PATH`：过滤基线已有问题。
- `--update-baseline`：用当前结果更新基线。

这些选项也可以放在 `pyproject.toml` 的 `[tool.deadcodex]` 中。命令行参数优先于配置文件，并对不兼容组合和错误类型进行校验。

### 4.15 `deadcodex/__init__.py`：公共 Python API

状态：扩展。

除了继续暴露 `DeadCodex` 外，该模块还公开项目分析和扩展所需的主要类型，例如：

- `Analyzer`、`ProjectAnalyzer`。
- `EntryPointProvider`、`FrameworkAdapter`。
- `DecoratorEntryPointAdapter`、`FlaskAdapter`、`FastAPIAdapter`。

这样二次开发者无需从内部模块路径拼接核心扩展接口。

### 4.16 `deadcodex/`：Python 包和命令入口

状态：新增。

- `deadcodex/__main__.py` 支持 `python -m deadcodex`。
- `deadcodex/__init__.py` 暴露稳定的公共分析 API。
- 安装后的主命令为 `deadcodex`。
- 主类为 `DeadCodex`，推荐使用 `from deadcodex import DeadCodex`。

发行名、源码包、导入路径、主类、命令行和配置节已经统一为 `deadcodex`；当前项目版本为 `1.0`。

## 5. 保留的基础模块

以下模块不是本次项目级架构的主要新增内容，但仍是完整系统的重要组成部分：

- `deadcodex/reachability.py`：分析单个函数或语句块内由 `return`、`raise`、`break`、恒真或恒假条件造成的控制流不可达代码。它和 `callgraph.py` 中的项目函数可达性不是同一概念。
- `deadcodex/lines.py`：计算 AST 节点的起止行号。
- `deadcodex/noqa.py`：解析并应用行级 `noqa` 忽略标记。
- `deadcodex/utils.py`：文件读取、路径格式化、模块发现、条件常量判断、日志集合和退出码等通用能力。
- `deadcodex/whitelists/`：保留常见标准库的内置白名单机制。

## 6. 四种主要工作流程

### 6.1 默认兼容模式

```text
读取文件 -> 解析 AST -> 收集定义和短名称使用 -> 原版名称级判定 -> 文本报告
```

没有指定入口点或框架时使用该模式，行为尽量与原版 Vulture 一致。

### 6.2 限定名分析模式

Python API 可以请求限定名结果。系统在导入和引用能够安全解析时区分同名符号；遇到不确定引用时回退到原有名称级策略。

### 6.3 项目入口可达性模式

```text
扫描全部模块
-> 解析导入
-> 解析名称与属性
-> 构建调用图
-> 从显式或框架入口遍历
-> 报告不可达的项目内函数、方法和类
```

示例：

```bash
deadcodex mypackage/ --entry-point mypackage.cli.main
deadcodex mypackage/ --framework fastapi
deadcodex mypackage/ --framework flask --entry-point mypackage.worker.run
```

### 6.4 报告和基线流程

```bash
# JSON 输出
deadcodex mypackage/ --format json

# 生成独立 HTML 文件
deadcodex mypackage/ --format html --output deadcodex-report.html

# 接受当前问题并生成基线
deadcodex mypackage/ --baseline deadcodex-baseline.json --update-baseline

# 以后只显示新增问题
deadcodex mypackage/ --baseline deadcodex-baseline.json
```

## 7. 测试模块说明

本次新增或重点扩展的测试包括：

| 测试文件 | 覆盖内容 |
| --- | --- |
| `tests/test_architecture.py` | 分层兼容、独立解析器和收集器 |
| `tests/test_project.py` | 项目发现、模块限定名和作用域 |
| `tests/test_resolver.py` | 绝对、相对、别名和异常导入解析 |
| `tests/test_references.py` | 词法名称、属性和跨模块引用解析 |
| `tests/test_callgraph.py` | 本地、跨模块和方法调用图 |
| `tests/test_project_reachability.py` | 入口可达性、递归、异常入口和保守策略 |
| `tests/test_adapters.py` | 通用装饰器、Flask 和 FastAPI 入口发现 |
| `tests/test_pipeline.py` | 项目分析步骤及执行顺序 |
| `tests/test_reporters.py` | 文本、JSON、HTML 输出及安全转义 |
| `tests/test_baseline.py` | 基线更新、读取、过滤和命令行流程 |
| `tests/test_delivery.py` | 演示项目端到端执行和 CI 配置 |
| `tests/test_config.py` | 新增配置项合并和输入校验 |
| `tests/test_script.py` | 新命令行选项及退出行为 |

原有测试套件也全部保留，用于证明安全重构没有破坏已有功能。

## 8. 工程交付内容

### 8.1 CI

`.github/workflows/ci.yml` 配置了：

- 多 Python 版本测试矩阵。
- Ruff 代码检查。
- Ruff 格式检查。
- tox 构建、安装和完整测试。
- 最小只读仓库权限。

### 8.2 演示项目

`examples/demo_project/` 提供一个可直接静态分析的 FastAPI 示例，其中包含：

- 被框架装饰器识别的 API 入口。
- 从入口调用的业务函数。
- 一个不可达的旧函数。

它用于演示项目调用图、FastAPI 入口发现和未使用函数报告。

### 8.3 配套文档

- `docs/architecture.md`：技术架构和关键算法。
- `docs/course-report.md`：课程项目报告主体。
- `docs/defense-outline.md`：答辩结构和讲解重点。
- `docs/team-workflow.md`：六人协作和开发流程。
- `docs/demo-guide.md`：现场演示步骤。
- `docs/requirements-traceability.md`：需求、实现和测试追踪矩阵。
- `docs/refactoring-module-summary.md`：本文档，面向模块级总结。

## 9. 验证结果

本次最终验证结果：

- Python 3.12 pytest：`377 passed`，无跳过项。
- 单次完整测试覆盖率：`94%`。
- Ruff 代码检查：通过。
- Ruff 格式检查：通过。
- tox 构建、安装和测试：通过。
- 演示项目文本报告：通过。
- 演示项目 JSON 报告：通过。
- 演示项目 HTML 报告：通过。

CI 工作流文件已经完成并经过本地结构测试，但只有推送到 GitHub 后才会真正触发云端 GitHub Actions。

## 10. 当前版本边界

为了保证第一版可运行、可测试和可解释，当前没有尝试完整支持下列高度动态的 Python 行为：

- `importlib` 等运行时动态导入。
- 任意 `getattr()` 和字符串反射。
- monkey patch。
- 依赖运行时类型的完整多态分派。
- 复杂继承和 MRO 下的全面方法解析。
- Django 等框架的深度语义适配。
- IDE 插件和实时编辑器诊断。
- SaaS 服务、数据库和多人在线平台。

这些是第一版明确排除的范围，不属于当前未完成缺陷。对于无法确认的调用和引用，当前实现优先选择保守保留，降低误报风险。

## 11. 后续适合继续开发的能力

建议下一阶段按照下面的顺序继续：

1. 增加分析过程的统计信息和可解释诊断，例如展示某个引用为何未解析。
2. 补充 Django、Click、Typer、pytest fixture 等专用入口适配器。
3. 扩展静态类层次和有限多态调用解析。
4. 支持常见常量字符串形式的 `getattr()` 和 `importlib.import_module()`。
5. 将调用图导出为 JSON、DOT 或交互式 HTML 可视化。
6. 增加差异报告，使 CI 只阻止本次提交新增的死代码。
7. 在接口稳定后再考虑 IDE 集成或服务化部署。

## 12. 总结

本次重构将 Vulture 从集中式 AST 访问器逐步演进为分层静态分析架构。默认模式保持原有行为，项目级能力通过显式入口和框架适配按需启用。各分析阶段之间通过领域模型连接，使导入解析、引用解析、调用图、报告格式和框架集成都可以独立测试和继续扩展。
