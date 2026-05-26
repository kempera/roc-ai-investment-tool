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
    MacroRegime,
    Policy,
    PortfolioCandidate,
    RiskReview,
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
        drawdown_buffer = max(candidate.estimated_max_drawdown - policy.max_drawdown_tolerance, 0)
        theme_headroom = max(policy.theme_limit - candidate.theme_exposure, 0)
        method_preference = {
            "committee_blend": 0.025,
            "drawdown_constrained": 0.012,
            "risk_parity": 0.004,
            "minimum_variance": -0.006,
            "maximum_sharpe": -0.006,
            "equal_weight_benchmark": -0.030,
        }.get(candidate.method, 0)
        return (
            candidate.expected_return
            + 0.025 * candidate.sharpe_estimate
            - 0.18 * volatility_fit
            + 0.030 * drawdown_buffer
            + 0.010 * theme_headroom
            + method_preference
        )

    selected = sorted(approved_candidates or candidates, key=cio_score, reverse=True)[0]
    candidate_diagnostics = build_candidate_diagnostics(candidates, risk, cio_score)

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
    reconcile_allocation_amounts(allocations, request.budget)

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
    allocation_check = build_allocation_check(request, policy, selected, allocations)
    risk_return_assessment = build_risk_return_assessment(request, policy, selected, allocation_check, theme_agent.provider_status)
    pros, cons, final_judgement = critical_review(
        request=request,
        policy=policy,
        macro=macro,
        selected=selected,
        risk=risk,
        data_provider_status=theme_agent.provider_status,
    )
    investment_memo = render_committee_memo(
        request=request,
        policy=policy,
        macro=macro,
        selected=selected,
        allocations=allocations,
        risk=risk,
        candidate_diagnostics=candidate_diagnostics,
        rationale=rationale,
        risk_return_assessment=risk_return_assessment,
        allocation_check=allocation_check,
        pros=pros,
        cons=cons,
        final_judgement=final_judgement,
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
        candidate_diagnostics=candidate_diagnostics,
        rationale=rationale,
        risk_return_assessment=risk_return_assessment,
        allocation_check=allocation_check,
        pros=pros,
        cons=cons,
        final_judgement=final_judgement,
        risks_to_monitor=risks_to_monitor,
        invalid_if=invalid_if,
        rebalance_rule=rebalance_rule,
        investment_memo=investment_memo,
        data_provider_status=theme_agent.provider_status,
        policy=policy,
        macro_regime=macro,
        asset_assumptions=assumptions,
    )


def reconcile_allocation_amounts(allocations: list[AllocationItem], budget: float) -> None:
    if not allocations:
        return
    residual = round(budget - sum(item.amount for item in allocations), 2)
    if abs(residual) < 0.01:
        return
    cash_item = next((item for item in allocations if item.asset.lower() == "cash"), None)
    target = cash_item or max(allocations, key=lambda item: item.amount)
    target.amount = round(target.amount + residual, 2)


def build_candidate_diagnostics(
    candidates: list[PortfolioCandidate],
    risk: RiskReview,
    score_fn,
) -> list[dict[str, str | float | bool]]:
    rejection_reasons = {item["method"]: item["reason"] for item in risk.rejected_portfolios}
    diagnostics = []
    for candidate in candidates:
        diagnostics.append(
            {
                "method": candidate.method,
                "approved": candidate.method in risk.approved_portfolios,
                "score": round(float(score_fn(candidate)), 4),
                "expected_return": round(candidate.expected_return, 4),
                "expected_volatility": round(candidate.expected_volatility, 4),
                "estimated_drawdown": round(candidate.estimated_max_drawdown, 4),
                "sharpe": round(candidate.sharpe_estimate, 4),
                "theme_exposure": round(candidate.theme_exposure, 4),
                "reason": rejection_reasons.get(candidate.method, "approved"),
            }
        )
    return sorted(diagnostics, key=lambda item: float(item["score"]), reverse=True)


def build_allocation_check(
    request: InvestmentRequest,
    policy: Policy,
    selected: PortfolioCandidate,
    allocations: list[AllocationItem],
) -> dict[str, bool | float | str]:
    weight_sum = round(sum(item.weight for item in allocations), 6)
    amount_sum = round(sum(item.amount for item in allocations), 2)
    drawdown_buffer = selected.estimated_max_drawdown - policy.max_drawdown_tolerance
    return_to_volatility = selected.expected_return / selected.expected_volatility if selected.expected_volatility else 0
    selected_weights = [round(weight, 4) for weight in selected.weights.values() if weight > 0.001]
    allocation_weights = [item.weight for item in allocations]

    return {
        "selected_method": selected.method,
        "weight_sum": weight_sum,
        "amount_sum": amount_sum,
        "budget": round(request.budget, 2),
        "weights_match_selected_method": allocation_weights == selected_weights,
        "weight_sum_ok": abs(weight_sum - 1.0) <= 0.001,
        "amount_sum_ok": abs(amount_sum - request.budget) <= max(0.05, request.budget * 0.00001),
        "volatility_within_target": policy.target_volatility[0] <= selected.expected_volatility <= policy.target_volatility[1],
        "drawdown_within_tolerance": selected.estimated_max_drawdown >= policy.max_drawdown_tolerance,
        "drawdown_buffer": round(drawdown_buffer, 4),
        "return_to_volatility": round(return_to_volatility, 4),
        "theme_exposure": round(selected.theme_exposure, 4),
        "theme_exposure_within_limit": selected.theme_exposure <= policy.theme_limit,
    }


def build_risk_return_assessment(
    request: InvestmentRequest,
    policy: Policy,
    selected: PortfolioCandidate,
    allocation_check: dict[str, bool | float | str],
    data_provider_status: dict[str, str | int | bool | None],
) -> list[str]:
    drawdown_buffer = float(allocation_check["drawdown_buffer"])
    provider = data_provider_status.get("provider", "unknown provider")
    assessment = [
        (
            f"Expected return is {selected.expected_return * 100:.1f}% p.a. with {selected.expected_volatility * 100:.1f}% "
            f"expected volatility, implying a return-to-volatility ratio of {float(allocation_check['return_to_volatility']):.2f}."
        ),
        (
            f"Estimated bear drawdown is {selected.estimated_max_drawdown * 100:.1f}% versus the user limit of "
            f"{policy.max_drawdown_tolerance * 100:.1f}%, leaving {drawdown_buffer * 100:.1f} percentage points of model buffer."
        ),
        (
            f"Volatility is {'inside' if allocation_check['volatility_within_target'] else 'outside'} the target range "
            f"of {policy.target_volatility[0] * 100:.1f}% to {policy.target_volatility[1] * 100:.1f}% for the {request.risk_level} profile."
        ),
        (
            f"Theme exposure is {selected.theme_exposure * 100:.1f}% of portfolio risk budget versus a configured limit of "
            f"{policy.theme_limit * 100:.1f}%."
        ),
    ]
    if provider == "Built-in universe":
        assessment.append(
            "The analysis uses the built-in UCITS universe and static assumptions, so treat it as a portfolio design baseline rather than a live market forecast."
        )
    elif data_provider_status.get("fallback"):
        assessment.append(
            f"{provider} did not deliver usable data and the engine fell back to built-in assumptions."
        )
    return assessment


def critical_review(
    request: InvestmentRequest,
    policy: Policy,
    macro: MacroRegime,
    selected: PortfolioCandidate,
    risk: RiskReview,
    data_provider_status: dict[str, str | int | bool | None],
) -> tuple[list[str], list[str], str]:
    provider_name = str(data_provider_status.get("provider") or "unknown provider")
    provider_ok = bool(data_provider_status.get("configured")) and not bool(data_provider_status.get("fallback"))
    provider_enriched = provider_ok and "capital iq" in provider_name.lower()
    drawdown_buffer = selected.estimated_max_drawdown - policy.max_drawdown_tolerance
    near_drawdown_limit = drawdown_buffer < 0.03

    pros = [
        f"The selected {selected.method.replace('_', ' ')} portfolio stays within the stated drawdown tolerance in the model.",
        "The recommendation is diversified across growth, defensive, and liquidity sleeves instead of relying on one security.",
        f"Expected volatility of {selected.expected_volatility * 100:.1f}% is inside or near the target range for a {request.risk_level} mandate.",
    ]
    if selected.sharpe_estimate > 0.20:
        pros.append(f"The portfolio has a positive estimated Sharpe ratio of {selected.sharpe_estimate:.2f} after the cash-rate hurdle.")
    if risk.approved_portfolios:
        pros.append(f"{len(risk.approved_portfolios)} construction methods survived the risk filter, reducing dependence on one optimizer.")
    if provider_enriched:
        pros.append(f"The investable universe was enriched through {provider_name}, improving security-level evidence versus built-in assumptions.")

    cons = [
        "The expected return and drawdown numbers are model estimates, not forecasts; the realised path can be materially worse.",
        "AI infrastructure exposure remains sensitive to valuation compression, earnings revisions, and semiconductor-cycle risk.",
        "The approach still requires human verification of execution venue, spreads, tax treatment, and suitability before any trade.",
    ]
    if near_drawdown_limit:
        cons.append("The estimated drawdown is close to the stated limit, so adverse correlation or liquidity surprises could breach tolerance.")
    if selected.theme_exposure > policy.theme_limit * 0.80:
        cons.append("Theme exposure is high relative to the configured limit, making the result vulnerable to a thesis-specific reversal.")
    if data_provider_status.get("fallback") or (not provider_ok and "capital iq" in provider_name.lower()):
        cons.append(
            f"{provider_name} did not provide confirmed live universe data; the decision relies on built-in assumptions until the API check passes."
        )
    if risk.rejected_portfolios:
        cons.append(f"{len(risk.rejected_portfolios)} candidate portfolios were rejected, showing that the hypothesis can breach risk limits if expressed too aggressively.")

    if selected.estimated_max_drawdown < policy.max_drawdown_tolerance:
        final_judgement = (
            "Do not invest yet. The selected portfolio breaches the stated drawdown tolerance, so the hypothesis should be resized, hedged, "
            "or deferred until a compliant allocation is available."
        )
    elif data_provider_status.get("fallback") or (not provider_ok and "capital iq" in provider_name.lower()):
        final_judgement = (
            "Conditional proceed. The portfolio is acceptable as a staged, risk-limited allocation, but the investment committee should treat "
            "it as provisional until Capital IQ/API data is confirmed and security identifiers are reviewed."
        )
    elif near_drawdown_limit:
        final_judgement = (
            "Proceed cautiously. The allocation is investable, but only with staged execution, active monitoring, and no increase in theme exposure "
            "unless drawdown risk improves."
        )
    else:
        final_judgement = (
            "Proceed with staged execution. The recommendation has a reasonable balance of thesis exposure, diversification, and downside control "
            "for the stated mandate."
        )

    return pros, cons, final_judgement


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
