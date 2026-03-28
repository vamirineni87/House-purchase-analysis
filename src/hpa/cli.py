"""Command-line interface for the Home Purchase Analysis tool.

Entry point is the ``cli`` group, registered as the ``hpa`` console script
in ``pyproject.toml``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hpa.config import AppConfig, load_config
from hpa.models.property import Address, PropertyDetails
from hpa.report.generator import AnalysisResults, ReportGenerator
from hpa.utils.geo import parse_address, validate_state

console = Console()
logger = logging.getLogger("hpa")

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "api_keys": {
        "fred": "",
        "rentcast": "",
        "greatschools": "",
        "walkscore": "",
        "api_ninjas": "",
        "census": "",
    },
    "defaults": {},
}


def _ensure_config(path: str) -> AppConfig:
    """Load configuration, creating a sensible default file if missing."""
    config_path = Path(path)
    if not config_path.is_file():
        # Try to copy from config.example.yaml in the working directory.
        example_path = Path("config.example.yaml")
        if example_path.is_file():
            config_path.write_text(example_path.read_text())
            console.print(
                f"[yellow]Created {config_path} from config.example.yaml[/yellow]"
            )
        else:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as fh:
                yaml.dump(_DEFAULT_CONFIG, fh, default_flow_style=False)
            console.print(
                f"[yellow]Created default {config_path} -- "
                "edit it to add your API keys[/yellow]"
            )
    return load_config(str(config_path))


def _build_address(address_str: str) -> Address:
    """Parse a raw address string into an ``Address`` model."""
    parts = parse_address(address_str)
    if not parts["city"] or not parts["state"]:
        raise click.BadParameter(
            "Address must be in the format 'Street, City, ST ZIP' "
            f"(got: {address_str!r})"
        )
    if not validate_state(parts["state"]):
        raise click.BadParameter(
            f"Unrecognized state abbreviation: {parts['state']!r}"
        )
    return Address(
        street=parts["street"],
        city=parts["city"],
        state=parts["state"],
        zip_code=parts["zip_code"],
    )


def _build_property(
    address: Address,
    price: float,
    sqft: int,
    beds: int,
    baths: float,
    year_built: Optional[int],
    hoa: float,
    lot_size: Optional[int],
    garage: int,
    stories: int,
    property_type: str,
) -> PropertyDetails:
    return PropertyDetails(
        address=address,
        list_price=price,
        bedrooms=beds,
        bathrooms=baths,
        square_feet=sqft,
        lot_size_sqft=lot_size,
        year_built=year_built,
        property_type=property_type,
        hoa_monthly=hoa,
        garage_spaces=garage,
        stories=stories,
    )


# -----------------------------------------------------------------------
# CLI group
# -----------------------------------------------------------------------


@click.group()
@click.version_option(package_name="hpa")
def cli() -> None:
    """Home Purchase Analysis Tool -- comprehensive property evaluation."""


# -----------------------------------------------------------------------
# hpa analyze
# -----------------------------------------------------------------------


@cli.command()
@click.argument("address")
@click.option("--price", required=True, type=float, help="Listing price.")
@click.option("--sqft", required=True, type=int, help="Square footage.")
@click.option("--beds", required=True, type=int, help="Number of bedrooms.")
@click.option("--baths", required=True, type=float, help="Number of bathrooms.")
@click.option("--year-built", type=int, default=None, help="Year the property was built.")
@click.option("--hoa", type=float, default=0.0, help="Monthly HOA fee.")
@click.option("--lot-size", type=int, default=None, help="Lot size in sq ft.")
@click.option("--garage", type=int, default=0, help="Garage spaces.")
@click.option("--stories", type=int, default=1, help="Number of stories.")
@click.option(
    "--property-type",
    type=click.Choice(
        ["single_family", "condo", "townhouse", "multi_family"],
        case_sensitive=False,
    ),
    default="single_family",
    help="Property type.",
)
@click.option(
    "--down-payment-pct",
    multiple=True,
    type=float,
    help="Down-payment percentage(s) to evaluate (repeatable). Default: 0.10 0.20.",
)
@click.option(
    "--loan-term",
    multiple=True,
    type=int,
    help="Loan term(s) in years to evaluate (repeatable). Default: 15 30.",
)
@click.option(
    "--output",
    "output_formats",
    multiple=True,
    type=click.Choice(["terminal", "html", "json", "pdf"], case_sensitive=False),
    help="Output format(s) (repeatable). Default: terminal html json.",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="./reports",
    show_default=True,
    help="Directory for generated reports.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(),
    default="config.yaml",
    show_default=True,
    help="Path to YAML configuration file.",
)
@click.option(
    "--skip-api",
    is_flag=True,
    default=False,
    help="Skip all analyzers that require external API calls.",
)
def analyze(
    address: str,
    price: float,
    sqft: int,
    beds: int,
    baths: float,
    year_built: Optional[int],
    hoa: float,
    lot_size: Optional[int],
    garage: int,
    stories: int,
    property_type: str,
    down_payment_pct: tuple[float, ...],
    loan_term: tuple[int, ...],
    output_formats: tuple[str, ...],
    output_dir: str,
    config_path: str,
    skip_api: bool,
) -> None:
    """Analyze a property for purchase.

    ADDRESS should be formatted as "Street, City, ST ZIP".

    Example:

        hpa analyze "123 Main St, Austin, TX 78701" --price 450000 --sqft 2000 --beds 3 --baths 2.5
    """
    # ---- defaults for tuple options ----
    if not down_payment_pct:
        down_payment_pct = (0.10, 0.20)
    if not loan_term:
        loan_term = (15, 30)
    if not output_formats:
        output_formats = ("terminal", "html", "json")

    # ---- config ----
    config = _ensure_config(config_path)

    # ---- build models ----
    try:
        addr = _build_address(address)
    except click.BadParameter as exc:
        console.print(f"[red]Error:[/red] {exc.format_message()}")
        raise SystemExit(1) from exc

    prop = _build_property(
        address=addr,
        price=price,
        sqft=sqft,
        beds=beds,
        baths=baths,
        year_built=year_built,
        hoa=hoa,
        lot_size=lot_size,
        garage=garage,
        stories=stories,
        property_type=property_type,
    )

    console.print(
        Panel(
            f"[bold]{addr.street}[/bold]\n"
            f"{addr.city}, {addr.state} {addr.zip_code}\n"
            f"${price:,.0f}  |  {sqft:,} sqft  |  {beds}bd / {baths}ba",
            title="Property Under Analysis",
            border_style="cyan",
        )
    )

    results = AnalysisResults()

    # ---- run analyzers ----
    _run_analyzers(prop, config, results, skip_api, down_payment_pct, loan_term)

    # ---- generate reports ----
    with console.status("[bold green]Generating reports..."):
        generator = ReportGenerator(output_dir=output_dir)
        outputs = generator.generate_all(
            property_details=prop,
            results=results,
            formats=list(output_formats),
        )

    # ---- summary ----
    console.print()
    summary_table = Table(title="Generated Reports", show_lines=True)
    summary_table.add_column("Format", style="bold")
    summary_table.add_column("Path")
    for fmt, path in outputs.items():
        summary_table.add_row(fmt, str(path) if path else "(printed to terminal)")
    console.print(summary_table)


def _run_analyzers(
    prop: PropertyDetails,
    config: AppConfig,
    results: AnalysisResults,
    skip_api: bool,
    down_payment_pcts: tuple[float, ...],
    loan_terms: tuple[int, ...],
) -> None:
    """Run each analyzer sequentially, catching errors per-analyzer."""

    analyzers_plan: list[tuple[str, str, bool]] = [
        ("financial", "Financial Analysis", False),
        ("appraisal", "Appraisal Analysis", True),
        ("neighborhood", "Neighborhood Analysis", True),
        ("tax", "Tax Analysis", False),
        ("insurance", "Insurance Analysis", False),
        ("investment", "Investment Analysis", False),
    ]

    for field_name, label, needs_api in analyzers_plan:
        if needs_api and skip_api:
            console.print(f"  [dim]Skipping {label} (--skip-api)[/dim]")
            continue

        with console.status(f"[bold green]Running {label}..."):
            try:
                result = _dispatch_analyzer(
                    field_name, prop, config, down_payment_pcts, loan_terms, results
                )
                setattr(results, field_name, result)
                console.print(f"  [green]:heavy_check_mark:[/green] {label}")
            except Exception as exc:
                console.print(f"  [red]:cross_mark: {label} failed:[/red] {exc}")
                logger.debug("Analyzer %s failed", field_name, exc_info=True)


def _dispatch_analyzer(
    name: str,
    prop: PropertyDetails,
    config: AppConfig,
    down_payment_pcts: tuple[float, ...],
    loan_terms: tuple[int, ...],
    partial_results: AnalysisResults,
):
    """Instantiate and run the named analyzer, returning its result model."""

    if name == "financial":
        from hpa.analysis.financial import FinancialAnalyzer

        analyzer = FinancialAnalyzer()
        return analyzer.analyze(prop, config)

    if name == "appraisal":
        from hpa.analysis.appraisal import AppraisalAnalyzer

        analyzer = AppraisalAnalyzer()
        return analyzer.analyze(prop, config)

    if name == "neighborhood":
        from hpa.analysis.neighborhood import NeighborhoodAnalyzer

        analyzer = NeighborhoodAnalyzer()
        return analyzer.analyze(prop, config)

    if name == "tax":
        from hpa.analysis.tax import TaxAnalyzer

        analyzer = TaxAnalyzer()
        return analyzer.analyze(prop, config)

    if name == "insurance":
        from hpa.analysis.insurance import InsuranceAnalyzer

        analyzer = InsuranceAnalyzer()
        return analyzer.analyze(prop, config)

    if name == "investment":
        from hpa.analysis.investment import InvestmentAnalyzer

        analyzer = InvestmentAnalyzer()
        return analyzer.analyze(prop, config)

    raise ValueError(f"Unknown analyzer: {name}")


# -----------------------------------------------------------------------
# hpa rates
# -----------------------------------------------------------------------


@cli.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(),
    default="config.yaml",
    show_default=True,
    help="Path to YAML configuration file.",
)
def rates(config_path: str) -> None:
    """Fetch and display current mortgage rates from the FRED API."""
    config = _ensure_config(config_path)

    if not config.api_keys.fred:
        console.print(
            "[red]Error:[/red] FRED API key is required. "
            "Set it in config.yaml or via the HPA_FRED environment variable."
        )
        raise SystemExit(1)

    from hpa.api.fred import FredClient

    async def _fetch() -> dict[int, Optional[float]]:
        client = FredClient(api_key=config.api_keys.fred)
        results: dict[int, Optional[float]] = {}
        try:
            for term in (30, 15):
                rate = await client.get_current_rate(term)
                results[term] = rate
        finally:
            await client.close()
        return results

    with console.status("[bold green]Fetching mortgage rates from FRED..."):
        rate_data = asyncio.run(_fetch())

    table = Table(title="Current Mortgage Rates (FRED)", show_lines=True)
    table.add_column("Loan Term", style="bold", justify="center")
    table.add_column("Rate", justify="center")

    for term in (30, 15):
        rate = rate_data.get(term)
        if rate is not None:
            table.add_row(f"{term}-year fixed", f"{rate * 100:.2f}%")
        else:
            table.add_row(f"{term}-year fixed", "[dim]unavailable[/dim]")

    console.print(table)


# -----------------------------------------------------------------------
# hpa compare
# -----------------------------------------------------------------------


@cli.command()
@click.option(
    "--file",
    "properties_file",
    required=True,
    type=click.Path(exists=True),
    help="YAML file listing properties to compare.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(),
    default="config.yaml",
    show_default=True,
    help="Path to YAML configuration file.",
)
def compare(properties_file: str, config_path: str) -> None:
    """Compare multiple properties side-by-side from a YAML file.

    The YAML file should contain a top-level ``properties`` list, each with
    at least ``address``, ``price``, ``sqft``, ``beds``, and ``baths``.
    """
    config = _ensure_config(config_path)

    # ---- load properties file ----
    with open(properties_file, "r") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict) or "properties" not in raw:
        console.print(
            "[red]Error:[/red] YAML file must contain a top-level "
            "'properties' list."
        )
        raise SystemExit(1)

    raw_props = raw["properties"]
    if not isinstance(raw_props, list) or len(raw_props) < 2:
        console.print(
            "[red]Error:[/red] At least two properties are required for comparison."
        )
        raise SystemExit(1)

    # ---- build PropertyDetails list ----
    properties: list[PropertyDetails] = []
    for idx, entry in enumerate(raw_props, start=1):
        try:
            addr = _build_address(entry["address"])
            prop = PropertyDetails(
                address=addr,
                list_price=float(entry["price"]),
                bedrooms=int(entry.get("beds", entry.get("bedrooms", 3))),
                bathrooms=float(entry.get("baths", entry.get("bathrooms", 2.0))),
                square_feet=int(entry["sqft"]),
                lot_size_sqft=entry.get("lot_size"),
                year_built=entry.get("year_built"),
                property_type=entry.get("property_type", "single_family"),
                hoa_monthly=float(entry.get("hoa", 0)),
                garage_spaces=int(entry.get("garage", 0)),
                stories=int(entry.get("stories", 1)),
            )
            properties.append(prop)
        except (KeyError, ValueError, TypeError) as exc:
            console.print(
                f"[red]Error in property #{idx}:[/red] {exc}"
            )
            raise SystemExit(1) from exc

    # ---- run comparison ----
    from hpa.analysis.comparison import ComparisonAnalyzer

    with console.status("[bold green]Running comparison analysis..."):
        try:
            analyzer = ComparisonAnalyzer()
            comparison = analyzer.analyze(properties, config)
        except Exception as exc:
            console.print(f"[red]Comparison failed:[/red] {exc}")
            logger.debug("Comparison analysis failed", exc_info=True)
            raise SystemExit(1) from exc

    # ---- display results ----
    table = Table(title="Property Comparison", show_lines=True)
    table.add_column("Rank", style="bold", justify="center")
    table.add_column("Address", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("$/sqft", justify="right")
    table.add_column("Monthly Pmt", justify="right")
    table.add_column("Total Score", justify="center")
    table.add_column("Pros")
    table.add_column("Cons")

    for rank, address_str in enumerate(comparison.ranking, start=1):
        score = next(
            (p for p in comparison.properties if p.address == address_str),
            None,
        )
        if score is None:
            continue
        table.add_row(
            str(rank),
            score.address,
            f"${score.monthly_payment * 360:,.0f}",  # rough total
            f"${score.price_per_sqft:,.0f}",
            f"${score.monthly_payment:,.0f}",
            f"{score.total_score:.1f}",
            "\n".join(f"+ {p}" for p in score.pros[:3]),
            "\n".join(f"- {c}" for c in score.cons[:3]),
        )

    console.print(table)

    console.print(
        Panel(
            f"[bold green]Best value:[/bold green] {comparison.best_value}",
            border_style="green",
        )
    )


# -----------------------------------------------------------------------
# Entry point (for python -m hpa.cli)
# -----------------------------------------------------------------------

if __name__ == "__main__":
    cli()
