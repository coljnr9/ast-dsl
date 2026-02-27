"""Prompt rendering using Jinja2 templates."""

import os
from typing import Any

import jinja2

# Setup jinja2 environment pointing to alspec/templates
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATE_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs: Any) -> str:
    """Render a Jinja2 template with the given keyword arguments."""
    template = _ENV.get_template(template_name)
    return template.render(**kwargs)
