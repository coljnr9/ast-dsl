import textwrap


def render() -> str:
    return textwrap.dedent(
        """\
        ## 2. Type Grammar

        ```
        Term     = Var(name, sort)
                 | FnApp(fn_name, tuple[Term, ...])    ← args are Terms
                 | FieldAccess(Term, field_name)        ← inner is a Term
                 | Literal(value, sort)

        Formula  = Equation(Term, Term)                 ← both sides are Terms
                 | PredApp(pred_name, tuple[Term, ...]) ← args are Terms
                 | Negation(Formula)                    ← inner is a Formula, NEVER a Term
                 | Conjunction(tuple[Formula, ...])     ← all elements are Formulas
                 | Disjunction(tuple[Formula, ...])     ← all elements are Formulas
                 | Implication(Formula, Formula)        ← both are Formulas
                 | Biconditional(Formula, Formula)      ← both are Formulas
                 | UniversalQuant(tuple[Var, ...], Formula)
                 | ExistentialQuant(tuple[Var, ...], Formula)
                 | Definedness(Term)                    ← inner is a Term
        ```

        ### Valid Compositions

        | Expression | Why it's correct |
        |-----------|-----------------|
        | `eq(app(...), app(...))` | Both are Terms ✓ |
        | `eq(app(...), var(...))` | Both are Terms ✓ |
        | `Negation(eq(...))` | eq returns a Formula ✓ |
        | `Negation(PredApp(...))` | PredApp is a Formula ✓ |
        | `Implication(PredApp(...), eq(...))` | Both are Formulas ✓ |

        ---
        """
    )
