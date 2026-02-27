from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .signature import Signature, Totality
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
    _var_used: list[set[str]] = field(default_factory=list)
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
        self._var_used.append(set())

    def bind_vars(self, variables: tuple[Var, ...]) -> None:
        for v in variables:
            self._var_env[-1][v.name] = v.sort

    def pop_scope(self) -> tuple[dict[str, SortRef], set[str]]:
        env = self._var_env.pop()
        used = self._var_used.pop()
        return env, used

    def get_var_sort(self, name: str) -> SortRef | None:
        for i in range(len(self._var_env) - 1, -1, -1):
            if name in self._var_env[i]:
                self._var_used[i].add(name)
                return self._var_env[i][name]
        return None

    def begin_axiom(self, label: str) -> None:
        self.axiom_label = label
        self._axiom_vars = {}
        self._var_env = []
        self._var_used = []

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
            # Check arguments
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
        env, used = ctx.pop_scope()
        for v in formula.variables:
            if v.name not in used:
                ctx.warning(
                    "var_used",
                    f"Variable '{v.name}' bound by quantifier is unused",
                    f"{path}.variables",
                )
    elif isinstance(formula, Definedness):
        check_term(formula.term, ctx, f"{path}.term")


def is_tautology(f: Formula) -> bool:
    if isinstance(f, Equation) and f.lhs == f.rhs:
        return True
    if isinstance(f, Biconditional) and f.lhs == f.rhs:
        return True
    if isinstance(f, UniversalQuant):
        return is_tautology(f.body)
    return False


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
    names = [
        spec.signature.sorts.keys(),
        spec.signature.functions.keys(),
        spec.signature.predicates.keys(),
    ]
    items = []
    for d in names:
        items.extend(list(d))
    from collections import Counter

    counts = Counter(items)
    for name, c in counts.items():
        if c > 1:
            ctx.error("no_name_collisions", f"Name '{name}' has a collision")


def get_used_sorts(spec: Spec) -> set[SortRef]:
    used = set()
    for fn in spec.signature.functions.values():
        used.add(fn.result)

    def visit(f: Formula) -> None:
        if isinstance(f, (UniversalQuant, ExistentialQuant)):
            for v in f.variables:
                used.add(v.sort)
            visit(f.body)
        elif isinstance(f, Negation):
            visit(f.formula)
        elif isinstance(f, (Conjunction, Disjunction)):
            subs = f.conjuncts if isinstance(f, Conjunction) else f.disjuncts
            for s in subs:
                visit(s)
        elif isinstance(f, (Implication, Biconditional)):
            visit(f.lhs if isinstance(f, Biconditional) else f.antecedent)
            visit(f.rhs if isinstance(f, Biconditional) else f.consequent)

    for ax in spec.axioms:
        visit(ax.formula)
    return used


def check_layer_1_warnings(spec: Spec, ctx: CheckContext) -> None:
    # no_empty_sorts
    used_sorts = get_used_sorts(spec)
    for sort_name in spec.signature.sorts:
        if sort_name not in used_sorts:
            ctx.warning(
                "no_empty_sorts",
                f"Sort '{sort_name}' has no function returning it and no variable quantified over it",
            )


def check_spec(spec: Spec) -> CheckResult:
    ctx = CheckContext(sig=spec.signature, axiom_label=None)

    check_layer_1(spec, ctx)
    check_layer_1_warnings(spec, ctx)

    # Layer 5: duplicate_axiom_labels
    labels = []
    for ax in spec.axioms:
        if ax.label in labels:
            ctx.error("duplicate_axiom_labels", f"Duplicate axiom label '{ax.label}'")
        labels.append(ax.label)

    for ax in spec.axioms:
        ctx.begin_axiom(ax.label)

        # Layer 5: trivial_axiom
        if is_tautology(ax.formula):
            ctx.warning("trivial_axiom", "Axiom is a trivial tautology", "formula")

        # Layer 5: axiom_quantified
        has_vars = check_has_vars(ax.formula)
        if has_vars and not isinstance(ax.formula, UniversalQuant):
            ctx.warning(
                "axiom_quantified",
                "Axiom has free variables but is not wrapped in a universal quantifier",
                "formula",
            )

        # Layer 2 & 3: Type checking & Var scoping
        check_formula(ax.formula, ctx, "formula")

    # Layer 4: Obligations
    check_obligations(spec, ctx)

    # Sort diagnostics by severity, check, axiom_label
    def sort_key(d: Diagnostic) -> tuple[int, str, str]:
        severity_order = 0 if d.severity == Severity.ERROR else 1
        return (severity_order, d.check, d.axiom or "")

    sorted_diagnostics = tuple(sorted(ctx.diagnostics, key=sort_key))
    return CheckResult(spec.name, sorted_diagnostics)


def check_has_vars(f: Formula) -> bool:
    def visit_term(t: Term) -> bool:
        if isinstance(t, Var):
            return True
        if isinstance(t, FnApp):
            return any(visit_term(a) for a in t.args)
        if isinstance(t, FieldAccess):
            return visit_term(t.term)
        return False

    def visit(f: Formula) -> bool:
        if isinstance(f, Equation):
            return visit_term(f.lhs) or visit_term(f.rhs)
        if isinstance(f, PredApp):
            return any(visit_term(a) for a in f.args)
        if isinstance(f, Definedness):
            return visit_term(f.term)
        if isinstance(f, Negation):
            return visit(f.formula)
        if isinstance(f, (Conjunction, Disjunction)):
            subs = f.conjuncts if isinstance(f, Conjunction) else f.disjuncts
            return any(visit(s) for s in subs)
        if isinstance(f, (Implication, Biconditional)):
            return visit(
                f.lhs if isinstance(f, Biconditional) else f.antecedent
            ) or visit(f.rhs if isinstance(f, Biconditional) else f.consequent)
        if isinstance(f, (UniversalQuant, ExistentialQuant)):
            # If bound here, we still consider the formula as having variables inside it from a free perspective if they were free?
            # Wait, the rule says "unless the axiom has no free variables" - wait, let me re-read:
            # "Every axiom's outermost formula is a UniversalQuant, unless the axiom has no free variables (e.g., ground equation). Violation: Axiom... where x and y are vars but the formula is not wrapped in forall."
            # So if it DOES have vars, it must be wrapped in ∀.
            return True
        return False  # type: ignore[unreachable]

    return visit(f)


def get_subterm_fns(t: Term) -> list[str]:
    if isinstance(t, FnApp):
        res = [t.fn_name]
        for a in t.args:
            res.extend(get_subterm_fns(a))
        return res
    elif isinstance(t, FieldAccess):
        return get_subterm_fns(t.term)
    return []


def extract_patterns(f: Formula) -> set[tuple[str, str]]:
    patterns = set()

    def visit_term_patterns(t: Term) -> None:
        if isinstance(t, FnApp):
            for a in t.args:
                if isinstance(a, FnApp):
                    patterns.add((t.fn_name, a.fn_name))
                visit_term_patterns(a)
        elif isinstance(t, FieldAccess):
            visit_term_patterns(t.term)

    def visit(f_n: Formula) -> None:
        if isinstance(f_n, Equation):
            visit_term_patterns(f_n.lhs)
            visit_term_patterns(f_n.rhs)
        elif isinstance(f_n, PredApp):
            for a in f_n.args:
                if isinstance(a, FnApp):
                    patterns.add((f_n.pred_name, a.fn_name))
                visit_term_patterns(a)
        elif isinstance(f_n, Definedness):
            visit_term_patterns(f_n.term)
        elif isinstance(f_n, Negation):
            visit(f_n.formula)
        elif isinstance(f_n, (Conjunction, Disjunction)):
            subs = f_n.conjuncts if isinstance(f_n, Conjunction) else f_n.disjuncts
            for s in subs:
                visit(s)
        elif isinstance(f_n, (Implication, Biconditional)):
            visit(f_n.lhs if isinstance(f_n, Biconditional) else f_n.antecedent)
            visit(f_n.rhs if isinstance(f_n, Biconditional) else f_n.consequent)
        elif isinstance(f_n, (UniversalQuant, ExistentialQuant)):
            visit(f_n.body)

    visit(f)
    return patterns


def compute_obligations(spec: Spec) -> list[tuple[str, str, bool, Totality]]:
    # 1. Classify constructors vs observers
    constructors_by_sort: dict[str, list[tuple[str, Totality]]] = {}
    observers_by_sort: dict[str, list[tuple[str, Totality]]] = {}

    for sort_name in spec.signature.sorts:
        constructors_by_sort[sort_name] = []
        observers_by_sort[sort_name] = []

    for name, fn in spec.signature.functions.items():
        if fn.result in spec.signature.sorts:
            constructors_by_sort[fn.result].append((name, fn.totality))
        if len(fn.params) > 0:
            first_sort = fn.params[0].sort
            if first_sort in spec.signature.sorts and fn.result != first_sort:
                observers_by_sort[first_sort].append((name, fn.totality))

    for name, pred in spec.signature.predicates.items():
        if len(pred.params) > 0:
            first_sort = pred.params[0].sort
            if first_sort in spec.signature.sorts:
                # predicates are inherently total unless we model undefinedness, which we don't for preds
                observers_by_sort[first_sort].append((name, Totality.TOTAL))

    patterns = set()
    for ax in spec.axioms:
        patterns.update(extract_patterns(ax.formula))

    result = []
    for sort_name in spec.signature.sorts:
        for obs, obs_tot in observers_by_sort[sort_name]:
            for con, _con_tot in constructors_by_sort[sort_name]:
                has_ax = (obs, con) in patterns
                result.append((obs, con, has_ax, obs_tot))

    return result


def check_obligations(spec: Spec, ctx: CheckContext) -> None:
    ctx.axiom_label = None
    obligations = compute_obligations(spec)
    for obs, con, has_ax, obs_tot in obligations:
        if not has_ax:
            if obs_tot == Totality.TOTAL:
                ctx.warning(
                    "obligation_coverage",
                    f"Total observer '{obs}' missing axiom for constructor '{con}'",
                )
            else:
                # partial observer missing case -> no generic warning per `obligation_partial_skip`
                pass
