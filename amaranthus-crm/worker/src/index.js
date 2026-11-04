/**
 * Amaranthus catalog sync Worker
 * Scrapes https://www.amaranthus-realestate.com (public HTML only).
 * No Nestermind API.
 *
 * Bindings: CATALOG (KV)
 * Routes:
 *   GET  /data.json     → cached catalog
 *   GET  /sync-meta.json
 *   POST /sync          → run sync now (optional header x-sync-key)
 * Cron: scheduled()
 */

const BASE = "https://www.amaranthus-realestate.com";
const INDEX_PATHS = {
  all: "/real-estate",
  sale: "/real-estate/sale",
  rent: "/real-estate/rent",
  holiday: "/real-estate/holiday",
  "off-market": "/real-estate/off-market",
  formentera: "/real-estate/formentera",
};
const SKIP = new Set(Object.keys(INDEX_PATHS));
const FACT_KEYS = new Set([
  "Bedrooms", "Rooms", "Bathrooms", "Floor", "Number of floors",
  "Number of residential units", "Net living area", "Usable area", "Plot area",
  "Garden area", "Terrace area", "Balcony area", "Year built", "Sale price",
  "Gross rent", "Security deposit", "Covered parking space",
  "Outdoor parking space", "Available from",
]);
const UA = "AmaranthusCatalogSync/1.0 (+cloudflare-worker; public pages only)";

function clean(text) {
  return String(text || "")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&#x27;|&apos;|’|‘/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "text/html" },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.text();
}

function parseIndex(html) {
  const meta = {};
  const re =
    /<a class="group flex flex-col gap-4" href="\/real-estate\/([a-z0-9\-]+)">([\s\S]*?)<\/a>/g;
  let m;
  while ((m = re.exec(html))) {
    const slug = m[1];
    const block = m[2];
    if (SKIP.has(slug)) continue;
    let type = "Property";
    let zone = "Ibiza";
    const tz = block.match(/uppercase"[^>]*>([\s\S]*?)<\/p>/);
    if (tz) {
      const raw = clean(tz[1]);
      if (raw.includes("|")) {
        const [t, z] = raw.split("|").map((x) => x.trim());
        type = t || type;
        zone = z || zone;
      } else if (raw) type = raw;
    }
    const title = block.match(/<h3[^>]*>([\s\S]*?)<\/h3>/);
    meta[slug] = {
      type,
      zone,
      title_card: title ? clean(title[1]) : slug,
    };
  }
  return meta;
}

async function collectListings() {
  const byFilter = {};
  const merged = {};
  for (const [name, path] of Object.entries(INDEX_PATHS)) {
    const html = await fetchText(BASE + path);
    const page = parseIndex(html);
    byFilter[name] = new Set(Object.keys(page));
    for (const [slug, info] of Object.entries(page)) {
      if (!merged[slug]) merged[slug] = info;
    }
  }
  return { merged, byFilter };
}

function parseFacts(html) {
  const facts = {};
  const re = /<dt[^>]*>(.*?)<\/dt>\s*<dd[^>]*>(.*?)<\/dd>/gi;
  let m;
  while ((m = re.exec(html))) {
    const key = clean(m[1]);
    const val = clean(m[2]);
    if (FACT_KEYS.has(key) && val) facts[key] = val;
  }
  return facts;
}

function parseGallery(html) {
  const out = [];
  const seen = new Set();
  const decoded = html.replace(/&amp;/g, "&");
  const re =
    /https:\/\/app\.nestermind\.com\/files\/attachment\/public\/[0-9a-f\-]+\.(?:JPG|JPEG|PNG|jpg|jpeg|png|webp)\?workspaceId=[0-9a-f\-]+/g;
  let m;
  while ((m = re.exec(decoded))) {
    if (!seen.has(m[0])) {
      seen.add(m[0]);
      out.push(m[0]);
    }
  }
  return out;
}

function parseFeatures(html) {
  const sec = html.match(
    /<h2[^>]*>\s*Features\s*<\/h2>\s*<ul[^>]*>([\s\S]*?)<\/ul>/i,
  );
  if (!sec) return [];
  return [...sec[1].matchAll(/<li[^>]*>(.*?)<\/li>/g)]
    .map((x) => clean(x[1]))
    .filter(Boolean);
}

function parseDescription(html) {
  const block = html.match(
    /<div class="flex max-w-\[68ch\] flex-col gap-4[^"]*">([\s\S]*?)<\/div>\s*<section class="flex flex-col gap-5">/,
  );
  if (!block) return [];
  return [...block[1].matchAll(/<p[^>]*>([\s\S]*?)<\/p>/g)]
    .map((x) => clean(x[1]))
    .filter(Boolean);
}

function parseTitleZonePrice(html) {
  let zone = "Ibiza";
  const zm = html.match(
    /<p class="flex items-center gap-2 text-\[15px\] text-mute">[\s\S]*?<\/svg>([^<]+)<\/p>/,
  );
  if (zm) zone = clean(zm[1]) || zone;
  let title = "";
  const tm = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/);
  if (tm) title = clean(tm[1]);
  let amount = null;
  let currency = null;
  const pm = html.match(
    /<h1[^>]*>[\s\S]*?<\/h1>\s*<p class="tabular[^"]*">\s*([^<]+)\s*<span[^>]*>\s*([^<]+)/,
  );
  if (pm) {
    amount = clean(pm[1]);
    currency = clean(pm[2]);
  }
  return { title, zone, amount, currency };
}

function parsePrice(amount, currency, facts, filters) {
  let operation = "Venta";
  let period = null;
  let cur = currency || "EUR";
  const rent = facts["Gross rent"];
  const sale = facts["Sale price"];
  if (filters.includes("holiday")) operation = "Alquiler vacacional";
  else if (filters.includes("rent") && !filters.includes("sale"))
    operation = "Alquiler";
  else if (rent && !sale) operation = "Alquiler";

  let raw = null;
  if (operation.startsWith("Alquiler") && rent) raw = rent;
  else if (sale) raw = sale;
  else if (amount) raw = `${cur} ${amount}`;

  let price_int = null;
  let price_display = null;
  if (raw) {
    const m = raw
      .replace(/’/g, "'")
      .match(/(EUR|CHF)\s*([\d][\d\s']*)(?:\s*\/\s*(month|week|year))?/i);
    if (m) {
      cur = m[1].toUpperCase();
      const pretty = m[2].replace(/\s+/g, "").replace(/’/g, "'");
      price_display = `${pretty} ${cur}`;
      price_int = parseInt(pretty.replace(/'/g, ""), 10) || null;
      if (m[3]) period = `/ ${m[3]}`;
    }
  }
  if (operation === "Alquiler vacacional" && !period) period = "/ week";
  if (operation === "Alquiler" && !period) period = "/ month";
  return { price_display, currency: cur, price: price_int, period, operation };
}

function descFlags(description, features, facts) {
  const blob = [...description, ...features, ...Object.values(facts)]
    .join(" ")
    .toLowerCase();
  return {
    terrace: /terrace|balcony|terraza/.test(blob),
    licence: /tourist (rental )?licen[cs]e|licen[cs]e/.test(blob),
    views: /\bviews?\b|sea view|panoramic/.test(blob),
    orientation: /orient|south-facing|sunny location/.test(blob),
    video: /\bvideo\b|youtube|vimeo/.test(blob),
    floorplan: /floor\s*plan|plano/.test(blob),
    energy: /energy\s*(certificate|rating)|certificado energ/.test(blob),
    pool: /pool|piscina|swimming/.test(blob),
  };
}

async function parseProperty(slug, card, filters) {
  const url = `${BASE}/real-estate/${slug}`;
  const html = await fetchText(url);
  const { title, zone, amount, currency } = parseTitleZonePrice(html);
  const facts = parseFacts(html);
  const gallery = parseGallery(html);
  const features = parseFeatures(html);
  const description = parseDescription(html);
  const price = parsePrice(amount, currency, facts, filters);
  const listings = ["sale", "rent", "holiday", "off-market", "formentera"].filter(
    (f) => filters.includes(f),
  );
  const finalTitle = title || card.title_card || slug;
  const off_market =
    filters.includes("off-market") ||
    finalTitle.toUpperCase().startsWith("OFF MARKET");
  const z = zone || card.zone || "Ibiza";
  return {
    slug,
    nestermind_id: null,
    resales_ref: null,
    url,
    title: finalTitle,
    zone: z,
    island:
      filters.includes("formentera") || /formentera/i.test(z)
        ? "Formentera"
        : "Ibiza",
    type: card.type || "Property",
    operation: price.operation,
    off_market,
    listings: listings.length
      ? listings
      : price.operation === "Venta"
        ? ["sale"]
        : ["rent"],
    price_display: price.price_display,
    currency: price.currency,
    price: price.price,
    period: price.period,
    photos: gallery.length,
    image: gallery[0] || null,
    facts,
    features,
    map: false,
    desc_flags: descFlags(description, features, facts),
    description,
    gallery,
  };
}

async function runSync(env) {
  const { merged, byFilter } = await collectListings();
  const slugs = Object.keys(merged).sort();
  const props = [];
  const errors = [];
  // Sequential batches to stay within CPU/subrequest limits
  const batchSize = 4;
  for (let i = 0; i < slugs.length; i += batchSize) {
    const batch = slugs.slice(i, i + batchSize);
    const part = await Promise.all(
      batch.map(async (slug) => {
        const filters = Object.entries(byFilter)
          .filter(([k, set]) => k !== "all" && set.has(slug))
          .map(([k]) => k);
        try {
          return await parseProperty(slug, merged[slug], filters);
        } catch (e) {
          errors.push(`${slug}: ${e.message || e}`);
          return null;
        }
      }),
    );
    for (const p of part) if (p) props.push(p);
  }
  props.sort((a, b) => a.slug.localeCompare(b.slug));
  const meta = {
    synced_at: new Date().toISOString(),
    source: BASE + "/real-estate",
    count: props.length,
    slugs: props.map((p) => p.slug),
    errors,
  };
  await env.CATALOG.put("data.json", JSON.stringify(props));
  await env.CATALOG.put("sync-meta.json", JSON.stringify(meta));
  return meta;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=60",
      "access-control-allow-origin": "*",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET,POST,OPTIONS",
          "access-control-allow-headers": "*",
        },
      });
    }
    if (url.pathname === "/data.json" || url.pathname === "/") {
      const raw = await env.CATALOG.get("data.json");
      if (!raw) return json({ error: "catalog not synced yet" }, 503);
      return new Response(raw, {
        headers: {
          "content-type": "application/json; charset=utf-8",
          "cache-control": "public, max-age=60",
          "access-control-allow-origin": "*",
        },
      });
    }
    if (url.pathname === "/sync-meta.json") {
      const raw = await env.CATALOG.get("sync-meta.json");
      return new Response(raw || "{}", {
        headers: {
          "content-type": "application/json; charset=utf-8",
          "access-control-allow-origin": "*",
        },
      });
    }
    if (url.pathname === "/sync" && request.method === "POST") {
      const key = env.SYNC_KEY;
      if (key) {
        const got = request.headers.get("x-sync-key");
        if (got !== key) return json({ error: "unauthorized" }, 401);
      }
      const meta = await runSync(env);
      return json({ ok: true, ...meta });
    }
    return json({ error: "not found" }, 404);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runSync(env));
  },
};
