from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from .signature import Signature
from .sorts import CoproductSort, ProductSort, SortKind, SortRef
from .spec import Spec
from .terms import (
    Biconditional,
    Conjunction,
    Definedness,
    Disjunction,
    Equation,
    ExistentialQuant,
    FieldAccess,
    FnApp,
    Formula,
    Implication,
    Literal,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    check: str
    severity: Severity
    axiom: str | None
    message: str
    path: str | None


@dataclass(frozen=True)
class CheckResult:
    spec_name: str
    diagnostics: tuple[Diagnostic, ...]

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == Severity.ERROR)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == Severity.WARNING)

    @property
    def is_well_formed(self) -> bool:
        return len(self.errors) == 0


@dataclass
class CheckContext:
    sig: Signature
    axiom_label: str | None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    _var_env: list[dict[str, SortRef]] = field(default_factory=list)
    _axiom_vars: dict[str, SortRef] = field(default_factory=dict)

    def error(self, check: str, message: str, path: str | None = None) -> None:
        self.diagnostics.append(
            Diagnostic(check, Severity.ERROR, self.axiom_label, message, path)
        )

    def warning(self, check: str, message: str, path: str | None = None) -> None:
        self.diagnostics.append(
            Diagnostic(check, Severity.WARNING, self.axiom_label, message, path)
        )

    def push_scope(self) -> None:
        self._var_env.append({})

    def bind_vars(self, variables: tuple[Var, ...]) -> None:
        for v in variables:
            self._var_env[-1][v.name] = v.sort

    def pop_scope(self) -> None:
        self._var_env.pop()

    def get_var_sort(self, name: str) -> SortRef | None:
        for i in range(len(self._var_env) - 1, -1, -1):
            if name in self._var_env[i]:
                return self._var_env[i][name]
        return None

    def begin_axiom(self, label: str) -> None:
        self.axiom_label = label
        self._axiom_vars = {}
        self._var_env = []

    def observe_var(self, name: str, sort: SortRef, path: str) -> None:
        if name in self._axiom_vars:
            if self._axiom_vars[name] != sort:
                self.error(
                    "var_sort_consistent",
                    f"Variable '{name}' appears with sort '{self._axiom_vars[name]}' and '{sort}'",
                    path,
                )
        else:
            self._axiom_vars[name] = sort


def check_term(term: Term, ctx: CheckContext, path: str) -> SortRef | None:
    if not isinstance(term, (Var, FnApp, FieldAccess, Literal)):
        ctx.error(  # type: ignore[unreachable]
            "formula_term_separation", f"Expected Term, got {type(term).__name__}", path
        )
        return None

    if isinstance(term, Var):
        sort = ctx.get_var_sort(term.name)
        if sort is None:
            ctx.error(
                "var_bound",
                f"Variable '{term.name}' is not bound by any quantifier",
                path,
            )
            return None
        ctx.observe_var(term.name, term.sort, path)
        return term.sort
    elif isinstance(term, FnApp):
        fn = ctx.sig.get_fn(term.fn_name)
        if fn is None:
            ctx.error("fn_declared", f"Function '{term.fn_name}' is not declared", path)
            return None
        if len(term.args) != len(fn.params):
            ctx.error(
                "fn_arity",
                f"Function '{term.fn_name}' expects {len(fn.params)} arguments, got {len(term.args)}",
                path,
            )
        else:
            for i, (arg, param) in enumerate(zip(term.args, fn.params, strict=False)):
                arg_sort = check_term(arg, ctx, f"{path}.args[{i}]")
                if arg_sort is not None and arg_sort != param.sort:
                    ctx.error(
                        "fn_arg_sorts",
                        f"Argument {i} to '{term.fn_name}' expected sort '{param.sort}', got '{arg_sort}'",
                        f"{path}.args[{i}]",
                    )
        return fn.result
    elif isinstance(term, FieldAccess):
        term_sort = check_term(term.term, ctx, f"{path}.term")
        if term_sort is None:
            return None
        sort_decl = ctx.sig.get_sort(term_sort)
        if sort_decl is None or sort_decl.kind != SortKind.PRODUCT:
            ctx.error(
                "field_access_valid",
                f"Term has sort '{term_sort}' which is not a ProductSort",
                path,
            )
            return None
        assert isinstance(sort_decl, ProductSort)
        field_sort = sort_decl.field_sort(term.field_name)
        if field_sort is None:
            ctx.error(
                "field_access_valid",
                f"Field '{term.field_name}' not found on ProductSort '{term_sort}'",
                path,
            )
            return None
        return field_sort
    elif isinstance(term, Literal):
        sort_decl = ctx.sig.get_sort(term.sort)
        if sort_decl is None:
            ctx.error(
                "sort_resolved", f"Sort '{term.sort}' in literal is not declared", path
            )
            return None
        return term.sort
    return None  # type: ignore[unreachable]


def check_formula(formula: Formula, ctx: CheckContext, path: str) -> None:
    if not isinstance(
        formula,
        (
            Equation,
            PredApp,
            Negation,
            Conjunction,
            Disjunction,
            Implication,
            Biconditional,
            UniversalQuant,
            ExistentialQuant,
            Definedness,
        ),
    ):
        ctx.error(  # type: ignore[unreachable]
            "formula_term_separation",
            f"Expected Formula, got {type(formula).__name__}",
            path,
        )
        return

    if isinstance(formula, Equation):
        lhs_sort = check_term(formula.lhs, ctx, f"{path}.lhs")
        rhs_sort = check_term(formula.rhs, ctx, f"{path}.rhs")
        if lhs_sort is not None and rhs_sort is not None and lhs_sort != rhs_sort:
            ctx.error(
                "equation_sort_match",
                f"LHS sort '{lhs_sort}' does not match RHS sort '{rhs_sort}'",
                path,
            )
    elif isinstance(formula, PredApp):
        pred = ctx.sig.get_pred(formula.pred_name)
        if pred is None:
            ctx.error(
                "pred_declared",
                f"Predicate '{formula.pred_name}' is not declared",
                path,
            )
        elif len(formula.args) != len(pred.params):
            ctx.error(
                "pred_arity",
                f"Predicate '{formula.pred_name}' expects {len(pred.params)} arguments, got {len(formula.args)}",
                path,
            )
        else:
            for i, (arg, param) in enumerate(
                zip(formula.args, pred.params, strict=False)
            ):
                arg_sort = check_term(arg, ctx, f"{path}.args[{i}]")
                if arg_sort is not None and arg_sort != param.sort:
                    ctx.error(
                        "pred_arg_sorts",
                        f"Argument {i} to predicate '{formula.pred_name}' expected '{param.sort}', got '{arg_sort}'",
                        f"{path}.args[{i}]",
                    )
    elif isinstance(formula, Negation):
        check_formula(formula.formula, ctx, f"{path}.formula")
    elif isinstance(formula, (Conjunction, Disjunction)):
        subformulas = (
            formula.conjuncts if isinstance(formula, Conjunction) else formula.disjuncts
        )
        attr = "conjuncts" if isinstance(formula, Conjunction) else "disjuncts"
        for i, f in enumerate(subformulas):
            check_formula(f, ctx, f"{path}.{attr}[{i}]")
    elif isinstance(formula, (Implication, Biconditional)):
        check_formula(
            formula.lhs if isinstance(formula, Biconditional) else formula.antecedent,
            ctx,
            f"{path}.lhs"
            if isinstance(formula, Biconditional)
            else f"{path}.antecedent",
        )
        check_formula(
            formula.rhs if isinstance(formula, Biconditional) else formula.consequent,
            ctx,
            f"{path}.rhs"
            if isinstance(formula, Biconditional)
            else f"{path}.consequent",
        )
    elif isinstance(formula, (UniversalQuant, ExistentialQuant)):
        for i, v in enumerate(formula.variables):
            ctx.observe_var(v.name, v.sort, f"{path}.variables[{i}]")
        ctx.push_scope()
        ctx.bind_vars(formula.variables)
        check_formula(formula.body, ctx, f"{path}.body")
        ctx.pop_scope()
    elif isinstance(formula, Definedness):
        check_term(formula.term, ctx, f"{path}.term")


def check_layer_1(spec: Spec, ctx: CheckContext) -> None:
    # sort_name_consistency
    ctx.axiom_label = None
    for name, sort_decl in spec.signature.sorts.items():
        if sort_decl.name != name:
            ctx.error(
                "sort_name_consistency",
                f"Sort key '{name}' does not match sort.name '{sort_decl.name}'",
            )

    # sort_resolved
    for fn in spec.signature.functions.values():
        if fn.result not in spec.signature.sorts:
            ctx.error(
                "sort_resolved",
                f"Result sort '{fn.result}' in function '{fn.name}' not in signature",
            )
        for p in fn.params:
            if p.sort not in spec.signature.sorts:
                ctx.error(
                    "sort_resolved",
                    f"Parameter sort '{p.sort}' in function '{fn.name}' not in signature",
                )

    for pred in spec.signature.predicates.values():
        for p in pred.params:
            if p.sort not in spec.signature.sorts:
                ctx.error(
                    "sort_resolved",
                    f"Parameter sort '{p.sort}' in predicate '{pred.name}' not in signature",
                )

    # product_sort_fields_resolved & coproduct_sort_alts_resolved
    for _name, sort_decl in spec.signature.sorts.items():
        if isinstance(sort_decl, ProductSort):
            for f in sort_decl.fields:
                if f.sort not in spec.signature.sorts:
                    ctx.error(
                        "product_sort_fields_resolved",
                        f"Field '{f.name}' sort '{f.sort}' not in signature",
                    )
        elif isinstance(sort_decl, CoproductSort):
            for a in sort_decl.alts:
                if a.sort not in spec.signature.sorts:
                    ctx.error(
                        "coproduct_sort_alts_resolved",
                        f"Alt '{a.tag}' sort '{a.sort}' not in signature",
                    )

    # no_name_collisions
    name_lists = [
        spec.signature.sorts.keys(),
        spec.signature.functions.keys(),
        spec.signature.predicates.keys(),
    ]
    items: list[str] = []
    for d in name_lists:
        items.extend(list(d))
    counts = Counter(items)
    for name, c in counts.items():
        if c > 1:
            ctx.error("no_name_collisions", f"Name '{name}' has a collision")


def check_spec(spec: Spec) -> CheckResult:
    ctx = CheckContext(sig=spec.signature, axiom_label=None)

    check_layer_1(spec, ctx)

    # Structural: duplicate_axiom_labels
    labels: list[str] = []
    for ax in spec.axioms:
        if ax.label in labels:
            ctx.error("duplicate_axiom_labels", f"Duplicate axiom label '{ax.label}'")
        labels.append(ax.label)

    # Layer 2 & 3: Type checking & Var scoping (per axiom)
    for ax in spec.axioms:
        ctx.begin_axiom(ax.label)
        check_formula(ax.formula, ctx, "formula")

    def sort_key(d: Diagnostic) -> tuple[int, str, str]:
        severity_order = 0 if d.severity == Severity.ERROR else 1
        return (severity_order, d.check, d.axiom or "")

    sorted_diagnostics = tuple(sorted(ctx.diagnostics, key=sort_key))
    return CheckResult(spec.name, sorted_diagnostics)
