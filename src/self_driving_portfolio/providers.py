from __future__ import annotations

import base64
import copy
import os
from typing import Any

import requests

from .data import DEFAULT_UNIVERSE
from .models import AssetAssumption, InvestmentRequest


def builtin_universe() -> list[dict[str, Any]]:
    return [copy.deepcopy(asset) for asset in DEFAULT_UNIVERSE.values()]


def provider_status(provider: str, configured: bool, message: str, count: int = 0) -> dict[str, str | int | bool | None]:
    return {
        "provider": provider,
        "configured": configured,
        "message": message,
        "asset_count": count,
    }


def get_research_universe(request: InvestmentRequest) -> tuple[list[AssetAssumption], dict[str, str | int | bool | None]]:
    if request.data_provider == "spglobal_capital_iq":
        assets, status = _spglobal_capital_iq_universe(request)
        if assets:
            return assets, status
        fallback_assets = [AssetAssumption(**asset) for asset in builtin_universe()]
        status["fallback"] = True
        status["fallback_message"] = "Using built-in universe because S&P/Capital IQ data was unavailable."
        return fallback_assets, status

    assets = [AssetAssumption(**asset) for asset in builtin_universe()]
    return assets, provider_status("Built-in universe", True, "Using built-in UCITS/EUR universe.", len(assets))


def _spglobal_capital_iq_universe(
    request: InvestmentRequest,
) -> tuple[list[AssetAssumption], dict[str, str | int | bool | None]]:
    config = _spglobal_config()
    missing = [key for key in ["base_url", "universe_endpoint"] if not config.get(key)]
    has_auth = bool(config.get("api_key") or (config.get("username") and config.get("password")))
    if missing or not has_auth:
        missing_text = ", ".join(missing + ([] if has_auth else ["api_key or username/password"]))
        return [], provider_status(
            "S&P Global / Capital IQ",
            False,
            f"Provider not configured. Missing: {missing_text}.",
        )

    try:
        headers = _spglobal_headers(config)
        url = _join_url(config["base_url"], config["universe_endpoint"])
        response = requests.get(
            url,
            headers=headers,
            params={
                "q": request.investment_hypothesis,
                "currency": request.currency,
                "allowed_assets": ",".join(request.allowed_assets),
                "candidates": ",".join(request.candidate_assets),
                "limit": request.universe_limit,
            },
            timeout=float(config.get("timeout") or 20),
        )
        response.raise_for_status()
        payload = response.json()
        records = _extract_records(payload)
        assets = [_asset_from_spglobal_record(record) for record in records]
        assets = [asset for asset in assets if asset is not None]
        assets = _ensure_cash(assets)
        if not assets:
            return [], provider_status(
                "S&P Global / Capital IQ",
                True,
                "Provider returned no usable assets.",
            )
        return assets[: request.universe_limit], provider_status(
            "S&P Global / Capital IQ",
            True,
            "Universe loaded from configured S&P/Capital IQ endpoint.",
            len(assets),
        )
    except Exception as exc:
        return [], provider_status(
            "S&P Global / Capital IQ",
            True,
            f"Provider request failed: {type(exc).__name__}: {exc}",
        )


def _spglobal_config() -> dict[str, str | None]:
    return {
        "base_url": _clean_config_value(os.getenv("SPGLOBAL_BASE_URL")),
        "universe_endpoint": _clean_config_value(os.getenv("SPGLOBAL_UNIVERSE_ENDPOINT")),
        "token_url": _clean_config_value(os.getenv("SPGLOBAL_TOKEN_URL")),
        "api_key": _clean_config_value(os.getenv("SPGLOBAL_API_KEY")),
        "api_key_header": _clean_config_value(os.getenv("SPGLOBAL_API_KEY_HEADER")),
        "username": _clean_config_value(os.getenv("SPGLOBAL_USERNAME")),
        "password": _clean_config_value(os.getenv("SPGLOBAL_PASSWORD")),
        "timeout": _clean_config_value(os.getenv("SPGLOBAL_TIMEOUT")) or "20",
    }


def _clean_config_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    lowered = text.lower()
    placeholder_markers = [
        "your-",
        "your/",
        "your_",
        "your.",
        "example",
        "if-you-have-one",
        "replace_me",
        "changeme",
        "<",
        ">",
    ]
    if any(marker in lowered for marker in placeholder_markers):
        return None
    return text


def _spglobal_headers(config: dict[str, str | None]) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if config.get("api_key"):
        api_key_header = config.get("api_key_header")
        if api_key_header:
            headers[api_key_header] = config["api_key"]
        else:
            headers["Authorization"] = f"Bearer {config['api_key']}"
        return headers

    if config.get("token_url"):
        token_response = requests.post(
            config["token_url"],
            data={
                "grant_type": "password",
                "username": config["username"],
                "password": config["password"],
            },
            timeout=float(config.get("timeout") or 20),
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        token = token_payload.get("access_token") or token_payload.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            return headers

    if config.get("username") and config.get("password"):
        raw = f"{config['username']}:{config['password']}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
        return headers

    return headers


def _join_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["data", "results", "items", "securities", "assets", "records"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _asset_from_spglobal_record(record: dict[str, Any]) -> AssetAssumption | None:
    name = _first(record, "name", "companyName", "securityName", "instrumentName")
    ticker = _first(record, "ticker", "symbol", "tradingSymbol", "localTicker")
    if not name or not ticker:
        return None

    yahoo_ticker = _first(record, "yahooTicker", "yahoo_ticker")
    isin = _first(record, "isin", "ISIN")
    asset_class = _normalize_asset_class(_first(record, "assetClass", "asset_class", "type"))
    expected_return = _float(record, ["expectedReturn", "expected_return", "return"], 0.06)
    expected_volatility = _float(record, ["expectedVolatility", "expected_volatility", "volatility"], 0.18)
    drawdown = _float(record, ["maxDrawdown", "max_drawdown", "drawdown"], -0.30)

    return AssetAssumption(
        ticker=str(ticker),
        name=str(name),
        asset_class=asset_class,
        isin=str(isin) if isin else None,
        wkn=_first(record, "wkn", "WKN"),
        security_type=_first(record, "securityType", "security_type", "type") or "security",
        exchange=_first(record, "exchange", "primaryExchange", "tradingVenue"),
        trading_currency=_first(record, "currency", "tradingCurrency") or "EUR",
        yahoo_ticker=yahoo_ticker,
        yahoo_url=f"https://finance.yahoo.com/quote/{yahoo_ticker}" if yahoo_ticker else None,
        execution_note=_first(record, "executionNote", "note", "brokerNote"),
        theme_exposure=_float(record, ["themeExposure", "theme_exposure"], 50),
        expected_return=expected_return,
        expected_volatility=expected_volatility,
        max_drawdown_estimate=min(drawdown, 0),
        liquidity_score=_float(record, ["liquidityScore", "liquidity_score"], 70),
        confidence=_float(record, ["confidence", "modelConfidence"], 0.55),
        key_risks=_list(record, "keyRisks", "key_risks", "risks"),
    )


def _ensure_cash(assets: list[AssetAssumption]) -> list[AssetAssumption]:
    if any(asset.asset_class == "cash" or asset.name.lower() == "cash" for asset in assets):
        return assets
    return assets + [AssetAssumption(**copy.deepcopy(DEFAULT_UNIVERSE["cash"]))]


def _first(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _float(record: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _list(record: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = record.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str) and value:
            return [part.strip() for part in value.split(";") if part.strip()]
    return ["data quality", "valuation", "liquidity"]


def _normalize_asset_class(value: str | None) -> str:
    text = (value or "").lower()
    if "bond" in text:
        return "bond_etf"
    if "cash" in text or "money" in text:
        return "cash"
    if "commodity" in text or "gold" in text or "etc" in text:
        return "commodity"
    return "equity_etf"
