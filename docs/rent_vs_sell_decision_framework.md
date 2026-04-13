# Rent vs Sell — Decision Framework

> Personal reference doc for the 43629 White Cap Ter (Aldie, VA) → new $1.325M home decision. Distilled from an analysis conversation; captures the framing, the math, the tax traps, and the clean options.

## The core question

**The real decision isn't "should I collect rent?" It's:**

> *Is the return on the ~$439k of equity trapped in the current home better than the guaranteed 6.45% return from using that equity to avoid borrowing it on the new home?*

That's a **1D question**. One variable dominates: current-home appreciation. Everything else is noise within ±20%.

## Your baseline numbers

**Current home (43629 White Cap Ter)**
| | |
|---|---|
| FMV | $790,000 |
| Adjusted basis | $478,000 (2015 purchase; no capex, $15k 2018 paint = repair, not capital improvement) |
| Current loan | $295,413 @ 2.50% |
| PITI | $1,956/mo (P+I ~$1,300, tax ~$573 at Loudoun's 0.87%, insurance ~$100) |
| HOA | $110/mo |
| Total carry | $2,066/mo |
| Net equity if sold today | $734,700 (93% of $790k) − $295,413 = **$439,287** |

**New home**
| | |
|---|---|
| Purchase price | $1,325,000 |
| Rate (30-yr fixed) | 6.45% |
| Base 20% down | $265,000 |
| Loan @ 20% down | $1,060,000 |
| Loan with sale proceeds applied | $621,000 (effective 53.1% down) |

**Key timing**
| | |
|---|---|
| Move out of White Cap Ter | May 2026 |
| Rental start | Jun 2026 |
| Section 121 cliff | May 2029 (36 months after move-out) |

## Why the simple spreadsheet is wrong

The naive "$42k rent − 22% tax − $2,066 carry = $664/mo positive cash flow" model is directionally right but has **three specific errors**:

### Error 1: Taxing the full gross rent at 22%

**Rental income is taxed on NET income after deductible expenses + depreciation**, not on the gross. Your actual taxable rental income is ~$6,400/yr (not $42k), and the effective rate is ~33.55% on that smaller base.

**Real rental tax: ~$2,150/yr**, not $9,240.

### Error 2: Subtracting the full PITI as a "cost"

**~$1,300/mo of your $1,956 PITI is principal paydown** — that's not a cost, it's equity growing in your pocket. True monthly carrying cost (interest + tax + insurance + HOA) is closer to **$1,500**, not $2,066.

### Error 3: Missing the comparison baseline

Your spreadsheet compared "+$664/mo rental surplus" against ZERO. The real comparison is **against what the $439k would do in the alternative** (selling and applying proceeds to the new home).

That alternative is **avoiding 6.45% × $439k = $28,300/yr of new-home interest = $2,360/mo**.

So the real comparison is:

| | Monthly benefit |
|---|---|
| Keep as rental | +$664/mo (before real landlord costs) |
| Sell and apply proceeds | +$2,360/mo (guaranteed interest savings) |

**Selling wins by ~$1,700/mo in pure cash flow.** Before we even get into appreciation or tax.

## Rental cash flow done properly

Clean, line-by-line analysis for year 1:

### Cash in
| | |
|---|---|
| Gross rent ($3,500/mo × 12) | $42,000 |
| Vacancy (0.5 mo/yr) | −$1,750 |
| Bad debt (0.5% of gross) | −$210 |
| **Collected rent** | **$40,040** |

### Cash out — operating
| | |
|---|---|
| Routine maintenance (5% of rent) | −$2,100 |
| Turnover cost (every 24 mo amortized) | −$1,250 |
| Capex reserve (water heater, HVAC, appliances) | −$1,500 |
| Landlord insurance bump (+15%) | −$180 |
| Self-management | $0 |
| **Operating out** | **$5,030** |

### Cash out — carrying (old home)
| | |
|---|---|
| PITI | $23,472 |
| HOA | $1,320 |
| **Carrying** | **$24,792** |

### Pre-tax cash flow
**$40,040 − $5,030 − $24,792 = $10,218/yr = $852/mo**

### Rental taxes (the real calculation)

Schedule E deductible expenses:
| | |
|---|---|
| Mortgage interest | $7,375 |
| Property tax | $6,676 (Loudoun 0.87%) |
| Insurance | $1,380 |
| HOA | $1,320 |
| Maintenance | $2,100 |
| Turnover | $1,250 |
| **Total deductible** | **$20,101** |

Depreciation (building portion of basis, 27.5-yr SL):
- Depreciable basis: min($478k, $790k) × 70.26% building = $335,843
- Annual: $335,843 / 27.5 = **$12,213**
- Year 1 mid-month convention: **$6,615** (6.5/12 × annual, placed in service June)

**Year 1 taxable rental income**:
$40,040 collected − $20,101 deductible − $6,615 depreciation = **$13,324**

**Year 1 rental tax** at 33.55% (24% fed + 5.75% VA + 3.8% NIIT):
$13,324 × 0.3355 = **$4,470**

### After-tax cash flow
$10,218 pre-tax − $4,470 tax = **$5,748/yr ≈ $479/mo**

**Year 2 onward** (full depreciation applies, interest shrinks as principal pays down):
Taxable income rises slightly each year → tax bill climbs ~$500/yr over the hold.

## The $439k return comparison — put numbers on it

### Side A: What the $439k earns if you SELL

Applies to new-home down payment. Every year you avoid paying 6.45% on that principal.

**Annual return: $28,300 (6.45% × $439k). Risk-free. Locked in for the life of the loan.**

Five-year total: ~$141,600
Ten-year total: ~$283,000

With refi path (5.5% at Y2, 4.5% at Y5):
- 5Y with refi: ~$129k
- 10Y with refi: ~$228k

The refi reduces the avoided interest because the blended rate is lower, but it affects both sides of the decision (keep case has an even bigger loan that also refis).

### Side B: What the $439k earns if you KEEP

Three components:

**B1. After-tax rental cash flow: ~$5,750/yr** (year 1; drifts to ~$4,000 by year 5)

**B2. Principal paydown on the 2.5% mortgage: ~$7,400/yr** (grows slightly each year)

**B3. Appreciation on the FULL $790k** (leveraged — you earn appreciation on the whole house but only $439k is at risk):

| 5Y total appreciation | Annual CAGR | Appreciation $ (net of 7% sell cost) | **Total annual return on $439k** |
|---|---|---|---|
| −10% total | −2.1%/yr | −$73,500 | **Keep LOSES ~9k/yr net** |
| 0% flat | 0% | $0 | ~$13k/yr = **3.0%** |
| +5% total | 1.0%/yr | +$36,800 | ~$20k/yr = **4.6%** |
| +10% total | 1.9%/yr | +$73,500 | ~$28k/yr = **6.4%** (matches sell) |
| +15% total | 2.8%/yr | +$110,300 | ~$35k/yr = **8.0%** |

### The break-even appreciation for your specific situation

**Keep beats sell when total 5-year appreciation exceeds ~8-9% (roughly 1.6-1.8%/yr CAGR).**

Full 5-year net worth delta table:

| 5Y Total Appreciation | Keep − Sell | Winner |
|---|---|---|
| −10% | −$148k | Sell, decisively |
| −5% | −$111k | Sell |
| 0% flat | −$64k | Sell |
| +5% | −$25k | Sell |
| **+8.7%** | **$0** | **Crossover** |
| +10% | +$10k | Keep (barely) |

**10-year picture is more favorable to keep** (assuming positive appreciation + the 4.5% refi at Y5):

| 10Y Total Appreciation | Keep − Sell |
|---|---|
| 0% | −$58k |
| +10% | +$52k |
| +15% | +$110k |
| +20% | +$165k |

**10Y break-even is ~4-5% total (~0.5%/yr)** — a much easier bar.

## IRS depreciation — how it actually works

### The mechanics

- **Residential rental**: 27.5-year straight-line (MACRS)
- Depreciable basis: **lower of (adjusted basis, FMV at conversion)**
- Your case: min($478k, $790k) = **$478k** ← FMV is higher, so you depreciate against basis
- Land doesn't depreciate. From 2016 county assessment: land 29.74%, building 70.26%
- Building basis: $478k × 0.7026 = **$335,843**
- Annual depreciation: $335,843 / 27.5 = **$12,213/yr**
- Mid-month convention applies in placed-in-service month and disposition month
- Year 1 (June placement): 6.5/12 × $12,213 = **$6,615**

### The "allowed or allowable" trap

Depreciation is **mandatory** once the property is placed in service. You can skip claiming it on your tax return, but the IRS still reduces your basis at sale by the amount you "should have" claimed. **Never skip it** — you lose the deduction AND still owe the recapture.

### Accumulated depreciation by hold length

| Hold | Dep claimed |
|---|---|
| Rent-then-sell May 2029 (36 mo) | $35,619 |
| Keep 5Y (Jun 2026 – May 2031) | $60,043 |
| Keep 10Y (Jun 2026 – May 2036) | $121,103 |

### Depreciation recapture at sale

Recaptured at **the lesser of your ordinary rate or 25% federal**, plus state, plus NIIT.

For your bracket: 24% fed + 5.75% VA + 3.8% NIIT = **33.55% effective**.

**§121 does NOT exclude depreciation recapture.** This is a specific carve-out in the tax code.

| Hold | Dep claimed | Recapture tax (33.55%) |
|---|---|---|
| Rent-then-sell May 2029 | $35,619 | **$11,950** |
| Keep 5Y → sell 2031 | $60,043 | **$20,144** |
| Keep 10Y → sell 2036 | $121,103 | **$40,630** |

### Depreciation's real value

It's a **timing shift**, not free money:
- Year 1: saves ~$4,100 in rental taxes
- At sale: claws back ~$4,000/yr of that saving as recapture
- **Net present benefit**: maybe $5-8k over 5 years (time value of money + possible bracket arbitrage)

Not the $20k of apparent savings. Useful but modest.

## Section 121 exclusion — when you get it and when you lose it

### The rule

**$500,000 of capital gain excluded for MFJ** if:
1. Owned at least 2 of the last 5 years ✓ (you've owned since 2015)
2. Used as **principal residence** at least 2 of the last 5 years before sale ← this is the one that matters
3. Haven't used §121 on another home in the last 2 years

### Your gain calculation

- Gross proceeds: $734,700 (93% of $790k)
- Basis: $478,000
- **Gain: ~$256,700** ← well under the $500k MFJ cap

This entire gain is **fully excludable IF you pass the 2-of-5 use test**.

### The 2-of-5 test against your timeline

| Sell date | 5-year lookback | PR-use months | Passes? |
|---|---|---|---|
| Today (May 2026) | 2021-05 → 2026-05 | 60 | ✓ |
| **Rent-then-sell May 2029** | 2024-05 → 2029-05 | **24 exactly** | ✓ barely |
| Jun 2029 (1 month later) | 2024-06 → 2029-06 | 23 | ✗ |
| 5Y hold (May 2031) | 2026-05 → 2031-05 | 0 | ✗ |
| 10Y hold (May 2036) | 2031-05 → 2036-05 | 0 | ✗ |

**The cliff is May 31, 2029.** Sell before → full exclusion. Sell after → zero exclusion on cap gain.

### Dollar impact of the cliff

Assuming gain stays roughly constant:

| Sell date | §121 excluded | Cap gain tax | Recapture tax | **Total sale tax** |
|---|---|---|---|---|
| Today | $256,700 | $0 | $0 | **$0** |
| May 2029 | $256,700 | $0 | $11,950 | **$11,950** |
| **Jun 2029 (1 month late!)** | **$0** | $63,020 | $11,950 | **$74,970** |
| 5Y (2031) | $0 | $48,279 | $20,144 | **$68,423** |
| 10Y (2036, w/ $79k appreciation) | $0 | $67,662 | $40,630 | **$108,292** |

**Missing the cliff by one month costs $63k in additional taxes.** This is the single hardest deadline in the whole decision.

## The §121(b)(5) "nonqualified use" trap

### Why "move back in for 6 months" doesn't work

Pre-2008, the classic strategy was: rent for a few years, move back in for a few months, sell and claim §121. Congress closed this with §121(b)(5) in the Housing Assistance Tax Act of 2008.

**The rule**: Any period of "nonqualified use" (rental use) during the ownership window prorates your exclusion.

**The exception**: Rental periods that fall **AFTER your last date of principal residence use** are excluded from the nonqualified count.

**The trap**: If you rent, then move back in, you create a NEW "last date of PR use" that's LATER than the rental period. The rental period is no longer "after last PR use" — it's now sandwiched in the middle of ownership, and it counts as nonqualified use.

### Worked example — the "move back for 6 months" scenario

Move out May 2026, rent to May 2029 (36 mo), move back May-Nov 2029, sell Nov 2029.

- Total ownership by Nov 2029: ~174 months
- Nonqualified use: 36 months (rental now counts because you moved back)
- Qualified ratio: (174 − 36) / 174 = **79.3%**
- Excluded gain: 79.3% × $256,700 = $203,665
- Nonqualified gain (taxed at LTCG): $53,035 × 24.55% = **$13,020**
- Recapture: **$11,950**
- **Total sale tax: $24,970**

**Moving back in costs you $13,020 in additional taxes compared to the clean Scenario B (rent-then-sell May 2029 with $11,950 total tax).**

### Why Scenario C ("re-establish 2-year use") is also worse

Rent 36 months, move back and live 24 months, sell May 2031:

- Still 36 months of nonqualified use
- Proration: (192 − 36) / 192 = 81.25%
- Cap gain tax on nonqualified portion: ~$11,830
- Plus recapture: $11,950
- **Total: $23,780**

Still worse than the clean rent-then-sell by $11,830 — and you've spent 2 years living in the old townhouse instead of the new home.

### Conclusion: the middle strategies don't exist

**There are only two tax-optimal rental paths:**
1. Sell now ($0 tax)
2. Rent clean through to May 2029 ($11,950 tax)

Everything else — move back, roommate, child, 5Y hold — is strictly worse than one of these two.

## Why roommate / child strategies also fail

### Roommate (you living in the townhouse with a renter)

This IS technically valid for §121 — having a roommate in your genuine principal residence doesn't disqualify you. But:

- "Principal residence" means **actually living there** (voter registration, driver's license, bills, majority of time). You can't commute from the new home and claim this.
- Roommate rent is **reportable rental income** on Schedule E
- **Depreciation** applies to the rented portion
- **Recapture** applies to the rented portion at sale
- Economic reality: a room rents for ~$900-1,200/mo in Aldie. Doesn't cover your $2,066 carrying cost. You'd subsidize the property by $10-15k/yr **while giving up the new home** for 2+ years to meet the 2-of-5 test.

**Technically valid, economically irrational for your situation.**

### Child living there

**Doesn't work.** §121 is personal to the taxpayer. Use by children (or any other family member) doesn't count as "principal residence use" by you.

Alternatives that also don't help:
- **Gift the house**: child inherits your basis ($478k), not a stepped-up basis. Plus gift tax.
- **Sell to child at FMV**: triggers your full tax event today, same as selling to a stranger.
- **Child rents from you at market rate**: you're a landlord, §121 doesn't apply.

## Virginia state tax — quick reference

- Graduated income tax, tops out at **5.75% on income > $17,000** (you're solidly in the top bracket at $300k combined)
- **No separate long-term capital gains rate** — cap gains taxed at ordinary rate (5.75%)
- **Conforms to federal AGI** — §121 exclusion passes through, depreciation deduction passes through
- **No 25% cap on recapture** at the state level — VA taxes recapture at 5.75%
- Property tax (Loudoun): **0.87% of assessed value** (current), ceiling ~1.07%

### Effective combined rates (yours)

| Income type | Fed | VA | NIIT | **Total** |
|---|---|---|---|---|
| Rental profit | 24% | 5.75% | 3.8% | **33.55%** |
| Long-term capital gain | 15% | 5.75% | 3.8% | **24.55%** |
| Depreciation recapture | 24% (capped at 25% fed) | 5.75% | 3.8% | **33.55%** |
| Gain excluded under §121 | 0% | 0% | 0% | **0%** |

**Key point**: Passive rental losses at your income level ($300k+ MAGI) are **suspended** — can't offset W-2 income. They're trapped until the property generates positive rental income or you sell.

## Property tax + insurance growth (Loudoun-specific)

Your current monthly carry decomposed:
| Line | Amount |
|---|---|
| P+I (2.5% on ~$295k, ~25yr remaining) | $1,300/mo |
| Property tax (0.87% on $790k) | $573/mo |
| Insurance | $100/mo |
| HOA | $110/mo |
| **Total** | **$2,083/mo** |

Growth assumptions:
- **Property tax** at 3%/yr base / 5%/yr stress (rate stable at 0.87-1.07%, assessments grow with market)
- **Insurance** at 5%/yr base (recent inflation elevated; some markets 10-15%)
- **HOA** at 3%/yr

Over 5 years, these compound to ~$3,500 extra cost in the keep case. Over 10 years, ~$17,000 extra. **Meaningful but doesn't flip the decision** — sits within the ±$50k error bars of the appreciation term.

## The DTI angle (financing, not taxes)

**The hidden factor most people miss**: when you apply for the new-home mortgage, the lender counts 75% of your projected rent ($2,625) as income and 100% of your old PITI ($2,066) as debt. **Your DTI just took a $1,100/mo hit.**

This can:
- Knock you into jumbo territory (higher rate)
- Force a bigger down payment
- Add 25-50 bps to the new-home rate

**25 bps on $1,060,000 = $2,650/yr = $13,250 over 5 years of extra interest cost.** This is potentially the single biggest hidden factor and it's LAYERED on top of everything else.

**Action**: call a lender and ask: "what's my new-home rate with the rental on my books vs. without?"

## The three clean strategies (and what drives each)

| Strategy | Tax at sale | Holding benefit | Risk profile |
|---|---|---|---|
| **Sell today** | $0 | $439k cash in hand, clean balance sheet, lower new-home rate | Lose all future appreciation + rental cash flow |
| **Rent-then-sell by May 2029** | $11,950 | 3 years of rent (~$17k net) + appreciation + paydown | Forced sale timing; 3 years of landlord hassle; DTI penalty on new-home mortgage |
| **Keep as rental long-term (10+ yr)** | $40-80k+ | 10+ years of rent + compounded appreciation + paydown + optional refi | Loss of §121; concentration risk; major capex exposure; 10 years of landlord commitment |

## Decision framework — 3 questions

If the answer to ALL three is yes → lean **keep** (specifically rent-then-sell 2029):

1. **Do I honestly believe Loudoun will appreciate at least 2%/yr for the next 3 years?** (break-even at 3Y horizon)
2. **Am I willing to be a landlord for 3 years and accept a FORCED sale by May 31, 2029 regardless of market conditions?**
3. **Have I confirmed with a lender that keeping the rental doesn't cost me 25+ bps on the new-home rate?** (or if it does, I've factored that in)

Any "no" → lean **sell**.

## The things that DON'T matter

Spend no time worrying about:
- Vacancy % (±0.5 mo/yr = ±$2k/yr, lost in the noise)
- Turnover frequency (±$500/yr)
- Management fee (you're self-managing)
- Exact tax bracket (24% vs 32% = ±$5k)
- Rent growth rate (±10% total = ±$2k/yr)
- Insurance bump (+10% vs +30% = ±$2k)
- HOA growth
- Minor capex ($0 to $3k/yr)

These are ALL second-order. Don't grid-search them. Appreciation is the only variable that actually changes the answer within realistic ranges.

## The things that DO matter

Watch these closely:
1. **Current-home appreciation** (±5%/yr swings answer $80k+ at 5Y)
2. **Hold horizon** (3Y favors sell, 10Y favors keep)
3. **Major capex shock probability × size** ($20k HVAC flips a close decision)
4. **New-home mortgage rate delta from DTI penalty** (25 bps = $13k over 5Y)
5. **Section 121 cliff discipline** (selling 1 month late costs $63k)

## One-number summary

**The break-even appreciation you need to make the rental case work:**

- Over 3 years (rent-then-sell): **~2.0%/yr compounded** (or ~6% total)
- Over 5 years (if §121 didn't matter): **~1.7%/yr compounded** (or ~8.7% total)
- Over 10 years: **~0.5%/yr compounded** (or ~5% total)

**Loudoun's historical average** over the last decade: 4-6%/yr. Pre-2020: 2-3%/yr.

**If you honestly believe Loudoun will do at least 2%/yr for the next 3 years, rent-then-sell 2029 beats sell-today.** Otherwise, sell today.

That's the whole decision in one sentence.
