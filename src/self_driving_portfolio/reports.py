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
    rationale: list[str],
    risks_to_monitor: list[str],
    invalid_if: list[str],
    rebalance_rule: str,
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
    risk_lines = "\n".join(f"- {item}" for item in risks_to_monitor)
    invalidation_lines = "\n".join(f"- {item}" for item in invalid_if)
    rejected_lines = "\n".join(
        f"- {item['method']}: {item['reason']}" for item in risk.rejected_portfolios
    ) or "- None"

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

## Committee Result

- Approved portfolios: {", ".join(risk.approved_portfolios)}

Rejected portfolios:

{rejected_lines}

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
