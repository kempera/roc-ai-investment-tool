from __future__ import annotations

import math

import numpy as np
import pandas as pd


DEFAULT_UNIVERSE = {
    "global_equity": {
        "ticker": "IWDA.AS",
        "name": "Global Equity ETF",
        "asset_class": "equity_etf",
        "theme_exposure": 30,
        "expected_return": 0.065,
        "expected_volatility": 0.16,
        "max_drawdown_estimate": -0.35,
        "liquidity_score": 92,
        "confidence": 0.72,
        "key_risks": ["global equity bear market", "currency exposure"],
    },
    "ai_semiconductor": {
        "ticker": "SMH",
        "name": "AI / Semiconductor ETF",
        "asset_class": "equity_etf",
        "theme_exposure": 95,
        "expected_return": 0.10,
        "expected_volatility": 0.25,
        "max_drawdown_estimate": -0.45,
        "liquidity_score": 95,
        "confidence": 0.64,
        "key_risks": ["valuation compression", "semiconductor cycle", "AI capex reset"],
    },
    "infrastructure": {
        "ticker": "GRID",
        "name": "Infrastructure ETF",
        "asset_class": "equity_etf",
        "theme_exposure": 70,
        "expected_return": 0.075,
        "expected_volatility": 0.18,
        "max_drawdown_estimate": -0.30,
        "liquidity_score": 80,
        "confidence": 0.62,
        "key_risks": ["rate sensitivity", "project execution risk"],
    },
    "global_bonds": {
        "ticker": "AGGH",
        "name": "Global Bond ETF",
        "asset_class": "bond_etf",
        "theme_exposure": 0,
        "expected_return": 0.035,
        "expected_volatility": 0.07,
        "max_drawdown_estimate": -0.14,
        "liquidity_score": 86,
        "confidence": 0.70,
        "key_risks": ["duration risk", "credit spread widening"],
    },
    "gold": {
        "ticker": "IGLN",
        "name": "Gold ETC",
        "asset_class": "commodity",
        "theme_exposure": 0,
        "expected_return": 0.04,
        "expected_volatility": 0.16,
        "max_drawdown_estimate": -0.25,
        "liquidity_score": 84,
        "confidence": 0.58,
        "key_risks": ["real yield increase", "US dollar moves"],
    },
    "cash": {
        "ticker": "Cash",
        "name": "Cash",
        "asset_class": "cash",
        "theme_exposure": 0,
        "expected_return": 0.025,
        "expected_volatility": 0.005,
        "max_drawdown_estimate": 0.0,
        "liquidity_score": 100,
        "confidence": 0.95,
        "key_risks": ["inflation drag", "opportunity cost"],
    },
}


def maybe_get_live_returns(tickers: list[str]) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except Exception:
        return None

    usable = [ticker for ticker in tickers if ticker.lower() != "cash"]
    if not usable:
        return None

    try:
        prices = yf.download(usable, period="5y", auto_adjust=True, progress=False)["Close"]
    except Exception:
        return None

    if isinstance(prices, pd.Series):
        prices = prices.to_frame(usable[0])

    returns = prices.pct_change().dropna(how="all")
    if returns.empty or returns.shape[0] < 120:
        return None

    if "Cash" in tickers:
        daily_cash = (1 + 0.025) ** (1 / 252) - 1
        returns["Cash"] = daily_cash

    return returns.dropna(axis=1, how="all")


def estimate_from_returns(returns: pd.DataFrame) -> dict[str, dict[str, float]]:
    estimates: dict[str, dict[str, float]] = {}
    for ticker in returns.columns:
        series = returns[ticker].dropna()
        if series.empty:
            continue
        cumulative = (1 + series).cumprod()
        drawdown = cumulative / cumulative.cummax() - 1
        estimates[ticker] = {
            "expected_return": float(series.mean() * 252),
            "expected_volatility": float(series.std() * math.sqrt(252)),
            "max_drawdown_estimate": float(drawdown.min()),
        }
    return estimates


def correlation_matrix(asset_count: int) -> np.ndarray:
    matrix = np.full((asset_count, asset_count), 0.35)
    np.fill_diagonal(matrix, 1.0)
    return matrix
