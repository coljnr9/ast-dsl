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

        Formula  = eq(Term, Term)                          ← Equation
                 | pred_app(pred_name, Term, ...)           ← PredApp (varargs)
                 | negation(Formula)                        ← inner is a Formula, NEVER a Term
                 | conjunction(Formula, ...)                ← all args are Formulas (varargs)
                 | disjunction(Formula, ...)                ← all args are Formulas (varargs)
                 | implication(Formula, Formula)            ← both are Formulas
                 | iff(Formula, Formula)                    ← both are Formulas (Biconditional)
                 | forall(list[Var], Formula)
                 | exists(list[Var], Formula)
                 | definedness(Term)                        ← inner is a Term
        ```

        ### Valid Compositions

        | Expression | Why it's correct |
        |-----------|------------------|
        | `eq(app(...), app(...))` | Both are Terms ✓ |
        | `eq(app(...), var(...))` | Both are Terms ✓ |
        | `negation(eq(...))` | eq returns a Formula ✓ |
        | `negation(pred_app(...))` | pred_app is a Formula ✓ |
        | `implication(pred_app(...), eq(...))` | Both are Formulas ✓ |
        | `iff(pred_app(...), pred_app(...))` | Formula ⇔ Formula ✓ |
        | `iff(pred_app(...), eq(...))` | Formula ⇔ Formula ✓ |
        | `conjunction(pred_app(...), pred_app(...))` | All args are Formulas ✓ |

        ---
        """
    )
