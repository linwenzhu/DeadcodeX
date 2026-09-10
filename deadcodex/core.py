import pkgutil
import sys
from pathlib import Path

from deadcodex import utils
from deadcodex.adapters import (
    DecoratorEntryPointAdapter,
    make_framework_adapter,
)
from deadcodex.baseline import Baseline
from deadcodex.callgraph import (
    CALLABLE_TYPES,
    CallGraphBuilder,
    ReachabilityAnalyzer,
)
from deadcodex.collector import ERROR_CODES as ERROR_CODES
from deadcodex.collector import AstCollector, _match
from deadcodex.config import InputError, make_config
from deadcodex.model import DEFAULT_CONFIDENCE as DEFAULT_CONFIDENCE
from deadcodex.model import CallGraph, ProjectModel, ResolutionStatus
from deadcodex.model import Item as Item
from deadcodex.parser import PythonParser
from deadcodex.pipeline import ProjectAnalyzer
from deadcodex.project import ProjectLoader
from deadcodex.reporters import make_reporter
from deadcodex.resolver import ImportResolver, ReferenceResolver
from deadcodex.scope import ScopeCollector
from deadcodex.utils import ExitCode


class DeadCodex(AstCollector):
    """Find dead code while preserving DeadCodex's public analysis API."""

    def __init__(
        self, verbose=False, ignore_names=None, ignore_decorators=None
    ):
        super().__init__(
            verbose=verbose,
            ignore_names=ignore_names,
            ignore_decorators=ignore_decorators,
        )
        self.parser = PythonParser()
        self.project_loader = ProjectLoader()
        self.import_resolver = ImportResolver()
        self.reference_resolver = ReferenceResolver()
        self.call_graph_builder = CallGraphBuilder()
        self.project_analyzer = ProjectAnalyzer(
            self.import_resolver,
            self.reference_resolver,
            self.call_graph_builder,
        )
        self.project_reachability_analyzer = ReachabilityAnalyzer()
        self.scope_collector = ScopeCollector()
        self.project = ProjectModel(root=Path())
        self.call_graph = CallGraph()
        self.project_reachability = None
        self.exit_code = ExitCode.NoDeadCode

    def scan(self, code, filename="", module=None):
        if module is None:
            module = (
                self.project.module_for_path(filename) if filename else None
            )
            if module is None:
                module = (
                    self.project_loader.module_from_path(filename)
                    if filename
                    else self.project_loader.in_memory_module()
                )
                self.project.add_module(module)
        else:
            filename = module.path

        module.reset_analysis()
        parsed_module = self.parser.parse(
            code, filename=filename, module=module
        )
        self.prepare_module(parsed_module)

        if isinstance(parsed_module.error, SyntaxError):
            self._handle_syntax_error(parsed_module.error)
            self.reachability.reset()
        elif isinstance(parsed_module.error, ValueError):
            # ValueError is raised if source contains null bytes.
            message = (
                f"{utils.format_path(parsed_module.filename)}: "
                f'invalid source code "{parsed_module.error}"'
            )
            self._log(
                message,
                file=sys.stderr,
                force=True,
            )
            self.exit_code = ExitCode.InvalidInput
            self.reachability.reset()
        else:
            self.scope_collector.collect(module, parsed_module.tree)
            # When parsing type comments, visiting can throw SyntaxError.
            try:
                self.collect(parsed_module)
            except SyntaxError as error:
                self._handle_syntax_error(error)

    def _handle_syntax_error(self, error):
        text = f' at "{error.text.strip()}"' if error.text else ""
        self._log(
            f"{utils.format_path(self.filename)}:{error.lineno}: "
            f"{error.msg}{text}",
            file=sys.stderr,
            force=True,
        )
        self.exit_code = ExitCode.InvalidInput

    def scavenge(self, paths, exclude=None):
        def prepare_pattern(pattern):
            if not any(char in pattern for char in "*?["):
                pattern = f"*{pattern}*"
            return pattern

        exclude = [prepare_pattern(pattern) for pattern in (exclude or [])]

        def exclude_path(path):
            return _match(path, exclude, case=False)

        discovered_project = self.project_loader.load(paths)
        discovered_modules = self.project.include(discovered_project)

        for module in discovered_modules:
            if exclude_path(module.path):
                self._log("Excluded:", module.path)
                continue

            self._log("Scanning:", module.path)
            try:
                module_string = self.project_loader.read_module(module)
            except utils.DeadCodexInputException as error:
                self._log(
                    f"Error: Could not read file {module.path} - {error}\n"
                    f"Try to change the encoding to UTF-8.",
                    file=sys.stderr,
                    force=True,
                )
                self.exit_code = ExitCode.InvalidInput
            else:
                self.scan(module_string, module=module)

        unique_imports = {item.name for item in self.defined_imports}
        for import_name in unique_imports:
            path = Path("whitelists") / (import_name + "_whitelist.py")
            if exclude_path(path):
                self._log("Excluded whitelist:", path)
            else:
                try:
                    module_data = pkgutil.get_data("deadcodex", str(path))
                    self._log("Included whitelist:", path)
                except OSError:
                    # Most imported modules don't have a whitelist.
                    continue
                assert module_data is not None
                module_string = module_data.decode("utf-8")
                self.scan(module_string, filename=path)

        self.resolve_references()

    def resolve_imports(self):
        return self.import_resolver.resolve(self.project, self.defined_items)

    def resolve_references(self):
        self.resolve_imports()
        self.call_graph = self.project_analyzer.analyze(
            self.project, self.defined_items, imports_resolved=True
        )
        return self.call_graph

    def get_unused_code(
        self, min_confidence=0, sort_by_size=False, qualified=False
    ) -> list[Item]:
        if not qualified:
            return super().get_unused_code(
                min_confidence=min_confidence, sort_by_size=sort_by_size
            )

        self.resolve_references()
        references = [
            reference
            for module in self.project.modules
            for reference in module.references
        ]
        return self.get_unused_code_qualified(
            references,
            min_confidence=min_confidence,
            sort_by_size=sort_by_size,
        )

    def analyze_reachability(self, entry_points=(), entry_point_providers=()):
        """Return project callables reachable from explicit entry points."""
        self.resolve_references()
        discovered_entry_points = list(entry_points)
        for provider in entry_point_providers:
            discovered_entry_points.extend(
                provider.discover(self.project, self.defined_items)
            )
        self.project_reachability = self.project_reachability_analyzer.analyze(
            self.project,
            self.defined_items,
            self.call_graph,
            discovered_entry_points,
        )
        return self.project_reachability

    def get_unused_code_project(
        self,
        entry_points=(),
        min_confidence=0,
        sort_by_size=False,
        entry_point_providers=(),
    ) -> list[Item]:
        """Return experimental project-aware unused items."""
        if not 0 <= min_confidence <= 100:
            raise ValueError("min_confidence must be between 0 and 100.")

        reachability = self.analyze_reachability(
            entry_points, entry_point_providers=entry_point_providers
        )
        invalid_entry_points = (
            reachability.unresolved_entry_points
            | reachability.ambiguous_entry_points
        )
        if invalid_entry_points:
            explanations = "; ".join(
                reachability.explain(target)
                for target in sorted(invalid_entry_points)
            )
            raise ValueError(
                f"Invalid or ambiguous entry points: {explanations}"
            )

        references = [
            reference
            for module in self.project.modules
            for reference in module.references
        ]
        qualified_unused = self.get_unused_code_qualified(references)
        non_callable_unused = {
            item for item in qualified_unused if item.typ not in CALLABLE_TYPES
        }
        uncertain_call_names = {
            call.callee_parts[-1]
            for call in self.call_graph.calls
            if call.callee_parts
            and call.status
            in {ResolutionStatus.UNRESOLVED, ResolutionStatus.AMBIGUOUS}
        }
        unreachable_callables = {
            item
            for item in self.defined_items
            if item.typ in CALLABLE_TYPES
            and item.qualified_name in reachability.unreachable
            and item.name not in uncertain_call_names
        }
        unused_items = non_callable_unused | unreachable_callables
        confidently_unused = [
            item for item in unused_items if item.confidence >= min_confidence
        ]

        def by_name(item):
            return str(item.filename).lower(), item.first_lineno

        def by_size(item):
            return item.size, *by_name(item)

        return sorted(
            confidently_unused, key=by_size if sort_by_size else by_name
        )

    def report(
        self,
        min_confidence=0,
        sort_by_size=False,
        make_whitelist=False,
        entry_points=None,
        entry_point_providers=(),
        output_format="text",
        output="",
        baseline="",
        update_baseline=False,
    ):
        """Print an ordered list of unused items to stdout."""
        if make_whitelist and output_format != "text":
            raise ValueError("Whitelist output requires the text format.")
        if entry_points or entry_point_providers:
            unused_code = self.get_unused_code_project(
                entry_points or (),
                min_confidence=min_confidence,
                sort_by_size=sort_by_size,
                entry_point_providers=entry_point_providers,
            )
        else:
            unused_code = self.get_unused_code(
                min_confidence=min_confidence, sort_by_size=sort_by_size
            )

        if update_baseline:
            if not baseline:
                raise ValueError(
                    "Updating a baseline requires a baseline path."
                )
            Baseline.from_items(unused_code, self.project.root).write(baseline)
            self.exit_code = ExitCode.NoDeadCode
            return self.exit_code
        if baseline:
            unused_code = Baseline.load(baseline).filter(
                unused_code, self.project.root
            )

        if make_whitelist:
            content = "\n".join(
                item.get_whitelist_string() for item in unused_code
            )
            if content:
                content += "\n"
        else:
            reporter = make_reporter(output_format, sort_by_size=sort_by_size)
            content = reporter.render(unused_code)

        if output:
            Path(output).write_text(content, encoding="utf-8")
        elif content:
            self._log(content.rstrip("\n"), force=True)
        if unused_code:
            self.exit_code = ExitCode.DeadCode
        return self.exit_code


def main():
    try:
        config = make_config()
    except InputError as error:
        print(error, file=sys.stderr)
        sys.exit(ExitCode.InvalidCmdlineArguments)

    deadcodex = DeadCodex(
        verbose=config["verbose"],
        ignore_names=config["ignore_names"],
        ignore_decorators=config["ignore_decorators"],
    )
    deadcodex.scavenge(config["paths"], exclude=config["exclude"])
    entry_point_providers = [
        make_framework_adapter(name) for name in config["frameworks"]
    ]
    if config["entry_point_decorators"]:
        entry_point_providers.append(
            DecoratorEntryPointAdapter(tuple(config["entry_point_decorators"]))
        )
    try:
        exit_code = deadcodex.report(
            min_confidence=config["min_confidence"],
            sort_by_size=config["sort_by_size"],
            make_whitelist=config["make_whitelist"],
            entry_points=config["entry_points"],
            entry_point_providers=tuple(entry_point_providers),
            output_format=config["output_format"],
            output=config["output"],
            baseline=config["baseline"],
            update_baseline=config["update_baseline"],
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(ExitCode.InvalidCmdlineArguments)
    sys.exit(exit_code)
