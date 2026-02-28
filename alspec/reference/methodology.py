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
        + render_partial_functions()
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
        3. For **partial** observers, you still need axioms for ALL constructors — some will
           be equations (where the observer is defined), some will be `Negation(Definedness(...))`
           assertions (where the observer is undefined). No exceptions — every cell must be filled.

        **Axiom obligation table format (Stack — selectors have mechanically derivable axioms):**

        | Observer | Constructor | Axiom |
        |----------|------------|-------|
        | `pop : Stack →? Stack` | `new` | `¬def(pop(new))` — explicit undefinedness |
        | `pop : Stack →? Stack` | `push(S, e)` | `pop(push(S, e)) = S` |
        | `top : Stack →? Elem` | `new` | `¬def(top(new))` — explicit undefinedness |
        | `top : Stack →? Elem` | `push(S, e)` | `top(push(S, e)) = e` |
        | `empty : Stack` | `new` | `empty(new)` |
        | `empty : Stack` | `push(S, e)` | `¬ empty(push(S, e))` |

        Note: `top` and `pop` are *selectors* of `push` — their axioms on `push` are mechanical
        extraction (`top(push(S,e)) = e`, `pop(push(S,e)) = S`). Their axioms on `new` must be
        explicit undefinedness: `¬def(top(new))` and `¬def(pop(new))`.

        **Axiom obligation table format (FiniteMap — destructive constructor needs explicit undefinedness):**

        | Observer | Constructor | Axiom |
        |----------|------------|-------|
        | `lookup : Map × Key →? Val` | `empty` | `¬def(lookup(empty, k))` — explicit undefinedness |
        | `lookup : Map × Key →? Val` | `update` hit | `lookup(update(m,k,v), k2) = v` |
        | `lookup : Map × Key →? Val` | `update` miss | delegates to `lookup(m, k2)` |
        | `lookup : Map × Key →? Val` | `remove` hit | `¬def(lookup(remove(m,k), k2))` — explicit undefinedness |
        | `lookup : Map × Key →? Val` | `remove` miss | delegates to `lookup(m, k2)` |

        **Completeness check:** If an observer has `k` constructors for its primary sort,
        it needs `k` axioms — no exceptions. Total observers produce equations.
        Partial observers produce either equations (where defined) or
        `Negation(Definedness(...))` assertions (where undefined). Every cell must
        be filled.

        **Stack completeness count:**
        - `pop`: 2 constructors = 2 axioms (1 undefinedness + 1 equation)
        - `top`: 2 constructors = 2 axioms (1 undefinedness + 1 equation)
        - `empty`: 2 constructors = 2 axioms
        Total expected axioms: 6.

        """
    )


def render_partial_functions() -> str:
    return textwrap.dedent(
        """\
        ### Partial Functions and Definedness

        **Critical: Under loose semantics, omitting an axiom does NOT make a function
        undefined — it leaves the interpretation unconstrained.** Any value is valid
        in some model. To force undefinedness, you must write an explicit axiom.

        **No omissions — every cell must be filled:**
        Under loose semantics, omitting an axiom for a partial observer on a base
        constructor does NOT make it undefined — it leaves the value unconstrained.
        Always write explicit `Negation(Definedness(...))` axioms. For example:
        `¬def(top(new))` and `¬def(pop(new))` are required axioms for the Stack,
        not optional annotations.

        Formal basis: CASL `free type` declarations mechanically generate
        `¬def(selector(foreign_constructor))` for every selector/constructor pair
        where the selector is not declared as a component of that constructor
        (CASL Reference Manual §2.3.4). Under Alspec's loose semantics, these must
        be stated explicitly since they are not automatic.

        **Three patterns for handling partiality:**

        **Pattern 1: Partial constructors (e.g., `withdraw`, `remove_stock`, `inc`).**
        Add a `Definedness` biconditional stating exactly when the constructor is defined.
        Observer axioms only need the defined case — strict error propagation handles
        the rest (undefined constructor → undefined observation automatically).

        ```python
        # withdraw is defined exactly when balance >= amount
        Axiom("withdraw_def", forall([a, n], iff(
            Definedness(app("withdraw", a, n)),
            PredApp("geq", (app("balance", a), n))
        )))
        # Observer axioms only cover the defined case:
        Axiom("balance_withdraw", forall([a, n], Implication(
            PredApp("geq", (app("balance", a), n)),
            eq(app("balance", app("withdraw", a, n)), app("sub", app("balance", a), n))
        )))
        ```

        **Pattern 2: Partial observers becoming undefined (e.g., `lookup` after `remove`,
        `get_assignee` after `create_ticket`, selectors on foreign constructors).**
        Write an explicit `Negation(Definedness(...))` axiom. This is required whenever
        an observer should be undefined on a specific constructor — either because the
        constructor destroys the relevant entry, because the constructor creates an
        entry without initializing this observer's value, or because a selector is
        applied to a constructor it doesn't belong to.

        ```python
        # Removing a key makes lookup explicitly undefined
        Axiom("lookup_remove_hit", forall([m, k, k2], Implication(
            PredApp("eq_key", (k, k2)),
            Negation(Definedness(app("lookup", app("remove", m, k), k2)))
        )))
        # New tickets have no assignee — explicitly undefined
        Axiom("get_assignee_create_hit", forall([s, k, k2, t, b], Implication(
            PredApp("eq_id", (k, k2)),
            Negation(Definedness(
                app("get_assignee", app("create_ticket", s, k, t, b), k2)
            ))
        )))
        # Stack selectors undefined on the base constructor
        Axiom("pop_new_undef", Negation(Definedness(app("pop", const("new")))))
        Axiom("top_new_undef", Negation(Definedness(app("top", const("new")))))
        ```

        **Pattern 3: Total constructors with existence guards — both polarities needed.**
        When a total constructor's observer axiom is guarded by an existence predicate
        (e.g., `has_ticket`), the negated guard needs a delegation axiom. The operation
        is a no-op on non-existent entries, but you must say so explicitly.

        ```python
        # resolve_ticket hit WITH ticket: status becomes resolved
        Axiom("get_status_resolve_hit", forall([s, k, k2], Implication(
            PredApp("eq_id", (k, k2)),
            Implication(
                PredApp("has_ticket", (s, k)),
                eq(app("get_status", app("resolve_ticket", s, k), k2), const("resolved"))
            )
        )))
        # resolve_ticket hit WITHOUT ticket: no-op, delegates
        Axiom("get_status_resolve_hit_noticket", forall([s, k, k2], Implication(
            PredApp("eq_id", (k, k2)),
            Implication(
                Negation(PredApp("has_ticket", (s, k))),
                eq(app("get_status", app("resolve_ticket", s, k), k2), app("get_status", s, k2))
            )
        )))
        ```

        - Declare partial functions with `total=False`.
        - Use `Definedness(term)` and `Negation(Definedness(term))` to control
          where functions are defined or undefined.
        - For partial constructors, always add a `Definedness` biconditional.
        - For partial observers on destructive or non-initializing constructors,
          always add `Negation(Definedness(...))`.
        - For selectors on foreign constructors (constructors they don't belong to),
          always add `Negation(Definedness(...))`.

        ---
        """
    )
