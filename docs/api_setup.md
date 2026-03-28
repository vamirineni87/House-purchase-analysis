# API Setup Guide

This guide walks you through setting up API keys for the Home Purchase Analysis tool. All APIs are optional -- the tool works without any keys by using default estimates.

## FRED API (Mortgage Rates)

**Free** -- Federal Reserve Economic Data

1. Visit https://fred.stlouisfed.org/docs/api/api_key.html
2. Create a free account
3. Request an API key (instant approval)
4. Add to `config.yaml`: `api_keys.fred: "your-key"`

Provides: Current 30-year and 15-year fixed mortgage rates (weekly data from Freddie Mac PMMS survey).

## RentCast API (Property Data & Comparables)

**Freemium** -- 50 free API calls per month

1. Visit https://www.rentcast.io/api
2. Sign up for a free account
3. Get your API key from the dashboard
4. Add to `config.yaml`: `api_keys.rentcast: "your-key"`

Provides: Property details, comparable sales data, and rental estimates.

## GreatSchools API (School Ratings)

**Free tier** -- 15,000 calls included

1. Visit https://www.greatschools.org/api/
2. Register for API access
3. Get your API key
4. Add to `config.yaml`: `api_keys.greatschools: "your-key"`

Provides: School ratings (1-10), test scores, school types, and distances.

## Walk Score API (Walkability)

**Free for consumer apps**

1. Visit https://www.walkscore.com/professional/api.php
2. Sign up for API access
3. Get your API key
4. Add to `config.yaml`: `api_keys.walkscore: "your-key"`

Provides: Walk Score, Transit Score, and Bike Score (0-100).

## API Ninjas (Property Tax)

**Free tier available**

1. Visit https://api-ninjas.com/
2. Create a free account
3. Get your API key
4. Add to `config.yaml`: `api_keys.api_ninjas: "your-key"`

Provides: Property tax rates by ZIP code, county, and state.

## US Census Bureau (Demographics)

**Free**

1. Visit https://api.census.gov/data/key_signup.html
2. Request a free API key (instant)
3. Add to `config.yaml`: `api_keys.census: "your-key"`

Provides: Population, median income, median home value by geography.

## No API Key Required

These services work without any API key:

- **FBI Crime Data Explorer** -- Crime statistics by state/region
- **OpenFEMA** -- Flood risk and disaster declaration data

## Environment Variable Overrides

You can also set API keys via environment variables (overrides config.yaml):

```bash
export HPA_FRED_API_KEY="your-key"
export HPA_RENTCAST_API_KEY="your-key"
export HPA_GREATSCHOOLS_API_KEY="your-key"
export HPA_WALKSCORE_API_KEY="your-key"
export HPA_API_NINJAS_KEY="your-key"
export HPA_CENSUS_API_KEY="your-key"
```
