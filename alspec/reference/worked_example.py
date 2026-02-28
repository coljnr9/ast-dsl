"""Section 6: Worked Example — reads from the golden bug-tracker spec.

The golden file golden/bug-tracker.py is the single source of truth.
Its docstring contains the pedagogical analysis; its code is the spec.
This module renders it as a prompt section.
"""

from pathlib import Path


def render() -> str:
    golden_path = Path(__file__).resolve().parent.parent.parent / "golden" / "bug-tracker.py"
    source = golden_path.read_text()
    return (
        "## 6. Worked Example: Bug Tracker with Ticket Store\n\n"
        "The following is a complete, verified specification that scores 1.00 health\n"
        "with 0 errors and 0 warnings. Study the docstring for the methodology,\n"
        "then study the code for the patterns. Your output should follow this structure.\n\n"
        f"```python\n{source}```"
    )
