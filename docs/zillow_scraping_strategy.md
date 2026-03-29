# Zillow Scraping Strategy

## Architecture

The ZillowScraper (`src/pipa/clients/scrapers/zillow.py`, v2.0.0) uses a 3-layer
extraction approach. It renders the real page with Playwright (non-headless),
intercepts the GraphQL API responses the browser naturally makes, and falls back
to HTML parsing for any missing fields.

**GraphQL cannot be called directly** — it requires PerimeterX cookies and session
tokens that are only generated during a real browser page load. Calling `/graphql/`
with httpx would be blocked immediately.

## Data Extraction Layers (from most reliable to least)

### Layer 1 (PRIMARY): GraphQL Interception

The browser makes internal calls to `/graphql/?zpid={zpid}` during page render.
We intercept these responses — they contain **all** structured property data
(325k+ chars of clean JSON). This is the most reliable source.

**Endpoint pattern:** `https://www.zillow.com/graphql/?zpid={zpid}&platform=DESKTOP_WEB&...`

**Fields available (confirmed from real scrape of 42580 Deer Isle Dr):**
- price, bedrooms, bathrooms (full + half), livingArea, yearBuilt
- hoaFee, zestimate, rentZestimate
- taxAnnualAmount, taxAssessedValue, taxAssessedYear
- daysOnZillow, homeStatus, homeType, isNewConstruction
- lotSize, lotAreaValue (acres), parcelId
- county, latitude, longitude, streetAddress, city, state, zipcode
- mlsId, propertyTaxRate, timeOnZillow
- pageViewCount, favoriteCount
- brokerageName, agentName, agentPhoneNumber
- Full priceHistory array (dates, prices, events — e.g. Listed, Price change, Sold)
- Full taxHistory array (year, taxPaid, assessedValue)
- Schools with name, rating, distance, level
- Photo URLs
- Full description

### Layer 2: JSON-LD (embedded in HTML, always present, no CAPTCHA risk)
Zillow embeds `<script type="application/ld+json">` with structured data:

```json
{
  "@type": ["RealEstateListing", "Product"],
  "offers": {
    "price": 1367000,
    "priceCurrency": "USD",
    "itemOffered": {
      "@type": "SingleFamilyResidence",
      "floorSize": {"value": 6045},
      "numberOfBedrooms": 6,
      "address": {
        "streetAddress": "42580 Deer Isle Dr",
        "addressLocality": "Chantilly",
        "addressRegion": "VA",
        "postalCode": "20152"
      },
      "geo": {"latitude": 38.87491, "longitude": -77.53065}
    }
  }
}
```

Also includes open house events with dates/times and listing agent (brokerage).

**Fields available:** price, sqft, beds, address, lat/lon, brokerage name, open house schedule.
**Fields NOT available:** baths, year_built, HOA, zestimate, tax, DOM, lot size, parcel.

### Layer 2: HTML DOM Elements + URL Params (in rendered HTML)
Zillow uses `data-testid` attributes for structured content:

```html
<!-- Beds/Baths/Sqft: data-testid="bed-bath-sqft-facts" -->
<div data-testid="bed-bath-sqft-facts">
  <div data-testid="bed-bath-sqft-fact-container">
    <span class="...ValueText...">6</span>
    <span class="...DescriptionText...">beds</span>
  </div>
  <div data-testid="bed-bath-sqft-fact-container">
    <span class="...ValueText...">5</span>
    <span class="...DescriptionText...">baths</span>
  </div>
  <div data-testid="bed-bath-sqft-fact-container">
    <span class="...ValueText...">6,045</span>
    <span class="...DescriptionText...">sqft</span>
  </div>
</div>

<!-- Price: data-testid="price" -->
<span data-testid="price">$1,367,000</span>
```

**Key CSS selectors:**
- `[data-testid="bed-bath-sqft-facts"] [data-testid="bed-bath-sqft-fact-container"]` — iterate children for beds/baths/sqft
- `[data-testid="price"]` — list price
- `HOAFee=(\d+)` in URL params within the page HTML — HOA monthly fee

**Additional text patterns:**
- `Built in (\d{4})` or `Year built.*?(\d{4})` — year built
- MLS number in text: `VALO2117592`
- School names: Buffalo Trail, Willard, Lightridge
- Property type: `Single Family`

**Fields available:** price, beds, baths, sqft, year_built, MLS, HOA (URL param), schools, property type.
**Fields NOT available:** zestimate, rent estimate, full tax details, lot size, parcel, DOM.

### Layer 3: GraphQL API Interception (requires JS execution, CAPTCHA risk)
Zillow's page makes internal GraphQL calls to `/graphql/?zpid={zpid}` after rendering.
This endpoint returns the **complete** property data (325k+ chars).

**Endpoint:** `https://www.zillow.com/graphql/?zpid={zpid}&platform=DESKTOP_WEB&...`

**Fields available (confirmed):**
- bedrooms, bathrooms, livingArea (sqft), yearBuilt
- hoaFee, zestimate, rentZestimate
- taxAnnualAmount, taxAssessedValue
- daysOnZillow, homeStatus, homeType
- lotSize, parcelId
- county, latitude, longitude
- Full price history, tax history
- School details with ratings
- Walk/transit/bike scores
- Description, listing agent, photos

**This is the goldmine** but requires:
1. Full browser rendering (Playwright)
2. Passing PerimeterX CAPTCHA if triggered
3. Waiting for JS to execute and make the GraphQL calls

## CAPTCHA: PerimeterX "Press & Hold"

### Detection
- Located inside an iframe (`about:blank` or captcha-specific URL)
- Element: `#px-captcha` inside the iframe
- Full-page overlay that blocks content loading

### Bypass (confirmed working)
1. Find `#px-captcha` element inside iframe frames
2. Get bounding box (should be ~530x100, NOT full-page)
3. Mouse move to center with human-like approach (small movements)
4. `page.mouse.down()` — hold for 10-12 seconds
5. `page.mouse.up()` — release
6. Wait 5-10s for page to reload with content
7. May need 2-3 attempts

### Anti-detection measures
- Launch with `--disable-blink-features=AutomationControlled`
- Override `navigator.webdriver` to `undefined`
- Use realistic user agent string
- Use full viewport (1920x1080)
- Non-headless browser (headless gets blocked more often)

### CAPTCHA frequency
- First visit in a session: sometimes no CAPTCHA
- Repeated visits: CAPTCHA appears more often
- Fresh browser context helps avoid CAPTCHA

## Recommended Extraction Order

1. **Always start with JSON-LD** — guaranteed, no JS needed
2. **Parse HTML text** for year_built, MLS, HOA, schools
3. **If GraphQL data captured** (from response interception) — use it for everything else
4. **If CAPTCHA blocked GraphQL** — fall back to Layer 1+2 data + county enrichment

## Comparison: GraphQL vs HTML vs Coldwell Banker

| Field | JSON-LD | HTML DOM | GraphQL | Coldwell Banker |
|---|---|---|---|---|
| Price | Yes | Yes (data-testid) | Yes | Yes |
| Beds | Yes | Yes (data-testid) | Yes | Yes |
| Baths | - | Yes (data-testid) | Yes | Yes |
| Sqft | Yes | Yes (data-testid) | Yes | Yes |
| Year Built | - | Yes (text) | Yes | Yes |
| HOA | - | Yes (URL param) | Yes | Yes |
| Zestimate | - | - | Yes | - |
| Rent Zestimate | - | - | Yes | - |
| Annual Tax | - | - | Yes | Yes |
| Tax Assessed | - | - | Yes | Yes |
| DOM | - | - | Yes | - |
| Lot Size | - | - | Yes | Yes |
| Parcel # | - | - | Yes | - |
| MLS # | - | Yes (text) | - | Yes |
| Schools | - | Names (text) | Full details | Yes |
| Walk Score | - | - | Yes | - |
| Description | - | - | Yes | Yes |
| Photos | - | - | Yes | Yes |
| Price History | - | Limited | Full | Partial |
| Tax History | - | Years only | Full | Partial |
| Agent | Brokerage | - | Full | Yes |
| Open House | Yes | - | - | - |

## Answer: Should we call GraphQL directly?

**NO — calling GraphQL blindly will get blocked faster than rendering the page.**

Zillow's GraphQL endpoint requires:
- Valid session cookies (set during page load)
- PerimeterX tokens (generated by their anti-bot JS)
- Proper referrer and origin headers
- Request context that matches a real browser session

Calling `/graphql/` directly without a browser session would be immediately flagged.

**Best approach: render the page with Playwright, intercept the GraphQL response.**
The browser naturally makes the GraphQL call as part of page rendering. We just listen for it.

## Fallback Strategy

If Zillow scraping fails entirely:
1. **Coldwell Banker** — full MLS data, no CAPTCHA, no anti-bot
2. **Compass, RE/MAX, Movoto** — same MLS data, different sites
3. **Realtor.com** — may require similar Playwright approach
4. **Manual entry** — user pastes key details
5. **County records** — parcel/assessment/permit data independent of listings
