"""
### Step 1: Identify Sorts
- `Name`: An opaque identifier acting as the key for phone book entries. (atomic)
- `Number`: An opaque identifier representing the associated phone number. (atomic)
- `PhoneBook`: The central collection mapping Names to Numbers. (atomic)

### Step 2: Classify Functions and Predicates
**Constructors (build PhoneBooks):**
- `empty : → PhoneBook`: Creates a new, empty phone book.
- `add : PhoneBook × Name × Number → PhoneBook`: Adds or updates a name-to-number mapping.
- `remove : PhoneBook × Name → PhoneBook`: Removes a mapping from the phone book.

**Observers (query the PhoneBook):**
- `lookup : PhoneBook × Name →? Number`: Queries the number for a given name. This is **partial**, as it is undefined if the name is not present in the phone book.

**Predicates:**
- `eq_name : Name × Name`: A key-equality helper predicate essential for dispatching hit/miss cases internally during `add` and `remove`.

### Step 3: Axiom Obligation Table
Observer: `lookup` (partial)
Constructors: `empty`, `add`, `remove`
Dispatch: Because `lookup` searches by `Name`, and both `add` and `remove` take a `Name` key, we have hit and miss branches tied to `eq_name(n, n2)`.

| Observer | Constructor | Case | Axiom Label | Behavior |
|----------|-------------|------|-------------|----------|
| `eq_name` | — | — | `eq_name_refl` | reflexivity |
| `eq_name` | — | — | `eq_name_sym` | symmetry |
| `eq_name` | — | — | `eq_name_trans` | transitivity |
| `lookup` | `empty` | — | *(omitted)* | Undefined (no names in empty book). |
| `lookup` | `add` | hit | `lookup_add_hit` | Returns the newly added `Number`. |
| `lookup` | `add` | miss | `lookup_add_miss` | Delegates to `lookup(pb, ...)` |
| `lookup` | `remove` | hit | *(omitted)* | Undefined (name just removed). |
| `lookup` | `remove` | miss | `lookup_remove_miss`| Delegates to `lookup(pb, ...)` |

### Step 4: Design Decisions & Tricky Cases
- **Undefinedness representation**: By omitting the `empty` constructor case and the `remove` hit case, we correctly capture undefinedness. If we ask `lookup` for something we just removed, there's no axiom resolving it to a value, accurately reflecting the declared partiality (`total=False`).
- **Update via Add**: Standard finite-map patterns handle key reassignment automatically through the `add` operator — a new `add` over an existing key will naturally short-circuit and shadow previous writes due to the structural recursive matching on the outermost term.
- **Total vs Partial removal**: Removing a name that does not exist remains total. Since `lookup_remove_miss` maintains previous lookups for non-matching keys, removing an already absent key essentially constructs a structurally thicker but logically identical map.

### Step 5: Completeness Count
- 3 foundational axioms for key equality (`eq_name`).
- 3 behavioral axioms mapping the single observer (`lookup`) against its applicable constructor branches (`add_hit`, `add_miss`, `remove_miss`).
- **Total Expected Axioms: 6**
"""

from alspec import (
    Axiom, Conjunction, Implication, Negation, PredApp,
    Signature, Spec, atomic, fn, pred, var, app, const, eq, forall
)

def phone_book_spec() -> Spec:
    # Variables for axioms
    pb = var("pb", "PhoneBook")
    n = var("n", "Name")
    n2 = var("n2", "Name")
    n3 = var("n3", "Name")
    num = var("num", "Number")

    sig = Signature(
        sorts={
            "Name": atomic("Name"),
            "Number": atomic("Number"),
            "PhoneBook": atomic("PhoneBook"),
        },
        functions={
            # Constructors
            "empty": fn("empty", [], "PhoneBook"),
            "add": fn("add", [("pb", "PhoneBook"), ("n", "Name"), ("num", "Number")], "PhoneBook"),
            "remove": fn("remove", [("pb", "PhoneBook"), ("n", "Name")], "PhoneBook"),
            # Observers
            "lookup": fn("lookup", [("pb", "PhoneBook"), ("n", "Name")], "Number", total=False),
        },
        predicates={
            # Helper predicate for key dispatch
            "eq_name": pred("eq_name", [("n1", "Name"), ("n2", "Name")]),
        }
    )

    axioms = (
        # ━━ eq_name basis ━━
        Axiom(
            label="eq_name_refl",
            formula=forall([n], PredApp("eq_name", (n, n)))
        ),
        Axiom(
            label="eq_name_sym",
            formula=forall([n, n2], Implication(
                PredApp("eq_name", (n, n2)),
                PredApp("eq_name", (n2, n))
            ))
        ),
        Axiom(
            label="eq_name_trans",
            formula=forall([n, n2, n3], Implication(
                Conjunction((
                    PredApp("eq_name", (n, n2)),
                    PredApp("eq_name", (n2, n3))
                )),
                PredApp("eq_name", (n, n3))
            ))
        ),

        # ━━ lookup: partial finite-map observer ━━
        # empty case OMITTED — undefined (no names in an empty phone book)

        # add hit: return the inserted number
        Axiom(
            label="lookup_add_hit",
            formula=forall([pb, n, n2, num], Implication(
                PredApp("eq_name", (n, n2)),
                eq(
                    app("lookup", app("add", pb, n, num), n2),
                    num
                )
            ))
        ),

        # add miss: delegate to the previous phone book state
        Axiom(
            label="lookup_add_miss",
            formula=forall([pb, n, n2, num], Implication(
                Negation(PredApp("eq_name", (n, n2))),
                eq(
                    app("lookup", app("add", pb, n, num), n2),
                    app("lookup", pb, n2)
                )
            ))
        ),

        # remove hit OMITTED — undefined (key has been deleted)

        # remove miss: delegate to the previous phone book state
        Axiom(
            label="lookup_remove_miss",
            formula=forall([pb, n, n2], Implication(
                Negation(PredApp("eq_name", (n, n2))),
                eq(
                    app("lookup", app("remove", pb, n), n2),
                    app("lookup", pb, n2)
                )
            ))
        ),
    )

    return Spec(name="PhoneBook", signature=sig, axioms=axioms)