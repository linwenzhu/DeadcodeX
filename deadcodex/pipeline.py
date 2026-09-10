from typing import Protocol

from deadcodex.model import CallGraph


class Analyzer(Protocol):
    """Common interface for an analysis pass over a project model."""

    def analyze(self, project, defined_items):
        """Analyze collected project data and return pass-specific output."""


class ProjectAnalyzer:
    """Run project-wide resolution passes in dependency order."""

    def __init__(
        self, import_resolver, reference_resolver, call_graph_builder
    ):
        self.import_resolver = import_resolver
        self.reference_resolver = reference_resolver
        self.call_graph_builder = call_graph_builder

    def analyze(
        self, project, defined_items, imports_resolved=False
    ) -> CallGraph:
        if not imports_resolved:
            self.import_resolver.resolve(project, defined_items)
        self.reference_resolver.resolve(project, defined_items)
        return self.call_graph_builder.build(project, defined_items)
