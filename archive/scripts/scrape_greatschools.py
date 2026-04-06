"""Scrape GreatSchools school profile page for detailed ratings + stats."""

import asyncio
import json
import re
from playwright.async_api import async_playwright


async def scrape_school(url: str) -> dict:
    """Scrape a GreatSchools school profile page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"Loading {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # Scroll to load all lazy content
        for i in range(10):
            await page.evaluate(f"window.scrollTo(0, {(i + 1) * 600})")
            await page.wait_for_timeout(600)
        await page.wait_for_timeout(3000)

        result = {}

        # Get window.gon data (has rating, school_id, etc.)
        gon = await page.evaluate("() => window.gon || null")
        if gon and isinstance(gon, dict):
            ad = gon.get("ad_set_targeting", {})
            result["gs_rating"] = ad.get("gs_rating")
            result["school_id"] = ad.get("school_id")
            result["city"] = ad.get("City") or ad.get("city_long")
            result["state"] = ad.get("State")
            result["zipcode"] = ad.get("zipcode")
            result["school_type"] = ad.get("type")
            result["level"] = ad.get("level")
            result["district_id"] = ad.get("district_id")
            result["num_reviews"] = ad.get("number_of_reviews_with_comments")
            result["address"] = ad.get("address")

        # Get ALL visible text from the page — this has everything rendered
        all_text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]

        # Extract test scores — GreatSchools shows "Math\n85%\nstate avg 70%"
        subjects = {}
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if line_lower in ("math", "reading", "science", "writing"):
                # Next line(s) should have the percentage
                for j in range(1, 4):
                    if i + j < len(lines):
                        pct_match = re.match(r"^(\d+(?:\.\d+)?)\s*%?$", lines[i + j])
                        if pct_match:
                            subjects[line] = {"score": float(pct_match.group(1))}
                            # Look for state average nearby
                            for k in range(j + 1, j + 4):
                                if i + k < len(lines):
                                    avg_match = re.search(
                                        r"(?:state\s*avg|state\s*average)[:\s]*([\d.]+)\s*%?",
                                        lines[i + k],
                                        re.IGNORECASE,
                                    )
                                    if avg_match:
                                        try:
                                            subjects[line]["state_avg"] = float(avg_match.group(1))
                                        except ValueError:
                                            pass
                                        break
                            break

        if subjects:
            result["test_scores"] = subjects

        # Extract sub-ratings (Test Score Rating, Academic Progress, etc.)
        sub_ratings = {}
        for rating_name in [
            "Test Score Rating",
            "Academic Progress Rating",
            "Equity Overview Rating",
            "College Readiness Rating",
        ]:
            for i, line in enumerate(lines):
                if rating_name.lower() in line.lower():
                    # Look for X/10 nearby
                    for j in range(-2, 5):
                        if 0 <= i + j < len(lines):
                            m = re.search(r"(\d+)\s*/\s*10", lines[i + j])
                            if m:
                                sub_ratings[rating_name] = int(m.group(1))
                                break
                    break
        if sub_ratings:
            result["sub_ratings"] = sub_ratings

        # Extract "outperforms X% of similar schools"
        for line in lines:
            m = re.search(r"outperforms?\s*(\d+)\s*%", line, re.IGNORECASE)
            if m:
                result.setdefault("outperforms", []).append(int(m.group(1)))

        # Extract enrollment
        for line in lines:
            m = re.match(r"^([\d,]+)\s*students?$", line, re.IGNORECASE)
            if m:
                result["enrollment"] = int(m.group(1).replace(",", ""))
                break

        # Extract student-teacher ratio
        for line in lines:
            m = re.search(r"(\d+(?:\.\d+)?)\s*:\s*1", line)
            if m and "student" in lines[max(0, lines.index(line) - 2):lines.index(line) + 2].__repr__().lower():
                result["student_teacher_ratio"] = float(m.group(1))
                break

        # Extract demographics (ethnicity percentages)
        demographics = {}
        for i, line in enumerate(lines):
            # Look for "48% Asian" or "Asian 48%" patterns
            m = re.match(r"^(\d+)\s*%\s*$", line)
            if m and i + 1 < len(lines):
                next_line = lines[i + 1]
                if any(eth in next_line for eth in [
                    "Asian", "White", "Black", "Hispanic", "Two or more",
                    "Pacific Islander", "American Indian", "Native",
                ]):
                    demographics[next_line] = int(m.group(1))
            # Also check "Asian or Pacific Islander\n48%"
            for eth in ["Asian", "White", "Black", "Hispanic", "Two or more", "Pacific", "American Indian"]:
                if eth.lower() in line.lower() and i + 1 < len(lines):
                    pct = re.match(r"^(\d+)\s*%?$", lines[i + 1])
                    if pct:
                        demographics[line] = int(pct.group(1))

        if demographics:
            result["demographics"] = demographics

        # Extract free/reduced lunch
        for line in lines:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*%\s*(?:.*(?:free|reduced|lunch|economically|low.income))",
                line,
                re.IGNORECASE,
            )
            if m:
                result["free_reduced_lunch_pct"] = float(m.group(1))
                break

        # Extract average review rating
        for line in lines:
            m = re.search(r"([\d.]+)\s*out of 5", line)
            if m:
                result["avg_review_stars"] = float(m.group(1))
                break

        # School name from h1
        name_el = await page.query_selector("h1")
        if name_el:
            result["name"] = (await name_el.text_content() or "").strip()

        print(json.dumps(result, indent=2))

        await browser.close()
        return result


async def main():
    schools = [
        ("Buffalo Trail ES", "https://www.greatschools.org/virginia/aldie/5236-Buffalo-Trail-Elementary-School/"),
        ("Willard MS", "https://www.greatschools.org/virginia/aldie/7734-WILLARD-INTERMEDIATE-SCHOOL/"),
        ("Lightridge HS", "https://www.greatschools.org/virginia/aldie/7898-Lightridge-High-School/"),
    ]

    all_results = {}
    for name, url in schools:
        print(f"\n{'='*60}")
        print(f"SCRAPING: {name}")
        print("=" * 60)
        data = await scrape_school(url)
        all_results[name] = data

    with open("greatschools_data.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to greatschools_data.json")


if __name__ == "__main__":
    asyncio.run(main())
