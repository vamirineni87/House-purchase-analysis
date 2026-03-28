# Home Purchase Analysis Tool (HPA)

A comprehensive Python CLI tool for analyzing potential home purchases. Built for buyers acquiring a second home as a new primary residence, with built-in analysis of whether to sell or rent out the first home.

## Features

- **Financial Analysis** -- Monthly payment breakdown (P&I, taxes, insurance, PMI, HOA), multi-scenario comparison (15yr vs 30yr, different down payments), full amortization schedules, closing cost estimation, total cost of ownership
- **Appraisal Module** -- Comparable sales analysis with standard adjustments, price-per-sqft market analysis, value range estimates (below/at/above market)
- **Neighborhood Analysis** -- School ratings, crime statistics, walkability scores, flood risk zones, demographics with composite scoring
- **Tax Analysis** -- Capital gains on selling first home (2-of-5-year rule), rental income analysis for keeping first home, SALT cap impact, mortgage interest deduction
- **Insurance & Risk** -- Homeowner's insurance estimation, FEMA flood zone classification, natural disaster risk by region
- **Investment Analysis** -- Equity buildup projections, rent-vs-buy break-even, IRR on down payment, net worth impact
- **Property Comparison** -- Side-by-side scoring of multiple properties across all dimensions
- **Report Generation** -- HTML, PDF, JSON, and Rich terminal output

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Run a full analysis
hpa analyze "123 Main St, Austin, TX 78701" \
    --price 450000 --sqft 2000 --beds 3 --baths 2.5 \
    --year-built 2005 --hoa 150

# View current mortgage rates
hpa rates

# Compare multiple properties
hpa compare --file properties.yaml

# Skip external API calls (use defaults only)
hpa analyze "123 Main St, Austin, TX 78701" \
    --price 450000 --sqft 2000 --beds 3 --baths 2.5 \
    --skip-api

# Choose specific output formats
hpa analyze "..." --price ... --sqft ... --beds ... --baths ... \
    --output terminal --output html --output json --output pdf

# Customize loan scenarios
hpa analyze "..." --price ... --sqft ... --beds ... --baths ... \
    --down-payment-pct 0.20 --down-payment-pct 0.10 --down-payment-pct 0.05 \
    --loan-term 30 --loan-term 15
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your details:

```yaml
api_keys:
  fred: "your-fred-api-key"        # Free: https://fred.stlouisfed.org/docs/api/api_key.html
  rentcast: "your-rentcast-key"     # 50 free/month: https://www.rentcast.io/api
  greatschools: "your-gs-key"      # Free: https://www.greatschools.org/api/
  walkscore: "your-walkscore-key"   # Free: https://www.walkscore.com/professional/api.php
  # FBI Crime and OpenFEMA require no API keys

# Your current home details (for sell vs rent analysis)
current_home:
  purchase_price: 300000
  purchase_date: "2020-06-15"
  estimated_current_value: 380000
  remaining_mortgage_balance: 240000
  monthly_payment: 1800
  mortgage_rate: 0.035
  annual_property_tax: 4000
  annual_insurance: 1500
  capital_improvements: 25000
  years_as_primary_residence: 5.5
  estimated_monthly_rent: 2200
```

## Data Sources

| Data | API | Cost |
|------|-----|------|
| Mortgage Rates | FRED (Federal Reserve) | Free |
| Property Data & Comps | RentCast | 50 free calls/month |
| School Ratings | GreatSchools | Free tier |
| Crime Statistics | FBI Crime Data Explorer | Free, no key |
| Flood Risk | OpenFEMA | Free, no key |
| Walkability | Walk Score | Free for consumer apps |
| Property Tax | API Ninjas | Free tier |
| Demographics | US Census ACS | Free |

All APIs are optional. When unavailable, the tool uses configurable default estimates.

## Output Formats

- **Terminal** -- Rich tables and panels, color-coded, instant viewing
- **HTML** -- Professional styled report, viewable in any browser
- **PDF** -- Print-ready document via WeasyPrint (requires system dependencies)
- **JSON** -- Full structured data export for integration with other tools

Reports are saved to `./reports/` by default.

## Project Structure

```
src/hpa/
├── cli.py              # Click CLI entry point
├── config.py           # Configuration loader
├── models/             # Pydantic v2 data models
├── api/                # External API clients (FRED, RentCast, etc.)
├── analysis/           # Analysis modules (financial, appraisal, tax, etc.)
├── report/             # Report generators (HTML, PDF, JSON, terminal)
│   └── templates/      # Jinja2 HTML templates + CSS
└── utils/              # Formatters, geocoding helpers
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Run with coverage
pytest --cov=hpa --cov-report=html
```

## License

MIT
