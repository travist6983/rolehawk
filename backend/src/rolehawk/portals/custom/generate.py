"""When detection finds nothing, Claude reads the page and proposes a definition: a JSON API
(if the page reveals one) or CSS selectors. The proposal is data, validated like any other
definition and test-run before the user can enable it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from rolehawk.llm.prompting import UNTRUSTED_RULES, untrusted
from rolehawk.portals.custom.definition import (
    FieldMap,
    HtmlDefinition,
    HtmlFields,
    JsonApiDefinition,
)
from rolehawk.portals.custom.detect import PageSample, slugify

RULES = f"""You help add a company's careers page to a job search app. The app has a small
engine that can read a job list in one of two ways; you choose one and fill in its settings.

1. "json_api": the page loads its jobs from a JSON URL. Use this only if you can see the URL
   in the page or in the API hints. Give api_url (GET, same site), items_path (dot path to
   the list, e.g. "data.jobs"; "" if the response is the list), and dot paths inside one job
   for title, url, and optionally id, location, company, description.
2. "html": the jobs are plain HTML. Give item_selector (a CSS selector matching each job
   once), and selectors inside an item for the title, optionally the link (default: the
   title's link), location, and company. Prefer stable class names; avoid :nth-child.

If neither works (the jobs aren't on the page), answer "none" and say why in reason.
Never use URLs on another site.

{UNTRUSTED_RULES}"""


class AiDraft(BaseModel):
    kind: Literal["json_api", "html", "none"]
    reason: str = Field(description="One sentence on why this approach")
    api_url: str | None
    items_path: str | None
    title_path: str | None
    url_path: str | None
    id_path: str | None
    location_path: str | None
    company_path: str | None
    description_path: str | None
    item_selector: str | None
    title_selector: str | None
    link_selector: str | None
    location_selector: str | None
    company_selector: str | None


class DraftError(ValueError):
    pass


def draft_prompt(sample: PageSample) -> str:
    hints = "\n".join(f"- {h}" for h in sample.api_hints) or "(none found)"
    return (
        f"Careers page: {sample.url}\n\nAPI-looking URLs found in the page's scripts:\n"
        f"{hints}\n\n{untrusted('careers_page', sample.excerpt)}\n\n"
        "How should the engine read this job list?"
    )


def to_definition(draft: AiDraft, url: str, name: str) -> JsonApiDefinition | HtmlDefinition:
    ident, label = slugify(name), name[:80]
    try:
        if draft.kind == "json_api" and draft.api_url and draft.title_path and draft.url_path:
            return JsonApiDefinition(
                id=ident,
                name=label,
                source_url=url,
                api_url=draft.api_url,
                items_path=draft.items_path or "",
                fields=FieldMap(
                    title=draft.title_path,
                    url=draft.url_path,
                    id=draft.id_path,
                    location=draft.location_path,
                    company=draft.company_path,
                    description=draft.description_path,
                ),
            )
        if draft.kind == "html" and draft.item_selector and draft.title_selector:
            return HtmlDefinition(
                id=ident,
                name=label,
                source_url=url,
                list_url=url,
                item_selector=draft.item_selector,
                fields=HtmlFields(
                    title=draft.title_selector,
                    link=draft.link_selector,
                    location=draft.location_selector,
                    company=draft.company_selector,
                ),
            )
    except ValidationError as exc:
        raise DraftError(f"Claude's proposal wasn't valid: {exc.errors()[0]['msg']}") from exc
    raise DraftError(draft.reason or "Claude couldn't find a way to read this page.")
