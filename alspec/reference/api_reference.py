import textwrap


def render() -> str:
    return textwrap.dedent(
        """\
        ## 3. Helper API

        Use these helpers to construct specs. Do not construct dataclasses directly.

        ### Sort Helpers

        | Call | Returns | Notes |
        |------|---------|-------|
        | `S(name)` | `SortRef` | Reference a sort by name |
        | `atomic(name)` | `AtomicSort` | Declare an opaque sort |
        | `ProductSort(name=S(...), fields=(...))` | `ProductSort` | Struct with named fields |
        | `CoproductSort(name=S(...), alts=(...))` | `CoproductSort` | Tagged union |

        ### Symbol & Variable Helpers

        | Call | Returns | Notes |
        |------|---------|-------|
        | `fn(name, params, result, total=True)` | `FnSymbol` | Declare a function symbol. `params`: `[(name, sort), ...]`, `result`: sort name |
        | `pred(name, params)` | `PredSymbol` | Declare a predicate. No result sort |
        | `var(name, sort)` | `Var` | Typed variable for use in axioms |

        ### Term Constructors

        | Call | Returns | Notes |
        |------|---------|-------|
        | `app(fn_name, *args)` | `FnApp` (Term) | Apply function symbol to Term arguments |
        | `const(name)` | `FnApp` (Term) | Nullary function application (0-ary constant) |
        | `field_access(term, field_name)` | `FieldAccess` (Term) | Access named field on product-sorted term |

        ### Formula Constructors

        | Call | Returns | Notes |
        |------|---------|-------|
        | `eq(lhs, rhs)` | `Equation` (Formula) | Both args must be Terms of same sort |
        | `forall(vars, body)` | `UniversalQuant` (Formula) | `vars`: list of Var, `body`: Formula |
        | `exists(vars, body)` | `ExistentialQuant` (Formula) | `vars`: list of Var, `body`: Formula |
        | `iff(lhs, rhs)` | `Biconditional` (Formula) | Both args must be Formulas |
        | `pred_app(pred_name, *args)` | `PredApp` (Formula) | `args`: Terms (varargs, NOT a tuple) |
        | `negation(formula)` | `Negation` (Formula) | Inner must be a Formula |
        | `conjunction(f1, f2, ...)` | `Conjunction` (Formula) | All args must be Formulas (varargs) |
        | `disjunction(f1, f2, ...)` | `Disjunction` (Formula) | All args must be Formulas (varargs) |
        | `implication(antecedent, consequent)` | `Implication` (Formula) | Both must be Formulas |
        | `definedness(term)` | `Definedness` (Formula) | Inner must be a Term |

        ### Assembly

        | Call | Notes |
        |------|-------|
        | `Signature(sorts={...}, functions={...}, predicates={...})` | Dict keys are names |
        | `Axiom(label=..., formula=...)` | Formula should be quantified |
        | `Spec(name=..., signature=..., axioms=(...))` | Axioms are a tuple |

        ---
        """
    )
