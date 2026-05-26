from __future__ import annotations

from .models import (
    AllocationItem,
    AssetAssumption,
    InvestmentRequest,
    MacroRegime,
    Policy,
    PortfolioCandidate,
    RiskReview,
    SingleAssetReview,
)


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}"


def render_committee_memo(
    request: InvestmentRequest,
    policy: Policy,
    macro: MacroRegime,
    selected: PortfolioCandidate,
    allocations: list[AllocationItem],
    risk: RiskReview,
    simulation_summary: dict[str, float | int | str],
    terminal_return_distribution: list[dict[str, float | str]],
    drawdown_distribution: list[dict[str, float | str]],
    candidate_diagnostics: list[dict[str, str | float | bool]],
    rationale: list[str],
    process_review: list[str],
    risk_return_assessment: list[str],
    allocation_check: dict[str, bool | float | str],
    pros: list[str],
    cons: list[str],
    final_judgement: str,
    risks_to_monitor: list[str],
    invalid_if: list[str],
    rebalance_rule: str,
    data_provider_status: dict[str, str | int | bool | None] | None = None,
) -> str:
    allocation_lines = "\n".join(
        f"- {item.asset}: {percent(item.weight)} / {money(item.amount, request.currency)}"
        for item in allocations
    )
    execution_rows = "\n".join(
        "| "
        + " | ".join(
            [
                item.asset,
                item.ticker or "-",
                item.isin or "-",
                item.wkn or "-",
                item.exchange or "-",
                item.trading_currency or "-",
                money(item.amount, request.currency),
                f"[Yahoo]({item.yahoo_url})" if item.yahoo_url else "-",
            ]
        )
        + " |"
        for item in allocations
    )
    execution_notes = "\n".join(
        f"- {item.asset}: {item.execution_note}"
        for item in allocations
        if item.execution_note
    )
    rationale_lines = "\n".join(f"- {item}" for item in rationale)
    process_review_lines = "\n".join(f"- {item}" for item in process_review)
    risk_return_lines = "\n".join(f"- {item}" for item in risk_return_assessment)
    terminal_distribution_lines = "\n".join(
        f"| {item['bucket']} | {float(item['probability']) * 100:.1f}% |"
        for item in terminal_return_distribution
    )
    drawdown_distribution_lines = "\n".join(
        f"| {item['bucket']} | {float(item['probability']) * 100:.1f}% |"
        for item in drawdown_distribution
    )
    pros_lines = "\n".join(f"- {item}" for item in pros)
    cons_lines = "\n".join(f"- {item}" for item in cons)
    risk_lines = "\n".join(f"- {item}" for item in risks_to_monitor)
    invalidation_lines = "\n".join(f"- {item}" for item in invalid_if)
    rejected_lines = "\n".join(
        f"- {item['method']}: {item['reason']}" for item in risk.rejected_portfolios
    ) or "- None"
    candidate_lines = "\n".join(
        "| "
        + " | ".join(
            [
                str(item["method"]).replace("_", " "),
                str(item.get("family", "n/a")).replace("_", " "),
                "yes" if item["approved"] else "no",
                str(item.get("borda_rank", "n/a")),
                percent(float(item["expected_return"])),
                percent(float(item["expected_volatility"])),
                percent(float(item["estimated_drawdown"])),
                f"{float(item.get('diversification_ratio', 0)):.2f}",
                f"{float(item.get('effective_assets', 0)):.1f}",
                f"{float(item['score']):.3f}",
                str(item["reason"]),
            ]
        )
        + " |"
        for item in candidate_diagnostics
    )
    provider = data_provider_status or {}
    provider_lines = "\n".join(
        [
            f"- Provider: {provider.get('provider', 'n/a')}",
            f"- Configured: {provider.get('configured', 'n/a')}",
            f"- Status: {provider.get('message', 'n/a')}",
            f"- Assets loaded: {provider.get('asset_count', 'n/a')}",
        ]
    )

    return f"""# Self-Driving Portfolio Investment Memo

## Executive Decision

Invest gradually over the recommended phase-in schedule using the **{selected.method.replace("_", " ")}** portfolio.

## Investor Constraints

- Budget: {money(request.budget, request.currency)}
- Time horizon: {request.time_horizon_months} months
- Risk level: {request.risk_level}
- Drawdown tolerance: {percent(policy.max_drawdown_tolerance)}
- Theme limit: {percent(policy.theme_limit)}
- Minimum cash: {percent(policy.minimum_cash)}
- Benchmark: {policy.benchmark}

## Investment Hypothesis

{request.investment_hypothesis}

## Market Regime

- Regime: {macro.macro_regime}
- Confidence: {percent(macro.confidence)}

## Data Provider

{provider_lines}

## Recommended Allocation

{allocation_lines}

## Execution Details

| Instrument | Ticker | ISIN | WKN | Exchange | Trading Currency | Amount | Yahoo Finance |
| --- | --- | --- | --- | --- | --- | ---: | --- |
{execution_rows}

Execution notes:

{execution_notes}

## Expected Risk And Return

- Expected return: {percent(selected.expected_return)} p.a.
- Expected volatility: {percent(selected.expected_volatility)}
- Estimated drawdown scenario: {percent(selected.estimated_max_drawdown)}
- Sharpe estimate: {selected.sharpe_estimate:.2f}

## Risk And Return Evaluation

{risk_return_lines}

## Stochastic Simulation

- Simulations: {int(simulation_summary.get("simulations", 0)):,}
- Horizon: {int(simulation_summary.get("horizon_months", request.time_horizon_months))} months
- Median terminal value: {money(float(simulation_summary.get("median_terminal_value", 0)), request.currency)}
- 5th percentile terminal value: {money(float(simulation_summary.get("p05_terminal_value", 0)), request.currency)}
- 95th percentile terminal value: {money(float(simulation_summary.get("p95_terminal_value", 0)), request.currency)}
- Probability of loss: {percent(float(simulation_summary.get("probability_of_loss", 0)))}
- Probability of drawdown breach: {percent(float(simulation_summary.get("probability_drawdown_breach", 0)))}
- 5% expected shortfall: {percent(float(simulation_summary.get("expected_shortfall_5", 0)))}

Terminal return distribution:

| Return bucket | Probability |
| --- | ---: |
{terminal_distribution_lines}

Max drawdown distribution:

| Drawdown bucket | Probability |
| --- | ---: |
{drawdown_distribution_lines}

## Allocation Check

- Selected method: {str(allocation_check.get("selected_method", "n/a")).replace("_", " ")}
- Weights sum: {float(allocation_check.get("weight_sum", 0)) * 100:.1f}%
- Target amount sum: {money(float(allocation_check.get("amount_sum", 0)), request.currency)}
- Budget match: {allocation_check.get("amount_sum_ok", "n/a")}
- Weights match selected method: {allocation_check.get("weights_match_selected_method", "n/a")}
- Drawdown within tolerance: {allocation_check.get("drawdown_within_tolerance", "n/a")}
- Volatility within target: {allocation_check.get("volatility_within_target", "n/a")}

## Committee Result

- Approved portfolios: {", ".join(risk.approved_portfolios)}

Rejected portfolios:

{rejected_lines}

## Portfolio Method Review

| Method | Family | Approved | Borda Rank | Return | Volatility | Drawdown | Diversification | Effective Assets | CIO Score | Reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
{candidate_lines}

## Process Review From Paper And Literature

{process_review_lines}

## Critical Review

### Pros

{pros_lines}

### Cons

{cons_lines}

### Final Judgement

{final_judgement}

## Rationale

{rationale_lines}

## Risks To Monitor

{risk_lines}

## Invalidation Triggers

{invalidation_lines}

## Rebalancing Rule

{rebalance_rule}
"""


def render_single_asset_memo(review: SingleAssetReview) -> str:
    risks = "\n".join(f"- {item}" for item in review.key_risks)
    invalid = "\n".join(f"- {item}" for item in review.invalid_if)
    watchlist = "\n".join(f"- {item}" for item in review.watchlist_conditions)
    return f"""# Single Investment Idea Review

## Decision

- Asset: {review.asset}
- Decision: {review.decision}
- Suggested position size: {review.suggested_position_size}
- Thesis fit: {review.thesis_fit}

## Investment View

- Expected return range: {review.expected_return_range}
- Downside risk: {review.downside_risk}
- Portfolio role: {review.portfolio_role}
- Required margin of safety: {review.required_margin_of_safety}

## Key Risks

{risks}

## Invalidation Triggers

{invalid}

## Watchlist Conditions

{watchlist}
"""
