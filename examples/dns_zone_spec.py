from alspec import (
    Axiom,
    Conjunction,
    Definedness,
    GeneratedSortInfo,
    Implication,
    Negation,
    PredApp,
    Signature,
    Spec,
    atomic,
    fn,
    pred,
    var,
    app,
    const,
    eq,
    forall,
    iff,
)


def dns_zone_spec() -> Spec:
    """DNS Zone specification.

    Models a DNS zone storing resource records indexed by (DomainName,
    RecordType). Demonstrates:

    - Dual-key dispatch: obligation table splits on eq_name (first key),
      then second-level key dispatch on eq_type (RecordType) within HIT
      cells via nested implication
    - Two sets of equality predicate basis axioms (eq_name, eq_type)
    - Doubly partial observers (get_rdata, get_ttl undefined on empty zone)
    - Nested implication guards mirroring hierarchical key dispatch
    - Guard polarity at both key levels
    - Delegation via strong equality (preserves/propagates undefinedness)
    - Existence predicate linked to observer definedness (has_record_def)

    Obligation table: 3 observers × 3 constructors = 9 base cells.
    empty cells are PLAIN (3). Keyed constructor cells split into HIT/MISS
    on eq_name (12 cells). HIT cells further split on eq_type (second-level
    key dispatch).
    Total axioms: 28 (21 obligation + 7 non-obligation).
    """
    # --- Variables ---
    z = var("z", "Zone")
    n = var("n", "DomainName")
    n2 = var("n2", "DomainName")
    n3 = var("n3", "DomainName")
    t = var("t", "RecordType")
    t2 = var("t2", "RecordType")
    t3 = var("t3", "RecordType")
    d = var("d", "RData")
    ttl = var("ttl", "Nat")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Zone": atomic("Zone"),
            "DomainName": atomic("DomainName"),
            "RecordType": atomic("RecordType"),
            "RData": atomic("RData"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Zone constructors
            "empty": fn("empty", [], "Zone"),
            "add_record": fn(
                "add_record",
                [
                    ("z", "Zone"),
                    ("n", "DomainName"),
                    ("t", "RecordType"),
                    ("d", "RData"),
                    ("ttl", "Nat"),
                ],
                "Zone",
            ),
            "remove_record": fn(
                "remove_record",
                [("z", "Zone"), ("n", "DomainName"), ("t", "RecordType")],
                "Zone",
            ),
            # Zone observers (partial — undefined when no record exists)
            "get_rdata": fn(
                "get_rdata",
                [("z", "Zone"), ("n", "DomainName"), ("t", "RecordType")],
                "RData",
                total=False,
            ),
            "get_ttl": fn(
                "get_ttl",
                [("z", "Zone"), ("n", "DomainName"), ("t", "RecordType")],
                "Nat",
                total=False,
            ),
        },
        predicates={
            "eq_name": pred(
                "eq_name", [("n1", "DomainName"), ("n2", "DomainName")]
            ),
            "eq_type": pred(
                "eq_type", [("t1", "RecordType"), ("t2", "RecordType")]
            ),
            "has_record": pred(
                "has_record",
                [("z", "Zone"), ("n", "DomainName"), ("t", "RecordType")],
            ),
        },
        generated_sorts={
            "Zone": GeneratedSortInfo(
                constructors=("empty", "add_record", "remove_record"),
                selectors={},
            ),
        },
    )

    axioms = (
        # ==================================================================
        # BASIS AXIOMS — eq_name (§9h)
        # ==================================================================
        Axiom(
            label="eq_name_refl",
            formula=forall(
                [n],
                PredApp("eq_name", (n, n)),
            ),
        ),
        Axiom(
            label="eq_name_sym",
            formula=forall(
                [n, n2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    PredApp("eq_name", (n2, n)),
                ),
            ),
        ),
        Axiom(
            label="eq_name_trans",
            formula=forall(
                [n, n2, n3],
                Implication(
                    Conjunction((
                        PredApp("eq_name", (n, n2)),
                        PredApp("eq_name", (n2, n3)),
                    )),
                    PredApp("eq_name", (n, n3)),
                ),
            ),
        ),
        # ==================================================================
        # BASIS AXIOMS — eq_type (§9h)
        # ==================================================================
        Axiom(
            label="eq_type_refl",
            formula=forall(
                [t],
                PredApp("eq_type", (t, t)),
            ),
        ),
        Axiom(
            label="eq_type_sym",
            formula=forall(
                [t, t2],
                Implication(
                    PredApp("eq_type", (t, t2)),
                    PredApp("eq_type", (t2, t)),
                ),
            ),
        ),
        Axiom(
            label="eq_type_trans",
            formula=forall(
                [t, t2, t3],
                Implication(
                    Conjunction((
                        PredApp("eq_type", (t, t2)),
                        PredApp("eq_type", (t2, t3)),
                    )),
                    PredApp("eq_type", (t, t3)),
                ),
            ),
        ),
        # ==================================================================
        # PLAIN CELLS — empty (base cases)
        # ==================================================================
        # Cell 1: get_rdata × empty — undefined (no records in empty zone)
        Axiom(
            label="get_rdata_empty",
            formula=forall(
                [n, t],
                Negation(
                    Definedness(app("get_rdata", const("empty"), n, t))
                ),
            ),
        ),
        # Cell 6: get_ttl × empty — undefined
        Axiom(
            label="get_ttl_empty",
            formula=forall(
                [n, t],
                Negation(
                    Definedness(app("get_ttl", const("empty"), n, t))
                ),
            ),
        ),
        # Cell 11: has_record × empty — no records
        Axiom(
            label="has_record_empty",
            formula=forall(
                [n, t],
                Negation(
                    PredApp("has_record", (const("empty"), n, t))
                ),
            ),
        ),
        # ==================================================================
        # get_rdata × add_record
        # First-level key dispatch on eq_name (from obligation table).
        # Second-level key dispatch on eq_type (within HIT cells, via
        # nested implication — both DomainName and RecordType are key
        # sorts with equality predicates).
        # ==================================================================
        # Cell 2a: HIT(name) + HIT(type) → return new data
        Axiom(
            label="get_rdata_add_hit_type_hit",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        PredApp("eq_type", (t, t2)),
                        eq(
                            app("get_rdata", app("add_record", z, n, t, d, ttl), n2, t2),
                            d,
                        ),
                    ),
                ),
            ),
        ),
        # Cell 2b: HIT(name) + MISS(type) → delegate (strong equality)
        Axiom(
            label="get_rdata_add_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        Negation(PredApp("eq_type", (t, t2))),
                        eq(
                            app("get_rdata", app("add_record", z, n, t, d, ttl), n2, t2),
                            app("get_rdata", z, n2, t2),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 3: MISS(name) → delegate unconditionally (strong equality)
        Axiom(
            label="get_rdata_add_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    Negation(PredApp("eq_name", (n, n2))),
                    eq(
                        app("get_rdata", app("add_record", z, n, t, d, ttl), n2, t2),
                        app("get_rdata", z, n2, t2),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # get_rdata × remove_record
        # ==================================================================
        # Cell 4a: HIT(name) + HIT(type) → undefined (record removed)
        Axiom(
            label="get_rdata_remove_hit_type_hit",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        PredApp("eq_type", (t, t2)),
                        Negation(
                            Definedness(
                                app("get_rdata", app("remove_record", z, n, t), n2, t2)
                            )
                        ),
                    ),
                ),
            ),
        ),
        # Cell 4b: HIT(name) + MISS(type) → delegate
        Axiom(
            label="get_rdata_remove_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        Negation(PredApp("eq_type", (t, t2))),
                        eq(
                            app("get_rdata", app("remove_record", z, n, t), n2, t2),
                            app("get_rdata", z, n2, t2),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 5: MISS(name) → delegate
        Axiom(
            label="get_rdata_remove_miss",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    Negation(PredApp("eq_name", (n, n2))),
                    eq(
                        app("get_rdata", app("remove_record", z, n, t), n2, t2),
                        app("get_rdata", z, n2, t2),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # get_ttl × add_record (parallel structure to get_rdata)
        # ==================================================================
        # Cell 7a: HIT(name) + HIT(type) → return new TTL
        Axiom(
            label="get_ttl_add_hit_type_hit",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        PredApp("eq_type", (t, t2)),
                        eq(
                            app("get_ttl", app("add_record", z, n, t, d, ttl), n2, t2),
                            ttl,
                        ),
                    ),
                ),
            ),
        ),
        # Cell 7b: HIT(name) + MISS(type) → delegate
        Axiom(
            label="get_ttl_add_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        Negation(PredApp("eq_type", (t, t2))),
                        eq(
                            app("get_ttl", app("add_record", z, n, t, d, ttl), n2, t2),
                            app("get_ttl", z, n2, t2),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 8: MISS(name) → delegate
        Axiom(
            label="get_ttl_add_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    Negation(PredApp("eq_name", (n, n2))),
                    eq(
                        app("get_ttl", app("add_record", z, n, t, d, ttl), n2, t2),
                        app("get_ttl", z, n2, t2),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # get_ttl × remove_record (parallel structure to get_rdata)
        # ==================================================================
        # Cell 9a: HIT(name) + HIT(type) → undefined
        Axiom(
            label="get_ttl_remove_hit_type_hit",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        PredApp("eq_type", (t, t2)),
                        Negation(
                            Definedness(
                                app("get_ttl", app("remove_record", z, n, t), n2, t2)
                            )
                        ),
                    ),
                ),
            ),
        ),
        # Cell 9b: HIT(name) + MISS(type) → delegate
        Axiom(
            label="get_ttl_remove_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        Negation(PredApp("eq_type", (t, t2))),
                        eq(
                            app("get_ttl", app("remove_record", z, n, t), n2, t2),
                            app("get_ttl", z, n2, t2),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 10: MISS(name) → delegate
        Axiom(
            label="get_ttl_remove_miss",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    Negation(PredApp("eq_name", (n, n2))),
                    eq(
                        app("get_ttl", app("remove_record", z, n, t), n2, t2),
                        app("get_ttl", z, n2, t2),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # has_record × add_record
        # ==================================================================
        # Cell 12a: HIT(name) + HIT(type) → true (record exists)
        Axiom(
            label="has_record_add_hit_type_hit",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        PredApp("eq_type", (t, t2)),
                        PredApp(
                            "has_record",
                            (app("add_record", z, n, t, d, ttl), n2, t2),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 12b: HIT(name) + MISS(type) → delegate
        Axiom(
            label="has_record_add_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        Negation(PredApp("eq_type", (t, t2))),
                        iff(
                            PredApp(
                                "has_record",
                                (app("add_record", z, n, t, d, ttl), n2, t2),
                            ),
                            PredApp("has_record", (z, n2, t2)),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 13: MISS(name) → delegate
        Axiom(
            label="has_record_add_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                Implication(
                    Negation(PredApp("eq_name", (n, n2))),
                    iff(
                        PredApp(
                            "has_record",
                            (app("add_record", z, n, t, d, ttl), n2, t2),
                        ),
                        PredApp("has_record", (z, n2, t2)),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # has_record × remove_record
        # ==================================================================
        # Cell 14a: HIT(name) + HIT(type) → false (record removed)
        Axiom(
            label="has_record_remove_hit_type_hit",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        PredApp("eq_type", (t, t2)),
                        Negation(
                            PredApp(
                                "has_record",
                                (app("remove_record", z, n, t), n2, t2),
                            )
                        ),
                    ),
                ),
            ),
        ),
        # Cell 14b: HIT(name) + MISS(type) → delegate
        Axiom(
            label="has_record_remove_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    PredApp("eq_name", (n, n2)),
                    Implication(
                        Negation(PredApp("eq_type", (t, t2))),
                        iff(
                            PredApp(
                                "has_record",
                                (app("remove_record", z, n, t), n2, t2),
                            ),
                            PredApp("has_record", (z, n2, t2)),
                        ),
                    ),
                ),
            ),
        ),
        # Cell 15: MISS(name) → delegate
        Axiom(
            label="has_record_remove_miss",
            formula=forall(
                [z, n, n2, t, t2],
                Implication(
                    Negation(PredApp("eq_name", (n, n2))),
                    iff(
                        PredApp(
                            "has_record",
                            (app("remove_record", z, n, t), n2, t2),
                        ),
                        PredApp("has_record", (z, n2, t2)),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — has_record (non-obligation)
        # Explicitly links the membership predicate to observer definedness:
        # a record exists at (name, type) iff get_rdata is defined there.
        # The obligation table still requires the per-constructor axioms
        # above — this definition provides the conceptual meaning but does
        # not substitute for obligation coverage.
        # ==================================================================
        Axiom(
            label="has_record_def",
            formula=forall(
                [z, n, t],
                iff(
                    PredApp("has_record", (z, n, t)),
                    Definedness(app("get_rdata", z, n, t)),
                ),
            ),
        ),
    )

    return Spec(name="DnsZone", signature=sig, axioms=axioms)
