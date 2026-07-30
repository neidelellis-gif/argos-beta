from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from inspect import signature
from collections.abc import Callable, Iterable
from typing import cast

import backend.daily.experience as experience_module
import pytest
from backend.daily.cache import DailyCache
from backend.daily.context_service import (
    DAILY_LOOKBACK_HOURS,
    AgendaEvent,
    DailyContextService,
    MarketEvent,
)
from backend.daily.experience import PANORAMA_TOPICS, build_daily_experience
from backend.daily.orchestrator import DailyOrchestrator
from backend.daily.providers import ExternalDataResult, FinnhubDailyProvider
from backend.daily.registry import (
    DailyProviderRegistry,
    build_default_registry,
    register_daily_provider,
)
from backend.daily.transformations import build_analyses, build_priorities
from backend.models import PortfolioOwner, PortfolioPosition
from dataclasses import FrozenInstanceError, replace

from backend.daily_brief import DailyPriorityLevel, ImportantFact
from backend.daily_experience import (
    DailyBlockType,
    DailyBlockVisibility,
    DailyExperienceComposer,
    DailyExperienceError,
    DailyExperienceStatus,
    DailyGreetingPeriod,
)
from backend.daily_orchestrator import (
    DailyOrchestrationError,
    DailyOrchestrator as OfficialDailyOrchestrator,
)
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshotBuilder
from backend.daily_priority import DailyPriorityAction, DailyPriorityEngine
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    ImportantFactsEngine,
    ImportantFactsResult,
)
from backend.portfolio_impact import PortfolioImpactEngine

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)


def test_experience_public_signature_is_preserved():
    parameters = signature(build_daily_experience).parameters

    assert tuple(parameters) == (
        "positions", "current_date", "now", "context_service",
    )
    assert parameters["positions"].default is parameters["positions"].empty
    assert all(
        parameters[name].default is None
        for name in ("current_date", "now", "context_service")
    )


def test_experience_delegates_all_arguments_to_orchestrator(monkeypatch):
    positions = (object(),)
    current_date = date(2026, 7, 28)
    context_service = object()
    expected = {"official": "daily-contract"}
    calls = []

    class OrchestratorSpy:
        def __init__(self, context_service=None):
            calls.append(("init", context_service))

        def build(self, positions=(), current_date=None, now=None):
            calls.append(("build", positions, current_date, now))
            return expected

    monkeypatch.setattr(experience_module, "DailyOrchestrator", OrchestratorSpy)

    result = build_daily_experience(
        cast(Iterable[PortfolioPosition], positions),
        current_date,
        NOW,
        cast(DailyContextService, context_service),
    )

    assert result is expected
    assert calls == [
        ("init", context_service),
        ("build", positions, current_date, NOW),
    ]


def test_experience_without_arguments_preserves_public_behavior(monkeypatch):
    calls = []
    monkeypatch.setattr(
        experience_module,
        "DailyOrchestrator",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(TypeError, match="positions"):
        cast(Callable[..., dict], build_daily_experience)()

    assert calls == []


def position(identifier, name=None, institution="UBS"):
    return PortfolioPosition(institution, PortfolioOwner.JOLIKA, None, None, None, name or identifier, identifier,
        "ticker", None, None, Decimal("100"), "USD", None, None, f"{institution}.csv")


def fact(identifier, hours, priority="Baixa", assets=(), category="Mercados", macro=False):
    return MarketEvent(identifier, f"Fato {identifier}", category, "Fonte real simulada",
        NOW - timedelta(hours=hours), priority, f"Resumo {identifier}", assets, macro)


def agenda(identifier, hours, assets=()):
    return AgendaEvent(identifier, f"Evento {identifier}", "Resultados",
        NOW + timedelta(hours=hours), "Fonte real simulada", "Moderada", assets)


class Provider:
    def __init__(self, facts=(), agenda=(), fail=False, name="test"):
        self.facts, self.agenda, self.fail, self.calls = facts, agenda, fail, 0
        self.name = name

    def _result(self, items):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provedor fora do ar")
        return ExternalDataResult("available" if items else "empty", tuple(items))

    def fetch_facts(self, now, positions): return self._result(self.facts)
    def fetch_agenda(self, now, positions): return self._result(self.agenda)


def service(tmp_path, provider):
    return DailyContextService(
        registry=DailyProviderRegistry((provider,)),
        cache=DailyCache(tmp_path, 60),
    )


def registry_service(tmp_path, *providers):
    return DailyContextService(
        registry=DailyProviderRegistry(providers),
        cache=DailyCache(tmp_path, 60),
    )


def test_window_limit_priority_order_and_expired_facts(tmp_path):
    facts = [
        fact("old", 49, "Alta"),
        fact("eligible", 25, "Alta"),
        fact("low", 1),
        fact("high-old", 8, "Alta"),
        fact("high-new", 2, "Alta"),
        fact("moderate", 1, "Moderada"),
        fact("extra-1", 3),
        fact("extra-2", 4),
    ]
    result = service(tmp_path, Provider(facts)).generate((), now=NOW)
    assert len(result["facts"]) == 5
    assert [item["id"] for item in result["facts"][:3]] == [
        "high-new", "high-old", "eligible",
    ]
    assert "eligible" in {item["id"] for item in result["facts"]}
    assert "old" not in {item["id"] for item in result["facts"]}


def test_official_lookback_configures_cutoff_and_payload(tmp_path):
    result = service(tmp_path, Provider([
        fact("at-cutoff", DAILY_LOOKBACK_HOURS),
        fact("past-cutoff", DAILY_LOOKBACK_HOURS + 1),
    ])).generate((), now=NOW)

    assert DAILY_LOOKBACK_HOURS == 48
    assert result["lookback_hours"] == DAILY_LOOKBACK_HOURS
    assert [item["id"] for item in result["facts"]] == ["at-cutoff"]


def test_experience_uses_the_official_priorities_transformation(tmp_path):
    daily = build_daily_experience(
        (),
        date(2026, 7, 28),
        NOW,
        service(tmp_path, Provider([
            fact("first", 1, "Alta"),
            fact("second", 2, "Moderada"),
            fact("third", 3, "Baixa"),
            fact("fourth", 4, "Baixa"),
        ])),
    )

    assert daily["priorities"] == build_priorities(daily["important_facts"])


def test_build_analyses_preserves_order_limit_and_contract(tmp_path):
    facts = service(tmp_path, Provider([
        fact("portfolio-first", 1, assets=("NVDA",)),
        fact("general", 2),
        fact("macro-second", 3, macro=True),
        fact("macro-limited", 4, macro=True),
    ])).generate([position("NVDA")], NOW)["facts"]

    analyses = build_analyses(facts)

    assert [item["id"] for item in analyses] == [
        "portfolio-first", "macro-second",
    ]
    assert set(analyses[0]) == {
        "id", "title", "reason", "related_to", "status", "updated_at",
    }
    assert analyses[0] == {
        "id": "portfolio-first",
        "title": "Fato portfolio-first",
        "reason": "Resumo portfolio-first",
        "related_to": "NVDA",
        "status": "Relacionado à carteira: NVDA",
        "updated_at": (NOW - timedelta(hours=1)).isoformat(),
    }


def test_build_analyses_empty_and_independent_between_calls():
    assert build_analyses([]) == []

    fact_payload = {
        "id": "macro",
        "title": "Fato macro",
        "summary": "Resumo macro",
        "matched_portfolio_assets": [],
        "context": "Contexto macro geral de mercado",
        "occurred_at": NOW.isoformat(),
        "context_type": "macro",
    }
    first = build_analyses([fact_payload])
    second = build_analyses([fact_payload])

    assert first == second
    assert first is not second
    assert first[0] is not second[0]


def test_experience_contract_matches_the_official_orchestrator(tmp_path):
    facts = [fact("macro", 1, macro=True)]
    wrapper_result = build_daily_experience(
        (), date(2026, 7, 28), NOW,
        service(tmp_path / "wrapper", Provider(facts)),
    )
    orchestrator_result = DailyOrchestrator(
        service(tmp_path / "orchestrator", Provider(facts)),
    ).build((), date(2026, 7, 28), NOW)

    assert wrapper_result == orchestrator_result


def test_direct_nvda_and_ethereum_relationships_without_indirect_etf_match(tmp_path):
    positions = [position("NVDA", "NVIDIA Corp"), position("ETHB", "Ethereum Brasil", "Santander"),
                 position("TECH", "Technology ETF")]
    result = service(tmp_path, Provider([
        fact("nvidia", 2, "Moderada", ("NVDA", "NVIDIA"), "Tecnologia"),
        fact("eth", 3, "Moderada", ("ETH", "ETHEREUM"), "Criptoativos"),
    ])).generate(positions, NOW)
    assert result["facts"][0]["matched_portfolio_assets"] == ["NVDA"]
    assert result["facts"][1]["matched_portfolio_assets"] == ["ETHB"]
    assert all("TECH" not in item["matched_portfolio_assets"] for item in result["facts"])


def test_works_without_portfolio_and_with_ubs_and_santander(tmp_path):
    provider = Provider([fact("macro", 1, "Alta", macro=True)])
    no_portfolio = service(tmp_path / "a", provider).generate((), NOW)
    combined = service(tmp_path / "b", Provider(provider.facts)).generate(
        [position("AAA", institution="UBS"), position("BBB", institution="Santander")], NOW)
    assert no_portfolio["facts"][0]["context"] == "Contexto macro geral de mercado"
    assert combined["facts"][0]["context"] == "Impacto macro para as carteiras"


def test_agenda_prioritizes_portfolio_then_chronology_and_excludes_past(tmp_path):
    events = [agenda("general-first", 1), agenda("portfolio-later", 4, ("NVDA",)),
              agenda("portfolio-first", 2, ("NVDA",)), agenda("past", -1)]
    result = service(tmp_path, Provider(agenda=events)).generate([position("NVDA")], NOW)
    assert [item["id"] for item in result["agenda"]] == [
        "portfolio-first", "portfolio-later", "general-first"]


def test_legitimate_empty_and_provider_failure_are_distinct(tmp_path):
    empty = service(tmp_path / "empty", Provider()).generate((), NOW)
    failed = service(tmp_path / "failed", Provider(fail=True)).generate((), NOW)
    assert empty["sources"]["facts"]["status"] == "empty"
    assert failed["sources"]["facts"]["status"] == "unavailable"
    assert "fora do ar" in failed["sources"]["facts"]["error"]


def test_missing_credential_is_controlled(tmp_path):
    provider = FinnhubDailyProvider(api_key="")
    result = service(tmp_path, provider).generate((), NOW)
    assert result["sources"]["facts"]["status"] == "unavailable"
    assert "FINNHUB_API_KEY" in result["sources"]["facts"]["error"]


def test_cache_avoids_calls_and_preserves_last_valid_on_failure(tmp_path):
    cache = DailyCache(tmp_path, 60)
    good = Provider([fact("valid", 1)], [agenda("future", 1)])
    registry = DailyProviderRegistry((good,))
    first = DailyContextService(registry=registry, cache=cache).generate((), NOW)
    second = DailyContextService(registry=registry, cache=cache).generate(
        (), NOW + timedelta(seconds=30)
    )
    assert good.calls == 2
    assert second["sources"]["facts"]["cached"] is True
    failing = Provider(fail=True)
    stale = DailyContextService(
        registry=DailyProviderRegistry((failing,)),
        cache=DailyCache(tmp_path, 1),
    ).generate((), NOW + timedelta(seconds=2))
    assert stale["facts"][0]["id"] == first["facts"][0]["id"]
    assert stale["sources"]["facts"]["cached"] is True
    assert stale["sources"]["facts"]["status"] == "unavailable"


def test_registry_queries_two_active_providers_in_priority_order(tmp_path):
    first = Provider([fact("first", 1)], name="first")
    second = Provider([fact("second", 2)], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert {item["id"] for item in result["facts"]} == {"first", "second"}
    assert first.calls == 2
    assert second.calls == 2
    assert [provider.name for provider in DailyProviderRegistry(
        (first, second)
    ).providers] == ["first", "second"]


def test_registered_provider_order_is_configurable():
    register_daily_provider("future-a", lambda: Provider(name="future-a"))
    register_daily_provider("future-b", lambda: Provider(name="future-b"))

    registry = build_default_registry("future-b,future-a")

    assert [provider.name for provider in registry.providers] == [
        "future-b", "future-a",
    ]


def test_registry_falls_back_when_first_provider_fails(tmp_path):
    first = Provider(fail=True, name="first")
    second = Provider([fact("fallback", 1)], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert [item["id"] for item in result["facts"]] == ["fallback"]
    assert result["sources"]["facts"]["status"] == "available"


def test_registry_combines_results_when_both_providers_respond(tmp_path):
    first = Provider([fact("alpha", 1)], [agenda("calendar-a", 2)], name="first")
    second = Provider([fact("beta", 2)], [agenda("calendar-b", 3)], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert {item["id"] for item in result["facts"]} == {"alpha", "beta"}
    assert {item["id"] for item in result["agenda"]} == {
        "calendar-a", "calendar-b",
    }


def test_registry_deduplicates_same_normalized_event(tmp_path):
    preferred = fact("preferred-id", 1, assets=("NVDA",), category="Tecnologia")
    duplicate = MarketEvent(
        "duplicate-id",
        "  FATO PREFERRED-ID  ",
        "tecnologia",
        "second source",
        preferred.occurred_at,
        preferred.priority,
        "Outro resumo",
        ("nvda",),
    )
    first = Provider([preferred], name="first")
    second = Provider([duplicate], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert [item["id"] for item in result["facts"]] == ["preferred-id"]
    assert result["facts"][0]["source"] == "Fonte real simulada"


def test_registry_reports_unavailable_when_both_providers_fail(tmp_path):
    result = registry_service(
        tmp_path,
        Provider(fail=True, name="first"),
        Provider(fail=True, name="second"),
    ).generate((), NOW)

    assert result["facts"] == []
    assert result["sources"]["facts"]["status"] == "unavailable"
    assert "first" in result["sources"]["facts"]["error"]
    assert "second" in result["sources"]["facts"]["error"]


def test_registry_treats_two_empty_responses_as_legitimate_empty(tmp_path):
    result = registry_service(
        tmp_path,
        Provider(name="first"),
        Provider(name="second"),
    ).generate((), NOW)

    assert result["sources"]["facts"]["status"] == "empty"


def test_provider_normalizes_news_and_calendars():
    news = FinnhubDailyProvider.normalize_news([{
        "id": 1, "headline": "NVIDIA announces platform", "summary": "NVDA update",
        "datetime": int(NOW.timestamp()), "source": "Reuters", "related": "NVDA"}])
    calendar = FinnhubDailyProvider.normalize_calendar(
        {"economicCalendar": [{"date": "2026-07-29T12:00:00Z", "event": "CPI inflation", "impact": 3}]},
        {"earningsCalendar": [{"date": "2026-07-30", "symbol": "NVDA"}]})
    assert news[0].category == "Tecnologia" and news[0].related_assets == ("NVDA", "NVIDIA")
    assert calendar[0].category == "Inflação" and calendar[0].importance == "Alta"
    assert calendar[1].related_assets == ("NVDA",)
    assert calendar[1].time_explicit is False


def test_provider_normalizes_available_dividends():
    calendar = FinnhubDailyProvider.normalize_calendar({}, {}, [{
        "date": "2026-07-31", "symbol": "NVDA", "amount": 0.01,
    }])
    assert calendar[0].category == "Dividendos"
    assert calendar[0].related_assets == ("NVDA",)
    assert calendar[0].time_explicit is False


def test_experience_neutral_panorama_and_empty_agenda(tmp_path):
    daily = build_daily_experience((), date(2026, 7, 28), NOW,
        service(tmp_path, Provider([fact("market", 1)])))
    assert tuple(item["topic"] for item in daily["global_overview"]) == PANORAMA_TOPICS
    assert daily["market_agenda"] == []
    assert daily["global_overview"][0]["summary"] == (
        f"Nenhum fato relevante identificado nas últimas {DAILY_LOOKBACK_HOURS} horas."
    )
    assert "etapa futura" not in str(daily)


def test_no_legacy_production_mocks_remain():
    from pathlib import Path
    production = "\n".join(path.read_text(encoding="utf-8") for path in Path("backend").rglob("*.py"))
    for legacy in ("Mock Federal Reserve", "nvidia-chips", "ethereum-network", "global-equities", "oil-supply"):
        assert legacy not in production


# Marco 15.0 — deterministic DailyExperienceComposer
REFERENCE_DATE = date(2026, 7, 30)
ENGINE_NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def experience_position(
    institution: str = "UBS",
    owner: PortfolioOwner = PortfolioOwner.JOLIKA,
    currency: str = "USD",
) -> PortfolioPosition:
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account="official",
        asset_class="Equities",
        asset_subclass="Technology",
        asset_name=f"{institution} asset",
        identifier=f"{institution}-1",
        identifier_type="TICKER",
        quantity=Decimal("2"),
        unit_price=Decimal("10.25"),
        market_value=Decimal("20.50"),
        currency=currency,
        portfolio_weight=None,
        reference_date=REFERENCE_DATE,
        source_file="fixture",
    )


def experience_candidate(
    identifier: str = "fact-1",
    institution: str | None = "UBS",
    currency: str | None = None,
    title: str = "Official fact title",
) -> FactCandidate:
    return FactCandidate(
        identifier,
        title,
        "Official structured description",
        "Official source",
        ENGINE_NOW - timedelta(hours=1),
        FactImportance.HIGH,
        FactCategory.MARKETS,
        urgency=FactImportance.HIGH,
        related_currencies=(currency,) if currency else (),
        related_institutions=(institution,) if institution else (),
    )


def experience_orchestrator() -> OfficialDailyOrchestrator:
    return OfficialDailyOrchestrator(
        DailyPortfolioSnapshotBuilder(),
        ImportantFactsEngine(clock=lambda: ENGINE_NOW),
        PortfolioImpactEngine(clock=lambda: ENGINE_NOW),
        DailyPriorityEngine(clock=lambda: ENGINE_NOW),
        clock=lambda: ENGINE_NOW,
    )


def completed_experience_source(
    positions: tuple[PortfolioPosition, ...] = (experience_position(),),
    candidates: tuple[FactCandidate, ...] = (experience_candidate(),),
):
    return experience_orchestrator().run(positions, candidates, REFERENCE_DATE)


def experience_composer(at: datetime = datetime(2026, 7, 30, 16, tzinfo=timezone.utc)):
    return DailyExperienceComposer(clock=lambda: at)


def test_complete_composition_contract_content_and_labels() -> None:
    source = completed_experience_source()
    result = experience_composer().compose(source)
    assert source.daily_priorities is not None

    assert result.reference_date == REFERENCE_DATE
    assert result.generated_at == datetime(2026, 7, 30, 16, tzinfo=timezone.utc)
    assert result.generated_at.utcoffset() == timedelta(0)
    assert result.header.user_name == "Nei"
    assert result.header.greeting_period is DailyGreetingPeriod.AFTERNOON
    assert result.header.greeting_text == "Boa tarde, Nei"
    assert result.header.formatted_date == "quinta-feira, 30 de julho de 2026"
    assert "ARGOS" not in result.header.greeting_text
    assert "Seu dia está sob controle" not in repr(result)
    assert result.status is DailyExperienceStatus.DECISION_REQUIRED
    assert result.message.text == "Há uma decisão que merece sua atenção hoje."
    assert result.facts[0].fact_id == "fact-1"
    assert result.facts[0].title == "Official fact title"
    assert result.facts[0].category == "MARKETS"
    assert result.facts[0].priority == "HIGH"
    assert result.facts[0].source == "Official source"
    assert result.priorities[0].level is DailyPriorityLevel.HIGH
    assert result.priorities[0].label == "Alta"
    assert result.analyses[0].action is DailyPriorityAction.DECIDE
    assert result.analyses[0].action_label == "Decidir"
    assert result.analyses[0].affected_dimensions == source.daily_priorities.priorities[0].affected_dimensions
    assert "Investigações" not in repr(result)


@pytest.mark.parametrize(
    ("local_hour", "expected_period", "expected_text"),
    (
        (5, DailyGreetingPeriod.MORNING, "Bom dia, Nei"),
        (11, DailyGreetingPeriod.MORNING, "Bom dia, Nei"),
        (12, DailyGreetingPeriod.AFTERNOON, "Boa tarde, Nei"),
        (17, DailyGreetingPeriod.AFTERNOON, "Boa tarde, Nei"),
        (18, DailyGreetingPeriod.EVENING, "Boa noite, Nei"),
        (4, DailyGreetingPeriod.EVENING, "Boa noite, Nei"),
    ),
)
def test_greeting_boundaries_in_sao_paulo(
    local_hour: int, expected_period: DailyGreetingPeriod, expected_text: str,
) -> None:
    # July 2026 in Sao Paulo is UTC-3.
    instant = datetime(2026, 7, 30, (local_hour + 3) % 24, 59, tzinfo=timezone.utc)
    result = experience_composer(instant).compose(completed_experience_source())
    assert result.header.greeting_period is expected_period
    assert result.header.greeting_text == expected_text


def test_exact_boundaries_custom_timezone_name_and_reference_date_independence() -> None:
    source = completed_experience_source()
    morning = DailyExperienceComposer(
        clock=lambda: datetime(2027, 1, 1, 5, tzinfo=timezone.utc),
        user_name="Ana",
        presentation_timezone="UTC",
    ).compose(source)
    afternoon = DailyExperienceComposer(
        clock=lambda: datetime(2027, 1, 1, 12, tzinfo=timezone.utc),
        presentation_timezone="UTC",
    ).compose(source)
    evening = DailyExperienceComposer(
        clock=lambda: datetime(2027, 1, 1, 18, tzinfo=timezone.utc),
        presentation_timezone="UTC",
    ).compose(source)
    assert morning.header.greeting_text == "Bom dia, Ana"
    assert afternoon.header.greeting_text == "Boa tarde, Nei"
    assert evening.header.greeting_text == "Boa noite, Nei"
    assert morning.reference_date == morning.header.reference_date == REFERENCE_DATE
    assert morning.header.formatted_date == "quinta-feira, 30 de julho de 2026"


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    (
        ({"user_name": ""}, "INVALID_USER_NAME"),
        ({"user_name": "  "}, "INVALID_USER_NAME"),
        ({"presentation_timezone": "Invalid/Nowhere"}, "INVALID_TIMEZONE"),
    ),
)
def test_constructor_rejects_invalid_configuration(kwargs, error_type: str) -> None:
    with pytest.raises(DailyExperienceError) as captured:
        DailyExperienceComposer(**kwargs)
    assert captured.value.error_type == error_type
    assert "Traceback" not in str(captured.value)


def test_naive_clock_and_clock_failure_are_typed_and_preserve_cause() -> None:
    with pytest.raises(DailyExperienceError, match="timezone-aware") as naive:
        experience_composer(datetime(2026, 7, 30, 12)).compose(completed_experience_source())
    assert naive.value.error_type == "INVALID_CLOCK"

    def failing_clock() -> datetime:
        raise RuntimeError("private clock detail")

    with pytest.raises(DailyExperienceError) as failed:
        DailyExperienceComposer(clock=failing_clock).compose(completed_experience_source())
    assert failed.value.error_type == "CLOCK_ERROR"
    assert isinstance(failed.value.cause, RuntimeError)
    assert failed.value.__cause__ is failed.value.cause
    assert "private clock detail" not in str(failed.value)


def test_failed_orchestration_and_wrong_type_are_rejected() -> None:
    class FailingBuilder(DailyPortfolioSnapshotBuilder):
        def build(self, positions, reference_date=None, validation_reports=None):
            raise RuntimeError("portfolio data")

    failing = OfficialDailyOrchestrator(
        FailingBuilder(), ImportantFactsEngine(), PortfolioImpactEngine(), DailyPriorityEngine(),
        clock=lambda: ENGINE_NOW,
    )
    with pytest.raises(DailyOrchestrationError) as orchestration_error:
        failing.run((), (), REFERENCE_DATE)
    with pytest.raises(DailyExperienceError) as failed:
        experience_composer().compose(orchestration_error.value.result)
    assert failed.value.error_type == "ORCHESTRATION_NOT_COMPLETED"
    with pytest.raises(DailyExperienceError) as wrong:
        cast(Callable[[object], object], experience_composer().compose)(None)
    assert wrong.value.error_type == "INVALID_RESULT_TYPE"


def test_empty_experience_and_global_fact_without_priority() -> None:
    empty = experience_composer().compose(completed_experience_source((), ()))
    assert empty.status is DailyExperienceStatus.NO_ACTION_REQUIRED
    assert empty.message.text == "Nada exige sua atenção na carteira hoje."
    assert empty.facts == empty.priorities == empty.analyses == ()
    assert all(block.visibility is DailyBlockVisibility.HIDDEN for block in empty.blocks)
    assert empty.summary.visible_block_count == 0
    assert empty.summary.hidden_block_count == 3
    assert not empty.summary.automatic_analysis_open
    assert not empty.summary.has_attention
    assert not empty.summary.has_decision

    global_only = experience_composer().compose(completed_experience_source((), (experience_candidate(institution=None),)))
    assert len(global_only.facts) == 1
    assert global_only.priorities == global_only.analyses == ()
    assert global_only.status is DailyExperienceStatus.NO_ACTION_REQUIRED
    assert not global_only.summary.automatic_analysis_open
    assert global_only.blocks[0].visibility is DailyBlockVisibility.VISIBLE
    assert global_only.blocks[1].visibility is DailyBlockVisibility.HIDDEN


def test_analyze_status_message_opening_and_moderate_label() -> None:
    source = completed_experience_source((experience_position(currency="USD"),), (experience_candidate(institution=None, currency="USD"),))
    result = experience_composer().compose(source)
    assert result.priorities[0].level is DailyPriorityLevel.MODERATE
    assert result.priorities[0].label == "Moderada"
    assert result.analyses[0].action is DailyPriorityAction.ANALYZE
    assert result.analyses[0].action_label == "Analisar"
    assert result.status is DailyExperienceStatus.ATTENTION_REQUIRED
    assert result.message.text == "Há pontos da carteira que merecem sua análise hoje."
    assert result.summary.automatic_analysis_open
    assert result.summary.has_attention
    assert not result.summary.has_decision


def test_fact_limit_preserves_first_five_and_does_not_mutate_source() -> None:
    source = completed_experience_source((), ())
    official_facts = tuple(
        ImportantFact(f"f-{index}", "LOW", "OTHER", f"Title {index}", "Text", f"Source {index}")
        for index in range(7)
    )
    expanded = replace(
        source,
        important_facts=ImportantFactsResult(official_facts, ()),
    )
    result = experience_composer().compose(expanded)
    assert tuple(item.fact_id for item in result.facts) == tuple(f"f-{index}" for index in range(5))
    assert result.summary.fact_count == 5
    assert expanded.important_facts is not None
    assert expanded.important_facts.important_facts == official_facts


def test_three_priorities_and_two_analyses_preserve_official_order() -> None:
    positions = (
        experience_position("UBS", PortfolioOwner.JOLIKA, "USD"),
        experience_position("Santander", PortfolioOwner.JOLIKA, "BRL"),
        experience_position("Bradesco", PortfolioOwner.NEI, "BRL"),
    )
    candidates = tuple(
        experience_candidate(institution=name, identifier=name.casefold(), title=f"Fact {name}")
        for name in ("UBS", "Santander", "Bradesco")
    )
    source = completed_experience_source(positions, candidates)
    result = experience_composer().compose(source)
    assert source.daily_priorities is not None
    official_ids = tuple(item.priority_id for item in source.daily_priorities.priorities)
    assert tuple(item.priority_id for item in result.priorities) == official_ids
    assert tuple(item.priority_id for item in result.analyses) == official_ids[:2]
    assert result.summary.priority_count == 3
    assert result.summary.analysis_count == 2
    assert all(item.label == "Alta" for item in result.priorities)
    assert all(item.action_label == "Decidir" for item in result.analyses)


def test_blocks_always_have_official_order_titles_visibility_and_counts() -> None:
    result = experience_composer().compose(completed_experience_source())
    assert tuple(block.block_type for block in result.blocks) == tuple(DailyBlockType)
    assert tuple(block.title for block in result.blocks) == (
        "Fatos importantes", "Prioridades do dia", "Análises",
    )
    assert len(result.blocks) == 3
    assert tuple(block.item_count for block in result.blocks) == (1, 1, 1)
    assert all(block.visibility is DailyBlockVisibility.VISIBLE for block in result.blocks)
    representation = repr(result)
    for excluded in ("AGENDA", "RISKS", "OPPORTUNITIES", "PERSONAL_COMMITMENTS", "INVESTIGATIONS"):
        assert excluded not in representation


def test_result_is_deeply_immutable_deterministic_and_preserves_input() -> None:
    source = completed_experience_source()
    before = repr(source)
    service = experience_composer()
    first = service.compose(source)
    second = service.compose(source)
    assert first == second
    assert repr(source) == before
    assert source.daily_priorities is not None
    assert first.analyses[0].affected_dimensions is source.daily_priorities.priorities[0].affected_dimensions
    with pytest.raises(FrozenInstanceError):
        setattr(first.header, "user_name", "Changed")
    with pytest.raises(FrozenInstanceError):
        setattr(first.message, "text", "Changed")
    with pytest.raises(FrozenInstanceError):
        setattr(first.facts[0], "title", "Changed")
    with pytest.raises(FrozenInstanceError):
        setattr(first.analyses[0], "affected_dimensions", ())


@pytest.mark.parametrize(
    ("institution", "owner", "currency"),
    (
        ("UBS", PortfolioOwner.JOLIKA, "USD"),
        ("Santander", PortfolioOwner.JOLIKA, "BRL"),
        ("Bradesco", PortfolioOwner.NEI, "BRL"),
    ),
)
def test_end_to_end_institution_scenarios_preserve_portfolio_contracts(
    institution: str, owner: PortfolioOwner, currency: str,
) -> None:
    source = completed_experience_source(
        (experience_position(institution, owner, currency),),
        (experience_candidate(institution=institution),),
    )
    before = repr(source)
    result = experience_composer().compose(source)
    assert source.snapshot is not None
    assert source.snapshot.owners == (owner,)
    assert source.snapshot.institutions == (institution,)
    assert source.snapshot.currencies == (currency,)
    assert all(
        isinstance(value, Decimal)
        for value in source.snapshot.consolidated.gross_value_by_currency.values()
    )
    assert result.status is DailyExperienceStatus.DECISION_REQUIRED
    assert result.summary.automatic_analysis_open
    assert repr(source) == before


def test_end_to_end_simultaneous_scenario_keeps_owners_currencies_separate() -> None:
    positions = (
        experience_position("UBS", PortfolioOwner.JOLIKA, "USD"),
        experience_position("Santander", PortfolioOwner.JOLIKA, "BRL"),
        experience_position("Bradesco", PortfolioOwner.NEI, "BRL"),
    )
    source = completed_experience_source(
        positions,
        tuple(
            experience_candidate(name.casefold(), name, title=f"Fact {name}")
            for name in ("UBS", "Santander", "Bradesco")
        ),
    )
    assert source.snapshot is not None
    original_values = source.snapshot.consolidated.gross_value_by_currency
    result = experience_composer().compose(source)
    assert source.snapshot.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert source.snapshot.institutions == ("Bradesco", "Santander", "UBS")
    assert source.snapshot.currencies == ("BRL", "USD")
    assert original_values == {"BRL": Decimal("41.00"), "USD": Decimal("20.50")}
    assert result.summary.priority_count == 3
    assert result.summary.analysis_count == 2
    assert not hasattr(result.summary, "gross_value")
    assert not hasattr(result, "market_agenda")
