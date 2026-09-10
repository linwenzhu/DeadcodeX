# DeadCodex 六人均衡分工与代码阅读清单

## 1. 分工目标

本方案面向六人课程小组，按“实现复杂度 + 测试量 + 集成责任 + 文档与评审”分配工作，而不是只按文件数或代码行数分配。每个人都负责一个可以独立讲解、实现和验收的端到端任务包。

统一估算为每人 34 小时，总计 204 人时。实际执行允许在 31～37 小时内波动；如果某项超过估算，应优先在同一接口边界内调剂，不把临时工作全部转给工程化负责人。

当前共同验收基线为：Python 3.12 下 377 个测试通过、无跳过项，覆盖率 94%，Ruff、格式检查以及 tox 的 wheel 构建安装测试通过。

## 2. 总体分配

| 成员 | 任务包 | 主责生产代码 | 主责测试 | 估算 |
|---|---|---|---|---:|
| A | 解析与 AST 信息采集 | `parser.py`、`collector.py`、`noqa.py`、`lines.py`，以及 `core.py` 的扫描部分 | AST、语法、编码、忽略规则和原行为回归 | 34 h |
| B | 领域模型与分析基础 | `model.py`、`scope.py`、`project.py`、`analysis.py`、`pipeline.py` | 模型、作用域、项目加载、限定名分析和架构边界 | 34 h |
| C | 导入与引用解析 | `resolver.py`，以及 Collector/Model 中的解析契约 | 导入绑定、相对导入、同名符号、引用状态 | 34 h |
| D | 控制流、调用图与项目可达性 | `reachability.py`、`callgraph.py`，以及 `core.py` 的项目分析部分 | 语句不可达、调用边、入口点、路径解释 | 34 h |
| E | 配置、CLI 与框架入口 | `config.py`、`adapters.py`、`__main__.py`，以及 `core.py:main()` | 配置优先级、命令行、Flask/FastAPI/自定义装饰器 | 34 h |
| F | 报告、Baseline 与可交付工程 | `reporters.py`、`baseline.py`，以及 `core.py:report()`、打包和 CI 文件 | 输出格式、Baseline、安装包、示例和发布验收 | 34 h |

工作量均衡不代表代码行数完全相等。例如 C 的文件较少，但名称解析、相对导入和歧义状态需要大量边界测试；F 的工程文件较多，但各模块内部逻辑相对独立。每人的估算都包含测试、文档和审查，不再由 F 一人承担全项目收尾。

## 3. `core.py` 的方法级所有权

`core.py` 是兼容门面，不能整体交给一个人。按方法拆分如下：

| 代码范围 | 第一负责人 | 需要共同审查的人 |
|---|---|---|
| `DeadCodex.__init__()`、`scan()`、`_handle_syntax_error()`、`scavenge()` | A | B；涉及 Resolver 时增加 C |
| `resolve_imports()`、`resolve_references()` | C | A、D |
| `get_unused_code(..., qualified=True)` | B | C |
| `analyze_reachability()`、`get_unused_code_project()` | D | C、E |
| `report()` | F | B、D、E |
| `main()` | E | F |

文件顶部 import 由修改对应方法的人同步维护。任何改变 `DeadCodex` 公共 API、默认行为或退出码的修改，至少需要表中一名共同审查人批准。

其余辅助文件按内容归属：A 主责 `utils.py` 的文件读取、路径、装饰器名称和日志容器以及 `whitelists/`；D 主责其中的常量条件求值；B 主责 `__init__.py` 的公共 Python API；E 主责 `__main__.py`；F 主责 `version.py` 和发布元数据。`ExitCode` 的值由 E 与 F 共同审查。

## 4. 成员 A：解析与 AST 信息采集

### 目标

保证 Python 源码能稳定转换成后续分析需要的定义、使用、导入和调用信息，同时尽量保持原 Vulture 的单文件检测行为。

### 必须理解的代码

- `deadcodex/parser.py`
  - `ParsedModule`：解析结果、源码、文件名和错误的统一载体。
  - `PythonParser.parse()`：`ast.parse()` 的封装和异常保留方式。
- `deadcodex/collector.py`
  - `AstCollector.prepare_module()`、`collect()`：一次模块分析的状态初始化和遍历入口。
  - `_define()`、`_define_variable()`：把 AST 节点转换为 `Item`，并设置限定名、作用域、置信度和行号。
  - `_add_aliases()`、`visit_Import()`、`visit_ImportFrom()`：把 import 语句记录为导入定义与 `ImportBinding`。
  - `visit_FunctionDef()`、`visit_ClassDef()`、`visit_Assign()`、`visit_Name()`、`visit_Attribute()`：定义和使用的主要采集规则。
  - `_record_usage()`、`_record_call()`、`_attribute_parts()`：为 C 和 D 生成引用及调用现场。
  - `visit()`、`generic_visit()`：与语句可达性、类型注解和 `noqa` 的兼容处理。
- `deadcodex/noqa.py`、`deadcodex/lines.py`
  - 行号范围、`# noqa` 指令和忽略错误码的计算。
- `deadcodex/core.py`
  - `scan()`、`scavenge()`：Parser、ScopeCollector、AstCollector 的调用顺序，以及白名单和输入错误处理。

### 具体任务

1. 维护 PythonParser 与 ParsedModule，确保语法错误、空字节、编码错误不会破坏整个项目扫描。
2. 维护类、函数、异步函数、方法、属性、变量、参数和 import 的定义采集。
3. 维护普通名称、属性链、格式化字符串、`__all__`、`locals()`、模式匹配等使用采集规则。
4. 为 C 输出完整的 `ImportBinding` 与 `UsageReference`，为 D 输出完整的 `CallSite`；不在 Collector 中直接决定跨模块目标。
5. 保持 ignore name、ignore decorator、测试文件规则、白名单和 `noqa` 行为兼容。
6. 负责扫描阶段错误信息和退出状态，确保一个坏文件不会导致其他合法文件丢失。
7. 补充对应正常、边界和失败路径测试，并记录与原版 Vulture 的兼容差异。

### 主责测试文件

- `tests/test_scavenging.py`
- `tests/test_format_strings.py`
- `tests/test_encoding.py`
- `tests/test_errors.py`
- `tests/test_ignore.py`
- `tests/test_noqa.py`
- `tests/test_size.py`
- `tests/test_confidence.py`
- `tests/test_utils.py` 中除常量条件求值外的用例

涉及导入目标的断言与 C 共同维护；涉及语句不可达的断言与 D 共同维护。

### 工时拆分

| 工作 | 工时 |
|---|---:|
| 阅读原行为、Parser 和 Collector 数据流 | 5 h |
| 定义、使用、导入和调用采集实现 | 14 h |
| 语法、编码、忽略与兼容边界 | 5 h |
| 单元测试和回归测试 | 7 h |
| 文档、代码审查和答辩准备 | 3 h |
| 合计 | 34 h |

### 验收标准

- 单文件默认检测结果不因架构拆分发生无说明的变化。
- 每一种定义类型都有定义和使用测试。
- Parser 的 SyntaxError、ValueError 和编码错误路径均有测试。
- Collector 只负责“采集事实”，不承担跨模块解析和可达性判断。

## 5. 成员 B：领域模型与分析基础

### 目标

建立所有分析阶段共享且稳定的数据语言，使单文件兼容分析和项目级分析可以共存。

### 必须理解的代码

- `deadcodex/model.py`
  - `QualifiedName`：模块、类、函数和符号的稳定身份。
  - `ScopeKind`、`ImportKind`、`UsageKind`、`ResolutionStatus`：分析状态枚举。
  - `ImportBinding`、`UsageReference`、`CallSite`、`CallEdge`：模块间的接口数据。
  - `CallGraph`、`ReachabilityResult`：图、路径和解释结果。
  - `Scope`、`ModuleModel`、`ProjectModel`：项目层级、索引和重复扫描重置。
  - `Item`、`Finding`：兼容内部对象与稳定报告对象的区别。
- `deadcodex/scope.py`
  - `ScopeCollector` 如何建立模块、类和函数的嵌套作用域。
- `deadcodex/project.py`
  - 源码根目录推导、路径到模块名转换、命名空间包和多输入路径合并。
- `deadcodex/analysis.py`
  - 名称级 `get_unused_code()` 与限定名级 `get_unused_code_qualified()` 的差别。
- `deadcodex/pipeline.py`
  - `Analyzer` 协议和 ImportResolver → ReferenceResolver → CallGraphBuilder 的编排。
- `deadcodex/core.py`
  - `get_unused_code(..., qualified=True)` 如何在保持默认行为的同时启用限定名分析。

### 具体任务

1. 维护领域模型字段、不可变性、相等性、哈希和序列化语义。
2. 定义 `QualifiedName` 生成规则，确保同名函数可按模块和作用域区分。
3. 维护 ProjectLoader 的模块发现、公共根目录计算、重复路径去重和模块索引。
4. 维护 ScopeCollector 的嵌套作用域和 AST 节点到 Scope 的映射。
5. 维护传统名称级 unused 算法和可选的限定名级 unused 算法，明确兼容边界。
6. 维护 ProjectAnalyzer 的阶段协议，不让上游直接依赖下游私有实现。
7. 评审所有领域模型字段变更，并给 C、D、E、F 提供迁移说明。

### 主责测试文件

- `tests/test_item.py`
- `tests/test_project.py`
- `tests/test_pipeline.py`
- `tests/test_architecture.py`
- `tests/test_sorting.py`

`tests/test_references.py` 中的限定名断言由 B 与 C 共同维护；`ReachabilityResult` 的路径测试由 B 与 D 共同维护。

### 工时拆分

| 工作 | 工时 |
|---|---:|
| 阅读数据流并冻结公共模型契约 | 6 h |
| Model、Item、Finding 和状态模型 | 11 h |
| Project、Scope 与 Pipeline | 8 h |
| 限定名分析和对应测试 | 6 h |
| 文档、接口评审和答辩准备 | 3 h |
| 合计 | 34 h |

### 验收标准

- `a.run` 与 `b.run` 可以被独立表示和比较。
- 重复扫描不会遗留旧 Scope、Reference 或 CallSite。
- 默认名称级 API 保持兼容，项目级 API 使用限定名。
- 跨模块接口均使用模型对象，不用无约束字典传递核心状态。

## 6. 成员 C：导入与引用解析

### 目标

把 A 采集到的导入和使用事实解析为项目内的准确目标，并对无法静态确定的情况给出显式状态。

### 必须理解的代码

- `deadcodex/resolver.py`
  - `ImportResolver.resolve()`、`_resolve_binding()`：逐模块解析导入绑定。
  - `_resolve_base()`、`_resolve_module()`：绝对导入、相对导入和父包定位。
  - `_is_external()`：项目外依赖的判定。
  - `ReferenceResolver.resolve()`、`_resolve_reference()`：为每个使用点选择候选目标。
  - `_resolve_name()`、`_resolve_imported_name()`：词法作用域与导入别名的查找顺序。
  - `_candidate_status()`：RESOLVED、AMBIGUOUS、UNRESOLVED、EXTERNAL 的产生条件。
  - `_attribute_target()`、`_instance_attribute_target()`：模块属性和实例属性的保守解析。
- `deadcodex/collector.py`
  - `_add_aliases()`、`_record_usage()`、`_attribute_parts()` 输出了哪些原始信息。
- `deadcodex/model.py`
  - `ImportBinding`、`UsageReference`、`Scope`、`QualifiedName` 和 `ResolutionStatus`。
- `deadcodex/project.py`
  - ProjectModel 的模块索引和模块名规则。
- `deadcodex/core.py`
  - `resolve_imports()`、`resolve_references()` 的执行时机及幂等要求。

### 具体任务

1. 支持 `import x`、`import x as y`、`from x import y`、别名和相对导入。
2. 区分项目内部模块、外部依赖、找不到的模块和多候选模块。
3. 按当前作用域、父作用域、模块定义和导入绑定解析普通名称。
4. 解析模块属性、类成员和可保守确认的实例属性，不对动态语义猜唯一结果。
5. 维护四种解析状态，并确保 D 能据此构造可信、歧义或未解析的调用信息。
6. 为同名符号、循环导入、namespace package、star import 限制和动态属性补充边界测试。
7. 与 A 共同维护采集契约，与 B 共同审核模型变更，与 D 共同审核目标格式。

### 主责测试文件

- `tests/test_imports.py`
- `tests/test_resolver.py`
- `tests/test_references.py`

此外，负责在 `tests/test_project.py` 中补充与模块名解析直接相关的用例。

### 工时拆分

| 工作 | 工时 |
|---|---:|
| 阅读 Collector、Model 和 Project 契约 | 5 h |
| ImportResolver 与 ReferenceResolver 实现 | 15 h |
| 歧义、外部和动态语义的状态设计 | 5 h |
| 单元、契约和回归测试 | 6 h |
| 文档、代码审查和答辩准备 | 3 h |
| 合计 | 34 h |

### 验收标准

- 内部导入可以定位到稳定的 QualifiedName。
- 同名候选不会被随意选中，而是返回 AMBIGUOUS。
- 外部依赖与项目内未解析引用可以区分。
- Resolver 多次运行结果一致，不重复产生引用目标或调用边。

## 7. 成员 D：控制流、调用图与项目可达性

### 目标

同时负责函数内部的不可达语句检测和项目级入口到调用目标的可达性分析，并清楚区分这两类“可达性”。

### 必须理解的代码

- `deadcodex/reachability.py`
  - `Reachability.visit()`、`_can_fall_through()`：函数内部控制流状态。
  - `_handle_reachability_if()`、`_handle_reachability_while()`、`_handle_reachability_try()`：常量条件、循环、异常和终止语句处理。
- `deadcodex/callgraph.py`
  - `CallGraphBuilder.build()`、`_resolve_call()`：从 CallSite 和 UsageReference 构造调用边。
  - `ReachabilityAnalyzer.analyze()`：入口点校验、BFS/队列遍历、前驱记录和 unreachable 计算。
- `deadcodex/model.py`
  - `CallSite`、`CallEdge`、`CallGraph`、`ReachabilityResult.path_to()` 和 `explain()`。
- `deadcodex/collector.py`
  - `_record_call()` 如何产生调用现场，`visit()` 如何调用语句级 Reachability。
- `deadcodex/resolver.py`
  - ReferenceResolver 的目标和状态是调用图的输入，而不是由 CallGraphBuilder 重新猜测。
- `deadcodex/adapters.py`
  - EntryPointProvider 如何向项目可达性提供入口。
- `deadcodex/core.py`
  - `analyze_reachability()`、`get_unused_code_project()` 如何合并限定名 unused 和不可达 callable。

### 具体任务

1. 维护 `if`、条件表达式、`while`、`try`、`return`、`raise`、`break`、`continue` 后的语句级不可达判断。
2. 把已解析 CallSite 转换为 CallEdge，同时保留 unresolved 和 ambiguous 调用信息。
3. 维护显式入口点和 Provider 入口点的合并、校验及去重。
4. 使用图遍历计算 reachable/unreachable，并记录可解释的前驱路径。
5. 对不存在或歧义入口点产生明确错误，不静默给出误导报告。
6. 未解析调用采用保守策略，避免把可能被调用的同名函数误报为死代码。
7. 为递归、互递归、类方法、跨模块调用、多入口和断路控制流补充测试。

### 主责测试文件

- `tests/test_reachability.py`
- `tests/test_conditions.py`
- `tests/test_callgraph.py`
- `tests/test_project_reachability.py`

`tests/test_utils.py` 中的常量条件求值用例也由 D 负责。

调用目标解析失败的根因测试由 C 负责，D 负责验证这些状态进入调用图后的行为。

### 工时拆分

| 工作 | 工时 |
|---|---:|
| 阅读两类可达性与上下游契约 | 5 h |
| 函数内部控制流不可达分析 | 10 h |
| 调用图、项目可达性和路径解释 | 10 h |
| 单元、集成和复杂图测试 | 6 h |
| 文档、代码审查和答辩准备 | 3 h |
| 合计 | 34 h |

### 验收标准

- 语句不可达和项目 callable 不可达使用不同模型和测试说明。
- 递归和环不会导致无限遍历。
- `explain()` 能给出可达路径或不可达/无效入口原因。
- unresolved/ambiguous 调用不会被伪装成可信调用边。

## 8. 成员 E：配置、CLI 与框架入口

### 目标

让项目级能力可以通过稳定命令行选择，并通过可插拔 Provider 识别框架入口，同时保证默认分析不被框架规则影响。

### 必须理解的代码

- `deadcodex/config.py`
  - `_parse_args()`：全部 CLI 参数、类型和默认值。
  - `_parse_toml()`：`pyproject.toml` 配置读取。
  - `_check_input_config()`、`_check_output_config()`：输入校验和跨参数约束。
  - `make_config()`：默认值、配置文件和命令行的合并优先级。
- `deadcodex/adapters.py`
  - `EntryPointProvider`、`FrameworkAdapter` 协议。
  - `DecoratorEntryPointAdapter.discover()`：规范化装饰器模式并发现入口。
  - `FlaskAdapter`、`FastAPIAdapter`、`make_framework_adapter()`：内置适配器与工厂。
- `deadcodex/core.py`
  - `main()` 如何从配置创建 DeadCodex、Provider 和 Reporter 流程。
  - `analyze_reachability()` 如何消费 Provider 输出。
- `deadcodex/__main__.py`、`pyproject.toml`
  - `python -m deadcodex` 和 `deadcodex` 命令的入口关系。

### 具体任务

1. 维护 CLI 参数、帮助文本、错误提示和退出码，并保持 `deadcodex` 包名与 1.0 版本交付一致。
2. 维护命令行 > `pyproject.toml` > 默认值的配置优先级以及非法组合校验。
3. 维护 EntryPointProvider 协议和装饰器模式的规范化、匹配与去重。
4. 维护 Flask、FastAPI 和自定义装饰器入口；所有框架规则必须显式启用。
5. 将配置转换成 DeadCodex 调用，不把 argparse/config 字典传播到分析内核。
6. 覆盖文本、JSON、HTML、baseline、entry point、framework 等 CLI 组合的参数传递；输出内容本身由 F 测试。
7. 为 README 中的命令示例和框架使用章节提供准确内容，F 只负责统一发布格式。

### 主责测试文件

- `tests/test_config.py`
- `tests/test_adapters.py`
- `tests/test_script.py`

`tests/test_delivery.py` 中命令入口和安装后执行部分由 E 与 F 共同维护。

### 工时拆分

| 工作 | 工时 |
|---|---:|
| 阅读用户流程、配置和入口协议 | 5 h |
| Config、CLI 校验与 `main()` 集成 | 10 h |
| 通用、Flask 和 FastAPI 入口适配 | 8 h |
| CLI、配置、Adapter 测试与示例 | 8 h |
| 文档、代码审查和答辩准备 | 3 h |
| 合计 | 34 h |

### 验收标准

- `deadcodex` 与 `python -m deadcodex` 都能运行。
- 同一配置项的优先级确定且有测试。
- 未指定 `--framework` 时不自动应用 Flask/FastAPI 规则。
- 未知框架、无效入口点和冲突输出参数给出可理解的错误。

## 9. 成员 F：报告、Baseline 与可交付工程

### 目标

把分析结果稳定地交付给人和自动化工具，保证项目可以安装、复现、验证和演示；不代替其他成员编写其模块测试和说明。

### 必须理解的代码

- `deadcodex/reporters.py`
  - `Reporter` 协议、`ConsoleReporter`、`JsonReporter`、`HtmlReporter` 和 `make_reporter()`。
  - `Finding.from_item()` 与 HTML 转义、稳定排序和末尾换行约定。
- `deadcodex/baseline.py`
  - `BaselineEntry.from_item()`、`Baseline.load()`、`filter()`、`write()`。
  - 相对路径和 `_fingerprint()` 如何让普通代码移动后仍尽量稳定。
- `deadcodex/core.py`
  - `report()` 中分析模式选择、baseline 更新/过滤、输出文件和退出码。
- `deadcodex/model.py`
  - `Item.get_report()`、`get_whitelist_string()`、`Finding.to_dict()` 的输出契约。
- 工程文件
  - `pyproject.toml`、`tox.ini`、`MANIFEST.in`、`uv.lock`、`.github/workflows/`、`.gitignore`。
- 示例和交付文档
  - `examples/`、`README.md`、`docs/course-report.md` 和变更记录。

### 具体任务

1. 维护文本、JSON 和 HTML Reporter，保证转义、排序、字段和空结果行为稳定。
2. 维护 Baseline 的版本校验、指纹、读取、过滤、更新和损坏文件错误路径。
3. 维护 `report()` 的输出选择、文件写入、白名单限制和退出码。
4. 维护 wheel/sdist 包含内容、console script、uv/tox 使用方式和多 Python CI。
5. 维护一个最小端到端 Demo 和全项目验收脚本；各功能示例内容由对应成员提供。
6. 汇总 README、架构文档和课程报告，但每个成员必须提交自己模块的原理、限制和演示说明。
7. 发布前执行完整测试、覆盖率、Ruff、格式和安装后测试，并记录可复现结果。

### 主责测试文件

- `tests/test_report.py`
- `tests/test_reporters.py`
- `tests/test_baseline.py`
- `tests/test_delivery.py`
- `tests/test_examples.py`
- `tests/test_make_whitelist.py`

### 工时拆分

| 工作 | 工时 |
|---|---:|
| 阅读输出契约、Baseline 和构建流程 | 5 h |
| Reporter、Baseline 与 `report()` | 8 h |
| 打包、uv/tox 和 CI | 7 h |
| 示例、集成验收和交付文档汇总 | 8 h |
| 全量质量检查、代码审查和答辩准备 | 6 h |
| 合计 | 34 h |

### 验收标准

- 三种报告格式对同一批 Item 给出语义一致的结果。
- HTML 中的文件名和符号名均安全转义，JSON 可被标准解析器读取。
- Baseline 更新和过滤可复现，错误版本或损坏文件不会被静默忽略。
- 从构建出的 wheel 安装后仍能运行 CLI 和完整测试。

## 10. 公共接口与交接关系

```text
A Parser/Collector ---- ImportBinding、UsageReference ----> C Resolver
        |                                                   |
        | Item、CallSite                                    | 已解析目标和状态
        v                                                   v
B Model/Project/Scope -------------------------------> D CallGraph/Reachability
        |                                                   ^
        | Finding、ProjectModel                             | EntryPoint
        v                                                   |
F Reporter/Baseline <------ 分析结果 ------ Core ------ E Config/CLI/Adapter
```

必须冻结的接口包括：

- A → C：`ImportBinding` 和 `UsageReference` 字段及属性链顺序。
- A/C → D：`CallSite`、已解析目标和 `ResolutionStatus` 语义。
- B → 全员：`QualifiedName`、`Scope`、`ModuleModel`、`ProjectModel` 的身份规则。
- E → D：`EntryPointProvider.discover()` 返回 `frozenset[QualifiedName]`。
- B/D → F：`Item`、`Finding` 和项目可达性结果的公开字段。
- E/F → 用户：CLI 参数、输出格式、退出码和 baseline 文件格式。

接口字段变化必须在 Pull Request 中写出调用方、兼容影响和迁移方式。未知动态行为统一表示为 unresolved 或 ambiguous，不由任何成员私自改为“猜测成功”。

## 11. 测试、审查与文档责任

每个人的任务包都必须包含：

1. 自己模块的正常路径测试。
2. 至少一个边界条件和一个失败路径测试。
3. 对外接口的契约测试。
4. README 或 `docs/` 中对应模块的说明。
5. 对另一名成员 Pull Request 的一次有效审查。

固定交叉审查配对：

| 作者 | 第一审查人 | 审查重点 |
|---|---|---|
| A | B | AST 信息是否正确进入模型，是否破坏兼容行为 |
| B | A | 模型是否足够支撑采集，是否增加不必要耦合 |
| C | D | 解析状态能否安全构造调用边 |
| D | C | 调用图是否尊重 Resolver 状态和保守策略 |
| E | F | CLI 配置能否稳定进入报告和交付流程 |
| F | E | 打包后的命令和各输出选项是否真正可用 |

全量回归和最终报告由 F 组织执行，但失败测试按上面的主责文件退回相应负责人修复。覆盖率下降也由新增未覆盖代码的作者负责，而不是默认交给 F。

## 12. 六周执行安排

| 周次 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| 1 | 原 Collector 行为 | 冻结模型接口 | 解析契约与夹具 | 两类可达性边界 | CLI/配置清单 | 输出与构建基线 |
| 2 | Parser 与定义采集 | Model/Scope | ImportResolver | 语句不可达 | Config/CLI | Reporter |
| 3 | 使用、导入、调用采集 | Project/Analysis | ReferenceResolver | CallGraph | Adapter | Baseline |
| 4 | 扫描兼容联调 | Pipeline/限定名 | 跨模块联调 | 项目可达性 | CLI 项目选项联调 | 打包/CI |
| 5 | 回归与修缺 | 模型边界修缺 | 歧义用例修缺 | 复杂图修缺 | 框架 Demo | 集成与报告汇总 |
| 6 | 文档/答辩 | 文档/答辩 | 文档/答辩 | 文档/答辩 | 文档/答辩 | 发布验收/答辩 |

每周至少进行一次全量 pytest；第 4 周和第 6 周运行完整 tox。若成员提前完成主责任务，应先处理其测试、文档和审查清单，再帮助相邻接口成员，不能只用新增功能数量衡量工作量。

## 13. 每人的答辩边界

- A 能用一段 Python 代码说明 AST 如何变成定义、使用和调用现场。
- B 能说明为什么 QualifiedName、Scope 和 ProjectModel 能解决同名符号问题。
- C 能演示绝对导入、相对导入、别名和歧义引用分别如何解析。
- D 能画出调用图，解释入口、路径、递归和不可达结果，并区分语句不可达。
- E 能从命令行参数讲到框架装饰器入口被发现的完整路径。
- F 能演示三种报告、Baseline、uv/tox、wheel 安装和 CI 验收。

这样每个人都既有核心代码，也有可展示功能、测试证据和文档产出，工作量与答辩内容基本对等。
