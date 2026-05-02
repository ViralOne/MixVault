"""Translation helpers: Google Translate + MyMemory fallback."""
import json, time
import urllib.request
import urllib.parse

def _mymemory_translate(text, src, tgt):
    """Fallback translator using MyMemory API."""
    params = urllib.parse.urlencode({'q': text, 'langpair': f'{src}|{tgt}'})
    req = urllib.request.Request(
        f'https://api.mymemory.translated.net/get?{params}',
        headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    translated = data.get('responseData', {}).get('translatedText', '')
    if not translated or data.get('responseStatus') != 200:
        raise Exception(f"MyMemory failed: {data.get('responseStatus')}")
    return translated

def _gtranslate(text, src, tgt):
    """Translate with Google→MyMemory fallback and retry/backoff."""
    if not text or not text.strip():
        return text
    # Try Google first with retry
    for attempt in range(3):
        try:
            params = urllib.parse.urlencode({'client':'gtx','sl':src,'tl':tgt,'dt':'t','q':text})
            req = urllib.request.Request(
                f'https://translate.googleapis.com/translate_a/single?{params}',
                headers={'User-Agent':'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            return ''.join(s[0] for s in data[0])
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    # Fallback to MyMemory
    return _mymemory_translate(text, src, tgt)
