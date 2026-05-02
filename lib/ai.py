"""AI chat provider abstraction and rate limiting."""
import json
import urllib.request
from .config import (log, LLM_PROVIDER, OLLAMA_URL, OLLAMA_MODEL,
                     GROQ_API_KEY, GROQ_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODEL)

# Rate limiting for AI endpoint
_ai_rate = {}  # ip -> (count, window_start)
AI_RATE_LIMIT = 10  # requests per minute
AI_RATE_WINDOW = 60  # seconds

def _ai_chat(messages, max_tokens=1024):
    """Call AI using provider priority from LLM_PROVIDER env var."""
    providers = []
    for p in LLM_PROVIDER.split(","):
        p = p.strip().lower()
        if p == "ollama" and OLLAMA_URL:
            providers.append(("ollama", f"{OLLAMA_URL.rstrip('/')}/api/chat", "", OLLAMA_MODEL, {}))
        elif p == "groq" and GROQ_API_KEY:
            providers.append(("groq", "https://api.groq.com/openai/v1/chat/completions", GROQ_API_KEY, GROQ_MODEL, {}))
        elif p == "openrouter" and OPENROUTER_API_KEY:
            providers.append(("openrouter", "https://openrouter.ai/api/v1/chat/completions", OPENROUTER_API_KEY, OPENROUTER_MODEL, {"HTTP-Referer": "http://localhost:8080"}))
    if not providers:
        return None
    for name, url, key, model, extra_headers in providers:
        try:
            if name == "ollama":
                # Ollama uses different API format
                body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
                headers = {"Content-Type": "application/json"}
            else:
                body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7}).encode()
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "MixVault/1.0"}
                headers.update(extra_headers)
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60 if name == "ollama" else 30)
            data = json.loads(resp.read())
            if name == "ollama":
                return data["message"]["content"]
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning(f"AI provider {name} failed: {e}")
            continue
    return None
