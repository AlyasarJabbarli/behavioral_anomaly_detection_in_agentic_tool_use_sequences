"""Value provenance: where the email addresses, IBANs and URLs in an action came from.

For every action call (write, delete, send, payment, access), each typed value
in any of its arguments gets a provenance class:

- ``user``: it appears in the user's request (the trusted prompt);
- ``trusted`` / ``untrusted``: otherwise, the trust of the earliest earlier
  output that contained it ("first appearance decides");
- ``none``: it appeared nowhere earlier.

Sources are the outputs of executed reads and of the write tools that echo
third-party text (``ToolCategories.is_value_source``); outputs of other actions
only echo the agent's own arguments. Reads themselves are not checked.

The detector only tests whether a value's string occurs in earlier text; it
never interprets that text.

Typed values:
- email address: ``name@domain.tld``;
- IBAN: two letters, two digits, 10–30 letters or digits (upper case);
- URL: starts with ``http(s)://`` or ``www.``, or is a dotted name ending in one
  of the original generic top-level domains (com, net, org, edu, gov, mil,
  int), optionally followed by a path; only URL characters are taken (letters,
  digits and ``-._~/?#=&%+:``), so markdown such as ``**`` or a following ``!``
  is not part of it. File names such as ``notes.docx`` are not URLs.
Literal escape sequences that agents sometimes write into arguments (``\\n``,
``\\t``, ``\\r``) are treated as spaces before extraction.
Values are compared in lower case; URLs without scheme, ``www.`` and trailing
slash; IBANs also against the text with whitespace removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from trace_ad.features.categories import ToolCategories
from trace_ad.features.intent import ACTION_CATEGORIES
from trace_ad.features.steps import first_true, running_count

USER, TRUSTED, UNTRUSTED, NONE = "user", "trusted", "untrusted", "none"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_URL_CHARS = r"[A-Za-z0-9\-._~/?#=&%+:]"
URL = re.compile(
    rf"https?://{_URL_CHARS}+"
    rf"|\bwww\.{_URL_CHARS}+"
    rf"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|edu|gov|mil|int)\b(?:/{_URL_CHARS}*)?",
    re.IGNORECASE,
)
_LITERAL_ESCAPE = re.compile(r"\\[ntr]")
_TRAILING = ".,;:!?"


def _strings(value: Any) -> list[str]:
    """All string leaves of an argument value (lists and dicts are walked)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def _normalise_url(url: str) -> str:
    url = url.rstrip(_TRAILING).lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.rstrip("/")


def extract_values(value: Any) -> list[tuple[str, str]]:
    """Typed values in an argument value, as (kind, normalised value) pairs."""
    out: list[tuple[str, str]] = []
    for text in _strings(value):
        text = _LITERAL_ESCAPE.sub(" ", text)
        out += [("email", m.lower()) for m in EMAIL.findall(text)]
        text = EMAIL.sub(" ", text)
        out += [("iban", m.lower()) for m in IBAN.findall(text)]
        text = IBAN.sub(" ", text)
        out += [("url", _normalise_url(m)) for m in URL.findall(text)]
    return [(k, v) for k, v in out if v]


@dataclass(frozen=True)
class TypedValue:
    kind: str
    value: str
    argument: str
    provenance: str


def _found(kind: str, value: str, text: str, text_no_space: str) -> bool:
    return value in text or (kind == "iban" and value in text_no_space)


def value_provenance(record: dict[str, Any], cats: ToolCategories) -> list[list[TypedValue]]:
    """Per tool call, the typed values of an action call with their provenance.

    Non-action calls get an empty list.
    """
    suite = record["suite"]
    prompt = (record.get("user_prompt") or "").lower()
    prompt_ns = re.sub(r"\s+", "", prompt)
    sources: list[tuple[str, str, str]] = []  # (text, text without spaces, trust)
    result = []
    for call in record["tool_calls"]:
        values: list[TypedValue] = []
        if cats.category(suite, call["function"]) in ACTION_CATEGORIES:
            for arg, raw in (call.get("args") or {}).items():
                for kind, value in extract_values(raw):
                    if _found(kind, value, prompt, prompt_ns):
                        prov = USER
                    else:
                        prov = next(
                            (trust for text, ns, trust in sources if _found(kind, value, text, ns)),
                            NONE,
                        )
                    values.append(TypedValue(kind, value, arg, prov))
        result.append(values)
        if (
            call["executed"]
            and call.get("output")
            and cats.is_value_source(suite, call["function"])
        ):
            text = call["output"].lower()
            trust = UNTRUSTED if cats.output_untrusted(suite, call["function"]) else TRUSTED
            sources.append((text, re.sub(r"\s+", "", text), trust))
    return result


def provenance_flags(record: dict[str, Any], cats: ToolCategories) -> list[dict[str, bool]]:
    """Per tool call: does it carry an ``untrusted`` value, a ``none`` value?"""
    return [
        {
            "untrusted": any(v.provenance == UNTRUSTED for v in values),
            "none": any(v.provenance == NONE for v in values),
        }
        for values in value_provenance(record, cats)
    ]


def running_untrusted_count(flags: list[dict[str, bool]]) -> list[int]:
    """Number of action calls carrying an untrusted value, up to and including each step."""
    return running_count([f["untrusted"] for f in flags])


def first_untrusted_step(flags: list[dict[str, bool]]) -> int | None:
    return first_true([f["untrusted"] for f in flags])
