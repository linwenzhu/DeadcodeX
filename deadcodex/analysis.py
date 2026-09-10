from deadcodex import utils
from deadcodex.model import Item, ResolutionStatus


def _get_unused_items(defined_items, used_names):
    unused_items = [
        item for item in set(defined_items) if item.name not in used_names
    ]
    unused_items.sort(key=lambda item: item.name.lower())
    return unused_items


class AnalysisResult:
    """Store definitions and usages collected across analyzed modules."""

    def __init__(self, verbose=False):
        def get_list(typ):
            return utils.LoggingList(typ, verbose)

        self.defined_attrs = get_list("attribute")
        self.defined_classes = get_list("class")
        self.defined_funcs = get_list("function")
        self.defined_imports = get_list("import")
        self.defined_methods = get_list("method")
        self.defined_props = get_list("property")
        self.defined_vars = get_list("variable")
        self.unreachable_code = get_list("unreachable_code")
        self.used_names = utils.LoggingSet("name", verbose)

    @property
    def defined_items(self):
        return (
            self.defined_attrs
            + self.defined_classes
            + self.defined_funcs
            + self.defined_imports
            + self.defined_methods
            + self.defined_props
            + self.defined_vars
        )

    def get_unused_code(
        self, min_confidence=0, sort_by_size=False
    ) -> list[Item]:
        """Return an ordered list of unused items."""
        if not 0 <= min_confidence <= 100:
            raise ValueError("min_confidence must be between 0 and 100.")

        def by_name(item):
            return str(item.filename).lower(), item.first_lineno

        def by_size(item):
            return item.size, *by_name(item)

        unused_code = (
            self.unused_attrs
            + self.unused_classes
            + self.unused_funcs
            + self.unused_imports
            + self.unused_methods
            + self.unused_props
            + self.unused_vars
            + self.unreachable_code
        )
        confidently_unused = [
            item for item in unused_code if item.confidence >= min_confidence
        ]
        return sorted(
            confidently_unused, key=by_size if sort_by_size else by_name
        )

    def get_unused_code_qualified(
        self, references, min_confidence=0, sort_by_size=False
    ) -> list[Item]:
        """Return experimental scope-aware unused items.

        Legacy name matching remains as a fallback whenever any reference with
        a given short name could not be resolved safely.
        """
        if not 0 <= min_confidence <= 100:
            raise ValueError("min_confidence must be between 0 and 100.")

        references_by_name = {}
        used_qualified_names = set()
        for reference in references:
            references_by_name.setdefault(reference.name, []).append(reference)
            if (
                reference.status is ResolutionStatus.RESOLVED
                and reference.target is not None
            ):
                used_qualified_names.add(reference.target)
            if reference.binding_target is not None:
                used_qualified_names.add(reference.binding_target)

        safely_resolved_names = {
            name
            for name, named_references in references_by_name.items()
            if all(
                reference.status is ResolutionStatus.RESOLVED
                for reference in named_references
            )
        }
        legacy_fallback_names = self.used_names - safely_resolved_names

        unused_items = [
            item
            for item in set(self.defined_items)
            if (
                item.qualified_name not in used_qualified_names
                and item.name not in legacy_fallback_names
            )
        ]
        unused_items.extend(self.unreachable_code)
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

    @property
    def unused_classes(self):
        return _get_unused_items(self.defined_classes, self.used_names)

    @property
    def unused_funcs(self):
        return _get_unused_items(self.defined_funcs, self.used_names)

    @property
    def unused_imports(self):
        return _get_unused_items(self.defined_imports, self.used_names)

    @property
    def unused_methods(self):
        return _get_unused_items(self.defined_methods, self.used_names)

    @property
    def unused_props(self):
        return _get_unused_items(self.defined_props, self.used_names)

    @property
    def unused_vars(self):
        return _get_unused_items(self.defined_vars, self.used_names)

    @property
    def unused_attrs(self):
        return _get_unused_items(self.defined_attrs, self.used_names)
