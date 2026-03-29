"""Extract EVERY piece of data from captured Zillow HTML.

Saves structured output to zillow_extracted_42580_deer_isle.json
"""

import re
import json

with open("zillowScrap.txt", "r", encoding="utf-8") as f:
    content = f.read()

result = {
    "_source": "zillow",
    "_url": "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/",
    "_extracted_from": "zillowScrap.txt",
    "_file_size": len(content),
}

# =============================================
# 1. JSON-LD structured data
# =============================================
ld_blocks = re.findall(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    content, re.DOTALL,
)
json_ld = []
for block in ld_blocks:
    try:
        json_ld.append(json.loads(block))
    except json.JSONDecodeError:
        pass
result["json_ld"] = json_ld

# =============================================
# 2. Bed / Bath / Sqft from data-testid
# =============================================
facts = re.findall(
    r'data-testid="bed-bath-sqft-fact-container"[^>]*>.*?'
    r'<span[^>]*>([\d,\.]+)</span>\s*<span[^>]*>(\w+)</span>',
    content,
)
bed_bath_sqft = {label: val for val, label in facts}
result["bed_bath_sqft"] = bed_bath_sqft

# =============================================
# 3. Price from data-testid
# =============================================
price_match = re.findall(r'data-testid="price"[^>]*>[^$]*\$([\d,]+)', content)
result["list_price"] = price_match[0] if price_match else None

# =============================================
# 4. ALL data-testid elements with their text content
# =============================================
testid_content = {}
# Get content near each data-testid
for m in re.finditer(r'data-testid="([^"]+)"', content):
    tid = m.group(1)
    # Get the next 500 chars after this testid
    snippet = content[m.end():m.end() + 500]
    # Extract visible text from the snippet (strip tags)
    text = re.sub(r'<[^>]+>', '|', snippet)
    text = re.sub(r'\|+', '|', text).strip('|').strip()
    # Only keep if there's meaningful text
    if text and len(text) > 1 and not text.startswith('{') and len(text) < 300:
        if tid not in testid_content:
            testid_content[tid] = text[:200]
result["data_testid_contents"] = testid_content

# =============================================
# 5. Zestimate
# =============================================
zest_patterns = [
    r'data-testid="primary-zestimate"[^>]*>.*?<span[^>]*>\$?([\d,]+)',
    r'data-testid="zest-overview-flex"[^>]*>.*?\$([\d,]+)',
    r'"zestimate"[:\s]*(\d+)',
    r'Zestimate[^$]*\$([\d,]+)',
]
for pat in zest_patterns:
    m = re.search(pat, content, re.DOTALL)
    if m:
        result["zestimate"] = m.group(1)
        break

# Rent zestimate
rent_zest = re.findall(r'data-testid="rent-zestimate"[^>]*>.*?\$([\d,]+)', content, re.DOTALL)
if not rent_zest:
    rent_zest = re.findall(r'"rentZestimate"[:\s]*(\d+)', content)
if rent_zest:
    result["rent_zestimate"] = rent_zest[0]

# =============================================
# 6. Full description
# =============================================
desc_match = re.search(
    r'data-testid="description"[^>]*>(.*?)</div>',
    content, re.DOTALL,
)
if desc_match:
    desc_html = desc_match.group(1)
    desc_text = re.sub(r'<[^>]+>', ' ', desc_html).strip()
    desc_text = re.sub(r'\s+', ' ', desc_text)
    result["description"] = desc_text

# Also try the JSON version
desc_json = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', content)
if desc_json:
    desc_decoded = desc_json.group(1).replace("\\n", "\n").replace("\\u0027", "'").replace('\\"', '"')
    result["description_full"] = desc_decoded

# =============================================
# 7. Price history (full)
# =============================================
# Extract all date + price + event combinations
# Zillow renders these in table rows with data-testid="data-price-row"
price_rows = re.findall(
    r'data-testid="data-price-row"(.*?)(?=data-testid="data-price-row"|</table|$)',
    content, re.DOTALL,
)
price_history = []
for row in price_rows:
    date = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', row)
    price = re.search(r'\$([\d,]+)', row)
    event = re.search(r'(Listed|Sold|Price change|Pending|Contingent|Removed|Relisted)', row, re.IGNORECASE)
    if date:
        entry = {"date": date.group(1)}
        if price:
            entry["price"] = price.group(1)
        if event:
            entry["event"] = event.group(1)
        price_history.append(entry)

# Also try the broader pattern for any date+price combos in the history section
if not price_history:
    # Find all date+price near each other
    all_date_price = re.findall(
        r'(\d{1,2}/\d{1,2}/\d{4})[^$]{0,200}?\$([\d,]+)',
        content[:600000],
    )
    seen = set()
    for date, price in all_date_price:
        key = f"{date}|{price}"
        if key not in seen:
            seen.add(key)
            price_history.append({"date": date, "price": price})

result["price_history"] = price_history

# =============================================
# 8. Tax history (full)
# =============================================
# Find tax-money-cell entries
tax_cells = re.findall(
    r'data-testid="tax-money-cell"[^>]*>(.*?)(?=data-testid="tax-money-cell"|</table|$)',
    content, re.DOTALL,
)
tax_history = []

# Broader approach: find year + dollar amount patterns near "tax"
# Look for the tax history table section
tax_section = re.search(r'(?:tax|Tax)\s*(?:history|History)(.*?)(?:Price|price|Neighborhood|neighborhood|Similar|similar)', content, re.DOTALL)
if tax_section:
    section = tax_section.group(1)
    years = re.findall(r'(20[12]\d)', section)
    amounts = re.findall(r'\$([\d,]+)', section)
    # Pair them up
    for i in range(min(len(years), len(amounts))):
        tax_history.append({"year": years[i], "amount": amounts[i]})

# Also look for assessment values
tax_assessed = re.findall(r'(20[12]\d)[^$]{0,50}?\$([\d,]+)[^$]{0,50}?\$([\d,]+)', content[:600000])
if tax_assessed:
    result["tax_assessment_raw"] = [
        {"year": y, "value1": v1, "value2": v2}
        for y, v1, v2 in tax_assessed[:10]
    ]

result["tax_history"] = tax_history

# =============================================
# 9. Facts and features (full extraction)
# =============================================
# Find all fact-category sections
fact_categories = re.findall(
    r'data-testid="fact-category"[^>]*>(.*?)(?=data-testid="fact-category"|data-testid="facts-and-features-wrapper-footer"|$)',
    content, re.DOTALL,
)
facts_and_features = {}
for cat_html in fact_categories:
    # Get category name
    cat_name = re.search(r'<h[56][^>]*>([^<]+)</h', cat_html)
    if cat_name:
        cat = cat_name.group(1).strip()
    else:
        cat = "Unknown"

    # Get all fact items within this category
    items = re.findall(r'<li[^>]*>(.*?)</li>', cat_html, re.DOTALL)
    fact_list = []
    for item in items:
        text = re.sub(r'<[^>]+>', ' ', item).strip()
        text = re.sub(r'\s+', ' ', text)
        if text and len(text) > 2:
            fact_list.append(text)

    if fact_list:
        facts_and_features[cat] = fact_list

result["facts_and_features"] = facts_and_features

# =============================================
# 10. Schools
# =============================================
schools = []
for level in ["Elementary", "Middle", "High", "District"]:
    school_section = re.search(
        rf'data-testid="school-listing-{level}"(.*?)(?=data-testid="school-listing-|$)',
        content, re.DOTALL,
    )
    if school_section:
        section = school_section.group(1)
        name = re.search(r'<a[^>]*>([^<]+)</a>', section)
        rating = re.search(r'(\d+)\s*/\s*10', section)
        distance = re.search(r'([\d\.]+)\s*mi', section)
        grades = re.search(r'Grades?\s*:?\s*([^<]+)', section)
        school = {"level": level}
        if name:
            school["name"] = name.group(1).strip()
        if rating:
            school["rating"] = rating.group(1)
        if distance:
            school["distance_mi"] = distance.group(1)
        if grades:
            school["grades"] = grades.group(1).strip()
        schools.append(school)

result["schools"] = schools

# =============================================
# 11. Walk/Transit/Bike scores
# =============================================
scores = {}
for pat, name in [
    (r"[Ww]alk\s*[Ss]core[^<\d]{0,30}(\d+)", "walk_score"),
    (r"[Tt]ransit\s*[Ss]core[^<\d]{0,30}(\d+)", "transit_score"),
    (r"[Bb]ike\s*[Ss]core[^<\d]{0,30}(\d+)", "bike_score"),
]:
    m = re.search(pat, content)
    if m:
        scores[name] = int(m.group(1))
result["scores"] = scores

# =============================================
# 12. Listing agent / attribution
# =============================================
agent_section = re.search(
    r'data-testid="attribution-LISTING_AGENT"(.*?)(?=data-testid="attribution-|$)',
    content, re.DOTALL,
)
if agent_section:
    agent_text = re.sub(r'<[^>]+>', '|', agent_section.group(1))
    agent_text = re.sub(r'\|+', '|', agent_text).strip('|')
    result["listing_agent_raw"] = agent_text[:300]

broker_section = re.search(
    r'data-testid="attribution-BROKER"(.*?)(?=data-testid="|$)',
    content, re.DOTALL,
)
if broker_section:
    broker_text = re.sub(r'<[^>]+>', '|', broker_section.group(1))
    broker_text = re.sub(r'\|+', '|', broker_text).strip('|')
    result["broker_raw"] = broker_text[:300]

# =============================================
# 13. Specific text-based extractions
# =============================================
text_fields = {}
for pat, name in [
    (r"Built in (\d{4})", "year_built"),
    (r"Year [Bb]uilt[:\s]*(\d{4})", "year_built_alt"),
    (r"([\d\.]+)\s*[Aa]cres?", "lot_acres"),
    (r"HOAFee=(\d+)", "hoa_monthly"),
    (r"MLS\s*#?\s*:?\s*([A-Z]{2,}\d+)", "mls_number"),
    (r"[Gg]arage[^<]{0,20}(\d+)\s*(?:spaces?|cars?)", "garage_spaces"),
    (r"(\d+)\s*[Gg]arage", "garage_alt"),
    (r"[Pp]arcel\s*(?:#|number|id)?\s*:?\s*([\d\-]+)", "parcel_number"),
    (r"[Ss]ingle\s*[Ff]amily", "property_type_single_family"),
    (r"[Cc]olonial", "style_colonial"),
    (r"[Cc]entral\s*(?:A/?C|[Aa]ir)", "has_central_ac"),
    (r"[Ff]ireplace", "has_fireplace"),
    (r"[Bb]asement", "has_basement"),
    (r"[Hh]ot\s*[Ww]ater", "heating_hot_water"),
    (r"[Nn]atural\s*[Gg]as", "fuel_natural_gas"),
    (r"[Pp]ublic\s*(?:[Ss]ewer|[Ww]ater)", "public_utilities"),
    (r"[Ff]ee\s*[Ss]imple", "ownership_fee_simple"),
    (r"[Mm]elody\s*[Ff]arm", "subdivision_melody_farm"),
    (r"[Ll]oudoun", "county_loudoun"),
    (r"[Mm]atterport|3D\s*[Tt]our", "has_3d_tour"),
    (r"[Oo]pen\s*[Hh]ouse", "has_open_house"),
    (r"zpid[=:](\d+)", "zpid"),
]:
    m = re.search(pat, content)
    if m:
        text_fields[name] = m.group(1) if m.lastindex else True

result["text_fields"] = text_fields

# =============================================
# 14. Monthly payment module data
# =============================================
payment_section = re.search(
    r'data-testid="monthly-payment-module"(.*?)(?=data-testid="(?!chip)[^"]+"|$)',
    content, re.DOTALL,
)
if payment_section:
    section = payment_section.group(1)[:3000]
    amounts = re.findall(r'\$([\d,]+)', section)
    labels = re.findall(r'>([^<]{2,30}(?:interest|tax|insurance|hoa|pmi|principal))[^<]*<', section, re.IGNORECASE)
    result["monthly_payment_raw"] = {
        "amounts": amounts[:10],
        "labels": labels[:10],
    }

# =============================================
# 15. Nearby/similar homes
# =============================================
nearby_section = re.search(
    r'data-testid="(?:nearby-homes-module|similar-homes-module)"(.*?)(?=data-testid="footer|$)',
    content, re.DOTALL,
)
if nearby_section:
    section = nearby_section.group(1)[:10000]
    nearby_prices = re.findall(r'\$([\d,]+)', section)
    nearby_addrs = re.findall(r'(\d+\s+[A-Z][^<,]{5,40}(?:Dr|St|Ct|Ln|Pl|Way|Ter|Rd|Cir|Ave))', section)
    result["nearby_homes_raw"] = {
        "prices": nearby_prices[:20],
        "addresses": nearby_addrs[:20],
    }

# =============================================
# 16. Photos
# =============================================
photo_urls = re.findall(r'"(https://photos\.zillowstatic\.com/[^"]+)"', content)
result["photo_urls"] = list(set(photo_urls))
result["photo_count"] = len(set(photo_urls))

# =============================================
# 17. Market value / climate sections
# =============================================
climate_section = re.search(
    r'data-testid="climate-hub"(.*?)(?=data-testid="[^"]+"|$)',
    content, re.DOTALL,
)
if climate_section:
    section = climate_section.group(1)[:2000]
    climate_text = re.sub(r'<[^>]+>', ' ', section)
    climate_text = re.sub(r'\s+', ' ', climate_text).strip()
    result["climate_info"] = climate_text[:500]

# =============================================
# Save everything
# =============================================
output_path = "zillow_extracted_42580_deer_isle.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, default=str)

print(f"Saved to {output_path}")
print(f"Total fields extracted: {len(result)}")
print()

# Print summary
print("=" * 80)
print("COMPLETE ZILLOW DATA: 42580 Deer Isle Dr, Chantilly VA 20152")
print("=" * 80)

print(f"\nPrice: ${result.get('list_price', 'N/A')}")
print(f"Beds/Baths/Sqft: {bed_bath_sqft}")
print(f"Zestimate: ${result.get('zestimate', 'N/A')}")
print(f"Rent Zestimate: ${result.get('rent_zestimate', 'N/A')}/mo")

print(f"\nDescription: {result.get('description', result.get('description_full', 'N/A'))[:300]}")

print(f"\nPrice History ({len(result.get('price_history', []))} entries):")
for ph in result.get("price_history", []):
    print(f"  {ph.get('date', '?')}: ${ph.get('price', '?')} {ph.get('event', '')}")

print(f"\nTax History ({len(result.get('tax_history', []))} entries):")
for th in result.get("tax_history", []):
    print(f"  {th.get('year', '?')}: ${th.get('amount', '?')}")

if result.get("tax_assessment_raw"):
    print(f"\nTax Assessment Raw:")
    for ta in result["tax_assessment_raw"]:
        print(f"  {ta}")

print(f"\nFacts & Features ({len(result.get('facts_and_features', {}))} categories):")
for cat, items in result.get("facts_and_features", {}).items():
    print(f"  {cat}:")
    for item in items:
        print(f"    - {item}")

print(f"\nSchools ({len(result.get('schools', []))}):")
for s in result.get("schools", []):
    print(f"  {s}")

print(f"\nScores: {result.get('scores', {})}")
print(f"Agent: {result.get('listing_agent_raw', 'N/A')}")
print(f"Broker: {result.get('broker_raw', 'N/A')}")

print(f"\nText fields: {json.dumps(result.get('text_fields', {}), indent=2)}")

print(f"\nPhotos: {result.get('photo_count', 0)} unique URLs")
print(f"Climate info: {result.get('climate_info', 'N/A')[:200]}")

if result.get("nearby_homes_raw"):
    print(f"\nNearby homes: {len(result['nearby_homes_raw'].get('addresses', []))} addresses, {len(result['nearby_homes_raw'].get('prices', []))} prices")

if result.get("monthly_payment_raw"):
    print(f"\nPayment module: {result['monthly_payment_raw']}")
