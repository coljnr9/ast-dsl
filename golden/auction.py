"""
### 1. Sort Classification
- **`Auction`** (Atomic): The main domain state object storing the auction configuration and bids.
- **`Bidder`** (Atomic): Opaque identifier for participating individuals.
- **`Amount`** (Atomic): Opaque representation of money/bid value.

*(Note: We don't need a `Status` sort because the binary open/closed state is captured perfectly and idiomatically using an `is_open` predicate.)*

### 2. Function and Predicate Roles
**Constructors:**
- `new : → Auction` (Total) — Creates a completely blank, open auction.
- `register : Auction × Bidder → Auction` (Total) — Idempotently registers a bidder.
- `submit : Auction × Bidder × Amount →? Auction` (Partial) — Submits a bid. Only defined if auction is open and bidder is registered.
- `close : Auction → Auction` (Total) — Closes the auction. 

**Observers:**
- `is_open : Auction` (Total Predicate) — True until the auction is closed.
- `is_registered : Auction × Bidder` (Total Predicate) — True if the bidder is registered.
- `highest_bid : Auction →? Amount` (Partial Observer) — The highest recorded bid amount. Undefined if no valid bids.
- `winner : Auction →? Bidder` (Partial Observer) — The bidder holding the `highest_bid`. Undefined if no valid bids.

**Helpers:**
- `eq_bidder : Bidder × Bidder` (Predicate) — Key equality for bidder dispatch.
- `gt : Amount × Amount` (Predicate) — Strict greater-than ordering for comparing bids.

### 3. Axiom Obligation Table

| Observer | Constructor | Case | Axiom Label | Behavior |
|----------|------------|------|-------------|----------|
| `eq_bidder` | — | — | `eq_bidder_refl`, `sym`, `trans` | Standard equivalence |
| `submit_definedness` | — | — | `submit_definedness` | `submit` defined ⟺ `is_open` ∧ `is_registered` |
| `is_open` | `new` | — | `is_open_new` | True |
| `is_open` | `register` | — | `is_open_register` | Preserved |
| `is_open` | `submit` | — | `is_open_submit` | Preserved (when defined) |
| `is_open` | `close` | — | `is_open_close` | False |
| `is_registered` | `new` | — | `is_registered_new` | False |
| `is_registered` | `register` | hit/miss | `..hit` / `..miss` | True / delegates |
| `is_registered` | `submit` | — | `is_registered_submit` | Preserved (when defined) |
| `is_registered` | `close` | — | `is_registered_close` | Preserved |
| `highest_bid` | `new` | — | *(omitted)* | Undefined |
| `highest_bid` | `register` | — | `highest_bid_register` | Universal preservation |
| `highest_bid` | `submit` | no prior bid | `highest_bid_submit_first` | Becomes `amt` |
| `highest_bid` | `submit` | update (gt) | `highest_bid_submit_update` | Becomes `amt` |
| `highest_bid` | `submit` | keep (≤) | `highest_bid_submit_keep` | Preserved |
| `highest_bid` | `close` | — | `highest_bid_close` | Universal preservation |
| `winner` | `new` | — | *(omitted)* | Undefined |
| `winner` | `register` | — | `winner_register` | Universal preservation |
| `winner` | `submit` | no prior bid | `winner_submit_first` | Becomes `b` |
| `winner` | `submit` | update (gt) | `winner_submit_update` | Becomes `b` |
| `winner` | `submit` | keep (≤) | `winner_submit_keep` | Preserved |
| `winner` | `close` | — | `winner_close` | Universal preservation |

### 4. Tricky Cases & Design Decisions
- **Guarding Partial Constructors:** `submit` is a partial constructor natively enforcing the "deadline" property via `is_open` verification. In standard total logic, an undefined partial operation conceptually produces an entirely malformed undefined term. Thus, ANY equation relying on the output of `submit` MUST be guarded by the constructor `Definedness(submit(...))` to remain rigorous and sound.
- **Handling Ties:** The specification for `submit` explicitly branches on the strict `gt` evaluation. If `gt(new_amt, current_amount)` evaluates to `false` (meaning the new bid is less than **or equal to** the current highest), the `submit_keep` axiom fires, preserving the current state. This naturally gives preference to the earliest highest bid, satisfying standard real-world auction mechanisms without requiring timestamps.
- **Sealed Bid Property:** While `winner` and `highest_bid` update dynamically via `submit`, there are computationally transparent. In the domain spec, hiding observer invocation isn't relevant constraints. We evaluate `submit` dynamically to compute state recursively, so exposing observers directly meets "revealing rules" and strict logic definitions.

### 5. Completeness Count
- Basis & helpers (`eq_bidder`, `submit_definedness`): 4 axioms
- `is_open`: 4 axioms
- `is_registered`: 5 axioms 
- `highest_bid`: 5 axioms
- `winner`: 5 axioms
**Total: 23 axioms.**
"""

from alspec import (
    Axiom, Conjunction, Implication, Negation, PredApp,
    Signature, Spec,
    atomic, fn, pred, var, app, const, eq, forall, iff, Definedness
)

def auction_spec() -> Spec:
    # Variables for generic references inside axioms
    a = var("a", "Auction")
    b = var("b", "Bidder")
    b2 = var("b2", "Bidder")
    b3 = var("b3", "Bidder")
    amt = var("amt", "Amount")

    sig = Signature(
        sorts={
            "Auction": atomic("Auction"),
            "Bidder": atomic("Bidder"),
            "Amount": atomic("Amount"),
        },
        functions={
            # Constructors
            "new": fn("new", [], "Auction"),
            "register": fn("register", [("a", "Auction"), ("b", "Bidder")], "Auction"),
            "submit": fn("submit", [("a", "Auction"), ("b", "Bidder"), ("amt", "Amount")], "Auction", total=False),
            "close": fn("close", [("a", "Auction")], "Auction"),
            
            # Partial State Observers
            "highest_bid": fn("highest_bid", [("a", "Auction")], "Amount", total=False),
            "winner": fn("winner", [("a", "Auction")], "Bidder", total=False),
        },
        predicates={
            # Foundation & Guards
            "eq_bidder": pred("eq_bidder", [("b1", "Bidder"), ("b2", "Bidder")]),
            "gt": pred("gt", [("amt1", "Amount"), ("amt2", "Amount")]),
            
            # Predicate Observers 
            "is_open": pred("is_open", [("a", "Auction")]),
            "is_registered": pred("is_registered", [("a", "Auction"), ("b", "Bidder")]),
        }
    )

    axioms = (
        # --- eq_bidder helper ---
        Axiom("eq_bidder_refl", forall([b], PredApp("eq_bidder", (b, b)))),
        Axiom("eq_bidder_sym", forall([b, b2], Implication(
            PredApp("eq_bidder", (b, b2)), 
            PredApp("eq_bidder", (b2, b))
        ))),
        Axiom("eq_bidder_trans", forall([b, b2, b3], Implication(
            Conjunction((PredApp("eq_bidder", (b, b2)), PredApp("eq_bidder", (b2, b3)))), 
            PredApp("eq_bidder", (b, b3))
        ))),

        # --- submit definedness mapping --- 
        Axiom("submit_definedness", forall([a, b, amt], iff(
            Definedness(app("submit", a, b, amt)), 
            Conjunction((PredApp("is_open", (a,)), PredApp("is_registered", (a, b))))
        ))),

        # --- is_open (Predicate Observer) ---
        Axiom("is_open_new", PredApp("is_open", (const("new"),))),
        Axiom("is_open_register", forall([a, b], iff(
            PredApp("is_open", (app("register", a, b),)), 
            PredApp("is_open", (a,))
        ))),
        Axiom("is_open_submit", forall([a, b, amt], Implication(
            Definedness(app("submit", a, b, amt)), 
            iff(PredApp("is_open", (app("submit", a, b, amt),)), PredApp("is_open", (a,)))
        ))),
        Axiom("is_open_close", forall([a], Negation(
            PredApp("is_open", (app("close", a),))
        ))),

        # --- is_registered (Predicate Observer) ---
        Axiom("is_registered_new", forall([b], Negation(
            PredApp("is_registered", (const("new"), b))
        ))),
        Axiom("is_registered_register_hit", forall([a, b, b2], Implication(
            PredApp("eq_bidder", (b, b2)), 
            PredApp("is_registered", (app("register", a, b), b2))
        ))),
        Axiom("is_registered_register_miss", forall([a, b, b2], Implication(
            Negation(PredApp("eq_bidder", (b, b2))), 
            iff(PredApp("is_registered", (app("register", a, b), b2)), PredApp("is_registered", (a, b2)))
        ))),
        Axiom("is_registered_submit", forall([a, b, b2, amt], Implication(
            Definedness(app("submit", a, b, amt)), 
            iff(PredApp("is_registered", (app("submit", a, b, amt), b2)), PredApp("is_registered", (a, b2)))
        ))),
        Axiom("is_registered_close", forall([a, b], iff(
            PredApp("is_registered", (app("close", a), b)), 
            PredApp("is_registered", (a, b))
        ))),

        # --- highest_bid (Partial Observer) ---
        Axiom("highest_bid_register", forall([a, b], eq(
            app("highest_bid", app("register", a, b)), 
            app("highest_bid", a)
        ))),
        Axiom("highest_bid_submit_first", forall([a, b, amt], Implication(
            Conjunction((Definedness(app("submit", a, b, amt)), Negation(Definedness(app("highest_bid", a))))), 
            eq(app("highest_bid", app("submit", a, b, amt)), amt)
        ))),
        Axiom("highest_bid_submit_update", forall([a, b, amt], Implication(
            Conjunction((Definedness(app("submit", a, b, amt)), Definedness(app("highest_bid", a)), PredApp("gt", (amt, app("highest_bid", a))))), 
            eq(app("highest_bid", app("submit", a, b, amt)), amt)
        ))),
        Axiom("highest_bid_submit_keep", forall([a, b, amt], Implication(
            Conjunction((Definedness(app("submit", a, b, amt)), Definedness(app("highest_bid", a)), Negation(PredApp("gt", (amt, app("highest_bid", a)))))), 
            eq(app("highest_bid", app("submit", a, b, amt)), app("highest_bid", a))
        ))),
        Axiom("highest_bid_close", forall([a], eq(
            app("highest_bid", app("close", a)), 
            app("highest_bid", a)
        ))),

        # --- winner (Partial Observer) ---
        Axiom("winner_register", forall([a, b], eq(
            app("winner", app("register", a, b)), 
            app("winner", a)
        ))),
        Axiom("winner_submit_first", forall([a, b, amt], Implication(
            Conjunction((Definedness(app("submit", a, b, amt)), Negation(Definedness(app("highest_bid", a))))), 
            eq(app("winner", app("submit", a, b, amt)), b)
        ))),
        Axiom("winner_submit_update", forall([a, b, amt], Implication(
            Conjunction((Definedness(app("submit", a, b, amt)), Definedness(app("highest_bid", a)), PredApp("gt", (amt, app("highest_bid", a))))), 
            eq(app("winner", app("submit", a, b, amt)), b)
        ))),
        Axiom("winner_submit_keep", forall([a, b, amt], Implication(
            Conjunction((Definedness(app("submit", a, b, amt)), Definedness(app("highest_bid", a)), Negation(PredApp("gt", (amt, app("highest_bid", a)))))), 
            eq(app("winner", app("submit", a, b, amt)), app("winner", a))
        ))),
        Axiom("winner_close", forall([a], eq(
            app("winner", app("close", a)), 
            app("winner", a)
        )))
    )

    return Spec(name="AuctionSpec", signature=sig, axioms=axioms)