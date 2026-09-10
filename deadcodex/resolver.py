import builtins
from collections import Counter, defaultdict

from deadcodex.model import (
    ImportKind,
    QualifiedName,
    ResolutionStatus,
    ScopeKind,
    UsageKind,
)


class ImportResolver:
    """Resolve import bindings against modules and symbols in a project."""

    def resolve(self, project, defined_items):
        self._project = project
        self.status_counts = Counter()

        self._symbol_origins = defaultdict(set)
        for item in defined_items:
            if item.qualified_name is not None:
                self._symbol_origins[str(item.qualified_name)].add(
                    item.filename.resolve()
                )

        self._project_roots = {
            module.qualified_name.parts[0] for module in project.modules
        }
        for module in project.modules:
            for binding in module.imports:
                binding.status, binding.target = self._resolve_binding(
                    module, binding
                )
                self.status_counts[binding.status] += 1
        return project

    def _resolve_binding(self, module, binding):
        if not binding.bound_name:
            return ResolutionStatus.UNRESOLVED, None
        if binding.kind is ImportKind.MODULE:
            target = QualifiedName.from_string(binding.module_name)
            return self._resolve_module(target, is_relative=False)

        base = self._resolve_base(module, binding)
        if base is None:
            return ResolutionStatus.UNRESOLVED, None

        base_modules = self._project.modules_named(base)
        if len(base_modules) > 1:
            return ResolutionStatus.AMBIGUOUS, None

        if binding.imported_name == "*":
            return self._resolve_module(base, is_relative=bool(binding.level))

        target = base.child(binding.imported_name)
        target_modules = self._project.modules_named(target)
        symbol_origins = self._symbol_origins[str(target)]
        candidate_count = len(target_modules) + len(symbol_origins)
        if candidate_count == 1:
            return ResolutionStatus.RESOLVED, target
        if candidate_count > 1:
            return ResolutionStatus.AMBIGUOUS, None

        if base_modules or not self._is_external(base, binding.level):
            return ResolutionStatus.UNRESOLVED, None
        return ResolutionStatus.EXTERNAL, None

    def _resolve_base(self, module, binding):
        if not binding.level:
            return QualifiedName.from_string(binding.module_name)

        package_parts = (
            module.qualified_name.parts
            if module.is_package
            else module.qualified_name.parts[:-1]
        )
        levels_up = binding.level - 1
        if not package_parts or levels_up >= len(package_parts):
            return None

        base_parts = package_parts[: len(package_parts) - levels_up]
        if binding.module_name:
            base_parts = (*base_parts, *binding.module_name.split("."))
        return QualifiedName(tuple(base_parts))

    def _resolve_module(self, target, is_relative):
        candidates = self._project.modules_named(target)
        if len(candidates) == 1:
            return ResolutionStatus.RESOLVED, target
        if len(candidates) > 1:
            return ResolutionStatus.AMBIGUOUS, None
        if is_relative or target.parts[0] in self._project_roots:
            return ResolutionStatus.UNRESOLVED, None
        return ResolutionStatus.EXTERNAL, None

    def _is_external(self, target, level):
        return not level and target.parts[0] not in self._project_roots


class ReferenceResolver:
    """Resolve recorded reads through lexical scopes and import bindings."""

    def resolve(self, project, defined_items):
        self._project = project
        self.status_counts = Counter()
        self._symbol_origins = defaultdict(set)
        for item in defined_items:
            if item.typ != "import" and item.qualified_name is not None:
                self._symbol_origins[str(item.qualified_name)].add(
                    item.filename.resolve()
                )

        self._builtin_names = set(dir(builtins))
        for module in project.modules:
            for reference in module.references:
                (
                    reference.status,
                    reference.target,
                    reference.binding_target,
                ) = self._resolve_reference(module, reference)
                self.status_counts[reference.status] += 1
        return project

    def _resolve_reference(self, module, reference):
        scope = module.scope_named(reference.scope_name) or module.scope
        if reference.kind is UsageKind.NAME:
            status, target, binding_target, _ = self._resolve_name(
                module, scope, reference.name
            )
            return status, target, binding_target

        if len(reference.parts) < 2:
            return ResolutionStatus.UNRESOLVED, None, None
        instance_target = self._instance_attribute_target(
            scope, reference.parts
        )
        if instance_target is not None:
            status = self._candidate_status(instance_target)
            return (
                status,
                (
                    instance_target
                    if status is ResolutionStatus.RESOLVED
                    else None
                ),
                None,
            )
        status, target, binding_target, binding = self._resolve_name(
            module, scope, reference.parts[0]
        )
        if status is not ResolutionStatus.RESOLVED:
            return status, None, binding_target

        candidate = self._attribute_target(reference.parts, target, binding)
        if candidate == target:
            return ResolutionStatus.RESOLVED, candidate, binding_target
        candidate_status = self._candidate_status(candidate)
        return (
            candidate_status,
            (
                candidate
                if candidate_status is ResolutionStatus.RESOLVED
                else None
            ),
            binding_target,
        )

    def _resolve_name(self, module, scope, name):
        starts_in_function = scope.kind is ScopeKind.FUNCTION
        current_scope = scope
        while current_scope is not None:
            skip_class_scope = (
                starts_in_function and current_scope.kind is ScopeKind.CLASS
            )
            if not skip_class_scope:
                candidate = current_scope.qualified_name.child(name)
                origins = self._symbol_origins[str(candidate)]
                if len(origins) == 1:
                    return ResolutionStatus.RESOLVED, candidate, None, None
                if len(origins) > 1:
                    return ResolutionStatus.AMBIGUOUS, None, None, None

            if current_scope.kind is ScopeKind.MODULE:
                bindings = [
                    binding
                    for binding in module.imports
                    if binding.bound_name == name
                ]
                if bindings:
                    return self._resolve_imported_name(module, name, bindings)
            current_scope = current_scope.parent

        if name in self._builtin_names:
            return ResolutionStatus.EXTERNAL, None, None, None
        return ResolutionStatus.UNRESOLVED, None, None, None

    @staticmethod
    def _resolve_imported_name(module, name, bindings):
        binding_target = module.qualified_name.child(name)
        outcomes = {(binding.status, binding.target) for binding in bindings}
        if len(outcomes) > 1:
            return (
                ResolutionStatus.AMBIGUOUS,
                None,
                binding_target,
                None,
            )

        binding = bindings[0]
        if binding.status is ResolutionStatus.RESOLVED:
            return binding.status, binding.target, binding_target, binding
        return binding.status, None, binding_target, binding

    def _candidate_status(self, candidate):
        module_count = len(self._project.modules_named(candidate))
        symbol_count = len(self._symbol_origins[str(candidate)])
        candidate_count = module_count + symbol_count
        if candidate_count == 1:
            return ResolutionStatus.RESOLVED
        if candidate_count > 1:
            return ResolutionStatus.AMBIGUOUS
        return ResolutionStatus.UNRESOLVED

    @staticmethod
    def _attribute_target(parts, target, binding):
        if (
            binding is not None
            and binding.kind is ImportKind.MODULE
            and binding.alias is None
        ):
            if tuple(parts[: len(target.parts)]) == target.parts:
                return QualifiedName(tuple(parts))
            if tuple(target.parts[: len(parts)]) == parts:
                return target
            return QualifiedName((target.parts[0], *parts[1:]))
        return QualifiedName((*target.parts, *parts[1:]))

    @staticmethod
    def _instance_attribute_target(scope, parts):
        if parts[0] not in {"self", "cls"}:
            return None
        current_scope = scope.parent
        while current_scope is not None:
            if current_scope.kind is ScopeKind.CLASS:
                return QualifiedName(
                    (*current_scope.qualified_name.parts, *parts[1:])
                )
            current_scope = current_scope.parent
        return None
