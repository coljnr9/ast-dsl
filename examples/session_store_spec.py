from alspec import (
    Axiom,
    Conjunction,
    Definedness,
    GeneratedSortInfo,
    Implication,
    Negation,
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


def session_store_spec() -> Spec:
    """Session Store specification.

    Models a single authentication session lifecycle with token-based
    verification, expiry, and refresh. Demonstrates:

    - Selector extraction + foreign (get_token, last_input)
    - Equality predicate basis axioms (eq_token)
    - Partial constructor with definedness biconditional (refresh)
    - Enumeration sort (Status: active/expired)
    - Domain case split in PLAIN cell (is_verified × verify)
    - State verification — guard references stored observer value (get_token)
    - Derived/composite predicate (needs_auth)
    - Guarded preservation on partial constructor (all observers × refresh)

    Obligation table: 4 observers × 4 constructors = 16 cells.
    All cells PLAIN (no key dispatch — observers take no key parameter).
    Total axioms: 27 (22 obligation + 3 basis + 1 definedness + 1 derived).
    """
    # --- Variables ---
    s = var("s", "Session")
    t = var("t", "Token")
    t2 = var("t2", "Token")
    t3 = var("t3", "Token")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Session": atomic("Session"),
            "Token": atomic("Token"),
            "Status": atomic("Status"),
        },
        functions={
            # Status enumeration (pattern 11)
            "active": fn("active", [], "Status"),
            "expired": fn("expired", [], "Status"),
            # Session constructors
            "create": fn("create", [("t", "Token")], "Session"),
            "verify": fn("verify", [("s", "Session"), ("t", "Token")], "Session"),
            "expire": fn("expire", [("s", "Session")], "Session"),
            "refresh": fn(
                "refresh", [("s", "Session")], "Session", total=False
            ),
            # Session observers
            "get_token": fn("get_token", [("s", "Session")], "Token"),
            "get_status": fn("get_status", [("s", "Session")], "Status"),
            "last_input": fn(
                "last_input", [("s", "Session")], "Token", total=False
            ),
        },
        predicates={
            "eq_token": pred("eq_token", [("t1", "Token"), ("t2", "Token")]),
            "is_verified": pred("is_verified", [("s", "Session")]),
            "needs_auth": pred("needs_auth", [("s", "Session")]),
        },
        generated_sorts={
            "Session": GeneratedSortInfo(
                constructors=("create", "verify", "expire", "refresh"),
                selectors={
                    "create": {"get_token": "Token"},
                    "verify": {"last_input": "Token"},
                },
            ),
            "Status": GeneratedSortInfo(
                constructors=("active", "expired"),
                selectors={},
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS (mechanical)
        # ==================================================================
        # Cell 1: get_token × create — SELECTOR_EXTRACT
        Axiom(
            label="get_token_create",
            formula=forall(
                [t],
                eq(app("get_token", app("create", t)), t),
            ),
        ),
        # Cell 10: last_input × verify — SELECTOR_EXTRACT
        Axiom(
            label="last_input_verify",
            formula=forall(
                [s, t],
                eq(app("last_input", app("verify", s, t)), t),
            ),
        ),
        # Cell 9: last_input × create — SELECTOR_FOREIGN
        Axiom(
            label="last_input_create_undef",
            formula=forall(
                [t],
                Negation(Definedness(app("last_input", app("create", t)))),
            ),
        ),
        # ==================================================================
        # BASIS AXIOMS — eq_token (pattern 6, §9h)
        # ==================================================================
        # Reflexivity
        Axiom(
            label="eq_token_refl",
            formula=forall(
                [t],
                PredApp("eq_token", (t, t)),
            ),
        ),
        # Symmetry
        Axiom(
            label="eq_token_sym",
            formula=forall(
                [t, t2],
                Implication(
                    PredApp("eq_token", (t, t2)),
                    PredApp("eq_token", (t2, t)),
                ),
            ),
        ),
        # Transitivity
        Axiom(
            label="eq_token_trans",
            formula=forall(
                [t, t2, t3],
                Implication(
                    Conjunction((
                        PredApp("eq_token", (t, t2)),
                        PredApp("eq_token", (t2, t3)),
                    )),
                    PredApp("eq_token", (t, t3)),
                ),
            ),
        ),
        # ==================================================================
        # CONSTRUCTOR DEFINEDNESS — refresh (pattern 9, §9f)
        # ==================================================================
        Axiom(
            label="refresh_def",
            formula=forall(
                [s],
                iff(
                    Definedness(app("refresh", s)),
                    eq(app("get_status", s), const("active")),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_token (preservation)
        # ==================================================================
        # Cell 2: get_token × verify — preservation
        Axiom(
            label="get_token_verify",
            formula=forall(
                [s, t],
                eq(
                    app("get_token", app("verify", s, t)),
                    app("get_token", s),
                ),
            ),
        ),
        # Cell 3: get_token × expire — preservation
        Axiom(
            label="get_token_expire",
            formula=forall(
                [s],
                eq(
                    app("get_token", app("expire", s)),
                    app("get_token", s),
                ),
            ),
        ),
        # Cell 4: get_token × refresh — guarded preservation
        Axiom(
            label="get_token_refresh",
            formula=forall(
                [s],
                Implication(
                    eq(app("get_status", s), const("active")),
                    eq(
                        app("get_token", app("refresh", s)),
                        app("get_token", s),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_status
        # ==================================================================
        # Cell 5: get_status × create — basis
        Axiom(
            label="get_status_create",
            formula=forall(
                [t],
                eq(app("get_status", app("create", t)), const("active")),
            ),
        ),
        # Cell 6: get_status × verify — preservation
        Axiom(
            label="get_status_verify",
            formula=forall(
                [s, t],
                eq(
                    app("get_status", app("verify", s, t)),
                    app("get_status", s),
                ),
            ),
        ),
        # Cell 7: get_status × expire
        Axiom(
            label="get_status_expire",
            formula=forall(
                [s],
                eq(app("get_status", app("expire", s)), const("expired")),
            ),
        ),
        # Cell 8: get_status × refresh — guarded
        Axiom(
            label="get_status_refresh",
            formula=forall(
                [s],
                Implication(
                    eq(app("get_status", s), const("active")),
                    eq(
                        app("get_status", app("refresh", s)),
                        const("active"),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — last_input (preservation)
        # ==================================================================
        # Cell 11: last_input × expire — preservation (strong equality)
        Axiom(
            label="last_input_expire",
            formula=forall(
                [s],
                eq(
                    app("last_input", app("expire", s)),
                    app("last_input", s),
                ),
            ),
        ),
        # Cell 12: last_input × refresh — guarded preservation (strong equality)
        Axiom(
            label="last_input_refresh",
            formula=forall(
                [s],
                Implication(
                    eq(app("get_status", s), const("active")),
                    eq(
                        app("last_input", app("refresh", s)),
                        app("last_input", s),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — is_verified (pattern 3)
        # ==================================================================
        # Cell 13: is_verified × create — basis
        Axiom(
            label="is_verified_create",
            formula=forall(
                [t],
                Negation(PredApp("is_verified", (app("create", t),))),
            ),
        ),
        # Cell 14a: is_verified × verify — POSITIVE polarity (patterns 17, 20)
        # Guard: eq_token(t, get_token(s)) ∧ get_status(s) = active
        Axiom(
            label="is_verified_verify_hit",
            formula=forall(
                [s, t],
                Implication(
                    Conjunction((
                        PredApp("eq_token", (t, app("get_token", s))),
                        eq(app("get_status", s), const("active")),
                    )),
                    PredApp("is_verified", (app("verify", s, t),)),
                ),
            ),
        ),
        # Cell 14b: is_verified × verify — NEGATIVE polarity
        # Guard negated: wrong token OR expired session → preserve
        Axiom(
            label="is_verified_verify_miss",
            formula=forall(
                [s, t],
                Implication(
                    Negation(
                        Conjunction((
                            PredApp("eq_token", (t, app("get_token", s))),
                            eq(app("get_status", s), const("active")),
                        )),
                    ),
                    iff(
                        PredApp("is_verified", (app("verify", s, t),)),
                        PredApp("is_verified", (s,)),
                    ),
                ),
            ),
        ),
        # Cell 15: is_verified × expire
        Axiom(
            label="is_verified_expire",
            formula=forall(
                [s],
                Negation(PredApp("is_verified", (app("expire", s),))),
            ),
        ),
        # Cell 16: is_verified × refresh — guarded
        Axiom(
            label="is_verified_refresh",
            formula=forall(
                [s],
                Implication(
                    eq(app("get_status", s), const("active")),
                    Negation(
                        PredApp("is_verified", (app("refresh", s),)),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # OBLIGATION CELLS — needs_auth (pattern 19)
        # The per-constructor axioms are derivable from needs_auth_def +
        # the is_verified and get_status axioms. We write both: the
        # definition teaches the "derived predicate" pattern, and the
        # per-constructor axioms satisfy obligation table completeness.
        # ==================================================================
        # Cell 17: needs_auth × create — active ∧ ¬verified → needs_auth
        Axiom(
            label="needs_auth_create",
            formula=forall(
                [t],
                PredApp("needs_auth", (app("create", t),)),
            ),
        ),
        # Cell 18a: needs_auth × verify — POSITIVE guard → ¬needs_auth
        Axiom(
            label="needs_auth_verify_hit",
            formula=forall(
                [s, t],
                Implication(
                    Conjunction((
                        PredApp("eq_token", (t, app("get_token", s))),
                        eq(app("get_status", s), const("active")),
                    )),
                    Negation(PredApp("needs_auth", (app("verify", s, t),))),
                ),
            ),
        ),
        # Cell 18b: needs_auth × verify — NEGATIVE guard → preserve
        Axiom(
            label="needs_auth_verify_miss",
            formula=forall(
                [s, t],
                Implication(
                    Negation(
                        Conjunction((
                            PredApp("eq_token", (t, app("get_token", s))),
                            eq(app("get_status", s), const("active")),
                        )),
                    ),
                    iff(
                        PredApp("needs_auth", (app("verify", s, t),)),
                        PredApp("needs_auth", (s,)),
                    ),
                ),
            ),
        ),
        # Cell 19: needs_auth × expire — expired → ¬needs_auth
        Axiom(
            label="needs_auth_expire",
            formula=forall(
                [s],
                Negation(PredApp("needs_auth", (app("expire", s),))),
            ),
        ),
        # Cell 20: needs_auth × refresh — guarded: refresh clears verification
        Axiom(
            label="needs_auth_refresh",
            formula=forall(
                [s],
                Implication(
                    eq(app("get_status", s), const("active")),
                    PredApp("needs_auth", (app("refresh", s),)),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — needs_auth (pattern 19, non-obligation)
        # This standalone biconditional defines needs_auth in terms of
        # get_status and is_verified. It is logically redundant with the
        # per-constructor axioms above, but teaches the "derived predicate"
        # pattern: a predicate whose meaning is defined compositionally
        # rather than by constructor analysis.
        # ==================================================================
        Axiom(
            label="needs_auth_def",
            formula=forall(
                [s],
                iff(
                    PredApp("needs_auth", (s,)),
                    Conjunction((
                        eq(app("get_status", s), const("active")),
                        Negation(PredApp("is_verified", (s,))),
                    )),
                ),
            ),
        ),
    )

    return Spec(name="SessionStore", signature=sig, axioms=axioms)
