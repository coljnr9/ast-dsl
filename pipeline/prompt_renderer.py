"""Prompt rendering from Jinja2 templates."""

from pathlib import Path

import typing
import jinja2

TEMPLATE_DIR = Path(__file__).parent / "prompt_templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs: typing.Any) -> str:
    return _env.get_template(template_name).render(**kwargs)
