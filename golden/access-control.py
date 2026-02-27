"""
### Axiom Obligation Analysis & Methodology

**1. Sort Identification**
- `UserId`, `ResourceId`: Atomic sorts for our entities. Keys for lookup.
- `Role`: Atomic sort representing the user's role. Modeled as an enumeration with constants.
- `System`: Atomic sort. The central domain object, mapping users to roles, and tracking granted permissions (FiniteMap pattern).

**2. Function & Predicate Classification**
- **System Constructors**:
  - `init : → System`: Creates an empty system.
  - `set_role : System × UserId × Role → System`: Assigns a role to a user.
  - `grant : System × UserId × ResourceId → System`: Grants a user direct access to a resource.
  - `revoke : System × UserId × ResourceId → System`: Revokes a user's direct access.
- **Role Constants (Constructors)**:
  - `admin : → Role`, `regular : → Role`, `none : → Role`.
- **Observers / Predicates**:
  - `get_role : System × UserId → Role` (Total observer: unassigned users default to `none` to avoid CASL undefinedness issues in derivations).
  - `has_permission : System × UserId × ResourceId` (Predicate observer: tracks explicitly granted access).
  - `can_access : System × UserId × ResourceId` (Derived predicate: Admin logic goes here).
- **Helper Predicates**:
  - `eq_user : UserId × UserId`, `eq_res : ResourceId × ResourceId` (for hit/miss key dispatch).

**3. Obligation Table & Tricky Cases / Design Decisions**
*Design Decision 1*: Using a `none` role makes `get_role` total. This allows us to safely use strong equations (like `get_role(s,u) = admin`) in the derivation of `can_access` without strict partiality concerns.
*Design Decision 2*: `can_access` is modeled as a derived predicate defined universally against `get_role` and `has_permission`, rather than mapped independently against all constructors. This is standard in CASL to prevent combinatorial axiom explosions for derived concepts.
*Design Decision 3*: `grant` and `revoke` utilize a joint primary key composed of `UserId` and `ResourceId`. Therefore, hit/miss dispatch requires taking the `Conjunction` of `eq_user` and `eq_res` in the antecedent.
*Design Decision 4*: Role constants require explicit distinctness axioms. Under loose semantics, without `admin ≠ regular` and similar, a model where all roles are equal is valid — which would make `can_access_def` grant admin access to everyone. The three distinctness axioms close this loophole.

| Observer/Predicate | Constructor | Case | Axiom Label | Expected Behavior |
|--------------------|-------------|------|-------------|-------------------|
| `eq_user` (Basis) | — | — | `eq_user_refl/sym/trans`| Equivalence relation (3 axioms) |
| `eq_res` (Basis) | — | — | `eq_res_refl/sym/trans` | Equivalence relation (3 axioms) |
| Role (Distinct.) | — | — | `role_*_ne_*` | Pairwise distinctness (3 axioms) |
| `get_role` | `init` | — | `get_role_init` | `none` |
| `get_role` | `set_role` | hit | `get_role_set_hit` | `role` |
| `get_role` | `set_role` | miss | `get_role_set_miss` | delegates |
| `get_role` | `grant` | any | `get_role_grant` | universal preservation |
| `get_role` | `revoke` | any | `get_role_revoke` | universal preservation |
| `has_permission` | `init` | — | `has_perm_init` | `false` |
| `has_permission` | `set_role` | any | `has_perm_set` | universal preservation |
| `has_permission` | `grant` | hit | `has_perm_grant_hit` | `true` (Conjunction of both equality checks) |
| `has_permission` | `grant` | miss| `has_perm_grant_miss` | delegates |
| `has_permission` | `revoke`| hit | `has_perm_revoke_hit` | `false` |
| `has_permission` | `revoke`| miss| `has_perm_revoke_miss`| delegates |
| `can_access` (derived)| — | — | `can_access_def` | `(get_role == admin) ∨ has_permission` |

**Completeness Count**:
3 (`eq_user`) + 3 (`eq_res`) + 3 (Role distinctness) + 5 (`get_role`) + 6 (`has_permission`) + 1 (`can_access`) = 21 Axioms.
"""

from alspec import (
    Axiom, Conjunction, Disjunction, Implication, Negation, PredApp,
    Signature, Spec,
    atomic, fn, pred, var, app, const, eq, forall, iff
)

def access_control_spec() -> Spec:
    # Variables
    s = var("s", "System")
    u = var("u", "UserId")
    u1 = var("u1", "UserId")
    u2 = var("u2", "UserId")
    u3 = var("u3", "UserId")
    r = var("r", "ResourceId")
    r1 = var("r1", "ResourceId")
    r2 = var("r2", "ResourceId")
    r3 = var("r3", "ResourceId")
    role = var("role", "Role")

    # Signature
    sig = Signature(
        sorts={
            "UserId": atomic("UserId"),
            "ResourceId": atomic("ResourceId"),
            "Role": atomic("Role"),
            "System": atomic("System"),
        },
        functions={
            # System constructors
            "init": fn("init", [], "System"),
            "set_role": fn("set_role", [("s", "System"), ("u", "UserId"), ("role", "Role")], "System"),
            "grant": fn("grant", [("s", "System"), ("u", "UserId"), ("r", "ResourceId")], "System"),
            "revoke": fn("revoke", [("s", "System"), ("u", "UserId"), ("r", "ResourceId")], "System"),
            
            # Role enumeration constants
            "none": fn("none", [], "Role"),
            "admin": fn("admin", [], "Role"),
            "regular": fn("regular", [], "Role"),
            
            # Observers
            "get_role": fn("get_role", [("s", "System"), ("u", "UserId")], "Role"),
        },
        predicates={
            "eq_user": pred("eq_user", [("u1", "UserId"), ("u2", "UserId")]),
            "eq_res": pred("eq_res", [("r1", "ResourceId"), ("r2", "ResourceId")]),
            "has_permission": pred("has_permission", [("s", "System"), ("u", "UserId"), ("r", "ResourceId")]),
            "can_access": pred("can_access", [("s", "System"), ("u", "UserId"), ("r", "ResourceId")]),
        }
    )

    # Axioms
    axioms = (
        # --- Helper: eq_user basis ---
        Axiom("eq_user_refl", forall([u], PredApp("eq_user", (u, u)))),
        Axiom("eq_user_sym", forall([u1, u2], Implication(
            PredApp("eq_user", (u1, u2)),
            PredApp("eq_user", (u2, u1))
        ))),
        Axiom("eq_user_trans", forall([u1, u2, u3], Implication(
            Conjunction((PredApp("eq_user", (u1, u2)), PredApp("eq_user", (u2, u3)))),
            PredApp("eq_user", (u1, u3))
        ))),

        # --- Helper: eq_res basis ---
        Axiom("eq_res_refl", forall([r], PredApp("eq_res", (r, r)))),
        Axiom("eq_res_sym", forall([r1, r2], Implication(
            PredApp("eq_res", (r1, r2)),
            PredApp("eq_res", (r2, r1))
        ))),
        Axiom("eq_res_trans", forall([r1, r2, r3], Implication(
            Conjunction((PredApp("eq_res", (r1, r2)), PredApp("eq_res", (r2, r3)))),
            PredApp("eq_res", (r1, r3))
        ))),

        # --- Role distinctness (enumeration) ---
        # Without these, a model where regular = admin is valid,
        # which would grant all regular users admin access.
        Axiom("role_admin_ne_regular", Negation(eq(const("admin"), const("regular")))),
        Axiom("role_admin_ne_none", Negation(eq(const("admin"), const("none")))),
        Axiom("role_regular_ne_none", Negation(eq(const("regular"), const("none")))),

        # --- Observer: get_role ---
        Axiom("get_role_init", forall([u], eq(
            app("get_role", const("init"), u),
            const("none")
        ))),
        Axiom("get_role_set_hit", forall([s, u1, u2, role], Implication(
            PredApp("eq_user", (u1, u2)),
            eq(app("get_role", app("set_role", s, u1, role), u2), role)
        ))),
        Axiom("get_role_set_miss", forall([s, u1, u2, role], Implication(
            Negation(PredApp("eq_user", (u1, u2))),
            eq(
                app("get_role", app("set_role", s, u1, role), u2),
                app("get_role", s, u2)
            )
        ))),
        Axiom("get_role_grant", forall([s, u1, u2, r1], eq(
            app("get_role", app("grant", s, u1, r1), u2),
            app("get_role", s, u2)
        ))),
        Axiom("get_role_revoke", forall([s, u1, u2, r1], eq(
            app("get_role", app("revoke", s, u1, r1), u2),
            app("get_role", s, u2)
        ))),

        # --- Observer: has_permission ---
        Axiom("has_perm_init", forall([u, r], Negation(
            PredApp("has_permission", (const("init"), u, r))
        ))),
        Axiom("has_perm_set", forall([s, u1, u2, role, r], iff(
            PredApp("has_permission", (app("set_role", s, u1, role), u2, r)),
            PredApp("has_permission", (s, u2, r))
        ))),
        
        # granting hit requires BOTH user and resource to match
        Axiom("has_perm_grant_hit", forall([s, u1, u2, r1, r2], Implication(
            Conjunction((PredApp("eq_user", (u1, u2)), PredApp("eq_res", (r1, r2)))),
            PredApp("has_permission", (app("grant", s, u1, r1), u2, r2))
        ))),
        # granting miss means at least one doesn't match
        Axiom("has_perm_grant_miss", forall([s, u1, u2, r1, r2], Implication(
            Negation(Conjunction((PredApp("eq_user", (u1, u2)), PredApp("eq_res", (r1, r2))))),
            iff(
                PredApp("has_permission", (app("grant", s, u1, r1), u2, r2)),
                PredApp("has_permission", (s, u2, r2))
            )
        ))),
        
        # revoking hit requires BOTH user and resource to match
        Axiom("has_perm_revoke_hit", forall([s, u1, u2, r1, r2], Implication(
            Conjunction((PredApp("eq_user", (u1, u2)), PredApp("eq_res", (r1, r2)))),
            Negation(PredApp("has_permission", (app("revoke", s, u1, r1), u2, r2)))
        ))),
        # revoking miss
        Axiom("has_perm_revoke_miss", forall([s, u1, u2, r1, r2], Implication(
            Negation(Conjunction((PredApp("eq_user", (u1, u2)), PredApp("eq_res", (r1, r2))))),
            iff(
                PredApp("has_permission", (app("revoke", s, u1, r1), u2, r2)),
                PredApp("has_permission", (s, u2, r2))
            )
        ))),

        # --- Derived Observer: can_access ---
        Axiom("can_access_def", forall([s, u, r], iff(
            PredApp("can_access", (s, u, r)),
            Disjunction((
                eq(app("get_role", s, u), const("admin")),
                PredApp("has_permission", (s, u, r))
            ))
        )))
    )

    return Spec(name="AccessControl", signature=sig, axioms=axioms)