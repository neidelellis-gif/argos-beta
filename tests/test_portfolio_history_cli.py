from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from backend.portfolio_change_reports import (
    DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY,
)
from backend.portfolio_history_cli import SUMMARY_FIELDS, build_parser, main
from backend.portfolio_history_cycle import PortfolioHistoryCycleStatus
from backend.portfolio_snapshots import DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY


UTC = timezone.utc
NOW = datetime(2026, 8, 17, 12, 30, tzinfo=UTC)


def cycle_result(*, historical=False, warnings=()):
    current = SimpleNamespace(snapshot_id="current-id", captured_at=NOW)
    previous = SimpleNamespace(
        snapshot_id="previous-id",
        captured_at=datetime(2026, 8, 16, 12, 30, tzinfo=UTC),
    )
    summary = SimpleNamespace(**dict.fromkeys(SUMMARY_FIELDS, 1))
    report = SimpleNamespace(report_id="report-id", summary=summary)
    return SimpleNamespace(
        status=(
            PortfolioHistoryCycleStatus.HISTORICAL_UPDATE
            if historical
            else PortfolioHistoryCycleStatus.INITIAL_SNAPSHOT
        ),
        current_snapshot=current,
        previous_snapshot=previous if historical else None,
        change_report=report if historical else None,
        snapshot_path=Path("snapshots/current.json"),
        report_path=Path("reports/change.json") if historical else None,
        position_count=2,
        totals_by_currency={"USD": Decimal("30.50")},
        warnings=tuple(warnings),
    )


def preflight_result(*, approved=True, baseline=True, warnings=(), blockers=()):
    return SimpleNamespace(
        approved=approved,
        ubs=SimpleNamespace(position_count=1),
        santander=SimpleNamespace(position_count=2),
        total_position_count=3,
        totals_by_currency=(("USD", Decimal("30.50")),),
        unresolved_count=4,
        unresolved_keys=("secret-identifier",),
        baseline_snapshot_id="baseline-id" if baseline else None,
        baseline_position_count=5 if baseline else None,
        position_count_change=-2 if baseline else None,
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )


def invoke(extra=(), *, result=None, preflight=None):
    argv = ["run", "--ubs", "ubs.csv", "--santander", "santander.xlsx", *extra]
    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        return_value=preflight or preflight_result(),
    ) as preflight_mock, patch(
        "backend.portfolio_history_cli.run_portfolio_history_cycle",
        return_value=result or cycle_result(),
    ) as workflow:
        code = main(argv)
    return code, preflight_mock, workflow


def invoke_preflight(extra=(), *, preflight=None):
    argv = ["preflight", "--ubs", "ubs.csv", "--santander", "santander.xlsx", *extra]
    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        return_value=preflight or preflight_result(),
    ) as preflight_mock, patch(
        "backend.portfolio_history_cli.run_portfolio_history_cycle"
    ) as workflow:
        code = main(argv)
    return code, preflight_mock, workflow


def test_parser_exposes_run_and_required_inputs():
    parser = build_parser()
    args = parser.parse_args(["run", "--ubs", "u", "--santander", "s"])
    assert args.command == "run"
    with pytest.raises(SystemExit) as missing_ubs:
        parser.parse_args(["run", "--santander", "s"])
    with pytest.raises(SystemExit) as missing_santander:
        parser.parse_args(["run", "--ubs", "u"])
    assert missing_ubs.value.code == missing_santander.value.code == 2


def test_parser_exposes_preflight_and_required_inputs():
    parser = build_parser()
    args = parser.parse_args(["preflight", "--ubs", "u", "--santander", "s"])
    assert args.command == "preflight"
    with pytest.raises(SystemExit) as missing_ubs:
        parser.parse_args(["preflight", "--santander", "s"])
    with pytest.raises(SystemExit) as missing_santander:
        parser.parse_args(["preflight", "--ubs", "u"])
    assert missing_ubs.value.code == missing_santander.value.code == 2


def test_parser_directory_defaults():
    args = build_parser().parse_args(["run", "--ubs", "u", "--santander", "s"])
    assert args.snapshot_directory == str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY)
    assert args.report_directory == str(DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY)
    preflight = build_parser().parse_args(
        ["preflight", "--ubs", "u", "--santander", "s"]
    )
    assert preflight.snapshot_directory == str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY)


def test_preflight_parser_rejects_run_only_options():
    parser = build_parser()
    for option in ("--overwrite", "--generated-at", "--report-directory"):
        values = ["preflight", "--ubs", "u", "--santander", "s", option]
        if option != "--overwrite":
            values.append("x")
        with pytest.raises(SystemExit):
            parser.parse_args(values)


def test_default_captured_at_is_utc_aware_and_generated_at_is_none():
    _, preflight, workflow = invoke()
    captured = workflow.call_args.kwargs["captured_at"]
    assert captured.tzinfo is UTC and captured.utcoffset() is not None
    assert workflow.call_args.kwargs["generated_at"] is None
    assert preflight.call_args.kwargs["before"] == captured


def test_preflight_default_captured_at_is_utc_aware():
    _, preflight, workflow = invoke_preflight()
    captured = preflight.call_args.kwargs["before"]
    assert captured.tzinfo is UTC and captured.utcoffset() is not None
    workflow.assert_not_called()


@pytest.mark.parametrize(
    ("option", "value", "expected"),
    [
        ("--captured-at", "2026-08-17T12:30:00Z", NOW),
        ("--captured-at", "2026-08-17T09:30:00-03:00", NOW),
        ("--generated-at", "2026-08-17T12:30:00Z", NOW),
    ],
)
def test_timestamps_accept_z_and_convert_offsets_to_utc(option, value, expected):
    _, preflight, workflow = invoke([option, value])
    field = "captured_at" if option == "--captured-at" else "generated_at"
    assert workflow.call_args.kwargs[field] == expected
    assert workflow.call_args.kwargs[field].tzinfo is UTC
    if option == "--captured-at":
        assert preflight.call_args.kwargs["before"] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-17T12:30:00Z", NOW),
        ("2026-08-17T09:30:00-03:00", NOW),
    ],
)
def test_preflight_timestamp_normalization(value, expected):
    _, preflight, workflow = invoke_preflight(["--captured-at", value])
    assert preflight.call_args.kwargs["before"] == expected
    assert preflight.call_args.kwargs["before"].tzinfo is UTC
    workflow.assert_not_called()


@pytest.mark.parametrize("command", ["run", "preflight"])
def test_naive_captured_at_fails_before_calls(command, capsys):
    argv = [command, "--ubs", "u", "--santander", "s", "--captured-at", "2026-08-17T12:30:00"]
    with patch("backend.portfolio_history_cli.run_portfolio_history_preflight") as preflight, patch(
        "backend.portfolio_history_cli.run_portfolio_history_cycle"
    ) as workflow:
        assert main(argv) == 2
    preflight.assert_not_called()
    workflow.assert_not_called()
    assert "timezone-aware" in capsys.readouterr().err


def test_generated_at_naive_fails_before_preflight_and_workflow(capsys):
    code, preflight, workflow = invoke(["--generated-at", "2026-08-17T12:30:00"])
    assert code == 2
    preflight.assert_not_called()
    workflow.assert_not_called()
    assert "timezone-aware" in capsys.readouterr().err


def test_delegates_once_and_forwards_all_arguments_and_overwrite():
    code, preflight, workflow = invoke(
        [
            "--snapshot-directory", "custom-snapshots",
            "--report-directory", "custom-reports",
            "--captured-at", "2026-08-17T12:30:00Z",
            "--generated-at", "2026-08-17T13:30:00+01:00",
            "--overwrite",
        ]
    )
    assert code == 0
    preflight.assert_called_once_with(
        ubs_path="ubs.csv",
        santander_path="santander.xlsx",
        snapshot_directory=Path("custom-snapshots"),
        before=NOW,
    )
    workflow.assert_called_once_with(
        ubs_path="ubs.csv",
        santander_path="santander.xlsx",
        snapshot_directory=Path("custom-snapshots"),
        report_directory=Path("custom-reports"),
        captured_at=NOW,
        generated_at=NOW,
        overwrite=True,
    )


def test_preflight_command_forwards_arguments_once_and_never_runs_cycle():
    code, preflight, workflow = invoke_preflight(
        ["--snapshot-directory", "custom-snapshots", "--captured-at", "2026-08-17T12:30:00Z"]
    )
    assert code == 0
    preflight.assert_called_once_with(
        ubs_path="ubs.csv",
        santander_path="santander.xlsx",
        snapshot_directory=Path("custom-snapshots"),
        before=NOW,
    )
    workflow.assert_not_called()


def test_preflight_approved_and_blocked_exit_codes(capsys):
    approved, _, approved_workflow = invoke_preflight(preflight=preflight_result())
    assert approved == 0
    approved_workflow.assert_not_called()
    capsys.readouterr()
    blocked, _, blocked_workflow = invoke_preflight(
        preflight=preflight_result(approved=False, blockers=("missing UBS positions",))
    )
    assert blocked == 2
    blocked_workflow.assert_not_called()
    output = capsys.readouterr().out
    assert "preflight_approved: false" in output
    assert "preflight_blocker: missing UBS positions" in output


def test_preflight_output_is_factual_private_and_complete(capsys):
    invoke_preflight(preflight=preflight_result(warnings=("review input",)))
    output = capsys.readouterr().out
    for line in (
        "preflight_approved: true",
        "preflight_total_positions: 3",
        "preflight_ubs_positions: 1",
        "preflight_santander_positions: 2",
        "preflight_unresolved: 4",
        "preflight_totals_by_currency: {'USD': '30.50'}",
        "preflight_baseline_snapshot_id: baseline-id",
        "preflight_baseline_position_count: 5",
        "preflight_position_count_change: -2",
        "preflight_warnings_count: 1",
        "preflight_blockers_count: 0",
        "preflight_warning: review input",
    ):
        assert line in output
    assert "secret-identifier" not in output
    assert "unresolved_keys" not in output
    assert "account" not in output
    assert "identifier" not in output


def test_preflight_none_baseline_values_are_rendered_as_none(capsys):
    invoke_preflight(preflight=preflight_result(baseline=False))
    output = capsys.readouterr().out
    assert "preflight_baseline_snapshot_id: none" in output
    assert "preflight_baseline_position_count: none" in output
    assert "preflight_position_count_change: none" in output


def test_initial_snapshot_output_has_no_report_object(capsys):
    code, _, _ = invoke(result=cycle_result())
    output = capsys.readouterr().out
    assert code == 0
    assert "status: INITIAL_SNAPSHOT" in output
    assert "snapshot_id: current-id" in output
    assert "captured_at: 2026-08-17T12:30:00+00:00" in output
    assert "positions: 2" in output
    assert "totals_by_currency: {'USD': '30.50'}" in output
    assert "snapshot_path: snapshots/current.json" in output
    assert "report_path: none" in output
    assert "report_id:" not in output
    assert "warnings_count: 0" in output


def test_historical_output_has_complete_factual_summary_without_details(capsys):
    code, _, _ = invoke(result=cycle_result(historical=True))
    output = capsys.readouterr().out
    assert code == 0
    assert "status: HISTORICAL_UPDATE" in output
    assert "previous_snapshot_id: previous-id" in output
    assert "current_snapshot_id: current-id" in output
    assert "previous_captured_at: 2026-08-16T12:30:00+00:00" in output
    assert "current_captured_at: 2026-08-17T12:30:00+00:00" in output
    assert "report_id: report-id" in output
    assert "report_path: reports/change.json" in output
    for field in SUMMARY_FIELDS:
        assert f"{field}: 1" in output
    assert "account:" not in output
    assert "identifier" not in output


def test_warnings_are_counted_and_printed(capsys):
    invoke(result=cycle_result(warnings=("UBS: review", "Santander: check")))
    output = capsys.readouterr().out
    assert "warnings_count: 2" in output
    assert "warning: UBS: review" in output
    assert "warning: Santander: check" in output


def test_preflight_output_precedes_cycle(capsys):
    invoke(preflight=preflight_result(warnings=("review input",)), result=cycle_result())
    output = capsys.readouterr().out
    assert output.index("preflight_approved") < output.index("status: INITIAL_SNAPSHOT")


def test_blocked_run_skips_cycle(capsys):
    code, preflight, workflow = invoke(
        preflight=preflight_result(
            approved=False,
            blockers=("missing UBS positions", "unresolved JOLIKA assets: 4"),
        )
    )
    assert code == 2
    preflight.assert_called_once()
    workflow.assert_not_called()
    output = capsys.readouterr().out
    assert "preflight_blockers_count: 2" in output


def test_preflight_runs_before_workflow_and_each_runs_once():
    calls = Mock()
    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        side_effect=lambda **kwargs: (calls("preflight"), preflight_result())[1],
    ) as preflight, patch(
        "backend.portfolio_history_cli.run_portfolio_history_cycle",
        side_effect=lambda **kwargs: (calls("workflow"), cycle_result())[1],
    ) as workflow:
        assert main(["run", "--ubs", "u", "--santander", "s"]) == 0
    preflight.assert_called_once()
    workflow.assert_called_once()
    assert calls.call_args_list == [call("preflight"), call("workflow")]


@pytest.mark.parametrize(
    "error",
    [ValueError("invalid input"), FileNotFoundError("missing file"), OSError("disk error")],
)
def test_preflight_command_operational_errors_return_two(error, capsys):
    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        side_effect=error,
    ), patch("backend.portfolio_history_cli.run_portfolio_history_cycle") as workflow:
        assert main(["preflight", "--ubs", "u", "--santander", "s"]) == 2
    workflow.assert_not_called()
    captured = capsys.readouterr()
    assert str(error) in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid input"),
        FileNotFoundError("missing file"),
        FileExistsError("already exists"),
        OSError("disk error"),
    ],
)
def test_workflow_operational_errors_return_two_without_traceback(error, capsys):
    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        return_value=preflight_result(),
    ), patch(
        "backend.portfolio_history_cli.run_portfolio_history_cycle",
        side_effect=error,
    ):
        assert main(["run", "--ubs", "u", "--santander", "s"]) == 2
    captured = capsys.readouterr()
    assert str(error) in captured.err
    assert "Traceback" not in captured.err


def test_unexpected_programming_errors_are_not_hidden():
    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        side_effect=RuntimeError("preflight bug"),
    ), patch("backend.portfolio_history_cli.run_portfolio_history_cycle") as workflow:
        with pytest.raises(RuntimeError, match="preflight bug"):
            main(["preflight", "--ubs", "u", "--santander", "s"])
    workflow.assert_not_called()

    with patch(
        "backend.portfolio_history_cli.run_portfolio_history_preflight",
        return_value=preflight_result(),
    ), patch(
        "backend.portfolio_history_cli.run_portfolio_history_cycle",
        side_effect=RuntimeError("bug"),
    ):
        with pytest.raises(RuntimeError, match="bug"):
            main(["run", "--ubs", "u", "--santander", "s"])


def test_preflight_command_has_no_persistence_side_effects(tmp_path):
    snapshot_directory = tmp_path / "snapshots"
    code, preflight, workflow = invoke_preflight(
        ["--snapshot-directory", str(snapshot_directory)]
    )
    assert code == 0
    preflight.assert_called_once()
    workflow.assert_not_called()
    assert not snapshot_directory.exists()
