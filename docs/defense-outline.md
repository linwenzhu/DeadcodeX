# DeadCodex 答辩提纲

## 答辩目标

用十二页内容说明项目为什么需要重构、系统如何协作、项目级模式如何降低误报，以及六人团队如何通过测试和工程化交付控制风险。建议总时长十二至十五分钟，演示三分钟，问答五分钟。

## 幻灯片安排

### 第一页 项目概览

- 项目名称、六人团队、基础项目 Vulture 2.16。
- 一句话目标：从名称级检测升级为可选的项目级、跨文件、框架感知分析。
- 说明默认行为保持兼容。

### 第二页 原问题

- 展示 `a.run` 与 `b.run` 同名时名称集合无法区分的例子。
- 展示 FastAPI 路由没有显式调用却会被框架执行的例子。
- 得出需要限定名、调用关系和框架入口的结论。

### 第三页 需求与范围

- 第一版功能：Symbol、Import Resolver、Call Graph、Reachability、Flask/FastAPI、Reporter、Baseline、CI。
- 明确不做动态 import、完整多态和 Web SaaS。

### 第四页 重构前后架构

- 重构前：一个核心类同时解析、遍历、分析和报告。
- 重构后：Parser、Collector、Model、Resolver、Call Graph、Adapter、Reporter。
- 强调 `DeadCodex` 是分层分析门面。

### 第五页 项目符号与导入解析

- 演示 `service.run`、`module.Class.run`。
- 展示 import、from import 和 alias 如何映射到目标。
- 说明 resolved、external、unresolved、ambiguous 状态。

### 第六页 Call Graph 与可达性

- 展示 `app -> service.run -> utils.log`。
- 说明 BFS、递归环处理和前驱路径。
- 演示不可达函数如何成为项目级候选。

### 第七页 Framework Adapter

- 展示 `@app.route` 与 `@router.get`。
- 说明 Adapter 只贡献入口，不侵入核心解析器。
- 展示 `--framework flask` 和 `--framework fastapi`。

### 第八页 Reporter 与 Baseline

- 对比 Console、JSON、HTML。
- 解释 Baseline 指纹和“只报告新增问题”的 CI 使用方式。

### 第九页 测试与质量

- 展示单元测试、集成测试、项目自扫描、覆盖率和 tox wheel。
- 展示 GitHub Actions 多版本矩阵。

### 第十页 六人协作

- 展示 A 至 F 的模块边界和接口关系。
- 说明 Code Review、分支策略、Definition of Done。

### 第十一页 现场演示

依次运行：

```bash
python -m deadcodex examples/demo_project --framework fastapi
python -m deadcodex examples/demo_project --framework fastapi --format json
python -m deadcodex examples/demo_project --framework fastapi --format html --output report.html
```

讲解路由函数和其依赖为什么不会被报告，旧函数为什么会被报告。

### 第十二页 总结与后续

- 已完成：架构重构、跨文件分析、框架入口、报告、Baseline、CI、Demo。
- 后续：函数值流、继承和 `super()`、Django/Pytest Adapter、SARIF。
- 总结项目价值：可运行、可测试、可扩展、范围受控。

## 常见问答准备

### 为什么不直接重写 Vulture

保留成熟 AST 和边缘语法处理可以降低回归风险；重构集中在职责边界和项目级信息，符合课程时间预算。

### 为什么 Call Graph 不能完全精确

Python 支持动态属性、运行时替换和反射。第一版对常见静态调用建立确定关系，对未知调用保留 unresolved 状态并采用保守策略。

### 如何证明没有破坏原工具

默认 CLI 没有入口配置时走原算法；原测试、项目自扫描、Ruff 和安装后 wheel 测试均作为质量门禁。

### Adapter 如何扩展

新增类实现 `EntryPointProvider.discover()` 即可贡献入口，不需要修改 Resolver 或 Reachability。

### Baseline 为什么不使用行号

普通定义使用限定名和相对路径作为稳定身份，代码上下移动时仍可匹配；只有没有限定名的不可达语句才使用行号区分。
