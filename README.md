# MixVault

A self-hosted recipe manager with 70,000+ recipes, AI-powered search, AI recipe creator, guided cooking mode, and multi-device sync.

## Features

- **Full-text search** across recipes in 22 languages
- **AI search** — describe what you want to cook in natural language
- **AI recipe creator** — chat with AI to generate recipes, find images, save to DB
- **Cookidoo URL import** — paste a URL, auto-import ingredients + AI-generate steps
- **Guided cooking mode** — step-by-step with timers, temperature, and speed indicators
- **Multi-device sync** — resume cooking from any device (continue cooking banner)
- **Shopping list** — add ingredients, merge duplicates by quantity, export to CSV, undo clear
- **Serving scaler** — adjust quantities (×½, ×1, ×2, ×3)
- **Translation** — translate any recipe between supported languages (Google + MyMemory fallback)
- **Ingredient icons** — 55K ingredient-to-icon mappings
- **Ingredient substitutions** — AI-powered alternatives for any ingredient
- **Nutrition filter** — filter recipes by calories, protein, carbs, fat
- **Recipe edit/delete** — modify or remove any recipe
- **Recipe sharing** — shareable standalone recipe page link
- **Favorites, notes, cooking history**
- **Recently viewed** — quick access to last viewed recipes
- **PIN authentication** — optional access protection
- **Dark mode**

## Quick Start

### Docker (recommended)

```bash
# Download the recipe database
./scripts/download-db.sh

# Start the app
docker compose up -d --build
```

Access at `http://localhost:8080`

### Local

```bash
python3 server.py
```

No dependencies required — stdlib only (Python 3.10+).

## Project Structure

```
.
├── server.py          # Backend (stdlib HTTP server + SQLite)
├── static/index.html  # Frontend (single-file vanilla HTML/CSS/JS)
├── data/              # Persistent state (mounted in Docker)
│   ├── recipes.db     # SQLite database
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
OLLAMA_MODEL=llama3

# Groq (free tier, fast)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# OpenRouter (free tier, many models)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Optional: PIN protection
AUTH_PIN=1234
```

Only configure the providers you want to use. The app tries them in `LLM_PROVIDER` order and falls through on failure.

## Architecture

- **Backend**: Python stdlib threaded HTTP server, SQLite with FTS5
- **Frontend**: Single-file vanilla HTML/CSS/JS (no build step)
- **Database**: SQLite with WAL mode, hourly automated backups, daily optimize
- **Deployment**: Docker + optional Caddy reverse proxy for HTTPS
- **Security**: PIN auth, rate limiting on AI, Content-Length limits, input sanitization

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
| `/api/export` | GET | Export data (JSON/CSV) |
| `/api/cooking-state` | GET/POST | Cross-device cooking resume |
| `/api/poll` | GET | Multi-device sync polling |
| `/api/health` | GET | Server health & stats |

## Backup

Automated hourly backups (keeps last 3) in `./data/backups/`. Manual backup:

```bash
./backup.sh
```

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
