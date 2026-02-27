"""Generate an LLM-consumable language reference for the alspec DSL."""

from alspec.gen_reference import generate_reference

if __name__ == "__main__":
    print(generate_reference())
