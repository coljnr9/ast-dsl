from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    negation,
    pred,
    pred_app,
    var,
)


def connection_spec() -> Spec:
    """Connection specification.

    Models a network connection with state lifecycle. Demonstrates:

    - Selector vs total observer contrast:
      get_error (partial selector of fail) vs get_timeout (total observer)
    - Derivation link: is_active derived from get_state via biconditional
    - Preservation collapse (get_timeout across all state-transition constructors)
    - Selector extraction + foreign undefinedness (get_error)
    - Enumeration sort with explicit distinctness (State: idle/active/failed)
    - Opaque Nat: timeout is stored by create and retrieved by get_timeout
      unchanged — the basis library provides structured Nat with arithmetic
      and comparison, but none of that is needed here; when no axiom computes
      or compares values of a sort, leave it unstructured and do not import
      basis operations

    Obligation table: 4 observers × 5 constructors = 20 cells, all PLAIN.
    No key dispatch. get_error is partial; all other functions are total.
    Total axioms: 24 (20 obligation + 1 derivation definition + 3 distinctness).
    """
    # --- Variables ---
    c = var("c", "Conn")
    n = var("n", "Nat")
    e = var("e", "ErrorCode")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Conn": atomic("Conn"),
            "State": atomic("State"),
            "Nat": atomic("Nat"),
            "ErrorCode": atomic("ErrorCode"),
        },
        functions={
            # State enumeration
            "idle_st": fn("idle_st", [], "State"),
            "active_st": fn("active_st", [], "State"),
            "failed_st": fn("failed_st", [], "State"),
            # Conn constructors
            "create": fn("create", [("n", "Nat")], "Conn"),
            "connect": fn("connect", [("c", "Conn")], "Conn"),
            "disconnect": fn("disconnect", [("c", "Conn")], "Conn"),
            "fail": fn("fail", [("c", "Conn"), ("e", "ErrorCode")], "Conn"),
            "retry": fn("retry", [("c", "Conn")], "Conn"),
            # Conn observers
            "get_state": fn("get_state", [("c", "Conn")], "State"),
            "get_timeout": fn("get_timeout", [("c", "Conn")], "Nat"),
            "get_error": fn(
                "get_error", [("c", "Conn")], "ErrorCode", total=False
            ),
        },
        predicates={
            # Conn predicate observer (derived from get_state)
            "is_active": pred("is_active", [("c", "Conn")]),
        },
        generated_sorts={
            "Conn": GeneratedSortInfo(
                constructors=("create", "connect", "disconnect", "fail", "retry"),
                selectors={
                    "fail": {"get_error": "e"},
                },
            ),
            "State": GeneratedSortInfo(
                constructors=("idle_st", "active_st", "failed_st"),
                selectors={},
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS — get_error (genuine partial selector of fail)
        #
        # get_error is partial: defined only on fail, undefined elsewhere.
        # This is the CASL free-type pattern — fail injects an ErrorCode,
        # get_error extracts it. Mechanical axiom generation handles these.
        # ==================================================================
        # get_error × fail — SELECTOR_EXTRACT
        Axiom(
            label="get_error_fail",
            formula=forall(
                [c, e],
                eq(app("get_error", app("fail", c, e)), e),
            ),
        ),
        # get_error × create — SELECTOR_FOREIGN
        Axiom(
            label="get_error_create",
            formula=forall(
                [n],
                negation(definedness(app("get_error", app("create", n)))),
            ),
        ),
        # get_error × connect — SELECTOR_FOREIGN
        Axiom(
            label="get_error_connect",
            formula=forall(
                [c],
                negation(definedness(app("get_error", app("connect", c)))),
            ),
        ),
        # get_error × disconnect — SELECTOR_FOREIGN
        Axiom(
            label="get_error_disconnect",
            formula=forall(
                [c],
                negation(definedness(app("get_error", app("disconnect", c)))),
            ),
        ),
        # get_error × retry — SELECTOR_FOREIGN
        Axiom(
            label="get_error_retry",
            formula=forall(
                [c],
                negation(definedness(app("get_error", app("retry", c)))),
            ),
        ),
        # ==================================================================
        # get_state CELLS — DOMAIN
        # ==================================================================
        Axiom(
            label="get_state_create",
            formula=forall(
                [n],
                eq(app("get_state", app("create", n)), const("idle_st")),
            ),
        ),
        Axiom(
            label="get_state_connect",
            formula=forall(
                [c],
                eq(app("get_state", app("connect", c)), const("active_st")),
            ),
        ),
        Axiom(
            label="get_state_disconnect",
            formula=forall(
                [c],
                eq(app("get_state", app("disconnect", c)), const("idle_st")),
            ),
        ),
        Axiom(
            label="get_state_fail",
            formula=forall(
                [c, e],
                eq(app("get_state", app("fail", c, e)), const("failed_st")),
            ),
        ),
        Axiom(
            label="get_state_retry",
            formula=forall(
                [c],
                eq(app("get_state", app("retry", c)), const("idle_st")),
            ),
        ),
        # ==================================================================
        # get_timeout CELLS — DOMAIN (total observer, NOT a selector)
        #
        # get_timeout(create(n)) = n looks like selector extraction, but
        # get_timeout is total — defined on every constructor. A CASL
        # selector must be partial (undefined on foreign constructors).
        # get_timeout is an observer whose create axiom coincidentally
        # resembles projection. The preservation axioms are domain equations
        # asserting configuration immutability, not structural consequences.
        # ==================================================================
        Axiom(
            label="get_timeout_create",
            formula=forall(
                [n],
                eq(app("get_timeout", app("create", n)), n),
            ),
        ),
        Axiom(
            label="get_timeout_connect",
            formula=forall(
                [c],
                eq(
                    app("get_timeout", app("connect", c)),
                    app("get_timeout", c),
                ),
            ),
        ),
        Axiom(
            label="get_timeout_disconnect",
            formula=forall(
                [c],
                eq(
                    app("get_timeout", app("disconnect", c)),
                    app("get_timeout", c),
                ),
            ),
        ),
        Axiom(
            label="get_timeout_fail",
            formula=forall(
                [c, e],
                eq(
                    app("get_timeout", app("fail", c, e)),
                    app("get_timeout", c),
                ),
            ),
        ),
        Axiom(
            label="get_timeout_retry",
            formula=forall(
                [c],
                eq(
                    app("get_timeout", app("retry", c)),
                    app("get_timeout", c),
                ),
            ),
        ),
        # ==================================================================
        # is_active CELLS — DOMAIN (derived from get_state)
        # ==================================================================
        Axiom(
            label="is_active_create",
            formula=forall(
                [n],
                negation(pred_app("is_active", app("create", n))),
            ),
        ),
        Axiom(
            label="is_active_connect",
            formula=forall(
                [c],
                pred_app("is_active", app("connect", c)),
            ),
        ),
        Axiom(
            label="is_active_disconnect",
            formula=forall(
                [c],
                negation(pred_app("is_active", app("disconnect", c))),
            ),
        ),
        Axiom(
            label="is_active_fail",
            formula=forall(
                [c, e],
                negation(pred_app("is_active", app("fail", c, e))),
            ),
        ),
        Axiom(
            label="is_active_retry",
            formula=forall(
                [c],
                negation(pred_app("is_active", app("retry", c))),
            ),
        ),
        # ==================================================================
        # NON-OBLIGATION AXIOMS
        # ==================================================================
        # Derivation definition — is_active is a conservative extension.
        # This is a definitional extension (conservative) — is_active adds no
        # semantic content beyond get_state, but provides a convenient boolean
        # query. The obligation table still requires per-constructor axioms
        # above — this definition provides the derivation link but does not
        # substitute for obligation coverage.
        # ==================================================================
        Axiom(
            label="is_active_def",
            formula=forall(
                [c],
                iff(
                    pred_app("is_active", c),
                    eq(app("get_state", c), const("active_st")),
                ),
            ),
        ),
        # ==================================================================
        # ENUMERATION DISTINCTNESS — State
        # idle_st, active_st, and failed_st are distinct constructors.
        # Without these axioms, loose semantics permits models where
        # idle_st = active_st, which would collapse the state machine.
        # ==================================================================
        Axiom(
            label="state_distinct_idle_active",
            formula=negation(eq(const("idle_st"), const("active_st"))),
        ),
        Axiom(
            label="state_distinct_idle_failed",
            formula=negation(eq(const("idle_st"), const("failed_st"))),
        ),
        Axiom(
            label="state_distinct_active_failed",
            formula=negation(eq(const("active_st"), const("failed_st"))),
        ),
    )

    return Spec(name="Connection", signature=sig, axioms=axioms)
