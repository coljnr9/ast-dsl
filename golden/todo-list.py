"""
# Specification Analysis: To-do List

## 1. Sort Classification
We model the system using the FiniteMap pattern, where the `TodoList` acts as the aggregate store indexed by item IDs.
- `ItemId`: **atomic** (opaque key for lookup).
- `Title`: **atomic** (opaque text block).
- `Status`: **atomic** (enumeration representing "done status", with nullary constructors `pending` and `done`). Using a custom enum instead of a hypothetical `Bool` sort keeps the spec self-contained.
- `TodoList`: **atomic** (the central collection).

## 2. Function & Predicate Roles
**Constructors (TodoList):**
- `empty : → TodoList`
- `add_item : TodoList × ItemId × Title → TodoList`
- `complete_item : TodoList × ItemId → TodoList`
- `remove_item : TodoList × ItemId → TodoList`

**Observers:**
- `has_item : TodoList × ItemId` (Predicate, **total** over the list)
- `get_title : TodoList × ItemId →? Title` (Function, **partial** — undefined if item missing)
- `get_status : TodoList × ItemId →? Status` (Function, **partial** — undefined if item missing)

**Constants (Status):**
- `pending : → Status`
- `done : → Status`

**Helper:**
- `eq_id : ItemId × ItemId` (Predicate)

## 3. Complete Axiom Obligation Table

We owe axioms for every (Observer × Constructor) pair. For constructors that take an `ItemId` (`add_item`, `complete_item`, `remove_item`), we dispatch based on key equality.

| Observer | Constructor | Case | Label | Behavior / Expression |
|----------|-------------|------|-------|-----------------------|
| `eq_id` | — | — | `eq_id_refl`, `sym`, `trans` | 3 structural axioms |
| `has_item` | `empty` | — | `has_item_empty` | `False` |
| `has_item` | `add_item` | hit | `has_item_add_hit` | `True` |
| `has_item` | `add_item` | miss | `has_item_add_miss` | delegates |
| `has_item` | `complete_item` | any | `has_item_complete` | universal preservation |
| `has_item` | `remove_item` | hit | `has_item_remove_hit` | `False` |
| `has_item` | `remove_item` | miss | `has_item_remove_miss`| delegates |
| `get_title` | `empty` | — | *(omitted)* | undefined |
| `get_title` | `add_item` | hit | `get_title_add_hit` | returns `t` |
| `get_title` | `add_item` | miss | `get_title_add_miss` | delegates |
| `get_title` | `complete_item` | any | `get_title_complete` | universal preservation |
| `get_title` | `remove_item` | hit | *(omitted)* | undefined |
| `get_title` | `remove_item` | miss | `get_title_remove_miss`| delegates |
| `get_status`| `empty` | — | *(omitted)* | undefined |
| `get_status`| `add_item` | hit | `get_status_add_hit` | returns `pending` |
| `get_status`| `add_item` | miss | `get_status_add_miss` | delegates |
| `get_status`| `complete_item`| hit | `get_status_complete_hit`| returns `done` (guarded by `has_item`) |
| `get_status`| `complete_item`| miss | `get_status_complete_miss`| delegates |
| `get_status`| `remove_item` | hit | *(omitted)* | undefined |
| `get_status`| `remove_item` | miss | `get_status_remove_miss`| delegates |

**Completeness Count:** Expected = 3 (`eq_id`) + 6 (`has_item`) + 4 (`get_title`) + 5 (`get_status`) = **18 axioms**.

## 4. Tricky Cases & Design Decisions
1. **Universal Preservation Optimization:** For instances where a constructor fundamentally doesn't interact with an observer regardless of key, we collapse hit/miss cases. `complete_item` doesn't change `has_item` or `get_title`, netting single universal axioms for both.
2. **Guarded Updates:** `get_status_complete_hit` must only return `done` if the item actually existed prior, so `Implication(PredApp("has_item", (l, k)), ...)` wraps the assignment. Otherwise, completing a nonexistent task would magically vivify its status.
3. **Undefined Removal States:** When processing a `remove_item` hit against partial observers (`get_title`, `get_status`), the results are intentionally left omitted. In standard CASL formalism, the lack of an equation correctly yields undefinedness for the removed item.
"""

from alspec import (
    Axiom, Conjunction, Implication, Negation, PredApp,
    Signature, Spec,
    atomic, fn, pred, var, app, const, eq, forall, iff,
)

def todo_list_spec() -> Spec:
    # Variables
    l = var("l", "TodoList")
    k = var("k", "ItemId")
    k2 = var("k2", "ItemId")
    k3 = var("k3", "ItemId")
    t = var("t", "Title")

    sig = Signature(
        sorts={
            "ItemId": atomic("ItemId"),
            "Title": atomic("Title"),
            "Status": atomic("Status"),
            "TodoList": atomic("TodoList"),
        },
        functions={
            # General Constructors
            "empty": fn("empty", [], "TodoList"),
            "add_item": fn("add_item", [("l", "TodoList"), ("k", "ItemId"), ("t", "Title")], "TodoList"),
            "complete_item": fn("complete_item", [("l", "TodoList"), ("k", "ItemId")], "TodoList"),
            "remove_item": fn("remove_item", [("l", "TodoList"), ("k", "ItemId")], "TodoList"),
            
            # Partial Observers
            "get_title": fn("get_title", [("l", "TodoList"), ("k", "ItemId")], "Title", total=False),
            "get_status": fn("get_status", [("l", "TodoList"), ("k", "ItemId")], "Status", total=False),
            
            # Enum Constants
            "pending": fn("pending", [], "Status"),
            "done": fn("done", [], "Status"),
        },
        predicates={
            "eq_id": pred("eq_id", [("k1", "ItemId"), ("k2", "ItemId")]),
            "has_item": pred("has_item", [("l", "TodoList"), ("k", "ItemId")]),
        },
    )

    axioms = (
        # ━━ eq_id basis (3) ━━
        Axiom(
            label="eq_id_refl",
            formula=forall([k], PredApp("eq_id", (k, k)))
        ),
        Axiom(
            label="eq_id_sym",
            formula=forall([k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                PredApp("eq_id", (k2, k)),
            ))
        ),
        Axiom(
            label="eq_id_trans",
            formula=forall([k, k2, k3], Implication(
                Conjunction((
                    PredApp("eq_id", (k, k2)),
                    PredApp("eq_id", (k2, k3)),
                )),
                PredApp("eq_id", (k, k3)),
            ))
        ),

        # ━━ has_item (total predicate) (6) ━━
        Axiom(
            label="has_item_empty",
            formula=forall([k], Negation(
                PredApp("has_item", (const("empty"), k))
            ))
        ),
        Axiom(
            label="has_item_add_hit",
            formula=forall([l, k, k2, t], Implication(
                PredApp("eq_id", (k, k2)),
                PredApp("has_item", (app("add_item", l, k, t), k2)),
            ))
        ),
        Axiom(
            label="has_item_add_miss",
            formula=forall([l, k, k2, t], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                iff(
                    PredApp("has_item", (app("add_item", l, k, t), k2)),
                    PredApp("has_item", (l, k2)),
                ),
            ))
        ),
        # Complete preserves item existence unconditionally
        Axiom(
            label="has_item_complete",
            formula=forall([l, k, k2], iff(
                PredApp("has_item", (app("complete_item", l, k), k2)),
                PredApp("has_item", (l, k2)),
            ))
        ),
        Axiom(
            label="has_item_remove_hit",
            formula=forall([l, k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                Negation(PredApp("has_item", (app("remove_item", l, k), k2))),
            ))
        ),
        Axiom(
            label="has_item_remove_miss",
            formula=forall([l, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                iff(
                    PredApp("has_item", (app("remove_item", l, k), k2)),
                    PredApp("has_item", (l, k2)),
                ),
            ))
        ),

        # ━━ get_title (partial observer) (4) ━━
        Axiom(
            label="get_title_add_hit",
            formula=forall([l, k, k2, t], Implication(
                PredApp("eq_id", (k, k2)),
                eq(app("get_title", app("add_item", l, k, t), k2), t),
            ))
        ),
        Axiom(
            label="get_title_add_miss",
            formula=forall([l, k, k2, t], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(
                    app("get_title", app("add_item", l, k, t), k2),
                    app("get_title", l, k2),
                ),
            ))
        ),
        # Completing an item preserves titles unconditionally
        Axiom(
            label="get_title_complete",
            formula=forall([l, k, k2], eq(
                app("get_title", app("complete_item", l, k), k2),
                app("get_title", l, k2),
            ))
        ),
        # remove_item_hit is correctly omitted (undefined result)
        Axiom(
            label="get_title_remove_miss",
            formula=forall([l, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(
                    app("get_title", app("remove_item", l, k), k2),
                    app("get_title", l, k2),
                ),
            ))
        ),

        # ━━ get_status (partial observer) (5) ━━
        Axiom(
            label="get_status_add_hit",
            formula=forall([l, k, k2, t], Implication(
                PredApp("eq_id", (k, k2)),
                eq(app("get_status", app("add_item", l, k, t), k2), const("pending")),
            ))
        ),
        Axiom(
            label="get_status_add_miss",
            formula=forall([l, k, k2, t], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(
                    app("get_status", app("add_item", l, k, t), k2),
                    app("get_status", l, k2),
                ),
            ))
        ),
        # Guarded completion: Ensure status only becomes "done" if the task already exists
        Axiom(
            label="get_status_complete_hit",
            formula=forall([l, k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                Implication(
                    PredApp("has_item", (l, k)),
                    eq(app("get_status", app("complete_item", l, k), k2), const("done")),
                )
            ))
        ),
        Axiom(
            label="get_status_complete_miss",
            formula=forall([l, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(
                    app("get_status", app("complete_item", l, k), k2),
                    app("get_status", l, k2),
                ),
            ))
        ),
        # remove_item_hit is correctly omitted (undefined result)
        Axiom(
            label="get_status_remove_miss",
            formula=forall([l, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(
                    app("get_status", app("remove_item", l, k), k2),
                    app("get_status", l, k2),
                ),
            ))
        ),
    )

    return Spec(name="TodoList", signature=sig, axioms=axioms)