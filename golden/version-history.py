"""
### Step 1: Identify Sorts
We need to model the domain of a version control system for a single document.
- `Content`: Opaque text payload. (**atomic**)
- `VersionId`: Opaque identifier for versions. (**atomic**)
- `Diff`: Opaque representation of changes. (**atomic**)
- `Repo`: The central domain object holding a finite map of versions. (**atomic**)

### Step 2: Classify Functions and Predicates
**Constructors of `Repo`**:
- `init : Content × VersionId → Repo` (Starts the repository with a first commit to avoid an empty-content state).
- `commit : Repo × Content × VersionId → Repo` (Records a new version and updates the current pointer).
- `revert : Repo × VersionId → Repo` (Restores current content to a historic version).

**Uninterpreted**:
- `compute_diff : Content × Content → Diff` (Actual logic to compute diffs is left abstract).

**Observers of `Repo`**:
- `current_content : Repo → Content` (total - points to active content).
- `current_version : Repo → VersionId` (total - points to active version).
- `get_content : Repo × VersionId →? Content` (partial - internal helper to retrieve historic content).
- `diff : Repo × VersionId × VersionId →? Diff` (partial - specific operation requested, relies on historic content).

**Predicates**:
- `eq_id : VersionId × VersionId` (Helper for key equality).
- `has_version : Repo × VersionId` (Predicate observer, checks if version exists).

### Step 3: Axiom Obligation Table
Total expected axioms: 31.
1-3. `eq_id`: reflexivity, symmetry, transitivity.

**Predicate Observer `has_version`** (4 axioms)
- × `init`: `has_version(init(c, v), v2) ⇔ eq_id(v, v2)`
- × `commit` (hit): `eq_id(v, v2) ⇒ has_version(...)`
- × `commit` (miss): `¬eq_id(v, v2) ⇒ (has_version(...) ⇔ has_version(r, v2))`
- × `revert`: Universal preservation `has_version(...) ⇔ has_version(r, v2)`

**Observer `current_content`** (4 axioms)
- × `init`: returns `c`.
- × `commit`: returns `c`.
- × `revert` (hit - version exists): returns `get_content(r, v)`.
- × `revert` (miss - version doesn't exist): no-op, returns `current_content(r)`.

**Observer `current_version`** (4 axioms)
- × `init`: returns `v`.
- × `commit`: returns `v`.
- × `revert` (hit): returns `v`.
- × `revert` (miss): returns `current_version(r)`.

**Observer `get_content` (Partial)** (5 axioms)
- × `init` (hit): returns `c`.
- × `init` (miss): explicit undefinedness (version not in fresh repo).
- × `commit` (hit): returns `c`.
- × `commit` (miss): delegates `get_content(r, v2)`.
- × `revert`: Universal preservation `get_content(r, v2)`.

**Observer `diff` (Doubly Partial, 2 keys)** (11 axioms)
Axioms must be split based on the combination of `v1` and `v2`.
- × `init` (both hit): returns `compute_diff(c, c)`.
- × `init` (hit/miss, miss/hit, miss/miss): explicit undefinedness (version not in fresh repo).
- × `commit` (both hit): returns `compute_diff(c, c)`.
- × `commit` (hit for v1, miss for v2): guarded by `has_version(r, v2)`, returns `compute_diff(c, get_content(r, v2))`. No-version: explicit undefinedness.
- × `commit` (miss for v1, hit for v2): guarded by `has_version(r, v1)`, returns `compute_diff(get_content(r, v1), c)`. No-version: explicit undefinedness.
- × `commit` (both miss): delegates `diff(r, v1, v2)`.
- × `revert`: Universal preservation `diff(r, v1, v2)`.
"""

from alspec import (
    Axiom, Conjunction, Definedness, Disjunction, Implication, Negation, PredApp,
    Signature, Spec, atomic, fn, pred, var, app, const, eq, forall, iff
)

def version_history_spec() -> Spec:
    # Variables for axioms
    r = var("r", "Repo")
    c = var("c", "Content")
    v = var("v", "VersionId")    # Main constructor key
    v1 = var("v1", "VersionId")  # First diff key
    v2 = var("v2", "VersionId")  # Observer key or Second diff key
    v3 = var("v3", "VersionId")  # For transitivity

    sig = Signature(
        sorts={
            "Content": atomic("Content"),
            "VersionId": atomic("VersionId"),
            "Diff": atomic("Diff"),
            "Repo": atomic("Repo"),
        },
        functions={
            # Constructors
            "init": fn("init", [("c", "Content"), ("v", "VersionId")], "Repo"),
            "commit": fn("commit", [("r", "Repo"), ("c", "Content"), ("v", "VersionId")], "Repo"),
            "revert": fn("revert", [("r", "Repo"), ("v", "VersionId")], "Repo"),
            
            # Uninterpreted
            "compute_diff": fn("compute_diff", [("c1", "Content"), ("c2", "Content")], "Diff"),
            
            # Observers
            "current_content": fn("current_content", [("r", "Repo")], "Content"),
            "current_version": fn("current_version", [("r", "Repo")], "VersionId"),
            "get_content": fn("get_content", [("r", "Repo"), ("v", "VersionId")], "Content", total=False),
            "diff": fn("diff", [("r", "Repo"), ("v1", "VersionId"), ("v2", "VersionId")], "Diff", total=False),
        },
        predicates={
            "eq_id": pred("eq_id", [("v1", "VersionId"), ("v2", "VersionId")]),
            "has_version": pred("has_version", [("r", "Repo"), ("v", "VersionId")]),
        }
    )

    axioms = (
        # -- Basis: eq_id --
        Axiom("eq_id_refl", forall([v], PredApp("eq_id", (v, v)))),
        Axiom("eq_id_sym", forall([v1, v2], Implication(
            PredApp("eq_id", (v1, v2)), 
            PredApp("eq_id", (v2, v1))
        ))),
        Axiom("eq_id_trans", forall([v1, v2, v3], Implication(
            Conjunction((PredApp("eq_id", (v1, v2)), PredApp("eq_id", (v2, v3)))),
            PredApp("eq_id", (v1, v3))
        ))),

        # -- has_version --
        Axiom("has_version_init", forall([c, v, v2], iff(
            PredApp("has_version", (app("init", c, v), v2)),
            PredApp("eq_id", (v, v2))
        ))),
        Axiom("has_version_commit_hit", forall([r, c, v, v2], Implication(
            PredApp("eq_id", (v, v2)),
            PredApp("has_version", (app("commit", r, c, v), v2))
        ))),
        Axiom("has_version_commit_miss", forall([r, c, v, v2], Implication(
            Negation(PredApp("eq_id", (v, v2))),
            iff(
                PredApp("has_version", (app("commit", r, c, v), v2)),
                PredApp("has_version", (r, v2))
            )
        ))),
        Axiom("has_version_revert", forall([r, v, v2], iff(
            PredApp("has_version", (app("revert", r, v), v2)),
            PredApp("has_version", (r, v2))
        ))),

        # -- current_content --
        Axiom("current_content_init", forall([c, v], eq(
            app("current_content", app("init", c, v)), c
        ))),
        Axiom("current_content_commit", forall([r, c, v], eq(
            app("current_content", app("commit", r, c, v)), c
        ))),
        Axiom("current_content_revert_hit", forall([r, v], Implication(
            PredApp("has_version", (r, v)),
            eq(app("current_content", app("revert", r, v)), app("get_content", r, v))
        ))),
        Axiom("current_content_revert_miss", forall([r, v], Implication(
            Negation(PredApp("has_version", (r, v))),
            eq(app("current_content", app("revert", r, v)), app("current_content", r))
        ))),

        # -- current_version --
        Axiom("current_version_init", forall([c, v], eq(
            app("current_version", app("init", c, v)), v
        ))),
        Axiom("current_version_commit", forall([r, c, v], eq(
            app("current_version", app("commit", r, c, v)), v
        ))),
        Axiom("current_version_revert_hit", forall([r, v], Implication(
            PredApp("has_version", (r, v)),
            eq(app("current_version", app("revert", r, v)), v)
        ))),
        Axiom("current_version_revert_miss", forall([r, v], Implication(
            Negation(PredApp("has_version", (r, v))),
            eq(app("current_version", app("revert", r, v)), app("current_version", r))
        ))),

        # -- get_content --
        Axiom("get_content_init_hit", forall([c, v, v2], Implication(
            PredApp("eq_id", (v, v2)),
            eq(app("get_content", app("init", c, v), v2), c)
        ))),
        # Version not in freshly initialized repo — explicitly undefined
        Axiom("get_content_init_miss", forall([c, v, v2], Implication(
            Negation(PredApp("eq_id", (v, v2))),
            Negation(Definedness(app("get_content", app("init", c, v), v2)))
        ))),
        Axiom("get_content_commit_hit", forall([r, c, v, v2], Implication(
            PredApp("eq_id", (v, v2)),
            eq(app("get_content", app("commit", r, c, v), v2), c)
        ))),
        Axiom("get_content_commit_miss", forall([r, c, v, v2], Implication(
            Negation(PredApp("eq_id", (v, v2))),
            eq(
                app("get_content", app("commit", r, c, v), v2),
                app("get_content", r, v2)
            )
        ))),
        Axiom("get_content_revert", forall([r, v, v2], eq(
            app("get_content", app("revert", r, v), v2),
            app("get_content", r, v2)
        ))),

        # -- diff --
        Axiom("diff_init_hit_hit", forall([c, v, v1, v2], Implication(
            Conjunction((PredApp("eq_id", (v, v1)), PredApp("eq_id", (v, v2)))),
            eq(app("diff", app("init", c, v), v1, v2), app("compute_diff", c, c))
        ))),
        # init with one or both versions missing — undefined
        Axiom("diff_init_hit_miss", forall([c, v, v1, v2], Implication(
            Conjunction((PredApp("eq_id", (v, v1)), Negation(PredApp("eq_id", (v, v2))))),
            Negation(Definedness(app("diff", app("init", c, v), v1, v2)))
        ))),
        Axiom("diff_init_miss_hit", forall([c, v, v1, v2], Implication(
            Conjunction((Negation(PredApp("eq_id", (v, v1))), PredApp("eq_id", (v, v2)))),
            Negation(Definedness(app("diff", app("init", c, v), v1, v2)))
        ))),
        Axiom("diff_init_miss_miss", forall([c, v, v1, v2], Implication(
            Conjunction((Negation(PredApp("eq_id", (v, v1))), Negation(PredApp("eq_id", (v, v2))))),
            Negation(Definedness(app("diff", app("init", c, v), v1, v2)))
        ))),
        Axiom("diff_commit_hit_hit", forall([r, c, v, v1, v2], Implication(
            Conjunction((PredApp("eq_id", (v, v1)), PredApp("eq_id", (v, v2)))),
            eq(app("diff", app("commit", r, c, v), v1, v2), app("compute_diff", c, c))
        ))),
        Axiom("diff_commit_hit_miss", forall([r, c, v, v1, v2], Implication(
            Conjunction((PredApp("eq_id", (v, v1)), Negation(PredApp("eq_id", (v, v2))))),
            Implication(
                PredApp("has_version", (r, v2)),
                eq(
                    app("diff", app("commit", r, c, v), v1, v2),
                    app("compute_diff", c, app("get_content", r, v2))
                )
            )
        ))),
        # v2 not in previous repo — diff undefined
        Axiom("diff_commit_hit_miss_noversion", forall([r, c, v, v1, v2], Implication(
            Conjunction((PredApp("eq_id", (v, v1)), Negation(PredApp("eq_id", (v, v2))))),
            Implication(
                Negation(PredApp("has_version", (r, v2))),
                Negation(Definedness(app("diff", app("commit", r, c, v), v1, v2)))
            )
        ))),
        Axiom("diff_commit_miss_hit", forall([r, c, v, v1, v2], Implication(
            Conjunction((Negation(PredApp("eq_id", (v, v1))), PredApp("eq_id", (v, v2)))),
            Implication(
                PredApp("has_version", (r, v1)),
                eq(
                    app("diff", app("commit", r, c, v), v1, v2),
                    app("compute_diff", app("get_content", r, v1), c)
                )
            )
        ))),
        # v1 not in previous repo — diff undefined
        Axiom("diff_commit_miss_hit_noversion", forall([r, c, v, v1, v2], Implication(
            Conjunction((Negation(PredApp("eq_id", (v, v1))), PredApp("eq_id", (v, v2)))),
            Implication(
                Negation(PredApp("has_version", (r, v1))),
                Negation(Definedness(app("diff", app("commit", r, c, v), v1, v2)))
            )
        ))),
        Axiom("diff_commit_miss_miss", forall([r, c, v, v1, v2], Implication(
            Conjunction((Negation(PredApp("eq_id", (v, v1))), Negation(PredApp("eq_id", (v, v2))))),
            eq(
                app("diff", app("commit", r, c, v), v1, v2),
                app("diff", r, v1, v2)
            )
        ))),
        Axiom("diff_revert", forall([r, v, v1, v2], eq(
            app("diff", app("revert", r, v), v1, v2),
            app("diff", r, v1, v2)
        ))),
    )

    return Spec(name="VersionHistory", signature=sig, axioms=axioms)