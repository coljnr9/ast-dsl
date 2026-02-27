"""
### Domain Analysis & Sorts

To specify the e-commerce shopping cart strictly within the CASL algebraic specification formalism, we use opaque/atomic descriptors for base types and treat the `Cart` as the central state object.

*   `Cart` (atomic): The collection state, represented as a sequenced history of constructors acting like a multiset.
*   `ItemId` (atomic): Identifiers for items.
*   `Price` (atomic): Opaque representation of monetary values.
*   `DiscountCode` (atomic): Identifiers for discount codes.

### Function Roles & Validations

**Constructors of `Cart`:**
*   `empty : → Cart` (Initial empty cart)
*   `add_item : Cart × ItemId → Cart` (Adds an item)
*   `apply_discount : Cart × DiscountCode → Cart` (Applies a discount code. Modeled as a constructor to safely encode discount state directly within the cart's history).

**Observers & Modifiers:**
*   `has_item : Cart × ItemId` (Predicate observer for membership/presence).
*   `remove_item : Cart × ItemId →? Cart` (**Partial modifier**, omitted on empty cart. This ensures undefined strictness bubbles up if an item is completely missing).
*   `compute_total : Cart → Price` (Observer reducing the `Cart` into a total `Price`).

**Uninterpreted Helpers (for Price logic):**
*   `zero : → Price`
*   `add_price : Price × Price → Price`
*   `item_price : ItemId → Price`
*   `apply_discount_logic : Price × DiscountCode → Price`

**Helper Predicates:**
*   `eq_id : ItemId × ItemId` (Fundamental key equality).

### Axiom Obligation Table
All observers owe an axiom to each constructor of their primary domain (`Cart`), with key dispatch paths logic as necessary depending on target signatures.

| Observer / Predicate | Constructor | Case | Axiom Label | Behavior |
| --- | --- | --- | --- | --- |
| `eq_id` (basis) | — | — | `eq_id_refl` | reflexivity |
| `eq_id` (basis) | — | — | `eq_id_sym` | symmetry |
| `eq_id` (basis) | — | — | `eq_id_trans` | transitivity |
| `has_item` | `empty` | — | `has_item_empty` | false |
| `has_item` | `add_item` | hit | `has_item_add_hit` | true |
| `has_item` | `add_item` | miss | `has_item_add_miss` | delegates to `has_item(c, j)` |
| `has_item` | `apply_discount` | any | `has_item_discount` | universal preservation |
| `remove_item` (partial) | `empty` | — | *(omitted)* | undefined (implements "fails if item not in cart") |
| `remove_item` (partial) | `add_item` | hit | `remove_item_add_hit` | returns `c` (multiset decrement semantic) |
| `remove_item` (partial) | `add_item` | miss | `remove_item_add_miss` | `add_item(remove_item(c, j), i)` |
| `remove_item` (partial) | `apply_discount` | any | `remove_item_discount` | universal penetration: `apply_discount(remove_item(c, j), d)` |
| `compute_total` | `empty` | — | `compute_total_empty` | `zero` |
| `compute_total` | `add_item` | any | `compute_total_add` | adds `item_price(i)` |
| `compute_total` | `apply_discount` | any | `compute_total_discount` | wrapper logic `apply_discount_logic` |

**Completeness Count:**
Expected: 3 (eq_id basis) + 4 (has_item) + 3 (remove_item) + 3 (compute_total) = 13 axioms.

### Design Decisions & Tricky Cases
1. **Failing Removal Strictness:** By omitting an axiom for `remove_item(empty, j)`, CASL strict application guarantees that if an item is never found, the entire sequential operation is fundamentally undefined. Missing items effectively short-circuit and crash standard processing matching "fails if item not in cart".
2. **Multiset Semantics:** `remove_item` applied when `eq_id(i, j)` hits returns `c` rather than continuing descent recursively. This appropriately implements removal by pulling exactly *one instance* from a cart that allows repetitive adds.
3. **Pervasive Universal Discount Application:** Rather than creating a separate boolean checkout flow, `compute_total` loops iteratively applying discount codes natively around the price total, mirroring modern algebraic workflows ensuring sequential states retain cart properties flawlessly.
"""

from alspec import (
    Axiom, Conjunction, Implication, Negation, PredApp,
    Signature, Spec,
    atomic, fn, pred, var, app, const, eq, forall, iff,
)

def shopping_cart_spec() -> Spec:
    # Variables for axioms
    c = var("c", "Cart")
    i = var("i", "ItemId")
    j = var("j", "ItemId")
    k = var("k", "ItemId")
    d = var("d", "DiscountCode")

    sig = Signature(
        sorts={
            "Cart": atomic("Cart"),
            "ItemId": atomic("ItemId"),
            "Price": atomic("Price"),
            "DiscountCode": atomic("DiscountCode"),
        },
        functions={
            # State Constructors
            "empty": fn("empty", [], "Cart"),
            "add_item": fn("add_item", [("c", "Cart"), ("i", "ItemId")], "Cart"),
            "apply_discount": fn("apply_discount", [("c", "Cart"), ("d", "DiscountCode")], "Cart"),
            
            # Partial Modifier (fails if item not in cart)
            "remove_item": fn("remove_item", [("c", "Cart"), ("i", "ItemId")], "Cart", total=False),
            
            # Observer
            "compute_total": fn("compute_total", [("c", "Cart")], "Price"),
            
            # Price Helper Mechanics
            "zero": fn("zero", [], "Price"),
            "add_price": fn("add_price", [("p1", "Price"), ("p2", "Price")], "Price"),
            "item_price": fn("item_price", [("i", "ItemId")], "Price"),
            "apply_discount_logic": fn("apply_discount_logic", [("p", "Price"), ("d", "DiscountCode")], "Price"),
        },
        predicates={
            "eq_id": pred("eq_id", [("i1", "ItemId"), ("i2", "ItemId")]),
            "has_item": pred("has_item", [("c", "Cart"), ("i", "ItemId")]),
        }
    )

    axioms = (
        # ━━ eq_id basis ━━
        Axiom(
            label="eq_id_refl",
            formula=forall([i], PredApp("eq_id", (i, i)))
        ),
        Axiom(
            label="eq_id_sym",
            formula=forall([i, j], Implication(
                PredApp("eq_id", (i, j)),
                PredApp("eq_id", (j, i))
            ))
        ),
        Axiom(
            label="eq_id_trans",
            formula=forall([i, j, k], Implication(
                Conjunction((
                    PredApp("eq_id", (i, j)),
                    PredApp("eq_id", (j, k))
                )),
                PredApp("eq_id", (i, k))
            ))
        ),

        # ━━ has_item predicate ━━
        Axiom(
            label="has_item_empty",
            formula=forall([j], Negation(
                PredApp("has_item", (const("empty"), j))
            ))
        ),
        Axiom(
            label="has_item_add_hit",
            formula=forall([c, i, j], Implication(
                PredApp("eq_id", (i, j)),
                PredApp("has_item", (app("add_item", c, i), j))
            ))
        ),
        Axiom(
            label="has_item_add_miss",
            formula=forall([c, i, j], Implication(
                Negation(PredApp("eq_id", (i, j))),
                iff(
                    PredApp("has_item", (app("add_item", c, i), j)),
                    PredApp("has_item", (c, j))
                )
            ))
        ),
        Axiom(
            label="has_item_discount",
            formula=forall([c, d, j], iff(
                PredApp("has_item", (app("apply_discount", c, d), j)),
                PredApp("has_item", (c, j))
            ))
        ),

        # ━━ remove_item (partial modifier) ━━
        # remove_item(empty, j) is OMITTED. Fails perfectly due to strict evaluation.
        
        # Multiset matching semantic: removes a single instance corresponding to match
        Axiom(
            label="remove_item_add_hit",
            formula=forall([c, i, j], Implication(
                PredApp("eq_id", (i, j)),
                eq(
                    app("remove_item", app("add_item", c, i), j),
                    c
                )
            ))
        ),
        Axiom(
            label="remove_item_add_miss",
            formula=forall([c, i, j], Implication(
                Negation(PredApp("eq_id", (i, j))),
                eq(
                    app("remove_item", app("add_item", c, i), j),
                    app("add_item", app("remove_item", c, j), i)
                )
            ))
        ),
        # Ensure discount wraps removal preservation mathematically universally
        Axiom(
            label="remove_item_discount",
            formula=forall([c, d, j], eq(
                app("remove_item", app("apply_discount", c, d), j),
                app("apply_discount", app("remove_item", c, j), d)
            ))
        ),

        # ━━ compute_total observer ━━
        # Unconditional evaluations applying directly to historical constructs
        Axiom(
            label="compute_total_empty",
            formula=eq(
                app("compute_total", const("empty")),
                const("zero")
            )
        ),
        Axiom(
            label="compute_total_add",
            formula=forall([c, i], eq(
                app("compute_total", app("add_item", c, i)),
                app("add_price", app("compute_total", c), app("item_price", i))
            ))
        ),
        Axiom(
            label="compute_total_discount",
            formula=forall([c, d], eq(
                app("compute_total", app("apply_discount", c, d)),
                app("apply_discount_logic", app("compute_total", c), d)
            ))
        ),
    )

    return Spec(name="ShoppingCart", signature=sig, axioms=axioms)