from backend.connectors.ubs_connector import load_positions as load_ubs
from backend.connectors.santander_connector import load_positions as load_santander
from backend.consolidation.engine import consolidate_accounts

SANTANDER_FILE = "data/santander/your-positions-4005106-34.xlsx"


def print_money(value):
    return f"US$ {value:,.2f}"


def main():
    ubs_positions = load_ubs()
    ubs_total = sum(p["value"] for p in ubs_positions)

    santander_positions, _ = load_santander(SANTANDER_FILE)
    santander_total = sum(p["value"] for p in santander_positions)

    jolika = consolidate_accounts(
        [
            {
                "name": "UBS",
                "total": ubs_total,
                "positions": ubs_positions,
            },
            {
                "name": "Santander",
                "total": santander_total,
                "positions": santander_positions,
            },
        ]
    )

    print("=" * 72)
    print("ARGOS ALPHA")
    print("=" * 72)
    print()
    print("JOLIKA CONSOLIDADA")
    print()
    print(f"UBS...............{print_money(ubs_total)}")
    print(f"Santander.........{print_money(santander_total)}")
    print("-" * 72)
    print(f"TOTAL.............{print_money(jolika['total'])}")
    print()
    print("=" * 72)
    print("TOP 20 POSIÇÕES CONSOLIDADAS")
    print("=" * 72)

    for position in jolika["positions"][:20]:
        print(
            f"{position['symbol'][:28]:28} "
            f"{print_money(position['total_value']):>16} "
            f"{position['weight']:6.2f}%"
        )

        for bank, value in sorted(position["accounts"].items()):
            print(f"  {bank:<12} {print_money(value):>16}")

        print()


if __name__ == "__main__":
    main()
