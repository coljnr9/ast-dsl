import textwrap


def render() -> str:
    return textwrap.dedent(
        """\
        ## 6. Worked Example: Bug Tracker with Ticket Store

        This section walks through the complete methodology for producing a
        specification. Follow these steps in order for every spec you write.

        ### Step 1: Identify Your Sorts

        Start by listing the domain's data. For each, decide: atomic (opaque
        identifier), product (struct with fields), or enumeration (finite set of
        constants).

        **Reasoning through each sort:**

        - `TicketId`, `Title`, `Body`, `UserId` — These are identifiers or text blobs
          with no internal structure we need to reason about. → **atomic**

        - `SeverityLevel` — This could be an enumeration (low/medium/high), but we're
          going to let `classify` determine severity, so we only need `high` as a
          named constant for the `is_critical` predicate. The other values exist but
          we don't need to name them all. → **atomic**, with `high` as a constant

        - `Status` — Finite set: open, resolved. These are the only two values.
          In CASL, model this as an **atomic sort with nullary constructors** (not a
          CoproductSort — Status has no carried data, it's just labels).

        - `Store` — This is the central domain object. We're modeling a **collection**
          of tickets, not a single ticket. Individual tickets don't exist as first-class
          values — they're implicit in the Store. All ticket properties are accessed
          through store observers with a `TicketId` key.

          *Why not have a `Ticket` sort?* Because we want the FiniteMap pattern:
          the Store is indexed by TicketId, and all observations go through the Store.
          This is the standard algebraic approach for collections. Making Ticket a
          separate sort would require modeling insertion/lookup separately, adding
          complexity without benefit.

        | Sort | Kind | Rationale |
        |------|------|----------|
        | `TicketId` | atomic | Opaque identifier — keys for lookup |
        | `Title` | atomic | Opaque text blob |
        | `Body` | atomic | Opaque text blob |
        | `SeverityLevel` | atomic | Uninterpreted — populated by `classify` |
        | `Status` | atomic (enumeration) | `open`, `resolved` as nullary constructors |
        | `UserId` | atomic | Opaque identifier for assignees |
        | `Store` | atomic | The collection — opaque, behavior defined by axioms |

        ### Step 2: Classify Functions and Predicates

        **Constructors** build values of a sort. **Observers** query or decompose them.
        Every observer owes axioms against every constructor of its primary sort.

        **Reasoning through each function:**

        - `empty : → Store` — **Constructor**. Creates an empty store with no tickets.

        - `create_ticket : Store × TicketId × Title × Body → Store` — **Constructor**.
          Adds a new ticket to the store. Takes the existing store and returns a
          new store with one more ticket. Total.

        - `resolve_ticket : Store × TicketId → Store` — **Constructor**. Transitions
          a ticket's status to resolved. Total — resolving a nonexistent ticket
          is a no-op (the store is unchanged).

        - `assign_ticket : Store × TicketId × UserId → Store` — **Constructor**.
          Sets the assignee on a ticket. Total — assigning to a nonexistent ticket
          is a no-op.

        - `classify : Title × Body → SeverityLevel` — **Uninterpreted**. Nothing in
          the spec defines what classify returns. It appears only *inside* other
          axioms (e.g., `get_severity(...) = classify(t, b)`). At implementation
          time, this could be an LLM call, a rules engine, or a lookup table.

        - `get_status : Store × TicketId →? Status` — **Observer**, **partial**.
          Undefined if the ticket doesn't exist in the store. Every ticket that
          exists has a status, but querying a nonexistent ticket is undefined.

        - `get_severity : Store × TicketId →? SeverityLevel` — **Observer**, **partial**.
          Same reason as get_status.

        - `get_assignee : Store × TicketId →? UserId` — **Observer**, **doubly partial**.
          Undefined for TWO reasons: the ticket might not exist, AND even if it does,
          it might not have an assignee yet. A freshly created ticket has no assignee.

        - `open`, `resolved` — Nullary constructors of Status (enumeration constants).

        - `high` — Nullary constructor of SeverityLevel (needed for is_critical).

        **Reasoning through predicates:**

        - `eq_id : TicketId × TicketId` — **Helper predicate** for key equality.
          We need this for dispatch: when `create_ticket(s, k, ...)` is observed at
          key `k2`, we split on whether `eq_id(k, k2)` holds (hit) or not (miss).

          *Critical:* `eq_id` is a PREDICATE, not a function returning Bool. This means
          using `PredApp("eq_id", ...)` everywhere — never `app("eq_id", ...)`.

        - `has_ticket : Store × TicketId` — **Predicate observer** on Store. True iff
          a ticket with that ID exists in the store. Total over the store.

        - `is_critical : Store × TicketId` — **Predicate observer** on Store. True iff
          the ticket exists AND its severity is `high`.

        | Function | Role | Profile | Notes |
        |----------|------|---------|-------|
        | `empty` | constructor | `→ Store` | Empty store, no tickets |
        | `create_ticket` | constructor | `Store × TicketId × Title × Body → Store` | Adds a new ticket |
        | `resolve_ticket` | constructor | `Store × TicketId → Store` | Transitions status (no-op if nonexistent) |
        | `assign_ticket` | constructor | `Store × TicketId × UserId → Store` | Sets assignee (no-op if nonexistent) |
        | `classify` | uninterpreted | `Title × Body → SeverityLevel` | Filled at implementation time |
        | `get_status` | observer | `Store × TicketId →? Status` | **Partial** — undefined if ticket doesn't exist |
        | `get_severity` | observer | `Store × TicketId →? SeverityLevel` | **Partial** — same |
        | `get_assignee` | observer | `Store × TicketId →? UserId` | **Partial** — doubly: nonexistent ticket OR no assignee |
        | `open` | constant | `→ Status` | Enumeration value |
        | `resolved` | constant | `→ Status` | Enumeration value |
        | `high` | constant | `→ SeverityLevel` | For `is_critical` definition |

        | Predicate | Role | Profile | Notes |
        |-----------|------|---------|-------|
        | `eq_id` | helper | `TicketId × TicketId` | Key equality for dispatch |
        | `has_ticket` | observer | `Store × TicketId` | True iff ticket with that ID exists |
        | `is_critical` | observer | `Store × TicketId` | True iff ticket exists and severity is high |

        ### Step 3: Build the Axiom Obligation Table

        Store constructors: `empty`, `create_ticket`, `resolve_ticket`, `assign_ticket`

        This is where key-dispatch makes things interesting. Every observer takes a
        `TicketId` key, and `create_ticket`, `resolve_ticket`, `assign_ticket` also
        take a `TicketId`. So for each (observer, constructor) pair we get a **hit/miss
        split**: does the constructor's key match the observer's key?

        **`eq_id` basis axioms (3 axioms):**
        Before the obligation table, we need reflexivity, symmetry, and transitivity
        for the key equality predicate. These are structural — they don't come from
        observer×constructor pairs. Transitivity also demonstrates `Conjunction` inside
        `Implication`, an important pattern.

        **`has_ticket` (predicate, total over store — 5 axioms):**
        - × `empty`: false — no tickets in an empty store.
        - × `create_ticket` hit: true — we just added a ticket at this key.
        - × `create_ticket` miss: delegates to `has_ticket(s, k2)` — creating a
          ticket at key `k` doesn't affect whether a ticket exists at a different key `k2`.
        - × `resolve_ticket`: **Both hit and miss produce identical preservation** —
          `has_ticket(resolve_ticket(s, k), k2) ⟺ has_ticket(s, k2)` holds
          unconditionally. Collapse into one universal axiom (same simplification as
          `get_severity × resolve_ticket`).
        - × `assign_ticket`: Same — both hit and miss preserve. One universal axiom.

        **`get_status` (partial — undefined when ticket doesn't exist — 6 axioms):**
        - × `empty`: **omitted** — base constructor, no prior state.
        - × `create_ticket` hit: returns `open` — new tickets start open.
        - × `create_ticket` miss: delegates to `get_status(s, k2)`.
        - × `resolve_ticket` hit + has_ticket: returns `resolved`.
        - × `resolve_ticket` hit + ¬has_ticket: delegates (no-op on nonexistent ticket).
        - × `resolve_ticket` miss: delegates.
        - × `assign_ticket`: universal preservation (collapsible).

        **`get_severity` (partial — undefined when ticket doesn't exist — 4 axioms):**
        - × `empty`: **omitted** — base constructor, no prior state.
        - × `create_ticket` hit: `classify(t, b)` — severity is set at creation.
        - × `create_ticket` miss: delegates.
        - × `resolve_ticket`: **No key dispatch needed!** Resolve doesn't change severity
          for ANY ticket, regardless of which key matches. We can write a single
          universal axiom: `get_severity(resolve_ticket(s, k), k2) = get_severity(s, k2)`.
        - × `assign_ticket`: Same — assign doesn't change severity. One universal axiom.

        *This is an important simplification:* when a constructor doesn't affect an
        observer at all, regardless of key, you can collapse the hit/miss pair into
        a single axiom covering all keys.

        **`get_assignee` (doubly partial — 6 axioms):**
        - × `empty`: **omitted** — base constructor, no prior state.
        - × `create_ticket` hit: **explicit undefinedness** — new tickets have no
          assignee. Use `Negation(Definedness(...))` because under loose semantics,
          omission would leave the value unconstrained, not undefined.
        - × `create_ticket` miss: delegates.
        - × `assign_ticket` hit + has_ticket: returns the new `UserId`.
        - × `assign_ticket` hit + ¬has_ticket: delegates (no-op on nonexistent ticket).
        - × `assign_ticket` miss: delegates.
        - × `resolve_ticket`: universal preservation — resolve doesn't change assignee.

        **`is_critical` (predicate — 5 axioms):**
        - × `empty`: false — no tickets, so nothing is critical.
        - × `create_ticket` hit: `⟺ classify(t, b) = high` — critical iff severity is high.
        - × `create_ticket` miss: delegates.
        - × `resolve_ticket`: universal preservation (criticality depends on severity,
          which resolve doesn't change).
        - × `assign_ticket`: universal preservation.

        **Completeness count:**
        - `eq_id` basis: 3 axioms (refl, sym, trans)
        - `has_ticket`: 5 axioms (empty + 2×create + 1×resolve_universal + 1×assign_universal)
        - `get_status`: 6 axioms (2×create + 2×resolve_hit + 1×resolve_miss + 1×assign_universal)
        - `get_severity`: 4 axioms (2×create + 1×resolve_universal + 1×assign_universal)
        - `get_assignee`: 6 axioms (1×create_hit_undef + 1×create_miss + 2×assign_hit + 1×assign_miss + 1×resolve_universal)
        - `is_critical`: 5 axioms (empty + 2×create + 1×resolve + 1×assign)
        - **Total: 29 axioms**

        | Observer / Predicate | Constructor | Case | Axiom Label | Behavior |
        |---------------------|------------|------|-------------|----------|
        | `eq_id` (basis) | — | — | `eq_id_refl` | reflexivity |
        | `eq_id` (basis) | — | — | `eq_id_sym` | symmetry |
        | `eq_id` (basis) | — | — | `eq_id_trans` | transitivity (Conjunction in antecedent) |
        | `has_ticket` | `empty` | — | `has_ticket_empty` | false |
        | `has_ticket` | `create_ticket` | hit | `has_ticket_create_hit` | true |
        | `has_ticket` | `create_ticket` | miss | `has_ticket_create_miss` | delegates |
        | `has_ticket` | `resolve_ticket` | any | `has_ticket_resolve` | universal preservation |
        | `has_ticket` | `assign_ticket` | any | `has_ticket_assign` | universal preservation |
        | `get_status` (partial) | `empty` | — | *(omitted)* | base constructor |
        | `get_status` (partial) | `create_ticket` | hit | `get_status_create_hit` | `open` |
        | `get_status` (partial) | `create_ticket` | miss | `get_status_create_miss` | delegates |
        | `get_status` (partial) | `resolve_ticket` | hit | `get_status_resolve_hit` | `resolved` (guarded by `has_ticket`) |
        | `get_status` (partial) | `resolve_ticket` | hit | `get_status_resolve_hit_noticket` | delegates (¬has_ticket) |
        | `get_status` (partial) | `resolve_ticket` | miss | `get_status_resolve_miss` | delegates |
        | `get_status` (partial) | `assign_ticket` | any | `get_status_assign` | universal preservation |
        | `get_severity` (partial) | `empty` | — | *(omitted)* | base constructor |
        | `get_severity` (partial) | `create_ticket` | hit | `get_severity_create_hit` | `classify(t, b)` |
        | `get_severity` (partial) | `create_ticket` | miss | `get_severity_create_miss` | delegates |
        | `get_severity` (partial) | `resolve_ticket` | any | `get_severity_resolve` | universal preservation |
        | `get_severity` (partial) | `assign_ticket` | any | `get_severity_assign` | universal preservation |
        | `get_assignee` (partial) | `empty` | — | *(omitted)* | base constructor |
        | `get_assignee` (partial) | `create_ticket` | hit | `get_assignee_create_hit` | **explicit undefinedness** `¬def(...)` |
        | `get_assignee` (partial) | `create_ticket` | miss | `get_assignee_create_miss` | delegates |
        | `get_assignee` (partial) | `assign_ticket` | hit | `get_assignee_assign_hit` | returns `u` (guarded by `has_ticket`) |
        | `get_assignee` (partial) | `assign_ticket` | hit | `get_assignee_assign_hit_noticket` | delegates (¬has_ticket) |
        | `get_assignee` (partial) | `assign_ticket` | miss | `get_assignee_assign_miss` | delegates |
        | `get_assignee` (partial) | `resolve_ticket` | any | `get_assignee_resolve` | universal preservation |
        | `is_critical` (pred) | `empty` | — | `is_critical_empty` | false |
        | `is_critical` (pred) | `create_ticket` | hit | `is_critical_create_hit` | `⟺ classify = high` |
        | `is_critical` (pred) | `create_ticket` | miss | `is_critical_create_miss` | delegates |
        | `is_critical` (pred) | `resolve_ticket` | any | `is_critical_resolve` | universal preservation |
        | `is_critical` (pred) | `assign_ticket` | any | `is_critical_assign` | universal preservation |

        ### Step 4: Write the Signature

        Now translate the tables above into DSL code:

        ```python
        from alspec import (
            Axiom, Conjunction, Definedness, Implication, Negation, PredApp,
            Signature, Spec,
            atomic, fn, pred, var, app, const, eq, forall, iff,
        )

        # Variables — three TicketId variables (k3 needed for eq_id transitivity)
        s = var("s", "Store")
        k = var("k", "TicketId")        # constructor's key
        k2 = var("k2", "TicketId")      # observer's key
        k3 = var("k3", "TicketId")      # auxiliary (transitivity only)
        t = var("t", "Title")
        b = var("b", "Body")
        u = var("u", "UserId")

        sig = Signature(
            sorts={
                "TicketId": atomic("TicketId"),
                "Title": atomic("Title"),
                "Body": atomic("Body"),
                "SeverityLevel": atomic("SeverityLevel"),
                "Status": atomic("Status"),
                "UserId": atomic("UserId"),
                "Store": atomic("Store"),
            },
            functions={
                # Store constructors
                "empty": fn("empty", [], "Store"),
                "create_ticket": fn("create_ticket",
                    [("s", "Store"), ("k", "TicketId"), ("t", "Title"), ("b", "Body")], "Store"),
                "resolve_ticket": fn("resolve_ticket",
                    [("s", "Store"), ("k", "TicketId")], "Store"),
                "assign_ticket": fn("assign_ticket",
                    [("s", "Store"), ("k", "TicketId"), ("u", "UserId")], "Store"),
                # Uninterpreted
                "classify": fn("classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"),
                # Partial observers
                "get_status": fn("get_status",
                    [("s", "Store"), ("k", "TicketId")], "Status", total=False),
                "get_severity": fn("get_severity",
                    [("s", "Store"), ("k", "TicketId")], "SeverityLevel", total=False),
                "get_assignee": fn("get_assignee",
                    [("s", "Store"), ("k", "TicketId")], "UserId", total=False),
                # Enumeration constants
                "open": fn("open", [], "Status"),
                "resolved": fn("resolved", [], "Status"),
                "high": fn("high", [], "SeverityLevel"),
            },
            predicates={
                "eq_id": pred("eq_id", [("k1", "TicketId"), ("k2", "TicketId")]),
                "has_ticket": pred("has_ticket", [("s", "Store"), ("k", "TicketId")]),
                "is_critical": pred("is_critical", [("s", "Store"), ("k", "TicketId")]),
            },
        )
        ```

        ### Step 5: Fill in Axioms from the Obligation Table

        Work through the table row by row. Key concepts:

        - **Hit case**: `eq_id(k, k2)` holds — the constructor's key matches the observer's key.
          Use `Implication(PredApp("eq_id", (k, k2)), ...)` as the guard.
        - **Miss case**: `eq_id(k, k2)` does NOT hold — different keys.
          Use `Implication(Negation(PredApp("eq_id", (k, k2))), ...)` as the guard.
        - **Universal preservation**: The constructor doesn't affect the observer at ANY key.
          No guard needed — write a single equation for all `k2`.
        - **Explicit undefinedness**: The observer should be undefined for this constructor.
          Use `Negation(Definedness(app("observer", app("constructor", ...), k2)))`.
        - **Both guard polarities**: When an axiom is guarded by a predicate (e.g.,
          `has_ticket`), write axioms for BOTH the positive and negative case.

        ```python
        axioms = (
            # ━━ eq_id basis ━━

            Axiom(
                label="eq_id_refl",
                formula=forall([k],
                    PredApp("eq_id", (k, k)),                       # Formula ✓
                ),
            ),
            Axiom(
                label="eq_id_sym",
                formula=forall([k, k2], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    PredApp("eq_id", (k2, k)),                      # Formula ✓
                )),
            ),

            # Conjunction inside Implication — transitivity: k=k2 ∧ k2=k3 ⇒ k=k3
            Axiom(
                label="eq_id_trans",
                formula=forall([k, k2, k3], Implication(
                    Conjunction((                                    # Formula ✓
                        PredApp("eq_id", (k, k2)),                  # Formula ✓
                        PredApp("eq_id", (k2, k3)),                 # Formula ✓
                    )),
                    PredApp("eq_id", (k, k3)),                      # Formula ✓
                )),
            ),

            # ━━ has_ticket: total predicate ━━

            # Negation(PredApp) as complete formula — no tickets in empty store
            Axiom(
                label="has_ticket_empty",
                formula=forall([k], Negation(
                    PredApp("has_ticket", (const("empty"), k)),      # Formula ✓
                )),
            ),

            # Implication(PredApp, PredApp) — hit: ticket just created
            Axiom(
                label="has_ticket_create_hit",
                formula=forall([s, k, k2, t, b], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                )),
            ),

            # Implication(Negation(PredApp), iff(PredApp, PredApp)) — miss
            Axiom(
                label="has_ticket_create_miss",
                formula=forall([s, k, k2, t, b], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    iff(
                        PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                        PredApp("has_ticket", (s, k2)),             # Formula ✓
                    ),
                )),
            ),

            # Universal preservation — resolve doesn't change ticket existence for ANY key.
            # Both hit and miss produce identical biconditionals, so collapse to one axiom.
            Axiom(
                label="has_ticket_resolve",
                formula=forall([s, k, k2],
                    iff(
                        PredApp("has_ticket", (app("resolve_ticket", s, k), k2)),  # Formula ✓
                        PredApp("has_ticket", (s, k2)),             # Formula ✓
                    ),
                ),
            ),

            # Universal preservation — assign doesn't change ticket existence for ANY key.
            Axiom(
                label="has_ticket_assign",
                formula=forall([s, k, k2, u],
                    iff(
                        PredApp("has_ticket", (app("assign_ticket", s, k, u), k2)),  # Formula ✓
                        PredApp("has_ticket", (s, k2)),             # Formula ✓
                    ),
                ),
            ),

            # ━━ get_status: partial, key-dispatch ━━
            # empty case OMITTED — base constructor, no prior state

            # PredApp inside Implication — hit: new tickets start open
            Axiom(
                label="get_status_create_hit",
                formula=forall([s, k, k2, t, b], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    eq(app("get_status", app("create_ticket", s, k, t, b), k2),
                       const("open")),                               # Term ✓
                )),
            ),

            # Negation(PredApp) inside Implication — miss: delegates
            Axiom(
                label="get_status_create_miss",
                formula=forall([s, k, k2, t, b], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    eq(app("get_status", app("create_ticket", s, k, t, b), k2),
                       app("get_status", s, k2)),                    # Term ✓
                )),
            ),

            # resolve_ticket hit: becomes resolved (guarded by has_ticket)
            Axiom(
                label="get_status_resolve_hit",
                formula=forall([s, k, k2], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    Implication(
                        PredApp("has_ticket", (s, k)),               # Formula ✓ — guard
                        eq(app("get_status", app("resolve_ticket", s, k), k2),
                           const("resolved")),                       # Term ✓
                    ),
                )),
            ),

            # resolve_ticket hit WITHOUT ticket: no-op, delegates
            # Under loose semantics, omitting this would leave the observer unconstrained
            # on non-existent tickets after resolve — any value would be a valid model.
            Axiom(
                label="get_status_resolve_hit_noticket",
                formula=forall([s, k, k2], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    Implication(
                        Negation(PredApp("has_ticket", (s, k))),     # Formula ✓ — guard
                        eq(app("get_status", app("resolve_ticket", s, k), k2),
                           app("get_status", s, k2)),                # Term ✓
                    ),
                )),
            ),

            # resolve_ticket miss: delegates
            Axiom(
                label="get_status_resolve_miss",
                formula=forall([s, k, k2], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    eq(app("get_status", app("resolve_ticket", s, k), k2),
                       app("get_status", s, k2)),                    # Term ✓
                )),
            ),

            # Universal preservation — assign doesn't change status for ANY key.
            Axiom(
                label="get_status_assign",
                formula=forall([s, k, k2, u], eq(
                    app("get_status", app("assign_ticket", s, k, u), k2),
                    app("get_status", s, k2),                        # Term ✓
                )),
            ),

            # ━━ get_severity: partial, key-dispatch on create only ━━
            # empty case OMITTED — base constructor, no prior state

            # create_ticket hit: severity = classify(t, b)
            Axiom(
                label="get_severity_create_hit",
                formula=forall([s, k, k2, t, b], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    eq(app("get_severity", app("create_ticket", s, k, t, b), k2),
                       app("classify", t, b)),                       # Term ✓
                )),
            ),

            # create_ticket miss: delegates
            Axiom(
                label="get_severity_create_miss",
                formula=forall([s, k, k2, t, b], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    eq(app("get_severity", app("create_ticket", s, k, t, b), k2),
                       app("get_severity", s, k2)),                  # Term ✓
                )),
            ),

            # Universal preservation — resolve doesn't change severity for ANY ticket.
            # No key dispatch needed: one axiom covers all k2.
            Axiom(
                label="get_severity_resolve",
                formula=forall([s, k, k2], eq(
                    app("get_severity", app("resolve_ticket", s, k), k2),
                    app("get_severity", s, k2),                      # Term ✓
                )),
            ),

            # Universal preservation — assign doesn't change severity either.
            Axiom(
                label="get_severity_assign",
                formula=forall([s, k, k2, u], eq(
                    app("get_severity", app("assign_ticket", s, k, u), k2),
                    app("get_severity", s, k2),                      # Term ✓
                )),
            ),

            # ━━ get_assignee: doubly partial ━━
            # empty case OMITTED — base constructor, no prior state

            # create_ticket hit: EXPLICIT UNDEFINEDNESS — new tickets have no assignee.
            # Under loose semantics, omitting this axiom would NOT make get_assignee
            # undefined — it would leave it unconstrained (any user is a valid model).
            Axiom(
                label="get_assignee_create_hit",
                formula=forall([s, k, k2, t, b], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    Negation(Definedness(
                        app("get_assignee", app("create_ticket", s, k, t, b), k2)
                    )),
                )),
            ),

            # create_ticket miss: delegates
            Axiom(
                label="get_assignee_create_miss",
                formula=forall([s, k, k2, t, b], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    eq(app("get_assignee", app("create_ticket", s, k, t, b), k2),
                       app("get_assignee", s, k2)),                  # Term ✓
                )),
            ),

            # assign_ticket hit: returns the new UserId (guarded — assigning to a
            # nonexistent ticket is a no-op, so get_assignee is still undefined there)
            Axiom(
                label="get_assignee_assign_hit",
                formula=forall([s, k, k2, u], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    Implication(
                        PredApp("has_ticket", (s, k)),              # Formula ✓ — guard
                        eq(app("get_assignee", app("assign_ticket", s, k, u), k2),
                           u),                                       # Term ✓
                    ),
                )),
            ),

            # assign_ticket hit WITHOUT ticket: no-op, delegates
            Axiom(
                label="get_assignee_assign_hit_noticket",
                formula=forall([s, k, k2, u], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    Implication(
                        Negation(PredApp("has_ticket", (s, k))),     # Formula ✓ — guard
                        eq(app("get_assignee", app("assign_ticket", s, k, u), k2),
                           app("get_assignee", s, k2)),              # Term ✓
                    ),
                )),
            ),

            # assign_ticket miss: delegates
            Axiom(
                label="get_assignee_assign_miss",
                formula=forall([s, k, k2, u], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    eq(app("get_assignee", app("assign_ticket", s, k, u), k2),
                       app("get_assignee", s, k2)),                  # Term ✓
                )),
            ),

            # Universal preservation — resolve doesn't change assignee.
            Axiom(
                label="get_assignee_resolve",
                formula=forall([s, k, k2], eq(
                    app("get_assignee", app("resolve_ticket", s, k), k2),
                    app("get_assignee", s, k2),                      # Term ✓
                )),
            ),

            # ━━ is_critical: predicate ━━

            # empty: no tickets → not critical
            Axiom(
                label="is_critical_empty",
                formula=forall([k], Negation(
                    PredApp("is_critical", (const("empty"), k)),     # Formula ✓
                )),
            ),

            # create_ticket hit: critical iff severity is high
            # PredApp inside iff with eq (Formula (Equation))
            Axiom(
                label="is_critical_create_hit",
                formula=forall([s, k, k2, t, b], Implication(
                    PredApp("eq_id", (k, k2)),                      # Formula ✓
                    iff(
                        PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                        eq(app("classify", t, b), const("high")),   # Formula (Equation) ✓
                    ),
                )),
            ),

            # create_ticket miss: delegates
            Axiom(
                label="is_critical_create_miss",
                formula=forall([s, k, k2, t, b], Implication(
                    Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                    iff(
                        PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                        PredApp("is_critical", (s, k2)),            # Formula ✓
                    ),
                )),
            ),

            # Universal preservation — resolve doesn't change criticality.
            Axiom(
                label="is_critical_resolve",
                formula=forall([s, k, k2],
                    iff(
                        PredApp("is_critical", (app("resolve_ticket", s, k), k2)),  # Formula ✓
                        PredApp("is_critical", (s, k2)),            # Formula ✓
                    ),
                ),
            ),

            # Universal preservation — assign doesn't change criticality.
            Axiom(
                label="is_critical_assign",
                formula=forall([s, k, k2, u],
                    iff(
                        PredApp("is_critical", (app("assign_ticket", s, k, u), k2)),  # Formula ✓
                        PredApp("is_critical", (s, k2)),            # Formula ✓
                    ),
                ),
            ),
        )

        spec = Spec(name="BugTracker", signature=sig, axioms=axioms)
        ```

        ### Summary

        | Feature | Where it appears |
        |---------|-----------------| 
        | Atomic sorts | `TicketId`, `Title`, `Body`, `SeverityLevel`, `Status`, `UserId`, `Store` |
        | Enumeration (constants) | `open`/`resolved` for Status, `high` for SeverityLevel |
        | Key equality predicate | `eq_id` — used in every hit/miss dispatch |
        | Store pattern (FiniteMap) | `Store` indexed by `TicketId`, no explicit `Ticket` sort |
        | **Hit/miss key dispatch** | `Implication(PredApp("eq_id", ...), ...)` vs `Implication(Negation(PredApp("eq_id", ...)), ...)` |
        | **PredApp inside Implication** | Every hit/miss guard uses `PredApp("eq_id", ...)` as the antecedent |
        | **Negation(PredApp) as formula** | `has_ticket_empty`, `is_critical_empty` |
        | **iff(PredApp, PredApp)** | `has_ticket_create_miss`, `has_ticket_resolve`, `has_ticket_assign` |
        | **iff(PredApp, Equation)** | `is_critical_create_hit` — critical iff severity = high |
        | **Universal preservation** | `get_severity_resolve`, `has_ticket_resolve`, etc. — no key dispatch needed |
        | **Collapsed hit/miss** | `has_ticket_resolve`, `has_ticket_assign` — identical in both branches → one axiom |
        | **Conjunction in antecedent** | `eq_id_trans` — `Conjunction((PredApp(...), PredApp(...)))` as guard |
        | Partial observer | `get_status`, `get_severity`, `get_assignee` — undefined when ticket doesn't exist |
        | Doubly partial observer | `get_assignee` — undefined if no ticket OR no assignee |
        | **Explicit undefinedness** | `get_assignee_create_hit` — `Negation(Definedness(...))` |
        | **Both guard polarities** | `get_status_resolve_hit` (has_ticket) + `get_status_resolve_hit_noticket` (¬has_ticket) |
        | **Definedness** node | `get_assignee_create_hit` uses `Definedness(Term)` wrapped in `Negation` |
        | Uninterpreted function | `classify` — appears in axioms but not defined by them |
        | Nested Implication | `get_status_resolve_hit`, `get_assignee_assign_hit` — guards inside key dispatch |
        """
    )
