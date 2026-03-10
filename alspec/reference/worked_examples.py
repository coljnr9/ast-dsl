from __future__ import annotations

from alspec.worked_example import (
    WorkedExample, SortInfo, FunctionInfo, FunctionRole, 
    ObligationCell, CellType, DesignDecision, Pattern, RenderMode
)

# ============================================================
# Stack
# ============================================================




# ============================================================
# Counter
# ============================================================

COUNTER = WorkedExample(
    domain_name="Counter",
    summary="Demonstrates a basic accumulating value object with increment/decrement operations and reset capability",
    patterns=frozenset({Pattern.ACCUMULATION, Pattern.CROSS_SORT, Pattern.KEYLESS_AGG}),
    sorts=(
        SortInfo("Counter", "GENERATED", "Central domain object representing counter state"),
        SortInfo("Int", "ATOMIC", "Represents counter's numeric value, allowing negative numbers"),
    ),
    functions=(
        FunctionInfo("new", "-> Counter", FunctionRole.CONSTRUCTOR, "Creates a fresh counter initialized to zero"),
        FunctionInfo("inc", "Counter -> Counter", FunctionRole.CONSTRUCTOR, "Increments counter by one"),
        FunctionInfo("dec", "Counter -> Counter", FunctionRole.CONSTRUCTOR, "Decrements counter by one"),
        FunctionInfo("reset", "Counter -> Counter", FunctionRole.CONSTRUCTOR, "Resets counter back to zero"),
        FunctionInfo("get_value", "Counter -> Int", FunctionRole.OBSERVER, "Returns current counter value"),
        FunctionInfo("zero", "-> Int", FunctionRole.HELPER, "Constant representing integer zero"),
        FunctionInfo("succ", "Int -> Int", FunctionRole.HELPER, "Integer successor function"),
        FunctionInfo("pred", "Int -> Int", FunctionRole.HELPER, "Integer predecessor function"),
    ),
    obligations=(
        ObligationCell("get_value", "new", CellType.BASIS, "zero"),
        ObligationCell("get_value", "inc", CellType.PRESERVATION, "succ(get_value(c))"),
        ObligationCell("get_value", "dec", CellType.PRESERVATION, "pred(get_value(c))"),
        ObligationCell("get_value", "reset", CellType.PRESERVATION, "zero"),
    ),
    design_decisions=(
        DesignDecision("Type Selection", "Used Int instead of Nat to allow unrestricted decrements below zero"),
        DesignDecision("Reset Operation", "Modeled reset through observer behavior rather than equating to new"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    var,
)


def counter_spec() -> Spec:
    # Variables
    c = var("c", "Counter")

    # Signature definition
    sig = Signature(
        sorts={
            "Counter": atomic("Counter"),
            "Int": atomic("Int"),
        },
        functions={
            # Counter Constructors
            "new": fn("new", [], "Counter"),
            "inc": fn("inc", [("c", "Counter")], "Counter"),
            "dec": fn("dec", [("c", "Counter")], "Counter"),
            "reset": fn("reset", [("c", "Counter")], "Counter"),
            # Counter Observer
            "get_value": fn("get_value", [("c", "Counter")], "Int"),
            # Int Operations (Helpers)
            "zero": fn("zero", [], "Int"),
            "succ": fn("succ", [("n", "Int")], "Int"),
            "pred": fn("pred", [("n", "Int")], "Int"),
        },
        predicates={},
        generated_sorts={
            "Counter": GeneratedSortInfo(
                constructors=("new", "inc", "dec", "reset"),
                selectors={},
            )
        },
    )

    # Axioms defining observable behavior
    axioms = (
        # == Basic Value Operations ==
        # observer x constructor: BASIS — new counter starts at zero
        Axiom(
            label="get_value_new",
            formula=eq(
                app("get_value", const("new")),
                const("zero"),
            ),
        ),
        # observer x constructor: PRESERVATION — increment adds one to current value
        Axiom(
            label="get_value_inc",
            formula=forall(
                [c],
                eq(
                    app("get_value", app("inc", c)),
                    app("succ", app("get_value", c)),
                ),
            ),
        ),
        # observer x constructor: PRESERVATION — decrement subtracts one from current value
        Axiom(
            label="get_value_dec",
            formula=forall(
                [c],
                eq(
                    app("get_value", app("dec", c)),
                    app("pred", app("get_value", c)),
                ),
            ),
        ),
        # observer x constructor: PRESERVATION — reset forces value back to zero
        Axiom(
            label="get_value_reset",
            formula=forall(
                [c],
                eq(
                    app("get_value", app("reset", c)),
                    const("zero"),
                ),
            ),
        ),
    )

    return Spec(name="Counter", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Traffic Light
# ============================================================

TRAFFIC_LIGHT = WorkedExample(
    domain_name="Traffic Light",
    summary="Models a traffic light system using an enumeration for colors and demonstrating cyclic state transitions through enumerated cases",
    patterns=frozenset({Pattern.CROSS_SORT, Pattern.ENUMERATION, Pattern.ENUM_CASE_SPLIT, Pattern.MULTI_GEN_SORT}),
    sorts=(
        SortInfo("Color", "ENUMERATION", "Represents the possible colors (Red, Yellow, Green)"),
        SortInfo("Light", "STATE", "Represents the stateful traffic light system"),
    ),
    functions=(
        FunctionInfo("red", "→ Color", FunctionRole.CONSTRUCTOR, "Constant constructor for red state"),
        FunctionInfo("yellow", "→ Color", FunctionRole.CONSTRUCTOR, "Constant constructor for yellow state"),
        FunctionInfo("green", "→ Color", FunctionRole.CONSTRUCTOR, "Constant constructor for green state"),
        FunctionInfo("next_color", "Color → Color", FunctionRole.OBSERVER, "Determines the next color in the sequence"),
        FunctionInfo("init", "→ Light", FunctionRole.CONSTRUCTOR, "Creates initial traffic light state"),
        FunctionInfo("cycle", "Light → Light", FunctionRole.CONSTRUCTOR, "Advances light to next state"),
        FunctionInfo("color", "Light → Color", FunctionRole.OBSERVER, "Returns current color of the light"),
    ),
    obligations=(
        ObligationCell("next_color", "red", CellType.BASIS, "green"),
        ObligationCell("next_color", "green", CellType.BASIS, "yellow"),
        ObligationCell("next_color", "yellow", CellType.BASIS, "red"),
        ObligationCell("color", "init", CellType.BASIS, "red"),
        ObligationCell("color", "cycle", CellType.PRESERVATION, "next_color(color(l))"),
    ),
    design_decisions=(
        DesignDecision("Helper Function", "Split domain into sequence definition (next_color) and stateful container (cycle) for cleaner axioms"),
        DesignDecision("Sequence", "Followed standard global sequence: Red->Green->Yellow->Red"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    var,
)


def traffic_light_spec() -> Spec:
    # Variables
    l = var("l", "Light")

    sig = Signature(
        sorts={
            "Color": atomic("Color"),
            "Light": atomic("Light"),
        },
        functions={
            # Color constants (constructors)
            "red": fn("red", [], "Color"),
            "yellow": fn("yellow", [], "Color"),
            "green": fn("green", [], "Color"),
            # Color transition logic (observer/combinator)
            "next_color": fn("next_color", [("c", "Color")], "Color"),
            # Light stateful constructors
            "init": fn("init", [], "Light"),
            "cycle": fn("cycle", [("l", "Light")], "Light"),
            # Light observer
            "color": fn("color", [("l", "Light")], "Color"),
        },
        predicates={},
        generated_sorts={
            "Color": GeneratedSortInfo(
                constructors=("red", "yellow", "green"), selectors={}
            ),
            "Light": GeneratedSortInfo(constructors=("init", "cycle"), selectors={}),
        },
    )

    axioms = (
        # == Color Sequence Definition ==
        # next_color x red: BASIS — Red transitions to Green
        Axiom(
            label="next_color_red",
            formula=eq(
                app("next_color", const("red")),
                const("green"),
            ),
        ),
        # next_color x green: BASIS — Green transitions to Yellow
        Axiom(
            label="next_color_green",
            formula=eq(
                app("next_color", const("green")),
                const("yellow"),
            ),
        ),
        # next_color x yellow: BASIS — Yellow transitions to Red
        Axiom(
            label="next_color_yellow",
            formula=eq(
                app("next_color", const("yellow")),
                const("red"),
            ),
        ),
        # == Light State Management ==
        # color x init: BASIS — Initial state is Red
        Axiom(
            label="color_init",
            formula=eq(
                app("color", const("init")),
                const("red"),
            ),
        ),
        # color x cycle: PRESERVATION — Cycling advances to next color in sequence
        Axiom(
            label="color_cycle",
            formula=forall(
                [l],
                eq(
                    app("color", app("cycle", l)),
                    app("next_color", app("color", l)),
                ),
            ),
        ),
    )

    return Spec(name="TrafficLight", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Boolean Flag
# ============================================================

BOOLEAN_FLAG = WorkedExample(
    domain_name="Boolean Flag",
    summary="Models a simple feature flag with enabled/disabled state using predicates rather than booleans, demonstrating singleton pattern with constructors for state changes.",
    patterns=frozenset({Pattern.SINGLETON}),
    sorts=(
        SortInfo("Flag", "CONTAINER", "Represents the feature flag state machine"),
    ),
    functions=(
        FunctionInfo("init", "-> Flag", FunctionRole.CONSTRUCTOR, "Creates a fresh feature flag in disabled state"),
        FunctionInfo("enable", "Flag -> Flag", FunctionRole.CONSTRUCTOR, "Transitions flag to enabled state"),
        FunctionInfo("disable", "Flag -> Flag", FunctionRole.CONSTRUCTOR, "Transitions flag to disabled state"),
        FunctionInfo("is_enabled", "Flag -> Bool", FunctionRole.PREDICATE, "Checks whether flag is currently enabled"),
    ),
    obligations=(
        ObligationCell("is_enabled", "init", CellType.BASIS, "¬is_enabled(init)"),
        ObligationCell("is_enabled", "enable", CellType.KEY_HIT, "is_enabled(enable(f))"),
        ObligationCell("is_enabled", "disable", CellType.KEY_MISS, "¬is_enabled(disable(f))"),
    ),
    design_decisions=(
        DesignDecision("Initial State", "Flag starts disabled by default via init constructor"),
        DesignDecision("Predicate vs Boolean", "Using predicate is_enabled over Flag sort is more idiomatic than defining Bool sort"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    fn,
    forall,
    negation,
    pred,
    pred_app,
    var,
)


def boolean_flag_spec() -> Spec:

    f = var("f", "Flag")

    sig = Signature(
        sorts={
            "Flag": atomic("Flag"),
        },
        functions={
            # Constructors
            "init": fn("init", [], "Flag"),
            "enable": fn("enable", [("f", "Flag")], "Flag"),
            "disable": fn("disable", [("f", "Flag")], "Flag"),
        },
        predicates={
            # Observer
            "is_enabled": pred("is_enabled", [("f", "Flag")]),
        },
        generated_sorts={
            "Flag": GeneratedSortInfo(
                constructors=("init", "enable", "disable"),
                selectors={},
            )
        },
    )

    axioms = (
        # observer x constructor: BASIS - New flag starts in disabled state
        Axiom(
            label="is_enabled_init",
            formula=negation(pred_app("is_enabled", const("init"))),
        ),
        # observer x constructor: KEY_HIT - Enabling flag makes it enabled
        Axiom(
            label="is_enabled_enable",
            formula=forall([f], pred_app("is_enabled", app("enable", f))),
        ),
        # observer x constructor: KEY_MISS - Disabling flag makes it disabled
        Axiom(
            label="is_enabled_disable",
            formula=forall([f], negation(pred_app("is_enabled", app("disable", f)))),
        ),
    )

    return Spec(name="BooleanFlag", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Queue
# ============================================================

FIFO_QUEUE = WorkedExample(
    domain_name="Queue",
    summary="Demonstrates structural recursion for implementing FIFO behavior through pattern matching on queue shape, with explicit undefined cases for empty queue operations",
    patterns=frozenset({Pattern.EXPLICIT_UNDEF, Pattern.STRUCT_RECUR}),
    sorts=(
        SortInfo("Queue", "ATOMIC", "Primary domain object representing the FIFO queue"),
        SortInfo("Elem", "ATOMIC", "Type of data stored inside the queue"),
    ),
    functions=(
        FunctionInfo("empty", "→ Queue", FunctionRole.CONSTRUCTOR, "Creates an empty queue"),
        FunctionInfo("enqueue", "Queue × Elem → Queue", FunctionRole.CONSTRUCTOR, "Adds element to back of queue"),
        FunctionInfo("dequeue", "Queue →? Queue", FunctionRole.OBSERVER, "Removes element from front, undefined when empty"),
        FunctionInfo("front", "Queue →? Elem", FunctionRole.OBSERVER, "Retrieves front element, undefined when empty"),
    ),
    obligations=(
        ObligationCell("dequeue", "empty", CellType.DOMAIN, "¬def(dequeue(empty))"),
        ObligationCell("dequeue", "enqueue(empty,e)", CellType.DOMAIN, "dequeue(enqueue(empty,e)) = empty"),
        ObligationCell("dequeue", "enqueue(enqueue(q,e1),e2)", CellType.DOMAIN, "dequeue(enqueue(enqueue(q,e1),e2)) = enqueue(dequeue(enqueue(q,e1)),e2)"),
        ObligationCell("front", "empty", CellType.DOMAIN, "¬def(front(empty))"),
        ObligationCell("front", "enqueue(empty,e)", CellType.DOMAIN, "front(enqueue(empty,e)) = e"),
        ObligationCell("front", "enqueue(enqueue(q,e1),e2)", CellType.DOMAIN, "front(enqueue(enqueue(q,e1),e2)) = front(enqueue(q,e1))"),
    ),
    design_decisions=(
        DesignDecision(
            "Observer vs Selector",
            "dequeue and front are not selectors since their axioms use structural recursion rather than simple extraction"
        ),
        DesignDecision(
            "FIFO Implementation",
            "Use structural pattern matching on queue shape rather than explicit emptiness tests"
        ),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    negation,
    var,
)


def fifo_queue_spec() -> Spec:

    # Variables for axioms
    q = var("q", "Queue")
    e = var("e", "Elem")
    e1 = var("e1", "Elem")
    e2 = var("e2", "Elem")

    sig = Signature(
        sorts={
            "Queue": atomic("Queue"),
            "Elem": atomic("Elem"),
        },
        functions={
            # Constructors
            "empty": fn("empty", [], "Queue"),
            "enqueue": fn("enqueue", [("q", "Queue"), ("e", "Elem")], "Queue"),
            # Partial observers - computed not extracted
            "dequeue": fn("dequeue", [("q", "Queue")], "Queue", total=False),
            "front": fn("front", [("q", "Queue")], "Elem", total=False),
        },
        predicates={},
        generated_sorts={
            "Queue": GeneratedSortInfo(
                constructors=("empty", "enqueue"),
                selectors={},  # front/dequeue compute, don't extract
            )
        },
    )

    axioms = (
        # == Dequeue Axioms ==
        # dequeue × empty: DOMAIN - undefined for empty queue
        Axiom(
            label="dequeue_empty_undef",
            formula=negation(definedness(app("dequeue", const("empty")))),
        ),
        # dequeue × enqueue(empty): DOMAIN - single element becomes empty
        Axiom(
            label="dequeue_empty_enqueue",
            formula=forall(
                [e],
                eq(
                    app("dequeue", app("enqueue", const("empty"), e)),
                    const("empty"),
                ),
            ),
        ),
        # dequeue × enqueue(nonempty): DOMAIN - preserve FIFO order through recursion
        Axiom(
            label="dequeue_nonempty_enqueue",
            formula=forall(
                [q, e1, e2],
                eq(
                    app("dequeue", app("enqueue", app("enqueue", q, e1), e2)),
                    app("enqueue", app("dequeue", app("enqueue", q, e1)), e2),
                ),
            ),
        ),
        # == Front Axioms ==
        # front × empty: DOMAIN - undefined for empty queue
        Axiom(
            label="front_empty_undef",
            formula=negation(definedness(app("front", const("empty")))),
        ),
        # front × enqueue(empty): DOMAIN - single element is front
        Axiom(
            label="front_empty_enqueue",
            formula=forall(
                [e],
                eq(app("front", app("enqueue", const("empty"), e)), e),
            ),
        ),
        # front × enqueue(nonempty): DOMAIN - recursively access frontmost element
        Axiom(
            label="front_nonempty_enqueue",
            formula=forall(
                [q, e1, e2],
                eq(
                    app("front", app("enqueue", app("enqueue", q, e1), e2)),
                    app("front", app("enqueue", q, e1)),
                ),
            ),
        ),
    )

    return Spec(name="Queue", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Bounded Counter
# ============================================================

BOUNDED_COUNTER = WorkedExample(
    domain_name="Bounded Counter",
    summary="Demonstrates a counter with an upper bound, showcasing partial constructors through the inc operation that fails at max, and cross-sort interaction with natural numbers for counting",
    patterns=frozenset({Pattern.ACCUMULATION, Pattern.COND_DEF, Pattern.CROSS_SORT, Pattern.PARTIAL_CTOR}),
    sorts=(
        SortInfo("Counter", CellType.DOMAIN, "The central domain object modeling the counter state"),
        SortInfo("Nat", FunctionRole.HELPER, "Required for counting values and maximum limit"),
    ),
    functions=(
        FunctionInfo("zero", "-> Nat", FunctionRole.CONSTANT, "Zero constant for natural numbers"),
        FunctionInfo("suc", "Nat -> Nat", FunctionRole.CONSTRUCTOR, "Successor function for natural numbers"),
        FunctionInfo("new", "Nat -> Counter", FunctionRole.CONSTRUCTOR, "Creates new counter with given maximum capacity"),
        FunctionInfo("inc", "Counter ->? Counter", FunctionRole.CONSTRUCTOR, "Increments counter, undefined at max"),
        FunctionInfo("val", "Counter -> Nat", FunctionRole.OBSERVER, "Returns current count value"),
        FunctionInfo("max_val", "Counter -> Nat", FunctionRole.OBSERVER, "Returns maximum allowed value"),
        FunctionInfo("is_at_max", "Counter -> Bool", FunctionRole.PREDICATE, "Tests if counter has reached maximum"),
    ),
    obligations=(
        ObligationCell("def", "inc", CellType.DOMAIN, "def(inc(c)) ⇔ ¬is_at_max(c)"),
        ObligationCell("val", "new", CellType.BASIS, "val(new(m)) = zero"),
        ObligationCell("val", "inc", CellType.GUARDED, "val(inc(c)) = suc(val(c))", "¬is_at_max(c)"),
        ObligationCell("max_val", "new", CellType.BASIS, "max_val(new(m)) = m"),
        ObligationCell("max_val", "inc", CellType.PRESERVATION, "max_val(inc(c)) = max_val(c)", "¬is_at_max(c)"),
        ObligationCell("is_at_max", "new", CellType.BASIS, "is_at_max(new(m)) ⇔ eq(zero, m)"),
        ObligationCell("is_at_max", "inc", CellType.GUARDED, "is_at_max(inc(c)) ⇔ eq(suc(val(c)), max_val(c))", "¬is_at_max(c)"),
    ),
    design_decisions=(
        DesignDecision("Explicit Definedness", "inc must be explicitly undefined when counter is at max using definedness axiom"),
        DesignDecision("max_val Observer", "Required to track maximum limit for determining when inc becomes undefined"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def bounded_counter_spec() -> Spec:

    # Variables definition
    c = var("c", "Counter")
    m = var("m", "Nat")

    # Signature definition
    sig = Signature(
        sorts={
            "Counter": atomic("Counter"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Nat helpers
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            # Counter constructors
            "new": fn("new", [("m", "Nat")], "Counter"),
            "inc": fn("inc", [("c", "Counter")], "Counter", total=False),
            # Counter observers
            "val": fn("val", [("c", "Counter")], "Nat"),
            "max_val": fn("max_val", [("c", "Counter")], "Nat"),
        },
        predicates={
            "is_at_max": pred("is_at_max", [("c", "Counter")]),
        },
        generated_sorts={
            "Counter": GeneratedSortInfo(
                constructors=("new", "inc"),
                selectors={},
            )
        },
    )

    # Axioms definition
    axioms = (
        # == Definedness Axioms ==
        # inc x def: DOMAIN — inc is defined exactly when counter is not at max
        Axiom(
            label="inc_def",
            formula=forall(
                [c],
                iff(
                    definedness(app("inc", c)),
                    negation(pred_app("is_at_max", c)),
                ),
            ),
        ),
        # == Value Observer Axioms ==
        # val x new: BASIS — new counter starts at zero
        Axiom(
            label="val_new",
            formula=forall(
                [m],
                eq(app("val", app("new", m)), const("zero")),
            ),
        ),
        # val x inc: GUARDED — increment increases value by one when not at max
        Axiom(
            label="val_inc",
            formula=forall(
                [c],
                implication(
                    negation(pred_app("is_at_max", c)),
                    eq(
                        app("val", app("inc", c)),
                        app("suc", app("val", c)),
                    ),
                ),
            ),
        ),
        # == Maximum Value Observer Axioms ==
        # max_val x new: BASIS — new counter stores its maximum parameter
        Axiom(
            label="max_val_new",
            formula=forall(
                [m],
                eq(app("max_val", app("new", m)), m),
            ),
        ),
        # max_val x inc: PRESERVATION — increment preserves maximum value
        Axiom(
            label="max_val_inc",
            formula=forall(
                [c],
                implication(
                    negation(pred_app("is_at_max", c)),
                    eq(
                        app("max_val", app("inc", c)),
                        app("max_val", c),
                    ),
                ),
            ),
        ),
        # == Is At Max Predicate Axioms ==
        # is_at_max x new: BASIS — new counter at max only if max is zero
        Axiom(
            label="is_at_max_new",
            formula=forall(
                [m],
                iff(
                    pred_app("is_at_max", app("new", m)),
                    eq(const("zero"), m),
                ),
            ),
        ),
        # is_at_max x inc: GUARDED — increment reaches max when next value equals max
        Axiom(
            label="is_at_max_inc",
            formula=forall(
                [c],
                implication(
                    negation(pred_app("is_at_max", c)),
                    iff(
                        pred_app("is_at_max", app("inc", c)),
                        eq(app("suc", app("val", c)), app("max_val", c)),
                    ),
                ),
            ),
        ),
    )

    return Spec(name="BoundedCounter", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Phone Book
# ============================================================

PHONE_BOOK = WorkedExample(
    domain_name="Phone Book",
    summary="Demonstrates a key-value mapping with partial lookup observer, explicit undefinedness, and structural delegation. Features name-to-number associations with update-or-insert add semantics.",
    patterns=frozenset({Pattern.COLLECTION_CONTAINER, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.OVERWRITE, Pattern.PRESERVATION}),
    sorts=(
        SortInfo("Name", "atomic", "Opaque identifier acting as key for phone book entries"),
        SortInfo("Number", "atomic", "Associated phone number value"),
        SortInfo("PhoneBook", "container", "Central collection mapping Names to Numbers"),
    ),
    functions=(
        FunctionInfo("empty", "→ PhoneBook", FunctionRole.CONSTRUCTOR, "Creates new empty phone book"),
        FunctionInfo("add", "PhoneBook × Name × Number → PhoneBook", FunctionRole.CONSTRUCTOR, "Adds or updates name-to-number mapping"),
        FunctionInfo("remove", "PhoneBook × Name → PhoneBook", FunctionRole.CONSTRUCTOR, "Removes mapping from phone book"),
        FunctionInfo("lookup", "PhoneBook × Name →? Number", FunctionRole.PARTIAL_OBSERVER, "Queries number for given name"),
        FunctionInfo("eq_name", "Name × Name → Bool", FunctionRole.PREDICATE, "Key equality for dispatch"),
    ),
    obligations=(
        ObligationCell("eq_name", "—", CellType.BASIS, "reflexivity"),
        ObligationCell("eq_name", "—", CellType.BASIS, "symmetry"),
        ObligationCell("eq_name", "—", CellType.BASIS, "transitivity"),
        ObligationCell("lookup", "empty", CellType.UNDEF, "undefined for empty book"),
        ObligationCell("lookup", "add", CellType.KEY_HIT, "return added number", "eq_name(n,n2)"),
        ObligationCell("lookup", "add", CellType.KEY_MISS, "delegate to previous state", "!eq_name(n,n2)"),
        ObligationCell("lookup", "remove", CellType.KEY_HIT, "explicitly undefined", "eq_name(n,n2)"),
        ObligationCell("lookup", "remove", CellType.KEY_MISS, "delegate to previous state", "!eq_name(n,n2)"),
    ),
    design_decisions=(
        DesignDecision("Explicit undefinedness", "Uses Negation(Definedness(...)) to force undefinedness for empty and remove-hit cases"),
        DesignDecision("Update via Add", "Add operator handles key reassignment through natural shadowing in recursive match"),
        DesignDecision("Total removal", "Removing non-existent key remains total, producing logically identical map"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
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
            "add": fn(
                "add",
                [("pb", "PhoneBook"), ("n", "Name"), ("num", "Number")],
                "PhoneBook",
            ),
            "remove": fn("remove", [("pb", "PhoneBook"), ("n", "Name")], "PhoneBook"),
            # Observers
            "lookup": fn(
                "lookup", [("pb", "PhoneBook"), ("n", "Name")], "Number", total=False
            ),
        },
        predicates={
            # Helper predicate for key dispatch
            "eq_name": pred("eq_name", [("n1", "Name"), ("n2", "Name")]),
        },
        generated_sorts={
            "PhoneBook": GeneratedSortInfo(
                constructors=("empty", "add", "remove"),
                selectors={},
            )
        },
    )

    axioms = (
        # == Key equality basis axioms ==
        # eq_name x reflexive: BASIS — name equals itself
        Axiom(
            label="eq_name_refl",
            formula=forall([n], pred_app("eq_name", n, n)),
        ),
        # eq_name x symmetric: BASIS — if n1=n2 then n2=n1
        Axiom(
            label="eq_name_sym",
            formula=forall(
                [n, n2],
                implication(
                    pred_app("eq_name", n, n2),
                    pred_app("eq_name", n2, n),
                ),
            ),
        ),
        # eq_name x transitive: BASIS — if n1=n2 and n2=n3 then n1=n3
        Axiom(
            label="eq_name_trans",
            formula=forall(
                [n, n2, n3],
                implication(
                    conjunction(pred_app("eq_name", n, n2),
                            pred_app("eq_name", n2, n3)),
                    pred_app("eq_name", n, n3),
                ),
            ),
        ),
        # == Lookup behavior axioms ==
        # lookup x empty: UNDEF — empty phone book has no entries
        Axiom(
            label="lookup_empty",
            formula=forall(
                [n],
                negation(
                    definedness(
                        app("lookup", const("empty"), n),
                    )
                ),
            ),
        ),
        # lookup x add: KEY_HIT — return the newly inserted number
        Axiom(
            label="lookup_add_hit",
            formula=forall(
                [pb, n, n2, num],
                implication(
                    pred_app("eq_name", n, n2),
                    eq(app("lookup", app("add", pb, n, num), n2), num),
                ),
            ),
        ),
        # lookup x add: KEY_MISS — delegate to previous phone book state
        Axiom(
            label="lookup_add_miss",
            formula=forall(
                [pb, n, n2, num],
                implication(
                    negation(pred_app("eq_name", n, n2)),
                    eq(
                        app("lookup", app("add", pb, n, num), n2),
                        app("lookup", pb, n2),
                    ),
                ),
            ),
        ),
        # lookup x remove: KEY_HIT — removed key is explicitly undefined
        Axiom(
            label="lookup_remove_hit",
            formula=forall(
                [pb, n, n2],
                implication(
                    pred_app("eq_name", n, n2),
                    negation(definedness(app("lookup", app("remove", pb, n), n2))),
                ),
            ),
        ),
        # lookup x remove: KEY_MISS — delegate to previous phone book state
        Axiom(
            label="lookup_remove_miss",
            formula=forall(
                [pb, n, n2],
                implication(
                    negation(pred_app("eq_name", n, n2)),
                    eq(
                        app("lookup", app("remove", pb, n), n2),
                        app("lookup", pb, n2),
                    ),
                ),
            ),
        ),
    )

    return Spec(name="PhoneBook", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Temperature Sensor
# ============================================================

TEMPERATURE_SENSOR = WorkedExample(
    domain_name="Temperature Sensor",
    summary="Demonstrates a single-value recording mechanism with explicit undefined state handling and selector extraction, where new values unconditionally overwrite old ones",
    patterns=frozenset({Pattern.SEL_EXTRACT, Pattern.EXPLICIT_UNDEF}),
    sorts=(
        SortInfo("Sensor", "carrier", "Primary sort representing the mutable state of the sensor"),
        SortInfo("Temp", "atomic", "Opaque temperature values recorded by the sensor"),
    ),
    functions=(
        FunctionInfo("init", "→ Sensor", FunctionRole.CONSTRUCTOR, "Creates new uninitialized sensor"),
        FunctionInfo("record", "Sensor × Temp → Sensor", FunctionRole.CONSTRUCTOR, "Overwrites sensor's current record"),
        FunctionInfo("read", "Sensor →? Temp", FunctionRole.PARTIAL_OBSERVER, "Retrieves current temperature if exists"),
        FunctionInfo("has_reading", "Sensor → Bool", FunctionRole.PREDICATE, "Guard for read operation"),
    ),
    obligations=(
        ObligationCell("has_reading", "init", CellType.BASIS, "false"),
        ObligationCell("has_reading", "record", CellType.BASIS, "true"),
        ObligationCell("read", "init", CellType.UNDEF, "undefined"),
        ObligationCell("read", "record", CellType.SELECTOR_EXTRACT, "t"),
    ),
    design_decisions=(
        DesignDecision(
            "State Replacement",
            "Making read only introspect the outermost record constructor ensures old values are completely invisible"
        ),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    negation,
    pred,
    pred_app,
    var,
)


def temperature_sensor_spec() -> Spec:
    # Variables for axioms
    s = var("s", "Sensor")
    t = var("t", "Temp")

    # Define the domain signature
    sig = Signature(
        sorts={
            "Sensor": atomic("Sensor"),
            "Temp": atomic("Temp"),
        },
        functions={
            "init": fn("init", [], "Sensor"),
            "record": fn("record", [("s", "Sensor"), ("t", "Temp")], "Sensor"),
            "read": fn("read", [("s", "Sensor")], "Temp", total=False),
        },
        predicates={
            "has_reading": pred("has_reading", [("s", "Sensor")]),
        },
        generated_sorts={
            "Sensor": GeneratedSortInfo(
                constructors=("init", "record"),
                selectors={"record": {"read": "Temp"}},
            )
        },
    )

    # Fulfill the obligation table
    axioms = (
        # == Base Cases ==
        # has_reading x init: BASIS — newly initialized sensors have no reading
        Axiom(
            label="has_reading_init",
            formula=negation(pred_app("has_reading", const("init"))),
        ),
        # has_reading x record: BASIS — recording always creates a valid reading
        Axiom(
            label="has_reading_record",
            formula=forall([s, t], pred_app("has_reading", app("record", s, t))),
        ),
        # == Partiality ==
        # read x init: UNDEF — cannot read from uninitialized sensor
        Axiom(
            label="read_init_undef",
            formula=negation(definedness(app("read", const("init")))),
        ),
        # == Selectors ==
        # read x record: SELECTOR_EXTRACT — extract temperature from record constructor
        Axiom(
            label="read_record",
            formula=forall([s, t], eq(app("read", app("record", s, t)), t)),
        ),
    )

    return Spec(name="TemperatureSensor", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Thermostat
# ============================================================

THERMOSTAT = WorkedExample(
    domain_name="Thermostat",
    summary="Models a thermostat with target/current temperatures and heater state, demonstrating selector extraction, biconditional characterization of derived state (heater_on), and preservation of unchanged values across operations.",
    patterns=frozenset({Pattern.SEL_EXTRACT, Pattern.BICOND_CHAR, Pattern.PRESERVATION, Pattern.UNINTERP_FN}),
    sorts=(
        SortInfo("Temp", "atomic", "Opaque temperature values that can only be compared via lt predicate"),
        SortInfo("Thermostat", "atomic", "Device state controlled through constructors/observers axioms"),
    ),
    functions=(
        FunctionInfo("new", "→ Thermostat", FunctionRole.CONSTRUCTOR, "Creates initial thermostat state"),
        FunctionInfo("set_target", "Thermostat × Temp → Thermostat", FunctionRole.CONSTRUCTOR, "Updates target temperature"),
        FunctionInfo("read_temp", "Thermostat × Temp → Thermostat", FunctionRole.CONSTRUCTOR, "Records new current temperature"),
        FunctionInfo("get_target", "Thermostat → Temp", FunctionRole.SELECTOR, "Reads target temperature"),
        FunctionInfo("get_current", "Thermostat → Temp", FunctionRole.SELECTOR, "Reads current temperature"),
        FunctionInfo("heater_on", "Thermostat", FunctionRole.PREDICATE, "Derived state: true when current < target"),
        FunctionInfo("init_target", "→ Temp", FunctionRole.CONSTANT, "Initial target temperature"),
        FunctionInfo("init_current", "→ Temp", FunctionRole.CONSTANT, "Initial current temperature"),
        FunctionInfo("lt", "Temp × Temp", FunctionRole.HELPER, "Uninterpreted strict less-than on temperatures"),
    ),
    obligations=(
        ObligationCell("get_target", "new", CellType.BASIS, "init_target"),
        ObligationCell("get_target", "set_target", CellType.SELECTOR_EXTRACT, "t"),
        ObligationCell("get_target", "read_temp", CellType.PRESERVATION, "get_target(th)"),
        ObligationCell("get_current", "new", CellType.BASIS, "init_current"),
        ObligationCell("get_current", "set_target", CellType.PRESERVATION, "get_current(th)"),
        ObligationCell("get_current", "read_temp", CellType.SELECTOR_EXTRACT, "r"),
        ObligationCell("heater_on", "new", CellType.BASIS, "lt(init_current, init_target)"),
        ObligationCell("heater_on", "set_target", CellType.DOMAIN, "lt(get_current(th), t)"),
        ObligationCell("heater_on", "read_temp", CellType.DOMAIN, "lt(r, get_target(th))"),
    ),
    design_decisions=(
        DesignDecision("Observer totality", "Since get_target and get_current are total, we need init_target and init_current constants to define their values on new()"),
        DesignDecision("Heater state", "heater_on is modeled as a derived predicate rather than mutable state, with activation rule encoded in axioms"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    iff,
    pred,
    pred_app,
    var,
)


def thermostat_spec() -> Spec:
    # Variables
    th = var("th", "Thermostat")
    t = var("t", "Temp")
    r = var("r", "Temp")

    sig = Signature(
        sorts={
            "Temp": atomic("Temp"),
            "Thermostat": atomic("Thermostat"),
        },
        functions={
            # Constructors
            "new": fn("new", [], "Thermostat"),
            "set_target": fn(
                "set_target", [("th", "Thermostat"), ("t", "Temp")], "Thermostat"
            ),
            "read_temp": fn(
                "read_temp", [("th", "Thermostat"), ("r", "Temp")], "Thermostat"
            ),
            # Observers
            "get_target": fn("get_target", [("th", "Thermostat")], "Temp"),
            "get_current": fn("get_current", [("th", "Thermostat")], "Temp"),
            # Initial constants
            "init_target": fn("init_target", [], "Temp"),
            "init_current": fn("init_current", [], "Temp"),
        },
        predicates={
            "lt": pred("lt", [("x", "Temp"), ("y", "Temp")]),
            "heater_on": pred("heater_on", [("th", "Thermostat")]),
        },
        generated_sorts={
            "Thermostat": GeneratedSortInfo(
                constructors=("new", "set_target", "read_temp"),
                selectors={
                    "set_target": {"get_target": "Temp"},
                    "read_temp": {"get_current": "Temp"},
                },
            )
        },
    )

    axioms = (
        # == Target Temperature Axioms ==
        # get_target x new: BASIS — Initial target temperature
        Axiom(
            label="get_target_new",
            formula=eq(app("get_target", const("new")), const("init_target")),
        ),
        # get_target x set_target: SELECTOR_EXTRACT — Extract new target value
        Axiom(
            label="get_target_set_target",
            formula=forall(
                [th, t],
                eq(app("get_target", app("set_target", th, t)), t),
            ),
        ),
        # get_target x read_temp: PRESERVATION — Target unchanged by reading temp
        Axiom(
            label="get_target_read_temp",
            formula=forall(
                [th, r],
                eq(app("get_target", app("read_temp", th, r)), app("get_target", th)),
            ),
        ),
        # == Current Temperature Axioms ==
        # get_current x new: BASIS — Initial current temperature
        Axiom(
            label="get_current_new",
            formula=eq(app("get_current", const("new")), const("init_current")),
        ),
        # get_current x set_target: PRESERVATION — Current unchanged by setting target
        Axiom(
            label="get_current_set_target",
            formula=forall(
                [th, t],
                eq(
                    app("get_current", app("set_target", th, t)), app("get_current", th)
                ),
            ),
        ),
        # get_current x read_temp: SELECTOR_EXTRACT — Extract new reading
        Axiom(
            label="get_current_read_temp",
            formula=forall(
                [th, r],
                eq(app("get_current", app("read_temp", th, r)), r),
            ),
        ),
        # == Heater Control Axioms ==
        # heater_on x new: BASIS — Initial heater state based on initial temperatures
        Axiom(
            label="heater_on_new",
            formula=iff(
                pred_app("heater_on", const("new")),
                pred_app("lt", const("init_current"), const("init_target")),
            ),
        ),
        # heater_on x set_target: BICOND_CHAR — Heater activates if current < new target
        Axiom(
            label="heater_on_set_target",
            formula=forall(
                [th, t],
                iff(
                    pred_app("heater_on", app("set_target", th, t)),
                    pred_app("lt", app("get_current", th), t),
                ),
            ),
        ),
        # heater_on x read_temp: BICOND_CHAR — Heater activates if new reading < target
        Axiom(
            label="heater_on_read_temp",
            formula=forall(
                [th, r],
                iff(
                    pred_app("heater_on", app("read_temp", th, r)),
                    pred_app("lt", r, app("get_target", th)),
                ),
            ),
        ),
    )

    return Spec(name="Thermostat", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Bank Account
# ============================================================

BANK_ACCOUNT = WorkedExample(
    domain_name="Bank Account",
    summary="Demonstrates partial constructor pattern for modeling failure cases (withdraw), with guarded axioms and definedness conditions to handle insufficient funds. Shows accumulation pattern for balance tracking.",
    patterns=frozenset({Pattern.ACCUMULATION, Pattern.BOTH_GUARD_POL, Pattern.COND_DEF, Pattern.KEYED_CONSTRUCTOR, Pattern.PARTIAL_CTOR}),
    sorts=(
        SortInfo("Account", "ATOMIC", "Primary carrier set for bank account state machine"),
        SortInfo("Amount", "ATOMIC", "Opaque carrier set representing money with basic arithmetic"),
    ),
    functions=(
        FunctionInfo("empty", "→ Account", FunctionRole.CONSTRUCTOR, "Initial state with zero balance"),
        FunctionInfo("deposit", "Account × Amount → Account", FunctionRole.CONSTRUCTOR, "Adds funds to account"),
        FunctionInfo("withdraw", "Account × Amount →? Account", FunctionRole.CONSTRUCTOR, "Removes funds if sufficient balance exists"),
        FunctionInfo("balance", "Account → Amount", FunctionRole.OBSERVER, "Returns current account balance"),
        FunctionInfo("zero", "→ Amount", FunctionRole.CONSTANT, "Neutral cash amount"),
        FunctionInfo("add", "Amount × Amount → Amount", FunctionRole.HELPER, "Money accumulation operator"),
        FunctionInfo("sub", "Amount × Amount → Amount", FunctionRole.HELPER, "Money reduction operator"),
        FunctionInfo("geq", "Amount × Amount → Bool", FunctionRole.PREDICATE, "Checks if first amount >= second"),
    ),
    obligations=(
        ObligationCell("balance", "empty", CellType.BASIS, "zero"),
        ObligationCell("balance", "deposit", CellType.PRESERVATION, "add(balance(a), m)"),
        ObligationCell("balance", "withdraw", CellType.GUARDED, "sub(balance(a), m)", "geq(balance(a), m)"),
        ObligationCell("withdraw", "—", CellType.DOMAIN, "geq(balance(a), m)"),
    ),
    design_decisions=(
        DesignDecision("Partial Constructor Choice", 
                      "Using withdraw as partial constructor elegantly models failure cases in algebraic formulation"),
        DesignDecision("Strong Equality Handling",
                      "Balance_withdraw axiom must be guarded to prevent unintentional totality assertion"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    pred,
    pred_app,
    var,
)


def bank_account_spec() -> Spec:

    # Variables
    a = var("a", "Account")
    m = var("m", "Amount")

    # Frame Definition
    sig = Signature(
        sorts={
            "Account": atomic("Account"),
            "Amount": atomic("Amount"),
        },
        functions={
            # Account Constructors
            "empty": fn("empty", [], "Account"),
            "deposit": fn("deposit", [("a", "Account"), ("m", "Amount")], "Account"),
            "withdraw": fn(
                "withdraw", [("a", "Account"), ("m", "Amount")], "Account", total=False
            ),
            # Account Observer
            "balance": fn("balance", [("a", "Account")], "Amount"),
            # Amount Operators (Uninterpreted basis)
            "zero": fn("zero", [], "Amount"),
            "add": fn("add", [("m1", "Amount"), ("m2", "Amount")], "Amount"),
            "sub": fn("sub", [("m1", "Amount"), ("m2", "Amount")], "Amount"),
        },
        predicates={
            "geq": pred("geq", [("m1", "Amount"), ("m2", "Amount")]),
        },
        generated_sorts={
            "Account": GeneratedSortInfo(
                constructors=("empty", "deposit", "withdraw"),
                selectors={},
            )
        },
    )

    axioms = (
        # == Basic Account Operations ==
        # balance x empty: BASIS — Initial empty account has zero balance
        Axiom(
            label="balance_empty",
            formula=eq(app("balance", const("empty")), const("zero")),
        ),
        # balance x deposit: PRESERVATION — Balance increases by deposited amount
        Axiom(
            label="balance_deposit",
            formula=forall(
                [a, m],
                eq(
                    app("balance", app("deposit", a, m)),
                    app("add", app("balance", a), m),
                ),
            ),
        ),
        # == Withdrawal Operations ==
        # withdraw domain: DOMAIN — Withdrawal only defined when sufficient funds exist
        Axiom(
            label="withdraw_definedness",
            formula=forall(
                [a, m],
                iff(
                    definedness(app("withdraw", a, m)),
                    pred_app("geq", app("balance", a), m),
                ),
            ),
        ),
        # balance x withdraw: GUARDED — Balance decreases by withdrawn amount when sufficient funds
        Axiom(
            label="balance_withdraw",
            formula=forall(
                [a, m],
                implication(
                    pred_app("geq", app("balance", a), m),
                    eq(
                        app("balance", app("withdraw", a, m)),
                        app("sub", app("balance", a), m),
                    ),
                ),
            ),
        ),
    )

    return Spec(name="BankAccount", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Door Lock
# ============================================================

DOOR_LOCK = WorkedExample(
    domain_name="Door Lock",
    summary="Demonstrates state-dependent behavior with enumerated states and guarded transitions requiring code validation",
    patterns=frozenset({Pattern.ENUMERATION, Pattern.ENUM_CASE_SPLIT, Pattern.STATE_DEPENDENT, Pattern.BOTH_GUARD_POL}),
    sorts=(
        SortInfo("Lock", "ATOMIC", "Central domain object representing lock machine state"),
        SortInfo("State", "ATOMIC", "Enumeration of lock states (locked, unlocked, open)"),
        SortInfo("Code", "ATOMIC", "Opaque security credential for validation"),
    ),
    functions=(
        FunctionInfo("locked", "→ State", FunctionRole.CONSTANT, "Enumerated lock state"),
        FunctionInfo("unlocked", "→ State", FunctionRole.CONSTANT, "Enumerated lock state"),
        FunctionInfo("open_state", "→ State", FunctionRole.CONSTANT, "Enumerated lock state"),
        FunctionInfo("new", "Code → Lock", FunctionRole.CONSTRUCTOR, "Creates new locked lock with code"),
        FunctionInfo("lock", "Lock × Code → Lock", FunctionRole.CONSTRUCTOR, "Transitions unlocked to locked if code matches"),
        FunctionInfo("unlock", "Lock × Code → Lock", FunctionRole.CONSTRUCTOR, "Transitions locked to unlocked if code matches"),
        FunctionInfo("open_door", "Lock → Lock", FunctionRole.CONSTRUCTOR, "Transitions unlocked to open"),
        FunctionInfo("close_door", "Lock → Lock", FunctionRole.CONSTRUCTOR, "Transitions open to unlocked"),
        FunctionInfo("get_state", "Lock → State", FunctionRole.OBSERVER, "Returns current lock state"),
        FunctionInfo("get_code", "Lock → Code", FunctionRole.OBSERVER, "Returns stored validation code"),
        FunctionInfo("eq_code", "Code × Code", FunctionRole.PREDICATE, "Code equality comparison"),
    ),
    obligations=(
        ObligationCell("eq_code", "—", CellType.BASIS, "Reflexivity axiom"),
        ObligationCell("eq_code", "—", CellType.BASIS, "Symmetry axiom"),
        ObligationCell("eq_code", "—", CellType.BASIS, "Transitivity axiom"),
        ObligationCell("get_code", "new", CellType.SELECTOR_EXTRACT, "Returns input code"),
        ObligationCell("get_code", "lock", CellType.PRESERVATION, "Preserves stored code"),
        ObligationCell("get_code", "unlock", CellType.PRESERVATION, "Preserves stored code"),
        ObligationCell("get_code", "open_door", CellType.PRESERVATION, "Preserves stored code"),
        ObligationCell("get_code", "close_door", CellType.PRESERVATION, "Preserves stored code"),
        ObligationCell("get_state", "new", CellType.SELECTOR_FOREIGN, "Returns locked initial state"),
        ObligationCell("get_state", "lock", CellType.KEY_HIT, "Changes unlocked to locked if code matches", "eq_code ∧ state=unlocked"),
        ObligationCell("get_state", "lock", CellType.KEY_MISS, "Preserves state if wrong code or state", "¬(hit condition)"),
        ObligationCell("get_state", "unlock", CellType.KEY_HIT, "Changes locked to unlocked if code matches", "eq_code ∧ state=locked"),
        ObligationCell("get_state", "unlock", CellType.KEY_MISS, "Preserves state if wrong code or state", "¬(hit condition)"),
        ObligationCell("get_state", "open_door", CellType.KEY_HIT, "Changes unlocked to open", "state=unlocked"),
        ObligationCell("get_state", "open_door", CellType.KEY_MISS, "Preserves state if not unlocked", "¬(state=unlocked)"),
        ObligationCell("get_state", "close_door", CellType.KEY_HIT, "Changes open to unlocked", "state=open_state"),
        ObligationCell("get_state", "close_door", CellType.KEY_MISS, "Preserves state if not open", "¬(state=open_state)"),
    ),
    design_decisions=(
        DesignDecision("State Machine Model", "Lock acts as immutable state machine where actions yield new states"),
        DesignDecision("Close Semantics", "Added close_door constructor to make system fully reachable"),
        DesignDecision("Code Retention", "Lock stores code internally to validate future operations"),
        DesignDecision("Graceful Failures", "Invalid transitions preserve current state as no-op"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def door_lock_spec() -> Spec:
    # Variables
    c = var("c", "Code")
    l = var("l", "Lock")
    c1 = var("c1", "Code")
    c2 = var("c2", "Code")
    c3 = var("c3", "Code")

    sig = Signature(
        sorts={
            "Code": atomic("Code"),
            "State": atomic("State"),
            "Lock": atomic("Lock"),
        },
        functions={
            # Enumeration Constants for State
            "locked": fn("locked", [], "State"),
            "unlocked": fn("unlocked", [], "State"),
            "open_state": fn("open_state", [], "State"),
            # Constructors for Lock
            "new": fn("new", [("c", "Code")], "Lock"),
            "lock": fn("lock", [("l", "Lock"), ("c", "Code")], "Lock"),
            "unlock": fn("unlock", [("l", "Lock"), ("c", "Code")], "Lock"),
            "open_door": fn("open_door", [("l", "Lock")], "Lock"),
            "close_door": fn("close_door", [("l", "Lock")], "Lock"),
            # Observers for Lock
            "get_state": fn("get_state", [("l", "Lock")], "State"),
            "get_code": fn("get_code", [("l", "Lock")], "Code"),
        },
        predicates={
            "eq_code": pred("eq_code", [("c1", "Code"), ("c2", "Code")]),
        },
        generated_sorts={
            "Lock": GeneratedSortInfo(
                constructors=("new", "lock", "unlock", "open_door", "close_door"),
                selectors={"new": {"get_code": "Code"}},
            )
        },
    )

    axioms = (
        # == eq_code basis axioms ==
        # eq_code x BASIS: BASIS - Code equality is reflexive
        Axiom(
            label="eq_code_refl",
            formula=forall([c1], pred_app("eq_code", c1, c1)),
        ),
        # eq_code x BASIS: BASIS - Code equality is symmetric
        Axiom(
            label="eq_code_sym",
            formula=forall(
                [c1, c2],
                implication(
                    pred_app("eq_code", c1, c2),
                    pred_app("eq_code", c2, c1),
                ),
            ),
        ),
        # eq_code x BASIS: BASIS - Code equality is transitive
        Axiom(
            label="eq_code_trans",
            formula=forall(
                [c1, c2, c3],
                implication(
                    conjunction(pred_app("eq_code", c1, c2),
                            pred_app("eq_code", c2, c3)),
                    pred_app("eq_code", c1, c3),
                ),
            ),
        ),
        # == get_code observer axioms ==
        # get_code x new: SELECTOR_EXTRACT - New lock stores provided code
        Axiom(
            label="get_code_new",
            formula=forall([c], eq(app("get_code", app("new", c)), c)),
        ),
        # get_code x lock: PRESERVATION - Lock operation preserves stored code
        Axiom(
            label="get_code_lock",
            formula=forall(
                [l, c], eq(app("get_code", app("lock", l, c)), app("get_code", l))
            ),
        ),
        # get_code x unlock: PRESERVATION - Unlock operation preserves stored code
        Axiom(
            label="get_code_unlock",
            formula=forall(
                [l, c], eq(app("get_code", app("unlock", l, c)), app("get_code", l))
            ),
        ),
        # get_code x open_door: PRESERVATION - Opening preserves stored code
        Axiom(
            label="get_code_open_door",
            formula=forall(
                [l], eq(app("get_code", app("open_door", l)), app("get_code", l))
            ),
        ),
        # get_code x close_door: PRESERVATION - Closing preserves stored code
        Axiom(
            label="get_code_close_door",
            formula=forall(
                [l], eq(app("get_code", app("close_door", l)), app("get_code", l))
            ),
        ),
        # == get_state observer axioms ==
        # get_state x new: SELECTOR_FOREIGN - New lock starts in locked state
        Axiom(
            label="get_state_new",
            formula=forall([c], eq(app("get_state", app("new", c)), const("locked"))),
        ),
        # == Lock state transitions ==
        # get_state x lock: KEY_HIT - Lock if correct code and unlocked
        Axiom(
            label="get_state_lock_hit",
            formula=forall(
                [l, c],
                implication(
                    conjunction(pred_app("eq_code", c, app("get_code", l)),
                            eq(app("get_state", l), const("unlocked"))),
                    eq(app("get_state", app("lock", l, c)), const("locked")),
                ),
            ),
        ),
        # get_state x lock: KEY_MISS - Preserve state if wrong code or not unlocked
        Axiom(
            label="get_state_lock_miss",
            formula=forall(
                [l, c],
                implication(
                    negation(
                        conjunction(pred_app("eq_code", c, app("get_code", l)),
                                eq(app("get_state", l), const("unlocked")))
                    ),
                    eq(app("get_state", app("lock", l, c)), app("get_state", l)),
                ),
            ),
        ),
        # == Unlock state transitions ==
        # get_state x unlock: KEY_HIT - Unlock if correct code and locked
        Axiom(
            label="get_state_unlock_hit",
            formula=forall(
                [l, c],
                implication(
                    conjunction(pred_app("eq_code", c, app("get_code", l)),
                            eq(app("get_state", l), const("locked"))),
                    eq(app("get_state", app("unlock", l, c)), const("unlocked")),
                ),
            ),
        ),
        # get_state x unlock: KEY_MISS - Preserve state if wrong code or not locked
        Axiom(
            label="get_state_unlock_miss",
            formula=forall(
                [l, c],
                implication(
                    negation(
                        conjunction(pred_app("eq_code", c, app("get_code", l)),
                                eq(app("get_state", l), const("locked")))
                    ),
                    eq(app("get_state", app("unlock", l, c)), app("get_state", l)),
                ),
            ),
        ),
        # == Open/Close state transitions ==
        # get_state x open_door: KEY_HIT - Open if unlocked
        Axiom(
            label="get_state_open_door_hit",
            formula=forall(
                [l],
                implication(
                    eq(app("get_state", l), const("unlocked")),
                    eq(app("get_state", app("open_door", l)), const("open_state")),
                ),
            ),
        ),
        # get_state x open_door: KEY_MISS - Preserve state if not unlocked
        Axiom(
            label="get_state_open_door_miss",
            formula=forall(
                [l],
                implication(
                    negation(eq(app("get_state", l), const("unlocked"))),
                    eq(app("get_state", app("open_door", l)), app("get_state", l)),
                ),
            ),
        ),
        # get_state x close_door: KEY_HIT - Close to unlocked if open
        Axiom(
            label="get_state_close_door_hit",
            formula=forall(
                [l],
                implication(
                    eq(app("get_state", l), const("open_state")),
                    eq(app("get_state", app("close_door", l)), const("unlocked")),
                ),
            ),
        ),
        # get_state x close_door: KEY_MISS - Preserve state if not open
        Axiom(
            label="get_state_close_door_miss",
            formula=forall(
                [l],
                implication(
                    negation(eq(app("get_state", l), const("open_state"))),
                    eq(app("get_state", app("close_door", l)), app("get_state", l)),
                ),
            ),
        ),
    )

    return Spec(name="DoorLock", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Todo List
# ============================================================

TODO_LIST = WorkedExample(
    domain_name="Todo List",
    summary="A key-indexed collection demonstrating key dispatch patterns, partial observers for item details, and explicit undefinedness handling for removed items",
    patterns=frozenset({Pattern.BICOND_CHAR, Pattern.COLLECTION_CONTAINER, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.OVERWRITE, Pattern.PRESERVATION}),
    sorts=(
        SortInfo("ItemId", "ATOMIC", "Opaque key for lookup"),
        SortInfo("Title", "ATOMIC", "Opaque text block"),
        SortInfo("Status", "ATOMIC", "Enum representing done status"),
        SortInfo("TodoList", "CONTAINER", "Central collection storing todo items"),
    ),
    functions=(
        FunctionInfo("empty", "→ TodoList", FunctionRole.CONSTRUCTOR, "Creates empty list"),
        FunctionInfo("add_item", "TodoList × ItemId × Title → TodoList", FunctionRole.CONSTRUCTOR, "Adds new item with pending status"),
        FunctionInfo("complete_item", "TodoList × ItemId → TodoList", FunctionRole.CONSTRUCTOR, "Marks existing item as done"),
        FunctionInfo("remove_item", "TodoList × ItemId → TodoList", FunctionRole.CONSTRUCTOR, "Removes item if it exists"),
        FunctionInfo("has_item", "TodoList × ItemId", FunctionRole.PREDICATE, "Tests if item exists"),
        FunctionInfo("get_title", "TodoList × ItemId →? Title", FunctionRole.PARTIAL_OBSERVER, "Gets title if item exists"),
        FunctionInfo("get_status", "TodoList × ItemId →? Status", FunctionRole.PARTIAL_OBSERVER, "Gets status if item exists"),
        FunctionInfo("pending", "→ Status", FunctionRole.CONSTANT, "Initial status value"),
        FunctionInfo("done", "→ Status", FunctionRole.CONSTANT, "Completed status value"),
        FunctionInfo("eq_id", "ItemId × ItemId", FunctionRole.PREDICATE, "Key equality test"),
    ),
    obligations=(
        ObligationCell("eq_id", "—", CellType.BASIS, "Reflexive"),
        ObligationCell("eq_id", "—", CellType.BASIS, "Symmetric"),
        ObligationCell("eq_id", "—", CellType.BASIS, "Transitive"),
        ObligationCell("has_item", "empty", CellType.BASIS, "False"),
        ObligationCell("has_item", "add_item", CellType.KEY_HIT, "True"),
        ObligationCell("has_item", "add_item", CellType.KEY_MISS, "Delegates"),
        ObligationCell("has_item", "complete_item", CellType.PRESERVATION, "Preserves membership"),
        ObligationCell("has_item", "remove_item", CellType.KEY_HIT, "False"),
        ObligationCell("has_item", "remove_item", CellType.KEY_MISS, "Delegates"),
        ObligationCell("get_title", "empty", CellType.UNDEF, "Undefined for empty list"),
        ObligationCell("get_title", "add_item", CellType.KEY_HIT, "Returns title"),
        ObligationCell("get_title", "add_item", CellType.KEY_MISS, "Delegates"),
        ObligationCell("get_title", "complete_item", CellType.PRESERVATION, "Preserves titles"),
        ObligationCell("get_title", "remove_item", CellType.KEY_HIT, "Explicitly undefined"),
        ObligationCell("get_title", "remove_item", CellType.KEY_MISS, "Delegates"),
        ObligationCell("get_status", "empty", CellType.UNDEF, "Undefined for empty list"),
        ObligationCell("get_status", "add_item", CellType.KEY_HIT, "Returns pending"),
        ObligationCell("get_status", "add_item", CellType.KEY_MISS, "Delegates"),
        ObligationCell("get_status", "complete_item", CellType.GUARDED, "Returns done if exists", "has_item"),
        ObligationCell("get_status", "complete_item", CellType.KEY_MISS, "Delegates"),
        ObligationCell("get_status", "remove_item", CellType.KEY_HIT, "Explicitly undefined"),
        ObligationCell("get_status", "remove_item", CellType.KEY_MISS, "Delegates"),
    ),
    design_decisions=(
        DesignDecision("Universal Preservation", "Complete_item preserves has_item and get_title regardless of key"),
        DesignDecision("Guarded Updates", "Complete_item only changes status if item exists"),
        DesignDecision("Explicit Undefinedness", "Remove_item explicitly forces undefinedness for removed items"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def todo_list_spec() -> Spec:

    # Variables
    l = var("l", "TodoList")
    k = var("k", "ItemId")
    k2 = var("k2", "ItemId")
    k3 = var("k3", "ItemId")
    t = var("t", "Title")

    sig = Signature(
        sorts={
            "ItemId": atomic("ItemId"),
            "Title": atomic("Title"),
            "Status": atomic("Status"),
            "TodoList": atomic("TodoList"),
        },
        functions={
            # General Constructors
            "empty": fn("empty", [], "TodoList"),
            "add_item": fn(
                "add_item",
                [("l", "TodoList"), ("k", "ItemId"), ("t", "Title")],
                "TodoList",
            ),
            "complete_item": fn(
                "complete_item", [("l", "TodoList"), ("k", "ItemId")], "TodoList"
            ),
            "remove_item": fn(
                "remove_item", [("l", "TodoList"), ("k", "ItemId")], "TodoList"
            ),
            # Partial Observers
            "get_title": fn(
                "get_title", [("l", "TodoList"), ("k", "ItemId")], "Title", total=False
            ),
            "get_status": fn(
                "get_status",
                [("l", "TodoList"), ("k", "ItemId")],
                "Status",
                total=False,
            ),
            # Enum Constants
            "pending": fn("pending", [], "Status"),
            "done": fn("done", [], "Status"),
        },
        predicates={
            "eq_id": pred("eq_id", [("k1", "ItemId"), ("k2", "ItemId")]),
            "has_item": pred("has_item", [("l", "TodoList"), ("k", "ItemId")]),
        },
        generated_sorts={
            "TodoList": GeneratedSortInfo(
                constructors=("empty", "add_item", "complete_item", "remove_item"),
                selectors={},
            )
        },
    )

    axioms = (
        # == eq_id structural axioms ==
        Axiom(
            "eq_id_refl", forall([k], pred_app("eq_id", k, k))
        ),  # eq_id x none: BASIS — reflexive
        Axiom(
            "eq_id_sym",  # eq_id x none: BASIS — symmetric
            forall(
                [k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    pred_app("eq_id", k2, k),
                ),
            ),
        ),
        Axiom(
            "eq_id_trans",  # eq_id x none: BASIS — transitive
            forall(
                [k, k2, k3],
                implication(
                    conjunction(pred_app("eq_id", k, k2),
                            pred_app("eq_id", k2, k3)),
                    pred_app("eq_id", k, k3),
                ),
            ),
        ),
        # == has_item axioms ==
        Axiom(
            "has_item_empty",  # has_item x empty: BASIS — empty list contains no items
            forall(
                [k],
                negation(
                    pred_app("has_item", const("empty"), k),
                ),
            ),
        ),
        Axiom(
            "has_item_add_hit",  # has_item x add_item: KEY_HIT — key match means item exists
            forall(
                [l, k, k2, t],
                implication(
                    pred_app("eq_id", k, k2),
                    pred_app("has_item", app("add_item", l, k, t), k2),
                ),
            ),
        ),
        Axiom(
            "has_item_add_miss",  # has_item x add_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2, t],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    iff(
                        pred_app("has_item", app("add_item", l, k, t), k2),
                        pred_app("has_item", l, k2),
                    ),
                ),
            ),
        ),
        Axiom(
            "has_item_complete",  # has_item x complete_item: PRESERVATION — complete preserves existence
            forall(
                [l, k, k2],
                iff(
                    pred_app("has_item", app("complete_item", l, k), k2),
                    pred_app("has_item", l, k2),
                ),
            ),
        ),
        Axiom(
            "has_item_remove_hit",  # has_item x remove_item: KEY_HIT — removed item doesn't exist
            forall(
                [l, k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    negation(pred_app("has_item", app("remove_item", l, k), k2)),
                ),
            ),
        ),
        Axiom(
            "has_item_remove_miss",  # has_item x remove_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    iff(
                        pred_app("has_item", app("remove_item", l, k), k2),
                        pred_app("has_item", l, k2),
                    ),
                ),
            ),
        ),
        # == get_title axioms ==
        Axiom(
            "get_title_empty_undef",  # get_title x empty: UNDEF — explicitly undefined for empty list
            forall([k], negation(definedness(app("get_title", const("empty"), k)))),
        ),
        Axiom(
            "get_title_add_hit",  # get_title x add_item: KEY_HIT — return added title
            forall(
                [l, k, k2, t],
                implication(
                    pred_app("eq_id", k, k2),
                    eq(app("get_title", app("add_item", l, k, t), k2), t),
                ),
            ),
        ),
        Axiom(
            "get_title_add_miss",  # get_title x add_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2, t],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    eq(
                        app("get_title", app("add_item", l, k, t), k2),
                        app("get_title", l, k2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_title_complete",  # get_title x complete_item: PRESERVATION — complete preserves titles
            forall(
                [l, k, k2],
                eq(
                    app("get_title", app("complete_item", l, k), k2),
                    app("get_title", l, k2),
                ),
            ),
        ),
        Axiom(
            "get_title_remove_hit",  # get_title x remove_item: KEY_HIT — explicitly undefined for removed item
            forall(
                [l, k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    negation(
                        definedness(app("get_title", app("remove_item", l, k), k2))
                    ),
                ),
            ),
        ),
        Axiom(
            "get_title_remove_miss",  # get_title x remove_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    eq(
                        app("get_title", app("remove_item", l, k), k2),
                        app("get_title", l, k2),
                    ),
                ),
            ),
        ),
        # == get_status axioms ==
        Axiom(
            "get_status_empty_undef",  # get_status x empty: UNDEF — explicitly undefined for empty list
            forall([k], negation(definedness(app("get_status", const("empty"), k)))),
        ),
        Axiom(
            "get_status_add_hit",  # get_status x add_item: KEY_HIT — new items start pending
            forall(
                [l, k, k2, t],
                implication(
                    pred_app("eq_id", k, k2),
                    eq(
                        app("get_status", app("add_item", l, k, t), k2),
                        const("pending"),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_add_miss",  # get_status x add_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2, t],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    eq(
                        app("get_status", app("add_item", l, k, t), k2),
                        app("get_status", l, k2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_complete_hit",  # get_status x complete_item: GUARDED — mark as done if exists
            forall(
                [l, k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    implication(
                        pred_app("has_item", l, k),
                        eq(
                            app("get_status", app("complete_item", l, k), k2),
                            const("done"),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_complete_hit_noitem",  # get_status x complete_item: KEY_HIT — no-op if missing
            forall(
                [l, k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    implication(
                        negation(pred_app("has_item", l, k)),
                        eq(
                            app("get_status", app("complete_item", l, k), k2),
                            app("get_status", l, k2),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_complete_miss",  # get_status x complete_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    eq(
                        app("get_status", app("complete_item", l, k), k2),
                        app("get_status", l, k2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_remove_hit",  # get_status x remove_item: KEY_HIT — explicitly undefined for removed item
            forall(
                [l, k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    negation(
                        definedness(app("get_status", app("remove_item", l, k), k2))
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_remove_miss",  # get_status x remove_item: KEY_MISS — delegate to underlying list
            forall(
                [l, k, k2],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    eq(
                        app("get_status", app("remove_item", l, k), k2),
                        app("get_status", l, k2),
                    ),
                ),
            ),
        ),
    )

    return Spec(name="TodoList", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Inventory
# ============================================================

INVENTORY_TRACKER = WorkedExample(
    domain_name="Inventory",
    summary="Demonstrates a finite map pattern with partial removal operations, using explicit definedness conditions to handle insufficient stock scenarios while maintaining collection integrity",
    patterns=frozenset({Pattern.ACCUMULATION, Pattern.COLLECTION_CONTAINER, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.PRESERVATION}),
    sorts=(
        SortInfo("Inventory", "CONTAINER", "Primary domain collection storing item quantities"),
        SortInfo("ItemId", "KEY", "Opaque identifier used as lookup keys"),
        SortInfo("Nat", CellType.BASIS, "Standard Peano basis sort for quantity arithmetic"),
    ),
    functions=(
        FunctionInfo("empty", "→ Inventory", FunctionRole.CONSTRUCTOR, "Creates empty inventory"),
        FunctionInfo("add_stock", "Inventory × ItemId × Nat → Inventory", FunctionRole.CONSTRUCTOR, "Adds quantity to item"),
        FunctionInfo("remove_stock", "Inventory × ItemId × Nat →? Inventory", FunctionRole.CONSTRUCTOR, "Partial: removes quantity if sufficient stock exists"),
        FunctionInfo("get_qty", "Inventory × ItemId → Nat", FunctionRole.OBSERVER, "Returns item quantity, zero for missing items"),
        FunctionInfo("zero", "→ Nat", FunctionRole.CONSTANT, "Basis constant for zero quantity"),
        FunctionInfo("add", "Nat × Nat → Nat", FunctionRole.HELPER, "Basis arithmetic"),
        FunctionInfo("sub", "Nat × Nat → Nat", FunctionRole.HELPER, "Basis arithmetic"),
        FunctionInfo("eq_id", "ItemId × ItemId", FunctionRole.PREDICATE, "Key equality dispatch"),
        FunctionInfo("leq", "Nat × Nat", FunctionRole.PREDICATE, "Quantity comparison for stock checks"),
    ),
    obligations=(
        ObligationCell("eq_id", "—", CellType.BASIS, "Reflexivity: k = k"),
        ObligationCell("eq_id", "—", CellType.BASIS, "Symmetry: k1 = k2 ⇒ k2 = k1"),
        ObligationCell("eq_id", "—", CellType.BASIS, "Transitivity: k1 = k2 ∧ k2 = k3 ⇒ k1 = k3"),
        ObligationCell("Definedness", "remove_stock", CellType.DOMAIN, "remove_stock defined iff leq(q, get_qty(i,k))"),
        ObligationCell("get_qty", "empty", CellType.BASIS, "get_qty(empty, k) = zero"),
        ObligationCell("get_qty", "add_stock", CellType.KEY_HIT, "get_qty(add_stock(i,k,q), k) = add(get_qty(i,k), q)", "eq_id(k,k2)"),
        ObligationCell("get_qty", "add_stock", CellType.KEY_MISS, "get_qty(add_stock(i,k,q), k2) = get_qty(i,k2)", "¬eq_id(k,k2)"),
        ObligationCell("get_qty", "remove_stock", CellType.KEY_HIT, "get_qty(remove_stock(i,k,q), k) = sub(get_qty(i,k), q)", "eq_id(k,k2) ∧ leq(q,get_qty(i,k))"),
        ObligationCell("get_qty", "remove_stock", CellType.KEY_MISS, "get_qty(remove_stock(i,k,q), k2) = get_qty(i,k2)", "¬eq_id(k,k2) ∧ leq(q,get_qty(i,k))"),
    ),
    design_decisions=(
        DesignDecision("Partial Constructor", "remove_stock is partial when stock insufficient, using explicit Definedness wrapper"),
        DesignDecision("Guarded Axioms", "All remove_stock axioms must be guarded by leq condition due to partiality"),
        DesignDecision("Zero Quantity", "Missing items conceptually have zero quantity, avoiding need for has_item predicate"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def inventory_spec() -> Spec:

    # Variables for equations
    i = var("i", "Inventory")
    k = var("k", "ItemId")  # Constructor key
    k2 = var("k2", "ItemId")  # Observer query key
    k3 = var("k3", "ItemId")  # Transitivity temp key
    q = var("q", "Nat")  # Modification quantity

    sig = Signature(
        sorts={
            "ItemId": atomic("ItemId"),
            "Nat": atomic("Nat"),
            "Inventory": atomic("Inventory"),
        },
        functions={
            # Inventory Constructors
            "empty": fn("empty", [], "Inventory"),
            "add_stock": fn(
                "add_stock",
                [("i", "Inventory"), ("k", "ItemId"), ("q", "Nat")],
                "Inventory",
            ),
            "remove_stock": fn(
                "remove_stock",
                [("i", "Inventory"), ("k", "ItemId"), ("q", "Nat")],
                "Inventory",
                total=False,
            ),  # Partial: Fails if not enough stock
            # Observers
            "get_qty": fn("get_qty", [("i", "Inventory"), ("k", "ItemId")], "Nat"),
            # Basis Uninterpreted operations
            "zero": fn("zero", [], "Nat"),
            "add": fn("add", [("n1", "Nat"), ("n2", "Nat")], "Nat"),
            "sub": fn("sub", [("n1", "Nat"), ("n2", "Nat")], "Nat"),
        },
        predicates={
            "eq_id": pred("eq_id", [("k1", "ItemId"), ("k2", "ItemId")]),
            "leq": pred("leq", [("n1", "Nat"), ("n2", "Nat")]),
        },
        generated_sorts={
            "Inventory": GeneratedSortInfo(
                constructors=("empty", "add_stock", "remove_stock"),
                selectors={},
            )
        },
    )

    axioms = (
        # == eq_id basis axioms ==
        # Reflexivity: every key equals itself
        Axiom(
            label="eq_id_refl",
            formula=forall([k], pred_app("eq_id", k, k)),
        ),
        # Symmetry: if k1 equals k2, then k2 equals k1
        Axiom(
            label="eq_id_sym",
            formula=forall(
                [k, k2],
                implication(
                    pred_app("eq_id", k, k2),
                    pred_app("eq_id", k2, k),
                ),
            ),
        ),
        # Transitivity: if k1=k2 and k2=k3 then k1=k3
        Axiom(
            label="eq_id_trans",
            formula=forall(
                [k, k2, k3],
                implication(
                    conjunction(pred_app("eq_id", k, k2),
                            pred_app("eq_id", k2, k3)),
                    pred_app("eq_id", k, k3),
                ),
            ),
        ),
        # == Definedness conditions ==
        # remove_stock is defined iff quantity to remove <= current quantity
        Axiom(
            label="remove_stock_def",
            formula=forall(
                [i, k, q],
                iff(
                    definedness(app("remove_stock", i, k, q)),
                    pred_app("leq", q, app("get_qty", i, k)),
                ),
            ),
        ),
        # == get_qty observer axioms ==
        # Empty inventory: all items have zero quantity
        Axiom(
            label="get_qty_empty",
            formula=forall(
                [k],
                eq(
                    app("get_qty", const("empty"), k),
                    const("zero"),
                ),
            ),
        ),
        # add_stock x get_qty: HIT — add new quantity to existing
        Axiom(
            label="get_qty_add_hit",
            formula=forall(
                [i, k, k2, q],
                implication(
                    pred_app("eq_id", k, k2),
                    eq(
                        app("get_qty", app("add_stock", i, k, q), k2),
                        app("add", app("get_qty", i, k2), q),
                    ),
                ),
            ),
        ),
        # add_stock x get_qty: MISS — preserve existing quantity
        Axiom(
            label="get_qty_add_miss",
            formula=forall(
                [i, k, k2, q],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    eq(
                        app("get_qty", app("add_stock", i, k, q), k2),
                        app("get_qty", i, k2),
                    ),
                ),
            ),
        ),
        # remove_stock x get_qty: HIT — subtract quantity if sufficient stock exists
        Axiom(
            label="get_qty_remove_hit",
            formula=forall(
                [i, k, k2, q],
                implication(
                    pred_app("eq_id", k, k2),
                    implication(
                        pred_app("leq", q, app("get_qty", i, k)),
                        eq(
                            app("get_qty", app("remove_stock", i, k, q), k2),
                            app("sub", app("get_qty", i, k2), q),
                        ),
                    ),
                ),
            ),
        ),
        # remove_stock x get_qty: MISS — preserve quantity if sufficient stock exists
        Axiom(
            label="get_qty_remove_miss",
            formula=forall(
                [i, k, k2, q],
                implication(
                    negation(pred_app("eq_id", k, k2)),
                    implication(
                        pred_app("leq", q, app("get_qty", i, k)),
                        eq(
                            app("get_qty", app("remove_stock", i, k, q), k2),
                            app("get_qty", i, k2),
                        ),
                    ),
                ),
            ),
        ),
    )

    return Spec(name="Inventory", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Shopping Cart
# ============================================================

SHOPPING_CART = WorkedExample(
    domain_name="Shopping Cart",
    summary="Demonstrates a collection container using multiset semantics for items with key-based removal and price accumulation. Features key dispatch for item operations, preservation across discount application, and explicit undefinedness for invalid removals.",
    patterns=frozenset({Pattern.COLLECTION_CONTAINER, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.DELEGATION, Pattern.ACCUMULATION, Pattern.EXPLICIT_UNDEF, Pattern.PRESERVATION}),
    sorts=(
        SortInfo("Cart", "CONTAINER", "Collection state represented as sequenced history of constructors acting like a multiset"),
        SortInfo("ItemId", "KEY", "Identifiers for items"),
        SortInfo("Price", "VALUE", "Opaque representation of monetary values"),
        SortInfo("DiscountCode", "KEY", "Identifiers for discount codes"),
    ),
    functions=(
        FunctionInfo("empty", "→ Cart", FunctionRole.CONSTRUCTOR, "Initial empty cart"),
        FunctionInfo("add_item", "Cart × ItemId → Cart", FunctionRole.CONSTRUCTOR, "Adds an item"),
        FunctionInfo("apply_discount", "Cart × DiscountCode → Cart", FunctionRole.CONSTRUCTOR, "Applies discount code, encoding state in cart history"),
        FunctionInfo("remove_item", "Cart × ItemId →? Cart", FunctionRole.PARTIAL_OBSERVER, "Removes single instance of item, undefined if missing"),
        FunctionInfo("compute_total", "Cart → Price", FunctionRole.OBSERVER, "Reduces cart to total price"),
        FunctionInfo("has_item", "Cart × ItemId → Bool", FunctionRole.PREDICATE, "Tests item membership"),
        FunctionInfo("zero", "→ Price", FunctionRole.CONSTANT, "Zero price value"),
        FunctionInfo("add_price", "Price × Price → Price", FunctionRole.HELPER, "Price addition"),
        FunctionInfo("item_price", "ItemId → Price", FunctionRole.HELPER, "Gets price for item"),
        FunctionInfo("apply_discount_logic", "Price × DiscountCode → Price", FunctionRole.HELPER, "Applies discount to price"),
        FunctionInfo("eq_id", "ItemId × ItemId → Bool", FunctionRole.PREDICATE, "Key equality"),
    ),
    obligations=(
        ObligationCell("eq_id", "—", CellType.BASIS, "Reflexivity"),
        ObligationCell("eq_id", "—", CellType.BASIS, "Symmetry"),
        ObligationCell("eq_id", "—", CellType.BASIS, "Transitivity"),
        ObligationCell("has_item", "empty", CellType.KEY_MISS, "Always false"),
        ObligationCell("has_item", "add_item", CellType.KEY_HIT, "True on match", "eq_id(i,j)"),
        ObligationCell("has_item", "add_item", CellType.KEY_MISS, "Delegate to cart", "!eq_id(i,j)"),
        ObligationCell("has_item", "apply_discount", CellType.PRESERVATION, "Preserves membership"),
        ObligationCell("remove_item", "empty", CellType.UNDEF, "Undefined on empty"),
        ObligationCell("remove_item", "add_item", CellType.KEY_HIT, "Returns cart on match", "eq_id(i,j)"),
        ObligationCell("remove_item", "add_item", CellType.KEY_MISS, "Recurse and reconstruct", "!eq_id(i,j)"),
        ObligationCell("remove_item", "apply_discount", CellType.PRESERVATION, "Preserves removal through discount"),
        ObligationCell("compute_total", "empty", CellType.BASIS, "Zero base case"),
        ObligationCell("compute_total", "add_item", CellType.DOMAIN, "Add item price to total"),
        ObligationCell("compute_total", "apply_discount", CellType.KEY_MISS, "Apply discount to total"),
    ),
    design_decisions=(
        DesignDecision("Failing Removal Strictness", "Omitting axiom for remove_item(empty,j) ensures undefined behavior bubbles up when item not found"),
        DesignDecision("Multiset Semantics", "remove_item returns c on eq_id(i,j) hit to implement single instance removal in repetitive adds"),
        DesignDecision("Pervasive Universal Discount", "compute_total applies discounts natively around price total for clean algebraic workflow"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def shopping_cart_spec() -> Spec:

    # Variables for axioms
    c = var("c", "Cart")
    i = var("i", "ItemId")
    j = var("j", "ItemId")
    k = var("k", "ItemId")
    d = var("d", "DiscountCode")

    sig = Signature(
        sorts={
            "Cart": atomic("Cart"),
            "ItemId": atomic("ItemId"),
            "Price": atomic("Price"),
            "DiscountCode": atomic("DiscountCode"),
        },
        functions={
            # State Constructors
            "empty": fn("empty", [], "Cart"),
            "add_item": fn("add_item", [("c", "Cart"), ("i", "ItemId")], "Cart"),
            "apply_discount": fn(
                "apply_discount", [("c", "Cart"), ("d", "DiscountCode")], "Cart"
            ),
            # Partial Modifier (fails if item not in cart)
            "remove_item": fn(
                "remove_item", [("c", "Cart"), ("i", "ItemId")], "Cart", total=False
            ),
            # Observer
            "compute_total": fn("compute_total", [("c", "Cart")], "Price"),
            # Price Helper Mechanics
            "zero": fn("zero", [], "Price"),
            "add_price": fn("add_price", [("p1", "Price"), ("p2", "Price")], "Price"),
            "item_price": fn("item_price", [("i", "ItemId")], "Price"),
            "apply_discount_logic": fn(
                "apply_discount_logic", [("p", "Price"), ("d", "DiscountCode")], "Price"
            ),
        },
        predicates={
            "eq_id": pred("eq_id", [("i1", "ItemId"), ("i2", "ItemId")]),
            "has_item": pred("has_item", [("c", "Cart"), ("i", "ItemId")]),
        },
        generated_sorts={
            "Cart": GeneratedSortInfo(
                constructors=("empty", "add_item", "apply_discount"),
                selectors={},
            )
        },
    )

    axioms = (
        # == eq_id basis axioms ==
        # eq_id x basis: BASIS — reflexivity property
        Axiom(
            label="eq_id_refl",
            formula=forall([i], pred_app("eq_id", i, i)),
        ),
        # eq_id x basis: BASIS — symmetry property
        Axiom(
            label="eq_id_sym",
            formula=forall(
                [i, j],
                implication(
                    pred_app("eq_id", i, j),
                    pred_app("eq_id", j, i),
                ),
            ),
        ),
        # eq_id x basis: BASIS — transitivity property
        Axiom(
            label="eq_id_trans",
            formula=forall(
                [i, j, k],
                implication(
                    conjunction(pred_app("eq_id", i, j),
                            pred_app("eq_id", j, k)),
                    pred_app("eq_id", i, k),
                ),
            ),
        ),
        # == has_item membership predicate axioms ==
        # has_item x empty: KEY_MISS — empty cart has no items
        Axiom(
            label="has_item_empty",
            formula=forall(
                [j],
                negation(
                    pred_app("has_item", const("empty"), j),
                ),
            ),
        ),
        # has_item x add_item: KEY_HIT — matching item found
        Axiom(
            label="has_item_add_hit",
            formula=forall(
                [c, i, j],
                implication(
                    pred_app("eq_id", i, j),
                    pred_app("has_item", app("add_item", c, i), j),
                ),
            ),
        ),
        # has_item x add_item: KEY_MISS — delegate to rest of cart
        Axiom(
            label="has_item_add_miss",
            formula=forall(
                [c, i, j],
                implication(
                    negation(pred_app("eq_id", i, j)),
                    iff(
                        pred_app("has_item", app("add_item", c, i), j),
                        pred_app("has_item", c, j),
                    ),
                ),
            ),
        ),
        # has_item x apply_discount: PRESERVATION — discount preserves membership
        Axiom(
            label="has_item_discount",
            formula=forall(
                [c, d, j],
                iff(
                    pred_app("has_item", app("apply_discount", c, d), j),
                    pred_app("has_item", c, j),
                ),
            ),
        ),
        # == remove_item partial modifier axioms ==
        # remove_item x empty: UNDEF — undefined when cart empty
        Axiom(
            label="remove_item_empty_undef",
            formula=forall(
                [j], negation(definedness(app("remove_item", const("empty"), j)))
            ),
        ),
        # remove_item x add_item: KEY_HIT — return cart when item matches
        Axiom(
            label="remove_item_add_hit",
            formula=forall(
                [c, i, j],
                implication(
                    pred_app("eq_id", i, j),
                    eq(app("remove_item", app("add_item", c, i), j), c),
                ),
            ),
        ),
        # remove_item x add_item: KEY_MISS — recurse and reconstruct
        Axiom(
            label="remove_item_add_miss",
            formula=forall(
                [c, i, j],
                implication(
                    negation(pred_app("eq_id", i, j)),
                    eq(
                        app("remove_item", app("add_item", c, i), j),
                        app("add_item", app("remove_item", c, j), i),
                    ),
                ),
            ),
        ),
        # remove_item x apply_discount: PRESERVATION — preserve removal through discount
        Axiom(
            label="remove_item_discount",
            formula=forall(
                [c, d, j],
                eq(
                    app("remove_item", app("apply_discount", c, d), j),
                    app("apply_discount", app("remove_item", c, j), d),
                ),
            ),
        ),
        # == compute_total observer axioms ==
        # compute_total x empty: BASIS — empty cart has zero total
        Axiom(
            label="compute_total_empty",
            formula=eq(
                app("compute_total", const("empty")),
                const("zero"),
            ),
        ),
        # compute_total x add_item: ACCUMULATION — add item price to total
        Axiom(
            label="compute_total_add",
            formula=forall(
                [c, i],
                eq(
                    app("compute_total", app("add_item", c, i)),
                    app("add_price", app("compute_total", c), app("item_price", i)),
                ),
            ),
        ),
        # compute_total x apply_discount: DELEGATION — apply discount to total price
        Axiom(
            label="compute_total_discount",
            formula=forall(
                [c, d],
                eq(
                    app("compute_total", app("apply_discount", c, d)),
                    app("apply_discount_logic", app("compute_total", c), d),
                ),
            ),
        ),
    )

    return Spec(name="ShoppingCart", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Access Control
# ============================================================

ACCESS_CONTROL = WorkedExample(
    domain_name="Access Control",
    summary="Demonstrates role-based access control with direct permissions, using key dispatch for user/resource pairs and preservation of unaffected state. Features admin override through derived predicate.",
    patterns=frozenset({Pattern.BICOND_CHAR, Pattern.BOTH_GUARD_POL, Pattern.COLLECTION_CONTAINER, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.NESTED_GUARD, Pattern.PRESERVATION}),
    sorts=(
        SortInfo("UserId", "ATOMIC", "Key for user identification and lookup"),
        SortInfo("ResourceId", "ATOMIC", "Key for resource identification"),
        SortInfo("Role", "ATOMIC", "Enumerated role types (admin, regular, none)"),
        SortInfo("System", "CONTAINER", "Central domain object mapping users to roles and tracking permissions"),
    ),
    functions=(
        FunctionInfo("init", "→ System", FunctionRole.CONSTRUCTOR, "Creates empty system"),
        FunctionInfo("set_role", "System × UserId × Role → System", FunctionRole.CONSTRUCTOR, "Assigns role to user"),
        FunctionInfo("grant", "System × UserId × ResourceId → System", FunctionRole.CONSTRUCTOR, "Grants direct resource access"),
        FunctionInfo("revoke", "System × UserId × ResourceId → System", FunctionRole.CONSTRUCTOR, "Revokes direct access"),
        FunctionInfo("none", "→ Role", FunctionRole.CONSTANT, "Default role for unassigned users"),
        FunctionInfo("admin", "→ Role", FunctionRole.CONSTANT, "Administrator role"),
        FunctionInfo("regular", "→ Role", FunctionRole.CONSTANT, "Regular user role"),
        FunctionInfo("get_role", "System × UserId → Role", FunctionRole.OBSERVER, "Retrieves user's role"),
        FunctionInfo("eq_user", "UserId × UserId → Bool", FunctionRole.PREDICATE, "User equality test"),
        FunctionInfo("eq_res", "ResourceId × ResourceId → Bool", FunctionRole.PREDICATE, "Resource equality test"),
        FunctionInfo("has_permission", "System × UserId × ResourceId → Bool", FunctionRole.PREDICATE, "Tests direct resource access"),
        FunctionInfo("can_access", "System × UserId × ResourceId → Bool", FunctionRole.PREDICATE, "Tests effective access including admin override"),
    ),
    obligations=(
        ObligationCell("eq_user", "—", CellType.BASIS, "Reflexivity/symmetry/transitivity"),
        ObligationCell("eq_res", "—", CellType.BASIS, "Reflexivity/symmetry/transitivity"),
        ObligationCell("get_role", "init", CellType.KEY_MISS, "Returns none"),
        ObligationCell("get_role", "set_role", CellType.KEY_HIT, "Returns new role", "eq_user(u1,u2)"),
        ObligationCell("get_role", "set_role", CellType.KEY_MISS, "Preserves existing role", "¬eq_user(u1,u2)"),
        ObligationCell("get_role", "grant", CellType.PRESERVATION, "Preserves all roles"),
        ObligationCell("get_role", "revoke", CellType.PRESERVATION, "Preserves all roles"),
        ObligationCell("has_permission", "init", CellType.KEY_MISS, "Returns false"),
        ObligationCell("has_permission", "set_role", CellType.PRESERVATION, "Preserves permissions"),
        ObligationCell("has_permission", "grant", CellType.KEY_HIT, "Grants permission", "eq_user(u1,u2) ∧ eq_res(r1,r2)"),
        ObligationCell("has_permission", "grant", CellType.KEY_MISS, "Preserves other permissions", "¬(eq_user(u1,u2) ∧ eq_res(r1,r2))"),
        ObligationCell("has_permission", "revoke", CellType.KEY_HIT, "Revokes permission", "eq_user(u1,u2) ∧ eq_res(r1,r2)"),
        ObligationCell("has_permission", "revoke", CellType.KEY_MISS, "Preserves other permissions", "¬(eq_user(u1,u2) ∧ eq_res(r1,r2))"),
    ),
    design_decisions=(
        DesignDecision("Role totality", "Using 'none' role makes get_role total, avoiding partiality in can_access"),
        DesignDecision("Derived access", "can_access defined universally against get_role/has_permission to prevent axiom explosion"),
        DesignDecision("Composite key", "grant/revoke use conjunction of eq_user/eq_res for hit/miss dispatch"),
        DesignDecision("Role distinctness", "Explicit distinctness axioms prevent model collapse making all roles equal"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
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
            "set_role": fn(
                "set_role",
                [("s", "System"), ("u", "UserId"), ("role", "Role")],
                "System",
            ),
            "grant": fn(
                "grant",
                [("s", "System"), ("u", "UserId"), ("r", "ResourceId")],
                "System",
            ),
            "revoke": fn(
                "revoke",
                [("s", "System"), ("u", "UserId"), ("r", "ResourceId")],
                "System",
            ),
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
            "has_permission": pred(
                "has_permission",
                [("s", "System"), ("u", "UserId"), ("r", "ResourceId")],
            ),
            "can_access": pred(
                "can_access", [("s", "System"), ("u", "UserId"), ("r", "ResourceId")]
            ),
        },
        generated_sorts={
            "System": GeneratedSortInfo(
                constructors=("init", "set_role", "grant", "revoke"),
                selectors={},
            )
        },
    )

    axioms = (
        # == Equality Basis ==
        # eq_user x basis: Equivalence relation properties
        Axiom("eq_user_refl", forall([u], pred_app("eq_user", u, u))),
        Axiom(
            "eq_user_sym",
            forall(
                [u1, u2],
                implication(
                    pred_app("eq_user", u1, u2),
                    pred_app("eq_user", u2, u1),
                ),
            ),
        ),
        Axiom(
            "eq_user_trans",
            forall(
                [u1, u2, u3],
                implication(
                    conjunction(pred_app("eq_user", u1, u2), pred_app("eq_user", u2, u3)),
                    pred_app("eq_user", u1, u3),
                ),
            ),
        ),
        # eq_res x basis: Equivalence relation properties
        Axiom("eq_res_refl", forall([r], pred_app("eq_res", r, r))),
        Axiom(
            "eq_res_sym",
            forall(
                [r1, r2],
                implication(
                    pred_app("eq_res", r1, r2),
                    pred_app("eq_res", r2, r1),
                ),
            ),
        ),
        Axiom(
            "eq_res_trans",
            forall(
                [r1, r2, r3],
                implication(
                    conjunction(pred_app("eq_res", r1, r2), pred_app("eq_res", r2, r3)),
                    pred_app("eq_res", r1, r3),
                ),
            ),
        ),
        # == Role Distinctness ==
        # Prevent model collapse where all roles are equal
        Axiom("role_admin_ne_regular", negation(eq(const("admin"), const("regular")))),
        Axiom("role_admin_ne_none", negation(eq(const("admin"), const("none")))),
        Axiom("role_regular_ne_none", negation(eq(const("regular"), const("none")))),
        # == Role Management ==
        # get_role x init: Default role is none
        Axiom(
            "get_role_init",
            forall(
                [u],
                eq(
                    app("get_role", const("init"), u),
                    const("none"),
                ),
            ),
        ),
        # get_role x set_role: Key hit returns new role
        Axiom(
            "get_role_set_hit",
            forall(
                [s, u1, u2, role],
                implication(
                    pred_app("eq_user", u1, u2),
                    eq(app("get_role", app("set_role", s, u1, role), u2), role),
                ),
            ),
        ),
        # get_role x set_role: Key miss preserves existing role
        Axiom(
            "get_role_set_miss",
            forall(
                [s, u1, u2, role],
                implication(
                    negation(pred_app("eq_user", u1, u2)),
                    eq(
                        app("get_role", app("set_role", s, u1, role), u2),
                        app("get_role", s, u2),
                    ),
                ),
            ),
        ),
        # get_role x grant: Preserves all roles
        Axiom(
            "get_role_grant",
            forall(
                [s, u1, u2, r1],
                eq(
                    app("get_role", app("grant", s, u1, r1), u2),
                    app("get_role", s, u2),
                ),
            ),
        ),
        # get_role x revoke: Preserves all roles
        Axiom(
            "get_role_revoke",
            forall(
                [s, u1, u2, r1],
                eq(
                    app("get_role", app("revoke", s, u1, r1), u2),
                    app("get_role", s, u2),
                ),
            ),
        ),
        # == Permission Management ==
        # has_permission x init: No initial permissions
        Axiom(
            "has_perm_init",
            forall(
                [u, r],
                negation(
                    pred_app("has_permission", const("init"), u, r),
                ),
            ),
        ),
        # has_permission x set_role: Preserves all permissions
        Axiom(
            "has_perm_set",
            forall(
                [s, u1, u2, role, r],
                iff(
                    pred_app("has_permission", app("set_role", s, u1, role), u2, r),
                    pred_app("has_permission", s, u2, r),
                ),
            ),
        ),
        # has_permission x grant: Key hit grants permission
        Axiom(
            "has_perm_grant_hit",
            forall(
                [s, u1, u2, r1, r2],
                implication(
                    conjunction(pred_app("eq_user", u1, u2), pred_app("eq_res", r1, r2)),
                    pred_app("has_permission", app("grant", s, u1, r1), u2, r2),
                ),
            ),
        ),
        # has_permission x grant: Key miss preserves permission
        Axiom(
            "has_perm_grant_miss",
            forall(
                [s, u1, u2, r1, r2],
                implication(
                    negation(
                        conjunction(pred_app("eq_user", u1, u2), pred_app("eq_res", r1, r2))
                    ),
                    iff(
                        pred_app("has_permission", app("grant", s, u1, r1), u2, r2),
                        pred_app("has_permission", s, u2, r2),
                    ),
                ),
            ),
        ),
        # has_permission x revoke: Key hit removes permission
        Axiom(
            "has_perm_revoke_hit",
            forall(
                [s, u1, u2, r1, r2],
                implication(
                    conjunction(pred_app("eq_user", u1, u2), pred_app("eq_res", r1, r2)),
                    negation(
                        pred_app("has_permission", app("revoke", s, u1, r1), u2, r2)
                    ),
                ),
            ),
        ),
        # has_permission x revoke: Key miss preserves permission
        Axiom(
            "has_perm_revoke_miss",
            forall(
                [s, u1, u2, r1, r2],
                implication(
                    negation(
                        conjunction(pred_app("eq_user", u1, u2), pred_app("eq_res", r1, r2))
                    ),
                    iff(
                        pred_app("has_permission", app("revoke", s, u1, r1), u2, r2),
                        pred_app("has_permission", s, u2, r2),
                    ),
                ),
            ),
        ),
        # == Access Rules ==
        # can_access: Admin override or explicit permission required
        Axiom(
            "can_access_def",
            forall(
                [s, u, r],
                iff(
                    pred_app("can_access", s, u, r),
                    disjunction(eq(app("get_role", s, u), const("admin")),
                            pred_app("has_permission", s, u, r)),
                ),
            ),
        ),
    )

    return Spec(name="AccessControl", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Library Lending
# ============================================================

LIBRARY_LENDING = WorkedExample(
    domain_name="Library Lending",
    summary="Demonstrates a collection-based library system with keyed lookup and status tracking. Uses key dispatch with guarded operations for book borrowing/return, and explicit undefined handling for missing books and borrowers.",
    patterns=frozenset({Pattern.BICOND_CHAR, Pattern.BOTH_GUARD_POL, Pattern.COLLECTION_CONTAINER, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.NESTED_GUARD, Pattern.PRESERVATION, Pattern.UNINTERP_FN}),
    sorts=(
        SortInfo("BookId", "ATOMIC", "Opaque identifier used as lookup key for books"),
        SortInfo("UserId", "ATOMIC", "Opaque identifier for library patrons"),
        SortInfo("Status", "ATOMIC", "Enumeration for book status (available/borrowed)"),
        SortInfo("Library", "CONTAINER", "Collection mapping books to statuses and borrowers"),
    ),
    functions=(
        FunctionInfo("empty", "→ Library", FunctionRole.CONSTRUCTOR, "Creates empty library"),
        FunctionInfo("register", "Library × BookId → Library", FunctionRole.CONSTRUCTOR, "Registers new book as available"),
        FunctionInfo("borrow", "Library × BookId × UserId → Library", FunctionRole.CONSTRUCTOR, "Records book borrow if available"),
        FunctionInfo("return_book", "Library × BookId → Library", FunctionRole.CONSTRUCTOR, "Marks borrowed book as available"),
        FunctionInfo("available", "→ Status", FunctionRole.CONSTANT, "Book status constant"),
        FunctionInfo("borrowed", "→ Status", FunctionRole.CONSTANT, "Book status constant"),
        FunctionInfo("get_status", "Library × BookId →? Status", FunctionRole.PARTIAL_OBSERVER, "Gets book status if registered"),
        FunctionInfo("get_borrower", "Library × BookId →? UserId", FunctionRole.PARTIAL_OBSERVER, "Gets current borrower if borrowed"),
        FunctionInfo("has_book", "Library × BookId", FunctionRole.PREDICATE, "Tests if book is registered"),
        FunctionInfo("eq_id", "BookId × BookId", FunctionRole.HELPER, "Key equality for dispatch"),
    ),
    obligations=(
        ObligationCell("get_status", "empty", CellType.UNDEF, "undefined"),
        ObligationCell("get_status", "register", CellType.KEY_HIT, "available", "eq_id(b,b2)"),
        ObligationCell("get_status", "register", CellType.KEY_MISS, "delegate", "!eq_id(b,b2)"),
        ObligationCell("get_status", "borrow", CellType.GUARDED, "borrowed", "eq_id(b,b2) && status=available"),
        ObligationCell("get_status", "borrow", CellType.PRESERVATION, "delegate", "!guard"),
        ObligationCell("get_status", "return_book", CellType.GUARDED, "available", "eq_id(b,b2) && status=borrowed"),
        ObligationCell("get_borrower", "empty", CellType.UNDEF, "undefined"),
        ObligationCell("get_borrower", "register", CellType.UNDEF, "undefined", "eq_id(b,b2)"),
        ObligationCell("get_borrower", "borrow", CellType.GUARDED, "u", "eq_id(b,b2) && status=available"),
        ObligationCell("get_borrower", "return_book", CellType.UNDEF, "undefined", "eq_id(b,b2) && status=borrowed"),
    ),
    design_decisions=(
        DesignDecision("Guard Strategy", "Use key dispatch with condition branching for borrow/return operations"),
        DesignDecision("Undefined Handling", "Explicitly declare undefined for missing books and cleared borrowers"),
        DesignDecision("State Model", "Embed book state directly in Library rather than separate Book sort"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def library_lending_spec() -> Spec:

    L = var("L", "Library")
    b = var("b", "BookId")
    b2 = var("b2", "BookId")
    b3 = var("b3", "BookId")
    u = var("u", "UserId")

    sig = Signature(
        sorts={
            "BookId": atomic("BookId"),
            "UserId": atomic("UserId"),
            "Status": atomic("Status"),
            "Library": atomic("Library"),
        },
        functions={
            # Collection constructors
            "empty": fn("empty", [], "Library"),
            "register": fn("register", [("L", "Library"), ("b", "BookId")], "Library"),
            "borrow": fn(
                "borrow",
                [("L", "Library"), ("b", "BookId"), ("u", "UserId")],
                "Library",
            ),
            "return_book": fn(
                "return_book", [("L", "Library"), ("b", "BookId")], "Library"
            ),
            # Constants
            "available": fn("available", [], "Status"),
            "borrowed": fn("borrowed", [], "Status"),
            # Partial Observers
            "get_status": fn(
                "get_status", [("L", "Library"), ("b", "BookId")], "Status", total=False
            ),
            "get_borrower": fn(
                "get_borrower",
                [("L", "Library"), ("b", "BookId")],
                "UserId",
                total=False,
            ),
        },
        predicates={
            "eq_id": pred("eq_id", [("b1", "BookId"), ("b2", "BookId")]),
            "has_book": pred("has_book", [("L", "Library"), ("b", "BookId")]),
        },
        generated_sorts={
            "Library": GeneratedSortInfo(
                constructors=("empty", "register", "borrow", "return_book"),
                selectors={},
            )
        },
    )

    axioms = (
        # == Equality Basis ==
        Axiom(
            "eq_id_refl", forall([b], pred_app("eq_id", b, b))
        ),  # eq_id x identity: BASIS — reflexivity
        Axiom(
            "eq_id_sym",
            forall(
                [b, b2],
                implication(  # eq_id x identity: BASIS — symmetry
                    pred_app("eq_id", b, b2),
                    pred_app("eq_id", b2, b),
                ),
            ),
        ),
        Axiom(
            "eq_id_trans",
            forall(
                [b, b2, b3],
                implication(  # eq_id x identity: BASIS — transitivity
                    conjunction(pred_app("eq_id", b, b2), pred_app("eq_id", b2, b3)),
                    pred_app("eq_id", b, b3),
                ),
            ),
        ),
        # == Book Registration Status ==
        Axiom(
            "has_book_empty",
            forall(
                [b],
                negation(  # has_book x empty: BASIS — no books in empty library
                    pred_app("has_book", const("empty"), b),
                ),
            ),
        ),
        Axiom(
            "has_book_register_hit",
            forall(
                [L, b, b2],
                implication(  # has_book x register: KEY_HIT — book becomes registered
                    pred_app("eq_id", b, b2),
                    pred_app("has_book", app("register", L, b), b2),
                ),
            ),
        ),
        Axiom(
            "has_book_register_miss",
            forall(
                [L, b, b2],
                implication(  # has_book x register: KEY_MISS — delegate to previous state
                    negation(pred_app("eq_id", b, b2)),
                    iff(
                        pred_app("has_book", app("register", L, b), b2),
                        pred_app("has_book", L, b2),
                    ),
                ),
            ),
        ),
        Axiom(
            "has_book_borrow_univ",
            forall(
                [L, b, b2, u],
                iff(  # has_book x borrow: PRESERVATION — borrowing preserves registration
                    pred_app("has_book", app("borrow", L, b, u), b2),
                    pred_app("has_book", L, b2),
                ),
            ),
        ),
        Axiom(
            "has_book_return_univ",
            forall(
                [L, b, b2],
                iff(  # has_book x return: PRESERVATION — returning preserves registration
                    pred_app("has_book", app("return_book", L, b), b2),
                    pred_app("has_book", L, b2),
                ),
            ),
        ),
        # == Book Status Management ==
        Axiom(
            "get_status_empty_undef",
            forall(
                [b],
                negation(
                    definedness(  # get_status x empty: UNDEF — no status in empty library
                        app("get_status", const("empty"), b),
                    )
                ),
            ),
        ),
        Axiom(
            "get_status_register_hit",
            forall(
                [L, b, b2],
                implication(  # get_status x register: KEY_HIT — new books are available
                    pred_app("eq_id", b, b2),
                    eq(
                        app("get_status", app("register", L, b), b2), const("available")
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_register_miss",
            forall(
                [L, b, b2],
                implication(  # get_status x register: KEY_MISS — delegate for other books
                    negation(pred_app("eq_id", b, b2)),
                    eq(
                        app("get_status", app("register", L, b), b2),
                        app("get_status", L, b2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_borrow_hit_succ",
            forall(
                [L, b, b2, u],
                implication(  # get_status x borrow: GUARDED — mark as borrowed if available
                    pred_app("eq_id", b, b2),
                    implication(
                        eq(app("get_status", L, b), const("available")),
                        eq(
                            app("get_status", app("borrow", L, b, u), b2),
                            const("borrowed"),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_borrow_hit_fail",
            forall(
                [L, b, b2, u],
                implication(  # get_status x borrow: PRESERVATION — preserve if not available
                    pred_app("eq_id", b, b2),
                    implication(
                        negation(eq(app("get_status", L, b), const("available"))),
                        eq(
                            app("get_status", app("borrow", L, b, u), b2),
                            app("get_status", L, b2),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_borrow_miss",
            forall(
                [L, b, b2, u],
                implication(  # get_status x borrow: KEY_MISS — delegate for other books
                    negation(pred_app("eq_id", b, b2)),
                    eq(
                        app("get_status", app("borrow", L, b, u), b2),
                        app("get_status", L, b2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_return_hit_succ",
            forall(
                [L, b, b2],
                implication(  # get_status x return: GUARDED — mark as available if borrowed
                    pred_app("eq_id", b, b2),
                    implication(
                        eq(app("get_status", L, b), const("borrowed")),
                        eq(
                            app("get_status", app("return_book", L, b), b2),
                            const("available"),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_return_hit_fail",
            forall(
                [L, b, b2],
                implication(  # get_status x return: PRESERVATION — preserve if not borrowed
                    pred_app("eq_id", b, b2),
                    implication(
                        negation(eq(app("get_status", L, b), const("borrowed"))),
                        eq(
                            app("get_status", app("return_book", L, b), b2),
                            app("get_status", L, b2),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_status_return_miss",
            forall(
                [L, b, b2],
                implication(  # get_status x return: KEY_MISS — delegate for other books
                    negation(pred_app("eq_id", b, b2)),
                    eq(
                        app("get_status", app("return_book", L, b), b2),
                        app("get_status", L, b2),
                    ),
                ),
            ),
        ),
        # == Borrower Management ==
        Axiom(
            "get_borrower_empty_undef",
            forall(
                [b],
                negation(
                    definedness(  # get_borrower x empty: UNDEF — no borrowers in empty library
                        app("get_borrower", const("empty"), b),
                    )
                ),
            ),
        ),
        Axiom(
            "get_borrower_register_hit",
            forall(
                [L, b, b2],
                implication(  # get_borrower x register: UNDEF — new books have no borrower
                    pred_app("eq_id", b, b2),
                    negation(
                        definedness(app("get_borrower", app("register", L, b), b2))
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_register_miss",
            forall(
                [L, b, b2],
                implication(  # get_borrower x register: KEY_MISS — delegate for other books
                    negation(pred_app("eq_id", b, b2)),
                    eq(
                        app("get_borrower", app("register", L, b), b2),
                        app("get_borrower", L, b2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_borrow_hit_succ",
            forall(
                [L, b, b2, u],
                implication(  # get_borrower x borrow: GUARDED — set borrower if available
                    pred_app("eq_id", b, b2),
                    implication(
                        eq(app("get_status", L, b), const("available")),
                        eq(app("get_borrower", app("borrow", L, b, u), b2), u),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_borrow_hit_fail",
            forall(
                [L, b, b2, u],
                implication(  # get_borrower x borrow: PRESERVATION — preserve if not available
                    pred_app("eq_id", b, b2),
                    implication(
                        negation(eq(app("get_status", L, b), const("available"))),
                        eq(
                            app("get_borrower", app("borrow", L, b, u), b2),
                            app("get_borrower", L, b2),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_borrow_miss",
            forall(
                [L, b, b2, u],
                implication(  # get_borrower x borrow: KEY_MISS — delegate for other books
                    negation(pred_app("eq_id", b, b2)),
                    eq(
                        app("get_borrower", app("borrow", L, b, u), b2),
                        app("get_borrower", L, b2),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_return_hit_succ",
            forall(
                [L, b, b2],
                implication(  # get_borrower x return: UNDEF — clear borrower if borrowed
                    pred_app("eq_id", b, b2),
                    implication(
                        eq(app("get_status", L, b), const("borrowed")),
                        negation(
                            definedness(
                                app("get_borrower", app("return_book", L, b), b2)
                            )
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_return_hit_fail",
            forall(
                [L, b, b2],
                implication(  # get_borrower x return: PRESERVATION — preserve if not borrowed
                    pred_app("eq_id", b, b2),
                    implication(
                        negation(eq(app("get_status", L, b), const("borrowed"))),
                        eq(
                            app("get_borrower", app("return_book", L, b), b2),
                            app("get_borrower", L, b2),
                        ),
                    ),
                ),
            ),
        ),
        Axiom(
            "get_borrower_return_miss",
            forall(
                [L, b, b2],
                implication(  # get_borrower x return: KEY_MISS — delegate for other books
                    negation(pred_app("eq_id", b, b2)),
                    eq(
                        app("get_borrower", app("return_book", L, b), b2),
                        app("get_borrower", L, b2),
                    ),
                ),
            ),
        ),
    )

    return Spec(name="LibraryLending", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Email Inbox
# ============================================================

EMAIL_INBOX = WorkedExample(
    domain_name="Email Inbox",
    summary="An email inbox implementation demonstrating collection patterns with keyed messages, read/unread state tracking, starring, and deletion, featuring key-based dispatch and explicit preservation rules.",
    patterns=frozenset({Pattern.COLLECTION_CONTAINER, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.DELEGATION, Pattern.OVERWRITE, Pattern.EXPLICIT_UNDEF, Pattern.PRESERVATION}),
    sorts=(
        SortInfo("MsgId", "KEY", "Opaque identifier for messages, acting as the key"),
        SortInfo("Inbox", "CONTAINER", "The main domain object, acting as a finite map/collection of messages"),
        SortInfo("Nat", FunctionRole.HELPER, "For tracking the unread count"),
    ),
    functions=(
        FunctionInfo("empty", "→ Inbox", FunctionRole.CONSTRUCTOR, "Creates an empty inbox"),
        FunctionInfo("receive", "Inbox × MsgId → Inbox", FunctionRole.CONSTRUCTOR, "Adds a new message"),
        FunctionInfo("mark_read", "Inbox × MsgId → Inbox", FunctionRole.CONSTRUCTOR, "Marks message as read"),
        FunctionInfo("mark_unread", "Inbox × MsgId → Inbox", FunctionRole.CONSTRUCTOR, "Marks message as unread"),
        FunctionInfo("delete", "Inbox × MsgId → Inbox", FunctionRole.CONSTRUCTOR, "Removes a message"),
        FunctionInfo("star", "Inbox × MsgId → Inbox", FunctionRole.CONSTRUCTOR, "Stars/unstars a message"),
        FunctionInfo("zero", "→ Nat", FunctionRole.HELPER, "Natural number zero"),
        FunctionInfo("suc", "Nat → Nat", FunctionRole.HELPER, "Natural number successor"),
        FunctionInfo("pred", "Nat → Nat", FunctionRole.HELPER, "Natural number predecessor"),
        FunctionInfo("unread_count", "Inbox → Nat", FunctionRole.OBSERVER, "Gets total unread messages"),
        FunctionInfo("eq_id", "MsgId × MsgId", FunctionRole.PREDICATE, "Message ID equality test"),
        FunctionInfo("has_msg", "Inbox × MsgId", FunctionRole.PREDICATE, "Tests message existence"),
        FunctionInfo("is_read", "Inbox × MsgId", FunctionRole.PREDICATE, "Tests if message is read"),
        FunctionInfo("is_starred", "Inbox × MsgId", FunctionRole.PREDICATE, "Tests if message is starred"),
    ),
    obligations=(
        ObligationCell("has_msg", "empty", CellType.BASIS, "false"),
        ObligationCell("has_msg", "receive", CellType.KEY_HIT, "true", "eq_id(m,m2)"),
        ObligationCell("has_msg", "receive", CellType.KEY_MISS, "has_msg(i,m2)", "¬eq_id(m,m2)"),
        ObligationCell("has_msg", "mark_read", CellType.PRESERVATION, "has_msg(i,m2)"),
        ObligationCell("has_msg", "mark_unread", CellType.PRESERVATION, "has_msg(i,m2)"),
        ObligationCell("has_msg", "delete", CellType.KEY_HIT, "false", "eq_id(m,m2)"),
        ObligationCell("has_msg", "delete", CellType.KEY_MISS, "has_msg(i,m2)", "¬eq_id(m,m2)"),
        ObligationCell("has_msg", "star", CellType.PRESERVATION, "has_msg(i,m2)"),
        ObligationCell("unread_count", "empty", CellType.BASIS, "zero"),
        ObligationCell("unread_count", "receive", CellType.GUARDED, "unread_count(i)", "has_msg(i,m)"),
        ObligationCell("unread_count", "receive", CellType.GUARDED, "suc(unread_count(i))", "¬has_msg(i,m)"),
    ),
    design_decisions=(
        DesignDecision("Missing Items", "Operations on missing items are preserved/no-ops to avoid zombie records"),
        DesignDecision("Unread Count", "Uses state-based dispatch via conjunctions rather than key dispatch"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def email_inbox_spec() -> Spec:

    # Variables
    i = var("i", "Inbox")
    m = var("m", "MsgId")
    m2 = var("m2", "MsgId")
    m3 = var("m3", "MsgId")
    n = var("n", "Nat")

    sig = Signature(
        sorts={
            "Inbox": atomic("Inbox"),
            "MsgId": atomic("MsgId"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Inbox constructors
            "empty": fn("empty", [], "Inbox"),
            "receive": fn("receive", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "mark_read": fn("mark_read", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "mark_unread": fn("mark_unread", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "delete": fn("delete", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "star": fn("star", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            # Nat helpers
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            "pred": fn("pred", [("n", "Nat")], "Nat"),
            # Observer
            "unread_count": fn("unread_count", [("i", "Inbox")], "Nat"),
        },
        predicates={
            "eq_id": pred("eq_id", [("m1", "MsgId"), ("m2", "MsgId")]),
            "has_msg": pred("has_msg", [("i", "Inbox"), ("m", "MsgId")]),
            "is_read": pred("is_read", [("i", "Inbox"), ("m", "MsgId")]),
            "is_starred": pred("is_starred", [("i", "Inbox"), ("m", "MsgId")]),
        },
        generated_sorts={
            "Inbox": GeneratedSortInfo(
                constructors=(
                    "empty",
                    "receive",
                    "mark_read",
                    "mark_unread",
                    "delete",
                    "star",
                ),
                selectors={},
            )
        },
    )

    axioms = (
        # == Basis: eq_id and pred ==
        # eq_id x reflexive: BASIS — Identity equals itself
        Axiom(label="eq_id_refl", formula=forall([m], pred_app("eq_id", m, m))),
        # eq_id x symmetric: BASIS — If a=b then b=a
        Axiom(
            label="eq_id_sym",
            formula=forall(
                [m, m2],
                implication(pred_app("eq_id", m, m2), pred_app("eq_id", m2, m)),
            ),
        ),
        # eq_id x transitive: BASIS — If a=b and b=c then a=c
        Axiom(
            label="eq_id_trans",
            formula=forall(
                [m, m2, m3],
                implication(
                    conjunction(pred_app("eq_id", m, m2), pred_app("eq_id", m2, m3)),
                    pred_app("eq_id", m, m3),
                ),
            ),
        ),
        # pred x zero: BASIS — pred(zero) = zero
        Axiom(label="pred_zero", formula=eq(app("pred", const("zero")), const("zero"))),
        # pred x suc: BASIS — pred(suc(n)) = n
        Axiom(label="pred_suc", formula=forall([n], eq(app("pred", app("suc", n)), n))),
        # == has_msg axioms ==
        # has_msg x empty: BASIS — Empty inbox has no messages
        Axiom(
            label="has_msg_empty",
            formula=forall([m], negation(pred_app("has_msg", const("empty"), m))),
        ),
        # has_msg x receive_hit: KEY_HIT — Message exists after receiving it
        Axiom(
            label="has_msg_receive_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    pred_app("has_msg", app("receive", i, m), m2),
                ),
            ),
        ),
        # has_msg x receive_miss: KEY_MISS — Other messages unaffected by receive
        Axiom(
            label="has_msg_receive_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("has_msg", app("receive", i, m), m2),
                        pred_app("has_msg", i, m2),
                    ),
                ),
            ),
        ),
        # has_msg x mark_read: PRESERVATION — Reading preserves existence
        Axiom(
            label="has_msg_mark_read",
            formula=forall(
                [i, m, m2],
                iff(
                    pred_app("has_msg", app("mark_read", i, m), m2),
                    pred_app("has_msg", i, m2),
                ),
            ),
        ),
        # has_msg x mark_unread: PRESERVATION — Unreading preserves existence
        Axiom(
            label="has_msg_mark_unread",
            formula=forall(
                [i, m, m2],
                iff(
                    pred_app("has_msg", app("mark_unread", i, m), m2),
                    pred_app("has_msg", i, m2),
                ),
            ),
        ),
        # has_msg x delete_hit: KEY_HIT — Message doesn't exist after deletion
        Axiom(
            label="has_msg_delete_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    negation(pred_app("has_msg", app("delete", i, m), m2)),
                ),
            ),
        ),
        # has_msg x delete_miss: KEY_MISS — Other messages unaffected by deletion
        Axiom(
            label="has_msg_delete_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("has_msg", app("delete", i, m), m2),
                        pred_app("has_msg", i, m2),
                    ),
                ),
            ),
        ),
        # has_msg x star: PRESERVATION — Starring preserves existence
        Axiom(
            label="has_msg_star",
            formula=forall(
                [i, m, m2],
                iff(
                    pred_app("has_msg", app("star", i, m), m2),
                    pred_app("has_msg", i, m2),
                ),
            ),
        ),
        # == is_read axioms ==
        # is_read x empty: BASIS — No read messages in empty inbox
        Axiom(
            label="is_read_empty",
            formula=forall([m], negation(pred_app("is_read", const("empty"), m))),
        ),
        # is_read x receive_hit: KEY_HIT — New message inherits read state
        Axiom(
            label="is_read_receive_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    iff(
                        pred_app("is_read", app("receive", i, m), m2),
                        conjunction(pred_app("has_msg", i, m2), pred_app("is_read", i, m2)),
                    ),
                ),
            ),
        ),
        # is_read x receive_miss: KEY_MISS — Other messages' read state preserved
        Axiom(
            label="is_read_receive_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_read", app("receive", i, m), m2),
                        pred_app("is_read", i, m2),
                    ),
                ),
            ),
        ),
        # is_read x mark_read_hit: KEY_HIT — Message becomes read if it exists
        Axiom(
            label="is_read_mark_read_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    iff(
                        pred_app("is_read", app("mark_read", i, m), m2),
                        pred_app("has_msg", i, m2),
                    ),
                ),
            ),
        ),
        # is_read x mark_read_miss: KEY_MISS — Other messages' read state preserved
        Axiom(
            label="is_read_mark_read_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_read", app("mark_read", i, m), m2),
                        pred_app("is_read", i, m2),
                    ),
                ),
            ),
        ),
        # is_read x mark_unread_hit: KEY_HIT — Message becomes unread
        Axiom(
            label="is_read_mark_unread_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    negation(pred_app("is_read", app("mark_unread", i, m), m2)),
                ),
            ),
        ),
        # is_read x mark_unread_miss: KEY_MISS — Other messages' read state preserved
        Axiom(
            label="is_read_mark_unread_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_read", app("mark_unread", i, m), m2),
                        pred_app("is_read", i, m2),
                    ),
                ),
            ),
        ),
        # is_read x delete_hit: KEY_HIT — Deleted message is not read
        Axiom(
            label="is_read_delete_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    negation(pred_app("is_read", app("delete", i, m), m2)),
                ),
            ),
        ),
        # is_read x delete_miss: KEY_MISS — Other messages' read state preserved
        Axiom(
            label="is_read_delete_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_read", app("delete", i, m), m2),
                        pred_app("is_read", i, m2),
                    ),
                ),
            ),
        ),
        # is_read x star: PRESERVATION — Starring preserves read state
        Axiom(
            label="is_read_star",
            formula=forall(
                [i, m, m2],
                iff(
                    pred_app("is_read", app("star", i, m), m2),
                    pred_app("is_read", i, m2),
                ),
            ),
        ),
        # == is_starred axioms ==
        # is_starred x empty: BASIS — No starred messages in empty inbox
        Axiom(
            label="is_starred_empty",
            formula=forall([m], negation(pred_app("is_starred", const("empty"), m))),
        ),
        # is_starred x receive_hit: KEY_HIT — New message inherits star state
        Axiom(
            label="is_starred_receive_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    iff(
                        pred_app("is_starred", app("receive", i, m), m2),
                        conjunction(pred_app("has_msg", i, m2),
                                pred_app("is_starred", i, m2)),
                    ),
                ),
            ),
        ),
        # is_starred x receive_miss: KEY_MISS — Other messages' star state preserved
        Axiom(
            label="is_starred_receive_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_starred", app("receive", i, m), m2),
                        pred_app("is_starred", i, m2),
                    ),
                ),
            ),
        ),
        # is_starred x mark_read: PRESERVATION — Reading preserves star state
        Axiom(
            label="is_starred_mark_read",
            formula=forall(
                [i, m, m2],
                iff(
                    pred_app("is_starred", app("mark_read", i, m), m2),
                    pred_app("is_starred", i, m2),
                ),
            ),
        ),
        # is_starred x mark_unread: PRESERVATION — Unreading preserves star state
        Axiom(
            label="is_starred_mark_unread",
            formula=forall(
                [i, m, m2],
                iff(
                    pred_app("is_starred", app("mark_unread", i, m), m2),
                    pred_app("is_starred", i, m2),
                ),
            ),
        ),
        # is_starred x delete_hit: KEY_HIT — Deleted message is not starred
        Axiom(
            label="is_starred_delete_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    negation(pred_app("is_starred", app("delete", i, m), m2)),
                ),
            ),
        ),
        # is_starred x delete_miss: KEY_MISS — Other messages' star state preserved
        Axiom(
            label="is_starred_delete_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_starred", app("delete", i, m), m2),
                        pred_app("is_starred", i, m2),
                    ),
                ),
            ),
        ),
        # is_starred x star_hit: KEY_HIT — Message becomes starred if it exists
        Axiom(
            label="is_starred_star_hit",
            formula=forall(
                [i, m, m2],
                implication(
                    pred_app("eq_id", m, m2),
                    iff(
                        pred_app("is_starred", app("star", i, m), m2),
                        pred_app("has_msg", i, m2),
                    ),
                ),
            ),
        ),
        # is_starred x star_miss: KEY_MISS — Other messages' star state preserved
        Axiom(
            label="is_starred_star_miss",
            formula=forall(
                [i, m, m2],
                implication(
                    negation(pred_app("eq_id", m, m2)),
                    iff(
                        pred_app("is_starred", app("star", i, m), m2),
                        pred_app("is_starred", i, m2),
                    ),
                ),
            ),
        ),
        # == unread_count axioms ==
        # unread_count x empty: BASIS — Empty inbox has zero unread
        Axiom(
            label="unread_count_empty",
            formula=eq(app("unread_count", const("empty")), const("zero")),
        ),
        # unread_count x receive: GUARDED — Increment only for new messages
        Axiom(
            label="unread_count_receive_preserve",
            formula=forall(
                [i, m],
                implication(
                    pred_app("has_msg", i, m),
                    eq(
                        app("unread_count", app("receive", i, m)),
                        app("unread_count", i),
                    ),
                ),
            ),
        ),
        Axiom(
            label="unread_count_receive_change",
            formula=forall(
                [i, m],
                implication(
                    negation(pred_app("has_msg", i, m)),
                    eq(
                        app("unread_count", app("receive", i, m)),
                        app("suc", app("unread_count", i)),
                    ),
                ),
            ),
        ),
        # unread_count x mark_read: GUARDED — Decrement only for unread messages
        Axiom(
            label="unread_count_mark_read_change",
            formula=forall(
                [i, m],
                implication(
                    conjunction(pred_app("has_msg", i, m),
                            negation(pred_app("is_read", i, m))),
                    eq(
                        app("unread_count", app("mark_read", i, m)),
                        app("pred", app("unread_count", i)),
                    ),
                ),
            ),
        ),
        Axiom(
            label="unread_count_mark_read_preserve",
            formula=forall(
                [i, m],
                implication(
                    negation(
                        conjunction(pred_app("has_msg", i, m),
                                negation(pred_app("is_read", i, m)))
                    ),
                    eq(
                        app("unread_count", app("mark_read", i, m)),
                        app("unread_count", i),
                    ),
                ),
            ),
        ),
        # unread_count x mark_unread: GUARDED — Increment only for read messages
        Axiom(
            label="unread_count_mark_unread_change",
            formula=forall(
                [i, m],
                implication(
                    conjunction(pred_app("has_msg", i, m), pred_app("is_read", i, m)),
                    eq(
                        app("unread_count", app("mark_unread", i, m)),
                        app("suc", app("unread_count", i)),
                    ),
                ),
            ),
        ),
        Axiom(
            label="unread_count_mark_unread_preserve",
            formula=forall(
                [i, m],
                implication(
                    negation(
                        conjunction(pred_app("has_msg", i, m), pred_app("is_read", i, m))
                    ),
                    eq(
                        app("unread_count", app("mark_unread", i, m)),
                        app("unread_count", i),
                    ),
                ),
            ),
        ),
        # unread_count x delete: GUARDED — Decrement only for unread messages
        Axiom(
            label="unread_count_delete_change",
            formula=forall(
                [i, m],
                implication(
                    conjunction(pred_app("has_msg", i, m),
                            negation(pred_app("is_read", i, m))),
                    eq(
                        app("unread_count", app("delete", i, m)),
                        app("pred", app("unread_count", i)),
                    ),
                ),
            ),
        ),
        Axiom(
            label="unread_count_delete_preserve",
            formula=forall(
                [i, m],
                implication(
                    negation(
                        conjunction(pred_app("has_msg", i, m),
                                negation(pred_app("is_read", i, m)))
                    ),
                    eq(
                        app("unread_count", app("delete", i, m)), app("unread_count", i)
                    ),
                ),
            ),
        ),
        # unread_count x star: PRESERVATION — Starring preserves unread count
        Axiom(
            label="unread_count_star",
            formula=forall(
                [i, m],
                eq(
                    app("unread_count", app("star", i, m)),
                    app("unread_count", i),
                ),
            ),
        ),
    )

    return Spec(name="EmailInbox", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Auction
# ============================================================

AUCTION = WorkedExample(
    domain_name="Auction",
    summary="Demonstrates a state-dependent auction system with key-based dispatch for bidders, guarded bid submission, and preservation of winner/bid state across operations",
    patterns=frozenset({Pattern.BOTH_GUARD_POL, Pattern.COLLECTION_CONTAINER, Pattern.COND_DEF, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.NESTED_GUARD, Pattern.PRESERVATION, Pattern.STATE_DEPENDENT}),
    sorts=(
        SortInfo("Auction", "CONTAINER", "Main domain state object storing auction configuration and bids"),
        SortInfo("Bidder", "KEY", "Opaque identifier for participating individuals"),
        SortInfo("Amount", "VALUE", "Opaque representation of money/bid value"),
    ),
    functions=(
        FunctionInfo("new", "→ Auction", FunctionRole.CONSTRUCTOR, "Creates blank, open auction"),
        FunctionInfo("register", "Auction × Bidder → Auction", FunctionRole.CONSTRUCTOR, "Idempotently registers a bidder"),
        FunctionInfo("submit", "Auction × Bidder × Amount →? Auction", FunctionRole.CONSTRUCTOR, "Submits bid if auction open and bidder registered"),
        FunctionInfo("close", "Auction → Auction", FunctionRole.CONSTRUCTOR, "Closes the auction"),
        FunctionInfo("is_open", "Auction", FunctionRole.PREDICATE, "True until auction closed"),
        FunctionInfo("is_registered", "Auction × Bidder", FunctionRole.PREDICATE, "True if bidder registered"),
        FunctionInfo("highest_bid", "Auction →? Amount", FunctionRole.PARTIAL_OBSERVER, "Highest recorded bid amount"),
        FunctionInfo("winner", "Auction →? Bidder", FunctionRole.PARTIAL_OBSERVER, "Bidder holding highest bid"),
        FunctionInfo("eq_bidder", "Bidder × Bidder", FunctionRole.HELPER, "Key equality for bidder dispatch"),
        FunctionInfo("gt", "Amount × Amount", FunctionRole.HELPER, "Strict greater-than for comparing bids"),
    ),
    obligations=(
        ObligationCell("is_open", "new", CellType.BASIS, "True"),
        ObligationCell("is_open", "register", CellType.PRESERVATION, "Preserved"),
        ObligationCell("is_open", "submit", CellType.PRESERVATION, "Preserved", "submit defined"),
        ObligationCell("is_open", "close", CellType.BASIS, "False"),
        ObligationCell("is_registered", "new", CellType.BASIS, "False"),
        ObligationCell("is_registered", "register", CellType.KEY_HIT, "True", "eq_bidder(b,b2)"),
        ObligationCell("is_registered", "register", CellType.KEY_MISS, "Delegate", "¬eq_bidder(b,b2)"),
        ObligationCell("is_registered", "submit", CellType.PRESERVATION, "Preserved", "submit defined"),
        ObligationCell("highest_bid", "new", CellType.UNDEF, "Undefined"),
        ObligationCell("highest_bid", "submit", CellType.GUARDED, "amt", "No prior bid"),
        ObligationCell("highest_bid", "submit", CellType.GUARDED, "amt", "gt(amt,current)"),
        ObligationCell("highest_bid", "submit", CellType.PRESERVATION, "Preserved", "¬gt(amt,current)"),
        ObligationCell("winner", "new", CellType.UNDEF, "Undefined"),
        ObligationCell("winner", "submit", CellType.GUARDED, "b", "No prior bid"),
        ObligationCell("winner", "submit", CellType.GUARDED, "b", "gt(amt,current)"),
        ObligationCell("winner", "submit", CellType.PRESERVATION, "Preserved", "¬gt(amt,current)"),
    ),
    design_decisions=(
        DesignDecision("Guarding Partial Constructors", "submit enforces deadline via is_open verification, requiring Definedness guards"),
        DesignDecision("Handling Ties", "First highest bid wins via strict gt evaluation"),
        DesignDecision("Sealed Bid Property", "winner/highest_bid update transparently via submit"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def auction_spec() -> Spec:
    # Variables for generic references inside axioms
    a = var("a", "Auction")
    b = var("b", "Bidder")
    b2 = var("b2", "Bidder")
    b3 = var("b3", "Bidder")
    amt = var("amt", "Amount")

    sig = Signature(
        sorts={
            "Auction": atomic("Auction"),
            "Bidder": atomic("Bidder"),
            "Amount": atomic("Amount"),
        },
        functions={
            # Constructors
            "new": fn("new", [], "Auction"),
            "register": fn("register", [("a", "Auction"), ("b", "Bidder")], "Auction"),
            "submit": fn(
                "submit",
                [("a", "Auction"), ("b", "Bidder"), ("amt", "Amount")],
                "Auction",
                total=False,
            ),
            "close": fn("close", [("a", "Auction")], "Auction"),
            # Partial State Observers
            "highest_bid": fn("highest_bid", [("a", "Auction")], "Amount", total=False),
            "winner": fn("winner", [("a", "Auction")], "Bidder", total=False),
        },
        predicates={
            # Foundation & Guards
            "eq_bidder": pred("eq_bidder", [("b1", "Bidder"), ("b2", "Bidder")]),
            "gt": pred("gt", [("amt1", "Amount"), ("amt2", "Amount")]),
            # Predicate Observers
            "is_open": pred("is_open", [("a", "Auction")]),
            "is_registered": pred("is_registered", [("a", "Auction"), ("b", "Bidder")]),
        },
        generated_sorts={
            "Auction": GeneratedSortInfo(
                constructors=("new", "register", "submit", "close"),
                selectors={},
            )
        },
    )

    axioms = (
        # == Helper Predicates ==
        # eq_bidder x refl: BASIS — reflexive property
        Axiom("eq_bidder_refl", forall([b], pred_app("eq_bidder", b, b))),
        # eq_bidder x sym: BASIS — symmetric property
        Axiom(
            "eq_bidder_sym",
            forall(
                [b, b2],
                implication(
                    pred_app("eq_bidder", b, b2),
                    pred_app("eq_bidder", b2, b),
                ),
            ),
        ),
        # eq_bidder x trans: BASIS — transitive property
        Axiom(
            "eq_bidder_trans",
            forall(
                [b, b2, b3],
                implication(
                    conjunction(pred_app("eq_bidder", b, b2), pred_app("eq_bidder", b2, b3)),
                    pred_app("eq_bidder", b, b3),
                ),
            ),
        ),
        # == Constructor Definedness ==
        # submit x definedness: GUARD — submit only defined for open auction with registered bidder
        Axiom(
            "submit_definedness",
            forall(
                [a, b, amt],
                iff(
                    definedness(app("submit", a, b, amt)),
                    conjunction(pred_app("is_open", a), pred_app("is_registered", a, b)),
                ),
            ),
        ),
        # == is_open Observer ==
        # is_open x new: BASIS — new auction starts open
        Axiom("is_open_new", pred_app("is_open", const("new"))),
        # is_open x register: PRESERVATION — registration preserves open state
        Axiom(
            "is_open_register",
            forall(
                [a, b],
                iff(
                    pred_app("is_open", app("register", a, b)),
                    pred_app("is_open", a),
                ),
            ),
        ),
        # is_open x submit: PRESERVATION — bid submission preserves open state
        Axiom(
            "is_open_submit",
            forall(
                [a, b, amt],
                implication(
                    definedness(app("submit", a, b, amt)),
                    iff(
                        pred_app("is_open", app("submit", a, b, amt)),
                        pred_app("is_open", a),
                    ),
                ),
            ),
        ),
        # is_open x close: BASIS — close operation makes auction not open
        Axiom(
            "is_open_close",
            forall(
                [a],
                negation(
                    pred_app("is_open", app("close", a)),
                ),
            ),
        ),
        # == is_registered Observer ==
        # is_registered x new: BASIS — new auction has no registered bidders
        Axiom(
            "is_registered_new",
            forall(
                [b],
                negation(
                    pred_app("is_registered", const("new"), b),
                ),
            ),
        ),
        # is_registered x register: KEY_HIT — matching bidder becomes registered
        Axiom(
            "is_registered_register_hit",
            forall(
                [a, b, b2],
                implication(
                    pred_app("eq_bidder", b, b2),
                    pred_app("is_registered", app("register", a, b), b2),
                ),
            ),
        ),
        # is_registered x register: KEY_MISS — non-matching bidder delegates to prior state
        Axiom(
            "is_registered_register_miss",
            forall(
                [a, b, b2],
                implication(
                    negation(pred_app("eq_bidder", b, b2)),
                    iff(
                        pred_app("is_registered", app("register", a, b), b2),
                        pred_app("is_registered", a, b2),
                    ),
                ),
            ),
        ),
        # is_registered x submit: PRESERVATION — bid submission preserves registration state
        Axiom(
            "is_registered_submit",
            forall(
                [a, b, b2, amt],
                implication(
                    definedness(app("submit", a, b, amt)),
                    iff(
                        pred_app("is_registered", app("submit", a, b, amt), b2),
                        pred_app("is_registered", a, b2),
                    ),
                ),
            ),
        ),
        # is_registered x close: PRESERVATION — closing preserves registration state
        Axiom(
            "is_registered_close",
            forall(
                [a, b],
                iff(
                    pred_app("is_registered", app("close", a), b),
                    pred_app("is_registered", a, b),
                ),
            ),
        ),
        # == highest_bid Observer ==
        # highest_bid x new: UNDEF — new auction has no bids
        Axiom(
            "highest_bid_new_undef",
            negation(definedness(app("highest_bid", const("new")))),
        ),
        # highest_bid x register: PRESERVATION — registration preserves highest bid
        Axiom(
            "highest_bid_register",
            forall(
                [a, b],
                eq(
                    app("highest_bid", app("register", a, b)),
                    app("highest_bid", a),
                ),
            ),
        ),
        # highest_bid x submit: GUARDED — first bid becomes highest
        Axiom(
            "highest_bid_submit_first",
            forall(
                [a, b, amt],
                implication(
                    conjunction(definedness(app("submit", a, b, amt)),
                            negation(definedness(app("highest_bid", a)))),
                    eq(app("highest_bid", app("submit", a, b, amt)), amt),
                ),
            ),
        ),
        # highest_bid x submit: GUARDED — higher bid becomes new highest
        Axiom(
            "highest_bid_submit_update",
            forall(
                [a, b, amt],
                implication(
                    conjunction(definedness(app("submit", a, b, amt)),
                            definedness(app("highest_bid", a)),
                            pred_app("gt", amt, app("highest_bid", a))),
                    eq(app("highest_bid", app("submit", a, b, amt)), amt),
                ),
            ),
        ),
        # highest_bid x submit: PRESERVATION — lower/equal bid preserves highest
        Axiom(
            "highest_bid_submit_keep",
            forall(
                [a, b, amt],
                implication(
                    conjunction(definedness(app("submit", a, b, amt)),
                            definedness(app("highest_bid", a)),
                            negation(pred_app("gt", amt, app("highest_bid", a)))),
                    eq(
                        app("highest_bid", app("submit", a, b, amt)),
                        app("highest_bid", a),
                    ),
                ),
            ),
        ),
        # highest_bid x close: PRESERVATION — closing preserves highest bid
        Axiom(
            "highest_bid_close",
            forall(
                [a],
                eq(
                    app("highest_bid", app("close", a)),
                    app("highest_bid", a),
                ),
            ),
        ),
        # == winner Observer ==
        # winner x new: UNDEF — new auction has no winner
        Axiom("winner_new_undef", negation(definedness(app("winner", const("new"))))),
        # winner x register: PRESERVATION — registration preserves winner
        Axiom(
            "winner_register",
            forall(
                [a, b],
                eq(
                    app("winner", app("register", a, b)),
                    app("winner", a),
                ),
            ),
        ),
        # winner x submit: GUARDED — first bidder becomes winner
        Axiom(
            "winner_submit_first",
            forall(
                [a, b, amt],
                implication(
                    conjunction(definedness(app("submit", a, b, amt)),
                            negation(definedness(app("highest_bid", a)))),
                    eq(app("winner", app("submit", a, b, amt)), b),
                ),
            ),
        ),
        # winner x submit: GUARDED — higher bidder becomes new winner
        Axiom(
            "winner_submit_update",
            forall(
                [a, b, amt],
                implication(
                    conjunction(definedness(app("submit", a, b, amt)),
                            definedness(app("highest_bid", a)),
                            pred_app("gt", amt, app("highest_bid", a))),
                    eq(app("winner", app("submit", a, b, amt)), b),
                ),
            ),
        ),
        # winner x submit: PRESERVATION — lower/equal bid preserves winner
        Axiom(
            "winner_submit_keep",
            forall(
                [a, b, amt],
                implication(
                    conjunction(definedness(app("submit", a, b, amt)),
                            definedness(app("highest_bid", a)),
                            negation(pred_app("gt", amt, app("highest_bid", a)))),
                    eq(app("winner", app("submit", a, b, amt)), app("winner", a)),
                ),
            ),
        ),
        # winner x close: PRESERVATION — closing preserves winner
        Axiom(
            "winner_close",
            forall(
                [a],
                eq(
                    app("winner", app("close", a)),
                    app("winner", a),
                ),
            ),
        ),
    )

    return Spec(name="Auction", signature=sig, axioms=axioms)
'''
)


# ============================================================
# Version History
# ============================================================

VERSION_HISTORY = WorkedExample(
    domain_name="Version History",
    summary="Demonstrates a keyed history container with partial observers requiring key dispatch and explicit undefined states for missing versions. Shows preservation across operations and complex diff computation with multiple keys.",
    patterns=frozenset({Pattern.COLLECTION_CONTAINER, Pattern.DELEGATION, Pattern.EXPLICIT_UNDEF, Pattern.KEYED_CONSTRUCTOR, Pattern.KEY_DISPATCH, Pattern.PRESERVATION, Pattern.STRUCT_RECUR}),
    sorts=(
        SortInfo("Content", "ATOMIC", "Opaque text payload for versioned content"),
        SortInfo("VersionId", "ATOMIC", "Opaque identifier for versions"),
        SortInfo("Diff", "ATOMIC", "Opaque representation of changes between versions"),
        SortInfo("Repo", "CONTAINER", "Central domain object holding version history"),
    ),
    functions=(
        FunctionInfo("init", "Content × VersionId → Repo", FunctionRole.CONSTRUCTOR, "Creates initial repository state with first commit"),
        FunctionInfo("commit", "Repo × Content × VersionId → Repo", FunctionRole.CONSTRUCTOR, "Records new version and updates current pointer"),
        FunctionInfo("revert", "Repo × VersionId → Repo", FunctionRole.CONSTRUCTOR, "Restores content to historic version"),
        FunctionInfo("compute_diff", "Content × Content → Diff", FunctionRole.HELPER, "Abstract diff computation between contents"),
        FunctionInfo("current_content", "Repo → Content", FunctionRole.OBSERVER, "Returns active content"),
        FunctionInfo("current_version", "Repo → VersionId", FunctionRole.OBSERVER, "Returns active version ID"),
        FunctionInfo("get_content", "Repo × VersionId →? Content", FunctionRole.PARTIAL_OBSERVER, "Retrieves historic content by version"),
        FunctionInfo("diff", "Repo × VersionId × VersionId →? Diff", FunctionRole.PARTIAL_OBSERVER, "Computes diff between two versions"),
        FunctionInfo("eq_id", "VersionId × VersionId → Bool", FunctionRole.PREDICATE, "Version ID equality"),
        FunctionInfo("has_version", "Repo × VersionId → Bool", FunctionRole.PREDICATE, "Checks if version exists in repo"),
    ),
    obligations=(
        ObligationCell("has_version", "init", CellType.KEY_HIT, "has_version(init(c,v), v2) ⇔ eq_id(v,v2)"),
        ObligationCell("has_version", "commit", CellType.KEY_HIT, "eq_id(v,v2) ⇒ has_version = true"),
        ObligationCell("has_version", "commit", CellType.KEY_MISS, "¬eq_id(v,v2) ⇒ delegate to r"),
        ObligationCell("has_version", "revert", CellType.PRESERVATION, "preserve has_version from r"),
        ObligationCell("current_content", "init", CellType.DOMAIN, "returns c"),
        ObligationCell("current_content", "commit", CellType.DOMAIN, "returns c"),
        ObligationCell("current_content", "revert", CellType.GUARDED, "if has_version then get_content else preserve"),
        ObligationCell("get_content", "init", CellType.KEY_HIT, "returns c if eq_id(v,v2)"),
        ObligationCell("get_content", "init", CellType.UNDEF, "undefined if ¬eq_id(v,v2)"),
        ObligationCell("get_content", "commit", CellType.KEY_HIT, "returns c if eq_id(v,v2)"),
        ObligationCell("get_content", "commit", CellType.KEY_MISS, "delegate to r if ¬eq_id(v,v2)"),
        ObligationCell("get_content", "revert", CellType.PRESERVATION, "preserve get_content from r"),
    ),
    design_decisions=(
        DesignDecision("Initial State", "Repository always starts with content to avoid empty state"),
        DesignDecision("Partial Operations", "get_content and diff are partial for missing versions"),
        DesignDecision("Current State", "Maintained through current_content/version observers"),
        DesignDecision("Version Existence", "Explicit has_version predicate for guards"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    conjunction,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def version_history_spec() -> Spec:

    # Variables for axioms
    r = var("r", "Repo")
    c = var("c", "Content")
    v = var("v", "VersionId")  # Main constructor key
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
            "commit": fn(
                "commit", [("r", "Repo"), ("c", "Content"), ("v", "VersionId")], "Repo"
            ),
            "revert": fn("revert", [("r", "Repo"), ("v", "VersionId")], "Repo"),
            # Uninterpreted
            "compute_diff": fn(
                "compute_diff", [("c1", "Content"), ("c2", "Content")], "Diff"
            ),
            # Observers
            "current_content": fn("current_content", [("r", "Repo")], "Content"),
            "current_version": fn("current_version", [("r", "Repo")], "VersionId"),
            "get_content": fn(
                "get_content",
                [("r", "Repo"), ("v", "VersionId")],
                "Content",
                total=False,
            ),
            "diff": fn(
                "diff",
                [("r", "Repo"), ("v1", "VersionId"), ("v2", "VersionId")],
                "Diff",
                total=False,
            ),
        },
        predicates={
            "eq_id": pred("eq_id", [("v1", "VersionId"), ("v2", "VersionId")]),
            "has_version": pred("has_version", [("r", "Repo"), ("v", "VersionId")]),
        },
        generated_sorts={
            "Repo": GeneratedSortInfo(
                constructors=("init", "commit", "revert"),
                selectors={},
            )
        },
    )

    axioms = (
        # == Version ID Equality ==
        # Basic reflexivity
        Axiom("eq_id_refl", forall([v], pred_app("eq_id", v, v))),
        # Symmetry of equality
        Axiom(
            "eq_id_sym",
            forall(
                [v1, v2],
                implication(
                    pred_app("eq_id", v1, v2),
                    pred_app("eq_id", v2, v1),
                ),
            ),
        ),
        # Transitivity of equality
        Axiom(
            "eq_id_trans",
            forall(
                [v1, v2, v3],
                implication(
                    conjunction(pred_app("eq_id", v1, v2), pred_app("eq_id", v2, v3)),
                    pred_app("eq_id", v1, v3),
                ),
            ),
        ),
        # == Version Existence Checks ==
        # init x has_version: KEY_HIT - Only initial version exists
        Axiom(
            "has_version_init",
            forall(
                [c, v, v2],
                iff(
                    pred_app("has_version", app("init", c, v), v2),
                    pred_app("eq_id", v, v2),
                ),
            ),
        ),
        # commit x has_version: KEY_HIT - New version exists
        Axiom(
            "has_version_commit_hit",
            forall(
                [r, c, v, v2],
                implication(
                    pred_app("eq_id", v, v2),
                    pred_app("has_version", app("commit", r, c, v), v2),
                ),
            ),
        ),
        # commit x has_version: KEY_MISS - Delegate to previous state
        Axiom(
            "has_version_commit_miss",
            forall(
                [r, c, v, v2],
                implication(
                    negation(pred_app("eq_id", v, v2)),
                    iff(
                        pred_app("has_version", app("commit", r, c, v), v2),
                        pred_app("has_version", r, v2),
                    ),
                ),
            ),
        ),
        # revert x has_version: PRESERVATION - Preserve all version existence
        Axiom(
            "has_version_revert",
            forall(
                [r, v, v2],
                iff(
                    pred_app("has_version", app("revert", r, v), v2),
                    pred_app("has_version", r, v2),
                ),
            ),
        ),
        # == Current Content Management ==
        # init x current_content: DOMAIN - Initial content
        Axiom(
            "current_content_init",
            forall([c, v], eq(app("current_content", app("init", c, v)), c)),
        ),
        # commit x current_content: DOMAIN - New content
        Axiom(
            "current_content_commit",
            forall([r, c, v], eq(app("current_content", app("commit", r, c, v)), c)),
        ),
        # revert x current_content: GUARDED - Restore if version exists
        Axiom(
            "current_content_revert_hit",
            forall(
                [r, v],
                implication(
                    pred_app("has_version", r, v),
                    eq(
                        app("current_content", app("revert", r, v)),
                        app("get_content", r, v),
                    ),
                ),
            ),
        ),
        # revert x current_content: PRESERVATION - Preserve if version missing
        Axiom(
            "current_content_revert_miss",
            forall(
                [r, v],
                implication(
                    negation(pred_app("has_version", r, v)),
                    eq(
                        app("current_content", app("revert", r, v)),
                        app("current_content", r),
                    ),
                ),
            ),
        ),
        # == Current Version Tracking ==
        # init x current_version: DOMAIN - Initial version
        Axiom(
            "current_version_init",
            forall([c, v], eq(app("current_version", app("init", c, v)), v)),
        ),
        # commit x current_version: DOMAIN - New version
        Axiom(
            "current_version_commit",
            forall([r, c, v], eq(app("current_version", app("commit", r, c, v)), v)),
        ),
        # revert x current_version: GUARDED - Switch if version exists
        Axiom(
            "current_version_revert_hit",
            forall(
                [r, v],
                implication(
                    pred_app("has_version", r, v),
                    eq(app("current_version", app("revert", r, v)), v),
                ),
            ),
        ),
        # revert x current_version: PRESERVATION - Preserve if version missing
        Axiom(
            "current_version_revert_miss",
            forall(
                [r, v],
                implication(
                    negation(pred_app("has_version", r, v)),
                    eq(
                        app("current_version", app("revert", r, v)),
                        app("current_version", r),
                    ),
                ),
            ),
        ),
        # == Content History Access ==
        # init x get_content: KEY_HIT - Initial content for initial version
        Axiom(
            "get_content_init_hit",
            forall(
                [c, v, v2],
                implication(
                    pred_app("eq_id", v, v2),
                    eq(app("get_content", app("init", c, v), v2), c),
                ),
            ),
        ),
        # init x get_content: UNDEF - Undefined for missing versions
        Axiom(
            "get_content_init_miss",
            forall(
                [c, v, v2],
                implication(
                    negation(pred_app("eq_id", v, v2)),
                    negation(definedness(app("get_content", app("init", c, v), v2))),
                ),
            ),
        ),
        # commit x get_content: KEY_HIT - New content for new version
        Axiom(
            "get_content_commit_hit",
            forall(
                [r, c, v, v2],
                implication(
                    pred_app("eq_id", v, v2),
                    eq(app("get_content", app("commit", r, c, v), v2), c),
                ),
            ),
        ),
        # commit x get_content: KEY_MISS - Delegate for other versions
        Axiom(
            "get_content_commit_miss",
            forall(
                [r, c, v, v2],
                implication(
                    negation(pred_app("eq_id", v, v2)),
                    eq(
                        app("get_content", app("commit", r, c, v), v2),
                        app("get_content", r, v2),
                    ),
                ),
            ),
        ),
        # revert x get_content: PRESERVATION - Preserve all historic content
        Axiom(
            "get_content_revert",
            forall(
                [r, v, v2],
                eq(
                    app("get_content", app("revert", r, v), v2),
                    app("get_content", r, v2),
                ),
            ),
        ),
        # == Diff Computation ==
        # init x diff: KEY_HIT - Same content for same version
        Axiom(
            "diff_init_hit_hit",
            forall(
                [c, v, v1, v2],
                implication(
                    conjunction(pred_app("eq_id", v, v1), pred_app("eq_id", v, v2)),
                    eq(
                        app("diff", app("init", c, v), v1, v2),
                        app("compute_diff", c, c),
                    ),
                ),
            ),
        ),
        # init x diff: UNDEF - Missing first version
        Axiom(
            "diff_init_hit_miss",
            forall(
                [c, v, v1, v2],
                implication(
                    conjunction(pred_app("eq_id", v, v1), negation(pred_app("eq_id", v, v2))),
                    negation(definedness(app("diff", app("init", c, v), v1, v2))),
                ),
            ),
        ),
        # init x diff: UNDEF - Missing second version
        Axiom(
            "diff_init_miss_hit",
            forall(
                [c, v, v1, v2],
                implication(
                    conjunction(negation(pred_app("eq_id", v, v1)), pred_app("eq_id", v, v2)),
                    negation(definedness(app("diff", app("init", c, v), v1, v2))),
                ),
            ),
        ),
        # init x diff: UNDEF - Both versions missing
        Axiom(
            "diff_init_miss_miss",
            forall(
                [c, v, v1, v2],
                implication(
                    conjunction(negation(pred_app("eq_id", v, v1)),
                            negation(pred_app("eq_id", v, v2))),
                    negation(definedness(app("diff", app("init", c, v), v1, v2))),
                ),
            ),
        ),
        # commit x diff: KEY_HIT - Same content for new version
        Axiom(
            "diff_commit_hit_hit",
            forall(
                [r, c, v, v1, v2],
                implication(
                    conjunction(pred_app("eq_id", v, v1), pred_app("eq_id", v, v2)),
                    eq(
                        app("diff", app("commit", r, c, v), v1, v2),
                        app("compute_diff", c, c),
                    ),
                ),
            ),
        ),
        # commit x diff: GUARDED - New to historic version
        Axiom(
            "diff_commit_hit_miss",
            forall(
                [r, c, v, v1, v2],
                implication(
                    conjunction(pred_app("eq_id", v, v1), negation(pred_app("eq_id", v, v2))),
                    implication(
                        pred_app("has_version", r, v2),
                        eq(
                            app("diff", app("commit", r, c, v), v1, v2),
                            app("compute_diff", c, app("get_content", r, v2)),
                        ),
                    ),
                ),
            ),
        ),
        # commit x diff: UNDEF - Second version missing
        Axiom(
            "diff_commit_hit_miss_noversion",
            forall(
                [r, c, v, v1, v2],
                implication(
                    conjunction(pred_app("eq_id", v, v1), negation(pred_app("eq_id", v, v2))),
                    implication(
                        negation(pred_app("has_version", r, v2)),
                        negation(
                            definedness(app("diff", app("commit", r, c, v), v1, v2))
                        ),
                    ),
                ),
            ),
        ),
        # commit x diff: GUARDED - Historic to new version
        Axiom(
            "diff_commit_miss_hit",
            forall(
                [r, c, v, v1, v2],
                implication(
                    conjunction(negation(pred_app("eq_id", v, v1)), pred_app("eq_id", v, v2)),
                    implication(
                        pred_app("has_version", r, v1),
                        eq(
                            app("diff", app("commit", r, c, v), v1, v2),
                            app("compute_diff", app("get_content", r, v1), c),
                        ),
                    ),
                ),
            ),
        ),
        # commit x diff: UNDEF - First version missing
        Axiom(
            "diff_commit_miss_hit_noversion",
            forall(
                [r, c, v, v1, v2],
                implication(
                    conjunction(negation(pred_app("eq_id", v, v1)), pred_app("eq_id", v, v2)),
                    implication(
                        negation(pred_app("has_version", r, v1)),
                        negation(
                            definedness(app("diff", app("commit", r, c, v), v1, v2))
                        ),
                    ),
                ),
            ),
        ),
        # commit x diff: KEY_MISS - Both versions historic
        Axiom(
            "diff_commit_miss_miss",
            forall(
                [r, c, v, v1, v2],
                implication(
                    conjunction(negation(pred_app("eq_id", v, v1)),
                            negation(pred_app("eq_id", v, v2))),
                    eq(
                        app("diff", app("commit", r, c, v), v1, v2),
                        app("diff", r, v1, v2),
                    ),
                ),
            ),
        ),
        # revert x diff: PRESERVATION - Preserve all diffs
        Axiom(
            "diff_revert",
            forall(
                [r, v, v1, v2],
                eq(
                    app("diff", app("revert", r, v), v1, v2),
                    app("diff", r, v1, v2),
                ),
            ),
        ),
    )

    return Spec(name="VersionHistory", signature=sig, axioms=axioms)
'''
)



# ============================================================
# Stack
# ============================================================

STACK = WorkedExample(
    domain_name="Stack",
    summary="Selectors + explicit undefinedness on foreign constructors",

    patterns=frozenset({
        Pattern.SEL_EXTRACT,
        Pattern.EXPLICIT_UNDEF,
    }),

    sorts=(
        SortInfo("Stack", "primary domain sort", "The collection being modeled. Atomic."),
        SortInfo("Elem", "element type", "The type of elements stored in the stack. Atomic."),
    ),

    functions=(
        FunctionInfo("new", "-> Stack", FunctionRole.CONSTANT,
                     "Creates an empty stack."),
        FunctionInfo("push", "Stack x Elem -> Stack", FunctionRole.CONSTRUCTOR,
                     "Adds an element to the top. Total."),
        FunctionInfo("pop", "Stack ->? Stack", FunctionRole.SELECTOR,
                     "Selector of push. Extracts the Stack component. Undefined on new."),
        FunctionInfo("top", "Stack ->? Elem", FunctionRole.SELECTOR,
                     "Selector of push. Extracts the Elem component. Undefined on new."),
        FunctionInfo("empty", "Stack", FunctionRole.PREDICATE,
                     "True iff the stack has no elements. Total."),
    ),

    obligations=(
        ObligationCell("pop", "new", CellType.SELECTOR_FOREIGN,
                       "neg def(pop(new))"),
        ObligationCell("pop", "push", CellType.SELECTOR_EXTRACT,
                       "pop(push(s, e)) = s"),
        ObligationCell("top", "new", CellType.SELECTOR_FOREIGN,
                       "neg def(top(new))"),
        ObligationCell("top", "push", CellType.SELECTOR_EXTRACT,
                       "top(push(s, e)) = e"),
        ObligationCell("empty", "new", CellType.DOMAIN,
                       "empty(new)"),
        ObligationCell("empty", "push", CellType.DOMAIN,
                       "neg empty(push(s, e))"),
    ),

    design_decisions=(
        DesignDecision(
            "Selectors in generated_sorts",
            "pop and top are declared as selectors of push. Their extraction axioms "
            "on push are mechanically derivable; their behavior on new requires "
            "explicit neg def(...) axioms."
        ),
        DesignDecision(
            "Predicate observer",
            "empty is a predicate (PredApp), not a boolean-returning function. "
            "Use Negation(PredApp(...)) for the push case."
        ),
        DesignDecision(
            "Loose semantics",
            "pop_new_undef and top_new_undef are mandatory. Omitting them leaves "
            "values unconstrained, not undefined."
        ),
    ),

    code="""from alspec import (
    Axiom,
    Definedness,
    GeneratedSortInfo,
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
)


def stack_spec() -> Spec:
    sig = Signature(
        sorts={
            "Stack": atomic("Stack"),
            "Elem": atomic("Elem"),
        },
        functions={
            "new": fn("new", [], "Stack"),
            "push": fn("push", [("s", "Stack"), ("e", "Elem")], "Stack"),
            "pop": fn("pop", [("s", "Stack")], "Stack", total=False),
            "top": fn("top", [("s", "Stack")], "Elem", total=False),
        },
        predicates={
            "empty": pred("empty", [("s", "Stack")]),
        },
        generated_sorts={
            "Stack": GeneratedSortInfo(
                constructors=("new", "push"),
                selectors={"push": {"top": "Elem", "pop": "Stack"}},
            )
        },
    )

    s = var("s", "Stack")
    e = var("e", "Elem")

    axioms = (
        # pop x new: SELECTOR_FOREIGN — explicit undefinedness
        Axiom(
            label="pop_new_undef",
            formula=Negation(Definedness(app("pop", const("new")))),
        ),
        # pop x push: SELECTOR_EXTRACT
        Axiom(
            label="pop_push",
            formula=forall([s, e], eq(app("pop", app("push", s, e)), s)),
        ),
        # top x new: SELECTOR_FOREIGN — explicit undefinedness
        Axiom(
            label="top_new_undef",
            formula=Negation(Definedness(app("top", const("new")))),
        ),
        # top x push: SELECTOR_EXTRACT
        Axiom(
            label="top_push",
            formula=forall([s, e], eq(app("top", app("push", s, e)), e)),
        ),
        # empty x new: DOMAIN — base case, predicate holds
        Axiom(
            label="empty_new",
            formula=PredApp("empty", (const("new"),)),
        ),
        # empty x push: DOMAIN — recursive case, predicate negated
        Axiom(
            label="not_empty_push",
            formula=forall(
                [s, e],
                Negation(
                    PredApp("empty", (app("push", s, e),)),
                ),
            ),
        ),
    )

    return Spec(name="Stack", signature=sig, axioms=axioms)
""",
)


# ============================================================
# Bug Tracker
# ============================================================

BUG_TRACKER = WorkedExample(
    domain_name="Bug Tracker",
    summary="Key dispatch, preservation, partial observers, guard polarity, uninterpreted functions",

    patterns=frozenset({
        Pattern.COLLECTION_CONTAINER,
        Pattern.KEYED_CONSTRUCTOR,
        Pattern.KEY_DISPATCH,
        Pattern.DELEGATION,
        Pattern.OVERWRITE,
        Pattern.PRESERVATION,
        Pattern.EXPLICIT_UNDEF,
        Pattern.DOUBLY_PARTIAL,
        Pattern.BICOND_CHAR,
        Pattern.UNINTERP_FN,
        Pattern.NESTED_GUARD,
        Pattern.BOTH_GUARD_POL,
        Pattern.TRANSITIVE_CLOSURE,
        Pattern.ENUMERATION,
    }),

    sorts=(
        SortInfo("Store", "primary domain sort",
                 "Collection of tickets indexed by TicketId. Follows the FiniteMap pattern."),
        SortInfo("TicketId", "key sort",
                 "Opaque identifier. No internal structure needed."),
        SortInfo("Title", "data sort", "Opaque. Passed to classify."),
        SortInfo("Body", "data sort", "Opaque. Passed to classify."),
        SortInfo("UserId", "data sort", "Opaque identifier for assignees."),
        SortInfo("Status", "enumeration",
                 "Finite: open, resolved. Modeled as atomic with nullary constructors."),
        SortInfo("SeverityLevel", "data sort",
                 "Atomic. high is a named constant for is_critical; classify determines severity."),
    ),

    functions=(
        # Store constructors
        FunctionInfo("empty", "-> Store", FunctionRole.CONSTANT,
                     "Empty store, no tickets."),
        FunctionInfo("create_ticket", "Store x TicketId x Title x Body -> Store",
                     FunctionRole.CONSTRUCTOR,
                     "Adds a ticket. Total."),
        FunctionInfo("resolve_ticket", "Store x TicketId -> Store",
                     FunctionRole.CONSTRUCTOR,
                     "Transitions status. Total (no-op on nonexistent ticket)."),
        FunctionInfo("assign_ticket", "Store x TicketId x UserId -> Store",
                     FunctionRole.CONSTRUCTOR,
                     "Sets assignee. Total (no-op on nonexistent ticket)."),

        # Constants
        FunctionInfo("open", "-> Status", FunctionRole.CONSTANT, "Enumeration value."),
        FunctionInfo("resolved", "-> Status", FunctionRole.CONSTANT, "Enumeration value."),
        FunctionInfo("high", "-> SeverityLevel", FunctionRole.CONSTANT,
                     "Needed for is_critical definition."),

        # Uninterpreted
        FunctionInfo("classify", "Title x Body -> SeverityLevel", FunctionRole.HELPER,
                     "Uninterpreted. Appears in axioms but not defined by them."),

        # Partial observers
        FunctionInfo("get_status", "Store x TicketId ->? Status",
                     FunctionRole.PARTIAL_OBSERVER,
                     "Undefined if ticket doesn't exist."),
        FunctionInfo("get_severity", "Store x TicketId ->? SeverityLevel",
                     FunctionRole.PARTIAL_OBSERVER,
                     "Undefined if ticket doesn't exist."),
        FunctionInfo("get_assignee", "Store x TicketId ->? UserId",
                     FunctionRole.PARTIAL_OBSERVER,
                     "Doubly partial: undefined if ticket doesn't exist AND if no assignee set."),

        # Predicates
        FunctionInfo("eq_id", "TicketId x TicketId", FunctionRole.PREDICATE,
                     "Key equality for dispatch. Use PredApp everywhere."),
        FunctionInfo("has_ticket", "Store x TicketId", FunctionRole.PREDICATE,
                     "True iff ticket exists. Total."),
        FunctionInfo("is_critical", "Store x TicketId", FunctionRole.PREDICATE,
                     "True iff ticket exists and severity is high."),
    ),

    obligations=(
        # eq_id basis (3 axioms)
        ObligationCell("eq_id", "—", CellType.DOMAIN, "eq_id(k, k) [reflexivity]"),
        ObligationCell("eq_id", "—", CellType.DOMAIN, "eq_id(k, k2) -> eq_id(k2, k) [symmetry]"),
        ObligationCell("eq_id", "—", CellType.DOMAIN,
                       "eq_id(k, k2) and eq_id(k2, k3) -> eq_id(k, k3) [transitivity]"),

        # has_ticket (5 axioms)
        ObligationCell("has_ticket", "empty", CellType.DOMAIN, "neg has_ticket(empty, k)"),
        ObligationCell("has_ticket", "create_ticket", CellType.KEY_HIT,
                       "has_ticket(create_ticket(s,k,t,b), k2)", guard="eq_id(k, k2)"),
        ObligationCell("has_ticket", "create_ticket", CellType.KEY_MISS,
                       "has_ticket(..., k2) iff has_ticket(s, k2)", guard="neg eq_id(k, k2)"),
        ObligationCell("has_ticket", "resolve_ticket", CellType.PRESERVATION,
                       "has_ticket(resolve_ticket(s,k), k2) iff has_ticket(s, k2)"),
        ObligationCell("has_ticket", "assign_ticket", CellType.PRESERVATION,
                       "has_ticket(assign_ticket(s,k,u), k2) iff has_ticket(s, k2)"),

        # get_status (7 axioms)
        ObligationCell("get_status", "empty", CellType.UNDEF,
                       "neg def(get_status(empty, k))"),
        ObligationCell("get_status", "create_ticket", CellType.KEY_HIT,
                       "get_status(..., k2) = open", guard="eq_id(k, k2)"),
        ObligationCell("get_status", "create_ticket", CellType.KEY_MISS,
                       "get_status(..., k2) = get_status(s, k2)", guard="neg eq_id(k, k2)"),
        ObligationCell("get_status", "resolve_ticket", CellType.KEY_HIT,
                       "get_status(..., k2) = resolved",
                       guard="eq_id(k, k2) and has_ticket(s, k)"),
        ObligationCell("get_status", "resolve_ticket", CellType.KEY_HIT,
                       "get_status(..., k2) = get_status(s, k2)",
                       guard="eq_id(k, k2) and neg has_ticket(s, k)"),
        ObligationCell("get_status", "resolve_ticket", CellType.KEY_MISS,
                       "get_status(..., k2) = get_status(s, k2)", guard="neg eq_id(k, k2)"),
        ObligationCell("get_status", "assign_ticket", CellType.PRESERVATION,
                       "get_status(assign_ticket(s,k,u), k2) = get_status(s, k2)"),

        # get_severity (5 axioms)
        ObligationCell("get_severity", "empty", CellType.UNDEF,
                       "neg def(get_severity(empty, k))"),
        ObligationCell("get_severity", "create_ticket", CellType.KEY_HIT,
                       "get_severity(..., k2) = classify(t, b)", guard="eq_id(k, k2)"),
        ObligationCell("get_severity", "create_ticket", CellType.KEY_MISS,
                       "get_severity(..., k2) = get_severity(s, k2)", guard="neg eq_id(k, k2)"),
        ObligationCell("get_severity", "resolve_ticket", CellType.PRESERVATION,
                       "get_severity(resolve_ticket(s,k), k2) = get_severity(s, k2)"),
        ObligationCell("get_severity", "assign_ticket", CellType.PRESERVATION,
                       "get_severity(assign_ticket(s,k,u), k2) = get_severity(s, k2)"),

        # get_assignee (7 axioms)
        ObligationCell("get_assignee", "empty", CellType.UNDEF,
                       "neg def(get_assignee(empty, k))"),
        ObligationCell("get_assignee", "create_ticket", CellType.KEY_HIT,
                       "neg def(get_assignee(create_ticket(s,k,t,b), k2))",
                       guard="eq_id(k, k2)"),
        ObligationCell("get_assignee", "create_ticket", CellType.KEY_MISS,
                       "get_assignee(..., k2) = get_assignee(s, k2)", guard="neg eq_id(k, k2)"),
        ObligationCell("get_assignee", "assign_ticket", CellType.KEY_HIT,
                       "get_assignee(..., k2) = u",
                       guard="eq_id(k, k2) and has_ticket(s, k)"),
        ObligationCell("get_assignee", "assign_ticket", CellType.KEY_HIT,
                       "get_assignee(..., k2) = get_assignee(s, k2)",
                       guard="eq_id(k, k2) and neg has_ticket(s, k)"),
        ObligationCell("get_assignee", "assign_ticket", CellType.KEY_MISS,
                       "get_assignee(..., k2) = get_assignee(s, k2)", guard="neg eq_id(k, k2)"),
        ObligationCell("get_assignee", "resolve_ticket", CellType.PRESERVATION,
                       "get_assignee(resolve_ticket(s,k), k2) = get_assignee(s, k2)"),

        # is_critical (5 axioms)
        ObligationCell("is_critical", "empty", CellType.DOMAIN,
                       "neg is_critical(empty, k)"),
        ObligationCell("is_critical", "create_ticket", CellType.KEY_HIT,
                       "is_critical(..., k2) iff classify(t,b) = high",
                       guard="eq_id(k, k2)"),
        ObligationCell("is_critical", "create_ticket", CellType.KEY_MISS,
                       "is_critical(..., k2) iff is_critical(s, k2)",
                       guard="neg eq_id(k, k2)"),
        ObligationCell("is_critical", "resolve_ticket", CellType.PRESERVATION,
                       "is_critical(resolve_ticket(s,k), k2) iff is_critical(s, k2)"),
        ObligationCell("is_critical", "assign_ticket", CellType.PRESERVATION,
                       "is_critical(assign_ticket(s,k,u), k2) iff is_critical(s, k2)"),
    ),

    design_decisions=(
        DesignDecision(
            "FiniteMap pattern",
            "Store is a collection indexed by TicketId. Individual tickets are NOT a "
            "separate sort — all properties are accessed through store observers with a key."
        ),
        DesignDecision(
            "Key dispatch",
            "Every (observer, keyed-constructor) pair splits into hit (eq_id holds) and "
            "miss (neg eq_id). Use Implication(PredApp('eq_id', ...), ...) for hit, "
            "Implication(Negation(PredApp('eq_id', ...)), ...) for miss."
        ),
        DesignDecision(
            "Universal preservation",
            "When a constructor doesn't affect an observer at ANY key, collapse hit/miss "
            "into one unguarded equation. resolve_ticket preserves get_severity; "
            "assign_ticket preserves get_status."
        ),
        DesignDecision(
            "Doubly partial get_assignee",
            "Undefined if ticket doesn't exist AND if ticket exists but has no assignee. "
            "create_ticket hit gets explicit neg def(...) — new tickets have no assignee."
        ),
        DesignDecision(
            "Both guard polarities",
            "When guarded by has_ticket, write axioms for BOTH positive and negative cases. "
            "Example: resolve_ticket hit splits into has_ticket (set resolved) and "
            "neg has_ticket (delegate/no-op)."
        ),
        DesignDecision(
            "Uninterpreted classify",
            "classify : Title x Body -> SeverityLevel appears in axioms but is not defined "
            "by them. At implementation time, could be an LLM call, rules engine, etc."
        ),
    ),

    code="""from alspec import (
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


def bug_tracker_spec() -> Spec:
    # Variables — declared before signature for readability
    s = var("s", "Store")
    k = var("k", "TicketId")
    k2 = var("k2", "TicketId")
    k3 = var("k3", "TicketId")
    t = var("t", "Title")
    b = var("b", "Body")
    u = var("u", "UserId")

    sig = Signature(
        sorts={
            "TicketId": atomic("TicketId"),
            "Title": atomic("Title"),
            "Body": atomic("Body"),
            "SeverityLevel": atomic("SeverityLevel"),
            "Status": atomic("Status"),
            "UserId": atomic("UserId"),
            "Store": atomic("Store"),
        },
        functions={
            # Store constructors
            "empty": fn("empty", [], "Store"),
            "create_ticket": fn(
                "create_ticket",
                [("s", "Store"), ("k", "TicketId"), ("t", "Title"), ("b", "Body")],
                "Store",
            ),
            "resolve_ticket": fn(
                "resolve_ticket", [("s", "Store"), ("k", "TicketId")], "Store"
            ),
            "assign_ticket": fn(
                "assign_ticket",
                [("s", "Store"), ("k", "TicketId"), ("u", "UserId")],
                "Store",
            ),
            # Uninterpreted function — appears in axioms, not defined by them
            "classify": fn(
                "classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"
            ),
            # Partial observers — undefined if ticket doesn't exist
            "get_status": fn(
                "get_status", [("s", "Store"), ("k", "TicketId")], "Status", total=False
            ),
            "get_severity": fn(
                "get_severity",
                [("s", "Store"), ("k", "TicketId")],
                "SeverityLevel",
                total=False,
            ),
            "get_assignee": fn(
                "get_assignee",
                [("s", "Store"), ("k", "TicketId")],
                "UserId",
                total=False,
            ),
            # Status constants
            "open": fn("open", [], "Status"),
            "resolved": fn("resolved", [], "Status"),
            # SeverityLevel constant — needed for is_critical
            "high": fn("high", [], "SeverityLevel"),
        },
        predicates={
            # Key equality for dispatch — use PredApp everywhere
            "eq_id": pred("eq_id", [("k1", "TicketId"), ("k2", "TicketId")]),
            # Ticket existence — total predicate over store
            "has_ticket": pred("has_ticket", [("s", "Store"), ("k", "TicketId")]),
            # Criticality — derived from severity
            "is_critical": pred("is_critical", [("s", "Store"), ("k", "TicketId")]),
        },
        generated_sorts={
            "Store": GeneratedSortInfo(
                constructors=(
                    "empty",
                    "create_ticket",
                    "resolve_ticket",
                    "assign_ticket",
                ),
                selectors={},
            )
        },
    )

    axioms = (
        # == eq_id basis (3 axioms) ==============================
        # Reflexivity: every key equals itself
        Axiom(
            label="eq_id_refl",
            formula=forall([k], PredApp("eq_id", (k, k))),
        ),
        # Symmetry: equality is bidirectional
        Axiom(
            label="eq_id_sym",
            formula=forall(
                [k, k2],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    PredApp("eq_id", (k2, k)),
                ),
            ),
        ),
        # Transitivity: equality chains
        Axiom(
            label="eq_id_trans",
            formula=forall(
                [k, k2, k3],
                Implication(
                    conjunction(PredApp("eq_id", (k, k2)),
                            PredApp("eq_id", (k2, k3))),
                    PredApp("eq_id", (k, k3)),
                ),
            ),
        ),
        # == has_ticket (5 axioms) ===============================
        # has_ticket x empty: no tickets in empty store
        Axiom(
            label="has_ticket_empty",
            formula=forall([k], Negation(PredApp("has_ticket", (const("empty"), k)))),
        ),
        # has_ticket x create_ticket HIT: creating makes it exist
        Axiom(
            label="has_ticket_create_hit",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),
                ),
            ),
        ),
        # has_ticket x create_ticket MISS: other tickets unchanged
        Axiom(
            label="has_ticket_create_miss",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    iff(
                        PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),
                        PredApp("has_ticket", (s, k2)),
                    ),
                ),
            ),
        ),
        # has_ticket x resolve_ticket: PRESERVATION
        Axiom(
            label="has_ticket_resolve",
            formula=forall(
                [s, k, k2],
                iff(
                    PredApp("has_ticket", (app("resolve_ticket", s, k), k2)),
                    PredApp("has_ticket", (s, k2)),
                ),
            ),
        ),
        # has_ticket x assign_ticket: PRESERVATION
        Axiom(
            label="has_ticket_assign",
            formula=forall(
                [s, k, k2, u],
                iff(
                    PredApp("has_ticket", (app("assign_ticket", s, k, u), k2)),
                    PredApp("has_ticket", (s, k2)),
                ),
            ),
        ),
        # == Partial observer x empty: all undefined (3 axioms) ==
        # get_status x empty: undefined — no ticket to query
        Axiom(
            label="get_status_empty_undef",
            formula=forall(
                [k], Negation(Definedness(app("get_status", const("empty"), k)))
            ),
        ),
        # get_severity x empty: undefined
        Axiom(
            label="get_severity_empty_undef",
            formula=forall(
                [k], Negation(Definedness(app("get_severity", const("empty"), k)))
            ),
        ),
        # get_assignee x empty: undefined
        Axiom(
            label="get_assignee_empty_undef",
            formula=forall(
                [k], Negation(Definedness(app("get_assignee", const("empty"), k)))
            ),
        ),
        # == get_status (4 more axioms) ==========================
        # get_status x create_ticket HIT: new tickets start as open
        Axiom(
            label="get_status_create_hit",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    eq(
                        app("get_status", app("create_ticket", s, k, t, b), k2),
                        const("open"),
                    ),
                ),
            ),
        ),
        # get_status x create_ticket MISS: delegates to inner store
        Axiom(
            label="get_status_create_miss",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    eq(
                        app("get_status", app("create_ticket", s, k, t, b), k2),
                        app("get_status", s, k2),
                    ),
                ),
            ),
        ),
        # get_status x resolve_ticket HIT + has_ticket: mark resolved
        Axiom(
            label="get_status_resolve_hit",
            formula=forall(
                [s, k, k2],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    Implication(
                        PredApp("has_ticket", (s, k)),
                        eq(
                            app("get_status", app("resolve_ticket", s, k), k2),
                            const("resolved"),
                        ),
                    ),
                ),
            ),
        ),
        # get_status x resolve_ticket HIT + neg has_ticket: no-op, delegate
        Axiom(
            label="get_status_resolve_hit_noticket",
            formula=forall(
                [s, k, k2],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    Implication(
                        Negation(PredApp("has_ticket", (s, k))),
                        eq(
                            app("get_status", app("resolve_ticket", s, k), k2),
                            app("get_status", s, k2),
                        ),
                    ),
                ),
            ),
        ),
        # get_status x resolve_ticket MISS: delegates
        Axiom(
            label="get_status_resolve_miss",
            formula=forall(
                [s, k, k2],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    eq(
                        app("get_status", app("resolve_ticket", s, k), k2),
                        app("get_status", s, k2),
                    ),
                ),
            ),
        ),
        # get_status x assign_ticket: PRESERVATION
        Axiom(
            label="get_status_assign",
            formula=forall(
                [s, k, k2, u],
                eq(
                    app("get_status", app("assign_ticket", s, k, u), k2),
                    app("get_status", s, k2),
                ),
            ),
        ),
        # == get_severity (4 more axioms) ========================
        # get_severity x create_ticket HIT: severity from classify
        Axiom(
            label="get_severity_create_hit",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    eq(
                        app("get_severity", app("create_ticket", s, k, t, b), k2),
                        app("classify", t, b),
                    ),
                ),
            ),
        ),
        # get_severity x create_ticket MISS: delegates
        Axiom(
            label="get_severity_create_miss",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    eq(
                        app("get_severity", app("create_ticket", s, k, t, b), k2),
                        app("get_severity", s, k2),
                    ),
                ),
            ),
        ),
        # get_severity x resolve_ticket: PRESERVATION
        Axiom(
            label="get_severity_resolve",
            formula=forall(
                [s, k, k2],
                eq(
                    app("get_severity", app("resolve_ticket", s, k), k2),
                    app("get_severity", s, k2),
                ),
            ),
        ),
        # get_severity x assign_ticket: PRESERVATION
        Axiom(
            label="get_severity_assign",
            formula=forall(
                [s, k, k2, u],
                eq(
                    app("get_severity", app("assign_ticket", s, k, u), k2),
                    app("get_severity", s, k2),
                ),
            ),
        ),
        # == get_assignee (4 more axioms) ========================
        # get_assignee x create_ticket HIT: explicit undef — no assignee yet
        Axiom(
            label="get_assignee_create_hit",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    Negation(
                        Definedness(
                            app("get_assignee", app("create_ticket", s, k, t, b), k2)
                        )
                    ),
                ),
            ),
        ),
        # get_assignee x create_ticket MISS: delegates
        Axiom(
            label="get_assignee_create_miss",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    eq(
                        app("get_assignee", app("create_ticket", s, k, t, b), k2),
                        app("get_assignee", s, k2),
                    ),
                ),
            ),
        ),
        # get_assignee x assign_ticket HIT + has_ticket: set assignee
        Axiom(
            label="get_assignee_assign_hit",
            formula=forall(
                [s, k, k2, u],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    Implication(
                        PredApp("has_ticket", (s, k)),
                        eq(app("get_assignee", app("assign_ticket", s, k, u), k2), u),
                    ),
                ),
            ),
        ),
        # get_assignee x assign_ticket HIT + neg has_ticket: no-op
        Axiom(
            label="get_assignee_assign_hit_noticket",
            formula=forall(
                [s, k, k2, u],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    Implication(
                        Negation(PredApp("has_ticket", (s, k))),
                        eq(
                            app("get_assignee", app("assign_ticket", s, k, u), k2),
                            app("get_assignee", s, k2),
                        ),
                    ),
                ),
            ),
        ),
        # get_assignee x assign_ticket MISS: delegates
        Axiom(
            label="get_assignee_assign_miss",
            formula=forall(
                [s, k, k2, u],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    eq(
                        app("get_assignee", app("assign_ticket", s, k, u), k2),
                        app("get_assignee", s, k2),
                    ),
                ),
            ),
        ),
        # get_assignee x resolve_ticket: PRESERVATION
        Axiom(
            label="get_assignee_resolve",
            formula=forall(
                [s, k, k2],
                eq(
                    app("get_assignee", app("resolve_ticket", s, k), k2),
                    app("get_assignee", s, k2),
                ),
            ),
        ),
        # == is_critical (5 axioms) ==============================
        # is_critical x empty: no tickets -> not critical
        Axiom(
            label="is_critical_empty",
            formula=forall([k], Negation(PredApp("is_critical", (const("empty"), k)))),
        ),
        # is_critical x create_ticket HIT: critical iff severity is high
        Axiom(
            label="is_critical_create_hit",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    PredApp("eq_id", (k, k2)),
                    iff(
                        PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),
                        eq(app("classify", t, b), const("high")),
                    ),
                ),
            ),
        ),
        # is_critical x create_ticket MISS: delegates
        Axiom(
            label="is_critical_create_miss",
            formula=forall(
                [s, k, k2, t, b],
                Implication(
                    Negation(PredApp("eq_id", (k, k2))),
                    iff(
                        PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),
                        PredApp("is_critical", (s, k2)),
                    ),
                ),
            ),
        ),
        # is_critical x resolve_ticket: PRESERVATION
        Axiom(
            label="is_critical_resolve",
            formula=forall(
                [s, k, k2],
                iff(
                    PredApp("is_critical", (app("resolve_ticket", s, k), k2)),
                    PredApp("is_critical", (s, k2)),
                ),
            ),
        ),
        # is_critical x assign_ticket: PRESERVATION
        Axiom(
            label="is_critical_assign",
            formula=forall(
                [s, k, k2, u],
                iff(
                    PredApp("is_critical", (app("assign_ticket", s, k, u), k2)),
                    PredApp("is_critical", (s, k2)),
                ),
            ),
        ),
    )

    return Spec(name="BugTracker", signature=sig, axioms=axioms)
""",
)


# ============================================================
# Session Store
# ============================================================

SESSION_STORE = WorkedExample(
    domain_name="Session Store",
    summary="Models a single authentication session lifecycle with token-based verification, expiry, and refresh. Demonstrates selector extraction/foreign, equality predicate basis, enumeration with explicit distinctness, partial constructor with definedness biconditional, definedness-guarded preservation, domain case split in PLAIN cells, state verification via stored observer values, and derived predicates.",
    patterns=frozenset({
        Pattern.SEL_EXTRACT,
        Pattern.EXPLICIT_UNDEF,
        Pattern.ENUMERATION,
        Pattern.PARTIAL_CTOR,
        Pattern.COND_DEF,
        Pattern.PRESERVATION,
        Pattern.BOTH_GUARD_POL,
        Pattern.STATE_DEPENDENT,
        Pattern.BICOND_CHAR,
        Pattern.MULTI_GEN_SORT,
    }),
    sorts=(
        SortInfo("Session", "GENERATED", "Central domain object representing authentication session state"),
        SortInfo("Token", "ATOMIC", "Opaque credential for session verification"),
        SortInfo("Status", "ENUMERATION", "Session lifecycle state (active/expired) with explicit distinctness"),
    ),
    functions=(
        FunctionInfo("active", "→ Status", FunctionRole.CONSTANT, "Enumeration value for active session"),
        FunctionInfo("expired", "→ Status", FunctionRole.CONSTANT, "Enumeration value for expired session"),
        FunctionInfo("create", "Token → Session", FunctionRole.CONSTRUCTOR, "Creates new active session with token"),
        FunctionInfo("verify", "Session × Token → Session", FunctionRole.CONSTRUCTOR, "Attempts token verification against stored token"),
        FunctionInfo("expire", "Session → Session", FunctionRole.CONSTRUCTOR, "Transitions session to expired state"),
        FunctionInfo("refresh", "Session →? Session", FunctionRole.CONSTRUCTOR, "Extends active session, undefined on expired"),
        FunctionInfo("get_token", "Session → Token", FunctionRole.SELECTOR, "Extracts stored authentication token"),
        FunctionInfo("get_status", "Session → Status", FunctionRole.OBSERVER, "Returns current session lifecycle status"),
        FunctionInfo("last_input", "Session →? Token", FunctionRole.SELECTOR, "Extracts last verification attempt token, undefined on create"),
        FunctionInfo("eq_token", "Token × Token", FunctionRole.PREDICATE, "Token equality for verification dispatch"),
        FunctionInfo("is_verified", "Session", FunctionRole.PREDICATE, "True iff session has been successfully verified"),
        FunctionInfo("needs_auth", "Session", FunctionRole.PREDICATE, "Derived: active ∧ ¬is_verified"),
    ),
    obligations=(
        ObligationCell("get_token", "create", CellType.SELECTOR_EXTRACT, "t"),
        ObligationCell("get_token", "verify", CellType.PRESERVATION, "get_token(s)"),
        ObligationCell("get_token", "expire", CellType.PRESERVATION, "get_token(s)"),
        ObligationCell("get_token", "refresh", CellType.GUARDED, "get_token(s)", "def(refresh(s))"),
        ObligationCell("get_status", "create", CellType.BASIS, "active"),
        ObligationCell("get_status", "verify", CellType.PRESERVATION, "get_status(s)"),
        ObligationCell("get_status", "expire", CellType.DOMAIN, "expired"),
        ObligationCell("get_status", "refresh", CellType.GUARDED, "active", "def(refresh(s))"),
        ObligationCell("last_input", "create", CellType.SELECTOR_FOREIGN, "¬def(last_input(create(t)))"),
        ObligationCell("last_input", "verify", CellType.SELECTOR_EXTRACT, "t"),
        ObligationCell("last_input", "expire", CellType.PRESERVATION, "last_input(s)"),
        ObligationCell("last_input", "refresh", CellType.GUARDED, "last_input(s)", "def(refresh(s))"),
        ObligationCell("is_verified", "create", CellType.BASIS, "¬is_verified(create(t))"),
        ObligationCell("is_verified", "verify", CellType.GUARDED, "is_verified(verify(s,t))", "eq_token(t,get_token(s)) ∧ active"),
        ObligationCell("is_verified", "verify", CellType.GUARDED, "preserve is_verified(s)", "¬(eq_token ∧ active)"),
        ObligationCell("is_verified", "expire", CellType.DOMAIN, "¬is_verified(expire(s))"),
        ObligationCell("is_verified", "refresh", CellType.GUARDED, "¬is_verified(refresh(s))", "def(refresh(s))"),
        ObligationCell("needs_auth", "create", CellType.DOMAIN, "needs_auth(create(t))"),
        ObligationCell("needs_auth", "verify", CellType.GUARDED, "¬needs_auth(verify(s,t))", "eq_token(t,get_token(s)) ∧ active"),
        ObligationCell("needs_auth", "verify", CellType.GUARDED, "preserve needs_auth(s)", "¬(eq_token ∧ active)"),
        ObligationCell("needs_auth", "expire", CellType.DOMAIN, "¬needs_auth(expire(s))"),
        ObligationCell("needs_auth", "refresh", CellType.GUARDED, "needs_auth(refresh(s))", "def(refresh(s))"),
    ),
    design_decisions=(
        DesignDecision("Partial refresh", "refresh is undefined on expired sessions via definedness biconditional, not via guard"),
        DesignDecision("Definedness guards", "All observer×refresh axioms guard with def(refresh(s)), not the raw condition — define once, reference via Definedness"),
        DesignDecision("Failed auth preserves verification", "Domain choice: failed verify preserves existing is_verified state rather than invalidating"),
        DesignDecision("Enumeration distinctness", "Explicit ¬eq(active, expired) prevents model collapse under loose semantics"),
        DesignDecision("Derived needs_auth", "Defined compositionally as active ∧ ¬is_verified; per-constructor axioms still required for obligation coverage"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    conjunction,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def session_store_spec() -> Spec:
    """Session Store specification.

    Models a single authentication session lifecycle with token-based
    verification, expiry, and refresh. Demonstrates:

    - Selector extraction + foreign (get_token, last_input)
    - Equality predicate basis axioms (eq_token)
    - Enumeration sort with explicit distinctness (Status: active/expired)
    - Partial constructor with definedness biconditional (refresh)
    - Definedness-guarded preservation (all observers × refresh)
    - Domain case split in PLAIN cell (is_verified × verify)
    - State verification — guard references stored observer value (get_token)
    - Derived/composite predicate (needs_auth)

    Obligation table: 5 observers × 4 constructors = 20 cells.
    All cells PLAIN (no key dispatch — observers take no key parameter).
    Cells 14 and 18 (is_verified/needs_auth × verify) each split into
    positive/negative guard sub-cases, yielding 22 obligation axioms.
    Total axioms: 28 (22 obligation + 6 non-obligation).
    """
    # --- Variables ---
    s = var("s", "Session")
    t = var("t", "Token")
    t2 = var("t2", "Token")
    t3 = var("t3", "Token")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Session": atomic("Session"),
            "Token": atomic("Token"),
            "Status": atomic("Status"),
        },
        functions={
            # Status enumeration
            "active": fn("active", [], "Status"),
            "expired": fn("expired", [], "Status"),
            # Session constructors
            "create": fn("create", [("t", "Token")], "Session"),
            "verify": fn("verify", [("s", "Session"), ("t", "Token")], "Session"),
            "expire": fn("expire", [("s", "Session")], "Session"),
            "refresh": fn(
                "refresh", [("s", "Session")], "Session", total=False
            ),
            # Session observers
            "get_token": fn("get_token", [("s", "Session")], "Token"),
            "get_status": fn("get_status", [("s", "Session")], "Status"),
            "last_input": fn(
                "last_input", [("s", "Session")], "Token", total=False
            ),
        },
        predicates={
            "eq_token": pred("eq_token", [("t1", "Token"), ("t2", "Token")]),
            "is_verified": pred("is_verified", [("s", "Session")]),
            "needs_auth": pred("needs_auth", [("s", "Session")]),
        },
        generated_sorts={
            "Session": GeneratedSortInfo(
                constructors=("create", "verify", "expire", "refresh"),
                selectors={
                    "create": {"get_token": "Token"},
                    "verify": {"last_input": "Token"},
                },
            ),
            "Status": GeneratedSortInfo(
                constructors=("active", "expired"),
                selectors={},
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS (mechanical)
        # ==================================================================
        # Cell 1: get_token × create — SELECTOR_EXTRACT
        Axiom(
            label="get_token_create",
            formula=forall(
                [t],
                eq(app("get_token", app("create", t)), t),
            ),
        ),
        # Cell 10: last_input × verify — SELECTOR_EXTRACT
        Axiom(
            label="last_input_verify",
            formula=forall(
                [s, t],
                eq(app("last_input", app("verify", s, t)), t),
            ),
        ),
        # Cell 9: last_input × create — SELECTOR_FOREIGN
        Axiom(
            label="last_input_create_undef",
            formula=forall(
                [t],
                negation(definedness(app("last_input", app("create", t)))),
            ),
        ),
        # ==================================================================
        # BASIS AXIOMS — eq_token (§9h)
        # ==================================================================
        Axiom(
            label="eq_token_refl",
            formula=forall(
                [t],
                pred_app("eq_token", t, t),
            ),
        ),
        Axiom(
            label="eq_token_sym",
            formula=forall(
                [t, t2],
                implication(
                    pred_app("eq_token", t, t2),
                    pred_app("eq_token", t2, t),
                ),
            ),
        ),
        Axiom(
            label="eq_token_trans",
            formula=forall(
                [t, t2, t3],
                implication(
                    conjunction(pred_app("eq_token", t, t2),
                        pred_app("eq_token", t2, t3)),
                    pred_app("eq_token", t, t3),
                ),
            ),
        ),
        # ==================================================================
        # CONSTRUCTOR DEFINEDNESS — refresh (§9f)
        # ==================================================================
        Axiom(
            label="refresh_def",
            formula=forall(
                [s],
                iff(
                    definedness(app("refresh", s)),
                    eq(app("get_status", s), const("active")),
                ),
            ),
        ),
        # ==================================================================
        # ENUMERATION DISTINCTNESS — Status
        # active and expired are distinct constructors. Without this axiom,
        # loose semantics permits models where active = expired.
        # ==================================================================
        Axiom(
            label="active_expired_distinct",
            formula=negation(eq(const("active"), const("expired"))),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_token (preservation)
        # ==================================================================
        # Cell 2: get_token × verify — preservation
        Axiom(
            label="get_token_verify",
            formula=forall(
                [s, t],
                eq(
                    app("get_token", app("verify", s, t)),
                    app("get_token", s),
                ),
            ),
        ),
        # Cell 3: get_token × expire — preservation
        Axiom(
            label="get_token_expire",
            formula=forall(
                [s],
                eq(
                    app("get_token", app("expire", s)),
                    app("get_token", s),
                ),
            ),
        ),
        # Cell 4: get_token × refresh — definedness-guarded preservation.
        # The guard uses def(refresh(s)) rather than duplicating the
        # definedness condition from refresh_def. Define the condition
        # once (refresh_def), then reference it via Definedness.
        Axiom(
            label="get_token_refresh",
            formula=forall(
                [s],
                implication(
                    definedness(app("refresh", s)),
                    eq(
                        app("get_token", app("refresh", s)),
                        app("get_token", s),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_status
        # ==================================================================
        # Cell 5: get_status × create — basis
        Axiom(
            label="get_status_create",
            formula=forall(
                [t],
                eq(app("get_status", app("create", t)), const("active")),
            ),
        ),
        # Cell 6: get_status × verify — preservation
        Axiom(
            label="get_status_verify",
            formula=forall(
                [s, t],
                eq(
                    app("get_status", app("verify", s, t)),
                    app("get_status", s),
                ),
            ),
        ),
        # Cell 7: get_status × expire
        Axiom(
            label="get_status_expire",
            formula=forall(
                [s],
                eq(app("get_status", app("expire", s)), const("expired")),
            ),
        ),
        # Cell 8: get_status × refresh — definedness-guarded
        Axiom(
            label="get_status_refresh",
            formula=forall(
                [s],
                implication(
                    definedness(app("refresh", s)),
                    eq(
                        app("get_status", app("refresh", s)),
                        const("active"),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — last_input (preservation)
        # ==================================================================
        # Cell 11: last_input × expire — preservation (strong equality:
        # if last_input(s) is undefined, both sides are undefined)
        Axiom(
            label="last_input_expire",
            formula=forall(
                [s],
                eq(
                    app("last_input", app("expire", s)),
                    app("last_input", s),
                ),
            ),
        ),
        # Cell 12: last_input × refresh — definedness-guarded preservation
        Axiom(
            label="last_input_refresh",
            formula=forall(
                [s],
                implication(
                    definedness(app("refresh", s)),
                    eq(
                        app("last_input", app("refresh", s)),
                        app("last_input", s),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — is_verified
        # ==================================================================
        # Cell 13: is_verified × create — basis
        Axiom(
            label="is_verified_create",
            formula=forall(
                [t],
                negation(pred_app("is_verified", app("create", t))),
            ),
        ),
        # Cell 14a: is_verified × verify — POSITIVE guard polarity.
        # Guard: eq_token(t, get_token(s)) ∧ get_status(s) = active.
        # This is a domain-level case split in a PLAIN cell (the observer
        # is_verified takes no key parameter, so the eq_token guard is
        # domain logic, not structural key dispatch).
        # State verification: the guard references get_token(s), a stored
        # observer value.
        Axiom(
            label="is_verified_verify_pos",
            formula=forall(
                [s, t],
                implication(
                    conjunction(pred_app("eq_token", t, app("get_token", s)),
                        eq(app("get_status", s), const("active"))),
                    pred_app("is_verified", app("verify", s, t)),
                ),
            ),
        ),
        # Cell 14b: is_verified × verify — NEGATIVE guard polarity.
        # Wrong token OR expired session → preserve current verification.
        # Domain choice: failed authentication preserves an already-verified
        # session. Alternative domains might invalidate on any failed attempt.
        # This is a design decision, not a structural necessity.
        Axiom(
            label="is_verified_verify_neg",
            formula=forall(
                [s, t],
                implication(
                    negation(
                        conjunction(pred_app("eq_token", t, app("get_token", s)),
                            eq(app("get_status", s), const("active"))),
                    ),
                    iff(
                        pred_app("is_verified", app("verify", s, t)),
                        pred_app("is_verified", s),
                    ),
                ),
            ),
        ),
        # Cell 15: is_verified × expire
        Axiom(
            label="is_verified_expire",
            formula=forall(
                [s],
                negation(pred_app("is_verified", app("expire", s))),
            ),
        ),
        # Cell 16: is_verified × refresh — definedness-guarded
        Axiom(
            label="is_verified_refresh",
            formula=forall(
                [s],
                implication(
                    definedness(app("refresh", s)),
                    negation(
                        pred_app("is_verified", app("refresh", s)),
                    ),
                ),
            ),
        ),
        # ==================================================================
        # OBLIGATION CELLS — needs_auth
        # The per-constructor axioms are structurally required by the
        # obligation table. The standalone definition (needs_auth_def)
        # provides the conceptual meaning; these axioms ensure every cell
        # is explicitly constrained under loose semantics.
        # ==================================================================
        # Cell 17: needs_auth × create
        Axiom(
            label="needs_auth_create",
            formula=forall(
                [t],
                pred_app("needs_auth", app("create", t)),
            ),
        ),
        # Cell 18a: needs_auth × verify — POSITIVE guard → ¬needs_auth
        Axiom(
            label="needs_auth_verify_pos",
            formula=forall(
                [s, t],
                implication(
                    conjunction(pred_app("eq_token", t, app("get_token", s)),
                        eq(app("get_status", s), const("active"))),
                    negation(pred_app("needs_auth", app("verify", s, t))),
                ),
            ),
        ),
        # Cell 18b: needs_auth × verify — NEGATIVE guard → preserve
        Axiom(
            label="needs_auth_verify_neg",
            formula=forall(
                [s, t],
                implication(
                    negation(
                        conjunction(pred_app("eq_token", t, app("get_token", s)),
                            eq(app("get_status", s), const("active"))),
                    ),
                    iff(
                        pred_app("needs_auth", app("verify", s, t)),
                        pred_app("needs_auth", s),
                    ),
                ),
            ),
        ),
        # Cell 19: needs_auth × expire
        Axiom(
            label="needs_auth_expire",
            formula=forall(
                [s],
                negation(pred_app("needs_auth", app("expire", s))),
            ),
        ),
        # Cell 20: needs_auth × refresh — definedness-guarded
        Axiom(
            label="needs_auth_refresh",
            formula=forall(
                [s],
                implication(
                    definedness(app("refresh", s)),
                    pred_app("needs_auth", app("refresh", s)),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — needs_auth (non-obligation)
        # Defines needs_auth compositionally in terms of get_status and
        # is_verified. The obligation table still requires per-constructor
        # axioms above — this definition provides the conceptual meaning
        # but does not substitute for obligation coverage.
        # ==================================================================
        Axiom(
            label="needs_auth_def",
            formula=forall(
                [s],
                iff(
                    pred_app("needs_auth", s),
                    conjunction(eq(app("get_status", s), const("active")),
                        negation(pred_app("is_verified", s))),
                ),
            ),
        ),
    )

    return Spec(name="SessionStore", signature=sig, axioms=axioms)
''',
    analysis_text=(
        "The domain is a single authentication session — not a session store with "
        "multiple sessions, just one session that goes through a lifecycle of creation, "
        "verification, expiry, and refresh. The generated sort is Session.\n\n"
        "Sessions have a two-phase lifecycle: active and expired. That gives me an "
        "enumeration sort Status with constructors active and expired. These must be "
        "explicitly distinct — under loose semantics, a model where active = expired "
        "would collapse the entire state machine.\n\n"
        "Four constructors handle the lifecycle: create(t) initializes a session with "
        "an authentication token t, starting active. verify(s, t) attempts to match "
        "token t against the session's stored token. expire(s) moves the session to "
        "expired status. refresh(s) extends the session, but only when it's active — "
        "this is a partial constructor, so I need a definedness biconditional: "
        "def(refresh(s)) ↔ get_status(s) = active. All observer axioms for refresh "
        "must guard on def(refresh(s)) rather than duplicating the raw condition.\n\n"
        "For observers, get_token is a selector of create — it extracts the stored "
        "authentication token and is preserved by all other constructors. get_status "
        "returns the lifecycle phase. last_input is a selector of verify — it records "
        "the most recently attempted token, and is undefined on create (selector "
        "foreign pattern) since no verification has been attempted yet.\n\n"
        "Verification logic requires comparing tokens, so I need eq_token with full "
        "basis axioms (reflexivity, symmetry, transitivity). The is_verified predicate "
        "tracks whether a successful verification has occurred: it starts false on "
        "create, becomes true when verify is called with a matching token on an active "
        "session (eq_token(t, get_token(s)) ∧ get_status(s) = active), and resets to "
        "false on expire. This is a domain-level case split in a PLAIN cell — the "
        "eq_token guard is domain logic, not structural key dispatch, because "
        "is_verified takes no key parameter.\n\n"
        "I also want a derived predicate needs_auth that captures \"this session needs "
        "authentication\" — the conjunction of being active and not yet verified. "
        "Derivation: needs_auth(s) ↔ get_status(s) = active ∧ ¬is_verified(s). "
        "Per-constructor needs_auth axioms follow by substituting the get_status and "
        "is_verified results for each constructor into this condition. Both needs_auth "
        "and is_verified require independent obligation coverage.\n\n"
        "The obligation table is 5 observers × 4 constructors = 20 PLAIN cells. No "
        "key dispatch — none of the observers take a key parameter. The verify cells "
        "for is_verified and needs_auth each split into positive/negative guard "
        "sub-cases, giving 22 obligation axioms total. Plus 6 non-obligation axioms: "
        "3 eq_token basis, 1 refresh definedness biconditional, 1 enumeration "
        "distinctness, and 1 needs_auth derivation definition."
    ),
)

# ============================================================
# Rate Limiter
# ============================================================

RATE_LIMITER = WorkedExample(
    domain_name="Rate Limiter",
    summary="Models a rate limiter tracking request counts against a configured maximum per window. Demonstrates multi-constructor selector extraction, cross-sort helpers (Nat with zero/succ), helper composition in accumulator axioms, comparison-driven predicate via inductive Peano geq, preservation collapse, function-valued derived observer with guard-split per-constructor axioms, and linked predicate/function derived observers.",
    patterns=frozenset({
        Pattern.SEL_EXTRACT,
        Pattern.PRESERVATION,
        Pattern.CROSS_SORT,
        Pattern.ACCUMULATION,
        Pattern.BICOND_CHAR,
        Pattern.KEYLESS_AGG,
        Pattern.ENUMERATION,
        Pattern.ENUM_CASE_SPLIT,
    }),
    sorts=(
        SortInfo("Limiter", "GENERATED", "Central domain object representing rate limiter state"),
        SortInfo("Nat", "ATOMIC", "Cross-sort Peano naturals for counting (zero/succ)"),
        SortInfo("Status", "ENUMERATION", "Rate limit status with explicit distinctness (ok/exceeded)"),
    ),
    functions=(
        FunctionInfo("zero", "→ Nat", FunctionRole.CONSTANT, "Natural number zero"),
        FunctionInfo("succ", "Nat → Nat", FunctionRole.HELPER, "Successor function for Peano naturals"),
        FunctionInfo("ok", "→ Status", FunctionRole.CONSTANT, "Rate limit not exceeded"),
        FunctionInfo("exceeded", "→ Status", FunctionRole.CONSTANT, "Rate limit exceeded"),
        FunctionInfo("create", "Nat → Limiter", FunctionRole.CONSTRUCTOR, "Creates limiter with given maximum"),
        FunctionInfo("record", "Limiter → Limiter", FunctionRole.CONSTRUCTOR, "Records one request, increments count"),
        FunctionInfo("reset", "Limiter → Limiter", FunctionRole.CONSTRUCTOR, "Resets count to zero for window rollover"),
        FunctionInfo("set_max", "Limiter × Nat → Limiter", FunctionRole.CONSTRUCTOR, "Updates maximum threshold"),
        FunctionInfo("get_count", "Limiter → Nat", FunctionRole.OBSERVER, "Returns current request count"),
        FunctionInfo("get_max", "Limiter → Nat", FunctionRole.SELECTOR, "Multi-constructor selector of create and set_max"),
        FunctionInfo("get_status", "Limiter → Status", FunctionRole.OBSERVER, "Derived: exceeded when geq(get_count, get_max), ok otherwise"),
        FunctionInfo("geq", "Nat × Nat", FunctionRole.PREDICATE, "Greater-or-equal comparison with Peano inductive definition"),
        FunctionInfo("over_limit", "Limiter", FunctionRole.PREDICATE, "Derived: geq(get_count(l), get_max(l))"),
    ),
    obligations=(
        ObligationCell("get_max", "create", CellType.SELECTOR_EXTRACT, "m"),
        ObligationCell("get_max", "set_max", CellType.SELECTOR_EXTRACT, "n"),
        ObligationCell("get_max", "record", CellType.PRESERVATION, "get_max(l)"),
        ObligationCell("get_max", "reset", CellType.PRESERVATION, "get_max(l)"),
        ObligationCell("get_count", "create", CellType.BASIS, "zero"),
        ObligationCell("get_count", "record", CellType.DOMAIN, "succ(get_count(l))"),
        ObligationCell("get_count", "reset", CellType.DOMAIN, "zero"),
        ObligationCell("get_count", "set_max", CellType.PRESERVATION, "get_count(l)"),
        ObligationCell("over_limit", "create", CellType.DOMAIN, "geq(zero, m)"),
        ObligationCell("over_limit", "record", CellType.DOMAIN, "geq(succ(get_count(l)), get_max(l))"),
        ObligationCell("over_limit", "reset", CellType.DOMAIN, "geq(zero, get_max(l))"),
        ObligationCell("over_limit", "set_max", CellType.DOMAIN, "geq(get_count(l), n)"),
        ObligationCell("get_status", "create", CellType.DOMAIN, "exceeded", "geq(zero, m)"),
        ObligationCell("get_status", "create", CellType.DOMAIN, "ok", "¬geq(zero, m)"),
        ObligationCell("get_status", "record", CellType.DOMAIN, "exceeded", "geq(succ(get_count(l)), get_max(l))"),
        ObligationCell("get_status", "record", CellType.DOMAIN, "ok", "¬geq(succ(get_count(l)), get_max(l))"),
        ObligationCell("get_status", "reset", CellType.DOMAIN, "exceeded", "geq(zero, get_max(l))"),
        ObligationCell("get_status", "reset", CellType.DOMAIN, "ok", "¬geq(zero, get_max(l))"),
        ObligationCell("get_status", "set_max", CellType.DOMAIN, "exceeded", "geq(get_count(l), n)"),
        ObligationCell("get_status", "set_max", CellType.DOMAIN, "ok", "¬geq(get_count(l), n)"),
    ),
    design_decisions=(
        DesignDecision("Multi-constructor selector", "get_max is declared as selector of both create and set_max"),
        DesignDecision("No partiality", "All constructors and observers are total — simplest possible obligation table"),
        DesignDecision("Peano geq axioms", "Three inductive axioms (base, zero<succ, succ-succ) prevent vacuous models under loose semantics"),
        DesignDecision("Derived over_limit", "Defined compositionally via geq(get_count, get_max); per-constructor obligation axioms still required"),
        DesignDecision("Dropped warn infrastructure", "Original design had set_warn/get_warn but stored config with no observable predicate is dead state — removed"),
        DesignDecision("Function-valued derived observer", "get_status is defined compositionally via geq(get_count, get_max) → Status. For each constructor, substitute its post-values into the condition: record changes get_count to succ(get_count(l)) and preserves get_max, giving geq(succ(get_count(l)), get_max(l)) → exceeded, ¬geq(...) → ok. Per-constructor axioms are required — a global definition does not satisfy obligation cells"),
        DesignDecision("Linked predicate and function observers", "over_limit (predicate) and get_status (function) are derived from the same geq condition; get_status_def links them via biconditional, demonstrating that both forms require independent obligation coverage"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
)


def rate_limiter_spec() -> Spec:
    """Rate Limiter specification.

    Models a rate limiter tracking request counts against a configured
    maximum per window. Demonstrates:

    - Selector extraction including multi-constructor selector (get_max
      is a selector of both create and set_max)
    - Selector foreign with preservation (total selectors on non-home ctors)
    - Cross-sort helpers (Nat with zero/succ)
    - Helper composition: succ(get_count(l)) in accumulator axiom
    - Accumulator pattern (get_count across constructors)
    - Comparison-driven predicate (over_limit via geq)
    - Inductive helper axioms (Peano definition of geq)
    - Preservation collapse across unrelated constructors
    - Function-valued derived observer (get_status via geq comparison)
    - Enumeration sort with explicit distinctness (Status: ok/exceeded)
    - Guard-split pattern for function-valued derived observer per-constructor axioms
    - Linked predicate and function derived observers (over_limit ↔ get_status)

    Obligation table: 3 observers × 4 constructors = 12 cells, all PLAIN.
    No key dispatch. No partial functions.
    Total axioms: 26 (20 obligation + 6 non-obligation).
    """
    # --- Variables ---
    l = var("l", "Limiter")
    m = var("m", "Nat")
    n = var("n", "Nat")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Limiter": atomic("Limiter"),
            "Nat": atomic("Nat"),
            "Status": atomic("Status"),
        },
        functions={
            # Nat helpers (cross-sort, pattern 10)
            "zero": fn("zero", [], "Nat"),
            "succ": fn("succ", [("n", "Nat")], "Nat"),
            # Status enumeration
            "ok": fn("ok", [], "Status"),
            "exceeded": fn("exceeded", [], "Status"),
            # Limiter constructors
            "create": fn("create", [("m", "Nat")], "Limiter"),
            "record": fn("record", [("l", "Limiter")], "Limiter"),
            "reset": fn("reset", [("l", "Limiter")], "Limiter"),
            "set_max": fn("set_max", [("l", "Limiter"), ("n", "Nat")], "Limiter"),
            # Limiter observers
            "get_count": fn("get_count", [("l", "Limiter")], "Nat"),
            "get_max": fn("get_max", [("l", "Limiter")], "Nat"),
            # Limiter observer (derived — compositional from get_count and get_max)
            "get_status": fn("get_status", [("l", "Limiter")], "Status"),
        },
        predicates={
            "geq": pred("geq", [("a", "Nat"), ("b", "Nat")]),
            "over_limit": pred("over_limit", [("l", "Limiter")]),
        },
        generated_sorts={
            "Limiter": GeneratedSortInfo(
                constructors=("create", "record", "reset", "set_max"),
                selectors={
                    "create": {"get_max": "Nat"},
                    "set_max": {"get_max": "Nat"},
                },
            ),
            "Status": GeneratedSortInfo(
                constructors=("ok", "exceeded"),
                selectors={},
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS (mechanical)
        # ==================================================================
        # Cell 1: get_max × create — SELECTOR_EXTRACT
        Axiom(
            label="get_max_create",
            formula=forall(
                [m],
                eq(app("get_max", app("create", m)), m),
            ),
        ),
        # Cell 2: get_max × set_max — SELECTOR_EXTRACT
        # get_max is declared as a selector of both create and set_max.
        Axiom(
            label="get_max_set_max",
            formula=forall(
                [l, n],
                eq(app("get_max", app("set_max", l, n)), n),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_count (accumulator, pattern 13)
        # ==================================================================
        # Cell 3: get_count × create — basis: new limiter starts at zero
        Axiom(
            label="get_count_create",
            formula=forall(
                [m],
                eq(app("get_count", app("create", m)), const("zero")),
            ),
        ),
        # Cell 4: get_count × record — accumulate (pattern 12: helper
        # composition with succ applied to get_count)
        Axiom(
            label="get_count_record",
            formula=forall(
                [l],
                eq(
                    app("get_count", app("record", l)),
                    app("succ", app("get_count", l)),
                ),
            ),
        ),
        # Cell 5: get_count × reset — window rollover: zero count
        Axiom(
            label="get_count_reset",
            formula=forall(
                [l],
                eq(app("get_count", app("reset", l)), const("zero")),
            ),
        ),
        # Cell 6: get_count × set_max — preservation
        Axiom(
            label="get_count_set_max",
            formula=forall(
                [l, n],
                eq(
                    app("get_count", app("set_max", l, n)),
                    app("get_count", l),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — get_max (preservation on non-extract cells)
        # ==================================================================
        # Cell 7: get_max × record — preservation
        Axiom(
            label="get_max_record",
            formula=forall(
                [l],
                eq(
                    app("get_max", app("record", l)),
                    app("get_max", l),
                ),
            ),
        ),
        # Cell 8: get_max × reset — preservation
        Axiom(
            label="get_max_reset",
            formula=forall(
                [l],
                eq(
                    app("get_max", app("reset", l)),
                    app("get_max", l),
                ),
            ),
        ),
        # ==================================================================
        # DOMAIN CELLS — over_limit (comparison-driven, pattern 18)
        # Each per-constructor axiom substitutes the post-constructor
        # values of get_count and get_max into the geq comparison.
        # ==================================================================
        # Cell 9: over_limit × create — count=zero vs max=m
        Axiom(
            label="over_limit_create",
            formula=forall(
                [m],
                iff(
                    pred_app("over_limit", app("create", m)),
                    pred_app("geq", const("zero"), m),
                ),
            ),
        ),
        # Cell 10: over_limit × record — count incremented vs max preserved
        Axiom(
            label="over_limit_record",
            formula=forall(
                [l],
                iff(
                    pred_app("over_limit", app("record", l)),
                    pred_app("geq", app("succ", app("get_count", l)),
                        app("get_max", l)),
                ),
            ),
        ),
        # Cell 11: over_limit × reset — count=zero vs max preserved
        Axiom(
            label="over_limit_reset",
            formula=forall(
                [l],
                iff(
                    pred_app("over_limit", app("reset", l)),
                    pred_app("geq", const("zero"), app("get_max", l)),
                ),
            ),
        ),
        # Cell 12: over_limit × set_max — count preserved vs new max
        Axiom(
            label="over_limit_set_max",
            formula=forall(
                [l, n],
                iff(
                    pred_app("over_limit", app("set_max", l, n)),
                    pred_app("geq", app("get_count", l), n),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — over_limit (non-obligation)
        # Defines over_limit compositionally: count ≥ max. The obligation
        # table still requires the per-constructor axioms above — this
        # definition provides the conceptual meaning but does not substitute
        # for obligation coverage.
        # ==================================================================
        Axiom(
            label="over_limit_def",
            formula=forall(
                [l],
                iff(
                    pred_app("over_limit", l),
                    pred_app("geq", app("get_count", l),
                        app("get_max", l)),
                ),
            ),
        ),
        # ==================================================================
        # ENUMERATION DISTINCTNESS — Status
        # ok and exceeded are distinct constructors. Without this axiom,
        # loose semantics permits models where ok = exceeded.
        # ==================================================================
        Axiom(
            label="ok_exceeded_distinct",
            formula=negation(eq(const("ok"), const("exceeded"))),
        ),
        # ==================================================================
        # OBLIGATION CELLS — get_status (function-valued derived observer)
        # get_status is defined compositionally: exceeded when count ≥ max,
        # ok otherwise. For each constructor, determine how it changes the
        # component observers, then substitute:
        #
        #   record: get_count → succ(get_count(l)), get_max → get_max(l)
        #           guard = geq(succ(get_count(l)), get_max(l))
        #
        # This substitution process applies to every derived observer:
        # look up each component's per-constructor axiom, plug the post-values
        # into the derivation condition, write the result as a structural axiom.
        # A global definition does not satisfy obligation cells.
        # ==================================================================
        # Cell 13a: get_status × create — POSITIVE guard → exceeded
        Axiom(
            label="get_status_create_pos",
            formula=forall(
                [m],
                implication(
                    pred_app("geq", const("zero"), m),
                    eq(app("get_status", app("create", m)), const("exceeded")),
                ),
            ),
        ),
        # Cell 13b: get_status × create — NEGATIVE guard → ok
        Axiom(
            label="get_status_create_neg",
            formula=forall(
                [m],
                implication(
                    negation(pred_app("geq", const("zero"), m)),
                    eq(app("get_status", app("create", m)), const("ok")),
                ),
            ),
        ),
        # Cell 14a: get_status × record — POSITIVE guard → exceeded
        Axiom(
            label="get_status_record_pos",
            formula=forall(
                [l],
                implication(
                    pred_app("geq", app("succ", app("get_count", l)),
                        app("get_max", l)),
                    eq(app("get_status", app("record", l)), const("exceeded")),
                ),
            ),
        ),
        # Cell 14b: get_status × record — NEGATIVE guard → ok
        Axiom(
            label="get_status_record_neg",
            formula=forall(
                [l],
                implication(
                    negation(pred_app("geq", app("succ", app("get_count", l)),
                        app("get_max", l))),
                    eq(app("get_status", app("record", l)), const("ok")),
                ),
            ),
        ),
        # Cell 15a: get_status × reset — POSITIVE guard → exceeded
        Axiom(
            label="get_status_reset_pos",
            formula=forall(
                [l],
                implication(
                    pred_app("geq", const("zero"), app("get_max", l)),
                    eq(app("get_status", app("reset", l)), const("exceeded")),
                ),
            ),
        ),
        # Cell 15b: get_status × reset — NEGATIVE guard → ok
        Axiom(
            label="get_status_reset_neg",
            formula=forall(
                [l],
                implication(
                    negation(pred_app("geq", const("zero"), app("get_max", l))),
                    eq(app("get_status", app("reset", l)), const("ok")),
                ),
            ),
        ),
        # Cell 16a: get_status × set_max — POSITIVE guard → exceeded
        Axiom(
            label="get_status_set_max_pos",
            formula=forall(
                [l, n],
                implication(
                    pred_app("geq", app("get_count", l), n),
                    eq(app("get_status", app("set_max", l, n)), const("exceeded")),
                ),
            ),
        ),
        # Cell 16b: get_status × set_max — NEGATIVE guard → ok
        Axiom(
            label="get_status_set_max_neg",
            formula=forall(
                [l, n],
                implication(
                    negation(pred_app("geq", app("get_count", l), n)),
                    eq(app("get_status", app("set_max", l, n)), const("ok")),
                ),
            ),
        ),
        # ==================================================================
        # DERIVED DEFINITION — get_status (non-obligation)
        # Links the function-valued and predicate-valued derived observers:
        # get_status returns exceeded iff over_limit holds. This shows that
        # both forms (predicate and function) can be derived from the same
        # underlying condition, and both still require per-constructor
        # obligation axioms — a global definition does not substitute for
        # structural coverage.
        # ==================================================================
        Axiom(
            label="get_status_def",
            formula=forall(
                [l],
                iff(
                    eq(app("get_status", l), const("exceeded")),
                    pred_app("over_limit", l),
                ),
            ),
        ),
        # ==================================================================
        # HELPER AXIOMS — geq (inductive definition on Nat)
        # Without these axioms, loose semantics permits models where geq
        # is unconditionally false (or true), making over_limit vacuous.
        # These three axioms provide the minimal Peano characterization
        # of ≥ on natural numbers built from zero/succ.
        # ==================================================================
        # Every natural number is ≥ zero
        Axiom(
            label="geq_zero_base",
            formula=forall(
                [m],
                pred_app("geq", m, const("zero")),
            ),
        ),
        # Zero is not ≥ any successor
        Axiom(
            label="geq_zero_succ",
            formula=forall(
                [m],
                negation(pred_app("geq", const("zero"), app("succ", m))),
            ),
        ),
        # Inductive step: succ(a) ≥ succ(b) ⟺ a ≥ b
        Axiom(
            label="geq_succ_succ",
            formula=forall(
                [m, n],
                iff(
                    pred_app("geq", app("succ", m), app("succ", n)),
                    pred_app("geq", m, n),
                ),
            ),
        ),
    )

    return Spec(name="RateLimiter", signature=sig, axioms=axioms)
''',
    analysis_text=(
        "The domain is a rate limiter that tracks request counts against a configured "
        "maximum per time window. The generated sort is Limiter.\n\n"
        "I need Peano naturals for counting — a separate sort Nat with zero and succ. "
        "This is a cross-sort helper: Nat is a generated sort with its own constructors "
        "but no obligation cells (no observers take Nat as first argument in the Limiter "
        "spec). I also need a comparison predicate geq (greater-or-equal) with inductive "
        "Peano axioms: geq(n, zero) holds for all n, ¬geq(zero, succ(n)), and "
        "geq(succ(a), succ(b)) ↔ geq(a, b). These three axioms fully characterize geq "
        "and prevent vacuous models under loose semantics.\n\n"
        "Four constructors: create(m) initializes the limiter with maximum m and count "
        "zero. record(l) increments the count by one. reset(l) sets the count back to "
        "zero for window rollover. set_max(l, n) updates the maximum threshold.\n\n"
        "The primary observers are get_count (returns current request count) and get_max "
        "(returns the configured maximum). get_max is a selector of both create and "
        "set_max — a multi-constructor selector pattern. Both record and reset preserve "
        "get_max since they don't affect the threshold.\n\n"
        "I need a rate limit status indicator in two forms. First, over_limit as a "
        "predicate observer: over_limit(l) holds exactly when "
        "geq(get_count(l), get_max(l)). This is a derivation — the definition axiom "
        "states over_limit(l) ↔ geq(get_count(l), get_max(l)), and per-constructor "
        "axioms follow by substituting each constructor's post-values for get_count "
        "and get_max into the geq condition. For record, get_count becomes "
        "succ(get_count(l)) and get_max is preserved, giving "
        "geq(succ(get_count(l)), get_max(l)).\n\n"
        "Second, get_status as a function observer returning a Status enumeration "
        "(ok/exceeded). get_status is derived from the same geq condition as "
        "over_limit: get_status(l) = exceeded ↔ over_limit(l). The per-constructor "
        "axioms for get_status use guard splits — for each constructor, evaluate the "
        "geq condition with post-values and branch: positive guard → exceeded, "
        "negative guard → ok. I'll write a get_status_def linking it to over_limit "
        "via biconditional so the relationship between the predicate and function "
        "forms is explicit.\n\n"
        "Status has two constructors ok and exceeded that must be explicitly distinct.\n\n"
        "The obligation table is 3 observers × 4 constructors = 12 PLAIN cells. No "
        "key dispatch. No partial functions. The get_status cells each need guard-split "
        "sub-cases (positive/negative), giving 20 obligation axioms. Plus 6 "
        "non-obligation: 3 geq basis, 1 over_limit derivation definition, 1 get_status "
        "derivation definition, and 1 enumeration distinctness."
    ),
)


# ============================================================
# DNS Zone
# ============================================================

DNS_ZONE = WorkedExample(
    domain_name="DNS Zone",
    summary="Models a DNS zone storing resource records indexed by (DomainName, RecordType). Demonstrates dual-key dispatch where the obligation table splits on the first key (eq_name) and the second key (eq_type) is handled as domain-level dispatch within HIT cells via nested implication. Features two equality predicate basis sets, doubly partial observers, delegation via strong equality, and existence predicate linked to observer definedness.",
    patterns=frozenset({
        Pattern.COLLECTION_CONTAINER,
        Pattern.KEYED_CONSTRUCTOR,
        Pattern.KEY_DISPATCH,
        Pattern.DELEGATION,
        Pattern.EXPLICIT_UNDEF,
        Pattern.OVERWRITE,
        Pattern.DOUBLY_PARTIAL,
        Pattern.NESTED_GUARD,
        Pattern.BOTH_GUARD_POL,
        Pattern.BICOND_CHAR,
    }),
    sorts=(
        SortInfo("Zone", "GENERATED", "Central collection storing DNS resource records"),
        SortInfo("DomainName", "ATOMIC", "First key sort — opaque domain name identifier"),
        SortInfo("RecordType", "ATOMIC", "Second key sort — opaque record type identifier"),
        SortInfo("RData", "ATOMIC", "Opaque record data payload"),
        SortInfo("Nat", "ATOMIC", "Opaque TTL value (no zero/succ — purely opaque in this domain)"),
    ),
    functions=(
        FunctionInfo("empty", "→ Zone", FunctionRole.CONSTRUCTOR, "Creates empty DNS zone"),
        FunctionInfo("add_record", "Zone × DomainName × RecordType × RData × Nat → Zone", FunctionRole.CONSTRUCTOR, "Adds or overwrites record at (name, type)"),
        FunctionInfo("remove_record", "Zone × DomainName × RecordType → Zone", FunctionRole.CONSTRUCTOR, "Removes record at (name, type)"),
        FunctionInfo("get_rdata", "Zone × DomainName × RecordType →? RData", FunctionRole.PARTIAL_OBSERVER, "Record data, undefined if no record exists"),
        FunctionInfo("get_ttl", "Zone × DomainName × RecordType →? Nat", FunctionRole.PARTIAL_OBSERVER, "TTL value, undefined if no record exists"),
        FunctionInfo("eq_name", "DomainName × DomainName", FunctionRole.PREDICATE, "First key equality for structural dispatch in obligation table"),
        FunctionInfo("eq_type", "RecordType × RecordType", FunctionRole.PREDICATE, "Second key equality for domain-level dispatch within HIT cells"),
        FunctionInfo("has_record", "Zone × DomainName × RecordType", FunctionRole.PREDICATE, "Record existence, linked to def(get_rdata) via biconditional"),
    ),
    obligations=(
        # get_rdata
        ObligationCell("get_rdata", "empty", CellType.UNDEF, "¬def(get_rdata(empty,n,t))"),
        ObligationCell("get_rdata", "add_record", CellType.KEY_HIT, "d", "eq_name(n,n2) ∧ eq_type(t,t2)"),
        ObligationCell("get_rdata", "add_record", CellType.KEY_MISS, "delegate", "eq_name(n,n2) ∧ ¬eq_type(t,t2)"),
        ObligationCell("get_rdata", "add_record", CellType.KEY_MISS, "delegate", "¬eq_name(n,n2)"),
        ObligationCell("get_rdata", "remove_record", CellType.KEY_HIT, "¬def", "eq_name(n,n2) ∧ eq_type(t,t2)"),
        ObligationCell("get_rdata", "remove_record", CellType.KEY_MISS, "delegate", "eq_name(n,n2) ∧ ¬eq_type(t,t2)"),
        ObligationCell("get_rdata", "remove_record", CellType.KEY_MISS, "delegate", "¬eq_name(n,n2)"),
        # get_ttl (parallel structure)
        ObligationCell("get_ttl", "empty", CellType.UNDEF, "¬def(get_ttl(empty,n,t))"),
        ObligationCell("get_ttl", "add_record", CellType.KEY_HIT, "ttl", "eq_name ∧ eq_type"),
        ObligationCell("get_ttl", "add_record", CellType.KEY_MISS, "delegate", "eq_name ∧ ¬eq_type"),
        ObligationCell("get_ttl", "add_record", CellType.KEY_MISS, "delegate", "¬eq_name"),
        ObligationCell("get_ttl", "remove_record", CellType.KEY_HIT, "¬def", "eq_name ∧ eq_type"),
        ObligationCell("get_ttl", "remove_record", CellType.KEY_MISS, "delegate", "eq_name ∧ ¬eq_type"),
        ObligationCell("get_ttl", "remove_record", CellType.KEY_MISS, "delegate", "¬eq_name"),
        # has_record
        ObligationCell("has_record", "empty", CellType.BASIS, "¬has_record(empty,n,t)"),
        ObligationCell("has_record", "add_record", CellType.KEY_HIT, "has_record", "eq_name ∧ eq_type"),
        ObligationCell("has_record", "add_record", CellType.KEY_MISS, "delegate iff", "eq_name ∧ ¬eq_type"),
        ObligationCell("has_record", "add_record", CellType.KEY_MISS, "delegate iff", "¬eq_name"),
        ObligationCell("has_record", "remove_record", CellType.KEY_HIT, "¬has_record", "eq_name ∧ eq_type"),
        ObligationCell("has_record", "remove_record", CellType.KEY_MISS, "delegate iff", "eq_name ∧ ¬eq_type"),
        ObligationCell("has_record", "remove_record", CellType.KEY_MISS, "delegate iff", "¬eq_name"),
    ),
    design_decisions=(
        DesignDecision("Dual-key dispatch via nested implication", "Obligation table splits on first key (DomainName); second key (RecordType) handled as domain logic within HIT cells via nested Implication"),
        DesignDecision("Nat is purely opaque", "No zero/succ — TTL has no arithmetic in this domain, unlike Rate Limiter"),
        DesignDecision("has_record linked to definedness", "has_record(z,n,t) ⟺ def(get_rdata(z,n,t)) via explicit biconditional; obligation axioms still required"),
        DesignDecision("Strong equality delegation", "MISS cells use strong equality (eq) which correctly propagates undefinedness for partial observers"),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    conjunction,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    implication,
    negation,
    pred,
    pred_app,
    var,
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
                pred_app("eq_name", n, n),
            ),
        ),
        Axiom(
            label="eq_name_sym",
            formula=forall(
                [n, n2],
                implication(
                    pred_app("eq_name", n, n2),
                    pred_app("eq_name", n2, n),
                ),
            ),
        ),
        Axiom(
            label="eq_name_trans",
            formula=forall(
                [n, n2, n3],
                implication(
                    conjunction(pred_app("eq_name", n, n2),
                        pred_app("eq_name", n2, n3)),
                    pred_app("eq_name", n, n3),
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
                pred_app("eq_type", t, t),
            ),
        ),
        Axiom(
            label="eq_type_sym",
            formula=forall(
                [t, t2],
                implication(
                    pred_app("eq_type", t, t2),
                    pred_app("eq_type", t2, t),
                ),
            ),
        ),
        Axiom(
            label="eq_type_trans",
            formula=forall(
                [t, t2, t3],
                implication(
                    conjunction(pred_app("eq_type", t, t2),
                        pred_app("eq_type", t2, t3)),
                    pred_app("eq_type", t, t3),
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
                negation(
                    definedness(app("get_rdata", const("empty"), n, t))
                ),
            ),
        ),
        # Cell 6: get_ttl × empty — undefined
        Axiom(
            label="get_ttl_empty",
            formula=forall(
                [n, t],
                negation(
                    definedness(app("get_ttl", const("empty"), n, t))
                ),
            ),
        ),
        # Cell 11: has_record × empty — no records
        Axiom(
            label="has_record_empty",
            formula=forall(
                [n, t],
                negation(
                    pred_app("has_record", const("empty"), n, t)
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        pred_app("eq_type", t, t2),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        negation(pred_app("eq_type", t, t2)),
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
                implication(
                    negation(pred_app("eq_name", n, n2)),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        pred_app("eq_type", t, t2),
                        negation(
                            definedness(
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        negation(pred_app("eq_type", t, t2)),
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
                implication(
                    negation(pred_app("eq_name", n, n2)),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        pred_app("eq_type", t, t2),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        negation(pred_app("eq_type", t, t2)),
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
                implication(
                    negation(pred_app("eq_name", n, n2)),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        pred_app("eq_type", t, t2),
                        negation(
                            definedness(
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        negation(pred_app("eq_type", t, t2)),
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
                implication(
                    negation(pred_app("eq_name", n, n2)),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        pred_app("eq_type", t, t2),
                        pred_app("has_record", app("add_record", z, n, t, d, ttl), n2, t2),
                    ),
                ),
            ),
        ),
        # Cell 12b: HIT(name) + MISS(type) → delegate
        Axiom(
            label="has_record_add_hit_type_miss",
            formula=forall(
                [z, n, n2, t, t2, d, ttl],
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        negation(pred_app("eq_type", t, t2)),
                        iff(
                            pred_app("has_record", app("add_record", z, n, t, d, ttl), n2, t2),
                            pred_app("has_record", z, n2, t2),
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
                implication(
                    negation(pred_app("eq_name", n, n2)),
                    iff(
                        pred_app("has_record", app("add_record", z, n, t, d, ttl), n2, t2),
                        pred_app("has_record", z, n2, t2),
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        pred_app("eq_type", t, t2),
                        negation(
                            pred_app("has_record", app("remove_record", z, n, t), n2, t2)
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
                implication(
                    pred_app("eq_name", n, n2),
                    implication(
                        negation(pred_app("eq_type", t, t2)),
                        iff(
                            pred_app("has_record", app("remove_record", z, n, t), n2, t2),
                            pred_app("has_record", z, n2, t2),
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
                implication(
                    negation(pred_app("eq_name", n, n2)),
                    iff(
                        pred_app("has_record", app("remove_record", z, n, t), n2, t2),
                        pred_app("has_record", z, n2, t2),
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
                    pred_app("has_record", z, n, t),
                    definedness(app("get_rdata", z, n, t)),
                ),
            ),
        ),
    )

    return Spec(name="DnsZone", signature=sig, axioms=axioms)
''',
    analysis_text=(
        "The domain is a DNS zone that stores resource records indexed by a composite "
        "key of (DomainName, RecordType). This is a keyed collection — the generated "
        "sort is Zone.\n\n"
        "The key structure has two levels: DomainName is the primary key, and "
        "RecordType is a secondary key within each name. Both need equality predicates "
        "(eq_name and eq_type) with full basis axioms (reflexivity, symmetry, "
        "transitivity for each). This dual-key structure drives the obligation table "
        "layout — the table splits on eq_name at the structural level, and then on "
        "eq_type within HIT cells via nested implication.\n\n"
        "Three constructors: empty creates an empty zone with no records. "
        "add_record(z, n, t, d, ttl) inserts or overwrites a record with domain name "
        "n, record type t, resource data d, and time-to-live ttl. "
        "remove_record(z, n, t) deletes the record at (n, t).\n\n"
        "The observers are both partial: get_rdata(z, n, t) returns the resource data "
        "and get_ttl(z, n, t) returns the TTL, but both are undefined when no record "
        "exists at (n, t). On the empty zone, both are unconditionally undefined for "
        "all name/type combinations. For add_record and remove_record, the axioms "
        "dispatch hierarchically: first check eq_name (structural key dispatch from "
        "the obligation table), then within the HIT case check eq_type (domain-level "
        "dispatch via nested implication). MISS on the name level delegates to the "
        "inner zone unconditionally. HIT on name but MISS on type also delegates. "
        "the new data for add, or become undefined for remove.\n\n"
        "I also want has_record as a predicate observer that answers \"does a record "
        "exist at (n, t)?\" This is derived from the definedness of get_rdata: "
        "has_record(z, n, t) ↔ def(get_rdata(z, n, t)). The derivation definition is "
        "a non-obligation axiom, but per-constructor has_record axioms are still "
        "required for obligation coverage. The has_record axioms follow the same "
        "dispatch structure as get_rdata — same guards, but the conclusions are "
        "boolean (true/false/delegate) rather than data values.\n\n"
        "MISS cells use strong equality (eq) for delegation, which correctly "
        "propagates undefinedness for the partial observers — if "
        "get_rdata(z, n2, t2) is undefined, then "
        "get_rdata(add_record(z, n, t, d, ttl), n2, t2) is also undefined via the "
        "strong equation.\n\n"
        "The obligation table is 3 observers × 3 constructors = 9 base cells. The "
        "empty cells are PLAIN (3). The add_record and remove_record cells split "
        "into HIT/MISS on eq_name, and HIT cells further split on eq_type, giving "
        "21 obligation axioms. Plus 7 non-obligation: 3 eq_name basis, 3 eq_type "
        "basis, and 1 has_record derivation definition."
    ),
)

# ============================================================
# Connection
# ============================================================

CONNECTION = WorkedExample(
    domain_name="Connection",
    summary=(
        "Models a network connection with state lifecycle. Teaches the distinction "
        "between a genuine CASL selector (get_error: partial, one home constructor) "
        "and a total observer that coincidentally projects a constructor parameter "
        "(get_timeout: total, preserved across all constructors). Also demonstrates "
        "derivation link, preservation collapse, and enumeration distinctness."
    ),
    patterns=frozenset({
        Pattern.ENUMERATION,
        Pattern.SEL_EXTRACT,
        Pattern.EXPLICIT_UNDEF,
        Pattern.PRESERVATION,
        Pattern.BICOND_CHAR,
        Pattern.STATE_DEPENDENT,
    }),
    sorts=(
        SortInfo("Conn", "GENERATED", "Central domain object representing connection state"),
        SortInfo("State", "ENUMERATION", "Connection lifecycle states with explicit distinctness (idle_st/active_st/failed_st)"),
        SortInfo("Nat", "ATOMIC", "Opaque timeout configuration value"),
        SortInfo("ErrorCode", "ATOMIC", "Opaque error payload — only meaningful after a failure"),
    ),
    functions=(
        FunctionInfo("idle_st", "→ State", FunctionRole.CONSTANT, "Initial and post-disconnect/retry state"),
        FunctionInfo("active_st", "→ State", FunctionRole.CONSTANT, "Successfully connected state"),
        FunctionInfo("failed_st", "→ State", FunctionRole.CONSTANT, "Error state after connection failure"),
        FunctionInfo("create", "Nat → Conn", FunctionRole.CONSTRUCTOR, "Creates new connection with timeout config, starts idle"),
        FunctionInfo("connect", "Conn → Conn", FunctionRole.CONSTRUCTOR, "Activates the connection"),
        FunctionInfo("disconnect", "Conn → Conn", FunctionRole.CONSTRUCTOR, "Graceful teardown, returns to idle"),
        FunctionInfo("fail", "Conn × ErrorCode → Conn", FunctionRole.CONSTRUCTOR, "Connection error with diagnostic code, enters failed state"),
        FunctionInfo("retry", "Conn → Conn", FunctionRole.CONSTRUCTOR, "Recovery attempt, returns to idle"),
        FunctionInfo("get_state", "Conn → State", FunctionRole.OBSERVER, "Returns current connection lifecycle state"),
        FunctionInfo("get_timeout", "Conn → Nat", FunctionRole.OBSERVER, "Total observer — returns configured timeout. NOT a selector: total functions are defined everywhere, contradicting selector foreign-undefinedness"),
        FunctionInfo("get_error", "Conn →? ErrorCode", FunctionRole.SELECTOR, "Selector of fail — extracts error code. Partial: undefined on all other constructors"),
        FunctionInfo("is_active", "Conn", FunctionRole.PREDICATE, "Derived: is_active(c) ↔ get_state(c) = active_st. Per-constructor axioms follow by substituting get_state results"),
    ),
    obligations=(
        # get_state (5 DOMAIN cells)
        ObligationCell("get_state", "create", CellType.DOMAIN, "idle_st"),
        ObligationCell("get_state", "connect", CellType.DOMAIN, "active_st"),
        ObligationCell("get_state", "disconnect", CellType.DOMAIN, "idle_st"),
        ObligationCell("get_state", "fail", CellType.DOMAIN, "failed_st"),
        ObligationCell("get_state", "retry", CellType.DOMAIN, "idle_st"),
        # get_timeout (5 DOMAIN cells — NOT selector, just a total observer)
        ObligationCell("get_timeout", "create", CellType.DOMAIN, "n (coincidental extraction — looks like projection but get_timeout is total)"),
        ObligationCell("get_timeout", "connect", CellType.PRESERVATION, "get_timeout(c) — config immutable"),
        ObligationCell("get_timeout", "disconnect", CellType.PRESERVATION, "get_timeout(c) — config immutable"),
        ObligationCell("get_timeout", "fail", CellType.PRESERVATION, "get_timeout(c) — config immutable"),
        ObligationCell("get_timeout", "retry", CellType.PRESERVATION, "get_timeout(c) — config immutable"),
        # get_error (1 SELECTOR_EXTRACT + 4 SELECTOR_FOREIGN — genuine partial selector)
        ObligationCell("get_error", "create", CellType.SELECTOR_FOREIGN, "¬def — no error on fresh connection"),
        ObligationCell("get_error", "connect", CellType.SELECTOR_FOREIGN, "¬def — no error on active connection"),
        ObligationCell("get_error", "disconnect", CellType.SELECTOR_FOREIGN, "¬def — no error on graceful teardown"),
        ObligationCell("get_error", "fail", CellType.SELECTOR_EXTRACT, "e — extracts error code from fail"),
        ObligationCell("get_error", "retry", CellType.SELECTOR_FOREIGN, "¬def — error cleared on recovery"),
        # is_active (5 DOMAIN cells — derived from get_state)
        ObligationCell("is_active", "create", CellType.DOMAIN, "false (idle_st ≠ active_st)"),
        ObligationCell("is_active", "connect", CellType.DOMAIN, "true (active_st = active_st)"),
        ObligationCell("is_active", "disconnect", CellType.DOMAIN, "false (idle_st ≠ active_st)"),
        ObligationCell("is_active", "fail", CellType.DOMAIN, "false (failed_st ≠ active_st)"),
        ObligationCell("is_active", "retry", CellType.DOMAIN, "false (idle_st ≠ active_st)"),
    ),
    design_decisions=(
        DesignDecision(
            "Selector vs total observer",
            "get_error is a genuine CASL selector of fail: partial, one home constructor, "
            "mechanical extraction + foreign-undefinedness. get_timeout is a total observer — "
            "get_timeout(create(n)) = n looks like extraction, but get_timeout is defined on "
            "every constructor (preservation), so it cannot be a selector. Selectors must be "
            "partial because they are undefined on foreign constructors"
        ),
        DesignDecision(
            "Derivation link",
            "is_active is derived from get_state: is_active(c) ↔ get_state(c) = active_st. "
            "Per-constructor is_active axioms follow by substituting the get_state result for each constructor "
            "into the derivation condition. Both observers require independent obligation coverage"
        ),
        DesignDecision(
            "Retry semantics",
            "retry returns to idle_st, not directly to active_st — recovery and reconnection are "
            "separate concerns. The lifecycle goes failed → idle → active, not failed → active"
        ),
        DesignDecision(
            "Error lifecycle",
            "Error codes are injected at failure and lost at recovery. get_error is undefined after "
            "retry because the failure context is cleared — this is the natural partial lifecycle"
        ),
    ),
    code='''from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    iff,
    negation,
    pred,
    pred_app,
    var,
)


def connection_spec() -> Spec:
    """Connection specification.

    Models a network connection with state lifecycle. Demonstrates:

    - Selector vs total observer contrast:
      get_error (partial selector of fail) vs get_timeout (total observer)
    - Derivation link: is_active derived from get_state via biconditional
    - Preservation collapse (get_timeout across all state-transition constructors)
    - Selector extraction + foreign undefinedness (get_error)
    - Enumeration sort with explicit distinctness (State: idle/active/failed)

    Obligation table: 4 observers × 5 constructors = 20 cells, all PLAIN.
    No key dispatch. get_error is partial; all other functions are total.
    Total axioms: 24 (20 obligation + 1 derivation definition + 3 distinctness).
    """
    # --- Variables ---
    c = var("c", "Conn")
    n = var("n", "Nat")
    e = var("e", "ErrorCode")

    # --- Signature ---
    sig = Signature(
        sorts={
            "Conn": atomic("Conn"),
            "State": atomic("State"),
            "Nat": atomic("Nat"),
            "ErrorCode": atomic("ErrorCode"),
        },
        functions={
            # State enumeration
            "idle_st": fn("idle_st", [], "State"),
            "active_st": fn("active_st", [], "State"),
            "failed_st": fn("failed_st", [], "State"),
            # Conn constructors
            "create": fn("create", [("n", "Nat")], "Conn"),
            "connect": fn("connect", [("c", "Conn")], "Conn"),
            "disconnect": fn("disconnect", [("c", "Conn")], "Conn"),
            "fail": fn("fail", [("c", "Conn"), ("e", "ErrorCode")], "Conn"),
            "retry": fn("retry", [("c", "Conn")], "Conn"),
            # Conn observers
            "get_state": fn("get_state", [("c", "Conn")], "State"),
            "get_timeout": fn("get_timeout", [("c", "Conn")], "Nat"),
            "get_error": fn(
                "get_error", [("c", "Conn")], "ErrorCode", total=False
            ),
        },
        predicates={
            # Conn predicate observer (derived from get_state)
            "is_active": pred("is_active", [("c", "Conn")]),
        },
        generated_sorts={
            "Conn": GeneratedSortInfo(
                constructors=("create", "connect", "disconnect", "fail", "retry"),
                selectors={
                    "fail": {"get_error": "ErrorCode"},
                },
            ),
            "State": GeneratedSortInfo(
                constructors=("idle_st", "active_st", "failed_st"),
                selectors={},
            ),
        },
    )

    axioms = (
        # ==================================================================
        # SELECTOR CELLS — get_error (genuine partial selector of fail)
        #
        # get_error is partial: defined only on fail, undefined elsewhere.
        # This is the CASL free-type pattern — fail injects an ErrorCode,
        # get_error extracts it. Mechanical axiom generation handles these.
        # ==================================================================
        # get_error × fail — SELECTOR_EXTRACT
        Axiom(
            label="get_error_fail",
            formula=forall(
                [c, e],
                eq(app("get_error", app("fail", c, e)), e),
            ),
        ),
        # get_error × create — SELECTOR_FOREIGN
        Axiom(
            label="get_error_create",
            formula=forall(
                [n],
                negation(definedness(app("get_error", app("create", n)))),
            ),
        ),
        # get_error × connect — SELECTOR_FOREIGN
        Axiom(
            label="get_error_connect",
            formula=forall(
                [c],
                negation(definedness(app("get_error", app("connect", c)))),
            ),
        ),
        # get_error × disconnect — SELECTOR_FOREIGN
        Axiom(
            label="get_error_disconnect",
            formula=forall(
                [c],
                negation(definedness(app("get_error", app("disconnect", c)))),
            ),
        ),
        # get_error × retry — SELECTOR_FOREIGN
        Axiom(
            label="get_error_retry",
            formula=forall(
                [c],
                negation(definedness(app("get_error", app("retry", c)))),
            ),
        ),
        # ==================================================================
        # get_state CELLS — DOMAIN
        # ==================================================================
        Axiom(
            label="get_state_create",
            formula=forall(
                [n],
                eq(app("get_state", app("create", n)), const("idle_st")),
            ),
        ),
        Axiom(
            label="get_state_connect",
            formula=forall(
                [c],
                eq(app("get_state", app("connect", c)), const("active_st")),
            ),
        ),
        Axiom(
            label="get_state_disconnect",
            formula=forall(
                [c],
                eq(app("get_state", app("disconnect", c)), const("idle_st")),
            ),
        ),
        Axiom(
            label="get_state_fail",
            formula=forall(
                [c, e],
                eq(app("get_state", app("fail", c, e)), const("failed_st")),
            ),
        ),
        Axiom(
            label="get_state_retry",
            formula=forall(
                [c],
                eq(app("get_state", app("retry", c)), const("idle_st")),
            ),
        ),
        # ==================================================================
        # get_timeout CELLS — DOMAIN (total observer, NOT a selector)
        #
        # get_timeout(create(n)) = n looks like selector extraction, but
        # get_timeout is total — defined on every constructor. A CASL
        # selector must be partial (undefined on foreign constructors).
        # get_timeout is an observer whose create axiom coincidentally
        # resembles projection. The preservation axioms are domain equations
        # asserting configuration immutability, not structural consequences.
        # ==================================================================
        Axiom(
            label="get_timeout_create",
            formula=forall(
                [n],
                eq(app("get_timeout", app("create", n)), n),
            ),
        ),
        Axiom(
            label="get_timeout_connect",
            formula=forall(
                [c],
                eq(
                    app("get_timeout", app("connect", c)),
                    app("get_timeout", c),
                ),
            ),
        ),
        Axiom(
            label="get_timeout_disconnect",
            formula=forall(
                [c],
                eq(
                    app("get_timeout", app("disconnect", c)),
                    app("get_timeout", c),
                ),
            ),
        ),
        Axiom(
            label="get_timeout_fail",
            formula=forall(
                [c, e],
                eq(
                    app("get_timeout", app("fail", c, e)),
                    app("get_timeout", c),
                ),
            ),
        ),
        Axiom(
            label="get_timeout_retry",
            formula=forall(
                [c],
                eq(
                    app("get_timeout", app("retry", c)),
                    app("get_timeout", c),
                ),
            ),
        ),
        # ==================================================================
        # is_active CELLS — DOMAIN (derived from get_state)
        # ==================================================================
        Axiom(
            label="is_active_create",
            formula=forall(
                [n],
                negation(pred_app("is_active", app("create", n))),
            ),
        ),
        Axiom(
            label="is_active_connect",
            formula=forall(
                [c],
                pred_app("is_active", app("connect", c)),
            ),
        ),
        Axiom(
            label="is_active_disconnect",
            formula=forall(
                [c],
                negation(pred_app("is_active", app("disconnect", c))),
            ),
        ),
        Axiom(
            label="is_active_fail",
            formula=forall(
                [c, e],
                negation(pred_app("is_active", app("fail", c, e))),
            ),
        ),
        Axiom(
            label="is_active_retry",
            formula=forall(
                [c],
                negation(pred_app("is_active", app("retry", c))),
            ),
        ),
        # ==================================================================
        # NON-OBLIGATION AXIOMS
        # ==================================================================
        # Derivation definition — is_active is a conservative extension.
        # This is a definitional extension (conservative) — is_active adds no
        # semantic content beyond get_state, but provides a convenient boolean
        # query. The obligation table still requires per-constructor axioms
        # above — this definition provides the derivation link but does not
        # substitute for obligation coverage.
        # ==================================================================
        Axiom(
            label="is_active_def",
            formula=forall(
                [c],
                iff(
                    pred_app("is_active", c),
                    eq(app("get_state", c), const("active_st")),
                ),
            ),
        ),
        # ==================================================================
        # ENUMERATION DISTINCTNESS — State
        # idle_st, active_st, and failed_st are distinct constructors.
        # Without these axioms, loose semantics permits models where
        # idle_st = active_st, which would collapse the state machine.
        # ==================================================================
        Axiom(
            label="state_distinct_idle_active",
            formula=negation(eq(const("idle_st"), const("active_st"))),
        ),
        Axiom(
            label="state_distinct_idle_failed",
            formula=negation(eq(const("idle_st"), const("failed_st"))),
        ),
        Axiom(
            label="state_distinct_active_failed",
            formula=negation(eq(const("active_st"), const("failed_st"))),
        ),
    )

    return Spec(name="Connection", signature=sig, axioms=axioms)
''',
    analysis_text=(
        "The domain is a network connection with a lifecycle — it gets created, "
        "activated, can fail, and can recover. The central abstraction is the "
        "connection object itself, so Conn is the generated sort.\n\n"
        "Connections have a lifecycle state that passes through three distinct "
        "phases: idle (freshly created or after teardown/recovery), active "
        "(successfully connected), and failed (after an error). This calls for an "
        "enumeration sort State with three nullary constructors idle_st, active_st, "
        "and failed_st. Since these are distinct states, I need explicit distinctness "
        "axioms — under loose semantics, nothing prevents a model from collapsing "
        "idle_st = failed_st without them.\n\n"
        "Failures carry diagnostic information, so I need an ErrorCode sort for the "
        "error payload. Nat models the timeout configuration value.\n\n"
        "The constructors of Conn correspond to lifecycle transitions: create(n) "
        "initializes a new connection with a timeout configuration and starts idle. "
        "connect(c) activates it. disconnect(c) is graceful teardown back to idle. "
        "fail(c, e) records a failure with an error code. retry(c) is recovery, "
        "returning to idle — not directly to active, because recovery and "
        "reconnection are separate concerns.\n\n"
        "For observers, get_state : Conn → State reports the lifecycle phase, and "
        "get_timeout : Conn → Nat returns the timeout configuration. Both are "
        "total — every connection has a state and a timeout.\n\n"
        "get_error : Conn →? ErrorCode is partial — error information only exists "
        "after a failure. This is a genuine CASL selector of fail: "
        "get_error(fail(c, e)) = e extracts the error code, and get_error is "
        "undefined on all other constructors. The partiality is the key signal: "
        "a selector is defined on its home constructor and undefined elsewhere "
        "(CASL RM §2.3.4). That is what makes mechanical axiom generation safe — "
        "the extraction axiom and the foreign-undefinedness axioms follow from the "
        "free-type structure alone.\n\n"
        "Contrast this with get_timeout. The axiom get_timeout(create(n)) = n "
        "looks like extraction, and get_timeout preserves across all other "
        "constructors. But get_timeout is total — defined everywhere, not just on "
        "create. A total function cannot be a CASL selector, because selectors "
        "must be undefined on foreign constructors. get_timeout is an observer "
        "whose create axiom coincidentally resembles projection. The preservation "
        "axioms (get_timeout(connect(c)) = get_timeout(c), etc.) are domain "
        "equations asserting configuration immutability, not structural "
        "consequences of a free-type declaration.\n\n"
        "I also want a convenience predicate is_active : Conn that answers the "
        "common boolean question 'is this connection currently active?' This is a "
        "derivation from get_state: is_active(c) holds exactly when "
        "get_state(c) = active_st. Every per-constructor is_active axiom follows "
        "by substituting the get_state result for each constructor "
        "into the derivation condition. Both observers require independent obligation coverage"
        "\n\n"
        "The obligation table is 4 observers × 5 constructors = 20 cells, all "
        "PLAIN. No key dispatch since none of the observers take a key parameter. "
        "get_error contributes 5 cells: 1 SELECTOR_EXTRACT (mechanical) and 4 "
        "SELECTOR_FOREIGN (mechanical). The remaining 15 cells require domain "
        "reasoning. Total axioms: 24 (20 obligation + 1 derivation definition + "
        "3 distinctness)."
    ),
)
ALL_EXAMPLES: dict[str, WorkedExample] = {
    "stack": STACK,
    "bug-tracker": BUG_TRACKER,
    "counter": COUNTER,
    "traffic-light": TRAFFIC_LIGHT,
    "boolean-flag": BOOLEAN_FLAG,
    "queue": FIFO_QUEUE,
    "bounded-counter": BOUNDED_COUNTER,
    "phone-book": PHONE_BOOK,
    "temperature-sensor": TEMPERATURE_SENSOR,
    "thermostat": THERMOSTAT,
    "bank-account": BANK_ACCOUNT,
    "door-lock": DOOR_LOCK,
    "todo-list": TODO_LIST,
    "inventory": INVENTORY_TRACKER,
    "shopping-cart": SHOPPING_CART,
    "access-control": ACCESS_CONTROL,
    "library-lending": LIBRARY_LENDING,
    "email-inbox": EMAIL_INBOX,
    "auction": AUCTION,
    "version-history": VERSION_HISTORY,
    "session-store": SESSION_STORE,
    "rate-limiter": RATE_LIMITER,
    "dns-zone": DNS_ZONE,
    "connection": CONNECTION,
}
