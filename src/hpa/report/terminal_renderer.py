"""Rich terminal renderer for home purchase analysis reports."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hpa.models.appraisal import AppraisalResult
from hpa.models.financial import FinancialAnalysisResult
from hpa.models.insurance import InsuranceAnalysisResult
from hpa.models.investment import InvestmentAnalysisResult
from hpa.models.neighborhood import NeighborhoodAnalysisResult
from hpa.models.property import PropertyDetails
from hpa.models.tax import TaxAnalysisResult
from hpa.report.generator import AnalysisResults
from hpa.utils.formatters import format_currency, format_number, format_percentage


def _color_for_assessment(assessment: str) -> str:
    """Return a Rich color name based on a qualitative assessment string."""
    mapping = {
        "below_market": "green",
        "at_market": "yellow",
        "above_market": "red",
        "buy": "green",
        "rent": "yellow",
        "marginal": "yellow",
        "sell": "cyan",
        "either": "yellow",
        "low": "green",
        "moderate": "yellow",
        "medium": "yellow",
        "high": "red",
        "unknown": "dim",
    }
    return mapping.get(assessment, "white")


def _risk_color(level: str) -> str:
    """Return a Rich color for a risk level string."""
    return {"low": "green", "moderate": "yellow", "high": "red", "unknown": "dim"}.get(
        level, "white"
    )


class TerminalRenderer:
    """Renders a complete analysis report to the terminal using Rich."""

    def __init__(self) -> None:
        self.console = Console()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def render(
        self, property_details: PropertyDetails, results: AnalysisResults
    ) -> None:
        """Print the full analysis report to the console."""
        self.console.print()
        self._render_header(property_details)

        if results.financial:
            self._render_financial(results.financial)
        if results.appraisal:
            self._render_appraisal(results.appraisal)
        if results.neighborhood:
            self._render_neighborhood(results.neighborhood)
        if results.tax:
            self._render_tax(results.tax)
        if results.insurance:
            self._render_insurance(results.insurance)
        if results.investment:
            self._render_investment(results.investment)

        self.console.print()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _render_header(self, prop: PropertyDetails) -> None:
        addr = prop.address
        location = f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}"

        lines: list[str] = []
        lines.append(f"[bold]{location}[/bold]")
        lines.append("")

        details: list[str] = [
            f"List Price: [bold green]{format_currency(prop.list_price)}[/bold green]",
            f"Beds / Baths: {prop.bedrooms} / {prop.bathrooms}",
            f"Sq Ft: {format_number(prop.square_feet)}",
        ]
        if prop.lot_size_sqft:
            details.append(f"Lot: {format_number(prop.lot_size_sqft)} sqft")
        if prop.year_built:
            details.append(f"Year Built: {prop.year_built}")
        if prop.hoa_monthly > 0:
            details.append(f"HOA: {format_currency(prop.hoa_monthly)}/mo")
        if prop.garage_spaces:
            details.append(f"Garage: {prop.garage_spaces} spaces")
        if prop.mls_number:
            details.append(f"MLS#: {prop.mls_number}")
        if prop.days_on_market is not None:
            details.append(f"Days on Market: {prop.days_on_market}")

        lines.append("  |  ".join(details[:3]))
        if len(details) > 3:
            lines.append("  |  ".join(details[3:]))

        self.console.print(
            Panel(
                "\n".join(lines),
                title="[bold white]Home Purchase Analysis[/bold white]",
                border_style="bright_blue",
                padding=(1, 2),
            )
        )

    # ------------------------------------------------------------------
    # Financial Analysis
    # ------------------------------------------------------------------

    def _render_financial(self, fin: FinancialAnalysisResult) -> None:
        self.console.print()
        self.console.rule("[bold cyan]Financial Analysis[/bold cyan]")

        # --- Monthly Payment Breakdown Table ---
        table = Table(
            title="Monthly Payment Breakdown",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        table.add_column("Component", style="bold")
        for scenario in fin.scenarios:
            table.add_column(scenario.name, justify="right")

        components = [
            ("Principal", "principal"),
            ("Interest", "interest"),
            ("Property Tax", "property_tax"),
            ("Insurance", "homeowners_insurance"),
            ("PMI", "pmi"),
            ("HOA", "hoa"),
            ("Total", "total"),
        ]

        for label, field in components:
            row = [label]
            for scenario in fin.scenarios:
                breakdown = fin.payment_breakdowns.get(scenario.name)
                if breakdown is None:
                    row.append("-")
                    continue
                value = getattr(breakdown, field)
                cell = format_currency(value)
                if label == "Total":
                    cell = f"[bold]{cell}[/bold]"
                elif field == "pmi" and value > 0:
                    cell = f"[yellow]{cell}[/yellow]"
                row.append(cell)
            style = "on grey15" if label == "Total" else None
            table.add_row(*row, style=style)

        self.console.print(table)

        # --- Loan Scenario Details ---
        detail_table = Table(
            title="Loan Scenario Details",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        detail_table.add_column("Detail", style="bold")
        for scenario in fin.scenarios:
            detail_table.add_column(scenario.name, justify="right")

        detail_rows = [
            ("Loan Amount", lambda s: format_currency(s.loan_amount)),
            ("Down Payment", lambda s: f"{format_currency(s.down_payment)} ({format_percentage(s.down_payment_pct)})"),
            ("Interest Rate", lambda s: format_percentage(s.interest_rate)),
            ("Term", lambda s: f"{s.term_years} years"),
            ("Points", lambda s: str(s.points)),
        ]

        for label, fn in detail_rows:
            row = [label] + [fn(s) for s in fin.scenarios]
            detail_table.add_row(*row)

        self.console.print(detail_table)

        # --- Cash Needed at Closing ---
        cash_table = Table(
            title="Cash Needed at Closing",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        cash_table.add_column("Scenario", style="bold")
        cash_table.add_column("Amount", justify="right")

        for scenario in fin.scenarios:
            amount = fin.cash_needed_at_closing.get(scenario.name, 0)
            cash_table.add_row(scenario.name, f"[bold]{format_currency(amount)}[/bold]")

        self.console.print(cash_table)

        # --- Closing Costs Breakdown ---
        cc = fin.closing_costs
        cc_table = Table(
            title="Closing Costs Breakdown",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        cc_table.add_column("Item", style="bold")
        cc_table.add_column("Amount", justify="right")

        cc_items = [
            ("Loan Origination", cc.loan_origination),
            ("Appraisal Fee", cc.appraisal_fee),
            ("Title Insurance", cc.title_insurance),
            ("Escrow Fees", cc.escrow_fees),
            ("Recording Fees", cc.recording_fees),
            ("Prepaid Taxes", cc.prepaid_taxes),
            ("Prepaid Insurance", cc.prepaid_insurance),
            ("Inspection Fees", cc.inspection_fees),
            ("Other", cc.other),
        ]
        for label, val in cc_items:
            if val > 0:
                cc_table.add_row(label, format_currency(val))
        cc_table.add_row(
            "Total", f"[bold]{format_currency(cc.total)}[/bold]", style="on grey15"
        )

        self.console.print(cc_table)

        # --- Amortization Highlights ---
        if fin.amortization_schedules:
            amort_table = Table(
                title="Amortization Highlights",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            amort_table.add_column("Milestone", style="bold")
            for scenario in fin.scenarios:
                amort_table.add_column(scenario.name, justify="right")

            milestones = {
                "Year 1": 12,
                "Year 5": 60,
                "Year 10": 120,
                "Year 15": 180,
                "Year 30": 360,
            }

            for label, month in milestones.items():
                row = [label]
                for scenario in fin.scenarios:
                    schedule = fin.amortization_schedules.get(scenario.name, [])
                    entry = None
                    for e in schedule:
                        if e.month == month:
                            entry = e
                            break
                    if entry is None:
                        row.append("-")
                    else:
                        row.append(
                            f"Bal: {format_currency(entry.remaining_balance)}  "
                            f"Eq: {format_percentage(entry.equity_pct)}"
                        )
                amort_table.add_row(*row)

            self.console.print(amort_table)

        # --- Total Cost of Ownership ---
        if fin.total_cost_of_ownership:
            tco_table = Table(
                title="Total Cost of Ownership",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            tco_table.add_column("Year", style="bold", justify="right")
            for scenario in fin.scenarios:
                tco_table.add_column(scenario.name, justify="right")

            # Collect all years across scenarios, show common checkpoints
            all_years: set[int] = set()
            for costs_by_year in fin.total_cost_of_ownership.values():
                all_years.update(costs_by_year.keys())
            target_years = [y for y in sorted(all_years) if y in {5, 10, 15, 20, 30}]
            if not target_years:
                target_years = sorted(all_years)[:5]

            for year in target_years:
                row = [str(year)]
                for scenario in fin.scenarios:
                    costs = fin.total_cost_of_ownership.get(scenario.name, {})
                    val = costs.get(year)
                    row.append(format_currency(val) if val is not None else "-")
                tco_table.add_row(*row)

            self.console.print(tco_table)

    # ------------------------------------------------------------------
    # Appraisal Analysis
    # ------------------------------------------------------------------

    def _render_appraisal(self, appr: AppraisalResult) -> None:
        self.console.print()
        self.console.rule("[bold cyan]Appraisal Analysis[/bold cyan]")

        # --- Value Summary ---
        assessment_color = _color_for_assessment(appr.value_assessment)
        assessment_label = appr.value_assessment.replace("_", " ").title()

        summary_lines = [
            f"Estimated Value Range: "
            f"[bold]{format_currency(appr.estimated_value_low)}[/bold] - "
            f"[bold]{format_currency(appr.estimated_value_high)}[/bold]",
            f"Midpoint Estimate: [bold green]{format_currency(appr.estimated_value_mid)}[/bold green]",
            f"Market $/sqft: {format_currency(appr.price_per_sqft_market)}  |  "
            f"Subject $/sqft: {format_currency(appr.subject_price_per_sqft)}",
            f"Assessment: [{assessment_color}][bold]{assessment_label}[/bold][/{assessment_color}]  |  "
            f"Confidence: [{_color_for_assessment(appr.confidence)}]{appr.confidence.title()}[/{_color_for_assessment(appr.confidence)}]",
        ]

        self.console.print(
            Panel(
                "\n".join(summary_lines),
                title="[bold]Value Assessment[/bold]",
                border_style="green",
                padding=(1, 2),
            )
        )

        # --- Comparable Sales Table ---
        if appr.comparables:
            comp_table = Table(
                title="Comparable Sales",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            comp_table.add_column("#", style="dim", justify="right")
            comp_table.add_column("Address")
            comp_table.add_column("Sale Price", justify="right")
            comp_table.add_column("Adj. Price", justify="right")
            comp_table.add_column("$/sqft", justify="right")
            comp_table.add_column("Sqft", justify="right")
            comp_table.add_column("Bed/Bath", justify="center")
            comp_table.add_column("Sale Date")
            comp_table.add_column("Dist.", justify="right")

            for i, comp in enumerate(appr.comparables, 1):
                adj_price = (
                    format_currency(comp.adjusted_price)
                    if comp.adjusted_price is not None
                    else "-"
                )
                comp_table.add_row(
                    str(i),
                    comp.address.street,
                    format_currency(comp.sale_price),
                    adj_price,
                    format_currency(comp.price_per_sqft),
                    format_number(comp.square_feet),
                    f"{comp.bedrooms}/{comp.bathrooms}",
                    comp.sale_date.isoformat(),
                    f"{comp.distance_miles:.1f} mi",
                )

            self.console.print(comp_table)

    # ------------------------------------------------------------------
    # Neighborhood Analysis
    # ------------------------------------------------------------------

    def _render_neighborhood(self, nbr: NeighborhoodAnalysisResult) -> None:
        self.console.print()
        self.console.rule("[bold cyan]Neighborhood Analysis[/bold cyan]")

        # --- Composite Score ---
        if nbr.composite_score is not None:
            score = nbr.composite_score
            if score >= 70:
                color = "green"
            elif score >= 50:
                color = "yellow"
            else:
                color = "red"
            self.console.print(
                f"  Composite Neighborhood Score: [{color}][bold]{score:.0f}/100[/bold][/{color}]"
                f"  (data completeness: {format_percentage(nbr.data_completeness)})"
            )
            self.console.print()

        # --- Schools ---
        if nbr.schools:
            school_table = Table(
                title="Nearby Schools",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            school_table.add_column("School")
            school_table.add_column("Type", style="dim")
            school_table.add_column("Grades")
            school_table.add_column("Rating", justify="center")
            school_table.add_column("Distance", justify="right")

            for s in nbr.schools:
                if s.rating is not None:
                    if s.rating >= 8:
                        rating_str = f"[green][bold]{s.rating}/10[/bold][/green]"
                    elif s.rating >= 5:
                        rating_str = f"[yellow]{s.rating}/10[/yellow]"
                    else:
                        rating_str = f"[red]{s.rating}/10[/red]"
                else:
                    rating_str = "-"

                distance_str = f"{s.distance_miles:.1f} mi" if s.distance_miles is not None else "-"
                school_table.add_row(
                    s.name,
                    s.type.title(),
                    s.grades or "-",
                    rating_str,
                    distance_str,
                )

            self.console.print(school_table)

        # --- Crime Statistics ---
        if nbr.crime:
            crime = nbr.crime
            crime_table = Table(
                title="Crime Statistics",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            crime_table.add_column("Metric", style="bold")
            crime_table.add_column("Value", justify="right")

            if crime.overall_safety_score is not None:
                score = crime.overall_safety_score
                if score >= 7:
                    color = "green"
                elif score >= 4:
                    color = "yellow"
                else:
                    color = "red"
                crime_table.add_row(
                    "Overall Safety Score",
                    f"[{color}][bold]{score}/10[/bold][/{color}]",
                )
            if crime.violent_crime_rate is not None:
                crime_table.add_row(
                    "Violent Crime Rate",
                    f"{crime.violent_crime_rate:.1f} per 100k",
                )
            if crime.property_crime_rate is not None:
                crime_table.add_row(
                    "Property Crime Rate",
                    f"{crime.property_crime_rate:.1f} per 100k",
                )
            if crime.data_year is not None:
                crime_table.add_row("Data Year", str(crime.data_year))

            self.console.print(crime_table)

        # --- Walkability ---
        if nbr.walkability:
            walk = nbr.walkability
            walk_table = Table(
                title="Walkability & Transit",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            walk_table.add_column("Score Type", style="bold")
            walk_table.add_column("Value", justify="center")
            walk_table.add_column("Rating")

            for label, val in [
                ("Walk Score", walk.walk_score),
                ("Transit Score", walk.transit_score),
                ("Bike Score", walk.bike_score),
            ]:
                if val is not None:
                    if val >= 70:
                        color, rating = "green", "Excellent"
                    elif val >= 50:
                        color, rating = "yellow", "Good"
                    elif val >= 25:
                        color, rating = "yellow", "Fair"
                    else:
                        color, rating = "red", "Poor"
                    walk_table.add_row(
                        label,
                        f"[{color}][bold]{val}[/bold][/{color}]",
                        f"[{color}]{rating}[/{color}]",
                    )

            if walk.description:
                walk_table.add_row("Description", walk.description, "")

            self.console.print(walk_table)

        # --- Flood Risk ---
        if nbr.flood_risk:
            flood = nbr.flood_risk
            risk_color = _risk_color(flood.risk_level)
            flood_lines = [
                f"Risk Level: [{risk_color}][bold]{flood.risk_level.title()}[/bold][/{risk_color}]",
            ]
            if flood.flood_zone:
                flood_lines.append(f"Flood Zone: {flood.flood_zone}")
            flood_lines.append(
                f"In Floodplain: {'[red]Yes[/red]' if flood.in_floodplain else '[green]No[/green]'}"
            )
            flood_lines.append(
                f"Flood Insurance Required: {'[red]Yes[/red]' if flood.flood_insurance_required else '[green]No[/green]'}"
            )
            if flood.recent_disasters:
                flood_lines.append(
                    f"Recent Disasters: [yellow]{flood.recent_disasters}[/yellow]"
                )

            self.console.print(
                Panel(
                    "\n".join(flood_lines),
                    title="[bold]Flood Risk[/bold]",
                    border_style=risk_color,
                    padding=(0, 2),
                )
            )

        # --- Demographics ---
        if nbr.demographics:
            demo = nbr.demographics
            demo_table = Table(
                title="Demographics",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            demo_table.add_column("Metric", style="bold")
            demo_table.add_column("Value", justify="right")

            if demo.total_population is not None:
                demo_table.add_row(
                    "Population", format_number(demo.total_population)
                )
            if demo.median_household_income is not None:
                demo_table.add_row(
                    "Median Household Income",
                    format_currency(demo.median_household_income),
                )
            if demo.median_home_value is not None:
                demo_table.add_row(
                    "Median Home Value",
                    format_currency(demo.median_home_value),
                )
            if demo.population_density is not None:
                demo_table.add_row(
                    "Population Density",
                    f"{format_number(demo.population_density)} per sq mi",
                )

            self.console.print(demo_table)

    # ------------------------------------------------------------------
    # Tax Analysis
    # ------------------------------------------------------------------

    def _render_tax(self, tax: TaxAnalysisResult) -> None:
        self.console.print()
        self.console.rule("[bold cyan]Tax Analysis[/bold cyan]")

        # --- First Home Strategy ---
        if tax.first_home_strategy:
            strat = tax.first_home_strategy
            rec_color = _color_for_assessment(strat.recommendation)

            strat_lines = [
                f"Recommendation: [{rec_color}][bold]{strat.recommendation.upper()}[/bold][/{rec_color}]",
                f"Reason: {strat.recommendation_reason}",
            ]

            if strat.sell_analysis:
                sell = strat.sell_analysis
                strat_lines.append("")
                strat_lines.append("[bold underline]Sell Analysis[/bold underline]")
                strat_lines.append(
                    f"  Estimated Sale Price: {format_currency(sell.estimated_sale_price)}"
                )
                strat_lines.append(
                    f"  Selling Costs: {format_currency(sell.selling_costs)}"
                )
                strat_lines.append(
                    f"  Gross Gain: {format_currency(sell.gross_gain)}"
                )
                strat_lines.append(
                    f"  Exclusion: {format_currency(sell.exclusion_amount)}"
                )
                taxable_color = "green" if sell.taxable_gain <= 0 else "yellow"
                strat_lines.append(
                    f"  Taxable Gain: [{taxable_color}]{format_currency(sell.taxable_gain)}[/{taxable_color}]"
                )
                strat_lines.append(
                    f"  Est. Federal Tax: {format_currency(sell.estimated_federal_tax)}"
                )
                strat_lines.append(
                    f"  Net Proceeds: [bold green]{format_currency(sell.net_proceeds)}[/bold green]"
                )
                res_test = (
                    "[green]Yes[/green]"
                    if sell.meets_primary_residence_test
                    else "[red]No[/red]"
                )
                strat_lines.append(
                    f"  Meets Primary Residence Test: {res_test}"
                )

            if strat.rent_analysis:
                rent = strat.rent_analysis
                strat_lines.append("")
                strat_lines.append("[bold underline]Rent Analysis[/bold underline]")
                strat_lines.append(
                    f"  Monthly Rent Income: {format_currency(rent.monthly_rent)}"
                )
                strat_lines.append(
                    f"  Monthly Mortgage: {format_currency(rent.monthly_mortgage)}"
                )
                cf_color = "green" if rent.monthly_cash_flow >= 0 else "red"
                strat_lines.append(
                    f"  Monthly Cash Flow: [{cf_color}]{format_currency(rent.monthly_cash_flow)}[/{cf_color}]"
                )
                strat_lines.append(
                    f"  Annual Cash Flow: [{cf_color}]{format_currency(rent.annual_cash_flow)}[/{cf_color}]"
                )
                strat_lines.append(
                    f"  Annual Depreciation: {format_currency(rent.annual_depreciation)}"
                )
                strat_lines.append(
                    f"  Tax Benefit (Depreciation): {format_currency(rent.annual_tax_benefit_from_depreciation)}"
                )
                strat_lines.append(
                    f"  Cap Rate: {format_percentage(rent.cap_rate)}"
                )

            strat_lines.append("")
            strat_lines.append(
                f"Sell Net Proceeds: [bold]{format_currency(strat.sell_net_proceeds)}[/bold]  |  "
                f"Rent Annual Net: [bold]{format_currency(strat.rent_annual_net)}[/bold]"
            )

            self.console.print(
                Panel(
                    "\n".join(strat_lines),
                    title="[bold]First Home Strategy[/bold]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

        # --- Mortgage Interest Deduction ---
        mid = tax.mortgage_interest_deduction
        ded_table = Table(
            title="Tax Deductions",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        ded_table.add_column("Deduction", style="bold")
        ded_table.add_column("Annual Amount", justify="right")
        ded_table.add_column("Deductible", justify="right")
        ded_table.add_column("Tax Savings", justify="right")
        ded_table.add_column("Notes")

        ded_table.add_row(
            "Mortgage Interest",
            format_currency(mid.annual_interest_paid),
            format_currency(mid.deductible_amount),
            f"[green]{format_currency(mid.tax_savings)}[/green]",
            f"Marginal rate: {format_percentage(mid.marginal_tax_rate)}",
        )

        ptd = tax.property_tax_deduction
        salt_note = "[red]SALT cap hit[/red]" if ptd.salt_cap_hit else "Within SALT cap"
        ded_table.add_row(
            "Property Tax",
            format_currency(ptd.annual_property_tax),
            format_currency(ptd.deductible_amount),
            f"[green]{format_currency(ptd.tax_savings)}[/green]",
            salt_note,
        )

        self.console.print(ded_table)

        # --- Summary ---
        self.console.print(
            f"  Total Annual Tax Benefit: [bold green]{format_currency(tax.total_annual_tax_benefit)}[/bold green]"
            f"  |  Effective Monthly Cost Reduction: "
            f"[bold green]{format_currency(tax.effective_monthly_cost_reduction)}[/bold green]"
        )

    # ------------------------------------------------------------------
    # Insurance Analysis
    # ------------------------------------------------------------------

    def _render_insurance(self, ins: InsuranceAnalysisResult) -> None:
        self.console.print()
        self.console.rule("[bold cyan]Insurance Analysis[/bold cyan]")

        # --- Homeowners Insurance ---
        ho = ins.homeowners
        ins_table = Table(
            title="Insurance Costs",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        ins_table.add_column("Coverage", style="bold")
        ins_table.add_column("Annual", justify="right")
        ins_table.add_column("Monthly", justify="right")
        ins_table.add_column("Details")

        ins_table.add_row(
            "Homeowners",
            format_currency(ho.annual_premium),
            format_currency(ho.monthly_premium),
            f"Coverage: {format_currency(ho.coverage_amount)}  |  "
            f"Deductible: {format_currency(ho.deductible)}",
        )

        if ins.flood:
            fl = ins.flood
            required_str = "[red]Required[/red]" if fl.required else "Optional"
            ins_table.add_row(
                "Flood",
                format_currency(fl.annual_premium),
                format_currency(fl.annual_premium / 12),
                f"Zone: {fl.flood_zone}  |  {required_str}  |  "
                f"Coverage: {format_currency(fl.coverage_amount)}",
            )

        ins_table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{format_currency(ins.total_annual_insurance)}[/bold]",
            f"[bold]{format_currency(ins.total_monthly_insurance)}[/bold]",
            "",
            style="on grey15",
        )

        self.console.print(ins_table)

        # --- Natural Disaster Risk ---
        dr = ins.disaster_risk
        risk_table = Table(
            title="Natural Disaster Risk Assessment",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
        )
        risk_table.add_column("Hazard", style="bold")
        risk_table.add_column("Risk Level", justify="center")

        for label, level in [
            ("Earthquake", dr.earthquake_risk),
            ("Hurricane", dr.hurricane_risk),
            ("Wildfire", dr.wildfire_risk),
            ("Tornado", dr.tornado_risk),
        ]:
            color = _risk_color(level)
            risk_table.add_row(label, f"[{color}]{level.title()}[/{color}]")

        overall_color = "green" if dr.overall_risk_score <= 3 else ("yellow" if dr.overall_risk_score <= 6 else "red")
        risk_table.add_row(
            "[bold]Overall Risk Score[/bold]",
            f"[{overall_color}][bold]{dr.overall_risk_score}/10[/bold][/{overall_color}]",
            style="on grey15",
        )

        self.console.print(risk_table)

        self.console.print(
            f"  Risk-Adjusted Monthly Housing Cost: "
            f"[bold]{format_currency(ins.risk_adjusted_monthly_cost)}[/bold]"
        )

    # ------------------------------------------------------------------
    # Investment Analysis
    # ------------------------------------------------------------------

    def _render_investment(self, inv: InvestmentAnalysisResult) -> None:
        self.console.print()
        self.console.rule("[bold cyan]Investment Analysis[/bold cyan]")

        # --- Key Metrics ---
        metrics_lines = [
            f"Appreciation Rate: [bold]{format_percentage(inv.appreciation_rate)}[/bold] per year",
        ]
        if inv.irr_on_down_payment is not None:
            irr_color = "green" if inv.irr_on_down_payment > 0 else "red"
            metrics_lines.append(
                f"IRR on Down Payment: [{irr_color}][bold]{format_percentage(inv.irr_on_down_payment)}[/bold][/{irr_color}]"
            )

        nw5_color = "green" if inv.net_worth_impact_5yr >= 0 else "red"
        nw10_color = "green" if inv.net_worth_impact_10yr >= 0 else "red"
        metrics_lines.append(
            f"Net Worth Impact (5yr): [{nw5_color}]{format_currency(inv.net_worth_impact_5yr)}[/{nw5_color}]"
            f"  |  (10yr): [{nw10_color}]{format_currency(inv.net_worth_impact_10yr)}[/{nw10_color}]"
        )

        self.console.print(
            Panel(
                "\n".join(metrics_lines),
                title="[bold]Key Investment Metrics[/bold]",
                border_style="green",
                padding=(0, 2),
            )
        )

        # --- Equity Projections ---
        if inv.total_equity_at_year:
            eq_table = Table(
                title="Equity Projections",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            eq_table.add_column("Year", justify="right", style="bold")
            eq_table.add_column("Total Equity", justify="right")

            for year in sorted(inv.total_equity_at_year.keys()):
                eq_table.add_row(
                    str(year),
                    f"[green]{format_currency(inv.total_equity_at_year[year])}[/green]",
                )

            self.console.print(eq_table)

        # --- Yearly Projections ---
        if inv.yearly_projections:
            proj_table = Table(
                title="Yearly Financial Projections",
                show_header=True,
                header_style="bold magenta",
                border_style="blue",
                padding=(0, 1),
            )
            proj_table.add_column("Year", justify="right", style="bold")
            proj_table.add_column("Home Value", justify="right")
            proj_table.add_column("Equity", justify="right")
            proj_table.add_column("Cumulative Cost", justify="right")
            proj_table.add_column("Tax Benefit", justify="right")
            proj_table.add_column("Net Position", justify="right")

            # Show select years to avoid overwhelming output
            years_to_show = {1, 2, 3, 5, 7, 10, 15, 20, 25, 30}
            for proj in inv.yearly_projections:
                if proj.year not in years_to_show:
                    continue
                net_color = "green" if proj.net_position >= 0 else "red"
                proj_table.add_row(
                    str(proj.year),
                    format_currency(proj.home_value),
                    f"[green]{format_currency(proj.equity)}[/green]",
                    format_currency(proj.cumulative_cost),
                    f"[green]{format_currency(proj.cumulative_tax_benefit)}[/green]",
                    f"[{net_color}]{format_currency(proj.net_position)}[/{net_color}]",
                )

            self.console.print(proj_table)

        # --- Rent vs Buy ---
        if inv.rent_vs_buy:
            rvb = inv.rent_vs_buy
            rec_color = _color_for_assessment(rvb.recommendation)

            rvb_lines = [
                f"Recommendation: [{rec_color}][bold]{rvb.recommendation.upper()}[/bold][/{rec_color}]",
                f"Equivalent Monthly Rent: {format_currency(rvb.monthly_rent_equivalent)}",
                f"Annual Rent Increase: {format_percentage(rvb.annual_rent_increase_pct)}",
            ]
            if rvb.buy_break_even_year is not None:
                rvb_lines.append(
                    f"Buy Break-Even Year: [bold]{rvb.buy_break_even_year}[/bold]"
                )

            self.console.print(
                Panel(
                    "\n".join(rvb_lines),
                    title="[bold]Rent vs Buy[/bold]",
                    border_style=rec_color,
                    padding=(0, 2),
                )
            )

            # Rent vs Buy cost comparison table
            if rvb.rent_total_cost and rvb.buy_total_cost:
                rvb_table = Table(
                    title="Rent vs Buy Cost Comparison",
                    show_header=True,
                    header_style="bold magenta",
                    border_style="blue",
                    padding=(0, 1),
                )
                rvb_table.add_column("Year", justify="right", style="bold")
                rvb_table.add_column("Cumulative Rent", justify="right")
                rvb_table.add_column("Cumulative Buy", justify="right")
                rvb_table.add_column("Difference", justify="right")

                all_years = sorted(
                    set(rvb.rent_total_cost.keys()) & set(rvb.buy_total_cost.keys())
                )
                display_years = [y for y in all_years if y in {1, 3, 5, 7, 10, 15, 20, 30}]
                if not display_years:
                    display_years = all_years[:8]

                for year in display_years:
                    rent_cost = rvb.rent_total_cost[year]
                    buy_cost = rvb.buy_total_cost[year]
                    diff = rent_cost - buy_cost
                    diff_color = "green" if diff > 0 else "red"
                    rvb_table.add_row(
                        str(year),
                        format_currency(rent_cost),
                        format_currency(buy_cost),
                        f"[{diff_color}]{format_currency(diff)}[/{diff_color}]",
                    )

                self.console.print(rvb_table)
