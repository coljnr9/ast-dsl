"""
### **Step 1: Identify Sorts**
- `Queue`: The primary domain object representing the FIFO queue. modeled as an **atomic** sort (its state is managed by its constructors).
- `Elem`: The type of data stored inside the queue. Modeled as an **atomic** sort.

### **Step 2: Classify Functions**
- `empty : → Queue`: **Constructor**. Creates an empty queue.
- `enqueue : Queue × Elem → Queue`: **Constructor**. Adds a new element to the back (tail) of the queue. Total.
- `dequeue : Queue →? Queue`: **Observer**. Removes an element from the front (head) of the queue. **Partial**, undefined when the queue is empty.
- `front : Queue →? Elem`: **Observer**. Retrieves the element at the front. **Partial**, undefined when the queue is empty.

Note: `dequeue` and `front` are NOT selectors — their axioms involve structural recursion,
not simple component extraction. `front(enqueue(empty, e)) = e` works because of the base
case structure, not direct extraction of `e` from `enqueue`.

*(Note: We omit an `is_empty` predicate because algebraic pattern matching on the constructors is sufficient and avoids introducing unrequested predicates.)*

### **Step 3: Build the Axiom Obligation Table**
For each (observer, constructor) pair, we write an axiom.
Under loose semantics, every cell must be filled — no omissions.
Observers: `dequeue`, `front`
Constructors: `empty`, `enqueue`

Since `Queue` follows a FIFO discipline, elements are enqueued at the back but dequeued from the front. This means `dequeue` and `front` on an `enqueue(q, e)` term branch depending on whether `q` is already empty or not. We can elegantly represent "not empty" without testing conditionals by structurally pattern matching `q` as `enqueue(q', e')`—since all valid, non-empty queues are produced by `enqueue`.

| Observer | Constructor / Subcase | Cell Type | Axiom Label | Behavior |
|----------|-----------------------|-----------|-------------|----------|
| `dequeue` (partial) | `empty` | `DOMAIN` | `dequeue_empty_undef` | `¬def(dequeue(empty))` — undefined |
| `dequeue` (partial) | `enqueue` / `q = empty` | `DOMAIN` | `dequeue_empty_enqueue` | `dequeue(enqueue(empty, e)) = empty` |
| `dequeue` (partial) | `enqueue` / `q = enqueue(q', e')` | `DOMAIN` | `dequeue_nonempty_enqueue` | `dequeue(enqueue(enqueue(q, e1), e2)) = enqueue(dequeue(enqueue(q, e1)), e2)` |
| `front` (partial) | `empty` | `DOMAIN` | `front_empty_undef` | `¬def(front(empty))` — undefined |
| `front` (partial) | `enqueue` / `q = empty` | `DOMAIN` | `front_empty_enqueue` | `front(enqueue(empty, e)) = e` |
| `front` (partial) | `enqueue` / `q = enqueue(q', e')`| `DOMAIN` | `front_nonempty_enqueue` | `front(enqueue(enqueue(q, e1), e2)) = front(enqueue(q, e1))` |

**Tricky Cases & Design Decisions:**
Unlike a LIFO stack where `pop(push(S, e)) = S`, the FIFO restriction means we can't merely undo the outermost `enqueue`—that element is at the back. By substituting `enqueue(q, e1)` directly in place of `q`, we safely decompose non-empty queues to isolate changes at the front, preserving the structure at the back.

**Completeness Count:**
- `dequeue`: 2 constructors (empty, enqueue) = 3 total axioms (1 undef + 2 equations split on enqueue shape)
- `front`: 2 constructors (empty, enqueue) = 3 total axioms (1 undef + 2 equations split on enqueue shape)
- **Total: 6 axioms**
"""

def queue_spec():
    from alspec import (
        Axiom, Definedness, GeneratedSortInfo, Negation, Signature, Spec,
        atomic, fn, var, app, const, eq, forall
    )

    # Variables for our axioms
    q = var("q", "Queue")
    e = var("e", "Elem")
    e1 = var("e1", "Elem")
    e2 = var("e2", "Elem")

    # Define the Signature
    sig = Signature(
        sorts={
            "Queue": atomic("Queue"),
            "Elem": atomic("Elem"),
        },
        functions={
            # Constructors
            "empty": fn("empty", [], "Queue"),
            "enqueue": fn("enqueue", [("q", "Queue"), ("e", "Elem")], "Queue"),

            # Partial Observers (not selectors — computed, not extracted)
            "dequeue": fn("dequeue", [("q", "Queue")], "Queue", total=False),
            "front": fn("front", [("q", "Queue")], "Elem", total=False),
        },
        predicates={},
        generated_sorts={
            "Queue": GeneratedSortInfo(
                constructors=("empty", "enqueue"),
                selectors={},  # front/dequeue compute, they don't extract components
            )
        },
    )

    # Implement Axiom Obligation Table
    axioms = (
        # ━━ dequeue ━━
        # dequeue × empty: explicit undefinedness required (DOMAIN, partial obs × base ctor)
        Axiom(
            label="dequeue_empty_undef",
            formula=Negation(Definedness(app("dequeue", const("empty"))))
        ),
        # Dequeueing a queue with 1 element leaves it empty
        Axiom(
            label="dequeue_empty_enqueue",
            formula=forall([e],
                eq(
                    app("dequeue", app("enqueue", const("empty"), e)),
                    const("empty")
                )
            )
        ),
        # Dequeueing a queue with >1 element removes the frontmost component
        # dequeue(enqueue(enqueue(q, e1), e2)) = enqueue(dequeue(enqueue(q, e1)), e2)
        Axiom(
            label="dequeue_nonempty_enqueue",
            formula=forall([q, e1, e2],
                eq(
                    app("dequeue", app("enqueue", app("enqueue", q, e1), e2)),
                    app("enqueue", app("dequeue", app("enqueue", q, e1)), e2)
                )
            )
        ),

        # ━━ front ━━
        # front × empty: explicit undefinedness required (DOMAIN, partial obs × base ctor)
        Axiom(
            label="front_empty_undef",
            formula=Negation(Definedness(app("front", const("empty"))))
        ),
        # Front of a queue with 1 element is that element
        Axiom(
            label="front_empty_enqueue",
            formula=forall([e],
                eq(
                    app("front", app("enqueue", const("empty"), e)),
                    e
                )
            )
        ),
        # Front of a queue with >1 element accesses the deeper, frontmost element
        # front(enqueue(enqueue(q, e1), e2)) = front(enqueue(q, e1))
        Axiom(
            label="front_nonempty_enqueue",
            formula=forall([q, e1, e2],
                eq(
                    app("front", app("enqueue", app("enqueue", q, e1), e2)),
                    app("front", app("enqueue", q, e1))
                )
            )
        ),
    )

    return Spec(name="FIFOQueue", signature=sig, axioms=axioms)
