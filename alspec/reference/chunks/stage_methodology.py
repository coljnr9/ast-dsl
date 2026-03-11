from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, SIG_AX, SIG, AX, register,
)


@register(
    id=ChunkId.SIGNATURE_METHODOLOGY,
    stages=SIG,
    concepts=frozenset({Concept.FUNCTION_ROLES, Concept.OBLIGATION_TABLE, Concept.KEY_DISPATCH}),
    depends_on=(ChunkId.DISPATCH_RULES,),
)
def _signature_methodology():
    return """### Signature Design Methodology

Follow these steps to design the signature. The worked examples above demonstrate each step.

**Step 1 — Identify sorts.** Name the state sort (the generated sort), all parameter sorts,
and any result sorts. Prefer the simplest sort set that captures the domain. Do not add
sorts speculatively — every sort should be justified by a function that uses it.

**Step 2 — Classify functions.** For each operation in the domain, decide its role:
- **Constructor:** builds or modifies the state sort (first param may or may not be the state sort)
- **Observer:** queries the state sort (first param IS the state sort, returns a different sort)
- **Selector:** extracts a component injected by a specific constructor (special case of observer)
- **Constant:** nullary function producing a parameter sort value (e.g., `zero`, `true`)
- **Helper:** operates entirely on parameter sorts, never touches the state sort (e.g., `succ`, `add`)

**Step 3 — Classify predicates.** For each predicate, decide its role:
- **Observer predicate:** first param is the generated sort — it queries state (e.g., `is_empty(s)`, `is_open(acc)`)
- **Equality predicate:** named `eq_<sort>`, used for key dispatch (e.g., `eq_token(t1, t2)`)
- **Helper predicate:** operates entirely on parameter sorts — comparisons, orderings (e.g., `geq(n1, n2)`, `lt(a, b)`)

This classification matters because observer predicates create obligation table rows.
Observer predicates have the generated sort as first parameter — they query state.
Helper predicates operate entirely on parameter sorts — comparisons, orderings.
Keep comparison logic in helper predicates and use observer predicates for simple state queries.
The worked examples demonstrate this distinction.

**Step 4 — Mark partial functions.** Any constructor or observer that may be undefined
in some cases gets `total=False`.

**Step 5 — Determine generated sorts and their constructors.** Identify which sort is
built by the constructors. Register selectors if any constructor injects a value that
a specific observer extracts.

### Output Format

Output Python code that assigns `sig = Signature(...)` at the top level (no function wrapper).
Include all necessary imports at the top.

Your code should look like:
```
from alspec import Signature, atomic, fn, pred, GeneratedSortInfo

sig = Signature(
    sorts={...},
    functions={...},
    predicates={...},
    generated_sorts={...},
)
```

- `sorts`: all sort declarations using `atomic(name)`
- `functions`: all function symbols using `fn(name, params, result, total=True/False)`
- `predicates`: all predicate symbols using `pred(name, params)`
- `generated_sorts`: for each generated sort, use `GeneratedSortInfo(constructors=(...), selectors={...})`

Do NOT wrap the code in a function definition.
Do NOT write any axioms — a later stage will handle axiom generation.
Call the `submit_signature` tool with your analysis and signature code."""


@register(
    id=ChunkId.AXIOMS_METHODOLOGY,
    stages=AX,
    concepts=frozenset({
        Concept.OBLIGATION_TABLE, Concept.COMPLETENESS, Concept.HIT_MISS,
        Concept.EQ_PRED, Concept.LOOSE_SEMANTICS,
    }),
    depends_on=(ChunkId.EQ_PRED_BASIS,),
)
def _axioms_methodology():
    return """### Axiom Writing Methodology

Write axioms covering **every obligation cell** in the obligation table provided in the user prompt.
Also write any additional axioms noted in the table (equality basis, definedness biconditionals).

Cell coverage rules:
- **MISS cells:** write delegation/preservation axioms
- **HIT cells:** write the domain-specific equation or predicate assertion
- **Equality predicates:** if the signature includes `eq_*` predicates, use them for key dispatch
  guards: `implication(pred_app("eq_id", k, k2), ...)` for HIT cells and
  `implication(negation(pred_app("eq_id", k, k2)), ...)` for MISS cells.
  Do NOT use term equality `eq(k, k2)` as a dispatch guard — always use the declared
  equality predicate via `pred_app`.
- Follow the loose semantics rules from the reference: use explicit `¬def(...)` for undefinedness

### Output Format

Return your axioms as formula fills using the `submit_axiom_fills` tool. Each fill has:
- `label`: A snake_case axiom label (e.g., `get_cv_step_reset`)
- `formula`: A complete Python DSL expression using the helper functions from the skeleton's import block

The skeleton (imports, signature, mechanical axioms) is provided in the user prompt.
Your fills will be spliced into it -- you do NOT need to write imports, the signature,
or the Spec wrapper. You MUST declare all variables you use in the `variables` field
of the tool call.

Multiple fills may target the same obligation cell. For example, `get_cv x step` in a priority-chain
domain might need 5 fills: one per priority level (reset, load, count-up, count-down, preserve),
each with appropriate guards.

Declare all variables in the `variables` field of the tool call. Each variable needs a name and sort matching the signature.
Use the exact helper functions shown in the skeleton's Imports section.
Do NOT use raw constructors like `FnApp(...)` -- always use the helpers (`app(...)`, `eq(...)`, etc.).

Call `submit_axiom_fills` with your analysis and fills array. Do NOT return code."""
