"""
### Domain Analysis: Warehouse Inventory Tracker 

**Step 1: Identify Your Sorts**
*   `Inventory`: The primary domain collection, storing item quantities (FiniteMap pattern). **atomic**.
*   `ItemId`: Opaque identifier used as lookup keys. **atomic**.
*   `Nat`: Represents item quantities. **atomic**. (We treat this as a standard Peano basis sort to support arithmetic).

**Step 2: Classify Functions and Predicates**
*   **Constructors** (returning `Inventory`):
    *   `empty : → Inventory` (Total)
    *   `add_stock : Inventory × ItemId × Nat → Inventory` (Total)
    *   `remove_stock : Inventory × ItemId × Nat →? Inventory` (**Partial**: Can fail if stock is insufficient).
*   **Observers** (over `Inventory`):
    *   `get_qty : Inventory × ItemId → Nat` (Total: non-existent items conceptually act as having `zero` quantity).
*   **Basis Functions** (representing `Nat` operations - Uninterpreted in this domain context):
    *   `zero : → Nat`
    *   `add : Nat × Nat → Nat`
    *   `sub : Nat × Nat → Nat`
*   **Predicates**:
    *   `eq_id : ItemId × ItemId` (Helper for finite map dispatch).
    *   `leq : Nat × Nat` (Basis predicate to check sufficient quantity).

**Step 3: Tricky Cases and Design Decisions**
1.  **Partial Constructor Defines Behavior**: The prompt strictly specifies `remove_stock` is *partial if insufficient*. To gracefully model this, I explicitly use the `Definedness` built-in wrapper, creating an axiom asserting that `remove_stock` is defined *if and only if* `leq(q, get_qty(i, k))` holds.
2.  **Guarding Miss Cases on Partial Constructors**: It's tempting to write an unconditional miss axiom (`get_qty(remove_stock(...), k2) = get_qty(i, k2)`) since the query key is different. However, applying strictly total logic over partial terms is dangerous: if `remove` fails, `remove_stock` evaluates to *undefined*. Asserting that querying an undefined store equals a *defined* integer (`Undefined = Defined`) evaluates to an implicit mathematical contradiction in partial frameworks. Ergo, all observer bindings concerning `remove_stock` (both HIT and MISS scenarios) are heavily protected / guarded by the definedness precondition `leq(q, get_qty(i, k))`.
3.  **Missing `has_item` Predicate**: Unlike the bug tracker that distinguishes open tickets from non-existent tickets, an item with zero quantity and an untracked item are semantically isomorphic in standard warehousing. Therefore, `get_qty` returning `zero` covers absence natively without requiring partial observer status.

**Step 4: Axiom Obligation Table**
| Observer / Concept | Constructor | Case | Axiom Label | Definition Detail |
|--------------------|-------------|------|-------------|-------------------|
| `eq_id` (basis)    | —           | —    | `eq_id_refl`| reflexivity |
| `eq_id` (basis)    | —           | —    | `eq_id_sym` | symmetry |
| `eq_id` (basis)    | —           | —    | `eq_id_trans`| transitivity |
| Definedness domain | `remove_stock`| —  | `remove_stock_def`| `Definedness(remove_stock(...)) ⇔ leq(q, get_qty(i, k))` |
| `get_qty`          | `empty`       | —    | `get_qty_empty` | `zero` |
| `get_qty`          | `add_stock`   | hit  | `get_qty_add_hit` | `add(get_qty(i, k2), q)` |
| `get_qty`          | `add_stock`   | miss | `get_qty_add_miss`| delegates back to `get_qty(i, k2)` |
| `get_qty`          | `remove_stock`| hit  | `get_qty_remove_hit`| `sub(get_qty(i, k2), q)` (guarded by `leq`) |
| `get_qty`          | `remove_stock`| miss | `get_qty_remove_miss`| delegates (guarded by `leq`) |

**Step 5: Completeness Count**
*   Basis (`eq_id`): 3 axioms
*   Partial Constructor definedness cap: 1 axiom
*   Total Observer (`get_qty`): 5 axioms (1 empty + 2 add + 2 remove)
*   **Total Expected Axioms:** 9
"""

def inventory_spec():
    from alspec import (
        Axiom, Conjunction, Implication, Negation, PredApp,
        Signature, Spec, atomic, fn, pred, var, app, const, eq, forall, iff, Definedness
    )

    # Variables for equations
    i = var("i", "Inventory")
    k = var("k", "ItemId")    # Constructor key
    k2 = var("k2", "ItemId")  # Observer query key
    k3 = var("k3", "ItemId")  # Transitivity temp key
    q = var("q", "Nat")       # Modification quantity

    sig = Signature(
        sorts={
            "ItemId": atomic("ItemId"),
            "Nat": atomic("Nat"),
            "Inventory": atomic("Inventory"),
        },
        functions={
            # Inventory Constructors
            "empty": fn("empty", [], "Inventory"),
            "add_stock": fn("add_stock", [
                ("i", "Inventory"), ("k", "ItemId"), ("q", "Nat")
            ], "Inventory"),
            "remove_stock": fn("remove_stock", [
                ("i", "Inventory"), ("k", "ItemId"), ("q", "Nat")
            ], "Inventory", total=False),  # Partial: Fails if not enough stock
            
            # Observers
            "get_qty": fn("get_qty", [
                ("i", "Inventory"), ("k", "ItemId")
            ], "Nat"),
            
            # Basis Uninterpreted operations
            "zero": fn("zero", [], "Nat"),
            "add": fn("add", [("n1", "Nat"), ("n2", "Nat")], "Nat"),
            "sub": fn("sub", [("n1", "Nat"), ("n2", "Nat")], "Nat"),
        },
        predicates={
            "eq_id": pred("eq_id", [("k1", "ItemId"), ("k2", "ItemId")]),
            "leq": pred("leq", [("n1", "Nat"), ("n2", "Nat")]),
        }
    )

    axioms = (
        # ━━ eq_id basis ━━
        Axiom(
            label="eq_id_refl",
            formula=forall([k], PredApp("eq_id", (k, k)))
        ),
        Axiom(
            label="eq_id_sym",
            formula=forall([k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                PredApp("eq_id", (k2, k))
            ))
        ),
        Axiom(
            label="eq_id_trans",
            formula=forall([k, k2, k3], Implication(
                Conjunction((
                    PredApp("eq_id", (k, k2)),
                    PredApp("eq_id", (k2, k3))
                )),
                PredApp("eq_id", (k, k3))
            ))
        ),

        # ━━ definedness boundaries ━━
        Axiom(
            label="remove_stock_def",
            formula=forall([i, k, q], iff(
                Definedness(app("remove_stock", i, k, q)),
                PredApp("leq", (q, app("get_qty", i, k)))
            ))
        ),

        # ━━ get_qty (total observer) ━━
        Axiom(
            label="get_qty_empty",
            formula=forall([k], eq(
                app("get_qty", const("empty"), k),
                const("zero")
            ))
        ),

        # Add Hit
        Axiom(
            label="get_qty_add_hit",
            formula=forall([i, k, k2, q], Implication(
                PredApp("eq_id", (k, k2)),
                eq(
                    app("get_qty", app("add_stock", i, k, q), k2),
                    app("add", app("get_qty", i, k2), q)
                )
            ))
        ),

        # Add Miss
        Axiom(
            label="get_qty_add_miss",
            formula=forall([i, k, k2, q], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(
                    app("get_qty", app("add_stock", i, k, q), k2),
                    app("get_qty", i, k2)
                )
            ))
        ),

        # Remove Hit (Guarded by leq condition since remove_stock is partial)
        Axiom(
            label="get_qty_remove_hit",
            formula=forall([i, k, k2, q], Implication(
                PredApp("eq_id", (k, k2)),
                Implication(
                    PredApp("leq", (q, app("get_qty", i, k))),
                    eq(
                        app("get_qty", app("remove_stock", i, k, q), k2),
                        app("sub", app("get_qty", i, k2), q)
                    )
                )
            ))
        ),

        # Remove Miss (Also guarded: an undefined function prevents equating its value to a valid Nat)
        Axiom(
            label="get_qty_remove_miss",
            formula=forall([i, k, k2, q], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                Implication(
                    PredApp("leq", (q, app("get_qty", i, k))),
                    eq(
                        app("get_qty", app("remove_stock", i, k, q), k2),
                        app("get_qty", i, k2)
                    )
                )
            ))
        ),
    )

    return Spec(name="InventoryTracker", signature=sig, axioms=axioms)