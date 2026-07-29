import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from backend.connectors.santander_connector import inspect_excel_export, load_positions, recognize


class SantanderExcelInspectionTests(unittest.TestCase):
    def create_workbook(self, sheets):
        temp_file = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        temp_file.close()
        path = Path(temp_file.name)
        workbook_sheets = []
        relationships = []

        with zipfile.ZipFile(path, "w") as archive:
            for sheet_index, (title, rows) in enumerate(sheets, start=1):
                workbook_sheets.append(
                    f'<sheet name="{escape(title)}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>'
                )
                relationships.append(
                    f'<Relationship Id="rId{sheet_index}" '
                    f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    f'Target="worksheets/sheet{sheet_index}.xml"/>'
                )
                row_xml = []
                for row_index, row in enumerate(rows, start=1):
                    cells = []
                    for column_index, value in enumerate(row, start=1):
                        if value is None:
                            continue
                        column = chr(ord("A") + column_index - 1)
                        if isinstance(value, str):
                            cells.append(
                                f'<c r="{column}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                            )
                        else:
                            cells.append(f'<c r="{column}{row_index}"><v>{value}</v></c>')
                    row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
                archive.writestr(
                    f"xl/worksheets/sheet{sheet_index}.xml",
                    '<?xml version="1.0"?><worksheet '
                    'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>',
                )

            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook '
                'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships '
                'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'{"".join(relationships)}</Relationships>',
            )

        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_counts_only_positions_between_header_and_total(self):
        path = self.create_workbook([
            ("Capa", [["Relatório Santander"]]),
            ("Posições", [
                ["RESUMO DE ATIVOS"],
                ["Observação"],
                ["NOME DO ATIVO", "SALDO MOEDA REFERÊNCIA", "PESO DA CONTA (%)"],
                ["Ativo A", 100, 10],
                ["Ativo B", 200, 20],
                ["Ativo sem saldo", None, 0],
                ["TOTAL", 300, 30],
                ["Fora da tabela", 999, 99],
            ]),
        ])

        self.assertEqual(inspect_excel_export(path), {
            "source": "Santander Excel Export",
            "position_count": 2,
        })

    def test_stops_counting_at_first_blank_row_after_table_starts(self):
        path = self.create_workbook([("Export", [
            ["RESUMO DE ATIVOS"],
            ["NOME DO ATIVO", "SALDO NA MOEDA DE REFERÊNCIA", "% DO TOTAL"],
            ["Ativo A", 100, 10],
            [None, None, None],
            ["Outra seção", 200, 20],
        ])])

        self.assertEqual(inspect_excel_export(path)["position_count"], 1)

    def test_official_connector_reads_xlsx_with_its_internal_parser(self):
        path = self.create_workbook([("Posições", [
            ["RESUMO DE ATIVOS"],
            [
                "NOME DO ATIVO",
                "ISIN",
                "SALDO MOEDA REFERÊNCIA",
                "PESO DA CONTA (%)",
                "MOEDA",
            ],
            ["Ativo sintético", "US0000000001", 250.25, 100, "USD"],
            ["TOTAL", None, 250.25, 100, "USD"],
        ])])

        self.assertTrue(recognize(path))
        positions = load_positions(path)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].asset_name, "Ativo sintético")

    def test_rejects_workbook_without_asset_summary(self):
        path = self.create_workbook([("Export", [["OUTRA SEÇÃO"]])])

        with self.assertRaisesRegex(ValueError, "RESUMO DE ATIVOS"):
            inspect_excel_export(path)


if __name__ == "__main__":
    unittest.main()
