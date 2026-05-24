from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize

from .data import DEFAULT_UNIVERSE, estimate_from_returns, maybe_get_live_returns
from .models import (
    AssetAssumption,
    InvestmentRequest,
    MacroRegime,
    Policy,
    PortfolioCandidate,
    RiskReview,
)


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
    def run(self, request: InvestmentRequest) -> list[AssetAssumption]:
        assets = list(DEFAULT_UNIVERSE.values())
        assumptions = [AssetAssumption(**asset) for asset in assets]

        if not request.use_live_data:
            return assumptions

        live_returns = maybe_get_live_returns([item.ticker for item in assumptions])
        if live_returns is None:
            return assumptions

        live_estimates = estimate_from_returns(live_returns)
        adjusted = []
        for asset in assumptions:
            estimate = live_estimates.get(asset.ticker)
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
        expected_returns = np.array([asset.expected_return * asset.confidence for asset in assumptions])
        volatilities = np.array([asset.expected_volatility for asset in assumptions])
        correlation = np.full((len(assumptions), len(assumptions)), 0.35)
        np.fill_diagonal(correlation, 1.0)
        covariance = np.outer(volatilities, volatilities) * correlation

        candidates = []
        candidates.append(self._candidate("equal_weight", np.ones(len(names)) / len(names), names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("risk_parity", self._risk_parity(volatilities, policy), names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("minimum_variance", self._min_variance(expected_returns, covariance, policy), names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("maximum_sharpe", self._max_sharpe(expected_returns, covariance, policy), names, expected_returns, covariance, assumptions))
        candidates.append(self._candidate("drawdown_constrained", self._drawdown_constrained(expected_returns, covariance, policy, assumptions), names, expected_returns, covariance, assumptions))
        return candidates

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

    def _normalize(self, weights: np.ndarray) -> np.ndarray:
        weights = np.clip(weights, 0, None)
        total = weights.sum()
        if total <= 0:
            return np.ones(len(weights)) / len(weights)
        return weights / total

    def _risk_parity(self, volatilities: np.ndarray, policy: Policy) -> np.ndarray:
        inv_vol = 1 / np.maximum(volatilities, 0.04)
        weights = self._normalize(inv_vol)
        weights[-1] = max(weights[-1], policy.minimum_cash)
        if weights[-1] > 0.25:
            excess = weights[-1] - 0.25
            weights[-1] = 0.25
            non_cash = self._normalize(weights[:-1])
            weights[:-1] += excess * non_cash
        return self._normalize(weights)

    def _min_variance(self, expected_returns: np.ndarray, covariance: np.ndarray, policy: Policy) -> np.ndarray:
        del expected_returns
        count = covariance.shape[0]
        result = minimize(
            lambda weights: weights @ covariance @ weights,
            np.ones(count) / count,
            bounds=[(0, 0.45)] * count,
            constraints=self._constraints(),
            method="SLSQP",
        )
        return self._normalize(result.x if result.success else np.ones(count) / count)

    def _max_sharpe(self, expected_returns: np.ndarray, covariance: np.ndarray, policy: Policy) -> np.ndarray:
        count = covariance.shape[0]

        def objective(weights: np.ndarray) -> float:
            ret = weights @ expected_returns
            vol = math.sqrt(max(weights @ covariance @ weights, 1e-9))
            return -(ret - 0.025) / vol

        result = minimize(
            objective,
            np.ones(count) / count,
            bounds=[(0, 0.45)] * count,
            constraints=self._constraints(),
            method="SLSQP",
        )
        weights = self._normalize(result.x if result.success else np.ones(count) / count)
        weights[-1] = max(weights[-1], policy.minimum_cash)
        return self._normalize(weights)

    def _drawdown_constrained(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        policy: Policy,
        assumptions: list[AssetAssumption],
    ) -> np.ndarray:
        del covariance
        raw = np.array([0.30, 0.15, 0.15, 0.25, 0.10, 0.05])
        if len(raw) != len(assumptions):
            raw = np.ones(len(assumptions)) / len(assumptions)
        if policy.max_drawdown_tolerance > -0.15:
            raw = np.array([0.20, 0.10, 0.10, 0.35, 0.10, 0.15])
        elif expected_returns.max() > 0.08 and policy.target_volatility[1] >= 0.15:
            raw = np.array([0.35, 0.25, 0.15, 0.15, 0.05, 0.05])
        raw[-1] = max(raw[-1], policy.minimum_cash)
        return self._normalize(raw)

    def _candidate(
        self,
        method: str,
        weights: np.ndarray,
        names: list[str],
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        assumptions: list[AssetAssumption],
    ) -> PortfolioCandidate:
        weights = self._normalize(weights)
        ret = float(weights @ expected_returns)
        vol = float(math.sqrt(max(weights @ covariance @ weights, 0)))
        theme_exposure = float(sum(weight * asset.theme_exposure / 100 for weight, asset in zip(weights, assumptions)))
        raw_drawdown = sum(weight * asset.max_drawdown_estimate for weight, asset in zip(weights, assumptions))
        diversification_factor = 0.62 + 0.10 * theme_exposure
        drawdown = float(raw_drawdown * diversification_factor)
        sharpe = float((ret - 0.025) / max(vol, 0.001))
        return PortfolioCandidate(
            method=method,
            weights={name: float(weight) for name, weight in zip(names, weights)},
            expected_return=ret,
            expected_volatility=vol,
            estimated_max_drawdown=drawdown,
            sharpe_estimate=sharpe,
            theme_exposure=theme_exposure,
        )


class RiskAgent:
    def run(self, policy: Policy, candidates: list[PortfolioCandidate]) -> RiskReview:
        approved = []
        rejected = []
        for candidate in candidates:
            reasons = []
            if candidate.estimated_max_drawdown < policy.max_drawdown_tolerance:
                reasons.append("estimated drawdown breaches tolerance")
            if candidate.theme_exposure > policy.theme_limit:
                reasons.append("theme exposure exceeds limit")
            if candidate.expected_volatility > policy.target_volatility[1] * 1.35:
                reasons.append("volatility materially exceeds target")
            if candidate.weights.get("Cash", 0) < policy.minimum_cash - 1e-6:
                reasons.append("cash buffer below minimum")

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
