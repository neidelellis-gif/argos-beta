# Daily API public contract

## Current version

`1.3` is the current response version. Every response, including HTTP boundary
errors, contains `contract_version: "1.3"`. Version 1.3 preserves facts, analyses
and priorities from 1.0, agenda from 1.1 and impacts from 1.2, and adds
`decision_contexts`. Older frontend payloads safely treat that collection as empty.

Each decision context publicly contains exactly `id`, `context_type`,
`relevance_level`, `title`, `summary`, `related_assets`, `context_factors` and
`limitations`, with at most five items. Profile data, source references, notes,
session data and internal relationship IDs are not exposed.

Each agenda item contains exactly `id`, `event_type`, `importance`, `title`,
`summary`, `event_date`, `event_time`, `timezone`, `all_day`, `affected_assets`
and `source_name`, with at most ten items.

The frontend verifies exact compatibility before rendering. It does not infer,
upgrade, downgrade, rename, or otherwise adapt response fields automatically.
An incompatible or incomplete successful response is handled as a safe internal
error.

## Boundary

The official integration flow is:

`DailyFrontendClient` → `DailyApiContract` → `DailyHttpAdapter` →
`DailyApiFacade` → `DailyOrchestrator` → `DailyExperienceComposer`.

The request contract contains `positions`, `fact_candidates`, `reference_date`,
and `validation_reports`. Unknown envelope fields are ignored and cannot change
execution. The two collection fields are required; the other fields are
optional.

The 1.3 response contract requires `status`, `generated_at`, `contract_version`,
`experience_status`, `header`, `message`, `facts`, `priorities`, `analyses`,
`blocks`, `market_agenda`, `impact_assessments`, `decision_contexts`, `summary`, and `error`. Official public enums and structural validators
are defined in `backend/daily_contract.py`; the corresponding compatibility
validator used by the browser is `DailyApiContract` in
`frontend/daily_client.js`.

## Version policy

Contract changes that are incompatible with version `1.0` require an explicit
new version and coordinated backend/frontend support. Neither side automatically
adapts one version into another. Additive unknown request-envelope fields remain
forward-compatible because version `1.0` deliberately ignores them.


## Impact assessments (1.2)

`impact_assessments` is always a JSON array. Each item exposes exactly `id`, `source_type`, `impact_level`, `impact_direction`, `confidence`, `title`, `summary`, `affected_assets`, and `impact_factors`. Internal source IDs, canonical position IDs, affected-position objects, related facts/events, and financial values are not public. Readers must treat the field as an empty array when consuming compatible 1.0 or 1.1 payloads.
