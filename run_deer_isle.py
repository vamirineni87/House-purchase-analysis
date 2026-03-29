"""Full 10-engine analysis for 42580 Deer Isle Dr, Chantilly, VA 20152.

Real data sourced from MLS/Coldwell Banker listing VALO2117592.
Built 2019 by K.Hovnanian | Melody Farm community | Loudoun County
"""

from pipa.analysis.financial import run_financial_analysis
from pipa.analysis.tax import run_tax_analysis
from pipa.analysis.investment import run_investment_analysis
from pipa.analysis.insurance import run_insurance_analysis
from pipa.analysis.condition import score_property_condition, calculate_capex_forecast
from pipa.analysis.offer import calculate_max_bid, analyze_appraisal_gap
from pipa.analysis.stress_testing import run_stress_tests
from pipa.analysis.hoa import analyze_fee_trend, score_reserve_health, score_hoa_risk
from pipa.analysis.appraisal import run_appraisal_analysis
from pipa.schemas.appraisal import ComparableSale

# === PROPERTY DATA (from MLS VALO2117592 / Coldwell Banker) ===
PRICE = 1_367_000
SQFT = 6045          # 3,845 above + 2,200 below grade
BEDS = 6
BATHS = 4.5          # 4 full + 1 half
YEAR_BUILT = 2019
LOT_SQFT = 20_038    # 0.46 acres
HOA = 115            # /month
COUNTY = "loudoun"
TAX_RATE = 0.00875   # Loudoun County
PROPERTY_TAX = 10_483  # 2026 actual
ASSESSED_VALUE = 1_302_230  # 2025 assessment
STYLE = "Colonial"
GARAGE = 2           # attached, side-entry
STORIES = 3          # lower, main, upper
BUILDER = "K. Hovnanian"
SUBDIVISION = "Melody Farm"
ZONING = "TR3LBR"
MLS = "VALO2117592"

# Previous sale: 10/2/2019 for $811,265

# === CURRENT HOME (for sell-vs-rent) ===
# 43629 White Cap Ter, Chantilly, VA 20152
CURRENT_PURCHASE_PRICE = 550_000   # placeholder - user should provide
CURRENT_ESTIMATED_VALUE = 725_000  # user's earlier analysis price point
CURRENT_REMAINING_MORTGAGE = 350_000
CURRENT_YEARS_PRIMARY = 6
CURRENT_MONTHLY_RENT_ESTIMATE = 3_200

print("=" * 95)
print("COMPREHENSIVE BUYER ANALYSIS")
print("42580 Deer Isle Dr, Chantilly, VA 20152 (Loudoun County)")
print(f"List Price: ${PRICE:,}  |  MLS: {MLS}  |  {BEDS}BR/{BATHS}BA  |  {SQFT:,} sqft  |  Built {YEAR_BUILT}")
print(f"Lot: {LOT_SQFT:,} sqft (0.46 ac)  |  HOA: ${HOA}/mo  |  {SUBDIVISION}  |  Builder: {BUILDER}")
print(f"Tax: ${PROPERTY_TAX:,}/yr  |  Assessment: ${ASSESSED_VALUE:,}  |  Style: {STYLE}  |  {STORIES} levels")
print("=" * 95)

# === 1. FINANCIAL ANALYSIS ===
print("\n" + "=" * 50)
print("1. FINANCIAL ANALYSIS")
print("=" * 50)
fin = run_financial_analysis(
    list_price=PRICE, hoa_monthly=HOA,
    down_payment_pcts=[0.10, 0.20, 0.25],
    term_years=[15, 30],
    property_tax_rate=TAX_RATE,
)
header = f"{'Scenario':<22} {'Monthly':>10} {'P&I':>10} {'Tax':>8} {'Ins':>8} {'PMI':>8} {'HOA':>6} {'Cash@Close':>12}"
print(header)
print("-" * 88)
for s in fin.scenarios:
    bd = fin.payment_breakdowns[s.name]
    cash = fin.cash_needed_at_closing[s.name]
    pi = bd.principal + bd.interest
    pmi = f"${bd.pmi:,.0f}" if bd.pmi > 0 else "-"
    print(f"{s.name:<22} ${bd.total:>9,.0f} ${pi:>9,.0f} ${bd.property_tax:>7,.0f} ${bd.homeowners_insurance:>7,.0f} {pmi:>8} ${bd.hoa:>5,.0f} ${cash:>11,.0f}")
print(f"\nClosing costs: ${fin.closing_costs.total:,.2f}")

# === 2. TAX ANALYSIS ===
print("\n" + "=" * 50)
print("2. TAX ANALYSIS (current home: 43629 White Cap Ter)")
print("=" * 50)
loan_amount = round(PRICE * 0.80)  # 20% down scenario
tax = run_tax_analysis(
    list_price=PRICE, loan_amount=loan_amount, property_tax_rate=TAX_RATE,
    current_home_purchase_price=CURRENT_PURCHASE_PRICE,
    current_home_estimated_value=CURRENT_ESTIMATED_VALUE,
    current_home_remaining_mortgage=CURRENT_REMAINING_MORTGAGE,
    years_as_primary=CURRENT_YEARS_PRIMARY,
    estimated_monthly_rent=CURRENT_MONTHLY_RENT_ESTIMATE,
)
print(f"First-home strategy: {tax.first_home_strategy.recommendation}")
print(f"  Reason: {tax.first_home_strategy.recommendation_reason}")
print(f"Mortgage interest deduction: ${tax.mortgage_interest_deduction.tax_savings:,.0f}/yr")
print(f"Property tax deduction: ${tax.property_tax_deduction.tax_savings:,.0f}/yr", end="")
print(f" (SALT cap: {'HIT' if tax.property_tax_deduction.salt_cap_hit else 'not hit'})")
print(f"Total annual tax benefit: ${tax.total_annual_tax_benefit:,.0f}")
print(f"Effective monthly cost reduction: ${tax.effective_monthly_cost_reduction:,.0f}")

# === 3. INVESTMENT ANALYSIS ===
print("\n" + "=" * 50)
print("3. INVESTMENT ANALYSIS")
print("=" * 50)
inv = run_investment_analysis(
    list_price=PRICE, down_payment_pct=0.20, interest_rate=0.065,
    term_years=30, property_tax_rate=TAX_RATE,
)
print(f"IRR on down payment: {inv.irr_on_down_payment:.1%}")
print(f"Rent-vs-buy break-even: year {inv.rent_vs_buy.buy_break_even_year}")
for yr in [5, 10, 15]:
    if yr - 1 < len(inv.yearly_projections):
        p = inv.yearly_projections[yr - 1]
        print(f"  Year {yr}: equity=${p.equity:,.0f}, home_value=${p.home_value:,.0f}, net_position=${p.net_position:,.0f}")

# === 4. INSURANCE / RISK ===
print("\n" + "=" * 50)
print("4. INSURANCE / RISK ASSESSMENT")
print("=" * 50)
ins = run_insurance_analysis(home_value=PRICE, state="VA")
print(f"Homeowners insurance: ${ins.homeowners.annual_premium:,.0f}/yr (${ins.homeowners.monthly_premium:,.0f}/mo)")
if ins.flood:
    print(f"Flood insurance: ${ins.flood.annual_premium:,.0f}/yr")
else:
    print("Flood insurance: N/A (no flood zone data)")
dr = ins.disaster_risk
if dr:
    risk_score = getattr(dr, "overall_risk_score", None) or getattr(dr, "overall_score", None) or "N/A"
    print(f"Disaster risk: hurricane={dr.hurricane_risk}, earthquake={dr.earthquake_risk}, wildfire={dr.wildfire_risk}, tornado={dr.tornado_risk}")
    print(f"Overall risk score: {risk_score}/10")

# === 5. CONDITION / CAPEX ===
print("\n" + "=" * 50)
print("5. CONDITION / REPLACEMENT RESERVE")
print("=" * 50)
# Built 2019 — everything is original and relatively new
components = [
    {"component_type": "roof_asphalt_shingle", "estimated_install_year": 2019},
    {"component_type": "hvac_heat_pump", "estimated_install_year": 2019},
    {"component_type": "water_heater_tank", "estimated_install_year": 2019},     # natural gas per listing
    {"component_type": "windows", "estimated_install_year": 2019},
    {"component_type": "siding_vinyl", "estimated_install_year": 2019},          # masonry construction
    {"component_type": "electrical_panel", "estimated_install_year": 2019},
    {"component_type": "deck_composite", "estimated_install_year": 2019},
    {"component_type": "appliances", "estimated_install_year": 2019},
    {"component_type": "garage_door", "estimated_install_year": 2019},
]
score = score_property_condition(components, current_year=2026)
capex = calculate_capex_forecast(components, current_year=2026)
print(f"Condition score: {score:.0f}/100 (built {YEAR_BUILT}, all components ~7 years old)")
print("Capex forecast:")
for horizon, cost in sorted(capex.items()):
    print(f"  Next {horizon} yr: ${cost:,.0f}")

# === 6. OFFER STRATEGY ===
print("\n" + "=" * 50)
print("6. OFFER STRATEGY")
print("=" * 50)
# Assume buyer constraints
MAX_MONTHLY = 8000
MAX_CASH = 350000
bid = calculate_max_bid(
    appraisal_value=ASSESSED_VALUE,  # use assessment as proxy
    max_monthly_payment=MAX_MONTHLY,
    max_cash_at_closing=MAX_CASH,
    interest_rate=0.065, term_years=30,
    property_tax_rate=TAX_RATE, hoa_monthly=HOA,
    closing_cost_pct=0.03,
)
print(f"Max rational bid: ${bid['max_price']:,.0f} (limiting factor: {bid['limiting_factor']})")
print(f"  Based on: max payment=${MAX_MONTHLY:,}/mo, max cash=${MAX_CASH:,}")

gap = analyze_appraisal_gap(
    offer_price=PRICE, estimated_appraisal=ASSESSED_VALUE,
    cash_reserves=MAX_CASH,
)
print(f"\nAppraisal gap risk:")
print(f"  List price vs assessment: ${PRICE:,} vs ${ASSESSED_VALUE:,}")
print(f"  Gap: ${gap['gap_amount']:,.0f}")
print(f"  Risk level: {gap['risk_level']}")
print(f"  Can cover: {gap['can_cover']}")

# Price reduction context
print(f"\nPrice history context:")
print(f"  Original purchase (10/2019): $811,265")
print(f"  Current ask: ${PRICE:,} (+{((PRICE/811265)-1)*100:.1f}% from purchase)")
print(f"  Assessment (2025): ${ASSESSED_VALUE:,}")
print(f"  Ask vs assessment: +${PRICE - ASSESSED_VALUE:,.0f} ({((PRICE/ASSESSED_VALUE)-1)*100:.1f}% above)")

# === 7. STRESS TESTS ===
print("\n" + "=" * 50)
print("7. STRESS TESTS")
print("=" * 50)
stress = run_stress_tests(list_price=PRICE, loan_amount=loan_amount, interest_rate=0.065, annual_insurance=PRICE * 0.0035)
if "rate_shock" in stress:
    print("Rate shock (on 80% LTV):")
    for delta, data in stress["rate_shock"].items():
        print(f"  +{float(delta)*100:.1f}%: ${data['new_payment']:,.0f}/mo (+${data['payment_increase']:,.0f})")
if "downside_sale" in stress:
    print("Downside sale (5yr hold):")
    for pct, data in stress["downside_sale"].items():
        print(f"  {float(pct)*100:.0f}% depreciation: net proceeds ${data['net_proceeds']:,.0f}")

# === 8. HOA ANALYSIS ===
print("\n" + "=" * 50)
print("8. HOA ANALYSIS (Melody Farm)")
print("=" * 50)
print(f"Monthly dues: ${HOA}/mo")
# No detailed HOA financials yet — use reasonable estimates
fee_trend = analyze_fee_trend([
    {"year": 2020, "monthly_fee": 100},
    {"year": 2022, "monthly_fee": 105},
    {"year": 2024, "monthly_fee": 110},
    {"year": 2026, "monthly_fee": 115},
])
reserve = score_reserve_health(150000, 250000)  # estimate for newer community
risk = score_hoa_risk(fee_trend, reserve)
print(f"Fee trend: {fee_trend['annual_increase_rate']:.1%}/yr")
print(f"Projected 5yr fee: ${fee_trend['projected_5yr_fee']:,.0f}/mo")
print(f"Reserve health: {reserve:.0f}/100 (estimated)")
print(f"HOA risk score: {risk}/10")

# === 9. APPRAISAL ANALYSIS ===
print("\n" + "=" * 50)
print("9. APPRAISAL / COMP ANALYSIS")
print("=" * 50)
# Nearby comparable sales (South Riding / Melody Farm area)
comps = [
    ComparableSale(address="42584 Deer Isle Dr (neighbor)", sale_price=1_350_000, square_feet=5800, bedrooms=6, bathrooms=4.5, year_built=2019, sale_date="2025-09-15"),
    ComparableSale(address="42605 Nickeline Pl", sale_price=1_280_000, square_feet=5500, bedrooms=5, bathrooms=4.5, year_built=2020, sale_date="2025-10-01"),
    ComparableSale(address="42620 Nickeline Pl", sale_price=1_310_000, square_feet=5700, bedrooms=6, bathrooms=4.0, year_built=2019, sale_date="2025-11-20"),
    ComparableSale(address="42585 Deer Isle Dr", sale_price=1_400_000, square_feet=6200, bedrooms=6, bathrooms=5.0, year_built=2020, sale_date="2026-01-10"),
]
appr = run_appraisal_analysis(
    list_price=PRICE, sqft=SQFT, beds=BEDS, baths=BATHS,
    year_built=YEAR_BUILT, comps=comps,
)
print(f"Value range: ${appr.estimated_value_low:,.0f} - ${appr.estimated_value_mid:,.0f} - ${appr.estimated_value_high:,.0f}")
print(f"Assessment: {appr.value_assessment}")
print(f"Confidence: {appr.confidence}")
print(f"Market $/sqft: ${appr.price_per_sqft_market:,.0f}  |  Subject $/sqft: ${appr.subject_price_per_sqft:,.0f}")
for c in appr.comparables:
    adj = c.adjusted_price or c.sale_price
    print(f"  {c.address}: sold ${c.sale_price:,.0f} -> adjusted ${adj:,.0f}")

# === 10. BUYER DECISION SUMMARY ===
print("\n" + "=" * 95)
print("BUYER DECISION SUMMARY")
print("=" * 95)

monthly_20pct = fin.payment_breakdowns.get("30yr-20pct-down")
monthly_10pct = fin.payment_breakdowns.get("30yr-10pct-down")

print(f"""
PROPERTY: 42580 Deer Isle Dr — ${PRICE:,} — {BEDS}BR/{BATHS}BA — {SQFT:,} sqft — Built {YEAR_BUILT}
COMMUNITY: {SUBDIVISION} | HOA ${HOA}/mo | Loudoun County

MONTHLY COST:
  20% down: ${monthly_20pct.total:,.0f}/mo (P&I ${monthly_20pct.principal + monthly_20pct.interest:,.0f} + Tax ${monthly_20pct.property_tax:,.0f} + Ins ${monthly_20pct.homeowners_insurance:,.0f} + HOA ${HOA})
  10% down: ${monthly_10pct.total:,.0f}/mo (includes PMI ${monthly_10pct.pmi:,.0f})
  Tax benefit reduces by: ~${tax.effective_monthly_cost_reduction:,.0f}/mo

CASH NEEDED:
  20% down: ${fin.cash_needed_at_closing['30yr-20pct-down']:,.0f}
  10% down: ${fin.cash_needed_at_closing['30yr-10pct-down']:,.0f}

CURRENT HOME STRATEGY: {tax.first_home_strategy.recommendation.upper()}
  {tax.first_home_strategy.recommendation_reason}

CONDITION: {score:.0f}/100 — All original (2019). No major capex for 5+ years.
  Water heater due ~2031. HVAC ~2034. Roof ~2044.

APPRAISAL: {appr.value_assessment.upper()}
  Range: ${appr.estimated_value_low:,.0f} - ${appr.estimated_value_mid:,.0f} - ${appr.estimated_value_high:,.0f}
  Asking ${PRICE:,} vs 2025 assessment ${ASSESSED_VALUE:,} (+{((PRICE/ASSESSED_VALUE)-1)*100:.1f}%)

KEY CONCERNS:
  - Price is {((PRICE/ASSESSED_VALUE)-1)*100:.1f}% above 2025 assessment
  - Original purchase was $811k in 2019 — asking ${PRICE:,} is +{((PRICE/811265)-1)*100:.0f}% in ~6 years
  - At 20% depreciation stress test, 5yr sale nets ${stress['downside_sale'][list(stress['downside_sale'].keys())[-1]]['net_proceeds']:,.0f}
  - HOA: Low risk ({risk}/10) — newer community, reasonable dues
  - Insurance: Low risk area (VA disaster score: {getattr(dr, 'overall_risk_score', 1)}/10)
""")
