import textwrap


def render() -> str:
    return textwrap.dedent(
        """\
        ## 6. Worked Example: Bug Tracker

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

        - `Ticket` — This is the central domain object. Tickets have observable
          properties (id, title, body, severity, status). → **product sort**

          *Note: Even though Ticket is a product sort, we don't use FieldAccess to
          read its fields — we use observer functions (get_severity, get_status, etc.)
          that we define axioms for. The ProductSort declaration documents the
          structure; the axioms define the behavior.*

        | Sort | Kind | Rationale |
        |------|------|----------|
        | `TicketId` | atomic | Opaque identifier — no internal structure |
        | `Title` | atomic | Opaque text blob |
        | `Body` | atomic | Opaque text blob |
        | `SeverityLevel` | atomic | Uninterpreted — populated by `classify` |
        | `Status` | atomic (enumeration) | Finite set: `open`, `resolved`. Modeled as nullary constructors |
        | `UserId` | atomic | Opaque identifier for assignees |
        | `Ticket` | product | Has observable fields: id, title, body, severity, status |

        ### Step 2: Classify Functions as Constructors or Observers

        **Constructors** build values of a sort. **Observers** query or decompose them.
        Every observer owes axioms against every constructor of its primary sort.

        **Reasoning through each function:**

        - `create : TicketId × Title × Body → Ticket` — Builds a new Ticket from
          parts. This is clearly a **constructor**. Total (you can always create a ticket).

        - `resolve : Ticket → Ticket` — Takes a Ticket, returns a Ticket. This is a
          **constructor** because it produces a new Ticket value (with different status).
          Even though the result sort equals the input sort, it's *building* a new
          value, not *extracting* information.

        - `assign : Ticket × UserId → Ticket` — Same pattern as resolve: produces
          a new Ticket with an assignee set. **Constructor**, total.

        - `classify : Title × Body → SeverityLevel` — This is interesting. Nothing in
          our spec defines what classify returns — no axiom has classify on the left
          side of an equation. It appears only *inside* other axioms (e.g.,
          `get_severity(create(id, t, b)) = classify(t, b)`). This makes it
          **uninterpreted** — the spec constrains how it's used but not what it
          computes. At implementation time, this could be an LLM call, a rules engine,
          or a lookup table.

        - `get_severity : Ticket → SeverityLevel` — Takes a Ticket, returns something
          that isn't a Ticket. Classic **observer**. Total (every ticket has a severity).

        - `get_status : Ticket → Status` — Same pattern. **Observer**, total.

        - `get_assignee : Ticket →? UserId` — Observer, but **partial**. Why partial?
          Because a freshly created ticket has no assignee — `get_assignee(create(...))`
          is undefined. This is the key design decision: we don't want a "no user"
          sentinel value; we want genuine undefinedness.

        - `open`, `resolved` — Nullary constructors of Status (enumeration constants).

        - `high` — Nullary constructor of SeverityLevel (needed for is_critical definition).

        - `is_critical` — **Predicate observer** on Ticket. Holds iff the ticket's
          severity is `high`. We'll use Biconditional to express this equivalence.

        | Function | Role | Profile | Notes |
        |----------|------|---------|------|
        | `create` | constructor | `TicketId × Title × Body → Ticket` | total |
        | `resolve` | constructor | `Ticket → Ticket` | total, transitions status |
        | `assign` | constructor | `Ticket × UserId → Ticket` | total, sets assignee |
        | `classify` | uninterpreted | `Title × Body → SeverityLevel` | total, not defined by any axiom |
        | `get_severity` | observer | `Ticket → SeverityLevel` | total |
        | `get_status` | observer | `Ticket → Status` | total |
        | `get_assignee` | observer | `Ticket →? UserId` | **partial** — undefined until assigned |
        | `open` | constant | `→ Status` | enumeration value |
        | `resolved` | constant | `→ Status` | enumeration value |
        | `high` | constant | `→ SeverityLevel` | for defining `is_critical` |

        | Predicate | Role | Profile |
        |-----------|------|--------|
        | `is_critical` | observer | `Ticket` |

        ### Step 3: Build the Axiom Obligation Table

        List every (observer, constructor) pair. For partial observers, identify which
        constructor cases produce undefined results — these rows produce no axiom.

        Ticket constructors: `create`, `resolve`, `assign`

        **Working through each observer systematically:**

        **`get_severity` (total, 3 constructors → 3 axioms):**
        - × `create`: Severity is determined at creation time by `classify(t, b)`.
          This is a *defining* axiom — it connects the observer to the constructor's arguments.
        - × `resolve`: Resolving a ticket doesn't change its severity. **Preservation**.
        - × `assign`: Assigning a ticket doesn't change its severity. **Preservation**.

        **`get_status` (total, 3 constructors → 3 axioms):**
        - × `create`: New tickets start with status `open`.
        - × `resolve`: Status becomes `resolved`. This is the *point* of the resolve constructor.
        - × `assign`: Assigning doesn't change status. **Preservation**.

        **`get_assignee` (PARTIAL, 3 constructors → 2 axioms + 1 omitted):**
        - × `create`: **OMITTED** — `get_assignee` is undefined on new tickets.
          No axiom needed; the `total=False` declaration handles undefinedness.
        - × `resolve`: Tricky case! Resolving a ticket should preserve the assignee
          *if one exists*, and leave it undefined if it didn't have one. This requires
          TWO things: a `Definedness` biconditional (definedness is preserved) and a
          value equation (when defined, the value is preserved). The value equation
          uses strong equality — it holds when both sides are defined and equal, or
          both undefined.
        - × `assign`: Returns the newly assigned `UserId`. This is the defining axiom.

        **`is_critical` (predicate, 3 constructors → 3 axioms):**
        - × `create`: Critical iff `classify(t, b) = high`. Use `Biconditional` to
          express this equivalence — `is_critical(create(...)) ⟺ classify(t,b) = high`.
          Not `Implication`! We need both directions.
        - × `resolve`: Criticality preserved. Use `Biconditional` with the same predicate
          on the inner ticket.
        - × `assign`: Criticality preserved. Same pattern as resolve.

        | Observer / Predicate | Constructor | Defined? | Axiom Label | Expected behavior |
        |---------------------|------------|----------|-------------|------------------|
        | `get_severity` (total) | `create` | ✓ | `get_severity_create` | `classify(t, b)` |
        | `get_severity` (total) | `resolve` | ✓ | `get_severity_resolve` | preserved |
        | `get_severity` (total) | `assign` | ✓ | `get_severity_assign` | preserved |
        | `get_status` (total) | `create` | ✓ | `get_status_create` | `open` |
        | `get_status` (total) | `resolve` | ✓ | `get_status_resolve` | `resolved` |
        | `get_status` (total) | `assign` | ✓ | `get_status_assign` | preserved |
        | `get_assignee` (**partial**) | `create` | **✗** | *(omitted)* | undefined — no assignee yet |
        | `get_assignee` (**partial**) | `resolve` | depends | `get_assignee_resolve` | preserved (definedness + value) |
        | `get_assignee` (**partial**) | `assign` | ✓ | `get_assignee_assign` | returns new `UserId` |
        | `is_critical` (pred) | `create` | ✓ | `is_critical_create` | `⟺ classify = high` |
        | `is_critical` (pred) | `resolve` | ✓ | `is_critical_resolve` | preserved |
        | `is_critical` (pred) | `assign` | ✓ | `is_critical_assign` | preserved |

        **Completeness check:** 3 + 3 + 2 + 3 = 11 value-equation axioms,
        plus 1 definedness biconditional for `get_assignee_resolve` = **12 axioms**.
        Adding the resolve value axiom separately: **total 13 axioms**.

        *Wait — let's recount carefully:*
        - `get_severity`: 3 axioms (create, resolve, assign)
        - `get_status`: 3 axioms (create, resolve, assign)
        - `get_assignee`: 3 axioms (resolve_definedness, resolve_value, assign)
          — create is **omitted**
        - `is_critical`: 3 axioms (create, resolve, assign)
        - **Total: 12 value/predicate axioms + 1 definedness biconditional = 13 axioms**

        ### Step 4: Write the Signature

        Now translate the tables above into DSL code:

        ```python
        from alspec import (
            Axiom, Signature, Spec, S,
            atomic, fn, pred, var, app, const, eq, forall, iff,
            ProductSort, ProductField,
            Biconditional, PredApp, Negation, Definedness,
        )

        # Variables
        id_var = var("id", "TicketId")
        t = var("t", "Title")
        b = var("b", "Body")
        tk = var("tk", "Ticket")
        u = var("u", "UserId")

        sig = Signature(
            sorts={
                "TicketId": atomic("TicketId"),
                "Title": atomic("Title"),
                "Body": atomic("Body"),
                "SeverityLevel": atomic("SeverityLevel"),
                "Status": atomic("Status"),
                "UserId": atomic("UserId"),
                "Ticket": ProductSort(
                    name=S("Ticket"),
                    fields=(
                        ProductField("id", S("TicketId")),
                        ProductField("title", S("Title")),
                        ProductField("body", S("Body")),
                        ProductField("severity", S("SeverityLevel")),
                        ProductField("status", S("Status")),
                    ),
                ),
            },
            functions={
                # Uninterpreted function — filled by LLM at code-gen time
                "classify": fn("classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"),
                # Constructors for Ticket
                "create": fn("create", [("id", "TicketId"), ("t", "Title"), ("b", "Body")], "Ticket"),
                "resolve": fn("resolve", [("tk", "Ticket")], "Ticket"),
                "assign": fn("assign", [("tk", "Ticket"), ("u", "UserId")], "Ticket"),
                # Observers
                "get_severity": fn("get_severity", [("tk", "Ticket")], "SeverityLevel"),
                "get_status": fn("get_status", [("tk", "Ticket")], "Status"),
                "get_assignee": fn("get_assignee", [("tk", "Ticket")], "UserId", total=False),
                # Status constants (enumeration)
                "open": fn("open", [], "Status"),
                "resolved": fn("resolved", [], "Status"),
                # SeverityLevel constants
                "high": fn("high", [], "SeverityLevel"),
            },
            predicates={
                "is_critical": pred("is_critical", [("tk", "Ticket")]),
            },
        )
        ```

        ### Step 5: Fill in Axioms from the Obligation Table

        Work through the table row by row. Each row becomes one `Axiom`.

        ```python
        axioms = (
            # ━━ get_severity: total, 3 constructors → 3 axioms ━━

            # get_severity × create: severity comes from classify
            Axiom(
                label="get_severity_create",
                formula=forall([id_var, t, b], eq(
                    app("get_severity", app("create", id_var, t, b)),
                    app("classify", t, b),
                )),
            ),
            # get_severity × resolve: severity preserved
            Axiom(
                label="get_severity_resolve",
                formula=forall([tk], eq(
                    app("get_severity", app("resolve", tk)),
                    app("get_severity", tk),
                )),
            ),
            # get_severity × assign: severity preserved
            Axiom(
                label="get_severity_assign",
                formula=forall([tk, u], eq(
                    app("get_severity", app("assign", tk, u)),
                    app("get_severity", tk),
                )),
            ),

            # ━━ get_status: total, 3 constructors → 3 axioms ━━

            # get_status × create: new tickets start open
            Axiom(
                label="get_status_create",
                formula=forall([id_var, t, b], eq(
                    app("get_status", app("create", id_var, t, b)),
                    const("open"),
                )),
            ),
            # get_status × resolve: status becomes resolved
            Axiom(
                label="get_status_resolve",
                formula=forall([tk], eq(
                    app("get_status", app("resolve", tk)),
                    const("resolved"),
                )),
            ),
            # get_status × assign: status preserved (assigning doesn't change status)
            Axiom(
                label="get_status_assign",
                formula=forall([tk, u], eq(
                    app("get_status", app("assign", tk, u)),
                    app("get_status", tk),
                )),
            ),

            # ━━ get_assignee: PARTIAL, 3 constructors → 2 axioms (undefined on create) ━━
            #
            # create: OMITTED — get_assignee is partial and undefined on new tickets.
            #         No axiom needed; the total=False declaration handles this.

            # get_assignee × resolve: assignee preserved across resolution
            # This uses Definedness in a biconditional — if the ticket had an assignee
            # before, it still has one after; if it didn't, it still doesn't.
            Axiom(
                label="get_assignee_resolve",
                formula=forall([tk], Biconditional(
                    lhs=Definedness(app("get_assignee", app("resolve", tk))),
                    rhs=Definedness(app("get_assignee", tk)),
                )),
            ),
            # When defined, the value is preserved:
            Axiom(
                label="get_assignee_resolve_value",
                formula=forall([tk], eq(
                    app("get_assignee", app("resolve", tk)),
                    app("get_assignee", tk),
                )),
            ),
            # get_assignee × assign: returns the new UserId
            Axiom(
                label="get_assignee_assign",
                formula=forall([tk, u], eq(
                    app("get_assignee", app("assign", tk, u)),
                    u,
                )),
            ),

            # ━━ is_critical: predicate, 3 constructors → 3 axioms ━━

            # is_critical × create: critical iff classify returns high
            Axiom(
                label="is_critical_create",
                formula=forall([id_var, t, b], Biconditional(
                    lhs=PredApp("is_critical", (app("create", id_var, t, b),)),
                    rhs=eq(app("classify", t, b), const("high")),
                )),
            ),
            # is_critical × resolve: criticality preserved
            Axiom(
                label="is_critical_resolve",
                formula=forall([tk], Biconditional(
                    lhs=PredApp("is_critical", (app("resolve", tk),)),
                    rhs=PredApp("is_critical", (tk,)),
                )),
            ),
            # is_critical × assign: criticality preserved (assignment doesn't affect severity)
            Axiom(
                label="is_critical_assign",
                formula=forall([tk, u], Biconditional(
                    lhs=PredApp("is_critical", (app("assign", tk, u),)),
                    rhs=PredApp("is_critical", (tk,)),
                )),
            ),
        )

        spec = Spec(name="BugTracker", signature=sig, axioms=axioms)
        ```

        ### Summary

        | Feature | Where it appears |
        |---------|------------------|
        | Atomic sorts | `TicketId`, `Title`, `Body`, `SeverityLevel`, `Status`, `UserId` |
        | Product sort | `Ticket` with 5 named fields |
        | Enumeration (constants) | `open`/`resolved` for Status, `high` for SeverityLevel |
        | Total observer | `get_severity`, `get_status` — one axiom per constructor |
        | **Partial observer** | `get_assignee` — undefined on `create`, defined on `assign`/`resolve` |
        | Predicate observer | `is_critical` — uses `Biconditional` for equivalence |
        | Uninterpreted function | `classify` — appears in axioms but is not defined by them |
        | Preservation pattern | Severity, status, criticality, assignee preserved across irrelevant constructors |
        | `Definedness` | Used in `get_assignee_resolve` to express definedness preservation |
        | `Biconditional` | Used for predicate equivalence and definedness preservation |
        | Strong equation on partial terms | `get_assignee_resolve_value` — holds when both sides defined and equal, or both undefined |
        """
    )
