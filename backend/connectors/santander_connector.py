from openpyxl import load_workbook
import sys
import warnings

warnings.filterwarnings("ignore", category=UserWarning)


def to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None


BLOCKS = [
    ("Renda Fixa", 18, 21, 19, 23),
    ("Renda Fixa", 25, 27, 19, 23),
    ("Renda Fixa", 31, 31, 12, 16),
    ("Ação", 37, 46, 12, 16),
    ("Ação", 50, 50, 12, 16),
    ("Ação", 54, 54, 12, 16),
    ("ETF/Fundo", 58, 62, 12, 16),
    ("ETF/Fundo", 66, 67, 12, 16),
    ("ETF/Fundo", 71, 71, 12, 16),
    ("Alternativos", 77, 78, 12, 16),
    ("Alternativos", 82, 85, 12, 13),
    ("Caixa", 91, 95, 5, 9),
]


def load_positions(file_path):
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active

    expected_total = to_float(ws["B13"].value)
    positions = []

    for asset_class, start_row, end_row, value_idx, weight_idx in BLOCKS:
        for row_number in range(start_row, end_row + 1):
            row = list(ws.iter_rows(
                min_row=row_number,
                max_row=row_number,
                values_only=True
            ))[0]

            name = row[0]
            value = to_float(row[value_idx])
            weight = to_float(row[weight_idx])

            if name is None or value is None:
                continue

            positions.append({
                "symbol": str(name),
                "name": str(name),
                "class": asset_class,
                "value": value,
                "weight": weight or 0.0,
            })

    return positions, expected_total


if __name__ == "__main__":
    file_path = sys.argv[1]
    positions, expected_total = load_positions(file_path)

    total = sum(p["value"] for p in positions)
    diff = total - expected_total
    diff_pct = diff / expected_total * 100

    print("=" * 60)
    print("SANTANDER CONNECTOR v4.1")
    print("=" * 60)
    print(f"Posições lidas      : {len(positions)}")
    print(f"Patrimônio lido     : US$ {total:,.2f}")
    print(f"Patrimônio relatório: US$ {expected_total:,.2f}")
    print(f"Diferença           : US$ {diff:,.2f} ({diff_pct:.4f}%)")
    print("=" * 60)