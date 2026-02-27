import textwrap


def render() -> str:
    return textwrap.dedent(
        """\
        # Many-Sorted Algebraic Specification DSL — Language Reference

        ## 1. Formal Frame

        You are writing specifications in **many-sorted first-order logic with
        partial functions** (the CASL fragment). Every expression you build lives
        in this formalism — use it to check your work.

        **Signature Σ = (S, F, P):**

        | Component | Definition |
        |-----------|-----------|
        | **S** | A set of *sort names* (the types / carrier sets) |
        | **F** | A set of *function symbols*, each with profile **f : s₁ × … × sₙ → s** (all sᵢ, s ∈ S). n = 0 ⇒ constant. Each is *total* (→) or *partial* (→?). |
        | **P** | A set of *predicate symbols*, each with profile **p : s₁ × … × sₙ** (no result sort — predicates hold or don't). |

        **Well-formedness:** A signature is well-formed when every sort reference
        in any function or predicate profile is declared in S. A term f(t₁, …, tₙ)
        is well-sorted when each tᵢ has sort sᵢ matching f's declared profile.
        An equation t₁ = t₂ is well-sorted when both sides have the *same* sort.
        An ill-sorted expression is meaningless, not merely wrong.

        **Terms vs. Formulas — these are categorically distinct:**
        - A **Term** denotes a *value* in a carrier set.
        - A **Formula** denotes a *truth value*.
        - You **cannot** put a Formula where a Term is expected, or vice versa.

        ---
        """
    )
