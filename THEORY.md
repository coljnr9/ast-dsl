# THEORY.md

## Formal Foundations

This project implements a fragment of many-sorted first-order logic with partial functions, following the Common Algebraic Specification Language (CASL). The two primary references are:

- Astesiano et al., "CASL: The Common Algebraic Specification Language" (2001)
- Sannella & Tarlecki, *Foundations of Algebraic Specification and Formal Software Development* (2012)

What follows are the formal definitions that ground the DSL's design. When in doubt about whether a spec is correct, check it against these definitions — not against pattern similarity to existing examples.

---

## 1. Signatures

A many-sorted signature **Σ = (S, F, P)** consists of:

- **S**: a set of *sort names*
- **F**: a set of *function symbols*, each with a profile **f : s₁ × s₂ × ... × sₙ → s** where all sᵢ and s are in S. A function with n = 0 is a *constant*. Each function is either *total* or *partial* (written →?).
- **P**: a set of *predicate symbols*, each with a profile **p : s₁ × s₂ × ... × sₙ** (no result sort — predicates hold or don't hold).

A signature is **well-formed** when every sort reference appearing in any function or predicate profile is declared in S.

## 2. Terms and Well-Sortedness

Given a signature Σ and a set of typed variables X = {x₁ : s₁, x₂ : s₂, ...}, the set of **well-sorted Σ-terms** T(Σ, X) is defined inductively:

1. Every variable x : s is a term of sort s.
2. If f : s₁ × ... × sₙ → s is in F, and t₁, ..., tₙ are terms of sorts s₁, ..., sₙ respectively, then **f(t₁, ..., tₙ)** is a term of sort s.
3. Constants (0-ary functions) c : → s yield the term **c** of sort s.

A term is **ill-sorted** if any function is applied to arguments whose sorts do not match its declared profile. Well-sortedness is the single most important static check — an ill-sorted equation is meaningless, not merely wrong.

## 3. Formulas

Formulas are built from terms but are categorically distinct from them. A term *denotes a value* in a carrier set; a formula *denotes a truth value*. The grammar:

- **t₁ = t₂** (equation) — where t₁ and t₂ are terms of the *same sort*
- **p(t₁, ..., tₙ)** (predicate application) — where the tᵢ match the profile of p
- **¬φ, φ₁ ∧ φ₂, φ₁ ∨ φ₂, φ₁ ⇒ φ₂, φ₁ ⇔ φ₂** (logical connectives over formulas)
- **∀x : s • φ, ∃x : s • φ** (quantification)
- **def(t)** (definedness assertion for partial functions)

Equations require both sides to have the same sort. This is a well-sortedness condition on formulas, not merely a convention.

## 4. Algebras and Satisfaction

A **Σ-algebra** A provides:

- A non-empty *carrier set* |A|ₛ for each sort s in S
- A function fᴬ : |A|ₛ₁ × ... × |A|ₛₙ → |A|ₛ for each total function symbol (partial functions may be undefined on some inputs)
- A relation pᴬ ⊆ |A|ₛ₁ × ... × |A|ₛₙ for each predicate symbol

An algebra A **satisfies** an axiom ∀x₁:s₁, ..., xₖ:sₖ • φ when, for every assignment of values from the appropriate carrier sets to the variables, the formula φ evaluates to true under the standard interpretation.

A **specification** SP = (Σ, Φ) consists of a signature Σ and a set of axioms Φ. The **models** of SP are all Σ-algebras that satisfy every axiom in Φ. This is *loose semantics* — we admit all algebras satisfying the axioms, not just the initial or free one.

## 5. Loose Semantics — The Governing Principle

This project uses **loose semantics** throughout. This is the single most important design decision and it affects everything: how axioms are written, what "complete" means, and what omission signifies.

Under loose semantics, the models of a specification are **all** Σ-algebras that satisfy the axiom set. There is no distinguished "intended" model. Any implementation that satisfies every axiom is a valid model — a hash map and a linked list are equally valid models of FiniteMap if they both satisfy the axioms.

The critical consequence: **silence is permission, not prohibition.** If the axiom set says nothing about `f(c(...))` for some constructor `c`, then every model is free to interpret that case however it wants. Some model returns 0. Another returns 42. Another is undefined. All are valid, because no axiom rules them out.

This means:

- **Omitting an axiom does NOT encode undefinedness.** It leaves the case unconstrained — "anything goes" in some valid model. If you *want* a partial function to be undefined on some constructor case, you must write an explicit `¬def(f(c(...)))` axiom. The partiality declaration (`→?`) merely permits undefinedness; it does not cause it.
- **A complete specification has no silent gaps.** Every cell in the (observer × constructor) obligation table must have an explicit axiom: an equation for defined cases, a `¬def(...)` for undefined cases, or a delegation. Missing a cell doesn't mean "undefined" — it means "I forgot to specify this, and implementations can do whatever they want."
- **This is what makes the obligation table methodology essential.** The table is a completeness checklist. Under free semantics, you might argue that constructor exhaustion handles completeness implicitly. Under loose semantics, every gap is a semantic hole that admits unintended models.

### Contrast with Generated and Free Semantics

- **Loose**: all Σ-algebras satisfying Φ. Maximum implementation freedom. This is what alspec produces.
- **Generated** (no junk): only algebras whose carrier sets are generated by the declared constructors. Every value must be expressible as a constructor term.
- **Free** (no junk, no confusion): generated algebras where distinct constructor terms yield distinct values. This is the standard interpretation of datatypes in programming languages.

The axiom obligation pattern — one axiom per (observer, constructor) pair — arises from structural induction over the free term algebra. If a sort has constructors c₁, ..., cₖ and an observer f, then f is *completely defined* when there is an axiom specifying f(cᵢ(...)) for each i. Under free/generated semantics, missing a constructor case means f is unspecified on those terms. Under loose semantics, missing a case means f is **unconstrained** — any behavior is permitted, which almost certainly admits unintended models.

## 6. Partial Functions and Definedness

A partial function f : s₁ × ... × sₙ →? s may be undefined for some inputs. CASL distinguishes:

- **Strong equation** (t₁ = t₂): holds when both sides are defined and equal, *or* both undefined.
- **Existential equation** (t₁ =ₑ t₂): holds only when both sides are defined and equal.
- **Definedness** (def(t)): holds when t is defined.

When any argument to a partial function is undefined, the result is undefined (strict error propagation). When any argument to a predicate is undefined, the predicate does not hold.

### Axiom Patterns for Partial Functions

Under loose semantics, partial functions require **explicit axioms for every constructor case**, including cases where the function is undefined. There are three patterns:

**1. Defined case — write the equation:**
```
top(push(s, e)) = e
```
The observer returns a value; say what it is.

**2. Undefined case — write an explicit undefinedness axiom:**
```
¬def(top(new))
```
The observer is undefined here. You must say so explicitly. Without this axiom, `top(new)` is not "undefined" — it is *unconstrained*, meaning some valid model could give it any value, which is almost certainly not what you intend.

**3. Partial constructor with a definedness biconditional:**
When a constructor itself is partial (e.g., `inc` on a bounded counter that can't increment past max), express the definedness condition:
```
def(inc(c)) ⇔ ¬is_at_max(c)
```
This constrains exactly when the constructor produces a defined value.

**The old pattern of "omit the case and let the partiality declaration handle it" is wrong under loose semantics.** The `→?` annotation permits undefinedness but does not cause it. Only an explicit `¬def(...)` axiom forces undefinedness in all models.

---

## 7. Generated Sorts, Constructors, and Selectors

### Generated Sorts

A **generated sort** is a sort whose values are built by a declared set of constructors. In alspec, this is recorded in the signature via `generated_sorts`:

```python
generated_sorts = {
    "Stack": GeneratedSortInfo(
        constructors=("new", "push"),
        selectors={"push": {"top": "Elem", "pop": "Stack"}},
    )
}
```

This declaration says: every value of sort `Stack` is either `new` or `push(s, e)` for some `s : Stack` and `e : Elem`. There is no "third kind" of stack. This is the structural basis for the obligation table — if you know the constructors, you know which cases every observer must cover.

Not every sort needs to be generated. Opaque sorts like `Elem`, `TicketId`, or `Temp` have no constructors declared in our spec — they represent abstract values we don't decompose. Only the *primary domain sorts* (Stack, Queue, Store, Lock, Thermostat, etc.) are generated.

### Function Roles

Every function in the signature occupies exactly one role relative to a generated sort:

| Role | Definition | Examples |
|------|-----------|----------|
| **Constructor** | Builds values of the generated sort. Listed in `constructors`. | `new`, `push`, `enqueue`, `create_ticket` |
| **Observer** | Takes the generated sort as first argument, returns a different sort. Not a constructor. | `get_value`, `front`, `get_status` |
| **Selector** | A special observer: extracts exactly one component from exactly one constructor. Declared in `selectors`. | `top` (extracts `Elem` from `push`), `pop` (extracts `Stack` from `push`) |
| **Constant** | Nullary function producing a non-generated sort. Not a constructor. | `zero`, `open`, `resolved`, `init_target` |
| **Uninterpreted** | Function that appears in axioms but is not defined by them. | `classify : Title × Body → SeverityLevel` |

The distinction between observers and selectors is important. An observer can have arbitrary axioms for each constructor case. A selector's axioms are *mechanically derivable* from the constructor profile — `top(push(s, e)) = e` extracts the second parameter, always and unconditionally.

### Selectors in Detail

A **selector** of constructor `c` is an observer `sel` such that `sel(c(x₁, ..., xₙ)) = xᵢ` — it extracts the i-th component by simple projection. The relationship is always per-constructor:

```
get_target(set_target(th, t)) = t     ← selector of set_target
get_target(read_temp(th, r)) = get_target(th)  ← NOT a selector of read_temp (preservation, not extraction)
```

In `golden/thermostat.py`, `get_target` is a selector of `set_target` but a regular observer of `read_temp` and `new`. The selector relationship governs one cell in the obligation table — not the whole observer.

Selectors matter because they determine **cell tiers** (see Section 8), which tell the axiom writer whether a cell is mechanical or requires domain reasoning.

### Predicate Roles

Predicates occupy analogous roles:

| Role | Definition | Examples |
|------|-----------|----------|
| **Observer predicate** | Takes the generated sort as first argument. Owes axioms against all constructors. | `empty`, `has_ticket`, `is_critical`, `heater_on` |
| **Equality predicate** | Binary predicate on an opaque sort, used for key dispatch. Requires basis axioms (reflexivity, symmetry, transitivity). | `eq_id`, `eq_code`, `eq_name` |
| **Helper predicate** | Used in axiom bodies but not an observer of the generated sort. | `lt` (temperature ordering), `geq` (balance comparison) |

---

## 8. The Obligation Table

The obligation table is the central completeness tool. It is a formal object derived mechanically from the signature — no domain knowledge required.

### 8a. Cell Generation

For each generated sort, the table has one cell per **(observer, constructor)** pair:

```
cells = { (obs, ctor) | obs ∈ observers_of(sort), ctor ∈ constructors_of(sort) }
```

An observer of a sort is any function or predicate whose first parameter is that sort and which is not itself a constructor.

**Example: Stack** has 2 constructors (`new`, `push`) and 3 observers (`pop`, `top`, `empty`), yielding 6 cells:

| Observer | new | push |
|----------|-----|------|
| pop      | ●   | ●    |
| top      | ●   | ●    |
| empty    | ●   | ●    |

**Example: Bug Tracker** has 4 constructors (`empty`, `create_ticket`, `resolve_ticket`, `assign_ticket`) and 5 observers (`get_status`, `get_severity`, `get_assignee`, `has_ticket`, `is_critical`), yielding 20 base cells. But some of these split into HIT+MISS via key dispatch (see 8b), producing 35 total cells.

### 8b. Dispatch Classification (PLAIN vs HIT/MISS)

When both an observer and a constructor take a **shared key sort** parameter, the cell splits into two sub-cells:

- **HIT**: the observer's key matches the constructor's key (`eq_pred(k, k2)` holds)
- **MISS**: the keys differ (`¬eq_pred(k, k2)`)

The split occurs when there exists a sort `K` such that:
1. The observer takes a parameter of sort `K` (beyond its first/primary argument)
2. The constructor takes a parameter of sort `K` (beyond its first/primary argument)
3. An equality predicate `eq_K : K × K` is declared in the signature

If no shared key sort exists, the cell is **PLAIN** — one axiom covers it completely.

**Example:** In Bug Tracker, `get_status : Store × TicketId → Status` and `create_ticket : Store × TicketId × Title × Body → Store` both take `TicketId`. With `eq_id : TicketId × TicketId` declared, the cell `(get_status, create_ticket)` splits into HIT and MISS:

```
get_status(create_ticket(s, k, t, b), k2)  where eq_id(k, k2)   → HIT cell
get_status(create_ticket(s, k, t, b), k2)  where ¬eq_id(k, k2)  → MISS cell
```

**Critical distinction — domain guards vs dispatch guards:** In `golden/door-lock.py`, the axiom for `get_state(lock(l, c))` has a guard `eq_code(c, get_code(l)) ∧ get_state(l) = unlocked`. This uses `eq_code`, but the cell is **PLAIN**, not HIT/MISS. Why? Because `get_state : Lock → State` and `lock : Lock × Code → Lock` — the observer takes no `Code` parameter. There is no shared key sort between observer and constructor. The `eq_code` guard is *domain logic* (checking the right code was provided), not *structural key dispatch* (routing to HIT vs MISS sub-cells).

**Rule of thumb:** Key dispatch requires a shared key sort in the *profiles* of both the observer and constructor. If only the constructor takes the key sort, any equality guard on that sort is domain logic, and the cell stays PLAIN.

### 8c. Cell Tiers

Each cell is classified into a tier that tells the axiom writer how much reasoning is required:

| Tier | Meaning | Axiom Pattern |
|------|---------|--------------|
| **SELECTOR_EXTRACT** | Observer is a selector of this constructor. Axiom is mechanical. | `sel(ctor(x₁, ..., xₙ)) = xᵢ` — extract the i-th component |
| **SELECTOR_FOREIGN** | Observer is a selector of a *different* constructor. Almost always undefined. | `¬def(sel(ctor(...)))` — the selector can't extract from a constructor it doesn't belong to |
| **DOMAIN** | Neither of the above. Requires domain-specific reasoning. | Equations, preservation, ¬def, biconditionals — whatever the domain demands |

**Example: Stack obligation table with tiers:**

| # | Observer | Constructor | Tier | Axiom |
|---|----------|------------|------|-------|
| 1 | `pop` (partial) | `new` | SELECTOR_FOREIGN | `¬def(pop(new))` |
| 2 | `pop` (partial) | `push` | SELECTOR_EXTRACT | `pop(push(s, e)) = s` |
| 3 | `top` (partial) | `new` | SELECTOR_FOREIGN | `¬def(top(new))` |
| 4 | `top` (partial) | `push` | SELECTOR_EXTRACT | `top(push(s, e)) = e` |
| 5 | `empty` (pred) | `new` | DOMAIN | `empty(new)` |
| 6 | `empty` (pred) | `push` | DOMAIN | `¬empty(push(s, e))` |

Cells 1-4 are mechanical — an LLM (or a code generator) can fill them without understanding what a stack is. Cells 5-6 require knowing that `new` creates an empty stack and `push` makes it non-empty.

**Example: Temperature Sensor with tiers:**

| # | Observer | Constructor | Tier | Axiom |
|---|----------|------------|------|-------|
| 1 | `read` (partial) | `init` | SELECTOR_FOREIGN | `¬def(read(init))` |
| 2 | `read` (partial) | `record` | SELECTOR_EXTRACT | `read(record(s, t)) = t` |
| 3 | `has_reading` (pred) | `init` | DOMAIN | `¬has_reading(init)` |
| 4 | `has_reading` (pred) | `record` | DOMAIN | `has_reading(record(s, t))` |

Selectors make the spec partially self-writing. The remaining DOMAIN cells are where the real specification work happens.

---

## 9. Axiom Patterns by Cell Type

Each obligation cell is filled by one or more axioms. The patterns below cover every case that appears across the 20 golden reference specs. They are grouped by the amount of reasoning required.

### 9a. Selector Extraction (SELECTOR_EXTRACT) — Mechanical

The observer extracts one component from the constructor. The axiom follows directly from the selector declaration.

```
∀s:Stack, e:Elem • pop(push(s, e)) = s            — extracts the Stack component
∀s:Stack, e:Elem • top(push(s, e)) = e            — extracts the Elem component
∀th:Thermostat, t:Temp • get_target(set_target(th, t)) = t    — extracts the Temp component
∀l:Lock, c:Code • get_code(new(c)) = c            — extracts the Code component (door-lock)
```

The pattern is always: `sel(ctor(x₁, ..., xₙ)) = xᵢ` where `xᵢ` is the parameter of sort matching the selector's result sort. No domain knowledge needed.

### 9b. Selector Foreign (SELECTOR_FOREIGN) — Mechanical

The observer is a selector that belongs to a *different* constructor. Under loose semantics, the selector must be explicitly marked undefined here.

```
¬def(pop(new))                                    — pop belongs to push, not new
¬def(top(new))                                    — top belongs to push, not new
¬def(read(init))                                  — read belongs to record, not init
```

The pattern is always: `¬def(sel(ctor(...)))`. No domain knowledge needed.

**Why this must be explicit:** Under loose semantics, omitting this axiom does not make `pop(new)` undefined. It leaves `pop(new)` *unconstrained* — some valid model could give it any stack value. The `¬def(...)` axiom forces undefinedness in all models.

### 9c. Domain Equations — Requires Reasoning

The most common cell type. The observer returns a specific value determined by the domain semantics.

**Simple equations (no guards):**
```
∀c:Counter • get_value(new) = zero
∀c:Counter • get_value(inc(c)) = succ(get_value(c))
∀s:Stack, e:Elem • ¬empty(push(s, e))
```

**Preservation equations** — the constructor doesn't change this observer:
```
∀th:Thermostat, r:Temp • get_target(read_temp(th, r)) = get_target(th)
∀l:Lock, c:Code • get_code(lock(l, c)) = get_code(l)
```

Preservation is the most common pattern for non-primary observers — if `read_temp` updates the current reading, it preserves the target temperature.

**Predicate observer biconditionals:**
```
∀th:Thermostat, t:Temp • heater_on(set_target(th, t)) ⇔ lt(get_current(th), t)
∀c:Counter, m:Nat • is_at_max(new(m)) ⇔ (zero = m)
```

When a predicate's truth value is determined by a condition, use a biconditional (`⇔`). This is stronger than an implication — it specifies both when the predicate holds and when it doesn't.

### 9d. Key Dispatch: HIT and MISS Cells

When a cell splits into HIT/MISS (see Section 8b), each sub-cell gets a guarded axiom.

**HIT — keys match, write the "update" behavior:**
```
∀s:Store, k:TicketId, k2:TicketId, t:Title, b:Body •
    eq_id(k, k2) ⇒ get_status(create_ticket(s, k, t, b), k2) = open
```

**MISS — keys differ, delegate to the inner state:**
```
∀s:Store, k:TicketId, k2:TicketId, t:Title, b:Body •
    ¬eq_id(k, k2) ⇒ get_status(create_ticket(s, k, t, b), k2) = get_status(s, k2)
```

This is the **FiniteMap pattern**: store-like data structures indexed by a key sort. The HIT case says "when you're looking up the key you just inserted/modified, here's the new value." The MISS case says "when you're looking up a different key, the value hasn't changed."

**Nested guards** — key dispatch wrapping a domain guard:

When the HIT behavior depends on additional conditions, nest implications:

```
∀s:Store, k:TicketId, k2:TicketId •
    eq_id(k, k2) ⇒                    ← outer: key dispatch (HIT)
        (has_ticket(s, k) ⇒           ← inner: domain guard
            get_status(resolve_ticket(s, k), k2) = resolved)
```

This says: when resolving ticket `k` and looking up `k2 = k`, if ticket `k` exists, its status becomes `resolved`. The domain guard `has_ticket` is inside the key dispatch guard `eq_id`.

**Both guard polarities must be written.** If you write the `has_ticket` positive case, you must also write the negative case:

```
∀s:Store, k:TicketId, k2:TicketId •
    eq_id(k, k2) ⇒
        (¬has_ticket(s, k) ⇒
            get_status(resolve_ticket(s, k), k2) = get_status(s, k2))
```

### 9e. Preservation Collapse

When a constructor does not affect an observer **for any key**, the HIT and MISS axioms collapse into a single universal equation:

```
∀s:Store, k:TicketId, k2:TicketId •
    get_severity(resolve_ticket(s, k), k2) = get_severity(s, k2)
```

This single axiom covers both the HIT cell and the MISS cell. There is no `eq_id` guard — the equation holds unconditionally for all `k` and `k2`. Resolving a ticket never changes any ticket's severity.

Compare with what two separate axioms would look like:
```
eq_id(k, k2) ⇒ get_severity(resolve_ticket(s, k), k2) = get_severity(s, k2)    ← HIT
¬eq_id(k, k2) ⇒ get_severity(resolve_ticket(s, k), k2) = get_severity(s, k2)   ← MISS
```

The RHS is identical in both cases, so the guard is redundant. One unguarded axiom is cleaner, and the obligation matcher recognizes it as covering both cells.

**When to use preservation collapse:** Whenever a constructor acts on a sort-level concern orthogonal to the observer. Common examples:
- `resolve_ticket` doesn't affect `get_severity` or `get_assignee`
- `assign_ticket` doesn't affect `get_status` or `get_severity`
- `read_temp` doesn't affect `get_target`

### 9f. Partial Constructor Definedness

When a constructor is partial (not all inputs produce a valid result), state when it's defined:

```
∀c:Counter • def(inc(c)) ⇔ ¬is_at_max(c)
```

This is a **biconditional on `Definedness`** — it says `inc(c)` is defined exactly when the counter isn't at max. This is NOT an obligation cell — it's a separate axiom about the constructor itself. The obligation matcher classifies it as `CONSTRUCTOR_DEF`.

The conditional axioms for observers of the partial constructor are then implicitly guarded by this definedness condition:

```
∀c:Counter • ¬is_at_max(c) ⇒ val(inc(c)) = suc(val(c))
∀c:Counter • ¬is_at_max(c) ⇒ (is_at_max(inc(c)) ⇔ suc(val(c)) = max_val(c))
```

### 9g. Domain Sub-Cases

Sometimes a single obligation cell requires multiple axioms because the behavior depends on the *structure* of the inner argument. This is distinct from key dispatch — there's no equality predicate involved.

**Queue** is the canonical example. The cell `(dequeue, enqueue)` needs two axioms because the behavior depends on whether the inner queue is empty:

```
∀e:Elem • dequeue(enqueue(empty, e)) = empty                              — base: 1-element queue
∀q:Queue, e1:Elem, e2:Elem • dequeue(enqueue(enqueue(q, e1), e2))         — recursive: >1 elements
    = enqueue(dequeue(enqueue(q, e1)), e2)
```

Both axioms fill the same `(dequeue, enqueue, PLAIN)` cell. The obligation matcher recognizes this as `MULTI_COVERED` — multiple axioms covering one cell, which is valid.

**Door-lock** has a similar pattern. The cell `(get_state, lock, PLAIN)` needs two axioms:

```
∀l:Lock, c:Code • eq_code(c, get_code(l)) ∧ get_state(l) = unlocked
    ⇒ get_state(lock(l, c)) = locked                                      — correct code + unlocked: lock it

∀l:Lock, c:Code • ¬(eq_code(c, get_code(l)) ∧ get_state(l) = unlocked)
    ⇒ get_state(lock(l, c)) = get_state(l)                                — wrong code or wrong state: no-op
```

These are domain-level case splits, not key dispatch. The cell is PLAIN because `get_state : Lock → State` has no key parameter to share with `lock`.

### 9h. Equality Predicate Basis Axioms

Every equality predicate requires three structural axioms that establish it as a congruence relation:

```
∀k:TicketId • eq_id(k, k)                                                 — reflexivity
∀k:TicketId, k2:TicketId • eq_id(k, k2) ⇒ eq_id(k2, k)                   — symmetry
∀k:TicketId, k2:TicketId, k3:TicketId •
    (eq_id(k, k2) ∧ eq_id(k2, k3)) ⇒ eq_id(k, k3)                       — transitivity
```

These are NOT obligation cells — they don't involve a constructor of the generated sort. The obligation matcher classifies them as `BASIS`. Every spec that uses key dispatch needs these three axioms per equality predicate.

---

## 10. Signature Morphisms

A **signature morphism** σ : Σ → Σ' maps sorts to sorts and function/predicate symbols to symbols of matching profile. This is how parameterized specs are instantiated: `FiniteMap(Key, Val)` becomes `LibraryCatalog(BookID, Patron)` via a morphism that sends `Key ↦ BookID`, `Val ↦ Patron`, preserving all profiles and axioms.

This matters for the code generation pipeline because each stage effectively constructs a morphism — mapping abstract sorts from the specification to concrete types in the implementation.
