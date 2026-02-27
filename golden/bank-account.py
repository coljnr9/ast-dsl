"""
### Step 1: Identify Your Sorts
- `Account` (**atomic**): The primary carrier set for the bank account state machine. Since we are modeling a single account mathematically, we don't need a `Store` or finite map.
- `Amount` (**atomic**): An opaque carrier set representing money. We won't fully axiomatize arithmetic, but we rely on a few standard operators and a predicate.

### Step 2: Classify Functions and Predicates
**Functions:**
- `empty : → Account` — **Constructor**. The initial state with a zero balance.
- `deposit : Account × Amount → Account` — **Constructor**. Adds funds, returning a new account state. Total.
- `withdraw : Account × Amount →? Account` — **Partial Constructor**. Fails (is mathematically undefined) if there are insufficient funds.
- `balance : Account → Amount` — **Observer**. Inspects the state, total for all valid accounts.
- `zero : → Amount` — **Uninterpreted**. Yields the neutral cash amount.
- `add : Amount × Amount → Amount` — **Uninterpreted**. Models money accumulation.
- `sub : Amount × Amount → Amount` — **Uninterpreted**. Models money reduction.

**Predicates:**
- `geq : Amount × Amount` — **Uninterpreted**. Checks if the first amount is greater than or equal to the second.

### Step 3: Build the Axiom Obligation Table
Because `balance` is the only observer of `Account`, we owe axioms for how `balance` evaluates over each of `Account`'s three constructors.

Additionally, because `withdraw` is a partial constructor, we need a definedness domain axiom to formalize the "fails if insufficient funds" requirement.

| Observer / Operation | Constructor | Case / Guard | Axiom Label | Behavior |
|---------------------|------------|--------------|-------------|----------|
| `balance` | `empty` | — | `balance_empty` | `zero` |
| `balance` | `deposit` | — | `balance_deposit` | `add(balance(a), m)` |
| `balance` | `withdraw` | hit (defined) | `balance_withdraw` | `sub(balance(a), m)` |
| `withdraw` (domain) | — | — | `withdraw_definedness` | `Definedness(withdraw(a, m)) ⇔ geq(balance(a), m)` |

### Completeness Count & Tricky Cases
- **Completeness Count**: 1 observer × 3 constructors = 3 axioms + 1 domain definedness axiom = **4 axioms total**.
- **Design Decision — `withdraw` as Partial Constructor**: In algebraic formulation, state transitions that can fail are beautifully handled as partial constructors.
- **Tricky Case — Strong Equality and Partiality**: Because standard equality equations in this fragment (`eq(lhs, rhs)`) hold only if both sides map to strict values, mapping a partial constructor like `withdraw` equal to a total result (`sub(...)`) would unintentionally assert totality! To prevent this, the `balance_withdraw` axiom MUST explicitly guard the equality with an `Implication` requiring `geq(balance(a), m)`, enforcing that the evaluation happens strictly in the function's valid domain.
"""

from alspec import (
    Axiom, Implication, PredApp, Definedness,
    Signature, Spec, atomic, fn, pred, var, app, const, eq, forall, iff
)

def bank_account_spec() -> Spec:
    # Variables
    a = var("a", "Account")
    m = var("m", "Amount")

    # Frame Definition
    sig = Signature(
        sorts={
            "Account": atomic("Account"),
            "Amount": atomic("Amount"),
        },
        functions={
            # Account Constructors
            "empty": fn("empty", [], "Account"),
            "deposit": fn("deposit", [("a", "Account"), ("m", "Amount")], "Account"),
            "withdraw": fn("withdraw", [("a", "Account"), ("m", "Amount")], "Account", total=False),
            # Account Observer
            "balance": fn("balance", [("a", "Account")], "Amount"),
            # Amount Operators (Uninterpreted basis)
            "zero": fn("zero", [], "Amount"),
            "add": fn("add", [("m1", "Amount"), ("m2", "Amount")], "Amount"),
            "sub": fn("sub", [("m1", "Amount"), ("m2", "Amount")], "Amount"),
        },
        predicates={
            "geq": pred("geq", [("m1", "Amount"), ("m2", "Amount")]),
        },
    )

    axioms = (
        # balance × empty
        Axiom(
            label="balance_empty",
            formula=eq(app("balance", const("empty")), const("zero")),
        ),
        
        # balance × deposit
        Axiom(
            label="balance_deposit",
            formula=forall([a, m], eq(
                app("balance", app("deposit", a, m)),
                app("add", app("balance", a), m),
            )),
        ),
        
        # Domain requirement: withdraw fails if insufficient funds
        Axiom(
            label="withdraw_definedness",
            formula=forall([a, m], iff(
                Definedness(app("withdraw", a, m)),
                PredApp("geq", (app("balance", a), m)),
            )),
        ),
        
        # balance × withdraw (must be guarded because withdraw is partial)
        Axiom(
            label="balance_withdraw",
            formula=forall([a, m], Implication(
                PredApp("geq", (app("balance", a), m)),
                eq(
                    app("balance", app("withdraw", a, m)),
                    app("sub", app("balance", a), m),
                ),
            )),
        ),
    )

    return Spec(name="BankAccount", signature=sig, axioms=axioms)
