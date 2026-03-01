from alspec import (
    Axiom,
    GeneratedSortInfo,
    PredApp,
    Signature,
    Spec,
    atomic,
    fn,
    pred,
    var,
    app,
    const,
    eq,
    forall,
    iff,
)


def rate_limiter_spec() -> Spec:
    """Rate Limiter specification.

    Models a rate limiter tracking request counts against a configured
    maximum per window with a configurable warning threshold. Demonstrates:

    - Selector extraction including multi-constructor selector (get_max)
    - Selector foreign with preservation (total selectors on non-home ctors)
    - Cross-sort helpers (Nat with zero/succ)
    - Helper composition: succ(get_count(l))
    - Accumulator pattern (get_count across 5 constructors)
    - Comparison-driven predicate (over_limit via geq)
    - Preservation collapse across unrelated constructors

    Obligation table: 4 observers × 5 constructors = 20 cells, all PLAIN.
    No key dispatch. No partial functions.
    Total axioms: 21 (20 obligation + 1 derived definition).
    """
    # --- Variables ---
    l = var("l", "Limiter")
    m = var("m", "Nat")
    n = var("n", "Nat")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Limiter": atomic("Limiter"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Nat helpers (pattern 10)
            "zero": fn("zero", [], "Nat"),
            "succ": fn("succ", [("n", "Nat")], "Nat"),
            # Limiter constructors
            "create": fn("create", [("m", "Nat")], "Limiter"),
            "record": fn("record", [("l", "Limiter")], "Limiter"),
            "reset": fn("reset", [("l", "Limiter")], "Limiter"),
            "set_max": fn("set_max", [("l", "Limiter"), ("n", "Nat")], "Limiter"),
            "set_warn": fn("set_warn", [("l", "Limiter"), ("n", "Nat")], "Limiter"),
            # Limiter observers
            "get_count": fn("get_count", [("l", "Limiter")], "Nat"),
            "get_max": fn("get_max", [("l", "Limiter")], "Nat"),
            "get_warn": fn("get_warn", [("l", "Limiter")], "Nat"),
        },
        predicates={
            "geq": pred("geq", [("a", "Nat"), ("b", "Nat")]),
            "over_limit": pred("over_limit", [("l", "Limiter")]),
        },
        generated_sorts={
            "Limiter": GeneratedSortInfo(
                constructors=("create", "record", "reset", "set_max", "set_warn"),
                selectors={
                    "create": {"get_max": "Nat"},
                    "set_max": {"get_max": "Nat"},
                    "set_warn": {"get_warn": "Nat"},
                },
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS (mechanical)
        # ==================================================================
        # Cell 6: get_max × create — SELECTOR_EXTRACT
        Axiom(
            label="get_max_create",
            formula=forall(
                [m],
                eq(app("get_max", app("create", m)), m),
            ),
        ),
        # Cell 9: get_max × set_max — extraction (tier says foreign, but
        # get_max is also a selector of set_max; matcher accepts this)
        Axiom(
            label="get_max_set_max",
            formula=forall(
                [l, n],
                eq(app("get_max", app("set_max", l, n)), n),
            ),
        ),
        # Cell 15: get_warn × set_warn — SELECTOR_EXTRACT
        Axiom(
            label="get_warn_set_warn",
            formula=forall(
                [l, n],
                eq(app("get_warn", app("set_warn", l, n)), n),
            ),
        ),
        # Cell 11: get_warn × create — DOMAIN (default: warn threshold = max)
        Axiom(
            label="get_warn_create",
            formula=forall(
                [m],
                eq(app("get_warn", app("create", m)), m),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_count (accumulator, pattern 13)
        # ==================================================================
        # Cell 1: get_count × create — basis: new limiter starts at zero
        Axiom(
            label="get_count_create",
            formula=forall(
                [m],
                eq(app("get_count", app("create", m)), const("zero")),
            ),
        ),
        # Cell 2: get_count × record — accumulate (pattern 12: helper composition)
        Axiom(
            label="get_count_record",
            formula=forall(
                [l],
                eq(
                    app("get_count", app("record", l)),
                    app("succ", app("get_count", l)),
                ),
            ),
        ),
        # Cell 3: get_count × reset — window rollover: zero count
        Axiom(
            label="get_count_reset",
            formula=forall(
                [l],
                eq(app("get_count", app("reset", l)), const("zero")),
            ),
        ),
        # Cell 4: get_count × set_max — preservation
        Axiom(
            label="get_count_set_max",
            formula=forall(
                [l, n],
                eq(
                    app("get_count", app("set_max", l, n)),
                    app("get_count", l),
                ),
            ),
        ),
        # Cell 5: get_count × set_warn — preservation
        Axiom(
            label="get_count_set_warn",
            formula=forall(
                [l, n],
                eq(
                    app("get_count", app("set_warn", l, n)),
                    app("get_count", l),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_max (preservation on non-extract cells)
        # ==================================================================
        # Cell 7: get_max × record — preservation
        Axiom(
            label="get_max_record",
            formula=forall(
                [l],
                eq(
                    app("get_max", app("record", l)),
                    app("get_max", l),
                ),
            ),
        ),
        # Cell 8: get_max × reset — preservation
        Axiom(
            label="get_max_reset",
            formula=forall(
                [l],
                eq(
                    app("get_max", app("reset", l)),
                    app("get_max", l),
                ),
            ),
        ),
        # Cell 10: get_max × set_warn — preservation
        Axiom(
            label="get_max_set_warn",
            formula=forall(
                [l, n],
                eq(
                    app("get_max", app("set_warn", l, n)),
                    app("get_max", l),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_warn (preservation on non-extract cells)
        # ==================================================================
        # Cell 12: get_warn × record — preservation
        Axiom(
            label="get_warn_record",
            formula=forall(
                [l],
                eq(
                    app("get_warn", app("record", l)),
                    app("get_warn", l),
                ),
            ),
        ),
        # Cell 13: get_warn × reset — preservation
        Axiom(
            label="get_warn_reset",
            formula=forall(
                [l],
                eq(
                    app("get_warn", app("reset", l)),
                    app("get_warn", l),
                ),
            ),
        ),
        # Cell 14: get_warn × set_max — preservation
        Axiom(
            label="get_warn_set_max",
            formula=forall(
                [l, n],
                eq(
                    app("get_warn", app("set_max", l, n)),
                    app("get_warn", l),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — over_limit (comparison-driven, pattern 18)
        # ==================================================================
        # Cell 16: over_limit × create — count=zero vs max=m
        Axiom(
            label="over_limit_create",
            formula=forall(
                [m],
                iff(
                    PredApp("over_limit", (app("create", m),)),
                    PredApp("geq", (const("zero"), m)),
                ),
            ),
        ),
        # Cell 17: over_limit × record — count incremented vs max preserved
        Axiom(
            label="over_limit_record",
            formula=forall(
                [l],
                iff(
                    PredApp("over_limit", (app("record", l),)),
                    PredApp("geq", (
                        app("succ", app("get_count", l)),
                        app("get_max", l),
                    )),
                ),
            ),
        ),
        # Cell 18: over_limit × reset — count=zero vs max preserved
        Axiom(
            label="over_limit_reset",
            formula=forall(
                [l],
                iff(
                    PredApp("over_limit", (app("reset", l),)),
                    PredApp("geq", (const("zero"), app("get_max", l))),
                ),
            ),
        ),
        # Cell 19: over_limit × set_max — count preserved vs new max
        Axiom(
            label="over_limit_set_max",
            formula=forall(
                [l, n],
                iff(
                    PredApp("over_limit", (app("set_max", l, n),)),
                    PredApp("geq", (app("get_count", l), n)),
                ),
            ),
        ),
        # Cell 20: over_limit × set_warn — preservation (set_warn changes
        # neither count nor max)
        Axiom(
            label="over_limit_set_warn",
            formula=forall(
                [l, n],
                iff(
                    PredApp("over_limit", (app("set_warn", l, n),)),
                    PredApp("over_limit", (l,)),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — over_limit (pattern 18, non-obligation)
        # Standalone definition: over_limit holds when count >= max.
        # Logically redundant with per-constructor axioms above, but
        # teaches the comparison-driven predicate pattern.
        # ==================================================================
        Axiom(
            label="over_limit_def",
            formula=forall(
                [l],
                iff(
                    PredApp("over_limit", (l,)),
                    PredApp("geq", (
                        app("get_count", l),
                        app("get_max", l),
                    )),
                ),
            ),
        ),
    )

    return Spec(name="RateLimiter", signature=sig, axioms=axioms)
