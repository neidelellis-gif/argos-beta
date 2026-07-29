"""Ordered registry and fallback orchestration for daily-data providers."""

from datetime import timezone

from backend.config.settings import get_setting
from backend.daily.providers import ExternalDataResult, FinnhubDailyProvider


def _normalized_text(value):
    return " ".join(str(value).casefold().split())


def _event_key(event, kind):
    event_time = (
        event.occurred_at if kind == "facts" else event.scheduled_at
    )
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    event_time = event_time.astimezone(timezone.utc).isoformat()
    assets = tuple(sorted({
        _normalized_text(asset)
        for asset in event.related_assets
        if str(asset).strip()
    }))
    return (
        _normalized_text(event.title),
        _normalized_text(event.category),
        event_time,
        assets,
    )


class DailyProviderRegistry:
    """Resolve and query normalized providers in configured priority order."""

    def __init__(self, providers=()):
        self._providers = []
        for provider in providers:
            self.add(provider)

    def add(self, provider):
        self._providers.append(provider)
        return self

    @property
    def providers(self):
        return tuple(self._providers)

    def fetch(self, kind, now, positions):
        items = []
        seen = set()
        errors = []
        successful = False

        for provider in self._providers:
            try:
                result = getattr(provider, f"fetch_{kind}")(now, positions)
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            if result.status == "unavailable":
                errors.append(
                    f"{provider.name}: {result.error or 'fonte indisponível'}"
                )
                continue
            successful = True
            for event in result.items:
                key = _event_key(event, kind)
                if key not in seen:
                    seen.add(key)
                    items.append(event)

        if items:
            return ExternalDataResult("available", tuple(items))
        if successful:
            return ExternalDataResult("empty", ())
        error = "; ".join(errors) or "Nenhum provedor diário configurado"
        return ExternalDataResult("unavailable", (), error=error)

    def fetch_facts(self, now, positions):
        return self.fetch("facts", now, positions)

    def fetch_agenda(self, now, positions):
        return self.fetch("agenda", now, positions)


_PROVIDER_FACTORIES = {
    "finnhub": FinnhubDailyProvider,
}


def register_daily_provider(name, factory):
    """Register a provider factory for use in configured priority lists."""
    normalized_name = str(name).strip().casefold()
    if not normalized_name:
        raise ValueError("O nome do provedor diário não pode ser vazio")
    _PROVIDER_FACTORIES[normalized_name] = factory


def build_default_registry(order=None):
    """Build the registry without exposing concrete providers to the service."""
    configured = order or get_setting("ARGOS_DAILY_PROVIDERS", "finnhub")
    names = (
        configured.split(",")
        if isinstance(configured, str)
        else configured
    )
    registry = DailyProviderRegistry()
    for name in names:
        normalized_name = str(name).strip().casefold()
        if normalized_name:
            factory = _PROVIDER_FACTORIES.get(normalized_name)
            if factory is None:
                raise ValueError(
                    f"Provedor diário não registrado: {name}"
                )
            registry.add(factory())
    return registry
