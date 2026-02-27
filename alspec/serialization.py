"""JSON serialization for many-sorted algebra types.

Every type serializes to a dict with a "type" discriminator field.
Round-trip: from_json(to_json(x)) == x for all x.
"""

from __future__ import annotations

import json
from typing import Any

from .sorts import (
    AtomicSort,
    CoproductAlt,
    CoproductSort,
    ProductField,
    ProductSort,
    SortDecl,
    SortRef,
)
from .signature import (
    FnParam,
    FnSymbol,
    PredSymbol,
    Signature,
    Totality,
)
from .terms import (
    Conjunction,
    Definedness,
    Disjunction,
    Equation,
    ExistentialQuant,
    FieldAccess,
    FnApp,
    Formula,
    Implication,
    Biconditional,
    Literal,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)
from .spec import Axiom, Spec


# ---------------------------------------------------------------------------
# Sorts
# ---------------------------------------------------------------------------


def sort_to_json(s: SortDecl) -> dict[str, Any]:
    if isinstance(s, AtomicSort):
        return {"type": "atomic", "name": s.name}
    elif isinstance(s, ProductSort):
        return {
            "type": "product",
            "name": s.name,
            "fields": [{"name": f.name, "sort": f.sort} for f in s.fields],
        }
    elif isinstance(s, CoproductSort):
        return {
            "type": "coproduct",
            "name": s.name,
            "alts": [{"tag": a.tag, "sort": a.sort} for a in s.alts],
        }
    raise TypeError(f"Unknown sort type: {type(s)}")


def sort_from_json(d: dict[str, Any]) -> SortDecl:
    t = d["type"]
    if t == "atomic":
        return AtomicSort(name=SortRef(d["name"]))
    elif t == "product":
        fields = tuple(
            ProductField(name=f["name"], sort=SortRef(f["sort"]))
            for f in d["fields"]
        )
        return ProductSort(name=SortRef(d["name"]), fields=fields)
    elif t == "coproduct":
        alts = tuple(
            CoproductAlt(tag=a["tag"], sort=SortRef(a["sort"]))
            for a in d["alts"]
        )
        return CoproductSort(name=SortRef(d["name"]), alts=alts)
    raise ValueError(f"Unknown sort type: {t}")


# ---------------------------------------------------------------------------
# Signature components
# ---------------------------------------------------------------------------


def fn_symbol_to_json(f: FnSymbol) -> dict[str, Any]:
    return {
        "type": "fn_symbol",
        "name": f.name,
        "params": [{"name": p.name, "sort": p.sort} for p in f.params],
        "result": f.result,
        "totality": f.totality.value,
    }


def fn_symbol_from_json(d: dict[str, Any]) -> FnSymbol:
    params = tuple(
        FnParam(name=p["name"], sort=SortRef(p["sort"])) for p in d["params"]
    )
    return FnSymbol(
        name=d["name"],
        params=params,
        result=SortRef(d["result"]),
        totality=Totality(d["totality"]),
    )


def pred_symbol_to_json(p: PredSymbol) -> dict[str, Any]:
    return {
        "type": "pred_symbol",
        "name": p.name,
        "params": [{"name": pp.name, "sort": pp.sort} for pp in p.params],
    }


def pred_symbol_from_json(d: dict[str, Any]) -> PredSymbol:
    params = tuple(
        FnParam(name=p["name"], sort=SortRef(p["sort"])) for p in d["params"]
    )
    return PredSymbol(name=d["name"], params=params)


def signature_to_json(sig: Signature) -> dict[str, Any]:
    return {
        "type": "signature",
        "sorts": {k: sort_to_json(v) for k, v in sig.sorts.items()},
        "functions": {k: fn_symbol_to_json(v) for k, v in sig.functions.items()},
        "predicates": {k: pred_symbol_to_json(v) for k, v in sig.predicates.items()},
    }


def signature_from_json(d: dict[str, Any]) -> Signature:
    sorts = {k: sort_from_json(v) for k, v in d["sorts"].items()}
    functions = {k: fn_symbol_from_json(v) for k, v in d["functions"].items()}
    predicates = {k: pred_symbol_from_json(v) for k, v in d["predicates"].items()}
    return Signature(sorts=sorts, functions=functions, predicates=predicates)


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def term_to_json(t: Term) -> dict[str, Any]:
    if isinstance(t, Var):
        return {"type": "var", "name": t.name, "sort": t.sort}
    elif isinstance(t, FnApp):
        return {
            "type": "fn_app",
            "fn_name": t.fn_name,
            "args": [term_to_json(a) for a in t.args],
        }
    elif isinstance(t, FieldAccess):
        return {
            "type": "field_access",
            "term": term_to_json(t.term),
            "field_name": t.field_name,
        }
    elif isinstance(t, Literal):
        return {"type": "literal", "value": t.value, "sort": t.sort}
    raise TypeError(f"Unknown term type: {type(t)}")


def term_from_json(d: dict[str, Any]) -> Term:
    t = d["type"]
    if t == "var":
        return Var(name=d["name"], sort=SortRef(d["sort"]))
    elif t == "fn_app":
        args = tuple(term_from_json(a) for a in d["args"])
        return FnApp(fn_name=d["fn_name"], args=args)
    elif t == "field_access":
        return FieldAccess(term=term_from_json(d["term"]), field_name=d["field_name"])
    elif t == "literal":
        return Literal(value=d["value"], sort=SortRef(d["sort"]))
    raise ValueError(f"Unknown term type: {t}")


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------


def formula_to_json(f: Formula) -> dict[str, Any]:
    if isinstance(f, Equation):
        return {
            "type": "equation",
            "lhs": term_to_json(f.lhs),
            "rhs": term_to_json(f.rhs),
        }
    elif isinstance(f, PredApp):
        return {
            "type": "pred_app",
            "pred_name": f.pred_name,
            "args": [term_to_json(a) for a in f.args],
        }
    elif isinstance(f, Negation):
        return {"type": "negation", "formula": formula_to_json(f.formula)}
    elif isinstance(f, Conjunction):
        return {
            "type": "conjunction",
            "conjuncts": [formula_to_json(c) for c in f.conjuncts],
        }
    elif isinstance(f, Disjunction):
        return {
            "type": "disjunction",
            "disjuncts": [formula_to_json(d) for d in f.disjuncts],
        }
    elif isinstance(f, Implication):
        return {
            "type": "implication",
            "antecedent": formula_to_json(f.antecedent),
            "consequent": formula_to_json(f.consequent),
        }
    elif isinstance(f, Biconditional):
        return {
            "type": "biconditional",
            "lhs": formula_to_json(f.lhs),
            "rhs": formula_to_json(f.rhs),
        }
    elif isinstance(f, UniversalQuant):
        return {
            "type": "forall",
            "variables": [term_to_json(v) for v in f.variables],
            "body": formula_to_json(f.body),
        }
    elif isinstance(f, ExistentialQuant):
        return {
            "type": "exists",
            "variables": [term_to_json(v) for v in f.variables],
            "body": formula_to_json(f.body),
        }
    elif isinstance(f, Definedness):
        return {"type": "definedness", "term": term_to_json(f.term)}
    raise TypeError(f"Unknown formula type: {type(f)}")


def formula_from_json(d: dict[str, Any]) -> Formula:
    t = d["type"]
    if t == "equation":
        return Equation(lhs=term_from_json(d["lhs"]), rhs=term_from_json(d["rhs"]))
    elif t == "pred_app":
        args = tuple(term_from_json(a) for a in d["args"])
        return PredApp(pred_name=d["pred_name"], args=args)
    elif t == "negation":
        return Negation(formula=formula_from_json(d["formula"]))
    elif t == "conjunction":
        return Conjunction(
            conjuncts=tuple(formula_from_json(c) for c in d["conjuncts"])
        )
    elif t == "disjunction":
        return Disjunction(
            disjuncts=tuple(formula_from_json(dd) for dd in d["disjuncts"])
        )
    elif t == "implication":
        return Implication(
            antecedent=formula_from_json(d["antecedent"]),
            consequent=formula_from_json(d["consequent"]),
        )
    elif t == "biconditional":
        return Biconditional(
            lhs=formula_from_json(d["lhs"]),
            rhs=formula_from_json(d["rhs"]),
        )
    elif t == "forall":
        variables = tuple(term_from_json(v) for v in d["variables"])
        assert all(isinstance(v, Var) for v in variables)
        return UniversalQuant(
            variables=variables,  # type: ignore[arg-type]
            body=formula_from_json(d["body"]),
        )
    elif t == "exists":
        variables = tuple(term_from_json(v) for v in d["variables"])
        assert all(isinstance(v, Var) for v in variables)
        return ExistentialQuant(
            variables=variables,  # type: ignore[arg-type]
            body=formula_from_json(d["body"]),
        )
    elif t == "definedness":
        return Definedness(term=term_from_json(d["term"]))
    raise ValueError(f"Unknown formula type: {t}")


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


def spec_to_json(sp: Spec) -> dict[str, Any]:
    return {
        "type": "spec",
        "name": sp.name,
        "signature": signature_to_json(sp.signature),
        "axioms": [
            {"label": a.label, "formula": formula_to_json(a.formula)}
            for a in sp.axioms
        ],
    }


def spec_from_json(d: dict[str, Any]) -> Spec:
    axioms = tuple(
        Axiom(label=a["label"], formula=formula_from_json(a["formula"]))
        for a in d["axioms"]
    )
    return Spec(
        name=d["name"],
        signature=signature_from_json(d["signature"]),
        axioms=axioms,
    )


# ---------------------------------------------------------------------------
# Convenience: dump / load entire specs as JSON strings
# ---------------------------------------------------------------------------


def dumps(sp: Spec) -> str:
    return json.dumps(spec_to_json(sp), indent=2)


def loads(s: str) -> Spec:
    return spec_from_json(json.loads(s))
