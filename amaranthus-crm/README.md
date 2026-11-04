# Amaranthus CRM — sync automático del catálogo

La CRM (`https://amaranthus-app.pages.dev`) se mantiene al día con la web oficial del cliente **sin API de Nestermind ni servicios externos de catálogo**.

Fuente: **https://www.amaranthus-realestate.com/real-estate** (HTML público).

## Cómo funciona

1. Un scraper propio (`sync/sync_catalog.py`) lee el listado y cada ficha de la web oficial.
2. Regenera `site/data.json` (+ miniaturas en `site/th/`).
3. GitHub Action lo ejecuta cada hora y hace commit si hay cambios.
4. La CRM carga el catálogo en este orden:
   - `raw.githubusercontent.com/.../main/.../data.json` (actualización automática al merge)
   - Worker Cloudflare opcional (`amaranthus-catalog-sync`)
   - `data.json` local embebido en Pages (fallback)

## Contenido

| Ruta | Uso |
|------|-----|
| `site/` | Frontend CRM + catálogo |
| `sync/sync_catalog.py` | Scraper oficial → `data.json` |
| `worker/` | Worker opcional con cron + `/data.json` |
| `deploy-pages.mjs` | Redeploy a Cloudflare Pages |

## Sync manual

```bash
python3 amaranthus-crm/sync/sync_catalog.py
python3 amaranthus-crm/sync/sync_catalog.py --refresh-thumbs
```

## Deploy CRM (Pages)

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
node amaranthus-crm/deploy-pages.mjs
# o:
npx wrangler pages deploy amaranthus-crm/site --project-name=amaranthus-app
```

## Worker opcional (cron en Cloudflare)

```bash
cd amaranthus-crm/worker
npx wrangler kv namespace create AMARANTHUS_CATALOG
# poner el id en wrangler.toml
npx wrangler deploy
curl -X POST https://<worker-host>/sync
```

## Secrets de GitHub (recomendados)

- `CLOUDFLARE_API_TOKEN` — redeploy Pages tras sync
- `CLOUDFLARE_ACCOUNT_ID`
- `AMARANTHUS_SYNC_URL` — URL del Worker (opcional)
- `AMARANTHUS_SYNC_KEY` — si proteges `POST /sync`
