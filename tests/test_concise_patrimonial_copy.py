"""Regression tests for concise presentation, using synthetic portfolio inputs."""

import unittest
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import patch

from backend.institution_patrimonial_report import (
    _asset_attention_lines,
    _display_asset_label,
    _quantitative_items,
    build_institution_patrimonial_report,
)
from backend.jolika_market_context_analysis import (
    JolikaMarketContextItem,
    _conversation_reading,
    _evidence_lines,
    build_market_context_stage,
)
from backend.jolika_master_assumptions_analysis import build_master_assumptions_stage


def structural(weight="0.054"):
    return NS(
        institution="UBS", position_count=32, currencies=("USD",), warnings=(),
        coverage=NS(total_positions=32, positions_with_economic_class=32),
        concentration_by_currency=(NS(currency="USD", top_1_weight=Decimal(weight),
            top_3_weight=Decimal("0.14"), top_5_weight=Decimal("0.21")),),
        economic_allocation_by_currency=(("USD", (
            (NS(value="Ações"), Decimal(60)),
            (NS(value="Renda Fixa"), Decimal(40)),)),),
    )


def quantitative():
    return NS(analyzed_position_count=10, unavailable_position_count=22, lookback_days=252,
        positions=(NS(status="available", annualized_volatility=.35, maximum_drawdown=-.18),))


def operational():
    return NS(executive_reading="Leitura executiva preservada.", overall_level="Alta",
        structural_level="Baixa", quantitative_level="Alta", attention_items=(
            NS(source="QUANTITATIVE", asset_label="Empresa Um", identifier="ALFA", reason="high_volatility"),
            NS(source="QUANTITATIVE", asset_label="Empresa Um", identifier="ALFA", reason="elevated_volatility"),
            NS(source="QUANTITATIVE", asset_label="Empresa Dois", identifier="BETA", reason="deep_drawdown"),
        ))


def market_item(assets=("ALFA",), source="Fonte oficial"):
    return JolikaMarketContextItem(fact_id="test-fact", title="Fato relevante para Alfa",
        affected_assets=assets, intensity="Alta", source=source, evidence="Descrição factual.")


class ConcisePatrimonialCopyTests(unittest.TestCase):
    def report(self):
        with patch("backend.jolika_market_context_analysis.analyze_jolika_market_context", return_value=()):
            return build_institution_patrimonial_report(structural(), quantitative(), operational())

    def test_five_stages_and_institution_scope_are_preserved(self):
        report = self.report()
        self.assertEqual(report.universe, "UBS")
        self.assertEqual(report.scope, "institution")
        self.assertEqual(tuple(s.key for s in report.stages), (
            "diagnosis", "composition", "master_assumptions", "market_context", "final_diagnosis"))
        self.assertEqual(report.stages[0].summary, operational().executive_reading)

    def test_stage_one_is_short_and_does_not_exclude_positions(self):
        stage = self.report().stages[0]
        self.assertIn("32 posições", stage.items[0].reading)
        self.assertIn("não exclui investimentos", stage.items[0].reading)
        self.assertLessEqual(len(stage.items[0].reading.split()), 25)
        self.assertEqual(stage.items[0].confidence, "Parcial")

    def test_stage_two_preserves_percentages_currency_and_limits(self):
        stage = self.report().stages[1]
        self.assertIn("USD", stage.summary)
        visible = " ".join(i.reading for i in stage.items)
        for value in ("60.0%", "40.0%", "5.4%", "14.0%", "21.0%", "35.0%", "18.0%"):
            self.assertIn(value, visible)
        for item in stage.items[-2:]:
            self.assertIn("histórico suficiente", item.reading)
            self.assertIn("252 dias", item.evidence[0])
            self.assertLessEqual(len(item.reading.split()), 25)

    def test_missing_price_history_does_not_produce_fake_metrics(self):
        self.assertEqual(_quantitative_items(NS(positions=())), ())

    def test_stage_three_readings_have_at_most_forty_words(self):
        stage = build_master_assumptions_stage(structural(), quantitative=quantitative())
        self.assertLessEqual(len(stage.summary.split()), 18)
        self.assertEqual(len(stage.items), 5)
        for item in stage.items:
            self.assertLessEqual(len(item.reading.split()), 40, item.title)

    def test_stage_three_keeps_return_goal_and_missing_history(self):
        stage = build_master_assumptions_stage(structural(), quantitative=quantitative())
        self.assertIn("12% ao ano em USD", stage.items[1].reading)
        self.assertIn("não um teto", stage.items[1].reading)
        self.assertIn("precisamos acompanhar o desempenho ao longo do tempo", stage.items[1].reading)
        self.assertIn("Falta histórico", stage.items[4].reading)
        self.assertTrue(all("Regras da JOLIKA v1.0" in i.evidence[0] for i in stage.items))

    def test_concentrated_portfolio_is_not_described_as_automatically_diversified(self):
        s = structural("0.95")
        s.concentration_by_currency[0].top_3_weight = Decimal("0.97")
        s.concentration_by_currency[0].top_5_weight = Decimal("0.99")
        stage = build_master_assumptions_stage(s)
        self.assertNotIn("nenhuma posição domina", stage.items[0].reading)
        self.assertIn("95.0%", stage.items[3].reading)

    def test_stage_three_without_quantitative_history_keeps_limit_visible(self):
        stage = build_master_assumptions_stage(structural())
        self.assertIn("sem deixar nenhum investimento fora da leitura da carteira", stage.items[2].reading)
        self.assertIn("ainda precisa de dados", stage.items[2].reading)

    def test_partial_history_counts_are_not_presented_as_total_analysis_coverage(self):
        stage = build_master_assumptions_stage(structural(), quantitative=quantitative())
        visible = " ".join(i.reading for i in stage.items)
        self.assertNotIn("10 posição", visible)
        self.assertNotIn("22", visible)
        self.assertIn("continua fazendo parte da análise", visible)

    def test_market_reading_keeps_asset_names_and_uncertainty(self):
        text = _conversation_reading(market_item(("ALFA", "BETA")), ())
        self.assertIn("ALFA, BETA", text)
        self.assertIn("ainda não está confirmado", text)
        self.assertLessEqual(len(text.split()), 30)

    def test_macro_reading_keeps_real_exposure_without_inventing_direction(self):
        position = NS(asset_class="Fixed Income", asset_subclass=None,
                      asset_name="US Treasury Note", identifier="UST10Y")
        item = market_item(assets=(), source="Federal Reserve")
        text = _conversation_reading(item, (position,))
        self.assertIn("pode repercutir principalmente em renda fixa", text)
        self.assertNotIn("ações", text)
        self.assertNotIn("favorável", text.casefold())
        self.assertNotIn("desfavorável", text.casefold())
        self.assertLessEqual(len(text.split()), 40)

    def test_market_source_attribution_is_preserved(self):
        item = market_item()
        self.assertEqual(_evidence_lines((item, item)), ("Fontes consultadas: Fonte oficial.",))

    def test_market_without_facts_remains_explicitly_limited(self):
        with patch("backend.jolika_market_context_analysis.analyze_jolika_market_context", return_value=()):
            stage = build_market_context_stage((), ())
        self.assertEqual(stage.status, "limited")
        self.assertEqual(stage.items, ())
        self.assertIn("vamos continuar acompanhando sem forçar uma conclusão", stage.summary)
        self.assertLessEqual(len(stage.summary.split()), 20)

    def test_santander_long_names_are_shortened_without_exposing_isin(self):
        self.assertEqual(
            _display_asset_label("CONSTELLATION ENERGY CORPORATION", "US21037T1097"),
            "Constellation Energy",
        )
        self.assertEqual(
            _display_asset_label("GE VERNOVA INC", "US36828A1016"),
            "GE Vernova",
        )
        self.assertEqual(
            _display_asset_label("ISHARES BITCOIN TRUST ETF", "US46438F1012"),
            "iShares Bitcoin Trust",
        )
        self.assertEqual(_display_asset_label("Empresa Dois", "BETA"), "Empresa Dois (BETA)")

    def test_stage_five_retains_named_assets_and_deduplicates_same_reason(self):
        lines = _asset_attention_lines(operational())
        self.assertEqual(len(lines), 2)
        self.assertIn("Empresa Dois (BETA) — queda recente relevante", lines[0])
        self.assertIn("verificar se o movimento persiste", lines[0])
        self.assertIn("Empresa Um (ALFA) — oscilações recentes elevadas", lines[1])
        stage = self.report().stages[4]
        visible = " ".join(i.reading for i in stage.items)
        self.assertIn("Empresa Um (ALFA)", visible)
        self.assertIn("Empresa Dois (BETA)", visible)
        self.assertEqual(tuple(i.title for i in stage.items), ("O que está bem", "O que merece atenção", "Encaminhamento"))
        self.assertIn("O principal ponto de atenção hoje é Empresa Dois (BETA)", visible)
        self.assertIn("Sugerimos conversar com seu gerente de banco ou Banker", visible)
        self.assertLessEqual(len(lines), 3)
        self.assertNotIn("Pontos de evolução", visible)
        self.assertNotIn("Destaques", visible)
        self.assertNotIn("recomend", visible.casefold())


if __name__ == "__main__":
    unittest.main()
