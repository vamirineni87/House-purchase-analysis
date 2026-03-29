"""PIPA CLI — power-user tool for property intelligence."""

from __future__ import annotations

import asyncio

import click
import uvicorn
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="pipa")
def cli():
    """PIPA — Property Intelligence Platform Analysis."""
    pass


@cli.command()
@click.option("--host", default="127.0.0.1", help="Server host")
@click.option("--port", default=8000, help="Server port")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool):
    """Start the PIPA API server."""
    console.print(f"[bold green]Starting PIPA server on {host}:{port}[/]")
    uvicorn.run(
        "pipa.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@cli.command()
def dbinfo():
    """Show database status and table counts."""

    async def _run():
        from pipa.core.dependencies import get_engine
        from pipa.core.database import healthcheck
        from sqlalchemy import text

        engine = get_engine()
        ok = await healthcheck(engine)
        console.print(f"Database healthy: [{'green' if ok else 'red'}]{ok}[/]")

        async with engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alembic%' ORDER BY name"
            ))
            tables = result.fetchall()

        table = Table(title="Database Tables")
        table.add_column("Table", style="cyan")
        table.add_column("Rows", justify="right")

        async with engine.begin() as conn:
            for (tname,) in tables:
                result = await conn.execute(text(f'SELECT COUNT(*) FROM "{tname}"'))
                count = result.scalar()
                table.add_row(tname, str(count))

        console.print(table)
        await engine.dispose()

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
