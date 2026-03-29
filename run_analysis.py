"""Full expanded analysis for 43629 White Cap Ter, Chantilly, VA 20152."""

from pipa.analysis.financial import run_financial_analysis
from pipa.analysis.tax import run_tax_analysis
from pipa.analysis.investment import run_investment_analysis
from pipa.analysis.insurance import run_insurance_analysis
from pipa.analysis.condition import score_property_condition, calculate_capex_forecast
from pipa.analysis.offer import calculate_max_bid, analyze_appraisal_gap
from pipa.analysis.stress_testing import run_stress_tests
from pipa.analysis.hoa import analyze_fee_trend, score_reserve_health, score_hoa_risk
from pipa.analysis.appraisal import run_appraisal_analysis

PRICE = 725000
COUNTY = "loudoun"
TAX_RATE = 0.00875
HOA = 150

print("=" * 90)
print("COMPREHENSIVE PROPERTY ANALYSIS")
print("43629 White Cap Ter, Chantilly, VA 20152 (Loudoun County)")
print(f"List Price: ${PRICE:,}  |  HOA: ${HOA}/mo  |  Tax Rate: {TAX_RATE*100:.3f}%")
print("=" * 90)

# === FINANCIAL ===
print("\n--- FINANCIAL ANALYSIS ---")
fin = run_financial_analysis(
    list_price=PRICE, hoa_monthly=HOA,
    down_payment_pcts=[0.10, 0.20], term_years=[15, 30],
    property_tax_rate=TAX_RATE,
)
header = f"{'Scenario':<22} {'Monthly':>10} {'P&I':>10} {'Tax':>8} {'Ins':>8} {'PMI':>8} {'Cash':>12}"
print(header)
print("-" * 80)
for s in fin.scenarios:
    bd = fin.payment_breakdowns[s.name]
    cash = fin.cash_needed_at_closing[s.name]
    pi = bd.principal + bd.interest
    pmi = f"${bd.pmi:,.0f}" if bd.pmi > 0 else "-"
    print(f"{s.name:<22} ${bd.total:>9,.0f} ${pi:>9,.0f} ${bd.property_tax:>7,.0f} ${bd.homeowners_insurance:>7,.0f} {pmi:>8} ${cash:>11,.0f}")
print(f"Closing costs: ${fin.closing_costs.total:,.2f}")

# === TAX ===
print("\n--- TAX ANALYSIS ---")
tax = run_tax_analysis(
    list_price=PRICE, loan_amount=580000, property_tax_rate=TAX_RATE,
    current_home_purchase_price=450000, current_home_estimated_value=620000,
    current_home_remaining_mortgage=280000, years_as_primary=6,
    estimated_monthly_rent=2800,
)
print(f"First-home strategy: {tax.first_home_strategy.recommendation}")
print(f"  Reason: {tax.first_home_strategy.recommendation_reason}")
print(f"Mortgage interest deduction: ${tax.mortgage_interest_deduction.tax_savings:,.0f}/yr")
print(f"Property tax deduction: ${tax.property_tax_deduction.tax_savings:,.0f}/yr", end="")
print(f" (SALT cap: {'hit' if tax.property_tax_deduction.salt_cap_hit else 'not hit'})")
print(f"Total annual tax benefit: ${tax.total_annual_tax_benefit:,.0f}")
print(f"Effective monthly cost reduction: ${tax.effective_monthly_cost_reduction:,.0f}")

# === INVESTMENT ===
print("\n--- INVESTMENT ANALYSIS ---")
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

# === INSURANCE ===
print("\n--- INSURANCE / RISK ---")
ins = run_insurance_analysis(home_value=PRICE, state="VA")
print(f"Homeowners insurance: ${ins.homeowners.annual_premium:,.0f}/yr (${ins.homeowners.monthly_premium:,.0f}/mo)")
if ins.flood:
    print(f"Flood insurance: ${ins.flood.annual_premium:,.0f}/yr (zone: {ins.flood.flood_zone}, risk: {ins.flood.risk_level})")
else:
    print("Flood insurance: N/A (no flood zone data)")
dr = ins.disaster_risk
if dr:
    print(f"Disaster risk: hurricane={dr.hurricane_risk}, earthquake={dr.earthquake_risk}, wildfire={dr.wildfire_risk}, tornado={dr.tornado_risk}")
    risk_score = getattr(dr, 'overall_risk_score', None) or getattr(dr, 'overall_score', None) or 'N/A'
    print(f"Overall risk score: {risk_score}/10")
else:
    print("Disaster risk: N/A")

# === CONDITION / CAPEX ===
print("\n--- CONDITION / REPLACEMENT RESERVE ---")
components = [
    {"component_type": "roof_asphalt_shingle", "estimated_install_year": 2008},
    {"component_type": "hvac_heat_pump", "estimated_install_year": 2018},
    {"component_type": "water_heater_tank", "estimated_install_year": 2019},
    {"component_type": "windows", "estimated_install_year": 2008},
    {"component_type": "siding_vinyl", "estimated_install_year": 2008},
    {"component_type": "electrical_panel", "estimated_install_year": 2008},
    {"component_type": "deck_composite", "estimated_install_year": 2015},
    {"component_type": "appliances", "estimated_install_year": 2020},
]
score = score_property_condition(components, current_year=2026)
capex = calculate_capex_forecast(components, current_year=2026)
print(f"Condition score: {score:.0f}/100")
print("Capex forecast:")
for horizon, cost in sorted(capex.items()):
    print(f"  Next {horizon} yr: ${cost:,.0f}")

# === OFFER ANALYSIS ===
print("\n--- OFFER STRATEGY ---")
bid = calculate_max_bid(
    appraisal_value=720000, max_monthly_payment=5000,
    max_cash_at_closing=160000, interest_rate=0.065,
    term_years=30, property_tax_rate=TAX_RATE, hoa_monthly=HOA,
)
print(f"Max rational bid: ${bid['max_price']:,.0f} (limiting factor: {bid['limiting_factor']})")

gap = analyze_appraisal_gap(offer_price=725000, estimated_appraisal=710000, cash_reserves=180000)
print(f"Appraisal gap risk: ${gap['gap_amount']:,.0f} gap, risk level: {gap['risk_level']}")
print(f"  Cash needed if gap: ${gap['required_cash']:,.0f}, can cover: {gap['can_cover']}")

# === STRESS TESTING ===
print("\n--- STRESS TESTS ---")
stress = run_stress_tests(list_price=PRICE, loan_amount=580000, interest_rate=0.065, annual_insurance=PRICE * 0.0035)
if "rate_shock" in stress:
    print("Rate shock scenarios:")
    for delta, data in stress["rate_shock"].items():
        print(f"  +{float(delta)*100:.1f}%: ${data['new_payment']:,.0f}/mo (+${data['payment_increase']:,.0f})")
if "downside_sale" in stress:
    print("Downside sale (5yr hold):")
    for pct, data in stress["downside_sale"].items():
        print(f"  {float(pct)*100:.0f}% depreciation: net proceeds ${data['net_proceeds']:,.0f}")

# === HOA ===
print("\n--- HOA ANALYSIS ---")
fee_trend = analyze_fee_trend([
    {"year": 2021, "monthly_fee": 125}, {"year": 2022, "monthly_fee": 130},
    {"year": 2023, "monthly_fee": 140}, {"year": 2024, "monthly_fee": 150},
])
reserve = score_reserve_health(85000, 200000)
risk = score_hoa_risk(fee_trend, reserve)
print(f"Fee trend: {fee_trend['annual_increase_rate']:.1%}/yr, projected 5yr: ${fee_trend['projected_5yr_fee']:,.0f}/mo")
print(f"Reserve health: {reserve:.0f}/100")
print(f"HOA risk score: {risk}/10")

# === APPRAISAL ===
print("\n--- APPRAISAL ANALYSIS ---")
from pipa.schemas.appraisal import ComparableSale
comps = [
    ComparableSale(address="43621 White Cap Ter", sale_price=710000, square_feet=2800, bedrooms=4, bathrooms=3.5, year_built=2007, sale_date="2025-11-15"),
    ComparableSale(address="43633 White Cap Ter", sale_price=735000, square_feet=3100, bedrooms=4, bathrooms=3.5, year_built=2009, sale_date="2025-12-01"),
    ComparableSale(address="25110 Mineral Springs Cir", sale_price=695000, square_feet=2750, bedrooms=4, bathrooms=3.0, year_built=2006, sale_date="2026-01-20"),
    ComparableSale(address="43520 Bowmore St", sale_price=748000, square_feet=3200, bedrooms=5, bathrooms=3.5, year_built=2010, sale_date="2026-02-10"),
]
appr = run_appraisal_analysis(
    list_price=725000, sqft=3000, beds=4, baths=3.5,
    year_built=2008, comps=comps,
)
print(f"Value range: ${appr.estimated_value_low:,.0f} - ${appr.estimated_value_mid:,.0f} - ${appr.estimated_value_high:,.0f}")
print(f"Assessment: {appr.value_assessment}")
print(f"Confidence: {appr.confidence}")
print(f"Market price/sqft: ${appr.price_per_sqft_market:,.0f}, subject: ${appr.subject_price_per_sqft:,.0f}")
for c in appr.comparables:
    adj = c.adjusted_price or c.sale_price
    print(f"  {c.address}: sold ${c.sale_price:,.0f} -> adjusted ${adj:,.0f}")

print("\n" + "=" * 90)
print("ANALYSIS COMPLETE — 10 engines, all results above")
print("=" * 90)
