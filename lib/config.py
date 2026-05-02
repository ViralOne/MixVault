"""Configuration, env loading, and constants."""
import os, sys, logging, time
from pathlib import Path

# ═══ LOGGING ═══
LOG_DIR = Path(os.environ.get("LOG_DIR", str(Path(__file__).parent.parent / "data" / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "server.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("cooker")

# Load .env
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ[k.strip()] = v.strip()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "")  # e.g. http://localhost:11434
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
# LLM_PROVIDER: comma-separated priority order. Options: ollama, groq, openrouter
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq,openrouter,ollama")
AUTH_PIN = os.environ.get("AUTH_PIN", "")
if OLLAMA_URL: log.info(f"Ollama configured ({OLLAMA_URL}, model={OLLAMA_MODEL})")
if GROQ_API_KEY: log.info(f"Groq API key loaded ({GROQ_API_KEY[:8]}...)")
if OPENROUTER_API_KEY: log.info(f"OpenRouter API key loaded ({OPENROUTER_API_KEY[:12]}...)")
if AUTH_PIN: log.info("PIN authentication enabled")
log.info(f"LLM priority: {LLM_PROVIDER}")

PORT = 8080
MAX_BODY_SIZE = 64 * 1024  # 64KB max POST body
START_TIME = time.time()

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "data" / "recipes.db"))
STATIC = str(Path(__file__).parent.parent / "static")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", str(Path(__file__).parent.parent / "data" / "backups")))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

LANG_NAMES = {
    "en":"English","de":"German","fr":"French","it":"Italian","es":"Spanish",
    "pt":"Portuguese","pl":"Polish","cs":"Czech","ro":"Romanian","nl":"Dutch",
    "da":"Danish","sv":"Swedish","no":"Norwegian","hu":"Hungarian","tr":"Turkish",
    "el":"Greek","zh":"Chinese","id":"Indonesian","ms":"Malay","is":"Icelandic",
    "ar":"Arabic","vi":"Vietnamese",
}

# Meta cache
META_CACHE_TTL = 30  # seconds
