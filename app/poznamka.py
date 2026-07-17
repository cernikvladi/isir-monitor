"""Parsing helpers for the ISIR WS_1 `poznamka` payload.

`poznamka` is a CDATA-wrapped XML document attached to some events, whose
schema (`verzeXsd`) has changed several times over the service's lifetime
(see Popis_WS_1 1.2.3). Rather than hardcode every field per schema version,
this walks the tree generically into a plain dict/JSON structure so nothing
is lost even as the schema evolves - normalized columns in app.sync only
pick out the fields we currently care about.
"""

from datetime import datetime

from lxml import etree


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _element_to_value(element: etree._Element):
    children = list(element)
    if not children:
        return element.text
    value: dict = {}
    for child in children:
        key = _local_name(child.tag)
        child_value = _element_to_value(child)
        if key in value:
            existing = value[key]
            if isinstance(existing, list):
                existing.append(child_value)
            else:
                value[key] = [existing, child_value]
        else:
            value[key] = child_value
    return value


def parse_poznamka(poznamka_xml: str | None) -> dict | None:
    """Parse the poznamka CDATA XML into a plain nested dict, or None if empty."""
    if not poznamka_xml or not poznamka_xml.strip():
        return None
    root = etree.fromstring(poznamka_xml.encode("utf-8"))
    data = _element_to_value(root)
    if not isinstance(data, dict):
        data = {}
    verze_xsd = root.get("verzeXsd")
    if verze_xsd:
        data["_verzeXsd"] = verze_xsd
    return data


def parse_isir_date(value: str | None) -> datetime | None:
    """Parse ISIR's date/dateTime strings.

    Two shapes show up in practice:
    - dateTime: "2022-02-01T12:50:40.000+01:00"
    - date with a timezone suffix instead of a time: "2017-07-12+02:00"
    """
    if not value:
        return None
    # Only trust fromisoformat directly when a "T<time>" separator is present.
    # Without it, e.g. "2017-07-12+02:00" is a bare date + UTC offset, but
    # fromisoformat silently misreads the offset as a local time instead
    # (datetime.fromisoformat("2017-07-12+02:00") -> 2017-07-12 02:00:00,
    # dropping the offset entirely) - so route those through the manual split below.
    if "T" in value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    # "date" fields come as YYYY-MM-DD followed directly by a UTC offset
    # (no "T<time>" separator), which fromisoformat mishandles.
    for sep in ("+", "-"):
        idx = value.rfind(sep)
        if idx > 9:  # skip the offset embedded in the date itself (YYYY-MM-DD)
            date_part, offset = value[:idx], value[idx:]
            try:
                return datetime.fromisoformat(f"{date_part}T00:00:00{offset}")
            except ValueError:
                continue
    # Plain "YYYY-MM-DD" with no offset at all.
    try:
        return datetime.fromisoformat(f"{value}T00:00:00")
    except ValueError:
        return None
