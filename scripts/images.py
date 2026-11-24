#!/usr/bin/env python3
"""Multi-provider Image Search & AI Image Generator for Reel Effects.

Original Reel Effects Pack by Adam Digital (@adam.godigital) & Vibha Ramprakash (MIT).
Extended for Antigravity with free image search (Pixabay, Pexels) and AI image generation
(Google AI Studio / Gemini / Imagen, OpenAI DALL-E / gpt-image-1, OpenRouter, Together, Fal.ai, Pollinations free fallback).

Usage:
  # Search free images (Pixabay default, fallback Pexels / Wikimedia / Pollinations)
  python scripts/images.py --search "tokyo neon street" --count 4 --out ./cards

  # Generate image with Google AI Studio (GEMINI_API_KEY / GOOGLE_API_KEY)
  python scripts/images.py --generate "futuristic glass dashboard UI" --provider google --out card.png

  # Generate image with other AI API keys (openai, openrouter, together, fal, pollinations)
  python scripts/images.py --generate "3d gold trophy icon" --provider openai --api-key sk-... --out card.png

  # Auto mode: uses Google AI Studio if key is available, else Pixabay search, else free Pollinations AI
  python scripts/images.py --auto "cyberpunk coding setup" --count 1 --out card.png

  # Check configured API keys (masked)
  python scripts/images.py --doctor
"""
import argparse, base64, hashlib, io, json, os, re, subprocess, sys, urllib.parse, urllib.request
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, '.cache', 'images')
ENV_PATHS = [
    os.path.join(ROOT, '.env'),
    r'C:\Users\user\Documents\local\docs\credentials\.env',
    os.path.expanduser('~/.env'),
]

PROVIDER_KEYS = {
    'pixabay': ('PIXABAY_API_KEY',),
    'pexels': ('PEXELS_API_KEY',),
    'unsplash': ('UNSPLASH_ACCESS_KEY', 'UNSPLASH_API_KEY'),
    'google': ('GEMINI_API_KEY', 'GOOGLE_AI_STUDIO_KEY', 'GOOGLE_API_KEY'),
    'openai': ('OPENAI_API_KEY',),
    'openrouter': ('OPENROUTER_API_KEY',),
    'together': ('TOGETHER_API_KEY',),
    'fal': ('FAL_KEY', 'FAL_API_KEY'),
    'stability': ('STABILITY_API_KEY',),
    'replicate': ('REPLICATE_API_TOKEN',),
}


def load_env_files():
    """Load key=value pairs from .env files without overwriting existing environment variables."""
    for p in ENV_PATHS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    if line.startswith('export '):
                        line = line[7:].strip()
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


load_env_files()


def get_key(provider, override=None):
    if override:
        return override.strip()
    for env_name in PROVIDER_KEYS.get(provider, ()):
        val = os.environ.get(env_name, '').strip()
        if val:
            return val
    return None


def http_json(url, method='GET', headers=None, payload=None, timeout=45):
    hdrs = {'User-Agent': 'ReelEffects-Antigravity/1.0'}
    if headers:
        hdrs.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        hdrs.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def download_image(url, dst_path, headers=None, timeout=45):
    hdrs = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReelEffects/1.0'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    im.save(dst_path)
    return dst_path


def save_b64_image(b64_str, dst_path):
    raw = base64.b64decode(b64_str)
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    im.save(dst_path)
    return dst_path


# ---------- 1. FREE STOCK SEARCH PROVIDERS ----------

def search_pixabay(query, count=1, dst_Paths=None, api_key=None, orientation='vertical'):
    """Search free images on Pixabay API (requires free PIXABAY_API_KEY from pixabay.com/api/docs/)."""
    key = get_key('pixabay', api_key)
    if not key:
        raise RuntimeError("Missing PIXABAY_API_KEY. Set PIXABAY_API_KEY in .env or pass --api-key.")
    q = urllib.parse.quote(query)
    ori = 'vertical' if orientation in ('vertical', 'portrait', '9:16') else 'all'
    per_page = max(3, min(50, count * 2))
    url = f"https://pixabay.com/api/?key={key}&q={q}&image_type=photo&orientation={ori}&per_page={per_page}&safesearch=true"
    data = http_json(url)
    hits = data.get('hits') or []
    if not hits and ori != 'all':
        url = f"https://pixabay.com/api/?key={key}&q={q}&image_type=all&per_page={per_page}&safesearch=true"
        hits = http_json(url).get('hits') or []
    if not hits:
        raise RuntimeError(f"Pixabay returned 0 results for '{query}'.")
    saved = []
    for i, h in enumerate(hits[:count]):
        img_url = h.get('largeImageURL') or h.get('webformatURL')
        if not img_url:
            continue
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('pixabay', query, i)
        saved.append(download_image(img_url, dst))
    return saved


def search_pexels(query, count=1, dst_Paths=None, api_key=None, orientation='portrait'):
    """Search free stock photos on Pexels API (PEXELS_API_KEY)."""
    key = get_key('pexels', api_key)
    if not key:
        raise RuntimeError("Missing PEXELS_API_KEY.")
    q = urllib.parse.quote(query)
    per_page = max(1, min(30, count))
    url = f"https://api.pexels.com/v1/search?query={q}&per_page={per_page}&orientation={orientation}"
    data = http_json(url, headers={'Authorization': key})
    photos = data.get('photos') or []
    if not photos:
        raise RuntimeError(f"Pexels returned 0 results for '{query}'.")
    saved = []
    for i, p in enumerate(photos[:count]):
        src = p.get('src') or {}
        img_url = src.get('large2x') or src.get('large') or src.get('original')
        if not img_url:
            continue
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('pexels', query, i)
        saved.append(download_image(img_url, dst))
    return saved


def search_wikimedia(query, count=1, dst_Paths=None):
    """Keyless free image search via Wikimedia Commons API."""
    params = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'search',
        'gsrsearch': f'filetype:bitmap {query}',
        'gsrlimit': max(5, count * 3),
        'prop': 'imageinfo',
        'iiprop': 'url',
        'iiurlwidth': 1080,
        'format': 'json',
    })
    url = f"https://commons.wikimedia.org/w/api.php?{params}"
    data = http_json(url)
    pages = (data.get('query') or {}).get('pages') or {}
    saved = []
    for page in pages.values():
        ii = (page.get('imageinfo') or [{}])[0]
        img_url = ii.get('thumburl') or ii.get('url')
        if not img_url or not any(img_url.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
            continue
        idx = len(saved)
        dst = dst_Paths[idx] if dst_Paths and idx < len(dst_Paths) else _cache_path('wikimedia', query, idx)
        try:
            saved.append(download_image(img_url, dst))
            if len(saved) >= count:
                break
        except Exception:
            continue
    if not saved:
        raise RuntimeError(f"Wikimedia Commons found no images for '{query}'.")
    return saved


# ---------- 2. AI IMAGE GENERATION PROVIDERS ----------

def generate_google_aistudio(prompt, count=1, dst_Paths=None, api_key=None, model=None, aspect_ratio='9:16'):
    """Generate images via Google AI Studio (GEMINI_API_KEY / GOOGLE_API_KEY).
    Tries Gemini native image output (gemini-2.5-flash-image / gemini-2.0-flash-exp-image-generation)
    and Imagen 3 (imagen-3.0-generate-002).
    """
    key = get_key('google', api_key)
    if not key:
        raise RuntimeError("Missing Google AI Studio key (set GEMINI_API_KEY or GOOGLE_AI_STUDIO_KEY, or pass --api-key).")

    models_to_try = [model] if model else [
        'gemini-2.5-flash-image-preview',
        'gemini-2.0-flash-exp-image-generation',
        'imagen-3.0-generate-002',
    ]
    saved = []
    last_err = None

    for m in models_to_try:
        if not m:
            continue
        try:
            if m.startswith('imagen-'):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:predict?key={key}"
                payload = {
                    'instances': [{'prompt': prompt}],
                    'parameters': {'sampleCount': max(1, min(4, count)), 'aspectRatio': aspect_ratio}
                }
                res = http_json(url, method='POST', payload=payload, timeout=90)
                preds = res.get('predictions') or []
                for i, pred in enumerate(preds[:count]):
                    b64 = pred.get('bytesBase64Encoded')
                    if b64:
                        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('google', prompt, i)
                        saved.append(save_b64_image(b64, dst))
                if saved:
                    return saved
            else:
                for i in range(count):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                    payload = {
                        'contents': [{'parts': [{'text': f"Generate a high-quality visual image for a video reel: {prompt}"}]}],
                        'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}
                    }
                    res = http_json(url, method='POST', payload=payload, timeout=90)
                    for cand in res.get('candidates') or []:
                        for part in (cand.get('content') or {}).get('parts') or []:
                            inline = part.get('inlineData') or part.get('inline_data')
                            if inline and inline.get('data'):
                                idx = len(saved)
                                dst = dst_Paths[idx] if dst_Paths and idx < len(dst_Paths) else _cache_path('google', prompt, idx)
                                saved.append(save_b64_image(inline['data'], dst))
                                break
                        if len(saved) > i:
                            break
                if saved:
                    return saved
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Google AI Studio generation failed ({last_err}). Check your credit/quota or try another model.")


def generate_openai(prompt, count=1, dst_Paths=None, api_key=None, model=None):
    """Generate images via OpenAI API (gpt-image-1 or dall-e-3)."""
    key = get_key('openai', api_key)
    if not key:
        raise RuntimeError("Missing OPENAI_API_KEY.")
    m = model or 'dall-e-3'
    saved = []
    for i in range(count):
        url = "https://api.openai.com/v1/images/generations"
        payload = {'model': m, 'prompt': prompt, 'n': 1, 'size': '1024x1024'}
        if m != 'gpt-image-1':
            payload['response_format'] = 'b64_json'
        res = http_json(url, method='POST', headers={'Authorization': f'Bearer {key}'}, payload=payload, timeout=90)
        item = (res.get('data') or [{}])[0]
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('openai', prompt, i)
        if item.get('b64_json'):
            saved.append(save_b64_image(item['b64_json'], dst))
        elif item.get('url'):
            saved.append(download_image(item['url'], dst))
    return saved


def generate_openrouter(prompt, count=1, dst_Paths=None, api_key=None, model=None):
    """Generate images via OpenRouter API (supports Gemini Flash Image / Flux / etc.)."""
    key = get_key('openrouter', api_key)
    if not key:
        raise RuntimeError("Missing OPENROUTER_API_KEY.")
    m = model or 'google/gemini-2.5-flash-image-preview'
    saved = []
    for i in range(count):
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            'model': m,
            'messages': [{'role': 'user', 'content': f"Generate an image: {prompt}"}],
            'modalities': ['image', 'text'],
        }
        res = http_json(url, method='POST', headers={'Authorization': f'Bearer {key}'}, payload=payload, timeout=90)
        msg = ((res.get('choices') or [{}])[0]).get('message') or {}
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('openrouter', prompt, i)
        # Check images list or base64 data URL in content
        imgs = msg.get('images') or []
        if imgs:
            u = (imgs[0].get('image_url') or {}).get('url', '')
            if u.startswith('data:image'):
                saved.append(save_b64_image(u.split(',', 1)[1], dst))
            elif u:
                saved.append(download_image(u, dst))
        else:
            content = str(msg.get('content') or '')
            m_b64 = re.search(r'data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)', content)
            if m_b64:
                saved.append(save_b64_image(m_b64.group(1), dst))
    if not saved:
        raise RuntimeError("OpenRouter did not return an image payload.")
    return saved


def generate_together(prompt, count=1, dst_Paths=None, api_key=None, model=None):
    """Generate images via Together AI (FLUX.1-schnell)."""
    key = get_key('together', api_key)
    if not key:
        raise RuntimeError("Missing TOGETHER_API_KEY.")
    m = model or 'black-forest-labs/FLUX.1-schnell'
    saved = []
    for i in range(count):
        url = "https://api.together.xyz/v1/images/generations"
        payload = {'model': m, 'prompt': prompt, 'width': 768, 'height': 1024, 'steps': 4, 'n': 1, 'response_format': 'b64_json'}
        res = http_json(url, method='POST', headers={'Authorization': f'Bearer {key}'}, payload=payload, timeout=90)
        item = (res.get('data') or [{}])[0]
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('together', prompt, i)
        if item.get('b64_json'):
            saved.append(save_b64_image(item['b64_json'], dst))
        elif item.get('url'):
            saved.append(download_image(item['url'], dst))
    return saved


def generate_fal(prompt, count=1, dst_Paths=None, api_key=None, model=None):
    """Generate images via Fal.ai (fal-ai/flux/schnell)."""
    key = get_key('fal', api_key)
    if not key:
        raise RuntimeError("Missing FAL_KEY.")
    m = model or 'fal-ai/flux/schnell'
    url = f"https://fal.run/{m}"
    payload = {'prompt': prompt, 'image_size': 'portrait_16_9', 'num_images': count}
    res = http_json(url, method='POST', headers={'Authorization': f'Key {key}'}, payload=payload, timeout=90)
    imgs = res.get('images') or []
    saved = []
    for i, item in enumerate(imgs[:count]):
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('fal', prompt, i)
        if item.get('url'):
            saved.append(download_image(item['url'], dst))
    if not saved:
        raise RuntimeError("Fal.ai returned no images.")
    return saved


def generate_pollinations(prompt, count=1, dst_Paths=None, width=768, height=1024):
    """Free keyless AI image generation via Pollinations.ai."""
    saved = []
    for i in range(count):
        seed = (abs(hash(f"{prompt}_{i}")) % 999999) + 1
        q = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{q}?width={width}&height={height}&seed={seed}&nologo=true"
        dst = dst_Paths[i] if dst_Paths and i < len(dst_Paths) else _cache_path('pollinations', prompt, i)
        saved.append(download_image(url, dst, timeout=60))
    return saved


def generate_agy_cli(prompt, dst_path):
    """Use Antigravity CLI built-in image-generator tool if available."""
    agy_bin = r"C:\Users\user\AppData\Local\agy\bin\agy.exe"
    if not os.path.exists(agy_bin):
        raise RuntimeError("Antigravity CLI (agy.exe) not found.")
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    clean_dst = os.path.abspath(dst_path).replace('\\', '/')
    cmd = [
        agy_bin, '-p',
        f"Generate an image of {prompt} using your image-generator tool. Save the output directly as {clean_dst}.",
        '--dangerously-skip-permissions'
    ]
    subprocess.run(cmd, check=True, timeout=180)
    if not os.path.exists(dst_path):
        raise RuntimeError("agy CLI completed but image file was not created.")
    return [dst_path]


# ---------- 3. UNIFIED RESOLVER FOR FX.PY ----------

def _cache_path(provider, query, idx=0):
    os.makedirs(CACHE_DIR, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '_', query.lower()).strip('_')[:32] or 'img'
    h = hashlib.md5(f"{provider}:{query}:{idx}".encode('utf-8')).hexdigest()[:8]
    return os.path.join(CACHE_DIR, f"{provider}_{slug}_{idx}_{h}.png")


def _target_paths(out, provider, query, count):
    if not out:
        return [_cache_path(provider, query, i) for i in range(count)]
    ext = os.path.splitext(out)[1].lower()
    if ext in ('.png', '.jpg', '.jpeg', '.webp') and count == 1:
        return [out]
    if ext in ('.png', '.jpg', '.jpeg', '.webp') and count > 1:
        base, e = os.path.splitext(out)
        return [f"{base}_{i+1}{e}" for i in range(count)]
    os.makedirs(out, exist_ok=True)
    return [os.path.join(out, f"img_{i+1:02d}.png") for i in range(count)]


def resolve_visual(query, mode='auto', provider='auto', count=1, out=None, api_key=None, model=None):
    """Resolve one or more images by search or AI generation with smart fallback.

    Modes:
      - 'search': Free stock photo search (Pixabay -> Pexels -> Wikimedia)
      - 'generate': AI image generation (Google AI Studio -> OpenAI -> OpenRouter -> Together -> Fal -> Pollinations)
      - 'auto': Try requested provider; if 'auto', use Pixabay/Pexels for search or Google AI Studio if key is set, else free Pollinations/Wikimedia.
    """
    prov = (provider or 'auto').lower().strip()

    # Check cache first if out is None
    if out is None and prov != 'auto':
        cached_files = [_cache_path(prov, query, i) for i in range(count)]
        if all(os.path.exists(p) for p in cached_files):
            return cached_files

    dsts = _target_paths(out, prov if prov != 'auto' else 'auto', query, count)

    # Explicit provider dispatch
    if prov == 'pixabay':
        return search_pixabay(query, count, dsts, api_key)
    if prov == 'pexels':
        return search_pexels(query, count, dsts, api_key)
    if prov in ('wikimedia', 'commons'):
        return search_wikimedia(query, count, dsts)
    if prov in ('google', 'gemini', 'aistudio', 'imagen'):
        return generate_google_aistudio(query, count, dsts, api_key, model)
    if prov in ('openai', 'dalle'):
        return generate_openai(query, count, dsts, api_key, model)
    if prov == 'openrouter':
        return generate_openrouter(query, count, dsts, api_key, model)
    if prov == 'together':
        return generate_together(query, count, dsts, api_key, model)
    if prov == 'fal':
        return generate_fal(query, count, dsts, api_key, model)
    if prov == 'pollinations':
        return generate_pollinations(query, count, dsts)
    if prov == 'agy':
        return generate_agy_cli(query, dsts[0])

    # Auto mode cascade
    errors = []
    if mode == 'search':
        order = [
            ('pixabay', lambda: search_pixabay(query, count, dsts, api_key)),
            ('pexels', lambda: search_pexels(query, count, dsts, api_key)),
            ('wikimedia', lambda: search_wikimedia(query, count, dsts)),
            ('pollinations', lambda: generate_pollinations(query, count, dsts)),
        ]
    elif mode == 'generate':
        order = [
            ('google', lambda: generate_google_aistudio(query, count, dsts, api_key, model)),
            ('openai', lambda: generate_openai(query, count, dsts, api_key, model)),
            ('openrouter', lambda: generate_openrouter(query, count, dsts, api_key, model)),
            ('together', lambda: generate_together(query, count, dsts, api_key, model)),
            ('fal', lambda: generate_fal(query, count, dsts, api_key, model)),
            ('pollinations', lambda: generate_pollinations(query, count, dsts)),
        ]
    else:
        # 'auto' mode: prefer Pixabay free search if key exists, then Google AI Studio if key exists, then Pexels, then Pollinations/Wikimedia
        order = [
            ('pixabay', lambda: search_pixabay(query, count, dsts, api_key)),
            ('google', lambda: generate_google_aistudio(query, count, dsts, api_key, model)),
            ('pexels', lambda: search_pexels(query, count, dsts, api_key)),
            ('openai', lambda: generate_openai(query, count, dsts, api_key, model)),
            ('openrouter', lambda: generate_openrouter(query, count, dsts, api_key, model)),
            ('together', lambda: generate_together(query, count, dsts, api_key, model)),
            ('fal', lambda: generate_fal(query, count, dsts, api_key, model)),
            ('pollinations', lambda: generate_pollinations(query, count, dsts)),
            ('wikimedia', lambda: search_wikimedia(query, count, dsts)),
        ]

    for name, fn in order:
        try:
            res = fn()
            if res:
                print(f"[images] Resolved {len(res)} image(s) for '{query}' via {name}", flush=True)
                return res
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    raise RuntimeError(f"All image providers failed for '{query}': " + " | ".join(errors))


def resolve_for_effect(opts, count_default=1):
    """Helper called by fx.py to resolve image/images from effect options.
    Supports:
      - image_search / search: "query" (searches Pixabay/Pexels/Wikimedia)
      - image_prompt / prompt / ai_prompt: "prompt" (generates via Google AI Studio / AI provider)
      - provider: "pixabay" | "google" | "openai" | "openrouter" | "together" | "fal" | "pollinations" | "pexels" | "wikimedia"
      - api_key: optional custom key override
      - model: optional AI model override
      - image / images: prefixes like "pixabay:cats", "google:futuristic city", "ai:neon dashboard"
    """
    prov = opts.get('provider') or opts.get('ai_provider') or 'auto'
    api_key = opts.get('api_key')
    model = opts.get('model')
    cnt = int(opts.get('count', count_default))

    # Check prefix syntax in 'image' or 'images' e.g. "pixabay:coffee shop" or "google:3d robot"
    for field in ('image', 'images'):
        val = str(opts.get(field) or '').strip()
        if ':' in val and not os.path.exists(val) and not (len(val) > 2 and val[1] == ':'):
            prefix, rest = val.split(':', 1)
            p_low = prefix.lower().strip()
            if p_low in ('pixabay', 'pexels', 'wikimedia', 'commons', 'search'):
                p_use = 'auto' if p_low == 'search' else p_low
                return resolve_visual(rest.strip(), mode='search', provider=p_use, count=1 if field == 'image' else cnt, api_key=api_key, model=model)
            if p_low in ('google', 'gemini', 'aistudio', 'imagen', 'openai', 'dalle', 'openrouter', 'together', 'fal', 'pollinations', 'agy', 'ai', 'generate'):
                p_use = 'auto' if p_low in ('ai', 'generate') else p_low
                return resolve_visual(rest.strip(), mode='generate', provider=p_use, count=1 if field == 'image' else cnt, api_key=api_key, model=model)

    if opts.get('image_search') or opts.get('search'):
        q = str(opts.get('image_search') or opts.get('search')).strip()
        return resolve_visual(q, mode='search', provider=prov, count=cnt, api_key=api_key, model=model)

    if opts.get('image_prompt') or opts.get('ai_prompt') or opts.get('prompt'):
        q = str(opts.get('image_prompt') or opts.get('ai_prompt') or opts.get('prompt')).strip()
        return resolve_visual(q, mode='generate', provider=prov, count=cnt, api_key=api_key, model=model)

    return None


def doctor():
    print("Reel Effects Image Providers Status:")
    print("-" * 55)
    for prov, env_vars in PROVIDER_KEYS.items():
        val = get_key(prov)
        status = f"READY ({env_vars[0]} set)" if val else f"missing ({' or '.join(env_vars)})"
        print(f"  {prov:12s} : {status}")
    print("  wikimedia    : READY (free keyless stock search)")
    print("  pollinations : READY (free keyless AI generation)")
    agy_ok = os.path.exists(r"C:\Users\user\AppData\Local\agy\bin\agy.exe")
    print(f"  agy          : {'READY (Antigravity CLI)' if agy_ok else 'missing'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--search', help='Search free images (Pixabay / Pexels / Wikimedia)')
    ap.add_argument('--generate', help='Generate AI image (Google AI Studio / OpenAI / OpenRouter / Fal / Together / Pollinations)')
    ap.add_argument('--auto', help='Auto resolve image by search or AI generation')
    ap.add_argument('--provider', default='auto', help='pixabay, pexels, wikimedia, google, openai, openrouter, together, fal, pollinations, agy')
    ap.add_argument('--api-key', help='Optional API key override (otherwise reads from environment / .env)')
    ap.add_argument('--model', help='Optional model override (e.g. imagen-3.0-generate-002, gemini-2.5-flash-image-preview, dall-e-3)')
    ap.add_argument('--count', type=int, default=1, help='Number of images to fetch/generate')
    ap.add_argument('--out', help='Output file path (if count=1) or output folder')
    ap.add_argument('--doctor', action='store_true', help='Check configured provider API keys')
    a = ap.parse_args()

    if a.doctor:
        doctor()
        return

    if a.search:
        paths = resolve_visual(a.search, mode='search', provider=a.provider, count=a.count, out=a.out, api_key=a.api_key, model=a.model)
    elif a.generate:
        paths = resolve_visual(a.generate, mode='generate', provider=a.provider, count=a.count, out=a.out, api_key=a.api_key, model=a.model)
    elif a.auto:
        paths = resolve_visual(a.auto, mode='auto', provider=a.provider, count=a.count, out=a.out, api_key=a.api_key, model=a.model)
    else:
        ap.print_help()
        return

    for p in paths:
        print(p)


if __name__ == '__main__':
    main()
