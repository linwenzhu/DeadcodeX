# DeadCodex internal architecture

The first refactoring stage separates the existing single-process analysis into
four layers without changing DeadCodex's name-based dead-code algorithm.

```text
paths  ->  ProjectLoader  ->  ProjectModel / ModuleModel
                                 |
source text  ->  PythonParser  ->  ParsedModule
                                 |
                     +-----------+-----------+
                     |                       |
                     v                       v
               ScopeCollector          AstCollector
                     |                       |
                     v                       v
                   Scope              AnalysisResult -> Item -> Finding
                     ^                       ^
                     +-----------+-----------+
                                 |
             DeadCodex (error handling, reporting and CLI orchestration)
                                 |
                                 v
                         ProjectAnalyzer
                                 |
                                 v
                         ImportResolver
                                 |
                                 v
                        ReferenceResolver
                                 |
                                 v
                        CallGraphBuilder
                                 |
                                 v
                            CallGraph -----------+
                                                 v
                      EntryPointProvider -> ReachabilityAnalyzer
                                                 |
                                                 v
                                      ReachabilityResult
                                                 |
                    +----------------------------+------------------+
                    v                            v                  v
                 Baseline                   JSON/HTML          Console
```

## Responsibilities

- `model.py` contains stable domain values such as `Item` and reporter-facing
  `Finding`.
- `parser.py` turns source text into an AST and keeps filename, source-line and
  `noqa` metadata together in `ParsedModule`.
- `project.py` discovers files, derives dotted module names and reads source
  through `ProjectLoader`.
- `model.py` also contains `ProjectModel`, `ModuleModel`, `QualifiedName` and
  lexical `Scope` objects for project-level analysis.
- `scope.py` builds class and function scope trees independently from the
  existing dead-code algorithm.
- `resolver.py` resolves recorded imports against project modules and qualified
  items, then resolves recorded name and attribute reads through lexical scopes
  and import aliases after all files have been scanned.
- `callgraph.py` matches collected call sites with resolved references and
  produces qualified, project-local caller-to-callee edges. It also traverses
  those edges from explicit entry points.
- `adapters.py` defines the `EntryPointProvider` and `FrameworkAdapter`
  protocols, a framework-neutral decorator matcher, and Flask/FastAPI
  implementations.
- `collector.py` owns AST traversal and records definitions, usages and
  unreachable code, as well as call sites for later graph construction.
- `analysis.py` owns cumulative analysis state and computes unused items.
- `pipeline.py` defines the shared `Analyzer` protocol and orders project-wide
  import, reference and call-graph passes through `ProjectAnalyzer`.
- `reporters.py` renders the same findings as compatible text, versioned JSON
  or escaped standalone HTML.
- `baseline.py` creates stable fingerprints and filters previously accepted
  findings.
- `core.py` is the public facade and coordinates scanning files,
  loading bundled whitelists, handling errors and producing reports.

`DeadCodex` still inherits from `ast.NodeVisitor` through `AstCollector`, and
`Item`, `DEFAULT_CONFIDENCE` and `ERROR_CODES` are importable from
`deadcodex.core` as convenience API symbols.

Each collected `Item` now has an optional `qualified_name`. For example, two
functions called `run` in `a.py` and `b.py` are represented as `a.run` and
`b.run`. Reports and equality deliberately continue to use the legacy fields;
qualified filtering is available through a separate experimental option.

## Import resolution

Each `ModuleModel` owns `ImportBinding` records. Absolute imports, relative
imports, aliases, star imports and package re-exports can resolve to a local
qualified module or symbol. Every binding has one explicit state:

- `resolved`: exactly one local target was found;
- `external`: the absolute import is outside the scanned project;
- `unresolved`: an expected project-relative target was not found;
- `ambiguous`: duplicate module or symbol candidates were found;
- `pending`: collection completed but resolution has not yet run.

The resolver also records each AST name or attribute read as a
`UsageReference`. References retain their source scope and can point both to a
local import binding and its resolved remote target.

`DeadCodex.get_unused_code(qualified=True)` exposes an experimental qualified-name
result. It only narrows legacy name matching when every reference with that
short name resolves safely; unresolved or ambiguous references keep the legacy
fallback. The default method call and CLI still use the original name-based
algorithm.

## Call graph

Every `ModuleModel` owns `CallSite` records. After reference resolution,
`CallGraphBuilder` turns calls with one statically resolved project-local class,
function or method target into `CallEdge` records. The graph preserves all call
sites, including external, unresolved and ambiguous calls, so consumers do not
need to infer uncertainty from missing edges. `DeadCodex.resolve_references()`
returns the generated graph, which is also available as `DeadCodex.call_graph`.

The graph does not alter default unused-code results or CLI output. Dynamic
dispatch and framework-defined entry points remain explicit extension layers
rather than assumptions in the core collector.

## Project reachability

`ReachabilityAnalyzer` accepts qualified modules, classes, functions or methods
as explicit entry points. It detects missing and ambiguous entries, traverses
recursive graphs safely, and records one deterministic predecessor chain for
each reachable node. `ReachabilityResult.path_to()` and `.explain()` expose
those decisions without coupling presentation to graph construction.

`DeadCodex.get_unused_code_project()` replaces name-based callable results with
unreachable project callables while retaining qualified analysis for imports,
variables, properties and unreachable statements. Unresolved or ambiguous call
names are kept conservative. This mode is opt-in through repeatable
`--entry-point QUALIFIED_NAME` arguments; invoking DeadCodex without entry points
continues to use the original algorithm.

## Framework entry-point adapters

Framework integration is isolated behind `EntryPointProvider.discover()`.
`DecoratorEntryPointAdapter` matches the decorator names already collected on
classes, functions and methods using glob patterns. It can be supplied through
the Python API or composed by the CLI through repeatable
`--entry-point-decorator PATTERN` arguments. For example, `router.*` matches
decorators such as `@router.get` and `@router.post` without importing or naming
a specific web framework in the analyzer core.

Adapters only contribute roots to the same reachability algorithm; they cannot
silently change reference resolution or default reports. More specialized
framework packages can implement the protocol when decorator matching is not
enough.

## Reports and baseline

Reporter implementations consume unused `Item` objects and convert them to the
stable `Finding` schema where needed. Console rendering delegates to the legacy
`Item.get_report()` method, preserving the existing output contract. JSON
includes an explicit format and version, while HTML is self-contained and
escapes paths, symbol names and messages.

Baseline entries use a SHA-256 digest of the item kind, project-relative file
and qualified identity. Normal definitions therefore survive line movement.
Unreachable statements without a qualified identity include their line number
to remain distinguishable. `--update-baseline` records the current result and
returns success; later runs with `--baseline` remove known entries before
reporting.
