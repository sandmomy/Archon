#!/usr/bin/env python3
"""Sync Amaranthus CRM catalog from the official public website.

Source of truth: https://www.amaranthus-realestate.com/real-estate
No Nestermind API — only public HTML pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

BASE = "https://www.amaranthus-realestate.com"
INDEX_PATHS = {
    "all": "/real-estate",
    "sale": "/real-estate/sale",
    "rent": "/real-estate/rent",
    "holiday": "/real-estate/holiday",
    "off-market": "/real-estate/off-market",
    "formentera": "/real-estate/formentera",
}
SKIP_SLUGS = set(INDEX_PATHS) | {"real-estate"}
UA = "AmaranthusCatalogSync/1.0 (+internal CRM sync; public pages only)"
# Polite delay between HTTP requests to avoid hammering the official site.
REQUEST_PAUSE_SEC = (1.0, 2.0)
FACT_KEYS = {
    "Bedrooms",
    "Rooms",
    "Bathrooms",
    "Floor",
    "Number of floors",
    "Number of residential units",
    "Net living area",
    "Usable area",
    "Plot area",
    "Garden area",
    "Terrace area",
    "Balcony area",
    "Year built",
    "Sale price",
    "Gross rent",
    "Security deposit",
    "Covered parking space",
    "Outdoor parking space",
    "Available from",
}


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = text.replace("\xa0", " ").replace("’", "'").replace("‘", "'")
    text = text.replace("&#x27;", "'").replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


def polite_pause() -> None:
    time.sleep(random.uniform(*REQUEST_PAUSE_SEC))


def fetch(url: str, retries: int = 3) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            polite_pause()
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.8 * (i + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def fetch_bytes(url: str) -> bytes:
    polite_pause()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def parse_index(html: str) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for m in re.finditer(
        r'<a class="group flex flex-col gap-4" href="/real-estate/([a-z0-9\-]+)">([\s\S]*?)</a>',
        html,
    ):
        slug, block = m.group(1), m.group(2)
        if slug in SKIP_SLUGS:
            continue
        typ = zone = None
        typ_zone = re.search(r'uppercase"[^>]*>([\s\S]*?)</p>', block)
        if typ_zone:
            raw = clean_html(typ_zone.group(1))
            if "|" in raw:
                typ, zone = [x.strip() for x in raw.split("|", 1)]
            else:
                typ = raw
        title = re.search(r"<h3[^>]*>([\s\S]*?)</h3>", block)
        price = re.search(r'text-\[17px\]"[^>]*>([\s\S]*?)</p>', block)
        img = re.search(
            r"https://app\.nestermind\.com/files/attachment/public/[^\"'&\s]+",
            urllib.parse.unquote(block),
        )
        meta[slug] = {
            "type": typ or "Property",
            "zone": zone or "Ibiza",
            "title_card": clean_html(title.group(1)) if title else slug,
            "price_card": clean_html(price.group(1)) if price else None,
            "image": img.group(0) if img else None,
        }
    return meta


def collect_listings() -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    by_filter: dict[str, set[str]] = {}
    merged: dict[str, dict[str, Any]] = {}
    for name, path in INDEX_PATHS.items():
        html = fetch(BASE + path)
        page_meta = parse_index(html)
        by_filter[name] = set(page_meta)
        for slug, info in page_meta.items():
            if slug not in merged:
                merged[slug] = info
    return merged, by_filter


def parse_facts(html: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    for a, b in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html, re.S | re.I):
        key, val = clean_html(a), clean_html(b)
        if key in FACT_KEYS and val:
            facts[key] = val
    return facts


def parse_gallery(html: str) -> list[str]:
    # Prefer the Gallery images array from Next flight data when present.
    m = re.search(r'"images":\[(.*?)\]', html)
    if m:
        urls = re.findall(
            r"https://app\.nestermind\.com/files/attachment/public/[^\\\"\s]+",
            m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore"),
        )
        # Keep order, unique
        out: list[str] = []
        seen: set[str] = set()
        for u in urls:
            u = u.split("\\")[0]
            if u not in seen:
                seen.add(u)
                out.append(u)
        if out:
            return out
    urls = re.findall(
        r"https://app\.nestermind\.com/files/attachment/public/[0-9a-f\-]+\.(?:JPG|JPEG|PNG|jpg|jpeg|png|webp)\?workspaceId=[0-9a-f\-]+",
        urllib.parse.unquote(html),
    )
    out = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def parse_features(html: str) -> list[str]:
    m = re.search(
        r"<h2[^>]*>\s*Features\s*</h2>\s*<ul[^>]*>([\s\S]*?)</ul>",
        html,
        re.I,
    )
    if not m:
        return []
    return [clean_html(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S) if clean_html(x)]


def parse_description(html: str) -> list[str]:
    m = re.search(
        r'flex max-w-\[68ch\] flex-col gap-4[\s\S]*?</header>([\s\S]*?)<section class="flex flex-col gap-5">',
        html,
    )
    # Fallback: block with whitespace-pre-line paragraphs after facts
    block = None
    m2 = re.search(
        r'<div class="flex max-w-\[68ch\] flex-col gap-4[^"]*">([\s\S]*?)</div>\s*<section class="flex flex-col gap-5">',
        html,
    )
    if m2:
        block = m2.group(1)
    if not block:
        return []
    paras = []
    for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>", block):
        t = clean_html(p)
        if t:
            paras.append(t)
    # Drop the repeated h2 title if captured somehow
    return paras


def parse_title_zone_price(html: str) -> tuple[str, str, str | None, str | None]:
    zone = "Ibiza"
    zm = re.search(
        r'<p class="flex items-center gap-2 text-\[15px\] text-mute">[\s\S]*?</svg>([^<]+)</p>',
        html,
    )
    if zm:
        zone = clean_html(zm.group(1)) or zone
    title = ""
    tm = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html)
    if tm:
        title = clean_html(tm.group(1))
    amount = currency = None
    pm = re.search(
        r"<h1[^>]*>[\s\S]*?</h1>\s*<p class=\"tabular[^\"]*\">\s*([^<]+)\s*<span[^>]*>\s*([^<]+)",
        html,
    )
    if pm:
        amount, currency = clean_html(pm.group(1)), clean_html(pm.group(2))
    return title, zone, amount, currency


def normalize_title(title: str) -> str:
    t = title.strip()
    # Keep OFF MARKET prefix as in current CRM for those listings.
    return t


def parse_price(
    amount: str | None,
    currency: str | None,
    facts: dict[str, str],
    filters: list[str],
) -> tuple[str | None, str | None, int | None, str | None, str]:
    """Return price_display, currency, price_int, period, operation."""
    operation = "Venta"
    period = None
    cur = currency or "EUR"

    rent = facts.get("Gross rent")
    sale = facts.get("Sale price")
    if "holiday" in filters:
        operation = "Alquiler vacacional"
    elif "rent" in filters and "sale" not in filters:
        operation = "Alquiler"
    elif rent and not sale:
        operation = "Alquiler"

    raw = None
    if operation.startswith("Alquiler") and rent:
        raw = rent  # e.g. EUR 3'650 / month
    elif sale:
        raw = sale  # e.g. EUR 698'000
    elif amount:
        raw = f"{cur} {amount}"

    price_int = None
    price_display = None
    if raw:
        m = re.search(
            r"(EUR|CHF)\s*([\d][\d\s'’]*)(?:\s*/\s*(month|week|year))?",
            raw.replace("’", "'"),
            re.I,
        )
        if m:
            cur = m.group(1).upper()
            num = m.group(2).replace(" ", "").replace("'", "")
            try:
                price_int = int(num)
            except ValueError:
                price_int = None
            pretty = m.group(2).replace(" ", "").replace("’", "'")
            # Swiss-style grouping already present; ensure apostrophe form
            price_display = f"{pretty} {cur}"
            if m.group(3):
                period = f"/ {m.group(3)}"
        elif amount:
            pretty = amount.replace("’", "'").replace(" ", "")
            price_display = f"{pretty} {cur}"
            try:
                price_int = int(re.sub(r"[^\d]", "", pretty))
            except ValueError:
                price_int = None

    # Period from CRM convention for holiday/rent when missing
    if operation == "Alquiler vacacional" and not period:
        period = "/ week"
    elif operation == "Alquiler" and not period:
        period = "/ month"

    return price_display, cur, price_int, period, operation


def desc_flags(description: list[str], features: list[str], facts: dict[str, str]) -> dict[str, bool]:
    blob = " ".join(description + features + list(facts.values())).lower()
    return {
        "terrace": bool(re.search(r"terrace|balcony|terraza", blob)),
        "licence": bool(re.search(r"tourist (rental )?licen[cs]e|licen[cs]e", blob)),
        "views": bool(re.search(r"\bviews?\b|sea view|panoramic", blob)),
        "orientation": bool(re.search(r"orient|south-facing|sunny location", blob)),
        "video": bool(re.search(r"\bvideo\b|youtube|vimeo", blob)),
        "floorplan": bool(re.search(r"floor\s*plan|plano", blob)),
        "energy": bool(re.search(r"energy\s*(certificate|rating)|certificado energ", blob)),
        "pool": bool(re.search(r"pool|piscina|swimming", blob)),
    }


def island_from_zone(zone: str, filters: list[str]) -> str:
    z = (zone or "").lower()
    if "formentera" in filters or "formentera" in z:
        return "Formentera"
    return "Ibiza"


def parse_property(slug: str, card: dict[str, Any], filters: list[str]) -> dict[str, Any]:
    url = f"{BASE}/real-estate/{slug}"
    html = fetch(url)
    title, zone_page, amount, currency = parse_title_zone_price(html)
    facts = parse_facts(html)
    gallery = parse_gallery(html)
    features = parse_features(html)
    description = parse_description(html)
    title = normalize_title(title or card.get("title_card") or slug)
    zone = zone_page or card.get("zone") or "Ibiza"
    price_display, cur, price_int, period, operation = parse_price(amount, currency, facts, filters)
    image = (gallery[0] if gallery else None) or card.get("image")
    off_market = "off-market" in filters or title.upper().startswith("OFF MARKET")
    listings = [f for f in ("sale", "rent", "holiday", "off-market", "formentera") if f in filters]
    if not listings:
        listings = ["sale"] if operation == "Venta" else ["rent"]

    return {
        "slug": slug,
        "nestermind_id": None,
        "resales_ref": None,
        "url": url,
        "title": title,
        "zone": zone,
        "island": island_from_zone(zone, filters),
        "type": card.get("type") or "Property",
        "operation": operation,
        "off_market": off_market,
        "listings": listings,
        "price_display": price_display,
        "currency": cur,
        "price": price_int,
        "period": period,
        "photos": len(gallery),
        "image": image,
        "facts": facts,
        "features": features,
        "map": False,
        "desc_flags": desc_flags(description, features, facts),
        "description": description,
        "gallery": gallery,
    }


def make_thumb(image_url: str, dest: Path, size: int = 480) -> bool:
    try:
        from PIL import Image
        from io import BytesIO
    except ImportError:
        print("Pillow missing; skip thumbs", file=sys.stderr)
        return False
    try:
        data = fetch_bytes(image_url)
        im = Image.open(BytesIO(data)).convert("RGB")
        im.thumbnail((size, size))
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "WEBP", quality=72, method=4)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"thumb fail {dest.name}: {exc}", file=sys.stderr)
        return False


def reapply_resized_photos(site_dir: Path) -> None:
    """Point catalog URLs back at local photos enlarged to 800 px."""
    manifest_path = site_dir / "photos-backup" / "manifest.json"
    data_path = site_dir / "data.json"
    if not manifest_path.is_file() or not data_path.is_file():
        return
    mapping = {
        row["source"]: row["resized"]
        for row in json.loads(manifest_path.read_text(encoding="utf-8"))
        if row.get("source") and row.get("resized")
    }
    if not mapping:
        return
    catalog = json.loads(data_path.read_text(encoding="utf-8"))
    changed = False
    for item in catalog:
        image = item.get("image")
        if isinstance(image, str) and image in mapping:
            item["image"] = mapping[image]
            changed = True
        gallery = item.get("gallery")
        if isinstance(gallery, list):
            updated = [mapping[url] if isinstance(url, str) and url in mapping else url for url in gallery]
            if updated != gallery:
                item["gallery"] = updated
                changed = True
    if changed:
        data_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Restored {len(mapping)} enlarged photo URLs", flush=True)


def sync(site_dir: Path, refresh_thumbs: bool = False) -> dict[str, Any]:
    cards, by_filter = collect_listings()
    slugs = sorted(cards)
    print(f"Found {len(slugs)} properties on official site", flush=True)

    props: list[dict[str, Any]] = []
    errors: list[str] = []

    def one(slug: str) -> dict[str, Any] | None:
        filters = [k for k, v in by_filter.items() if slug in v and k != "all"]
        try:
            return parse_property(slug, cards[slug], filters)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{slug}: {exc}")
            return None

    # Sequential fetches so polite_pause between requests is respected.
    for slug in slugs:
        item = one(slug)
        if item:
            props.append(item)

    props.sort(key=lambda x: x["slug"])
    out = site_dir / "data.json"
    out.write_text(json.dumps(props, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(props)} items)", flush=True)

    th_dir = site_dir / "th"
    th_dir.mkdir(exist_ok=True)
    for p in props:
        dest = th_dir / f"{p['slug']}.webp"
        if dest.exists() and not refresh_thumbs:
            continue
        if p.get("image"):
            ok = make_thumb(p["image"], dest)
            print(f"thumb {p['slug']}: {'ok' if ok else 'fail'}", flush=True)

    reapply_resized_photos(site_dir)

    meta = {
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": BASE + "/real-estate",
        "count": len(props),
        "slugs": [p["slug"] for p in props],
        "errors": errors,
    }
    (site_dir / "sync-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("Errors:", *errors, sep="\n  ", file=sys.stderr)
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--site-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "site",
    )
    ap.add_argument("--refresh-thumbs", action="store_true")
    args = ap.parse_args()
    meta = sync(args.site_dir, refresh_thumbs=args.refresh_thumbs)
    print(json.dumps({"ok": True, **{k: meta[k] for k in ("synced_at", "count", "errors")}}, indent=2))
    return 1 if meta["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
