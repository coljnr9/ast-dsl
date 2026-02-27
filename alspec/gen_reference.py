"""Auto-generate an LLM-consumable language reference for the alspec DSL.

Structure (in order):
  1. Formal frame — signatures, well-sortedness, term/formula distinction
  2. Type grammar — Term and Formula grammars + illegal compositions
  3. Helper API — compact table, not prose
  4. Basis library — concise catalog of signature profiles + axiom names
  5. Well-formedness rules + axiom methodology
  6. Worked example — Bug Tracker (annotated)

Run: python -m alspec.gen_reference > LANGUAGE_REFERENCE.md
"""

from __future__ import annotations

from alspec.prompt import render
from alspec.reference import (
    api_reference,
    basis_catalog,
    formal_frame,
    methodology,
    type_grammar,
    worked_example,
)


def generate_reference() -> str:
    """Generate the full language reference document."""
    return render(
        "language_reference.md.j2",
        formal_frame=formal_frame.render(),
        type_grammar=type_grammar.render(),
        api_reference=api_reference.render(),
        basis_catalog=basis_catalog.render(),
        methodology=methodology.render(),
        worked_example=worked_example.render(),
    )


if __name__ == "__main__":
    print(generate_reference())
