# MixVault

[![Docker image](https://github.com/ViralOne/MixVault/actions/workflows/docker.yml/badge.svg)](https://github.com/ViralOne/MixVault/actions/workflows/docker.yml)

A self-hosted recipe manager with 70,000+ recipes, AI-powered search, AI recipe creator, guided cooking mode, and multi-device sync.

## Features

- **Full-text search** across recipes in 22 languages
- **AI search** — describe what you want to cook in natural language
- **AI recipe creator** — chat with AI to generate recipes, find images, save to DB
- **Cookidoo URL import** — paste a URL, auto-import ingredients + AI-generate steps
- **Guided cooking mode** — step-by-step with timers, temperature, and speed indicators
- **Hands-on step animations** — steps that don't use the Thermomix (chopping, washing, oven, fridge, plating…) get their own illustrated scene instead of the bowl/blade
- **Multi-device sync** — resume cooking from any device (continue cooking banner)
- **Shopping list** — add ingredients, merge duplicates by quantity, export to CSV, undo clear
- **Serving scaler** — adjust quantities (×½, ×1, ×2, ×3)
- **Translation** — translate any recipe between supported languages (Google + MyMemory fallback)
- **Ingredient icons** — 55K ingredient-to-icon mappings
- **Ingredient substitutions** — AI-powered alternatives for any ingredient
- **Nutrition filter** — filter recipes by calories, protein, carbs, fat
- **Tags** — tag recipes and filter the whole library by tag
- **Recipe edit/delete** — modify or remove any recipe
- **Recipe sharing** — shareable standalone recipe page link
- **Favorites, notes, cooking history**
- **Recently cooked carousel** — snap-scrolling rail with repeat counts and "cooked X ago"
- **Vaults (multi-user)** — one long random access key per person, no usernames or
  passwords. Each vault sees the shared recipe library plus only its own
  favourites, history, lists, notes, tags and imported recipes; nobody can tell
  who else uses the install
- **Dark mode**

## Quick Start

### Docker (recommended)

```bash
# Download the recipe database
./scripts/download-db.sh

# Start the app
docker compose up -d --build
```

Access at `http://localhost:8039`

#### Or run the pre-built image

Every push to `master` publishes `ghcr.io/viralone/mixvault` for `linux/amd64` and
`linux/arm64` (so a Raspberry Pi or ARM NAS works), tagged `latest`, `sha-<commit>`
and — for a `v*` tag — the version. The image contains no recipes: `recipes.db` is
mounted, and `vault.db` is created next to it on first run.

```bash
docker run -d --name mixvault -p 8039:8080 \
  -v "$PWD/data:/data" --env-file .env \
  ghcr.io/viralone/mixvault:latest
```

To use it from compose instead of building locally, swap the `build: .` line in
`docker-compose.yml` for `image: ghcr.io/viralone/mixvault:latest`.

### Local

```bash
python3 server.py            # serves the pre-built frontend from static/
```

The backend needs no dependencies — stdlib only (Python 3.10+).

### Frontend development

The UI is a SolidJS + TypeScript app in `web/`, built by Vite into `static/`
(the server's document root). The built output is committed so `python3 server.py`
works without Node.

```bash
cd web
npm install
npm run dev          # http://localhost:5173, proxies /api to :8039 (API_TARGET to override)
npm run build        # writes ../static
npm run typecheck    # tsc --noEmit
```

`#/dev/scenes` in dev mode renders every hands-on cooking animation on one page.

## Vaults and access keys

Recipes are shared; everything personal is not.

- `data/recipes.db` — the recipe library and its search index. No personal data
  ever lands here, so you can copy it or hand it to someone else as-is.
- `data/vault.db` — access keys plus every vault's favourites, cooking history,
  shopping list, notes, tags, resume state and privately imported recipes.

A person signs in with one key — there is no username and no password:

```
mv_7q4k-x9f2-h8ta-3wnp-6dbe-5rjm
```

### In the app

Once at least one key exists, three controls appear (they are hidden while the
install is still a single open vault — that is why you may not see them yet):

| where | what it does |
|---|---|
| `⇄` in the top bar, next to `⋮` | **Switch vault** — clears the session and returns to the access-key page, where you paste another key. Its tooltip names the vault you are in. |
| Settings → *Create a vault key* | Mints a key for someone else and shows it once with a Copy button. Your own session is untouched. |
| Settings → *Sign out* | Same as `⇄`, next to the current vault's name. |

Each browser holds its own session, so you can be one vault in Chrome and another
in a private window at the same time, without switching.

### From the CLI

Needed for the first key and for admin tasks (the key is printed once; only its
hash is stored):

```bash
python3 scripts/users.py add "Petre"                     # new empty vault
python3 scripts/users.py add "Petre" --claim             # ...and adopt existing data
python3 scripts/users.py list                            # ids/labels, never keys
python3 scripts/users.py stats                           # rows per vault
python3 scripts/users.py revoke <id> [--delete-data]

# Docker
docker compose exec cooker python3 scripts/users.py add "Petre" --claim
```

Notes:

- **Until the first key exists** the app behaves exactly as before: one open
  vault, or PIN-protected if `AUTH_PIN` is set. Creating the first key with
  `--claim` (the default on an install that already has data) hands the existing
  favourites and history to that vault, and from then on every request needs a key.
- **No enumeration.** No endpoint lists or counts vaults; `/api/session` only
  describes the caller. A wrong key, a malformed key and a revoked key produce the
  same message, and failed attempts are rate-limited per IP.
- **Private recipes.** AI-created, Cookidoo-imported and translated recipes live in
  the vault and are visible only to their owner — including via `/api/share/:id`.
- **The shared library is read-only** once access keys exist: no vault can edit or
  delete a recipe everyone else sees (`403`). In single-user mode both still work.
- **Who may mint keys.** Anyone already signed in (a new empty vault reveals
  nothing about existing ones, and they can already see their own). Strangers on
  the login page cannot, unless you set `ALLOW_SIGNUP=1`, which adds a "Create a
  new vault" button there.
- **Losing a key means losing the vault.** Keep `data/vault.db` in your backups —
  hourly backups cover both databases (`data/backups/recipes_*.db`, `vault_*.db`).
- **Going back to one open vault** takes more than revoking the keys: the data now
  has an owner, so it would look empty afterwards. Revoke all keys *and* move the
  rows back to the unowned `user_id = ''`.
- Behind HTTPS, forward `X-Forwarded-Proto` so the session cookie gets `Secure`.

## Project Structure

```
.
├── .github/workflows/ # CI: typecheck, smoke-test the image, publish to GHCR
├── server.py          # Backend (stdlib HTTP server + SQLite)
├── lib/               # Backend modules (db, config, users, handlers, ai, translate)
├── scripts/users.py   # Vault key management (add / list / stats / revoke)
├── web/               # Frontend source (SolidJS + TypeScript + Vite)
│   ├── src/lib/       # api client, formatting, step classifier, device APIs
│   ├── src/state/     # signals: browse, recipe, cooking, shopping, router, toast
│   ├── src/components/# views, carousel, cooking scenes, panels, modals
│   └── src/styles/    # design tokens + per-area CSS
├── static/            # Built frontend (generated by `npm run build`)
├── data/              # Persistent state (mounted in Docker)
│   ├── recipes.db     # Recipe library (shareable, no personal data)
│   ├── vault.db       # Access keys + per-vault data (private, back this up)
│   ├── logs/          # Server logs
│   └── backups/       # Automated hourly backups
├── Dockerfile
├── docker-compose.yml
├── Caddyfile          # Optional HTTPS reverse proxy
├── entrypoint.sh      # Auto-restart with backoff
├── backup.sh          # Manual backup script
├── build_db.py        # Build DB from recipe JSON
└── build_icons.py     # Extract ingredient icons from HTML
```

## Configuration

Create a `.env` file (see `.env.example`):

```env
# LLM provider priority (comma-separated): ollama, groq, openrouter
LLM_PROVIDER=groq,openrouter,ollama

# Ollama (self-hosted, no API key needed)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5

# Groq (free tier, fast)
GROQ_API_KEY=gsk_...
GROQ_MODEL=qwen/qwen3.8-27b

# OpenRouter (free tier, many models). openrouter/free auto-routes to whatever
# free model is live, so it does not go stale like a pinned id.
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openrouter/free

# Access: vaults are opened with access keys (scripts/users.py add)
ALLOW_SIGNUP=          # 1 = show "Create a new vault" on the login page
COOKIE=mv_key          # session cookie name; rename to sign every device out
SESSION_MAX_AGE=31536000   # session lifetime in seconds (1 year)
CORS_ORIGINS=          # extra origins allowed to call the API; empty = same-origin only
TRUST_PROXY=           # 1 only behind a proxy you control (login throttle + Secure cookie)

# Legacy: single shared PIN, ignored once access keys exist
AUTH_PIN=1234
```

Only configure the providers you want to use. The app tries them in `LLM_PROVIDER` order and falls through on failure — silently, so a retired model id looks like "AI unavailable". Both providers publish their current list:

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY" | jq -r '.data[].id'
curl -s https://openrouter.ai/api/v1/models | jq -r '.data[].id'
```

## Architecture

- **Backend**: Python stdlib threaded HTTP server, SQLite with FTS5
- **Frontend**: SolidJS + TypeScript, built with Vite into `static/` (~34 kB gzipped)
- **Database**: two SQLite files (library + vault) opened as one connection via
  `ATTACH`; WAL mode, hourly automated backups of both, daily optimize
- **Deployment**: Docker + optional Caddy reverse proxy for HTTPS

### Security

| Area | What is in place |
|------|------------------|
| Sessions | Access-key cookie, httpOnly, `SameSite=Lax`, `Secure` when `TRUST_PROXY=1` and the proxy reports https |
| Vault isolation | Every query is scoped by `user_id`; the shared library is read-only once keys exist; nothing over HTTP can list or count vaults |
| Login | Per-IP throttle (8 tries / 5 min, then a lockout), identical wording for wrong, unknown and revoked keys, `hmac.compare_digest` on the legacy PIN |
| Cross-site | Writes with a foreign `Origin` or `Sec-Fetch-Site` are refused — including `/api/auth`, so no site can sign a visitor into its own vault |
| Browser headers | CSP with the inline script allowed by hash (no `unsafe-inline` for scripts), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` |
| Outbound requests | A user-supplied import URL must be http(s), on a real Cookidoo site, resolving to a public address — redirects re-checked, response size capped ([`lib/net.py`](lib/net.py)) |
| Untrusted input | One place shapes every write: HTML stripped, lengths and row counts capped, JSON columns validated ([`lib/sanitize.py`](lib/sanitize.py)) |
| Third-party cost | Per-identity rate limits on chat, image lookup, translation and import |
| At rest | `vault.db` and its backups are `0600`; `no-store, private` on every personal response; share pages HTML-escaped under `default-src 'none'` |
| Exports | Shopping-list CSV neutralises spreadsheet formulas (`=`, `+`, `-`, `@`) |

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/recipes` | GET | Search/browse recipes |
| `/api/recipe/:id` | GET | Full recipe details with ingredient icons |
| `/api/recipe/import` | POST | Import custom recipe |
| `/api/recipe/edit/:id` | POST | Edit recipe |
| `/api/recipe/delete/:id` | POST | Delete recipe |
| `/api/similar/:id` | GET | Related recipes (deduplicated) |
| `/api/ai` | POST | AI-powered natural language search |
| `/api/ai/create` | POST | AI recipe creator (multi-turn chat) |
| `/api/ai/images` | POST | Find images for a recipe |
| `/api/shopping` | GET | Shopping list |
| `/api/shopping/add` | POST | Add ingredients |
| `/api/shopping/restore` | POST | Undo clear |
| `/api/export` | GET | Export your vault (JSON: favourites, notes, list, tags, history, your recipes — CSV: shopping list) |
| `/api/import/restore` | POST | Load a vault export into the calling vault |
| `/api/cooking-state` | GET/POST | Cross-device cooking resume |
| `/api/tags` | GET | All tags with usage counts (browse filter) |
| `/api/tags/:id` | GET/POST | Tags for one recipe |
| `/api/poll` | GET | Multi-device sync polling |
| `/api/auth` | POST | Exchange an access key for a session cookie |
| `/api/auth/new` | POST | Mint a vault key (signed-in members, or `ALLOW_SIGNUP=1`) |
| `/api/auth/logout` | POST | Clear the session cookie |
| `/api/session` | GET | Own session info (never other vaults) |
| `/api/health` | GET | Server health & stats |

## Backup

Automated hourly backups of both databases (keeps the last 3 of each) in
`./data/backups/`. `vault_*.db` is the one you cannot rebuild — access keys and
everyone's personal data live there. Manual backup:

```bash
./backup.sh
```

**Per-vault backup.** Settings → *Download Backup* exports one vault as JSON:
favourites, cooking history, shopping list, notes, tags and the recipes that vault
added. The shared library is not in there — it is `recipes.db`, one file you copy
directly. *Restore from backup* loads such a file into whichever vault is signed
in, so a backup also serves to move a vault or rebuild one after a lost key;
restoring the same file twice does not duplicate anything except shopping items.

## Building the Database

The database is built from recipe HTML files. To generate it:

1. **Obtain recipe HTML files** — Search for "Recipes after TM7 UI" archives online. These contain recipe pages organized by country and collection.

2. **Run the build script:**
   ```bash
   ./scripts/build.sh /path/to/recipe-html-folder
   ```

   This will parse HTML → build SQLite DB → extract ingredient icons → place `recipes.db` in `data/`.

3. **Start the app:**
   ```bash
   docker compose up -d --build
   ```

The HTML files should be organized as:
```
Recipe Folder/
├── Country/
│   ├── Collection/
│   │   ├── Recipe Name.html
│   │   └── ...
```

Each HTML file contains structured recipe data (JSON-LD schema + ingredient icons) that the scripts extract automatically.

## Reverse Proxy (HTTPS)

Edit `Caddyfile` with your domain, then uncomment the Caddy service in `docker-compose.yml`.

Works great with Tailscale Funnel for external access.

## License

Personal use.
