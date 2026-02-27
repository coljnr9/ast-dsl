import sys
from pathlib import Path

# Add project root to sys.path so 'pipeline' and 'alspec' are found when run as a script
sys.path.append(str(Path(__file__).parent.parent))

from alspec.basis import ALL_BASIS_SPECS
from pipeline import render


def main() -> None:
    # Instantiate basis specs to pass to template
    specs = [s_fn() for s_fn in ALL_BASIS_SPECS]

    prompt = render("hello_world.md.j2", basis_specs=specs)
    print(prompt)


if __name__ == "__main__":
    main()
