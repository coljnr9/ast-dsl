from dataclasses import dataclass


@dataclass(frozen=True)
class DomainPrompt:
    id: str
    name: str
    description: str
    expected_features: set[str]
    complexity: int


DOMAINS: list[DomainPrompt] = [
    DomainPrompt(
        id="counter",
        name="Counter",
        description="A simple counter that can be incremented, decremented, and reset.",
        expected_features=set(),
        complexity=1,
    ),
    DomainPrompt(
        id="traffic-light",
        name="Traffic Light Controller",
        description="A traffic light that cycles through red, yellow, and green states.",
        expected_features={"enumeration"},
        complexity=1,
    ),
    DomainPrompt(
        id="boolean-flag",
        name="Feature Flag",
        description="A feature flag that can be enabled or disabled, with a query for current state.",
        expected_features={"predicate"},
        complexity=1,
    ),
    DomainPrompt(
        id="temperature-sensor",
        name="Temperature Sensor",
        description="A sensor that records temperature readings. New readings replace old. Has a read operation.",
        expected_features=set(),
        complexity=1,
    ),
    DomainPrompt(
        id="stack",
        name="LIFO Stack",
        description="A LIFO stack of elements with push, pop, top, and an emptiness check.",
        expected_features={"partial", "predicate"},
        complexity=2,
    ),
    DomainPrompt(
        id="bank-account",
        name="Bank Account",
        description="A bank account with deposit, withdraw (fails if insufficient funds), and balance check.",
        expected_features={"partial", "predicate"},
        complexity=2,
    ),
    DomainPrompt(
        id="todo-list",
        name="Todo List",
        description="A to-do list where items can be added, completed, and removed. Items have a title and done status.",
        expected_features={"product_sort", "enumeration"},
        complexity=2,
    ),
    DomainPrompt(
        id="door-lock",
        name="Door Lock",
        description="A door lock with states: locked, unlocked, open. Lock/unlock requires a code. Open only works when unlocked.",
        expected_features={"enumeration", "partial", "predicate"},
        complexity=2,
    ),
    DomainPrompt(
        id="queue",
        name="FIFO Queue",
        description="A FIFO queue with enqueue, dequeue, front. Dequeue and front undefined on empty.",
        expected_features={"partial"},
        complexity=2,
    ),
    DomainPrompt(
        id="bounded-counter",
        name="Bounded Counter",
        description="A counter with a maximum value. Increment fails at max. Has observers for value and is-at-max.",
        expected_features={"partial", "predicate", "definedness"},
        complexity=2,
    ),
    DomainPrompt(
        id="phone-book",
        name="Phone Book",
        description="A phone book mapping names to phone numbers. Add, remove, lookup (partial — undefined if name not present).",
        expected_features={"key_dispatch", "partial"},
        complexity=3,
    ),
    DomainPrompt(
        id="inventory",
        name="Inventory",
        description="A warehouse inventory tracking item quantities. Add stock, remove stock (partial if insufficient), query quantity.",
        expected_features={"key_dispatch", "partial"},
        complexity=3,
    ),
    DomainPrompt(
        id="access-control",
        name="Access Control",
        description="A system with users and resources. Grant/revoke permissions. Check if user has access to resource. Admin role bypasses checks.",
        expected_features={"key_dispatch", "predicate", "biconditional"},
        complexity=3,
    ),
    DomainPrompt(
        id="library-lending",
        name="Library Lending System",
        description=(
            "A library system that manages book lending. Books can be registered "
            "in the library's catalog, borrowed by patrons, and returned. Each book "
            "is identified by a unique BookId. The system should track whether each "
            "book is available or currently borrowed, and if borrowed, which patron "
            "(identified by UserId) has it. Borrowing should only succeed if the book "
            "is available, and returning should only succeed if the book is currently "
            "borrowed. Looking up the borrower of a book that isn't currently borrowed "
            "should be undefined."
        ),
        expected_features={"key_dispatch", "partial", "predicate", "definedness"},
        complexity=3,
    ),
    DomainPrompt(
        id="bug-tracker",
        name="Bug Tracker",
        description="A bug tracking system with tickets that have severity, status, and optional assignee. Severity is classified from title and body.",
        expected_features={
            "product_sort",
            "partial",
            "predicate",
            "biconditional",
            "uninterpreted",
            "definedness",
        },
        complexity=3,
    ),
    DomainPrompt(
        id="shopping-cart",
        name="Shopping Cart",
        description="An e-commerce shopping cart. Add/remove items, apply discount code, compute total. Remove fails if item not in cart.",
        expected_features={"key_dispatch", "partial", "uninterpreted"},
        complexity=3,
    ),
    DomainPrompt(
        id="thermostat",
        name="Thermostat",
        description="A thermostat with target temperature, current temperature readings, and heater on/off state. Heater activates when current < target.",
        expected_features={"product_sort", "predicate", "biconditional"},
        complexity=3,
    ),
    DomainPrompt(
        id="email-inbox",
        name="Email Inbox",
        description="An email inbox. Receive messages, mark read/unread, delete, star. Query unread count, starred status.",
        expected_features={"key_dispatch", "predicate", "enumeration"},
        complexity=3,
    ),
    DomainPrompt(
        id="version-history",
        name="Version History",
        description="A version control system for a single document. Commit new versions, revert to previous. Query current content, version number, diff between versions (partial — can't diff with nonexistent version).",
        expected_features={"partial", "definedness"},
        complexity=3,
    ),
    DomainPrompt(
        id="auction",
        name="Auction",
        description="A sealed-bid auction. Register bidders, submit bids (partial — only before deadline), reveal winner. Track highest bid and whether auction is open/closed.",
        expected_features={
            "partial",
            "predicate",
            "uninterpreted",
            "enumeration",
            "definedness",
        },
        complexity=3,
    ),
]
