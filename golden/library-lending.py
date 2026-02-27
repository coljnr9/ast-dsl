"""
**Analysis & Methodology Walkthrough**

**1. Sort Identification**
To model the library lending system, we need to carefully define the sorts:
- `BookId` (atomic): The opaque identifier used as the lookup key for books.
- `UserId` (atomic): The opaque identifier for a patron.
- `Status` (atomic enumeration): Constants `available` and `borrowed`. We will use these rather than individual predicates to closely mirror the reference FiniteMap approach.
- `Library` (atomic): The collection of books mapped to statuses and patrons. Models the internal state. No distinct `Book` sort exists—book state is entirely embedded inside `Library`.

**2. Function and Predicate Roles**
- **Constructors** for `Library`:
  - `empty : → Library` (initializes empty library)
  - `register : Library × BookId → Library` (registers a new book, initializing it unconditionally to `available` with no associated borrower)
  - `borrow : Library × BookId × UserId → Library` (conditionally records a borrow action)
  - `return_book : Library × BookId → Library` (conditionally resolves a borrowed book)
- **Observers** for `Library`:
  - `has_book : Library × BookId` (Predicate)
  - `get_status : Library × BookId →? Status` (Partial: undefined for unregistered books)
  - `get_borrower : Library × BookId →? UserId` (Partial: undefined for unregistered OR available books)
- **Constants** for `Status`:
  - `available : → Status`
  - `borrowed : → Status`
- **Helpers**:
  - `eq_id : BookId × BookId` (key dispatching equality predicate over `BookId`)

**3. Design Decisions & Tricky Cases**
- **Conditional Actions via Guards:** The specification requires that borrowing "only succeed if available" and returning "only succeed if borrowed." Rather than enforcing equality constraint on the library state (e.g. `borrow(...) = L` on fail), we manage this observationally using key-dispatch methodology with condition branching (Hit Success vs Hit Failure). E.g., if a book is not `available`, the hit failure axiom preserves the existing state (`get_status(borrow(...), b2) = get_status(L, b2)`).
- **Undefined Evaluations:** By evaluating `eq(get_status(L, b), available)`, we handle non-existent books elegantly. If `b` isn't in `L`, `get_status(L, b)` is undefined, failing the strict equality equation, naturally routing to the unmutating hit-fail preserving path via negation mechanism `Negation(eq(...))`.
- **Doubly Partial `get_borrower`:** `get_borrower` is inherently partial when a book isn't registered, and also must become explicitly undefined when a book is newly registered (no borrower yet) or returned (borrower released). We use `Negation(Definedness(...))` to assert undefinedness in these cases, since under loose semantics mere omission of an axiom leaves the interpretation unconstrained rather than forcing undefinedness.

**4. Axiom Obligation Table**
- **Basis `eq_id`**: refl, sym, trans (3 axioms)
- **`has_book`** (Predicate, 5 axioms): 
    - `empty`: returns false
    - `register_hit`: becomes true
    - `register_miss`: delegates
    - `borrow` / `return_book`: universal preservation (borrow/return do not register nor unregister books, hence state is fully preserved via iff).
- **`get_status`** (Partial, 8 axioms):
    - `empty`: omitted
    - `register_hit`: unconditionally returns `available`
    - `register_miss`: delegates
    - `borrow_hit_succ`: conditional on `eq(status, available)`, returns `borrowed`
    - `borrow_hit_fail`: negated condition, delegates
    - `borrow_miss`: delegates
    - `return_hit_succ`: conditional on `eq(status, borrowed)`, returns `available`
    - `return_hit_fail`: negated condition, delegates
    - `return_miss`: delegates
- **`get_borrower`** (Partial, 8 axioms):
    - `empty`: omitted
    - `register_hit`: explicit undefinedness (new books have no borrower)
    - `register_miss`: delegates
    - `borrow_hit_succ`: conditional on `eq(status, available)`, returns `u`
    - `borrow_hit_fail`: negated condition, delegates
    - `borrow_miss`: delegates
    - `return_hit_succ`: explicit undefinedness (returned books lose borrower)
    - `return_hit_fail`: negated condition, delegates
    - `return_miss`: delegates

**5. Completeness Check:** 
3 + 5 + 8 + 8 = 24 axioms mapped exactly per observer and constructor key/status dispatch cases over valid partial evaluations.
"""

from alspec import (
    Axiom, Conjunction, Definedness, Implication, Negation, PredApp,
    Signature, Spec, atomic, fn, pred, var, app, const, eq, forall, iff
)

def library_lending_spec() -> Spec:
    L = var("L", "Library")
    b = var("b", "BookId")
    b2 = var("b2", "BookId")
    b3 = var("b3", "BookId")
    u = var("u", "UserId")

    sig = Signature(
        sorts={
            "BookId": atomic("BookId"),
            "UserId": atomic("UserId"),
            "Status": atomic("Status"),
            "Library": atomic("Library"),
        },
        functions={
            # Collection constructors
            "empty": fn("empty", [], "Library"),
            "register": fn("register", [("L", "Library"), ("b", "BookId")], "Library"),
            "borrow": fn("borrow", [("L", "Library"), ("b", "BookId"), ("u", "UserId")], "Library"),
            "return_book": fn("return_book", [("L", "Library"), ("b", "BookId")], "Library"),
            
            # Constants
            "available": fn("available", [], "Status"),
            "borrowed": fn("borrowed", [], "Status"),
            
            # Partial Observers
            "get_status": fn("get_status", [("L", "Library"), ("b", "BookId")], "Status", total=False),
            "get_borrower": fn("get_borrower", [("L", "Library"), ("b", "BookId")], "UserId", total=False),
        },
        predicates={
            "eq_id": pred("eq_id", [("b1", "BookId"), ("b2", "BookId")]),
            "has_book": pred("has_book", [("L", "Library"), ("b", "BookId")]),
        }
    )

    axioms = (
        # ━━ eq_id basis ━━
        Axiom("eq_id_refl", forall([b], PredApp("eq_id", (b, b)))),
        Axiom("eq_id_sym", forall([b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            PredApp("eq_id", (b2, b))
        ))),
        Axiom("eq_id_trans", forall([b, b2, b3], Implication(
            Conjunction((PredApp("eq_id", (b, b2)), PredApp("eq_id", (b2, b3)))),
            PredApp("eq_id", (b, b3))
        ))),

        # ━━ has_book (5 axioms) ━━
        Axiom("has_book_empty", forall([b], Negation(
            PredApp("has_book", (const("empty"), b))
        ))),
        Axiom("has_book_register_hit", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            PredApp("has_book", (app("register", L, b), b2))
        ))),
        Axiom("has_book_register_miss", forall([L, b, b2], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            iff(
                PredApp("has_book", (app("register", L, b), b2)),
                PredApp("has_book", (L, b2))
            )
        ))),
        Axiom("has_book_borrow_univ", forall([L, b, b2, u], iff(
            PredApp("has_book", (app("borrow", L, b, u), b2)),
            PredApp("has_book", (L, b2))
        ))),
        Axiom("has_book_return_univ", forall([L, b, b2], iff(
            PredApp("has_book", (app("return_book", L, b), b2)),
            PredApp("has_book", (L, b2))
        ))),

        # ━━ get_status (8 axioms) ━━
        Axiom("get_status_register_hit", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            eq(app("get_status", app("register", L, b), b2), const("available"))
        ))),
        Axiom("get_status_register_miss", forall([L, b, b2], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            eq(app("get_status", app("register", L, b), b2), app("get_status", L, b2))
        ))),
        
        Axiom("get_status_borrow_hit_succ", forall([L, b, b2, u], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                eq(app("get_status", L, b), const("available")),
                eq(app("get_status", app("borrow", L, b, u), b2), const("borrowed"))
            )
        ))),
        Axiom("get_status_borrow_hit_fail", forall([L, b, b2, u], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                Negation(eq(app("get_status", L, b), const("available"))),
                eq(app("get_status", app("borrow", L, b, u), b2), app("get_status", L, b2))
            )
        ))),
        Axiom("get_status_borrow_miss", forall([L, b, b2, u], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            eq(app("get_status", app("borrow", L, b, u), b2), app("get_status", L, b2))
        ))),

        Axiom("get_status_return_hit_succ", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                eq(app("get_status", L, b), const("borrowed")),
                eq(app("get_status", app("return_book", L, b), b2), const("available"))
            )
        ))),
        Axiom("get_status_return_hit_fail", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                Negation(eq(app("get_status", L, b), const("borrowed"))),
                eq(app("get_status", app("return_book", L, b), b2), app("get_status", L, b2))
            )
        ))),
        Axiom("get_status_return_miss", forall([L, b, b2], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            eq(app("get_status", app("return_book", L, b), b2), app("get_status", L, b2))
        ))),

        # ━━ get_borrower (8 axioms) ━━
        # Newly registered books have no borrower — explicitly undefined
        Axiom("get_borrower_register_hit", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            Negation(Definedness(app("get_borrower", app("register", L, b), b2)))
        ))),
        Axiom("get_borrower_register_miss", forall([L, b, b2], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            eq(app("get_borrower", app("register", L, b), b2), app("get_borrower", L, b2))
        ))),
        
        Axiom("get_borrower_borrow_hit_succ", forall([L, b, b2, u], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                eq(app("get_status", L, b), const("available")),
                eq(app("get_borrower", app("borrow", L, b, u), b2), u)
            )
        ))),
        Axiom("get_borrower_borrow_hit_fail", forall([L, b, b2, u], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                Negation(eq(app("get_status", L, b), const("available"))),
                eq(app("get_borrower", app("borrow", L, b, u), b2), app("get_borrower", L, b2))
            )
        ))),
        Axiom("get_borrower_borrow_miss", forall([L, b, b2, u], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            eq(app("get_borrower", app("borrow", L, b, u), b2), app("get_borrower", L, b2))
        ))),
        
        # Returned books lose their borrower — explicitly undefined
        Axiom("get_borrower_return_hit_succ", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                eq(app("get_status", L, b), const("borrowed")),
                Negation(Definedness(app("get_borrower", app("return_book", L, b), b2)))
            )
        ))),
        Axiom("get_borrower_return_hit_fail", forall([L, b, b2], Implication(
            PredApp("eq_id", (b, b2)),
            Implication(
                Negation(eq(app("get_status", L, b), const("borrowed"))),
                eq(app("get_borrower", app("return_book", L, b), b2), app("get_borrower", L, b2))
            )
        ))),
        Axiom("get_borrower_return_miss", forall([L, b, b2], Implication(
            Negation(PredApp("eq_id", (b, b2))),
            eq(app("get_borrower", app("return_book", L, b), b2), app("get_borrower", L, b2))
        ))),
    )

    return Spec(name="LibraryLending", signature=sig, axioms=axioms)