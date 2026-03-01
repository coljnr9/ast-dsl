#!/usr/bin/env python3
"""Fix missing trailing commas after v2 guard=None removal.

The v2 script removed ', None)' → ')' but this also removed the 
trailing comma needed to separate tuple elements.

Run: uv run python scripts/fix_worked_examples_v3.py
"""

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(".")
    wes_path = root / "alspec" / "reference" / "worked_examples.py"
    text = wes_path.read_text()

    # Find lines ending with ) that are inside a tuple (followed by
    # another ObligationCell, DesignDecision, FunctionInfo, SortInfo, or closing paren)
    # and are missing trailing commas.
    #
    # Pattern: line ends with ')' (no comma), next non-blank line starts
    # with ObligationCell/DesignDecision/FunctionInfo/SortInfo or ')'

    lines = text.split('\n')
    fixes = 0

    for i in range(len(lines) - 1):
        line = lines[i].rstrip()
        
        # Skip empty lines
        if not line.strip():
            continue
            
        # Check if line ends with ) but no comma
        if line.endswith(')') and not line.endswith(',)') and not line.endswith('),'):
            # Look at next non-empty line
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                # If next line is another dataclass call or closing paren of tuple
                if (next_line.startswith(('ObligationCell(', 'DesignDecision(',
                                          'FunctionInfo(', 'SortInfo(', ')'))
                    and not line.strip().startswith(('def ', 'class ', '#', 'return'))):
                    lines[i] = line + ','
                    fixes += 1
                break

    text = '\n'.join(lines)
    wes_path.write_text(text)

    print(f"Fixed {fixes} missing trailing commas")
    
    # Verify it compiles
    try:
        compile(text, str(wes_path), 'exec')
        print("✓ File compiles successfully")
    except SyntaxError as e:
        print(f"✗ Still has syntax error: {e}")
        return 1

    print("\nNow re-run: uv run python scripts/validate_worked_examples.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
