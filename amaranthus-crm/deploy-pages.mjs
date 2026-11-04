#!/usr/bin/env node
/**
 * Deploy amaranthus-crm/site to Cloudflare Pages (direct upload).
 * Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
 *
 *   CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... node amaranthus-crm/deploy-pages.mjs
 */
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, posix } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const SITE = join(__dirname, "site");
const PROJECT = process.env.PAGES_PROJECT || "amaranthus-app";
const ACCOUNT = process.env.CLOUDFLARE_ACCOUNT_ID;
const TOKEN = process.env.CLOUDFLARE_API_TOKEN;

if (!ACCOUNT || !TOKEN) {
  console.error("Missing CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID");
  process.exit(1);
}

function walk(dir, base = dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, base, out);
    else out.push(p);
  }
  return out;
}

function contentType(path) {
  if (path.endsWith(".html")) return "text/html; charset=utf-8";
  if (path.endsWith(".json")) return "application/json";
  if (path.endsWith(".webp")) return "image/webp";
  if (path.endsWith(".png")) return "image/png";
  if (path.endsWith(".js")) return "application/javascript";
  if (path.endsWith(".css")) return "text/css";
  return "application/octet-stream";
}

const files = walk(SITE);
const manifest = {};
const blobs = {};
for (const abs of files) {
  const rel = posix.join(...relative(SITE, abs).split("\\"));
  const buf = readFileSync(abs);
  const hash =
    createHash("sha256").update(buf).digest("hex").slice(0, 32);
  manifest[`/${rel}`] = hash;
  blobs[hash] = { buf, path: rel, type: contentType(rel) };
}

const api = async (path, init = {}) => {
  const res = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`${res.status} ${path}: ${text.slice(0, 200)}`);
  }
  if (!res.ok || json.success === false) {
    throw new Error(`${res.status} ${path}: ${JSON.stringify(json.errors || json)}`);
  }
  return json;
};

const tokenRes = await api(
  `/accounts/${ACCOUNT}/pages/projects/${PROJECT}/upload-token`,
);
const jwt = tokenRes.result.jwt;

const missingRes = await fetch("https://api.cloudflare.com/client/v4/pages/assets/check-missing", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${jwt}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ hashes: Object.keys(blobs) }),
});
const missingJson = await missingRes.json();
if (!missingRes.ok) throw new Error(JSON.stringify(missingJson));
const missing = new Set(missingJson.result || []);

for (const hash of missing) {
  const { buf, type } = blobs[hash];
  const b64 = buf.toString("base64");
  const up = await fetch("https://api.cloudflare.com/client/v4/pages/assets/upload", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jwt}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify([{ key: hash, value: b64, metadata: { contentType: type } }]),
  });
  const upJson = await up.json();
  if (!up.ok) throw new Error(`upload ${hash}: ${JSON.stringify(upJson)}`);
  console.log("uploaded", hash);
}

await fetch("https://api.cloudflare.com/client/v4/pages/assets/upsert-hashes", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${jwt}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ hashes: Object.keys(blobs) }),
});

const form = new FormData();
form.append(
  "manifest",
  JSON.stringify(manifest),
);
form.append("branch", "main");

const dep = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/pages/projects/${PROJECT}/deployments`,
  {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}` },
    body: form,
  },
);
const depJson = await dep.json();
if (!dep.ok || !depJson.success) {
  throw new Error(`deploy failed: ${JSON.stringify(depJson.errors || depJson)}`);
}
console.log("Deployed:", depJson.result.url);
