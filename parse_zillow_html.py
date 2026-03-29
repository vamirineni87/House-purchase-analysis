"""Parse the captured Zillow HTML to find ALL available data using correct DOM patterns."""

import re
import json

with open("zillowScrap.txt", "r", encoding="utf-8") as f:
    content = f.read()

print(f"File: {len(content):,} chars")
print()

# =============================================
# 1. Find ALL data-testid elements (this tells us what Zillow exposes)
# =============================================
testids = re.findall(r'data-testid="([^"]+)"', content)
unique_testids = sorted(set(testids))
print(f"=== ALL data-testid values ({len(unique_testids)}) ===")
for tid in unique_testids:
    print(f"  {tid}")

# =============================================
# 2. Extract bed/bath/sqft from data-testid containers
# =============================================
print("\n=== BED / BATH / SQFT ===")
# Pattern: value span followed by label span within fact-container
facts = re.findall(
    r'data-testid="bed-bath-sqft-fact-container"[^>]*>.*?'
    r'<span[^>]*>([\d,\.]+)</span>\s*<span[^>]*>(\w+)</span>',
    content,
)
for val, label in facts:
    print(f"  {label}: {val}")

# =============================================
# 3. Extract price
# =============================================
print("\n=== PRICE ===")
# Try multiple patterns
for pat in [
    r'data-testid="price"[^>]*>[^$]*\$([\d,]+)',
    r'"price":\s*"?\$?([\d,]+)',
    r'class="[^"]*price[^"]*"[^>]*>[^$]*\$([\d,]+)',
]:
    m = re.findall(pat, content, re.IGNORECASE)
    if m:
        print(f"  pattern matched: {list(set(m))[:5]}")

# =============================================
# 4. Extract all facts/features sections
# =============================================
print("\n=== FACTS & FEATURES ===")
# Zillow has fact-label + fact-value pairs
fact_pairs = re.findall(
    r'<span[^>]*>([^<]{2,50})</span>\s*(?:</[^>]+>\s*)*<span[^>]*>([^<]{1,100})</span>',
    content,
)
# Filter for property-related facts
property_keywords = [
    "year", "built", "lot", "hoa", "garage", "parking", "heating",
    "cooling", "roof", "flooring", "appliance", "basement", "stories",
    "style", "type", "material", "sewer", "water", "zoning",
    "fireplace", "laundry", "school", "district",
]
for label, value in fact_pairs:
    label_clean = label.strip().lower()
    if any(kw in label_clean for kw in property_keywords):
        print(f"  {label.strip()}: {value.strip()}")

# =============================================
# 5. Search for specific data patterns in raw text
# =============================================
print("\n=== TEXT PATTERNS ===")
patterns = [
    (r"Built in (\d{4})", "year_built"),
    (r"Year [Bb]uilt[:\s]*(\d{4})", "year_built_alt"),
    (r"(\d[\d,]*)\s*sqft", "sqft"),
    (r"([\d\.]+)\s*[Aa]cres?", "lot_acres"),
    (r"Lot[:\s]*([\d,]+)\s*sqft", "lot_sqft"),
    (r"HOA[:\s]*\$\s*([\d,]+)", "hoa"),
    (r"HOAFee=(\d+)", "hoa_url_param"),
    (r"(\d+)\s*[Dd]ays?\s*on\s*[Zz]illow", "dom"),
    (r"MLS\s*#?\s*:?\s*([A-Z]{2,}\d+)", "mls"),
    (r"[Pp]arcel\s*#?\s*:?\s*([\d\-]+)", "parcel"),
    (r"[Gg]arage\s*[Ss]paces?\s*:?\s*(\d+)", "garage"),
    (r"(\d+)\s*[Ss]tories", "stories"),
    (r"[Ff]ireplace", "has_fireplace"),
    (r"[Bb]asement", "has_basement"),
    (r"[Cc]entral\s*(?:A/?C|[Aa]ir)", "has_central_ac"),
    (r"[Hh]eat(?:ing)?\s*(?:[Tt]ype)?\s*:?\s*([^<,]{3,30})", "heating"),
    (r"[Cc]ool(?:ing)?\s*(?:[Tt]ype)?\s*:?\s*([^<,]{3,30})", "cooling"),
    (r"[Rr]oof\s*(?:[Tt]ype)?\s*:?\s*([^<,]{3,30})", "roof_type"),
    (r"[Ff]loor(?:ing)?\s*:?\s*([^<,]{3,30})", "flooring"),
]
for pat, name in patterns:
    matches = re.findall(pat, content)
    if matches:
        unique = list(set(matches))[:3]
        print(f"  {name}: {unique}")

# =============================================
# 6. JSON-LD extraction
# =============================================
print("\n=== JSON-LD ===")
ld_blocks = re.findall(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    content,
    re.DOTALL,
)
for i, block in enumerate(ld_blocks):
    try:
        data = json.loads(block)
        t = data.get("@type", "unknown")
        if isinstance(t, list):
            t = t[0]
        if t in ("RealEstateListing", "Product", "Event"):
            print(f"  Block {i+1} ({t}):")
            # Flatten and print key fields
            if "offers" in data:
                offers = data["offers"]
                print(f"    price: ${offers.get('price', 'N/A'):,}")
                item = offers.get("itemOffered", {})
                print(f"    type: {item.get('@type', 'N/A')}")
                fs = item.get("floorSize", {})
                print(f"    sqft: {fs.get('value', 'N/A')}")
                print(f"    beds: {item.get('numberOfBedrooms', 'N/A')}")
                addr = item.get("address", {})
                print(f"    address: {addr.get('streetAddress', '')} {addr.get('addressLocality', '')} {addr.get('addressRegion', '')} {addr.get('postalCode', '')}")
                geo = item.get("geo", {})
                print(f"    lat/lon: {geo.get('latitude', '')}, {geo.get('longitude', '')}")
            if "performer" in data:
                print(f"    agent/brokerage: {data['performer']}")
            if "startDate" in data:
                print(f"    open_house: {data['startDate']} to {data.get('endDate', '')}")
    except json.JSONDecodeError:
        pass

# =============================================
# 7. Search for price history / tax history sections
# =============================================
print("\n=== PRICE/TAX HISTORY PATTERNS ===")
# Look for date+price combos
date_price = re.findall(r"(\d{1,2}/\d{1,2}/\d{4})[^$]*?\$([\d,]+)", content[:500000])
if date_price:
    seen = set()
    for date, price in date_price[:20]:
        key = f"{date}|{price}"
        if key not in seen:
            seen.add(key)
            print(f"  {date}: ${price}")

# Tax years + amounts
tax_patterns = re.findall(r"(20[12]\d)\s*(?:</[^>]+>\s*)*(?:<[^>]+>\s*)*\$([\d,]+)", content[:500000])
if tax_patterns:
    seen = set()
    for year, amount in tax_patterns[:10]:
        key = f"{year}|{amount}"
        if key not in seen:
            seen.add(key)
            print(f"  Tax {year}: ${amount}")

# =============================================
# 8. School info
# =============================================
print("\n=== SCHOOLS ===")
school_patterns = re.findall(
    r"(Buffalo Trail|Willard|Lightridge|Stone Hill|Liberty|Freedom|Briar Woods|Rock Ridge)[^<]{0,100}",
    content,
    re.IGNORECASE,
)
seen = set()
for s in school_patterns[:10]:
    clean = s.strip()[:60]
    if clean not in seen:
        seen.add(clean)
        print(f"  {clean}")

# =============================================
# 9. Walk/Transit/Bike scores
# =============================================
print("\n=== SCORES ===")
for pat, name in [
    (r"[Ww]alk\s*[Ss]core[^<\d]*(\d+)", "walk_score"),
    (r"[Tt]ransit\s*[Ss]core[^<\d]*(\d+)", "transit_score"),
    (r"[Bb]ike\s*[Ss]core[^<\d]*(\d+)", "bike_score"),
]:
    m = re.findall(pat, content)
    if m:
        print(f"  {name}: {list(set(m))}")

print("\n=== DONE ===")
