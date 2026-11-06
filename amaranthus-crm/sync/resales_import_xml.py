#!/usr/bin/env python3
"""Build a Resales-Online import XML (v1.5) from the website catalog.

Reads site/data.json, keeps sales (operation Venta), and writes
site/resales-import.xml. That file is the feed for the automated import:
only the client's own sales, never the Balearics search dump. Resales
collects it from a URL once a day. This script does not call Resales and
does not invent cadastral, Spanish text, commission, or image size.

Listings with no street get address1 "Marina Botafoc". That value is
provisional until the client supplies a real address.

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

# The public website has no street field. Use this until the client
# provides a real address for each listing.
DEFAULT_STREET = "Marina Botafoc"

# Website type -> (Resales type, Resales subtype). Subtypes are the closest
# Appendix 1 labels. The catalog does not store a Resales subtype.
TYPE_MAP = {
    "Apartment": ("Apartment", "Middle Floor"),
    "Penthouse": ("Apartment", "Penthouse"),
    "Villa": ("Villa", "Detached"),
    "Building land": ("Plot", "Land"),
    "Hotel": ("Commercial", "Hotel"),
    "Restaurant": ("Commercial", "Restaurant"),
    "Commercial space": ("Commercial", "Commercial Premises"),
}

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


def load_sales(path: Path) -> list[dict]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise SystemExit(f"El catálogo no es una lista: {path}")
    return [item for item in catalog if item.get("operation") == "Venta"]


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


def image_urls(item: dict) -> list[str]:
    urls: list[str] = []
    for url in [item.get("image"), *(item.get("gallery") or [])]:
        text = str(url or "").strip()
        if text and text not in urls:
            urls.append(text)
    return urls


def bedrooms(item: dict) -> str:
    return whole(fact(item, "Bedrooms") or fact(item, "Rooms"))


def real_street(item: dict) -> str:
    for key in ("address1", "street", "address"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def street_line(item: dict) -> str:
    return real_street(item) or DEFAULT_STREET


def property_element(item: dict) -> ET.Element:
    website_type = str(item.get("type") or "")
    resales_type, subtype = TYPE_MAP.get(website_type, ("Apartment", "Middle Floor"))
    if "Ground floor" in (item.get("features") or []) and resales_type == "Apartment":
        subtype = "Ground Floor"
    features = item.get("features") or []
    slug = str(item.get("slug") or "").strip()
    zone = str(item.get("zone") or "").strip()
    prop = ET.Element("property")
    add(prop, "referenceId", slug)
    add(prop, "type", resales_type)
    add(prop, "subType", subtype)
    add(prop, "currency", str(item.get("currency") or "EUR"))
    add(prop, "sizeType", "1")
    add(prop, "status", "Off Market" if item.get("off_market") else "Available")
    if "New build" in features:
        add(prop, "newBuild", "1")

    address = ET.SubElement(prop, "address")
    add(address, "address1", street_line(item))
    add(address, "town", zone)
    add(address, "province", "Islas Baleares")
    add(address, "country", "Spain")

    sale = ET.SubElement(prop, "saleDetails")
    add(sale, "saleReferenceId", slug)
    add(sale, "price", whole(str(item.get("price") or "")))

    sizes = ET.SubElement(prop, "propertySizes")
    add(sizes, "built", whole(fact(item, "Net living area") or fact(item, "Usable area")))
    add(sizes, "terrace", whole(fact(item, "Terrace area") or fact(item, "Balcony area")))
    add(sizes, "plot", whole(fact(item, "Plot area")))
    add(sizes, "garden", whole(fact(item, "Garden area")))

    add(prop, "bedrooms", bedrooms(item))
    add(prop, "bathrooms", whole(fact(item, "Bathrooms")))
    add(prop, "floor", whole(fact(item, "Floor")))
    add(prop, "levels", "1")
    floors = whole(fact(item, "Number of floors"))
    add(prop, "floorsInBuilding", floors or "1")
    add(prop, "builtYear", whole(fact(item, "Year built")))

    grouped: dict[str, list[str]] = {}
    for label in features:
        kind, value = FEATURE_MAP.get(label, ("Features", label))
        grouped.setdefault(kind, [])
        if value not in grouped[kind]:
            grouped[kind].append(value)
    feature_root = ET.SubElement(prop, "propertyFeatures")
    if not grouped:
        grouped["Features"] = ["Not specified"]
    for name, values in grouped.items():
        block = ET.SubElement(feature_root, "featureType")
        add(block, "name", name)
        for value in values:
            add(block, "value", value)

    descriptions = ET.SubElement(prop, "descriptions")
    add(descriptions, "en", description_text(item))

    images = ET.SubElement(prop, "propertyImages")
    for url in image_urls(item):
        image = ET.SubElement(images, "image")
        add(image, "url", url)
    return prop


def build_tree(sales: list[dict]) -> ET.ElementTree:
    root = ET.Element("properties")
    feed = ET.SubElement(root, "feed")
    add(feed, "version", "1.5")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    add(feed, "generated", generated)
    add(feed, "source", "amaranthus-web")
    for item in sales:
        root.append(property_element(item))
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def missing_report(sales: list[dict]) -> list[str]:
    def lacks(check) -> list[str]:
        return [str(item.get("slug")) for item in sales if check(item)]

    rows = [
        (
            "address1 real (calle)",
            lacks(lambda item: not real_street(item)),
            f"sin calle en el JSON; el XML usa el valor provisional {DEFAULT_STREET}",
        ),
        ("address2", lacks(lambda item: True), "el nodo es obligatorio en el XML y no hay segunda línea"),
        ("postCode", lacks(lambda item: True), "no hay código postal"),
        ("cadastralRef", lacks(lambda item: True), "no hay referencia catastral"),
        ("descriptions/es", lacks(lambda item: True), "el texto del catálogo está en inglés"),
        ("saleType", lacks(lambda item: True), "no dice Freehold o Leasehold"),
        ("shared", lacks(lambda item: True), "no dice si se comparte con otras agencias"),
        ("commissionPct", lacks(lambda item: True), "no hay comisión"),
        ("commissionOwnPct", lacks(lambda item: True), "no hay porcentaje del listing agent"),
        ("image pixel size", lacks(lambda item: True), "las URLs no dicen si el lado largo mide 800 px"),
        ("bedrooms", lacks(lambda item: not bedrooms(item)), "ni Rooms ni Bedrooms"),
        ("bathrooms", lacks(lambda item: not fact(item, "Bathrooms")), "sin Bathrooms"),
        ("built or plot", lacks(lambda item: not (
            fact(item, "Net living area") or fact(item, "Usable area") or fact(item, "Plot area")
        )), "sin superficie"),
        ("resales_ref", lacks(lambda item: not item.get("resales_ref")), "la referencia de Resales está vacía"),
    ]
    lines = [f"Ventas en el XML: {len(sales)}"]
    for label, slugs, reason in rows:
        if len(slugs) == len(sales):
            lines.append(f"- {label}: falta en las {len(slugs)}. {reason}.")
        elif slugs:
            lines.append(f"- {label}: falta en {len(slugs)} ({', '.join(slugs)}). {reason}.")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Resales import XML from the website catalog.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    sales = load_sales(args.catalog)
    tree = build_tree(sales)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.out, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {args.out} ({len(sales)} ventas)")
    print("\n".join(missing_report(sales)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
