---
name: business-contact-scraping
description: Extract business contact data (phone, WhatsApp, email) from Latin American directories, Google Maps, and chain store locators for lead generation. Covers progressive multi-city collection, phone-number dedup, and mobile-only filtering for cold-calling campaigns.
version: 2
---

# Business Contact Scraping for Lead Generation

Trigger when the user asks to **find/extract contact numbers, WhatsApp, or email from businesses** in a specific sector (opticians, dentists, clinics, restaurants, etc.) for **cold calling, lead generation, or outreach**.

Also trigger on: "scrape contactos", "busca números", "lista de clientes", "lead generation", "directorio teléfonos".

## Workflow

### 1. Clarify scope
- **Sector:** What type of business? (ópticas, clínicas, restaurantes, etc.)
- **Geography:** City, department, or nationwide in Colombia (or other LatAm country)
- **Contact type:** Mobile only (+57 3xx), WhatsApp, or all phones?
- **Target quantity:** How many contacts do they want? (50, 100, 200+)

### 2. Source selection

| Source | Best for | Tool | Notes |
|--------|----------|------|-------|
| **Páginas Amarillas** (paginasamarillas.com.co) | Large cities, many results | `scrape(url, mode="stealthy")` | Best directory for Colombian businesses. Has `__NEXT_DATA__` with WhatsApp contacts. |
| **Chain store websites** | Multi-location businesses | `scrape(url, mode="stealthy")` | One page can yield 6-10+ phones across cities |
| **Google Maps** (unsigned) | Small/medium cities | `scrape(url, mode="stealthy")` | ~8 results per query. Good for cities not in PA. Use stealthy mode, NOT browser. |
| **Nexdu** (nexdu.com) | Alternative directory | `scrape(url, mode="stealthy")` | Some phone numbers visible |
| **Cybo** (cybo.com) | Alternative directory | `scrape(url, mode="stealthy")` | Often returns 404 — verify first |
| **Infoisinfo** (infoisinfo.com.co) | Alternative directory | `scrape(url, mode="stealthy")` | Phones behind JS "click to reveal" |

### 3. Páginas Amarillas pattern

Base URL: `https://www.paginasamarillas.com.co/{city}/servicios/{category}`

The city slug is lowercase without accents (e.g. `medellin`, `bogota`, `cali`). The category slug is plural (e.g. `opticas`, `clinicas`, `odontologos`).

**Stealthy scrape:** Returns clean text with business names, phone numbers, and "Whatsapp" tags next to mobile numbers.

**`__NEXT_DATA__` trick (WhatsApp-only):** Navigate with browser, then extract WhatsApp links from the embedded JSON:
```javascript
JSON.parse(document.querySelector('#__NEXT_DATA__').textContent)
  .props.pageProps.results
  .filter(r => r.contactMap?.WHATSAPP?.length)
  .map(r => ({
    name: r.name,
    phones: r.contactMap.WHATSAPP.map(w => w.replace('https://wa.me/', '+57 ')),
    city: r.mainAddress?.addressLocality
  }))
```

**Limitation:** Only first page (15 results) is in `__NEXT_DATA__`. Subsequent pages load via API — need `browser_click` on pagination buttons and re-extract from rendered DOM.

### 4. Google Maps (unsigned) — primary or fallback

Best technique — use the `scrape` tool with `mode="stealthy"` directly, NOT the browser tool:

```python
# ✅ Works for most cities (each call returns ~8 results)
city_url = f"https://www.google.com/maps/search/%C3%B3pticas+en+{city_url_fragment},+Colombia/"
# Use URL-encoded format: "ópticas+en+Bogotá" → "%C3%B3pticas+en+Bogot%C3%A1"
```

**Limitations confirmed in practice:**
- ~8 results per query max without signing in
- Bogotá specifically gets IP-blocked after 1 request (returns `ip_block` error, but still returns partial data)
- Some cities occasionally get IP-blocked (Pasto, Bogotá) — retry with slight URL variation
- Google's "You're seeing a limited view of Google Maps" banner is permanent without login
- The `scrape` tool's stealthy mode works for most Colombian cities (23/25 tested worked)
- ScrapeGraphAI **cannot** parse Google Maps — skip it

**Extracting data from the raw text output:**
The `scrape` tool returns a text block with business names, addresses, and phone numbers in a semi-structured format. Parse it with a Python script:

```python
import re, csv
text = result["content"]  # from scrape tool
# Pattern: Name followed by address line + phone line
entries = []
lines = text.strip().split('\n')
for i, line in enumerate(lines):
    # Look for phone numbers to identify business entries
    phone_match = re.search(r'\+57[\s\d]+', line)
    if phone_match and i > 0:
        name = lines[i-3].strip() if i >= 3 else ''
        address = lines[i-2].strip() if i >= 2 else ''
        phone = phone_match.group().strip()
        entries.append([name, phone, address, city])
```

**Filter chain stores OUT after extraction:**
The user may want only independent businesses, not chain franchises. Known chain keywords per sector:

| Sector | Chain keywords to filter |
|--------|--------------------------|
| Ópticas | `óptica alemana`, `óptica valle`, `opticalia`, `lafam`, `gmo`, `óptica colombiana` |
| (General) | Match against `name.lower()` and skip if any chain keyword is present |

Build a chain-keywords list per sector and filter before writing the final CSV.

**Output CSV format:**
```csv
Nombre,Teléfono,Dirección,Ciudad
"Optica Ejemplo",+57 300 1234567,Cra. 7 #22-11,Ibagué
```

### 5. User preference: Google Maps ONLY

Some users explicitly want **only Google Maps data** — no directories like Páginas Amarillas, Izi, Cylex, Infoisinfo, or Nexdu. This is because Google Maps:
- Has the most up-to-date phone numbers
- Shows actual physical stores (not directories of registered businesses)
- Avoids duplicate/outdated entries from directory aggregators
- Is the source the user trusts for cold-calling campaigns

When this preference is stated, **skip all directory sources** and only scrape Google Maps city by city.
Use the progressive multi-city approach (section 6 below) to reach 100+ contacts, since each Google Maps query returns only ~8 results.

### 6. Progressive collection (100+ contacts)

When the target is 100+ contacts across many cities:

**For Google Maps only** — scrape city by city directly (each call is fast):
```python
cities = ["Medellín", "Cali", "Barranquilla", ...]
for city in cities:
    # scrape with stealthy mode
    result = scrape(...)
    # parse contacts and append to CSV
# Dedup by phone number, not business name
# columns: Nombre, Teléfono, Dirección, Ciudad
```

**For directories** — use `delegate_task` with `["web", "terminal", "file"]` toolsets:
```python
# Each subagent covers 5-10 cities and appends to a shared CSV
# Dedup by phone number, not business name
# columns: business_name, phone, city, source
```

Build the CSV cumulatively — each subagent run reads existing, adds new, writes back.

### 7. Colombian phone numbers — patterns

```python
import re
# Mobile only: +57 3xx xxx xxxx
mobile = re.findall(r'\+57\s*3\d{2}\s*\d{3}\s*\d{4}', text)
# Landline: +57 60x/1xx xxx xxxx
landline = re.findall(r'\+57\s*[16]\d{2}\s*\d{3}\s*\d{4}', text)
# WhatsApp link: https://wa.me/57300XXXXXX
whatsapp = re.findall(r'wa\.me/(57\d+)', text)
```

### 8. Output format

```csv
business_name,phone,city,source
"Optica Ejemplo",+57 300 1234567,Bogotá,www.paginasamarillas.com.co
```

## Lead quality signals
- 🔥 **WhatsApp tag / WhatsApp link** — ready for cold messaging
- ✅ **Mobile (+57 3xx)** — direct line, likely WhatsApp
- ⚠️ **Landline (+57 60x/1xx)** — needs reception; lower conversion for cold calling

## CSV Cleaning — Phone/Address Column Swaps

Google Maps raw text output often has **phone numbers and addresses in swapped columns** after parsing. Common failure modes:

| Symptom | Likely cause |
|---------|-------------|
| Address field starts with `+57` or `57` | Phone landed in address column by regex |
| Phone field is >20 chars and doesn't start with `+` | Address text landed in phone column |
| Two consecutive address-like strings, no phone visible | Actual phone was in the previous entry's address field |

**Auto-detection and fix script pattern:**

```python
import csv, re

# Phase 1: detect and swap
for row in rows:
    name, phone, address, city = row
    # Phone in address column?
    if address.startswith('+57') or (address.startswith('57') and len(address) >= 10):
        phone, address = address, phone  # swap
    # Address in phone column?
    if phone and not phone.startswith('+') and not re.match(r'^57?\d{7,}', phone) and len(phone) > 10:
        if address.startswith('+57'):
            address, phone = phone, address  # swap back
        else:
            phone, address = '', phone  # phone is empty, address was in phone column
    # Add country prefix
    if phone and phone.startswith('57') and not phone.startswith('+'):
        phone = '+' + phone

# Phase 2: sanity check — flag remaining anomalies
for r in rows:
    if r[1] and len(r[1]) > 5 and not r[1].startswith('+') and not r[1].startswith('57'):
        print(f"Flagged: {r[0]} | tel={r[1][:30]}")
    if r[2] and (r[2].startswith('+57') or (r[2].startswith('57') and len(r[2]) >= 10)):
        print(f"Flagged: {r[0]} | addr has phone={r[2][:30]}")
```

**Real-world stats:** In a 249-contact scrape, 89 entries (~36%) had swapped phone/address columns. The auto-fix script caught all of them. 3 entries had genuinely missing phones (no phone in either column) — those need manual review.

## OCR Fallback for Image Analysis

When the active model does not support vision (image_url format rejected, e.g. DeepSeek V4 Flash, x-ai/grok-4.3), use **tesseract OCR** as a fallback to extract text from images.

**Setup (one-time):**
```bash
uv pip install pytesseract Pillow
```

**Usage:**
```python
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

img = Image.open('/path/to/image.jpg')
enhancer = ImageEnhance.Contrast(img)
img = enhancer.enhance(2.0)
img = img.convert('L')
img = img.filter(ImageFilter.SHARPEN)

text = pytesseract.image_to_string(img, lang='spa+eng', config='--psm 6')
print(text)
```

**Limitations:**
- Only extracts **text** — no layout analysis, no image understanding
- Quality depends heavily on image resolution and contrast
- Screenshots work better than photos
- Not a replacement for a real vision model — use only as fallback

## Pitfalls
- Páginas Amarillas blocks direct HTTP (curl, Python requests) — always use `scrape` stealthy mode or browser
- PA pagination is broken — `?page=N` returns same results. Scrape by city URL or click through with browser
- Only ~5-7% of directory businesses list mobile numbers. Set expectations accordingly.
- Google Maps (unsigned) shows ~8 results per query, then IP may get flagged after ~6-8 rapid queries — add delays between cities
- **Chain store filtering is critical** for cold-calling campaigns — build a sector-specific chain keyword list and filter by `name.lower()` before writing the final CSV
- Bogotá and Pasto are the most likely cities to get IP-blocked on Google Maps — retry with different URL variations or accept partial results
- **`wait_selector` on the `scrape` tool BREAKS Google Maps scraping** — the limited-view banner never fires the selector. NEVER pass `wait_selector` for a Google Maps URL. Use `mode="stealthy"` and `format="text"` only.
- **City-label gotcha in scripts**: When you hardcode city names in comments above data blocks in Python (e.g. `=== Pasto (las que no teníamos) ===`), the parser picks up the parenthetical comment as part of the city name. Use clean labels: `=== Pasto ===`
- **Dedup strategy when merging old + new data**: Use `(name_lower, phone)` tuple as the dict key for O(1) dedup. Some cities appear in both old and new scrapes. Write merged data back to the same CSV.
- **Scalability ceiling**: ~250 contacts across 34 cities is the practical max from Google Maps unsigned. Each city yields ~5-11 contacts. To go beyond, you need a residential proxy or a signed-in Google session.
- **ScrapeGraphAI cannot parse Google Maps** — the structured extraction always fails. Skip it; use the raw text from `scrape` tool with `mode="stealthy"` and parse with Python regex instead.
- Dedup by **phone number**, not business name — same chain in different cities = different numbers
- Empresite has addresses but NO phone numbers — skip it
- Cybo URLs often return 404 for LatAm — verify first
- Search engine results for Colombian business directories are unreliable — scrape directories directly
- Some directories mix unrelated businesses in results — filter by name/business type relevance
- Chain store locators are goldmines: one page can yield 6-10+ phones across multiple cities
- Use the `scrapling-official` skill for the actual scraping tool commands and Python API
