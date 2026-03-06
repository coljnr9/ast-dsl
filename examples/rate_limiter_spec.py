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
    implication,
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
    - Function-valued derived observer (get_status via geq comparison)
    - Enumeration sort with explicit distinctness (Status: ok/exceeded)
    - Guard-split pattern for function-valued derived observer per-constructor axioms
    - Linked predicate and function derived observers (over_limit ↔ get_status)

    Obligation table: 3 observers × 4 constructors = 12 cells, all PLAIN.
    No key dispatch. No partial functions.
    Total axioms: 26 (20 obligation + 6 non-obligation).
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
            "Status": atomic("Status"),
        },
        functions={
            # Nat helpers (cross-sort, pattern 10)
            "zero": fn("zero", [], "Nat"),
            "succ": fn("succ", [("n", "Nat")], "Nat"),
            # Status enumeration
            "ok": fn("ok", [], "Status"),
            "exceeded": fn("exceeded", [], "Status"),
            # Limiter constructors
            "create": fn("create", [("m", "Nat")], "Limiter"),
            "record": fn("record", [("l", "Limiter")], "Limiter"),
            "reset": fn("reset", [("l", "Limiter")], "Limiter"),
            "set_max": fn("set_max", [("l", "Limiter"), ("n", "Nat")], "Limiter"),
            # Limiter observers
            "get_count": fn("get_count", [("l", "Limiter")], "Nat"),
            "get_max": fn("get_max", [("l", "Limiter")], "Nat"),
            # Limiter observer (derived — compositional from get_count and get_max)
            "get_status": fn("get_status", [("l", "Limiter")], "Status"),
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
            "Status": GeneratedSortInfo(
                constructors=("ok", "exceeded"),
                selectors={},
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
        # ENUMERATION DISTINCTNESS — Status
        # ok and exceeded are distinct constructors. Without this axiom,
        # loose semantics permits models where ok = exceeded.
        # ==================================================================
        Axiom(
            label="ok_exceeded_distinct",
            formula=negation(eq(const("ok"), const("exceeded"))),
        ),
        # ==================================================================
        # OBLIGATION CELLS — get_status (function-valued derived observer)
        # get_status is defined compositionally: exceeded when count ≥ max,
        # ok otherwise. For each constructor, determine how it changes the
        # component observers, then substitute:
        #
        #   record: get_count → succ(get_count(l)), get_max → get_max(l)
        #           guard = geq(succ(get_count(l)), get_max(l))
        #
        # This substitution process applies to every derived observer:
        # look up each component's per-constructor axiom, plug the post-values
        # into the derivation condition, write the result as a structural axiom.
        # A global definition does not satisfy obligation cells.
        # ==================================================================
        # Cell 13a: get_status × create — POSITIVE guard → exceeded
        Axiom(
            label="get_status_create_pos",
            formula=forall(
                [m],
                implication(
                    pred_app("geq", const("zero"), m),
                    eq(app("get_status", app("create", m)), const("exceeded")),
                ),
            ),
        ),
        # Cell 13b: get_status × create — NEGATIVE guard → ok
        Axiom(
            label="get_status_create_neg",
            formula=forall(
                [m],
                implication(
                    negation(pred_app("geq", const("zero"), m)),
                    eq(app("get_status", app("create", m)), const("ok")),
                ),
            ),
        ),
        # Cell 14a: get_status × record — POSITIVE guard → exceeded
        Axiom(
            label="get_status_record_pos",
            formula=forall(
                [l],
                implication(
                    pred_app("geq", app("succ", app("get_count", l)),
                        app("get_max", l)),
                    eq(app("get_status", app("record", l)), const("exceeded")),
                ),
            ),
        ),
        # Cell 14b: get_status × record — NEGATIVE guard → ok
        Axiom(
            label="get_status_record_neg",
            formula=forall(
                [l],
                implication(
                    negation(pred_app("geq", app("succ", app("get_count", l)),
                        app("get_max", l))),
                    eq(app("get_status", app("record", l)), const("ok")),
                ),
            ),
        ),
        # Cell 15a: get_status × reset — POSITIVE guard → exceeded
        Axiom(
            label="get_status_reset_pos",
            formula=forall(
                [l],
                implication(
                    pred_app("geq", const("zero"), app("get_max", l)),
                    eq(app("get_status", app("reset", l)), const("exceeded")),
                ),
            ),
        ),
        # Cell 15b: get_status × reset — NEGATIVE guard → ok
        Axiom(
            label="get_status_reset_neg",
            formula=forall(
                [l],
                implication(
                    negation(pred_app("geq", const("zero"), app("get_max", l))),
                    eq(app("get_status", app("reset", l)), const("ok")),
                ),
            ),
        ),
        # Cell 16a: get_status × set_max — POSITIVE guard → exceeded
        Axiom(
            label="get_status_set_max_pos",
            formula=forall(
                [l, n],
                implication(
                    pred_app("geq", app("get_count", l), n),
                    eq(app("get_status", app("set_max", l, n)), const("exceeded")),
                ),
            ),
        ),
        # Cell 16b: get_status × set_max — NEGATIVE guard → ok
        Axiom(
            label="get_status_set_max_neg",
            formula=forall(
                [l, n],
                implication(
                    negation(pred_app("geq", app("get_count", l), n)),
                    eq(app("get_status", app("set_max", l, n)), const("ok")),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — get_status (non-obligation)
        # Links the function-valued and predicate-valued derived observers:
        # get_status returns exceeded iff over_limit holds. This shows that
        # both forms (predicate and function) can be derived from the same
        # underlying condition, and both still require per-constructor
        # obligation axioms — a global definition does not substitute for
        # structural coverage.
        # ==================================================================
        Axiom(
            label="get_status_def",
            formula=forall(
                [l],
                iff(
                    eq(app("get_status", l), const("exceeded")),
                    pred_app("over_limit", l),
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
