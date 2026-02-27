import sys
from pathlib import Path

# Add project root to sys.path so 'alspec' and 'pipeline' are found when run as a script
sys.path.append(str(Path(__file__).parent.parent))

from alspec.examples import main

if __name__ == "__main__":
    main()
