import textwrap


def render() -> str:
    return (
        textwrap.dedent(
            """\
        ## 5. Well-Formedness Rules & Axiom Methodology

        ### Well-Formedness Checklist

        1. **Every sort referenced must be declared.** A function returning `"Severity"`
           requires a sort `"Severity"` in the signature.
        2. **Every function/predicate used in terms must be declared.** `app("classify", t, b)`
           requires `"classify"` in `functions`.
        3. **Variable sorts must match function profiles.** If `add : Nat × Nat → Nat`,
           then `app("add", x, y)` requires `x` and `y` to have sort `Nat`.
        4. **Equation sides must have the same sort.** In `eq(lhs, rhs)`, both sides
           must resolve to the same sort.
        5. **Field access requires a product sort.** `FieldAccess(term, "severity")`
           requires `term` to have a product sort declaring a `"severity"` field.
        6. **Constants are zero-arity functions.** Declare with `fn("zero", [], "Nat")`
           and use with `const("zero")`.
        7. **Mark partial functions.** Functions undefined for some inputs use `total=False`.

        """
        )
        + render_steps()
        + textwrap.dedent(
            """\
        ### Partial Functions

        - Declare partial functions with `total=False`.
        - Omit the constructor case where the function is undefined.
        - The partiality declaration itself encodes undefinedness — no explicit axiom needed.
        - Example: `top : Stack →? Elem` has an axiom for `push` but not for `new`.

        ---
        """
        )
    )


def render_steps() -> str:
    return textwrap.dedent(
        """\
        ### Axiom Obligation Pattern (Core Methodology)

        For each **observer** (function or predicate) of a sort, and each **constructor**
        of that sort's primary argument, write **one axiom per (observer, constructor) pair**.

        **Process:**
        1. List the constructors of the observer's primary argument sort.
        2. For each constructor, write an axiom specifying the observer applied to that constructor.
        3. For **partial** observers, *omit* the constructor case where the function is
           undefined. The `total=False` declaration handles the undefinedness — no explicit
           "undefined" axiom is needed.

        **Axiom obligation table format:**

        | Observer | Constructor | Axiom |
        |----------|------------|-------|
        | `pop : Stack →? Stack` | `new` | *(omitted — pop is partial, undefined on new)* |
        | `pop : Stack →? Stack` | `push(S, e)` | `pop(push(S, e)) = S` |
        | `top : Stack →? Elem` | `new` | *(omitted — top is partial, undefined on new)* |
        | `top : Stack →? Elem` | `push(S, e)` | `top(push(S, e)) = e` |
        | `empty : Stack` | `new` | `empty(new)` |
        | `empty : Stack` | `push(S, e)` | `¬ empty(push(S, e))` |

        **Completeness check:** If an observer has `k` constructors for its primary sort
        and is total, it needs `k` axioms. If partial, it needs `k - (undefined cases)` axioms.

        """
    )
