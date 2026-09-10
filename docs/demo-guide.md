# DeadCodex 演示手册

## 演示目的

本演示验证 FastAPI 隐式入口、项目调用可达性、JSON/HTML 报告和 Baseline。示例只进行静态分析，不需要安装或运行 FastAPI。

## 准备

在仓库根目录创建并激活开发环境，安装项目测试依赖。确认以下命令成功：

```bash
python -m deadcodex --version
```

## 场景一 框架感知检测

```bash
python -m deadcodex examples/demo_project --framework fastapi
```

预期结果只包含 `old_format_user`。`read_user` 由 `@app.get` 识别为入口，`serialize_user` 通过调用边可达。

## 场景二 JSON 报告

```bash
python -m deadcodex examples/demo_project --framework fastapi --format json
```

预期输出包含 `format`、`version` 和 `findings`，每条 Finding 包含名称、限定名、类型、文件、行号、大小、消息和置信度。

## 场景三 HTML 报告

```bash
python -m deadcodex examples/demo_project --framework fastapi \
  --format html --output demo-report.html
```

用浏览器打开 `demo-report.html`，确认汇总数量和表格内容正确。HTML 为独立文件，不依赖网络资源。

## 场景四 Baseline

先生成当前基线：

```bash
python -m deadcodex examples/demo_project --framework fastapi \
  --baseline demo-baseline.json --update-baseline
```

再次应用基线：

```bash
python -m deadcodex examples/demo_project --framework fastapi \
  --baseline demo-baseline.json
```

预期没有输出且退出码为 0。随后在示例中增加一个新的未调用函数，再次执行时只报告新问题。

## 场景五 显式入口与路径解释

Python API 示例：

```python
from deadcodex import DeadCodex

analyzer = DeadCodex()
analyzer.scavenge(["examples/demo_project"])
result = analyzer.analyze_reachability(["app.read_user"])
print(result.explain("app.serialize_user"))
```

预期解释为从 `app.read_user` 到 `app.serialize_user` 的可达路径。

## 故障处理

- 入口不存在：检查模块限定名是否相对于扫描根目录。
- 框架处理函数仍被报告：确认使用了 `--framework` 或正确的 `--entry-point-decorator`。
- Baseline 无法加载：确认文件是工具生成的 version 1 JSON。
- 报告文件没有生成：确认输出目录存在且可写。
