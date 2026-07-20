# Scraping Latin American Business Directories for Lead Generation

Use when the user asks to **find and extract contact data (phone, email, WhatsApp) from business directories** like Páginas Amarillas, Nexdu, Infoisinfo, Cybo, or similar platforms in Latin America.

## Tool choice

| Source | Best tool | Notes |
|--------|-----------|-------|
| **Páginas Amarillas** (paginasamarillas.com.co) | `scrape(url, mode="stealthy")` | Clean text with names and phones |
| **Nexdu** (nexdu.com) | `scrape(url, mode="stealthy")` | Phones visible on listing |
| **Infoisinfo** (infoisinfo.com.co) | `scrape(url, mode="stealthy")` | Phones on individual detail pages |
| **Cybo** (cybo.com) | `scrape(url, mode="stealthy")` | Listing + phones in one page |
| **Chain stores** (store locators) | `scrape(url, mode="stealthy")` | Often all locations + phones on one page |

## Colombian phone extraction

```python
import re

# Mobile: +57 3xx xxx xxxx
mobile = re.findall(r"\+57\s*3\d{2}\s*\d{3}\s*\d{4}", text)
# Landline
landline = re.findall(r"\+57\s*[16]\d{2}\s*\d{3}\s*\d{4}", text)
```

## Páginas Amarillas pattern
URL: `https://www.paginasamarillas.com.co/{city}/servicios/{category}`

Returns business name, phone, "Whatsapp" tag near mobile numbers. Pagination broken after page 1 — scrape by different city URLs instead.

## Lead quality signals
- 🔥 **WhatsApp tag next to number** — ready for cold messaging
- ✅ **Mobile (+57 3xx)** — direct line
- ⚠️ **Landline (+57 60x/1xx)** — may need reception

## Pitfalls
- Páginas Amarillas pagination returns same results for pages 2+ — scrape by city, not page
- Empresite has addresses but no phone numbers
- Some directories mix unrelated businesses — filter by name relevance
- Chain store locators (e.g. Óptica Iris, Clínica de Ojos) are goldmines — one page, many phones
- Avoid scraping Google Maps directly — rate-limited without residential proxy
