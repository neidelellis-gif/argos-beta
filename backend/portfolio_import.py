"""Session-only orchestration for importing portfolios through connectors."""

from pathlib import Path
from typing import Dict, Iterable, Tuple

from backend.connectors import registry
from backend.dashboard import build_dashboard
from backend.models import PortfolioPosition
from backend.portfolio_diagnostics import diagnose_institution


SUPPORTED_EXTENSIONS = frozenset(
    extension
    for connector in registry.active()
    for extension in connector.supported_extensions
)


def _load_recognized_file(file_path: Path) -> Tuple[PortfolioPosition, ...]:
    """Return MPU positions from the single connector that recognizes a file."""
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Arquivo inválido: {file_path.name}. Use CSV, XLS ou XLSX."
        )

    matches = []
    for connector in registry.for_extension(file_path, active_only=True):
        try:
            if not connector.recognize(file_path):
                continue
            positions = connector.load_positions(file_path)
        except (OSError, ValueError):
            continue
        if positions:
            matches.append(positions)

    if len(matches) != 1:
        raise ValueError(f"Instituição não reconhecida: {file_path.name}.")
    return matches[0]


def import_portfolios(file_paths: Iterable[Path]) -> Dict:
    """Import and diagnose every institution before building the dashboard."""
    paths = tuple(file_paths)
    if not paths:
        raise ValueError("Envie ao menos um arquivo para importação.")

    positions_by_institution: dict[str, list[PortfolioPosition]] = {}
    imported_files: list[dict[str, str | int]] = []
    for path in paths:
        positions = _load_recognized_file(path)
        institution = positions[0].institution
        positions_by_institution.setdefault(institution, []).extend(positions)
        imported_files.append({
            "name": path.name,
            "institution": institution,
            "position_count": len(positions),
        })

    diagnostics = []
    all_positions: list[PortfolioPosition] = []
    for institution in sorted(positions_by_institution):
        institution_positions = tuple(positions_by_institution[institution])
        diagnostics.append(diagnose_institution(institution_positions))
        all_positions.extend(institution_positions)

    # Consolidation is deliberately deferred until every diagnostic is ready.
    dashboard = build_dashboard(all_positions)
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
