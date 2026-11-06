#!/usr/bin/env python3
"""Build a Resales-Online import XML (v1.5) from the website catalog.

Reads site/data.json, keeps sales (operation Venta), and writes
site/resales-import.xml. That file is the feed for the automated import:
only the client's own sales, never the Balearics search dump. lasboas-top
stays out: that apartment is already in Resales. Resales collects the file
from a URL once a day. This script does not call Resales and does not
invent cadastral references, commission, image size, floor counts,
feature labels, or bedroom and bathroom counts. A layout line the
catalog sync drops can still supply one bedroom count. Those sentences
are in PUBLIC_PAGE_TEXT. A range stays empty, and Rooms is never copied.
bedrooms and bathrooms are Numeric in schema 1.5. That definition
documents no N/A token. add() omits a node when the text is empty, and
that omission is how a commercial property or a plot is marked not
applicable. Website types Hotel, Restaurant, Commercial space, and
Building land (Resales types Commercial and Plot) omit both nodes even
when the catalog stores a number. The feed does not write 0 and does
not write "N/A". A dwelling keeps the verified count. Spanish text is
read from sync/descriptions_es.json, a translation of the English
catalog copy. The website sync does not rewrite that file. The
translation should be reviewed with the client.
saleType is Freehold and shared is 0 on every sale. Both are provisional
defaults and must be checked listing by listing with the client.
Commission stays in the feed setup.

address1 is the catalog zone when that zone names a place other than
the island. A municipality yields to a finer place named in the title
(Cala Tarida, Es Pujols, Sa Caleta). If the zone is empty or only
"Ibiza", the place is taken from the English description, then from
the title. There is no default street.

See sync/RESALES_IMPORT.md for the field map and the setup steps.
Schema: https://devdocs.resales-online.com/docs/property-import-xml-definition-1-5/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "site" / "data.json"
DEFAULT_OUT = ROOT / "site" / "resales-import.xml"
# Kept beside the generator. sync_catalog.py rewrites site/data.json from
# the English website and would drop a Spanish field stored there.
DEFAULT_SPANISH = Path(__file__).resolve().parent / "descriptions_es.json"

# "Ibiza" is the island, already stored as the town. It is not a street.
GENERIC_ZONES = {"ibiza"}

# The card stores the municipality. A place in the title is more specific.
COARSE_ZONES = {
    "sant josep de sa talaia",
    "sant antoni de portmany",
    "santa eulària des riu",
    "santa eularia des riu",
    "formentera",
}

# The catalog only has the municipality. The client wants this zone name.
CLIENT_ZONES = {
    "vedella-27": "Cala Vedella",
}

# Already in Resales (internal ref R5442232). Left out of the feed.
# If that slug is ever included, the agency reference must be LasBoas-7.1,
# not the website slug, or the first import creates a duplicate.
EXCLUDE_SLUGS = {"lasboas-top"}
AGENCY_REFS = {"lasboas-top": "LasBoas-7.1"}

# The catalog does not record tenure. Freehold is the usual default in
# Ibiza and is written on every sale in this feed. It is provisional:
# confirm each listing with the client before the feed is handed over.
DEFAULT_SALE_TYPE = "Freehold"

# Las Boas (R5442232) has Compartido unticked. 0 keeps the 35 off the
# network until the client confirms each listing. 1 would share them.
DEFAULT_SHARED = "0"

# Enlarged photos live in this public repository. The agency website
# does not serve /photos/ (that path returns 404).
RESIZED_PHOTO_BASE = (
    "https://raw.githubusercontent.com/sandmomy/Archon/"
    "cursor/resales-import-xml-eff5/amaranthus-crm/site/"
)

# These files are the "More properties" cards, not the listing itself.
RELATED_IMAGE_OWNER = {
    "1ecd2306": "lasboas-top",
    "9a1f052f": "bossanova",
    "341b3b15": "espujols-flats",
}

# Place names that appear in the English descriptions and titles.
# Longer names first so "Playa d'en Bossa" wins over a shorter neighbour.
PLACE_NAMES = (
    "Playa d'en Bossa",
    "Platja d'en Bossa",
    "Passeig de Vara de Rey",
    "Marina Botafoch",
    "Cala Vedella",
    "Cala Tarida",
    "Vista Alegre",
    "Vistalegre",
    "Figueretes",
    "Es Cubells",
    "Illa Plana",
    "Plaza del Parque",
    "Es Torrent",
    "Cas Mut",
    "Jesús",
    "Jesus",
    "Talamanca",
    "Ibiza Town",
    "Dalt Vila",
    "Sa Caleta",
    "Benimussa",
    "San Augustin",
    "Es Pujols",
    "Sa Serra",
)

# The property is in this place.
LOCATED = re.compile(
    r"(in the heart of|located in|located near|set in|situated in|gated community of|area of|nestled within|in the centre of|in the center of)\s+$",
    re.I,
)
# A neighbour or a view. Used only when no location phrase names a place.
NEARBY = re.compile(
    r"(toward|towards|minutes from|close to|next to|near|walk from|short walk from|views of|views over|overlooking|stretching|proximity to)\s+$",
    re.I,
)

# Website type -> (Resales type, Resales subtype). Subtypes are the closest
# Appendix 1 labels. The catalog does not store a Resales subtype.
TYPE_MAP = {
    "Apartment": ("Apartment", "Middle Floor"),
    "Penthouse": ("Apartment", "Penthouse"),
    "Villa": ("House", "Villa"),
    "Building land": ("Plot", "Land"),
    "Hotel": ("Commercial", "Hotel"),
    "Restaurant": ("Commercial", "Restaurant"),
    "Commercial space": ("Commercial", "Commercial Premises"),
}

# Not a dwelling. The catalog calls a plot "Building land". The cafe is
# "Commercial space". A bar is not a separate type here; one filed as
# Restaurant or Commercial space follows the same rule. Resales types
# Commercial and Plot are included so the feed type, not only the
# website label, decides.
NOT_APPLICABLE_WEBSITE_TYPES = frozenset({
    "Hotel",
    "Restaurant",
    "Commercial space",
    "Building land",
    "Plot",
})
NOT_APPLICABLE_RESALES_TYPES = frozenset({"Commercial", "Plot"})

FEATURE_MAP = {
    "Swimming pool": ("Pool", "Private"),
    "Parking": ("Parking", "Private"),
    "Garage box": ("Parking", "Garage"),
    "Underground garage": ("Parking", "Underground"),
    "Mountain view": ("Views", "Mountain"),
    "Lift": ("Features", "Lift"),
    "Balcony": ("Features", "Balcony"),
    "Fireplace": ("Features", "Fireplace"),
    "Cellar": ("Features", "Storage Room"),
    "Storeroom": ("Features", "Storage Room"),
}

# Appendix 2 labels taken from the listing's own wording, and only when
# the catalog features list is empty.
TEXT_FEATURES = {
    "boutiquehotel": [("Setting", "Close To Sea")],
    "cafe-bistro": [("Features", "Private Terrace"), ("Setting", "Village")],
    "restaurant-marina": [("Setting", "Marina"), ("Features", "Private Terrace")],
    "restaurant-varaderey": [("Setting", "Town"), ("Features", "Private Terrace")],
    "patioblanco": [("Pool", "Communal"), ("Features", "Private Terrace"), ("Setting", "Marina")],
    "vedella-27": [("Features", "Private Terrace"), ("Setting", "Close To Sea")],
}

# Layout lines the public page shows and the catalog sync drops. It keeps
# paragraphs and skips the list. Read only when the Bedrooms fact and the
# catalog title and description do not already give one count. The same
# single-count rule applies, so a range stays empty. This is not the Rooms fact.
# patioblanco, layout list of this apartment (not a related card), checked
# 2026-11-06 at https://www.amaranthus-realestate.com/real-estate/patioblanco :
# "2 bedrooms".
PUBLIC_PAGE_TEXT = {
    "patioblanco": "2 bedrooms",
}


def load_sales(path: Path) -> list[dict]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise SystemExit(f"El catálogo no es una lista: {path}")
    return [
        item
        for item in catalog
        if item.get("operation") == "Venta" and str(item.get("slug") or "") not in EXCLUDE_SLUGS
    ]


def fact(item: dict, name: str) -> str:
    value = (item.get("facts") or {}).get(name)
    return str(value).strip() if value not in (None, "") else ""


def number(text: str) -> str:
    match = re.search(r"\d+(?:[.,]\d+)?", text.replace("'", ""))
    if not match:
        return ""
    return match.group(0).replace(",", ".")


def whole(text: str) -> str:
    raw = number(text)
    if not raw:
        return ""
    return str(int(float(raw)))


def add(parent: ET.Element, tag: str, text: str | None) -> None:
    if text is None or text == "":
        return
    node = ET.SubElement(parent, tag)
    node.text = text


def description_text(item: dict) -> str:
    parts = item.get("description") or []
    if isinstance(parts, str):
        return parts.strip()
    return "\n\n".join(part.strip() for part in parts if str(part).strip())


def paragraphs_to_text(value: object) -> str:
    if isinstance(value, list):
        return "\n\n".join(str(part).strip() for part in value if str(part).strip())
    return str(value or "").strip()


def load_spanish(path: Path) -> dict[str, str]:
    """Spanish by slug. Keys starting with '_' are notes, not listings."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"El archivo de español no es un objeto: {path}")
    out: dict[str, str] = {}
    for slug, value in raw.items():
        key = str(slug).strip()
        if not key or key.startswith("_"):
            continue
        text = paragraphs_to_text(value)
        if text:
            out[key] = text
    return out


def spanish_text(item: dict, spanish: dict[str, str]) -> str:
    return spanish.get(str(item.get("slug") or "").strip(), "")


def image_urls(item: dict) -> list[str]:
    slug = str(item.get("slug") or "")
    urls: list[str] = []
    for url in [item.get("image"), *(item.get("gallery") or [])]:
        text = str(url or "").strip()
        if not text or text in urls:
            continue
        if any(
            token in text and slug != owner
            for token, owner in RELATED_IMAGE_OWNER.items()
        ):
            continue
        if text.startswith("photos/"):
            text = RESIZED_PHOTO_BASE + text
        urls.append(text)
    return urls


def _single_count(text: str, word: str) -> str:
    """One explicit count. A range such as '1 and 2 bedrooms' is not a count."""
    if re.search(rf"\d+\s*(?:-|\band\b)\s*(?:and\s+)?\d+[-\s]*{word}", text, re.I):
        return ""
    if re.search(rf"\b(?:one|two|three)\s*-\s*and\s+(?:one|two|three)-{word}", text, re.I):
        return ""
    found = re.findall(rf"\b(\d+)\s+(?:\w+\s+){{0,2}}{word}s?\b", text, re.I)
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return ""


def bedrooms(item: dict) -> str:
    """Bedrooms only. Rooms is a different fact and is not copied across."""
    direct = whole(fact(item, "Bedrooms"))
    if direct:
        return direct
    text = f"{item.get('title') or ''}\n{description_text(item)}"
    found = _single_count(text, "bedroom")
    if found:
        return found
    extra = PUBLIC_PAGE_TEXT.get(str(item.get("slug") or "").strip(), "")
    return _single_count(extra, "bedroom")


def bathrooms(item: dict) -> str:
    # The fact wins over a conflicting sentence. whiteangel lists
    # Bathrooms 2 and one sentence says "3-bathroom"; the feed keeps 2.
    direct = whole(fact(item, "Bathrooms"))
    if direct:
        return direct
    text = f"{item.get('title') or ''}\n{description_text(item)}"
    return _single_count(text, "bathroom")


def counts_not_applicable(item: dict) -> bool:
    """Commercial properties and plots omit bedrooms and bathrooms.

    Resales XML 1.5 defines both fields as Numeric and documents no N/A
    token. add() already omits a node when the text is empty, so that
    omission is how these listings are marked not applicable. Do not
    write 0 and do not write "N/A". A catalog number is still omitted:
    it is not a dwelling count for this feed.
    """
    website_type = str(item.get("type") or "").strip()
    if website_type in NOT_APPLICABLE_WEBSITE_TYPES:
        return True
    mapped = TYPE_MAP.get(website_type)
    resales_type = mapped[0] if mapped else ""
    return resales_type in NOT_APPLICABLE_RESALES_TYPES


def bedroom_text(item: dict) -> str:
    if counts_not_applicable(item):
        return ""
    return bedrooms(item)


def bathroom_text(item: dict) -> str:
    if counts_not_applicable(item):
        return ""
    return bathrooms(item)


def reference_id(item: dict) -> str:
    slug = str(item.get("slug") or "").strip()
    return AGENCY_REFS.get(slug, slug)


def town_name(item: dict) -> str:
    zone = str(item.get("zone") or "").strip()
    if zone.casefold() == "ibiza":
        return "Ibiza"
    return zone


def real_street(item: dict) -> str:
    for key in ("address1", "street", "address"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def specific_zone(item: dict) -> str:
    zone = str(item.get("zone") or "").strip()
    if not zone or zone.casefold() in GENERIC_ZONES:
        return ""
    return zone


def area_from_text(text: str) -> str:
    """Place the text treats as the property's zone, not a neighbour or a view."""
    folded = text.casefold()
    ranked: list[tuple[int, int, str]] = []
    for name in PLACE_NAMES:
        key = name.casefold()
        start = 0
        while True:
            index = folded.find(key, start)
            if index < 0:
                break
            prefix = folded[max(0, index - 48):index]
            if LOCATED.search(prefix):
                rank = 0
            elif NEARBY.search(prefix):
                rank = 2
            else:
                rank = 1
            ranked.append((rank, index, name))
            start = index + len(key)
    if not ranked:
        return ""
    ranked.sort()
    best = ranked[0][0]
    # A view or a neighbour is not the zone when nothing better was said.
    if best == 2:
        return ""
    return ranked[0][2]


def area_from_copy(item: dict) -> str:
    """Place named in the English description, then in the title."""
    return area_from_text(description_text(item)) or area_from_text(str(item.get("title") or ""))


STREET_RE = re.compile(
    r"\b(?:Calle|Carrer)\s+[A-ZÀ-ÿ][\wÀ-ÿ'’.\-]*(?:\s+[A-ZÀ-ÿ][\wÀ-ÿ'’.\-]*)*\s+\d+\b"
    r"|\bPasseig(?:\s+(?:de\s+)?[A-ZÀ-ÿ][\wÀ-ÿ'’.\-]+){1,4}",
)


def concrete_street(item: dict) -> str:
    """A postal street named in the English description, such as Calle Calvià 27."""
    match = STREET_RE.search(description_text(item))
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(0)).strip(" ,.;")


def title_place(item: dict) -> str:
    """Place named in the title, such as Cala Tarida or Es Pujols."""
    return area_from_text(str(item.get("title") or ""))


def zone_name(item: dict) -> str:
    chosen = CLIENT_ZONES.get(str(item.get("slug") or "").strip())
    if chosen:
        return chosen
    zone = specific_zone(item)
    titled = title_place(item)
    if titled and zone.casefold() in COARSE_ZONES and titled.casefold() not in zone.casefold():
        return titled
    return zone or area_from_copy(item)


def street_line(item: dict) -> str:
    explicit = real_street(item)
    if explicit:
        return explicit
    zone = zone_name(item)
    street = concrete_street(item)
    if street and zone and street.casefold() not in zone.casefold():
        return f"{street}, {zone}"
    return street or zone


def property_element(item: dict, spanish: dict[str, str] | None = None) -> ET.Element:
    website_type = str(item.get("type") or "")
    mapped = TYPE_MAP.get(website_type)
    resales_type, subtype = mapped if mapped else ("", "")
    if "Ground floor" in (item.get("features") or []) and resales_type == "Apartment":
        subtype = "Ground Floor"
    features = item.get("features") or []
    ref = reference_id(item)
    prop = ET.Element("property")
    add(prop, "referenceId", ref)
    add(prop, "type", resales_type)
    add(prop, "subType", subtype)
    add(prop, "currency", str(item.get("currency") or "").strip())
    add(prop, "sizeType", "1")
    add(prop, "status", "Off Market" if item.get("off_market") else "Available")
    if "New build" in features:
        add(prop, "newBuild", "1")

    address = ET.SubElement(prop, "address")
    add(address, "address1", street_line(item))
    add(address, "town", town_name(item))
    add(address, "province", "Islas Baleares")
    add(address, "country", "Spain")

    sale = ET.SubElement(prop, "saleDetails")
    add(sale, "saleReferenceId", ref)
    add(sale, "saleType", DEFAULT_SALE_TYPE)
    add(sale, "shared", DEFAULT_SHARED)
    add(sale, "price", whole(str(item.get("price") or "")))

    sizes = ET.SubElement(prop, "propertySizes")
    add(sizes, "built", whole(fact(item, "Net living area") or fact(item, "Usable area")))
    add(sizes, "terrace", whole(fact(item, "Terrace area") or fact(item, "Balcony area")))
    add(sizes, "plot", whole(fact(item, "Plot area")))
    add(sizes, "garden", whole(fact(item, "Garden area")))

    # Empty text makes add() skip the node. For commercial properties and
    # plots that skip is the not-applicable mark: the schema has no other value.
    add(prop, "bedrooms", bedroom_text(item))
    add(prop, "bathrooms", bathroom_text(item))
    add(prop, "floor", whole(fact(item, "Floor")))
    add(prop, "floorsInBuilding", whole(fact(item, "Number of floors")))
    add(prop, "builtYear", whole(fact(item, "Year built")))

    grouped: dict[str, list[str]] = {}
    for label in features:
        kind, value = FEATURE_MAP.get(label, ("Features", label))
        grouped.setdefault(kind, [])
        if value not in grouped[kind]:
            grouped[kind].append(value)
    if not grouped:
        for kind, value in TEXT_FEATURES.get(str(item.get("slug") or ""), []):
            grouped.setdefault(kind, [])
            if value not in grouped[kind]:
                grouped[kind].append(value)
    feature_root = ET.SubElement(prop, "propertyFeatures")
    for name, values in grouped.items():
        block = ET.SubElement(feature_root, "featureType")
        add(block, "name", name)
        for value in values:
            add(block, "value", value)

    descriptions = ET.SubElement(prop, "descriptions")
    add(descriptions, "en", description_text(item))
    add(descriptions, "es", spanish_text(item, spanish or {}))

    images = ET.SubElement(prop, "propertyImages")
    for url in image_urls(item):
        image = ET.SubElement(images, "image")
        add(image, "url", url)
    return prop


def build_tree(sales: list[dict], spanish: dict[str, str] | None = None) -> ET.ElementTree:
    root = ET.Element("properties")
    feed = ET.SubElement(root, "feed")
    add(feed, "version", "1.5")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    add(feed, "generated", generated)
    add(feed, "source", "amaranthus-web")
    for item in sales:
        root.append(property_element(item, spanish))
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def missing_report(sales: list[dict], spanish: dict[str, str] | None = None) -> list[str]:
    def lacks(check) -> list[str]:
        return [str(item.get("slug")) for item in sales if check(item)]

    rows = [
        (
            "address1",
            lacks(lambda item: not street_line(item)),
            "la zona es solo Ibiza o está vacía, y ni la descripción ni el título nombran un lugar",
        ),
        ("address2", lacks(lambda item: True), "el nodo es obligatorio en el XML y no hay segunda línea"),
        ("postCode", lacks(lambda item: True), "no hay código postal"),
        ("cadastralRef", lacks(lambda item: True), "no hay referencia catastral"),
        (
            "descriptions/es",
            lacks(lambda item: not spanish_text(item, spanish or {})),
            "no hay traducción en descriptions_es.json",
        ),
        ("descriptions/en", lacks(lambda item: not description_text(item)), "la ficha no trae texto"),
        ("built or plot", lacks(lambda item: not (
            fact(item, "Net living area") or fact(item, "Usable area") or fact(item, "Plot area")
        )), "sin superficie"),
        ("resales_ref", lacks(lambda item: not item.get("resales_ref")), "la referencia de Resales está vacía"),
    ]
    lines = [
        f"Ventas en el XML: {len(sales)}",
        (
            f"- saleType: {DEFAULT_SALE_TYPE} en las {len(sales)}. "
            "Valor provisional por defecto. Hay que revisarlo ficha por ficha con el cliente."
        ),
        (
            f"- shared: {DEFAULT_SHARED} en las {len(sales)}. "
            "Provisional: Las Boas no está marcada como Compartida. "
            "Hay que confirmarlo ficha por ficha con el cliente."
        ),
        (
            "- commissionPct y commissionOwnPct: no van en el XML. "
            "Se dejan en el alta del feed. En Las Boas el panel muestra 4,52 % y un reparto del 50 %."
        ),
    ]
    for label, slugs, reason in rows:
        if len(slugs) == len(sales):
            lines.append(f"- {label}: falta en las {len(slugs)}. {reason}.")
        elif slugs:
            lines.append(f"- {label}: falta en {len(slugs)} ({', '.join(slugs)}). {reason}.")
    # Commercial and plot omissions are not missing data. Schema 1.5
    # types both fields as Numeric and documents no N/A token, so the
    # empty text passed to add() is the not-applicable mark.
    not_applicable = lacks(counts_not_applicable)
    pending_beds = lacks(lambda item: not counts_not_applicable(item) and not bedrooms(item))
    pending_baths = lacks(lambda item: not counts_not_applicable(item) and not bathrooms(item))
    if not_applicable:
        lines.append(
            f"- bedrooms y bathrooms: no aplicables en {len(not_applicable)} "
            f"({', '.join(not_applicable)}). Comercial o parcela. "
            "El esquema 1.5 los define como Numeric y no documenta N/A. "
            "Se omiten los dos nodos aunque el catálogo traiga un número. "
            "No se escribe 0 ni N/A."
        )
    if pending_beds:
        lines.append(
            f"- bedrooms: pendiente en {len(pending_beds)} "
            f"({', '.join(pending_beds)}). "
            "Vivienda sin un solo número de dormitorios. "
            "Rooms no se copia y un rango no se convierte en un número."
        )
    if pending_baths:
        lines.append(
            f"- bathrooms: pendiente en {len(pending_baths)} "
            f"({', '.join(pending_baths)}). "
            "Vivienda sin un solo número de baños."
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Resales import XML from the website catalog.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--spanish", type=Path, default=DEFAULT_SPANISH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    sales = load_sales(args.catalog)
    spanish = load_spanish(args.spanish)
    tree = build_tree(sales, spanish)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.out, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {args.out} ({len(sales)} ventas)")
    print("\n".join(missing_report(sales, spanish)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
