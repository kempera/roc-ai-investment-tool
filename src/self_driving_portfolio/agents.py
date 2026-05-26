from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize

from .data import estimate_from_returns, maybe_get_live_returns
from .models import (
    AssetAssumption,
    InvestmentRequest,
    MacroRegime,
    Policy,
    PortfolioCandidate,
    RiskReview,
)
from .providers import get_research_universe


class InvestmentPolicyAgent:
    def run(self, request: InvestmentRequest) -> Policy:
        vol_targets = {
            "conservative": (0.04, 0.08),
            "balanced": (0.08, 0.12),
            "growth": (0.12, 0.18),
        }
        return Policy(
            portfolio_mode="portfolio_construction",
            base_currency=request.currency,
            budget=request.budget,
            target_volatility=vol_targets[request.risk_level],
            max_drawdown_tolerance=request.max_drawdown_tolerance,
            single_position_limit=request.single_name_limit,
            theme_limit=request.theme_limit,
            minimum_cash=request.minimum_cash_buffer,
            excluded_assets=request.excluded_assets,
            benchmark=request.benchmark,
            rebalance_frequency=request.rebalance_frequency,
        )


class MacroRegimeAgent:
    def run(self, request: InvestmentRequest) -> MacroRegime:
        hypothesis = request.investment_hypothesis.lower()
        if "distress" in hypothesis or "recession" in hypothesis:
            regime = "recession_or_liquidity_stress"
            confidence = 0.55
        elif "ai" in hypothesis or "infrastructure" in hypothesis:
            regime = "late_cycle_with_structural_ai_capex"
            confidence = 0.62
        else:
            regime = "balanced_expansion"
            confidence = 0.50

        return MacroRegime(
            macro_regime=regime,
            confidence=confidence,
            risk_implications=[
                "Stress-test equity valuation compression",
                "Keep liquidity reserve aligned with user requirement",
                "Avoid portfolios dependent on one macro outcome",
            ],
            portfolio_tilts={
                "equities": "neutral_to_overweight" if request.risk_level != "conservative" else "neutral",
                "bonds": "neutral",
                "cash": "minimum_buffer",
                "gold": "small_hedge",
            },
        )


class ThemeAssetReturnAgent:
    def __init__(self) -> None:
        self.provider_status: dict[str, str | int | bool | None] = {}

    def run(self, request: InvestmentRequest) -> list[AssetAssumption]:
        assumptions, status = get_research_universe(request)
        self.provider_status = status

        if not request.use_live_data:
            return assumptions

        yahoo_tickers = [item.yahoo_ticker or item.ticker for item in assumptions]
        live_returns = maybe_get_live_returns(yahoo_tickers)
        if live_returns is None:
            return assumptions

        live_estimates = estimate_from_returns(live_returns)
        adjusted = []
        for asset in assumptions:
            estimate = live_estimates.get(asset.yahoo_ticker or asset.ticker)
            if not estimate:
                adjusted.append(asset)
                continue

            adjusted.append(
                asset.model_copy(
                    update={
                        "expected_return": 0.65 * asset.expected_return + 0.35 * estimate["expected_return"],
                        "expected_volatility": max(asset.expected_volatility, estimate["expected_volatility"]),
                        "max_drawdown_estimate": min(asset.max_drawdown_estimate, estimate["max_drawdown_estimate"]),
                    }
                )
            )
        return adjusted


class PortfolioOptimizerAgent:
    def run(self, policy: Policy, assumptions: list[AssetAssumption]) -> list[PortfolioCandidate]:
        names = [asset.name for asset in assumptions]
        cash_rate = 0.025
        expected_returns = np.array(
            [
                cash_rate + asset.confidence * (asset.expected_return - cash_rate)
                for asset in assumptions
            ]
        )
        volatilities = np.array([asset.expected_volatility for asset in assumptions])
        correlation = self._correlation_matrix(assumptions)
        covariance = np.outer(volatilities, volatilities) * correlation

        equal_weight = np.ones(len(names)) / len(names)
        risk_parity = self._risk_parity(volatilities, policy, covariance, assumptions)
        minimum_variance = self._min_variance(expected_returns, covariance, policy, assumptions)
        maximum_diversification = self._maximum_diversification(volatilities, covariance, policy, assumptions)
        maximum_sharpe = self._max_sharpe(expected_returns, covariance, policy, assumptions)
        maximum_entropy = self._maximum_entropy(expected_returns, covariance, policy, assumptions, maximum_sharpe)
        tail_risk_parity = self._tail_risk_parity(covariance, policy, assumptions)
        drawdown_constrained = self._drawdown_constrained(expected_returns, covariance, policy, assumptions)
        adversarial_diversifier = self._adversarial_diversifier(
            expected_returns,
            covariance,
            policy,
            assumptions,
            {
                "risk_parity": risk_parity,
                "minimum_variance": minimum_variance,
                "maximum_diversification": maximum_diversification,
                "maximum_sharpe": maximum_sharpe,
                "maximum_entropy": maximum_entropy,
                "tail_risk_parity": tail_risk_parity,
                "drawdown_constrained": drawdown_constrained,
            },
        )
        committee_blend = self._committee_blend(
            {
                "risk_parity": risk_parity,
                "minimum_variance": minimum_variance,
                "maximum_diversification": maximum_diversification,
                "maximum_sharpe": maximum_sharpe,
                "maximum_entropy": maximum_entropy,
                "tail_risk_parity": tail_risk_parity,
                "drawdown_constrained": drawdown_constrained,
                "adversarial_diversifier": adversarial_diversifier,
            },
            policy,
        )

        candidates = []
        candidates.append(self._candidate("equal_weight_benchmark", "heuristic", equal_weight, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("risk_parity", "risk_structured", risk_parity, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("minimum_variance", "risk_structured", minimum_variance, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("maximum_diversification", "risk_structured", maximum_diversification, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("maximum_sharpe", "return_optimized", maximum_sharpe, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("maximum_entropy", "researcher", maximum_entropy, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("tail_risk_parity", "non_traditional", tail_risk_parity, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("drawdown_constrained", "non_traditional", drawdown_constrained, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("adversarial_diversifier", "non_traditional", adversarial_diversifier, names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("committee_blend", "cio_ensemble", committee_blend, names, expected_returns, covariance, assumptions))
        return candidates

    def _correlation_matrix(self, assumptions: list[AssetAssumption]) -> np.ndarray:
        count = len(assumptions)
        matrix = np.eye(count)
        for i, left in enumerate(assumptions):
            for j, right in enumerate(assumptions):
                if i == j:
                    continue
                matrix[i, j] = self._pairwise_correlation(left, right)
        return matrix

    def _pairwise_correlation(self, left: AssetAssumption, right: AssetAssumption) -> float:
        left_class = left.asset_class.lower()
        right_class = right.asset_class.lower()
        classes = {left_class, right_class}

        if "cash" in classes:
            return 0.02
        if left_class == right_class == "equity_etf":
            if min(left.theme_exposure, right.theme_exposure) >= 60:
                return 0.82
            return 0.68
        if left_class.startswith("equity") and right_class.startswith("equity"):
            return 0.72
        if any(item.startswith("equity") for item in classes) and "bond_etf" in classes:
            return 0.18
        if any(item.startswith("equity") for item in classes) and "commodity" in classes:
            return 0.12
        if "bond_etf" in classes and "commodity" in classes:
            return 0.06
        if left_class == right_class == "bond_etf":
            return 0.62
        if left_class == right_class == "commodity":
            return 0.50
        return 0.30

    def _bounds(self, policy: Policy, assumptions: list[AssetAssumption]) -> list[tuple[float, float]]:
        bounds = []
        for asset in assumptions:
            if asset.asset_class == "cash":
                bounds.append((policy.minimum_cash, 0.40))
            elif asset.asset_class == "equity_etf":
                bounds.append((0.0, min(policy.theme_limit, 0.45)))
            else:
                bounds.append((0.0, 0.35))
        return bounds

    def _constraints(self) -> list[dict]:
        return [{"type": "eq", "fun": lambda weights: np.sum(weights) - 1}]

    def _risk_constraints(self, policy: Policy, covariance: np.ndarray, assumptions: list[AssetAssumption]) -> list[dict]:
        return self._constraints() + [
            {
                "type": "ineq",
                "fun": lambda weights: self._estimated_drawdown(weights, assumptions) - policy.max_drawdown_tolerance,
            },
            {
                "type": "ineq",
                "fun": lambda weights: policy.theme_limit - self._theme_exposure(weights, assumptions),
            },
            {
                "type": "ineq",
                "fun": lambda weights: policy.target_volatility[1] * 1.05 - self._volatility(weights, covariance),
            },
        ]

    def _normalize(self, weights: np.ndarray) -> np.ndarray:
        weights = np.clip(weights, 0, None)
        total = weights.sum()
        if total <= 0:
            return np.ones(len(weights)) / len(weights)
        return weights / total

    def _project_to_policy(
        self,
        weights: np.ndarray,
        policy: Policy,
        covariance: np.ndarray,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        count = len(weights)
        target = self._normalize(weights)
        result = minimize(
            lambda candidate: float(np.sum((candidate - target) ** 2)),
            target,
            bounds=self._bounds(policy, assumptions),
            constraints=self._risk_constraints(policy, covariance, assumptions),
            method="SLSQP",
            options={"maxiter": 300},
        )
        if result.success:
            return self._normalize(result.x)

        clipped = np.array(
            [min(max(weight, low), high) for weight, (low, high) in zip(target, self._bounds(policy, assumptions))]
        )
        if clipped.sum() <= 0:
            clipped = np.ones(count) / count
        return self._normalize(clipped)

    def _risk_parity(
        self,
        volatilities: np.ndarray,
        policy: Policy,
        covariance: np.ndarray,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        inv_vol = 1 / np.maximum(volatilities, 0.04)
        weights = self._normalize(inv_vol)
        weights[-1] = max(weights[-1], policy.minimum_cash)
        if weights[-1] > 0.25:
            excess = weights[-1] - 0.25
            weights[-1] = 0.25
            non_cash = self._normalize(weights[:-1])
            weights[:-1] += excess * non_cash
        return self._project_to_policy(weights, policy, covariance, assumptions)

    def _min_variance(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        del expected_returns
        count = covariance.shape[0]
        result = minimize(
            lambda weights: weights @ covariance @ weights,
            np.ones(count) / count,
            bounds=self._bounds(policy, assumptions),
            constraints=self._constraints(),
            method="SLSQP",
        )
        return self._normalize(result.x if result.success else np.ones(count) / count)

    def _max_sharpe(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        count = covariance.shape[0]

        def objective(weights: np.ndarray) -> float:
            ret = weights @ expected_returns
            vol = math.sqrt(max(weights @ covariance @ weights, 1e-9))
            return -(ret - 0.025) / vol

        result = minimize(
            objective,
            np.ones(count) / count,
            bounds=self._bounds(policy, assumptions),
            constraints=self._constraints(),
            method="SLSQP",
        )
        weights = self._normalize(result.x if result.success else np.ones(count) / count)
        weights[-1] = max(weights[-1], policy.minimum_cash)
        return self._normalize(weights)

    def _maximum_diversification(
        self,
        volatilities: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        count = len(assumptions)
        start = self._risk_parity(volatilities, policy, covariance, assumptions)

        def objective(weights: np.ndarray) -> float:
            weighted_volatility = float(weights @ volatilities)
            portfolio_volatility = self._volatility(weights, covariance)
            diversification_ratio = weighted_volatility / max(portfolio_volatility, 0.001)
            return -diversification_ratio

        result = minimize(
            objective,
            start,
            bounds=self._bounds(policy, assumptions),
            constraints=self._risk_constraints(policy, covariance, assumptions),
            method="SLSQP",
            options={"maxiter": 500},
        )
        return self._normalize(result.x if result.success else start)

    def _maximum_entropy(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
        maximum_sharpe: np.ndarray,
    ) -> np.ndarray:
        count = len(assumptions)
        start = self._project_to_policy(np.ones(count) / count, policy, covariance, assumptions)
        max_sharpe_floor = max(self._sharpe(maximum_sharpe, expected_returns, covariance) * 0.60, 0.02)

        def entropy(weights: np.ndarray) -> float:
            usable = np.clip(weights, 1e-9, 1)
            return float(-np.sum(usable * np.log(usable)) / math.log(count))

        def objective(weights: np.ndarray) -> float:
            drawdown_buffer = max(self._estimated_drawdown(weights, assumptions) - policy.max_drawdown_tolerance, 0)
            return -(
                entropy(weights)
                + 0.20 * max(self._sharpe(weights, expected_returns, covariance), 0)
                + 0.10 * drawdown_buffer
            )

        constraints = self._risk_constraints(policy, covariance, assumptions) + [
            {
                "type": "ineq",
                "fun": lambda weights: self._sharpe(weights, expected_returns, covariance) - max_sharpe_floor,
            }
        ]
        result = minimize(
            objective,
            start,
            bounds=self._bounds(policy, assumptions),
            constraints=constraints,
            method="SLSQP",
            options={"maxiter": 500},
        )
        return self._normalize(result.x if result.success else start)

    def _tail_risk_parity(
        self,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        count = len(assumptions)
        tail_risk = np.array(
            [
                max(abs(asset.max_drawdown_estimate), asset.expected_volatility * 1.75, 0.02)
                for asset in assumptions
            ]
        )
        start = self._project_to_policy(1 / tail_risk, policy, covariance, assumptions)

        def objective(weights: np.ndarray) -> float:
            contributions = weights * tail_risk
            target = float(np.mean(contributions))
            return float(np.sum((contributions - target) ** 2) + 0.05 * self._volatility(weights, covariance))

        result = minimize(
            objective,
            start,
            bounds=self._bounds(policy, assumptions),
            constraints=self._risk_constraints(policy, covariance, assumptions),
            method="SLSQP",
            options={"maxiter": 500},
        )
        return self._normalize(result.x if result.success else start)

    def _drawdown_constrained(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        count = len(assumptions)
        start = self._risk_parity(
            np.array([asset.expected_volatility for asset in assumptions]),
            policy,
            covariance,
            assumptions,
        )
        target_volatility = sum(policy.target_volatility) / 2

        def objective(weights: np.ndarray) -> float:
            ret = weights @ expected_returns
            vol = self._volatility(weights, covariance)
            drawdown = self._estimated_drawdown(weights, assumptions)
            theme = self._theme_exposure(weights, assumptions)
            drawdown_buffer = max(drawdown - policy.max_drawdown_tolerance, 0)
            theme_headroom = max(policy.theme_limit - theme, 0)
            return -(
                ret
                + 0.025 * ((ret - 0.025) / max(vol, 0.001))
                + 0.020 * drawdown_buffer
                + 0.010 * theme_headroom
                - 0.12 * abs(vol - target_volatility)
            )

        result = minimize(
            objective,
            start if len(start) == count else np.ones(count) / count,
            bounds=self._bounds(policy, assumptions),
            constraints=self._risk_constraints(policy, covariance, assumptions),
            method="SLSQP",
            options={"maxiter": 500},
        )
        return self._normalize(result.x if result.success else start)

    def _adversarial_diversifier(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
        method_weights: dict[str, np.ndarray],
    ) -> np.ndarray:
        count = len(assumptions)
        centroid = self._normalize(np.mean(np.array(list(method_weights.values())), axis=0))
        max_sharpe = max(self._sharpe(method_weights["maximum_sharpe"], expected_returns, covariance), 0.02)
        sharpe_floor = max_sharpe * 0.50
        start = self._project_to_policy(1 - centroid, policy, covariance, assumptions)

        def objective(weights: np.ndarray) -> float:
            active = weights - centroid
            tracking_variance = float(active @ covariance @ active)
            entropy_penalty = float(np.sum(np.clip(weights, 1e-9, 1) * np.log(np.clip(weights, 1e-9, 1))))
            return -(tracking_variance - 0.002 * entropy_penalty)

        constraints = self._risk_constraints(policy, covariance, assumptions) + [
            {
                "type": "ineq",
                "fun": lambda weights: self._sharpe(weights, expected_returns, covariance) - sharpe_floor,
            }
        ]
        result = minimize(
            objective,
            start,
            bounds=self._bounds(policy, assumptions),
            constraints=constraints,
            method="SLSQP",
            options={"maxiter": 700},
        )
        return self._normalize(result.x if result.success else start)

    def _committee_blend(self, method_weights: dict[str, np.ndarray], policy: Policy) -> np.ndarray:
        if policy.target_volatility[1] <= 0.08:
            style_weights = {
                "risk_parity": 0.24,
                "minimum_variance": 0.16,
                "maximum_diversification": 0.22,
                "maximum_sharpe": 0.03,
                "maximum_entropy": 0.08,
                "tail_risk_parity": 0.17,
                "drawdown_constrained": 0.08,
                "adversarial_diversifier": 0.02,
            }
        elif policy.target_volatility[1] >= 0.18:
            style_weights = {
                "risk_parity": 0.10,
                "minimum_variance": 0.03,
                "maximum_diversification": 0.17,
                "maximum_sharpe": 0.28,
                "maximum_entropy": 0.12,
                "tail_risk_parity": 0.08,
                "drawdown_constrained": 0.17,
                "adversarial_diversifier": 0.05,
            }
        else:
            style_weights = {
                "risk_parity": 0.12,
                "minimum_variance": 0.03,
                "maximum_diversification": 0.10,
                "maximum_sharpe": 0.18,
                "maximum_entropy": 0.17,
                "tail_risk_parity": 0.05,
                "drawdown_constrained": 0.30,
                "adversarial_diversifier": 0.05,
            }

        blended = None
        for method, style_weight in style_weights.items():
            weights = method_weights[method]
            blended = style_weight * weights if blended is None else blended + style_weight * weights

        blended = self._normalize(blended)
        blended[-1] = max(blended[-1], policy.minimum_cash)
        return self._normalize(blended)

    def _volatility(self, weights: np.ndarray, covariance: np.ndarray) -> float:
        return float(math.sqrt(max(weights @ covariance @ weights, 0)))

    def _sharpe(self, weights: np.ndarray, expected_returns: np.ndarray, covariance: np.ndarray) -> float:
        ret = float(weights @ expected_returns)
        vol = self._volatility(weights, covariance)
        return float((ret - 0.025) / max(vol, 0.001))

    def _theme_exposure(self, weights: np.ndarray, assumptions: list[AssetAssumption]) -> float:
        return float(sum(weight * asset.theme_exposure / 100 for weight, asset in zip(weights, assumptions)))

    def _estimated_drawdown(self, weights: np.ndarray, assumptions: list[AssetAssumption]) -> float:
        theme = self._theme_exposure(weights, assumptions)
        raw_drawdown = sum(weight * asset.max_drawdown_estimate for weight, asset in zip(weights, assumptions))
        diversification_factor = 0.62 + 0.10 * theme
        return float(raw_drawdown * diversification_factor)

    def _candidate(
        self,
        method: str,
        method_family: str,
        weights: np.ndarray,
        names: list[str],
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        assumptions: list[AssetAssumption],
    ) -> PortfolioCandidate:
        weights = self._normalize(weights)
        ret = float(weights @ expected_returns)
        vol = self._volatility(weights, covariance)
        theme_exposure = self._theme_exposure(weights, assumptions)
        drawdown = self._estimated_drawdown(weights, assumptions)
        sharpe = self._sharpe(weights, expected_returns, covariance)
        asset_volatilities = np.array([asset.expected_volatility for asset in assumptions])
        diversification_ratio = float((weights @ asset_volatilities) / max(vol, 0.001))
        effective_assets = float(1 / max(np.sum(weights**2), 0.001))
        concentration = float(np.max(weights))
        average_confidence = float(
            sum(weight * asset.confidence for weight, asset in zip(weights, assumptions))
        )
        estimation_risk = float(
            min(1, max(0, 0.55 * concentration + 0.30 * theme_exposure + 0.15 * (1 - average_confidence)))
        )
        return PortfolioCandidate(
            method=method,
            method_family=method_family,
            weights={name: float(weight) for name, weight in zip(names, weights)},
            expected_return=ret,
            expected_volatility=vol,
            estimated_max_drawdown=drawdown,
            sharpe_estimate=sharpe,
            theme_exposure=theme_exposure,
            effective_assets=effective_assets,
            diversification_ratio=diversification_ratio,
            estimation_risk=estimation_risk,
        )


class RiskAgent:
    def run(self, policy: Policy, candidates: list[PortfolioCandidate]) -> RiskReview:
        approved = []
        rejected = []
        for candidate in candidates:
            reasons = []
            if candidate.estimated_max_drawdown < policy.max_drawdown_tolerance - 1e-6:
                reasons.append("estimated drawdown breaches tolerance")
            if candidate.theme_exposure > policy.theme_limit + 1e-6:
                reasons.append("theme exposure exceeds limit")
            if candidate.expected_volatility > policy.target_volatility[1] * 1.35:
                reasons.append("volatility materially exceeds target")
            if candidate.weights.get("Cash", 0) < policy.minimum_cash - 1e-6:
                reasons.append("cash buffer below minimum")
            if candidate.method == "adversarial_diversifier":
                reasons.append("dissenting diversifier for ensemble use, not a standalone portfolio")

            if reasons:
                rejected.append({"method": candidate.method, "reason": "; ".join(reasons)})
            else:
                approved.append(candidate.method)

        if not approved and candidates:
            best = sorted(candidates, key=lambda item: (item.estimated_max_drawdown, item.expected_volatility), reverse=True)[0]
            approved.append(best.method)
            rejected = [item for item in rejected if item["method"] != best.method]

        return RiskReview(
            approved_portfolios=approved,
            rejected_portfolios=rejected,
            stress_test_summary={
                "equity_crash": -0.30,
                "rate_shock_bps": 200,
                "usd_eur_move": 0.15,
                "ai_valuation_compression": -0.35,
                "liquidity_risk": "acceptable_if_cash_buffer_maintained",
            },
        )
