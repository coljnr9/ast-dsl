import textwrap

from alspec.basis import ALL_BASIS_SPECS


def render() -> str:
    parts: list[str] = []

    parts.append(
        textwrap.dedent(
            """\
            ## 4. Basis Library (Standard Patterns)

            Pre-built, verified specifications covering fundamental algebraic patterns.
            Use these to recognize when your domain matches an existing pattern.
            Sources: CASL Basic Libraries (CoFI), Sannella & Tarlecki (2012).
            """
        )
    )

    for spec_fn in ALL_BASIS_SPECS:
        sp = spec_fn()
        sig = sp.signature

        parts.append(f"### {sp.name}\n")

        # One-line description from docstring
        if spec_fn.__doc__:
            doc = textwrap.dedent(spec_fn.__doc__).strip()
            first_line = doc.split("\n")[0]
            parts.append(f"{first_line}\n")

        # Signature profile
        sort_names = ", ".join(sig.sorts.keys())
        parts.append(f"**Sorts:** {sort_names}  ")

        if sig.functions:
            fn_lines = []
            for f in sig.functions.values():
                params = " × ".join(f"{p.sort}" for p in f.params)
                arrow = "→" if f.totality.value == "total" else "→?"
                profile = (
                    f"{params} {arrow} {f.result}" if params else f"{arrow} {f.result}"
                )
                fn_lines.append(f"`{f.name} : {profile}`")
            parts.append(f"**Functions:** {', '.join(fn_lines)}  ")

        if sig.predicates:
            pred_lines = []
            for p in sig.predicates.values():
                params = " × ".join(str(pp.sort) for pp in p.params)
                pred_lines.append(f"`{p.name} : {params}`")
            parts.append(f"**Predicates:** {', '.join(pred_lines)}  ")

        ax_names = ", ".join(a.label for a in sp.axioms)
        parts.append(f"**Axioms ({len(sp.axioms)}):** {ax_names}\n")

    parts.append("---\n")
    return "\n".join(parts)
