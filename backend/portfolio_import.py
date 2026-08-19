"""Session-only orchestration for importing portfolios through connectors."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, Tuple

from backend.asset_resolution import (
    collect_unresolved_jolika_assets,
    resolve_jolika_positions,
)
from backend.connectors import registry
from backend.dashboard import build_dashboard
from backend.models import PortfolioPosition
from backend.portfolio_classification import classify_jolika_positions
from backend.portfolio_diagnostics import diagnose_institution


logger = logging.getLogger("argos.import")


def _configure_import_logger():
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _log_import(message, **details):
    _configure_import_logger()
    detail_text = " ".join(f"{key}={value!r}" for key, value in sorted(details.items()))
    logger.info("%s%s", message, f" {detail_text}" if detail_text else "")


SUPPORTED_EXTENSIONS = frozenset(
    extension
    for connector in registry.active()
    for extension in connector.supported_extensions
)


def _load_recognized_file(file_path: Path) -> Tuple[PortfolioPosition, ...]:
    """Return MPU positions from the single connector that recognizes a file."""
    _log_import(
        "received portfolio file",
        file_name=file_path.name,
        suffix=file_path.suffix.lower(),
    )
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Arquivo inválido: {file_path.name}. Use CSV, XLS ou XLSX.")

    matches = []
    for connector in registry.for_extension(file_path, active_only=True):
        try:
            recognized = connector.recognize(file_path)
            _log_import(
                "connector recognition result",
                file_name=file_path.name,
                connector_id=connector.connector_id,
                institution=connector.institution,
                recognized=recognized,
            )
            if not recognized:
                continue
            _log_import(
                "calling connector.load_positions",
                file_name=file_path.name,
                connector_id=connector.connector_id,
                institution=connector.institution,
            )
            positions = resolve_jolika_positions(
                classify_jolika_positions(connector.load_positions(file_path))
            )
            unresolved_assets = collect_unresolved_jolika_assets(positions)
            total_market_value = sum(position.market_value for position in positions)
            _log_import(
                "connector.load_positions returned",
                file_name=file_path.name,
                connector_id=connector.connector_id,
                institution=connector.institution,
                position_count=len(positions),
                total_market_value=str(total_market_value),
                ten_thousand_sources=[
                    position.asset_name
                    for position in positions
                    if position.market_value == Decimal("10000")
                ],
                unresolved_asset_count=len(unresolved_assets),
                unresolved_asset_keys=[asset.stable_key for asset in unresolved_assets],
            )
        except (OSError, ValueError, KeyError) as exc:
            _log_import(
                "connector skipped after error",
                file_name=file_path.name,
                connector_id=connector.connector_id,
                institution=connector.institution,
                error=str(exc),
            )
            continue
        if positions:
            matches.append(positions)

    if len(matches) != 1:
        _log_import(
            "file recognition ambiguous or empty",
            file_name=file_path.name,
            match_count=len(matches),
        )
        raise ValueError(f"Instituição não reconhecida: {file_path.name}.")
    _log_import(
        "file recognized and loaded",
        file_name=file_path.name,
        position_count=len(matches[0]),
    )
    return matches[0]


def import_portfolios(file_paths: Iterable[Path]) -> Dict:
    """Import and diagnose every institution before building the dashboard."""
    paths = tuple(file_paths)
    if not paths:
        raise ValueError("Envie ao menos um arquivo para importação.")

    positions_by_institution: dict[str, list[PortfolioPosition]] = {}
    imported_files: list[dict[str, str | int]] = []
    for path in paths:
        _log_import("starting portfolio import file", file_name=path.name)
        positions = _load_recognized_file(path)
        institution = positions[0].institution
        positions_by_institution.setdefault(institution, []).extend(positions)
        imported_files.append(
            {
                "name": path.name,
                "institution": institution,
                "position_count": len(positions),
            }
        )

    diagnostics = []
    all_positions: list[PortfolioPosition] = []
    for institution in sorted(positions_by_institution):
        institution_positions = tuple(positions_by_institution[institution])
        diagnostics.append(diagnose_institution(institution_positions))
        all_positions.extend(institution_positions)

    # Consolidation is deliberately deferred until every diagnostic is ready.
    dashboard = build_dashboard(
        all_positions,
        last_import_at=datetime.now(timezone.utc),
    )
    _log_import(
        "portfolio import dashboard built",
        total_positions=len(all_positions),
        total_market_value=str(
            sum(position.market_value for position in all_positions)
        ),
        institutions=sorted(positions_by_institution),
    )
    return {
        "positions": tuple(all_positions),
        "files": imported_files,
        "diagnostics": [
            {
                "institution": diagnostic.institution,
                "position_count": diagnostic.position_count,
                "warnings": list(diagnostic.data_quality_warnings),
            }
            for diagnostic in diagnostics
        ],
        "dashboard": dashboard,
    }
