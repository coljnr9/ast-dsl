"""Auto-generate an LLM-consumable language reference for the alspec DSL.

Documents the PUBLIC API: the helper functions an LLM uses to construct specs.
Run: python -m alspec.gen_reference > LANGUAGE_REFERENCE.md
"""

from __future__ import annotations

import json
import inspect
import textwrap

from alspec.serialization import spec_to_json
from alspec.examples import (
    nat_spec,
    stack_spec,
    partial_order_spec,
    bug_tracker_spec,
)
from alspec.basis import ALL_BASIS_SPECS


def generate_reference() -> str:
    parts: list[str] = []

    # ── Header ─────────────────────────────────────────────────
    parts.append(
        textwrap.dedent(
            """\
    # Many-Sorted Algebraic Specification DSL — Language Reference

    This document is the complete reference for writing algebraic specifications
    using the `alspec` Python DSL. A specification consists of:

    - **Sorts** — the types (carrier sets)
    - **Function symbols** — typed operations over sorts
    - **Predicate symbols** — typed boolean relations over sorts
    - **Axioms** — universally quantified equations and logical formulas

    To write a specification, you write a Python function that uses the helper
    functions below and returns a `Spec` object.

    ---

    ## Imports

    Everything you need comes from two places:

    ```python
    from alspec import (
        # Core types (only needed occasionally)
        Axiom, Signature, Spec, SortRef,
        # Product/Coproduct sorts (when needed)
        ProductSort, ProductField, CoproductSort, CoproductAlt,
        # Formula types for complex axioms
        Conjunction, Disjunction, Implication, Biconditional, Negation,
        PredApp, Definedness,
        # Field access for product sorts
        FieldAccess,
        # Serialization
        dumps, loads,
    )
    ```

    Most of the time you'll use the helper functions described below rather than
    constructing types directly.

    ---

    ## Helper Functions (Public API)

    These are the primary building blocks. An LLM writing a spec should use
    these almost exclusively.

    ### Sorts

    ```python
    S(name: str) -> SortRef
    ```
    Reference a sort by name. Use everywhere a sort is needed.

    ```python
    atomic(name: str) -> AtomicSort
    ```
    Declare an opaque sort with no internal structure.
    Examples: `atomic("Nat")`, `atomic("Elem")`, `atomic("TicketId")`

    For **product sorts** (structs with fields), construct directly:
    ```python
    ProductSort(
        name=S("Ticket"),
        fields=(
            ProductField("id", S("TicketId")),
            ProductField("title", S("Title")),
            ProductField("severity", S("SeverityLevel")),
        ),
    )
    ```

    For **coproduct sorts** (tagged unions), construct directly:
    ```python
    CoproductSort(
        name=S("Result"),
        alts=(
            CoproductAlt("ok", S("Value")),
            CoproductAlt("err", S("Error")),
        ),
    )
    ```

    ### Function Symbols

    ```python
    fn(name: str, params: list[tuple[str, str]], result: str, total: bool = True) -> FnSymbol
    ```
    Declare a function symbol with a typed profile.

    - `params`: list of `(param_name, sort_name)` tuples. Empty list `[]` for constants.
    - `result`: the return sort name.
    - `total`: `True` (default) for total functions, `False` for partial.

    Examples:
    ```python
    fn("zero", [], "Nat")                                    # constant
    fn("suc", [("n", "Nat")], "Nat")                         # unary total
    fn("add", [("x", "Nat"), ("y", "Nat")], "Nat")           # binary total
    fn("top", [("S", "Stack")], "Elem", total=False)          # partial
    fn("classify", [("t", "Title"), ("b", "Body")], "Severity")  # domain function
    ```

    ### Predicate Symbols

    ```python
    pred(name: str, params: list[tuple[str, str]]) -> PredSymbol
    ```
    Declare a predicate (boolean relation). No return sort — predicates hold or don't.

    Examples:
    ```python
    pred("empty", [("S", "Stack")])                    # unary
    pred("leq", [("x", "Elem"), ("y", "Elem")])        # binary
    ```

    ### Variables

    ```python
    var(name: str, sort: str) -> Var
    ```
    Declare a typed variable for use in axioms.

    ```python
    x = var("x", "Nat")
    s = var("S", "Stack")
    e = var("e", "Elem")
    ```

    ### Term Constructors

    ```python
    app(fn_name: str, *args) -> FnApp
    ```
    Apply a function symbol to arguments. Arguments can be `Var` or other `FnApp`.

    ```python
    const(name: str) -> FnApp
    ```
    Nullary function application (a constant). Equivalent to `app(name)`.

    ```python
    FieldAccess(term, field_name: str)
    ```
    Access a named field on a product-sorted term.

    Examples:
    ```python
    const("zero")                          # the constant zero
    app("suc", x)                          # suc(x)
    app("add", x, app("suc", y))           # add(x, suc(y))
    app("push", s, e)                      # push(S, e)
    FieldAccess(app("create", id, t, b), "severity")  # create(id, t, b).severity
    ```

    ### Formula Constructors

    ```python
    eq(lhs, rhs) -> Equation
    ```
    Equation between two terms: `lhs = rhs`.

    ```python
    forall(variables: list[Var], body) -> UniversalQuant
    ```
    Universal quantification: `∀ vars • body`.

    ```python
    PredApp(pred_name: str, args: tuple[Term, ...])
    ```
    Apply a predicate to arguments.

    ```python
    Negation(formula)                       # ¬ formula
    Conjunction((f1, f2, ...))              # f1 ∧ f2 ∧ ...
    Disjunction((f1, f2, ...))              # f1 ∨ f2 ∨ ...
    Implication(antecedent, consequent)     # antecedent ⇒ consequent
    Biconditional(lhs, rhs)                 # lhs ⇔ rhs
    Definedness(term)                       # def(term) — for partial functions
    ```

    ### Type Grammar (Composition Rules)

    **This is critical.** `Term` and `Formula` are DIFFERENT types and cannot
    be mixed. Use this grammar to check every expression you write:

    ```
    Term     = Var(name, sort)
             | FnApp(fn_name, tuple[Term, ...])    ← args are Terms
             | FieldAccess(Term, field_name)        ← inner is a Term
             | Literal(value, sort)

    Formula  = Equation(Term, Term)                 ← both sides are Terms
             | PredApp(pred_name, tuple[Term, ...]) ← args are Terms
             | Negation(Formula)                    ← inner is a Formula, NEVER a Term
             | Conjunction(tuple[Formula, ...])     ← all elements are Formulas
             | Disjunction(tuple[Formula, ...])     ← all elements are Formulas
             | Implication(Formula, Formula)        ← both are Formulas
             | Biconditional(Formula, Formula)      ← both are Formulas
             | UniversalQuant(tuple[Var, ...], Formula)
             | ExistentialQuant(tuple[Var, ...], Formula)
             | Definedness(Term)                    ← inner is a Term
    ```

    **Helper return types:**
    ```
    var(...)    → Var       (a Term)
    app(...)    → FnApp     (a Term)
    const(...)  → FnApp     (a Term)
    eq(...)     → Equation  (a Formula)  ← takes two Terms, returns a Formula
    forall(...) → UniversalQuant (a Formula) ← takes Vars + a Formula
    iff(...)    → Biconditional (a Formula)  ← takes two Formulas
    ```

    **Common illegal compositions:**
    ```
    Negation(app(...))          ← WRONG: app returns Term, Negation needs Formula
    Negation(eq(...))           ← RIGHT: eq returns Formula
    Negation(PredApp(...))      ← RIGHT: PredApp is a Formula
    eq(Definedness(...), ...)   ← WRONG: Definedness is a Formula, eq needs Terms
    eq(PredApp(...), ...)       ← WRONG: PredApp is a Formula, eq needs Terms
    eq(app(...), app(...))      ← RIGHT: both are Terms
    eq(app(...), var(...))      ← RIGHT: both are Terms
    Implication(app(...), ...)  ← WRONG: app returns Term, Implication needs Formula
    Implication(PredApp(...), eq(...))  ← RIGHT: both are Formulas
    ```

    ### Putting It Together

    ```python
    Signature(
        sorts={"Name": sort_decl, ...},
        functions={"name": fn_symbol, ...},
        predicates={"name": pred_symbol, ...},
    )

    Axiom(label="name", formula=...)

    Spec(name="Name", signature=sig, axioms=(axiom1, axiom2, ...))
    ```

    ---

    ## Serialization

    Every `Spec` transparently round-trips to/from JSON:

    ```python
    from alspec import dumps, loads

    json_str = dumps(spec)     # Spec → JSON string
    spec = loads(json_str)     # JSON string → Spec
    ```

    ---
    """
        )
    )

    # ── Complete Examples ──────────────────────────────────────
    parts.append("## Complete Examples\n")

    examples = [
        ("Natural Numbers (Peano)", nat_spec),
        ("Stack (with partial functions and predicates)", stack_spec),
        ("Partial Order (pure predicate spec)", partial_order_spec),
        (
            "Bug Tracker (product sorts, field access, domain functions)",
            bug_tracker_spec,
        ),
    ]

    for title, spec_fn in examples:
        parts.append(f"### {title}\n")

        # Get the source code of the spec function
        source = inspect.getsource(spec_fn)
        parts.append(f"```python\n{source}```\n")

        # Show the resulting JSON (collapsed summary)
        sp = spec_fn()
        sig = sp.signature

        # Compact signature summary
        sort_names = ", ".join(sig.sorts.keys())
        parts.append(f"**Sorts:** {sort_names}\n")

        if sig.functions:
            fn_lines = []
            for f in sig.functions.values():
                params = " × ".join(f"{p.sort}" for p in f.params)
                arrow = "→" if f.totality.value == "total" else "→?"
                profile = (
                    f"{params} {arrow} {f.result}" if params else f"{arrow} {f.result}"
                )
                fn_lines.append(f"`{f.name} : {profile}`")
            parts.append(f"**Functions:** {', '.join(fn_lines)}\n")

        if sig.predicates:
            pred_lines = []
            for p in sig.predicates.values():
                params = " × ".join(str(pp.sort) for pp in p.params)
                pred_lines.append(f"`{p.name} : {params}`")
            parts.append(f"**Predicates:** {', '.join(pred_lines)}\n")

        ax_names = ", ".join(a.label for a in sp.axioms)
        parts.append(f"**Axioms:** {ax_names}\n")

        parts.append("---\n")

    # ── Standard Library (Basis) ───────────────────────────────
    parts.append(
        textwrap.dedent(
            """\
    ## Standard Library (Basis)

    The following specifications are pre-built and verified. They cover the
    fundamental algebraic patterns that real specifications compose from.
    Import them from `alspec.basis` rather than redefining from scratch.

    Sources: CASL Basic Libraries (CoFI, tool-checked by Hets),
    Sannella & Tarlecki "Foundations of Algebraic Specification" (2012).
    """
        )
    )

    for spec_fn in ALL_BASIS_SPECS:
        sp = spec_fn()
        sig = sp.signature

        parts.append(f"### {sp.name}\n")

        # Docstring (first paragraph only)
        if spec_fn.__doc__:
            doc = textwrap.dedent(spec_fn.__doc__).strip()
            parts.append(f"{doc}\n")

        # Compact signature summary
        sort_names = ", ".join(sig.sorts.keys())
        parts.append(f"**Sorts:** {sort_names}\n")

        if sig.functions:
            fn_lines = []
            for f in sig.functions.values():
                params = " × ".join(f"{p.sort}" for p in f.params)
                arrow = "→" if f.totality.value == "total" else "→?"
                profile = (
                    f"{params} {arrow} {f.result}" if params else f"{arrow} {f.result}"
                )
                fn_lines.append(f"`{f.name} : {profile}`")
            parts.append(f"**Functions:** {', '.join(fn_lines)}\n")

        if sig.predicates:
            pred_lines = []
            for p in sig.predicates.values():
                params = " × ".join(str(pp.sort) for pp in p.params)
                pred_lines.append(f"`{p.name} : {params}`")
            parts.append(f"**Predicates:** {', '.join(pred_lines)}\n")

        ax_names = ", ".join(a.label for a in sp.axioms)
        parts.append(f"**Axioms ({len(sp.axioms)}):** {ax_names}\n")

        parts.append("---\n")

    # ── Rules for Well-Formed Specs ────────────────────────────
    parts.append(
        textwrap.dedent(
            """\
    ## Rules for Well-Formed Specifications

    When writing a specification, ensure:

    1. **Every sort referenced must be declared.** If a function returns `"Severity"`,
       there must be a sort named `"Severity"` in the signature.

    2. **Every function/predicate used in a term must be declared in the signature.**
       `app("classify", t, b)` requires `"classify"` to be in `functions`.

    3. **Variable sorts must match function profiles.** If `add : Nat × Nat → Nat`,
       then `app("add", x, y)` requires `x` and `y` to have sort `Nat`.

    4. **Equation sides must have the same sort.** In `eq(lhs, rhs)`, both sides
       must resolve to the same sort.

    5. **Field access requires a product sort.** `FieldAccess(term, "severity")`
       requires `term` to have a product sort that declares a `"severity"` field.

    6. **Partial functions should be marked.** Functions like `top` or `pop` that
       are undefined for some inputs should use `total=False`.

    7. **Constants are zero-arity functions.** Use `fn("zero", [], "Nat")` and
       `const("zero")` in terms — not a special constant type.
    """
        )
    )

    return "\n".join(parts)


if __name__ == "__main__":
    print(generate_reference())
