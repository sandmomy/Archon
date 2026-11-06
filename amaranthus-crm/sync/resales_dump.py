#!/usr/bin/env python3
"""One-shot dump of the Resales Online sale catalog into site/resales.json.

The API key is read from RESALES_API_KEY and is never written to disk or to
the repo. The call only succeeds from the IP registered on that key.

Does not touch the website scraper or site/data.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT = "https://webapi.resales-online.com/V6/SearchProperties"
P1 = "1175569"
FILTER_ID = "1"
PAGE_SIZE = 50
TIMEOUT = 40
PAUSE_SEC = 1.2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "resales.json"


def fetch_page(api_key: str, page: int, query_id: str | None) -> tuple[int, dict]:
    params = {
        "p_agency_filterid": FILTER_ID,
        "p1": P1,
        "p2": api_key,
        "P_PageSize": str(PAGE_SIZE),
        "P_PageNo": str(page),
    }
    if query_id:
        params["P_QueryId"] = query_id
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"transaction": {"status": "error", "errordescription": raw[:500]}}
        return exc.code, body


def public_error(body: dict) -> dict:
    tx = body.get("transaction") if isinstance(body, dict) else {}
    if not isinstance(tx, dict):
        tx = {}
    parsed = tx.get("parsedparameters")
    if isinstance(parsed, dict) and "P2" in parsed:
        parsed = {**parsed, "P2": "redacted"}
    return {
        "status": tx.get("status"),
        "errordescription": tx.get("errordescription"),
        "incomingIp": tx.get("incomingIp"),
        "parsedparameters": parsed,
    }


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def slugify(reference: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", reference.lower()).strip("-")
    return "r-" + (text or "sin-ref")


def money(value) -> int | None:
    if value is None or value == "":
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def to_card(prop: dict, used: set[str]) -> dict:
    ref = str(prop.get("Reference") or prop.get("AgencyRef") or "").strip()
    slug = slugify(ref or str(prop.get("AgencyRef") or "propiedad"))
    n = 2
    base = slug
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)

    ptype = prop.get("PropertyType") if isinstance(prop.get("PropertyType"), dict) else {}
    kind = str(ptype.get("Type") or ptype.get("NameType") or "Property")
    location = str(prop.get("Location") or "").strip()
    province = str(prop.get("Province") or "").strip()
    area = str(prop.get("Area") or "").strip()
    zone = location or area or province or "Ibiza"
    blob = " ".join([location, area, province]).lower()
    if "formentera" in blob:
        island = "Formentera"
    elif "ibiza" in blob or "eivissa" in blob:
        island = "Ibiza"
    else:
        island = province or "Ibiza"

    price = money(prop.get("Price"))
    currency = str(prop.get("Currency") or "EUR")
    price_display = f"{price} {currency}" if price else "Precio a consultar"
    built = prop.get("Built")
    terrace = prop.get("Terrace")
    plot = prop.get("GardenPlot")
    facts: dict[str, str] = {}
    if prop.get("Bedrooms") not in (None, ""):
        facts["Bedrooms"] = str(prop.get("Bedrooms"))
    if prop.get("Bathrooms") not in (None, ""):
        facts["Bathrooms"] = str(prop.get("Bathrooms"))
    if built not in (None, "", 0, "0"):
        facts["Net living area"] = f"{built} m²"
    if terrace not in (None, "", 0, "0"):
        facts["Terrace area"] = f"{terrace} m²"
    if plot not in (None, "", 0, "0"):
        facts["Plot area"] = f"{plot} m²"
    if price:
        facts["Sale price"] = f"{currency} {price}"

    features = []
    if prop.get("Pool") not in (None, 0, "0", ""):
        features.append("Swimming pool")
    if prop.get("Parking") not in (None, 0, "0", ""):
        features.append("Parking")
    if prop.get("Garden") not in (None, 0, "0", ""):
        features.append("Garden")

    image = str(prop.get("MainImage") or "").strip()
    description = [line.strip() for line in re.split(r"\r\n|\n", str(prop.get("Description") or "")) if line.strip()]
    title_place = zone[:1].upper() + zone[1:] if zone else "Propiedad"
    title = f"{title_place} - {kind}"
    if ref:
        title = f"{title} ({ref})"

    return {
        "slug": slug,
        "nestermind_id": None,
        "resales_ref": ref or None,
        "url": "",
        "title": title,
        "zone": title_place,
        "island": island,
        "type": kind,
        "operation": "Venta",
        "off_market": False,
        "listings": ["sale", "resales"],
        "price_display": price_display,
        "currency": currency,
        "price": price or 0,
        "period": None,
        "photos": 1 if image else 0,
        "image": image,
        "facts": facts,
        "features": features,
        "map": False,
        "desc_flags": {
            "terrace": bool(facts.get("Terrace area")),
            "licence": False,
            "views": False,
            "orientation": False,
            "video": False,
            "floorplan": False,
            "energy": bool(prop.get("EnergyRated")),
            "pool": "Swimming pool" in features,
        },
        "description": description,
        "gallery": [image] if image else [],
    }


def main() -> int:
    api_key = os.environ.get("RESALES_API_KEY", "").strip()
    if not api_key:
        print("Falta RESALES_API_KEY", file=sys.stderr)
        return 1

    page = 1
    query_id = None
    total = None
    raw_props: list[dict] = []

    while True:
        code, body = fetch_page(api_key, page, query_id)
        tx = body.get("transaction") if isinstance(body, dict) else {}
        ok = code == 200 and isinstance(tx, dict) and tx.get("status") == "success"
        if page == 1 and not ok:
            print(f"HTTP {code}")
            print(json.dumps(public_error(body), ensure_ascii=False, indent=2))
            print("No se escribe resales.json")
            return 1
        if not ok:
            print(f"HTTP {code} en la página {page}")
            print(json.dumps(public_error(body), ensure_ascii=False, indent=2))
            print("No se escribe resales.json")
            return 1

        info = body.get("QueryInfo") if isinstance(body.get("QueryInfo"), dict) else {}
        if page == 1:
            total = int(info.get("PropertyCount") or 0)
            query_id = info.get("QueryId")
            print(f"PropertyCount: {total}")
        batch = [p for p in as_list(body.get("Property")) if isinstance(p, dict)]
        raw_props.extend(batch)
        if total is not None and (len(raw_props) >= total or not batch):
            break
        page += 1
        time.sleep(PAUSE_SEC)

    used: set[str] = set()
    cards = [to_card(p, used) for p in raw_props]
    OUT.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(cards)} fichas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
