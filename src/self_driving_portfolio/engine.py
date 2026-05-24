from __future__ import annotations

from .agents import (
    InvestmentPolicyAgent,
    MacroRegimeAgent,
    PortfolioOptimizerAgent,
    RiskAgent,
    ThemeAssetReturnAgent,
)
from .models import (
    AllocationItem,
    CommitteeResult,
    InvestmentRequest,
    SingleAssetRequest,
    SingleAssetReview,
)
from .reports import render_committee_memo


def run_committee(request: InvestmentRequest) -> CommitteeResult:
    policy = InvestmentPolicyAgent().run(request)
    macro = MacroRegimeAgent().run(request)
    theme_agent = ThemeAssetReturnAgent()
    assumptions = theme_agent.run(request)
    candidates = PortfolioOptimizerAgent().run(policy, assumptions)
    risk = RiskAgent().run(policy, candidates)

    approved_candidates = [candidate for candidate in candidates if candidate.method in risk.approved_portfolios]
    target_midpoint = sum(policy.target_volatility) / 2

    def cio_score(candidate):
        volatility_fit = abs(candidate.expected_volatility - target_midpoint)
        return (
            candidate.expected_return
            + 0.04 * candidate.sharpe_estimate
            - 0.20 * volatility_fit
            + 0.03 * min(candidate.theme_exposure, policy.theme_limit)
        )

    selected = sorted(approved_candidates or candidates, key=cio_score, reverse=True)[0]

    assumption_by_name = {asset.name: asset for asset in assumptions}
    allocations = []
    for asset_name, weight in selected.weights.items():
        if weight <= 0.001:
            continue
        assumption = assumption_by_name.get(asset_name)
        allocations.append(
            AllocationItem(
                asset=asset_name,
                weight=round(weight, 4),
                amount=round(weight * request.budget, 2),
                ticker=assumption.ticker if assumption else None,
                isin=assumption.isin if assumption else None,
                wkn=assumption.wkn if assumption else None,
                security_type=assumption.security_type if assumption else None,
                exchange=assumption.exchange if assumption else None,
                trading_currency=assumption.trading_currency if assumption else None,
                yahoo_ticker=assumption.yahoo_ticker if assumption else None,
                yahoo_url=assumption.yahoo_url if assumption else None,
                execution_note=assumption.execution_note if assumption else None,
            )
        )

    phase_in = "Invest gradually over 3 months"
    if request.risk_level == "conservative" or selected.estimated_max_drawdown < request.max_drawdown_tolerance * 0.95:
        phase_in = "Invest gradually over 6 months and keep extra cash until risk improves"
    elif request.risk_level == "growth":
        phase_in = "Invest in 2 to 3 tranches, keeping risk limits active"

    rationale = [
        "Maps the hypothesis into diversified listed exposures instead of a single narrative bet.",
        "Keeps cash, bonds, and gold as portfolio stabilizers around the AI infrastructure sleeve.",
        "Rejects allocations that breach drawdown, theme concentration, or cash-buffer constraints.",
    ]
    risks_to_monitor = [
        "AI capital expenditure revisions and semiconductor order momentum.",
        "Valuation compression in high-growth technology assets.",
        "Credit spreads, yield-curve shifts, and liquidity stress.",
        "Currency exposure versus the investor's base currency.",
    ]
    invalid_if = [
        "Portfolio drawdown breaches the stated maximum drawdown tolerance.",
        "AI earnings revisions turn negative for two consecutive quarters.",
        "The AI or semiconductor sleeve exceeds the configured theme limit after drift.",
        "Liquidity conditions deteriorate enough to impair rebalancing.",
    ]
    rebalance_rule = (
        f"Rebalance {policy.rebalance_frequency} or when any position drifts more than "
        "5 percentage points from target."
    )
    investment_memo = render_committee_memo(
        request=request,
        policy=policy,
        macro=macro,
        selected=selected,
        allocations=allocations,
        risk=risk,
        rationale=rationale,
        risks_to_monitor=risks_to_monitor,
        invalid_if=invalid_if,
        rebalance_rule=rebalance_rule,
        data_provider_status=theme_agent.provider_status,
    )

    return CommitteeResult(
        decision=f"{phase_in} using the {selected.method.replace('_', ' ')} portfolio.",
        selected_method=selected.method,
        recommended_portfolio=allocations,
        expected_return=round(selected.expected_return, 4),
        expected_volatility=round(selected.expected_volatility, 4),
        max_drawdown_scenario=round(selected.estimated_max_drawdown, 4),
        approved_portfolios=risk.approved_portfolios,
        rejected_portfolios=risk.rejected_portfolios,
        stress_test_summary=risk.stress_test_summary,
        rationale=rationale,
        risks_to_monitor=risks_to_monitor,
        invalid_if=invalid_if,
        rebalance_rule=rebalance_rule,
        investment_memo=investment_memo,
        data_provider_status=theme_agent.provider_status,
        policy=policy,
        macro_regime=macro,
        asset_assumptions=assumptions,
    )


def run_single_asset_review(request: SingleAssetRequest) -> SingleAssetReview:
    asset_upper = request.asset.upper().strip()
    thesis = request.hypothesis.lower()
    high_ai_fit = any(term in thesis or term in asset_upper for term in ["ai", "semiconductor", "data", "cloud", "gpu", "NVDA"])

    if request.distressed or request.idea_type.lower() == "distressed":
        has_catalyst = bool(request.catalyst.strip())
        decision = "watchlist" if has_catalyst else "avoid"
        suggested_size = f"0-{min(request.maximum_position_size * 100, 2):.0f}%"
        return SingleAssetReview(
            asset=asset_upper,
            decision=decision,
            suggested_position_size=suggested_size,
            thesis_fit="event-driven",
            expected_return_range="highly asymmetric but catalyst-dependent",
            downside_risk="permanent capital loss possible",
            portfolio_role="small special-situation sleeve only",
            required_margin_of_safety="clear recovery value, visible liquidity runway, and identifiable catalyst",
            key_risks=[
                "insolvency or restructuring outcome worse than modeled",
                "catalyst delay",
                "poor liquidity",
                "legal or capital-structure subordination risk",
            ],
            invalid_if=[
                "recovery value cannot be bounded",
                "liquidity runway falls below 12 months",
                "catalyst disappears or becomes unverifiable",
            ],
            watchlist_conditions=[
                "restructuring terms become public",
                "asset sale or refinancing process begins",
                "position can be sized small enough to survive a zero",
            ],
        )

    if high_ai_fit:
        decision = "small_position_or_watchlist"
        thesis_fit = "high"
        downside = "material if AI capex expectations reset or valuation compresses"
        expected = "above-market potential with high valuation sensitivity"
        role = "satellite growth exposure"
    else:
        decision = "watchlist_pending_more_evidence"
        thesis_fit = "medium"
        downside = "depends on valuation, earnings quality, and balance-sheet resilience"
        expected = "uncertain until fundamentals and valuation are modeled"
        role = "candidate satellite or diversifier"

    return SingleAssetReview(
        asset=asset_upper,
        decision=decision,
        suggested_position_size=f"0-{request.maximum_position_size * 100:.0f}%",
        thesis_fit=thesis_fit,
        expected_return_range=expected,
        downside_risk=downside,
        portfolio_role=role,
        required_margin_of_safety="prefer entry after valuation support, earnings confirmation, or improved risk/reward",
        key_risks=[
            "valuation compression",
            "earnings revision downgrade",
            "position concentration",
            "macro sensitivity",
        ],
        invalid_if=[
            "core thesis metrics deteriorate for two consecutive quarters",
            "price action breaks down while fundamentals weaken",
            "position would breach portfolio concentration rules",
        ],
        watchlist_conditions=[
            "valuation resets to a more attractive range",
            "earnings revisions remain positive",
            "risk budget is available within the total portfolio",
        ],
    )
