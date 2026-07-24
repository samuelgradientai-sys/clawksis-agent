# Google Maps Business Contact Scraping

## Technique: City-by-city with `scrape` stealthy mode

Discovered 2026-07-16 while scraping ~160 ópticas from 23 Colombian cities.

### Working approach

```python
from clawk_tools import scrape

# For each city, URL-encode the search term
city = "Medellín"
url = "https://www.google.com/maps/search/%C3%B3pticas+en+" + urllib.parse.quote(city) + ",+Colombia/"

result = scrape(url=url, mode="stealthy", format="text")
# result["content"] contains the raw text
```

### What the raw text looks like

```
Óptica Moderna
Óptica Moderna
Optician

Cra. 47 #54-70
Closed
· Opens 8:30 AM Fri
+57 311 7057231
```

### Extraction pattern (two approaches)

#### Approach A: Positional (fragile)
The structure is roughly:
- **Line N-3**: Business name (appears twice; use first occurrence)
- **Line N-2**: Address
- **Line N-1**: Business hours / status
- **Line N**: Phone number

#### Approach B: Regex scan (recommended)
Scan the entire text for Colombian phone patterns, then grab the surrounding context:

```python
import re

def parse_maps_text(text, city_name):
    entries = []
    lines = text.strip().split('\n')
    for i, line in enumerate(lines):
        mobile_match = re.findall(r'\+57\s*3\d{2}\s*\d{3}\s*\d{4}', line)
        landline_match = re.findall(r'\+57\s*[16]\d{2}\s*\d{3}\s*\d{4}', line)
        phones = mobile_match + landline_match
        if phones and i >= 2:
            name = lines[i-3].strip() if i >= 3 else lines[i-2].strip()
            address = lines[i-2].strip() if i >= 2 else ''
            address = re.sub(r'\uE934', '', address).strip()  # wheelchair icon
            if address == name:
                address = lines[i-4].strip() if i >= 4 else ''
            for phone in phones:
                phone_clean = phone.replace(' ', '').strip()
                entries.append([name, phone_clean, address, city_name])
    return entries
```

Then deduplicate by (name_lower, phone) tuple before writing the CSV.

### Cities that worked (34 cities, expanded 2026-07-17)

| Status | Cities |
|--------|--------|
| ✅ Works | Medellín, Cali, Barranquilla, Bucaramanga, Cartagena, Ibagué, Pereira, Manizales, Santa Marta, Villavicencio, Cúcuta, Neiva, Montería, Sincelejo, Armenia, Popayán, Valledupar, Soacha, Soledad, Floridablanca, Tunja, Zipaquirá, Sogamoso, Tuluá, Rionegro, Envigado, Itagüí, Dosquebradas, Barrancabermeja, Apartadó, Ocaña |
| ⚠️ IP block (partial data still returned) | Bogotá, Pasto, Buga |

### Top coverage example

| City | Contacts |
|------|----------|
| Sincelejo | 13 (7 old + 7 new, deduped) |
| Zipaquirá | 11 |
| Pasto | 9 |
| Most others | 5-8 each |

### Limitations and pitfalls
- **~8 results per city max** (Google's unsigned limit). This is the hard cap — do NOT try to scroll or paginate.
- **`wait_selector` BREAKS the scrape** — Google Maps never fires the wait selector because of the limited-view banner. NEVER pass `wait_selector` for Google Maps URLs.
- IP gets flagged after ~6-8 rapid requests — add `time.sleep(2)` between cities.
- Scrolling in browser does NOT load more results without sign-in.
- ScrapeGraphAI returns empty for Google Maps — use the `scrape` tool instead.
- **City-label gotcha**: When hardcoding city names above data blocks in scripts, a comment like `=== Pasto (las que no teníamos) ===` becomes a real city name in the CSV. Use clean labels only: `=== Pasto ===`.
- Residential proxy (`SCRAPLING_PROXY`) or a signed-in session is required for full results beyond ~8 per city.

### Chain stores to filter out (ópticas sector)

```python
chains = [
    'optica alemana', 'óptica alemana',
    'optica valle', 'óptica valle',
    'opticalia', 'lafam', 'gmo',
    'optica colombiana', 'óptica colombiana',
    'optikaf', 'pracso',
    'optica italiana', 'óptica italiana',
    'univer', 'zeiss vision', 'naratodo',
    'santa lucia', 'óptica santa lucía'
]
skip = any(c in name.lower() for c in chains)
```
