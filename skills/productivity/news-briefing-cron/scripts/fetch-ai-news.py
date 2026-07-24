#!/usr/bin/env python3
"""Briefing IA — Noticias de IA recientes desde Google News RSS + Hacker News.
   Script para cron en modo script+agent (no_agent=false).
   El script recolecta, el agente formatea."""
import urllib.request, json, html, xml.etree.ElementTree as ET
from datetime import datetime, timezone

FECHA = datetime.now(timezone.utc).strftime("%d de %B de %Y")

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except:
        return ""

seen = set()
all_news = []

# Source 1: Google News RSS (multiple queries, last 24h)
queries = [
    "artificial+intelligence+AI+news",
    "AI+model+release+launch+2026",
    "SpaceX+Cursor+AI+acquisition",
    "Anthropic+OpenAI+Google+AI",
    "mini+PC+local+AI+model+2026",
    "local+AI+inference+mini+PC+LLM",
    "ejecutar+modelos+locales+mini+PC+2026",
    "inteligencia+artificial+noticias+2026",
]
for q in queries:
    data = fetch(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en&date=1d")
    if not data: continue
    try:
        root = ET.fromstring(data)
        for item in root.findall('.//item'):
            t = item.findtext('title', '').strip()
            s = item.findtext('source', '') or 'Google News'
            d = item.findtext('pubDate', '')
            t = html.unescape(t)
            if t and t not in seen and len(t) > 20:
                seen.add(t)
                all_news.append((d, t, s))
    except: pass

# Source 2: Hacker News (last 48h)
data = fetch(f"https://hn.algolia.com/api/v1/search?query=AI+artificial+intelligence&tags=story&hitsPerPage=10&numericFilters=created_at_i>{int(datetime.now().timestamp())-172800}")
if data:
    try:
        for hit in json.loads(data).get("hits", []):
            t = hit.get("title", "")
            if t and t not in seen and len(t) > 15:
                seen.add(t)
                p = hit.get("points", 0)
                all_news.append(("", t, f"Hacker News (▲{p})"))
    except: pass

# Output: raw news, newest first
recent = [n for n in all_news if any(w in n[0].lower() for w in ["jun", "may", "2026"])][:12]
rest = [n for n in all_news if n not in recent][:4]
combined = (recent + rest)[:10]

if not combined:
    print(f"## 🧠 Briefing IA — {FECHA}")
    print()
    print("No se encontraron noticias de hoy/ayer. Intenta más tarde.")
    exit(0)

for d, t, s in combined:
    ts = f" — {d[:16]}" if d else ""
    print(f"{t}|{s}{ts}")
