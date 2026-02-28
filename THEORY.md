# THEORY.md

## Formal Foundations

This project implements a fragment of many-sorted first-order logic with partial functions, following the Common Algebraic Specification Language (CASL). The two primary references are:

- Astesiano et al., "CASL: The Common Algebraic Specification Language" (2001)
- Sannella & Tarlecki, *Foundations of Algebraic Specification and Formal Software Development* (2012)

What follows are the formal definitions that ground the DSL's design. When in doubt about whether a spec is correct, check it against these definitions — not against pattern similarity to existing examples.

---

## Signatures

A many-sorted signature **Σ = (S, F, P)** consists of:

- **S**: a set of *sort names*
- **F**: a set of *function symbols*, each with a profile **f : s₁ × s₂ × ... × sₙ → s** where all sᵢ and s are in S. A function with n = 0 is a *constant*. Each function is either *total* or *partial* (written →?).
- **P**: a set of *predicate symbols*, each with a profile **p : s₁ × s₂ × ... × sₙ** (no result sort — predicates hold or don't hold).

A signature is **well-formed** when every sort reference appearing in any function or predicate profile is declared in S.

## Terms and Well-Sortedness

Given a signature Σ and a set of typed variables X = {x₁ : s₁, x₂ : s₂, ...}, the set of **well-sorted Σ-terms** T(Σ, X) is defined inductively:

1. Every variable x : s is a term of sort s.
2. If f : s₁ × ... × sₙ → s is in F, and t₁, ..., tₙ are terms of sorts s₁, ..., sₙ respectively, then **f(t₁, ..., tₙ)** is a term of sort s.
3. Constants (0-ary functions) c : → s yield the term **c** of sort s.

A term is **ill-sorted** if any function is applied to arguments whose sorts do not match its declared profile. Well-sortedness is the single most important static check — an ill-sorted equation is meaningless, not merely wrong.

## Formulas

Formulas are built from terms but are categorically distinct from them. A term *denotes a value* in a carrier set; a formula *denotes a truth value*. The grammar:

- **t₁ = t₂** (equation) — where t₁ and t₂ are terms of the *same sort*
- **p(t₁, ..., tₙ)** (predicate application) — where the tᵢ match the profile of p
- **¬φ, φ₁ ∧ φ₂, φ₁ ∨ φ₂, φ₁ ⇒ φ₂, φ₁ ⇔ φ₂** (logical connectives over formulas)
- **∀x : s • φ, ∃x : s • φ** (quantification)
- **def(t)** (definedness assertion for partial functions)

Equations require both sides to have the same sort. This is a well-sortedness condition on formulas, not merely a convention.

## Algebras and Satisfaction

A **Σ-algebra** A provides:

- A non-empty *carrier set* |A|ₛ for each sort s in S
- A function fᴬ : |A|ₛ₁ × ... × |A|ₛₙ → |A|ₛ for each total function symbol (partial functions may be undefined on some inputs)
- A relation pᴬ ⊆ |A|ₛ₁ × ... × |A|ₛₙ for each predicate symbol

An algebra A **satisfies** an axiom ∀x₁:s₁, ..., xₖ:sₖ • φ when, for every assignment of values from the appropriate carrier sets to the variables, the formula φ evaluates to true under the standard interpretation.

A **specification** SP = (Σ, Φ) consists of a signature Σ and a set of axioms Φ. The **models** of SP are all Σ-algebras that satisfy every axiom in Φ. This is *loose semantics* — we admit all algebras satisfying the axioms, not just the initial or free one.

## Loose Semantics — The Governing Principle

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

## Partial Functions and Definedness

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

## Signature Morphisms

A **signature morphism** σ : Σ → Σ' maps sorts to sorts and function/predicate symbols to symbols of matching profile. This is how parameterized specs are instantiated: `FiniteMap(Key, Val)` becomes `LibraryCatalog(BookID, Patron)` via a morphism that sends `Key ↦ BookID`, `Val ↦ Patron`, preserving all profiles and axioms.

This matters for the code generation pipeline because each stage effectively constructs a morphism — mapping abstract sorts from the specification to concrete types in the implementation.
