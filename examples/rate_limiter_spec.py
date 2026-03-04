from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    iff,
    negation,
    pred,
    pred_app,
    var,
)


def rate_limiter_spec() -> Spec:
    """Rate Limiter specification.

    Models a rate limiter tracking request counts against a configured
    maximum per window. Demonstrates:

    - Selector extraction including multi-constructor selector (get_max
      is a selector of both create and set_max)
    - Selector foreign with preservation (total selectors on non-home ctors)
    - Cross-sort helpers (Nat with zero/succ)
    - Helper composition: succ(get_count(l)) in accumulator axiom
    - Accumulator pattern (get_count across constructors)
    - Comparison-driven predicate (over_limit via geq)
    - Inductive helper axioms (Peano definition of geq)
    - Preservation collapse across unrelated constructors

    Obligation table: 3 observers × 4 constructors = 12 cells, all PLAIN.
    No key dispatch. No partial functions.
    Total axioms: 16 (12 obligation + 4 non-obligation).
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
            # Nat helpers (cross-sort, pattern 10)
            "zero": fn("zero", [], "Nat"),
            "succ": fn("succ", [("n", "Nat")], "Nat"),
            # Limiter constructors
            "create": fn("create", [("m", "Nat")], "Limiter"),
            "record": fn("record", [("l", "Limiter")], "Limiter"),
            "reset": fn("reset", [("l", "Limiter")], "Limiter"),
            "set_max": fn("set_max", [("l", "Limiter"), ("n", "Nat")], "Limiter"),
            # Limiter observers
            "get_count": fn("get_count", [("l", "Limiter")], "Nat"),
            "get_max": fn("get_max", [("l", "Limiter")], "Nat"),
        },
        predicates={
            "geq": pred("geq", [("a", "Nat"), ("b", "Nat")]),
            "over_limit": pred("over_limit", [("l", "Limiter")]),
        },
        generated_sorts={
            "Limiter": GeneratedSortInfo(
                constructors=("create", "record", "reset", "set_max"),
                selectors={
                    "create": {"get_max": "Nat"},
                    "set_max": {"get_max": "Nat"},
                },
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS (mechanical)
        # ==================================================================
        # Cell 1: get_max × create — SELECTOR_EXTRACT
        Axiom(
            label="get_max_create",
            formula=forall(
                [m],
                eq(app("get_max", app("create", m)), m),
            ),
        ),
        # Cell 2: get_max × set_max — SELECTOR_EXTRACT
        # get_max is declared as a selector of both create and set_max.
        Axiom(
            label="get_max_set_max",
            formula=forall(
                [l, n],
                eq(app("get_max", app("set_max", l, n)), n),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_count (accumulator, pattern 13)
        # ==================================================================
        # Cell 3: get_count × create — basis: new limiter starts at zero
        Axiom(
            label="get_count_create",
            formula=forall(
                [m],
                eq(app("get_count", app("create", m)), const("zero")),
            ),
        ),
        # Cell 4: get_count × record — accumulate (pattern 12: helper
        # composition with succ applied to get_count)
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
        # Cell 5: get_count × reset — window rollover: zero count
        Axiom(
            label="get_count_reset",
            formula=forall(
                [l],
                eq(app("get_count", app("reset", l)), const("zero")),
            ),
        ),
        # Cell 6: get_count × set_max — preservation
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
        # ==================================================================
        # DOMAIN CELLS — over_limit (comparison-driven, pattern 18)
        # Each per-constructor axiom substitutes the post-constructor
        # values of get_count and get_max into the geq comparison.
        # ==================================================================
        # Cell 9: over_limit × create — count=zero vs max=m
        Axiom(
            label="over_limit_create",
            formula=forall(
                [m],
                iff(
                    pred_app("over_limit", app("create", m)),
                    pred_app("geq", const("zero"), m),
                ),
            ),
        ),
        # Cell 10: over_limit × record — count incremented vs max preserved
        Axiom(
            label="over_limit_record",
            formula=forall(
                [l],
                iff(
                    pred_app("over_limit", app("record", l)),
                    pred_app("geq", app("succ", app("get_count", l)),
                        app("get_max", l)),
                ),
            ),
        ),
        # Cell 11: over_limit × reset — count=zero vs max preserved
        Axiom(
            label="over_limit_reset",
            formula=forall(
                [l],
                iff(
                    pred_app("over_limit", app("reset", l)),
                    pred_app("geq", const("zero"), app("get_max", l)),
                ),
            ),
        ),
        # Cell 12: over_limit × set_max — count preserved vs new max
        Axiom(
            label="over_limit_set_max",
            formula=forall(
                [l, n],
                iff(
                    pred_app("over_limit", app("set_max", l, n)),
                    pred_app("geq", app("get_count", l), n),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — over_limit (non-obligation)
        # Defines over_limit compositionally: count ≥ max. The obligation
        # table still requires the per-constructor axioms above — this
        # definition provides the conceptual meaning but does not substitute
        # for obligation coverage.
        # ==================================================================
        Axiom(
            label="over_limit_def",
            formula=forall(
                [l],
                iff(
                    pred_app("over_limit", l),
                    pred_app("geq", app("get_count", l),
                        app("get_max", l)),
                ),
            ),
        ),
        # ==================================================================
        # HELPER AXIOMS — geq (inductive definition on Nat)
        # Without these axioms, loose semantics permits models where geq
        # is unconditionally false (or true), making over_limit vacuous.
        # These three axioms provide the minimal Peano characterization
        # of ≥ on natural numbers built from zero/succ.
        # ==================================================================
        # Every natural number is ≥ zero
        Axiom(
            label="geq_zero_base",
            formula=forall(
                [m],
                pred_app("geq", m, const("zero")),
            ),
        ),
        # Zero is not ≥ any successor
        Axiom(
            label="geq_zero_succ",
            formula=forall(
                [m],
                negation(pred_app("geq", const("zero"), app("succ", m))),
            ),
        ),
        # Inductive step: succ(a) ≥ succ(b) ⟺ a ≥ b
        Axiom(
            label="geq_succ_succ",
            formula=forall(
                [m, n],
                iff(
                    pred_app("geq", app("succ", m), app("succ", n)),
                    pred_app("geq", m, n),
                ),
            ),
        ),
    )

    return Spec(name="RateLimiter", signature=sig, axioms=axioms)
