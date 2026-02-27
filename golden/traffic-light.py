"""
### Step 1: Identify Sorts
To model the traffic light, we need to represent two distinct concepts: the physical states the light can be in, and the traffic light itself as a stateful entity.
*   **`Color`**: An atomic sort acting as an enumeration. It represents the actual set of possible colors (Red, Yellow, Green).
*   **`Light`**: An atomic sort representing the traffic light system. It holds the state and transitions over time.

### Step 2: Classify Functions and Predicates
**For `Color`:**
*   `red : → Color` — **Constructor** (constant).
*   `yellow : → Color` — **Constructor** (constant).
*   `green : → Color` — **Constructor** (constant).
*   `next_color : Color → Color` — **Observer/Combinator**. Returns the deterministic next color in the sequence. Separating this from the `Light` itself gives us a much cleaner mathematical model.

**For `Light`:**
*   `init : → Light` — **Constructor**. Starts the light in an initial configuration.
*   `cycle : Light → Light` — **Constructor**. Advances the light to its next state. Total.
*   `color : Light → Color` — **Observer**. Returns the current color of the traffic light. Total.

### Step 3: Build the Axiom Obligation Table
Following the rule that every observer must be defined against every constructor of its primary sort:

**Observer `next_color` (Primary sort: `Color`)**
*   Constructors: `red`, `green`, `yellow`
1.  `next_color` × `red`: Cycles Red to Green. -> `green`
2.  `next_color` × `green`: Cycles Green to Yellow. -> `yellow`
3.  `next_color` × `yellow`: Cycles Yellow to Red. -> `red`

**Observer `color` (Primary sort: `Light`)**
*   Constructors: `init`, `cycle`
4.  `color` × `init`: The light defaults to Red. -> `red`
5.  `color` × `cycle`: Applying a cycle transition to the light causes its `color` to map through the `next_color` combinator. -> `next_color(color(l))`

### Completeness Count & Tricky Cases
*   Total axioms required: 3 (for `next_color`) + 2 (for `color`) = **5 axioms**.
*   **Design Decision (Helper Function):** Rather than writing conditional axioms (e.g. using `Implication` matching an explicit state) for `color(cycle(l))`, which can be computationally bloated, we split the domain into the sequence definition (`next_color`) and the stateful container (`cycle`). This transforms what would have been multi-conditional branching into a highly readable, unconditional structural equation: `color(cycle(l)) = next_color(color(l))`.
*   **Design Decision (Sequence):** Followed the standard global sequence model: Red (stop) -> Green (go) -> Yellow (prepare to stop) -> Red.
"""

from alspec import (
    Axiom, Signature, Spec,
    atomic, fn, var, app, const, eq, forall
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
        predicates={}
    )
    
    axioms = (
        # ━━ next_color: defining the raw sequence ━━
        
        Axiom(
            label="next_color_red",
            formula=eq(
                app("next_color", const("red")), 
                const("green")
            )
        ),
        Axiom(
            label="next_color_green",
            formula=eq(
                app("next_color", const("green")), 
                const("yellow")
            )
        ),
        Axiom(
            label="next_color_yellow",
            formula=eq(
                app("next_color", const("yellow")), 
                const("red")
            )
        ),
        
        # ━━ color: defining the light's state representation ━━
        
        Axiom(
            label="color_init",
            formula=eq(
                app("color", const("init")), 
                const("red")
            )
        ),
        Axiom(
            label="color_cycle",
            formula=forall([l], eq(
                app("color", app("cycle", l)),
                app("next_color", app("color", l))
            ))
        ),
    )
    
    return Spec(name="TrafficLight", signature=sig, axioms=axioms)
