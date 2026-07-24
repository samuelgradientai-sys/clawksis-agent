#!/usr/bin/env python3
"""Briefing IA — Noticias de IA recientes desde Google News RSS + Hacker News.
Run: python3 ~/.clawksis/scripts/fetch-ai-news.py
Used by: cron Briefing diario de IA (13:00 UTC)
Output: titulares con fuentes para que un agente formatee."""
import urllib.request, json, html, xml.etree.ElementTree as ET
from datetime import datetime, timezone

FECHA = datetime.now(timezone.utc).strftime("%d de %B de %Y")

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except:
        return ""

seen = set()
all_news = []

# Google News RSS
for q in ["artificial+intelligence+AI+news", "AI+model+release+launch+2026",
          "SpaceX+Cursor+AI+acquisition", "Anthropic+OpenAI+Google+AI",
          "inteligencia+artificial+noticias+2026"]:
    data = fetch(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en&date=1d")
    if not data: continue
    try:
        root = ET.fromstring(data)
        for item in root.findall('.//item'):
            t = html.unescape(item.findtext('title', '').strip())
            s = item.findtext('source', '') or 'Google News'
            d = item.findtext('pubDate', '')
            if t and t not in seen and len(t) > 20:
                seen.add(t); all_news.append((d, t, s))
    except: pass

# Hacker News
data = fetch(f"https://hn.algolia.com/api/v1/search?query=AI&tags=story&hitsPerPage=10&numericFilters=created_at_i>{int(datetime.now().timestamp())-172800}")
if data:
    try:
        for hit in json.loads(data).get("hits", []):
            t = hit.get("title", "")
            if t and t not in seen and len(t) > 15:
                seen.add(t); all_news.append(("", t, f"Hacker News (▲{hit.get('points',0)})"))
    except: pass

recent = [n for n in all_news if any(w in n[0].lower() for w in ["jun","may","2026"])][:12]
combined = (recent + [n for n in all_news if n not in recent])[:10]
if not combined:
    print(f"## Briefing IA — {FECHA}\n\nNo se encontraron noticias de hoy/ayer.")
    exit(0)

print(f"## Briefing IA — {FECHA}\n")
for d, t, s in combined:
    print(f"**{t}**\n   *{s}{' — '+d[:16] if d else ''}*\n")
print("---\n📡 Próximo briefing: mañana 13:00 UTC")
