
import json
from alspec.reference.worked_examples import SESSION_STORE, RATE_LIMITER, DNS_ZONE, CONNECTION
from alspec.obligation import build_obligation_table
from alspec.axiom_gen import generate_mechanical_axioms, _render_formula, collect_variables
from alspec.spec import Spec

EXAMPLES = [
    ("SESSION_STORE", SESSION_STORE),
    ("RATE_LIMITER", RATE_LIMITER),
    ("DNS_ZONE", DNS_ZONE),
    ("CONNECTION", CONNECTION),
]

def extract_fills(example_name, example):
    # Execute the code to get the spec
    # The code is a string containing a function and possibly other things.
    # We need to find the function name and call it.
    
    # Simple way: the function name is usually lower_case(example_name) + "_spec"
    # But let's look at the code string to find the function name properly.
    import re
    match = re.search(r"def (\w+)\(\)", example.code)
    if not match:
        raise ValueError(f"Could not find spec function in {example_name}")
    func_name = match.group(1)
    
    local_vars = {}
    exec(example.code, local_vars)
    spec: Spec = local_vars[func_name]()
    
    sig = spec.signature
    table = build_obligation_table(sig)
    
    from alspec.axiom_gen import _select_generator
    
    mech_cells = set()
    for cell in table.cells:
        if _select_generator(cell) is not None:
             mech_cells.add((cell.observer_name, cell.constructor_name, cell.dispatch))
    
    from alspec.axiom_match import match_spec_sync
    match_report = match_spec_sync(spec, table, sig)
    
    domain_axioms = []
    # match_report.axiom_to_cells is not a field in the MatchReport dataclass.
    # We need to iterate over match_report.matches which is a tuple[AxiomCellMatch, ...].
    
    # We need to find the actual Axiom objects. match_spec_sync returns AxiomCellMatch which has axiom_label.
    # We can match by label.
    label_to_axiom = {a.label: a for a in spec.axioms}
    domain_axioms = []
    seen_labels = set()
    
    for match in match_report.matches:
        is_mech = False
        if match.cells:
            for cell in match.cells:
                if (cell.observer_name, cell.constructor_name, cell.dispatch) in mech_cells:
                    is_mech = True
                    break
        
        if not is_mech:
            if match.axiom_label in label_to_axiom and match.axiom_label not in seen_labels:
                domain_axioms.append(label_to_axiom[match.axiom_label])
                seen_labels.add(match.axiom_label)
    
    # Also include unmatched axioms
    for label in match_report.unmatched_axioms:
        if label in label_to_axiom and label not in seen_labels:
            domain_axioms.append(label_to_axiom[label])
            seen_labels.add(label)
    
    variables = {}
    fills = []
    
    for axiom in domain_axioms:
        axiom_vars = collect_variables(axiom)
        for name, sort in axiom_vars:
            variables[name] = sort
        
        short_names = {name for name, _ in axiom_vars}
        formula_str = _render_formula(axiom.formula, short_names)
        fills.append({
            "label": axiom.label,
            "formula": formula_str
        })
        
    var_list = [{"name": name, "sort": sort} for name, sort in sorted(variables.items())]
    
    print(f"\n# === {example_name} FILLS DATA ===")
    print(f"fills_variables={tuple(var_list)}")
    print(f"fills_entries={tuple(fills)}")

if __name__ == "__main__":
    for name, example in EXAMPLES:
        extract_fills(name, example)
