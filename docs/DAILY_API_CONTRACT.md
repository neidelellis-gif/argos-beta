# Daily API public contract

## Current version

`1.0` is the only supported version. Every response, including HTTP boundary
errors, contains `contract_version: "1.0"`.

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

The response contract requires `status`, `generated_at`, `contract_version`,
`experience_status`, `header`, `message`, `facts`, `priorities`, `analyses`,
`blocks`, `summary`, and `error`. Official public enums and structural validators
are defined in `backend/daily_contract.py`; the corresponding compatibility
validator used by the browser is `DailyApiContract` in
`frontend/daily_client.js`.

## Version policy

Contract changes that are incompatible with version `1.0` require an explicit
new version and coordinated backend/frontend support. Neither side automatically
adapts one version into another. Additive unknown request-envelope fields remain
forward-compatible because version `1.0` deliberately ignores them.
