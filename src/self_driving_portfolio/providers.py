from __future__ import annotations

import base64
import copy
import json
import os
from typing import Any

import requests

from .data import DEFAULT_UNIVERSE
from .models import AssetAssumption, InvestmentRequest


CAPITAL_IQ_BASE_URL = "https://api-ciq.marketintelligence.spglobal.com"
CAPITAL_IQ_TOKEN_PATH = "/gdsapi/rest/authenticate/api/v1/token"
CAPITAL_IQ_CLIENTSERVICE_PATH = "/gdsapi/rest/v3/clientservice.json"
CAPITAL_IQ_DEFAULT_MNEMONICS = [
    "IQ_COMPANY_NAME",
    "IQ_MARKETCAP",
    "IQ_TOTAL_REV",
    "IQ_EBITDA",
]


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

    if config.get("universe_endpoint"):
        return _custom_spglobal_universe(request, config)
    return _capital_iq_api_universe(request, config)


def _custom_spglobal_universe(
    request: InvestmentRequest,
    config: dict[str, str | None],
) -> tuple[list[AssetAssumption], dict[str, str | int | bool | None]]:
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
        if not assets:
            return [], provider_status(
                "S&P Global / Capital IQ",
                True,
                "Provider returned no usable assets.",
            )
        assets = _ensure_cash(assets)
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
            _provider_error_message(exc),
        )


def _capital_iq_api_universe(
    request: InvestmentRequest,
    config: dict[str, str | None],
) -> tuple[list[AssetAssumption], dict[str, str | int | bool | None]]:
    if not (config.get("username") and config.get("password")):
        return [], provider_status(
            "S&P Capital IQ API",
            False,
            "Provider not configured. Missing username/password for S&P Capital IQ token authentication.",
        )

    identifiers = _capital_iq_identifiers(request, config)
    if not identifiers:
        return [], provider_status(
            "S&P Capital IQ API",
            False,
            "Provider not configured. Add Capital IQ identifiers in the candidate list, for example IBM:NYSE or NVDA:NASDAQ.",
        )

    try:
        session = requests.Session()
        token = _capital_iq_access_token(config, session)
        payload = _capital_iq_clientservice_request(config, session, token, identifiers)
        values = _extract_capital_iq_values(payload)
        assets = _capital_iq_assets_from_values(identifiers, values, request)
        assets = [asset for asset in assets if asset is not None]
        if not assets:
            return [], provider_status(
                "S&P Capital IQ API",
                True,
                "Capital IQ returned no usable assets. Check identifiers, mnemonics, and account entitlements.",
            )

        assets = _ensure_cash(assets)
        loaded = len([asset for asset in assets if asset.asset_class != "cash"])
        return assets[: request.universe_limit], provider_status(
            "S&P Capital IQ API",
            True,
            f"Loaded {loaded} candidate securities from Capital IQ Web Service Direct.",
            loaded,
        )
    except Exception as exc:
        return [], provider_status(
            "S&P Capital IQ API",
            True,
            _provider_error_message(exc),
        )


def _spglobal_config() -> dict[str, str | None]:
    base_url = _clean_config_value(os.getenv("SPGLOBAL_BASE_URL")) or CAPITAL_IQ_BASE_URL
    return {
        "base_url": base_url,
        "universe_endpoint": _clean_config_value(os.getenv("SPGLOBAL_UNIVERSE_ENDPOINT")),
        "token_url": _clean_config_value(os.getenv("SPGLOBAL_TOKEN_URL")),
        "capital_iq_token_url": _clean_config_value(os.getenv("SPGLOBAL_TOKEN_URL")) or _join_url(base_url, CAPITAL_IQ_TOKEN_PATH),
        "clientservice_url": _clean_config_value(os.getenv("SPGLOBAL_CLIENTSERVICE_URL"))
        or _join_url(base_url, CAPITAL_IQ_CLIENTSERVICE_PATH),
        "api_key": _clean_config_value(os.getenv("SPGLOBAL_API_KEY")),
        "api_key_header": _clean_config_value(os.getenv("SPGLOBAL_API_KEY_HEADER")),
        "username": _clean_config_value(os.getenv("SPGLOBAL_USERNAME")),
        "password": _clean_config_value(os.getenv("SPGLOBAL_PASSWORD")),
        "ciq_mnemonics": _clean_config_value(os.getenv("SPGLOBAL_CIQ_MNEMONICS")),
        "ciq_identifier_map": _clean_config_value(os.getenv("SPGLOBAL_CIQ_IDENTIFIER_MAP")),
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
        "real-",
        "real/",
        "real_",
        "real.",
        "example",
        "if-you-have-one",
        "placeholder",
        "replace_me",
        "changeme",
        "<",
        ">",
    ]
    if any(marker in lowered for marker in placeholder_markers):
        return None
    return text


def _provider_error_message(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return (
            "Provider request timed out. Check the S&P/Capital IQ endpoint URL, firewall/VPN access, "
            "and increase timeout if the endpoint is slow."
        )

    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        if status_code in {401, 403}:
            return "Provider rejected the request. Check the API key, username/password, token URL, and account entitlements."
        if status_code == 404:
            return "Provider endpoint was not found. Check base_url and universe_endpoint."
        return f"Provider returned HTTP {status_code}. Check the endpoint, request schema, and account permissions."

    if isinstance(exc, requests.exceptions.ConnectionError):
        return (
            "Provider host could not be reached. Replace template values such as REAL_SPGLOBAL_API_HOST "
            "with the real S&P/Capital IQ API host, and verify network/DNS access."
        )

    if isinstance(exc, requests.exceptions.RequestException):
        return "Provider request failed. Check the S&P/Capital IQ API host, endpoint, credentials, and network access."

    if isinstance(exc, ValueError):
        return "Provider returned a response that could not be parsed as JSON. Check the configured endpoint."

    return f"Provider request failed: {type(exc).__name__}."


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


def _capital_iq_access_token(config: dict[str, str | None], session: requests.Session) -> str:
    response = session.post(
        config["capital_iq_token_url"],
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "username": config["username"],
            "password": config["password"],
        },
        timeout=float(config.get("timeout") or 20),
    )
    response.raise_for_status()
    token_payload = response.json()
    token = token_payload.get("access_token")
    if not token:
        raise ValueError("Capital IQ token response did not include access_token.")
    return str(token)


def _capital_iq_clientservice_request(
    config: dict[str, str | None],
    session: requests.Session,
    token: str,
    identifiers: list[str],
) -> dict[str, Any]:
    input_requests = []
    mnemonics = _capital_iq_mnemonics(config)
    for identifier in identifiers:
        for mnemonic in mnemonics:
            input_requests.append(_capital_iq_input_request(identifier, mnemonic))

    response = session.post(
        config["clientservice_url"],
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        data=json.dumps({"inputRequests": input_requests}),
        timeout=float(config.get("timeout") or 20),
    )
    response.raise_for_status()
    return response.json()


def _capital_iq_input_request(identifier: str, mnemonic: str) -> dict[str, Any]:
    request: dict[str, Any] = {
        "function": "GDSP",
        "identifier": identifier,
        "mnemonic": mnemonic,
    }
    if mnemonic in {"IQ_TOTAL_REV", "IQ_EBITDA"}:
        request["properties"] = {"PeriodType": "IQ_FY"}
    return request


def _capital_iq_mnemonics(config: dict[str, str | None]) -> list[str]:
    configured = config.get("ciq_mnemonics")
    if not configured:
        return CAPITAL_IQ_DEFAULT_MNEMONICS
    mnemonics = [item.strip() for item in configured.split(",") if item.strip()]
    return mnemonics or CAPITAL_IQ_DEFAULT_MNEMONICS


def _capital_iq_identifiers(request: InvestmentRequest, config: dict[str, str | None]) -> list[str]:
    identifier_map = _capital_iq_identifier_map(config)
    raw_identifiers = request.candidate_assets or [asset["yahoo_ticker"] or asset["ticker"] for asset in builtin_universe()]
    identifiers = []
    for item in raw_identifiers:
        text = str(item).strip()
        if not text:
            continue
        mapped = identifier_map.get(text) or identifier_map.get(text.upper()) or text
        if mapped.lower() == "cash":
            continue
        identifiers.append(mapped)
    return identifiers[: request.universe_limit]


def _capital_iq_identifier_map(config: dict[str, str | None]) -> dict[str, str]:
    raw = config.get("ciq_identifier_map")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value}


def _extract_capital_iq_values(payload: Any) -> dict[str, dict[str, Any]]:
    responses = []
    if isinstance(payload, dict):
        candidate = payload.get("GDSSDKResponse") or payload.get("GDSSDKResponses") or payload.get("responses")
        if isinstance(candidate, list):
            responses = candidate
    elif isinstance(payload, list):
        responses = payload

    values: dict[str, dict[str, Any]] = {}
    for item in responses:
        if not isinstance(item, dict):
            continue
        identifier = _first(item, "Identifier", "identifier")
        mnemonic = _first(item, "Mnemonic", "mnemonic")
        if not identifier or not mnemonic:
            continue
        err_msg = _first(item, "ErrMsg", "errMsg", "error")
        if err_msg:
            continue
        value = _capital_iq_response_value(item)
        if value in (None, ""):
            continue
        values.setdefault(identifier, {})[mnemonic] = value
    return values


def _capital_iq_response_value(item: dict[str, Any]) -> Any:
    for key in ["Value", "value", "Data", "data"]:
        if item.get(key) not in (None, ""):
            return item[key]

    rows = item.get("Rows") or item.get("rows")
    if not isinstance(rows, list) or not rows:
        return None

    first_row = rows[0]
    if isinstance(first_row, dict):
        row = first_row.get("Row") or first_row.get("row")
        if isinstance(row, list) and row:
            return row[0]
        if row not in (None, ""):
            return row
    if isinstance(first_row, list) and first_row:
        return first_row[0]
    return None


def _capital_iq_assets_from_values(
    identifiers: list[str],
    values: dict[str, dict[str, Any]],
    request: InvestmentRequest,
) -> list[AssetAssumption]:
    assets = []
    for identifier in identifiers:
        record = values.get(identifier) or values.get(identifier.upper()) or {}
        base_asset = _default_asset_for_identifier(identifier)
        if not record and base_asset is None:
            continue
        assets.append(_capital_iq_asset_from_record(identifier, record, request, base_asset))
    return assets


def _capital_iq_asset_from_record(
    identifier: str,
    record: dict[str, Any],
    request: InvestmentRequest,
    base_asset: dict[str, Any] | None,
) -> AssetAssumption:
    ticker, exchange = _split_capital_iq_identifier(identifier)
    name = str(record.get("IQ_COMPANY_NAME") or (base_asset or {}).get("name") or identifier)
    market_cap = _safe_float(record.get("IQ_MARKETCAP"))
    revenue = _safe_float(record.get("IQ_TOTAL_REV"))
    ebitda = _safe_float(record.get("IQ_EBITDA"))

    if base_asset:
        payload = copy.deepcopy(base_asset)
        payload["execution_note"] = _execution_note_with_ciq(payload.get("execution_note"), market_cap, revenue, ebitda)
        payload["confidence"] = min(0.90, float(payload.get("confidence", 0.60)) + _capital_iq_confidence_bonus(record))
        return AssetAssumption(**payload)

    liquidity = _liquidity_from_market_cap(market_cap)
    theme_exposure = _theme_exposure_from_text(request.investment_hypothesis, name, identifier)
    yahoo_ticker = ticker if exchange else identifier
    return AssetAssumption(
        ticker=ticker,
        name=name,
        asset_class="equity_etf" if "etf" in name.lower() else "equity",
        isin=None,
        wkn=None,
        security_type="stock",
        exchange=exchange,
        trading_currency=request.currency,
        yahoo_ticker=yahoo_ticker,
        yahoo_url=f"https://finance.yahoo.com/quote/{yahoo_ticker}",
        execution_note=_execution_note_with_ciq(
            "Loaded from S&P Capital IQ API; verify broker identifier before execution.",
            market_cap,
            revenue,
            ebitda,
        ),
        theme_exposure=theme_exposure,
        expected_return=0.055 + min(theme_exposure / 100, 0.80) * 0.035,
        expected_volatility=0.18 if liquidity >= 75 else 0.26,
        max_drawdown_estimate=-0.35 if liquidity >= 75 else -0.50,
        liquidity_score=liquidity,
        confidence=0.50 + _capital_iq_confidence_bonus(record),
        key_risks=["valuation", "earnings revisions", "Capital IQ entitlement/data coverage"],
    )


def _default_asset_for_identifier(identifier: str) -> dict[str, Any] | None:
    identifier_upper = identifier.upper()
    ticker, _ = _split_capital_iq_identifier(identifier_upper)
    for asset in builtin_universe():
        aliases = {
            str(asset.get("ticker") or "").upper(),
            str(asset.get("yahoo_ticker") or "").upper(),
            str(asset.get("isin") or "").upper(),
            str(asset.get("wkn") or "").upper(),
        }
        if identifier_upper in aliases or ticker in aliases:
            return asset
    return None


def _split_capital_iq_identifier(identifier: str) -> tuple[str, str | None]:
    if ":" not in identifier:
        return identifier, None
    ticker, exchange = identifier.split(":", 1)
    return ticker, exchange or None


def _execution_note_with_ciq(note: str | None, market_cap: float | None, revenue: float | None, ebitda: float | None) -> str:
    parts = [note] if note else []
    metrics = []
    if market_cap is not None:
        metrics.append(f"market cap {market_cap:,.0f}")
    if revenue is not None:
        metrics.append(f"revenue {revenue:,.0f}")
    if ebitda is not None:
        metrics.append(f"EBITDA {ebitda:,.0f}")
    if metrics:
        parts.append("Capital IQ metrics: " + ", ".join(metrics) + ".")
    else:
        parts.append("Capital IQ record loaded; verify identifiers and latest data before order entry.")
    return " ".join(parts)


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _liquidity_from_market_cap(market_cap: float | None) -> float:
    if market_cap is None:
        return 65
    if market_cap >= 200_000_000_000:
        return 95
    if market_cap >= 50_000_000_000:
        return 88
    if market_cap >= 10_000_000_000:
        return 78
    if market_cap >= 2_000_000_000:
        return 65
    return 45


def _theme_exposure_from_text(hypothesis: str, name: str, identifier: str) -> float:
    text = f"{hypothesis} {name} {identifier}".lower()
    score = 25
    for keyword in ["ai", "artificial intelligence", "semiconductor", "chip", "data center", "cloud", "infrastructure"]:
        if keyword in text:
            score += 12
    return float(min(score, 95))


def _capital_iq_confidence_bonus(record: dict[str, Any]) -> float:
    populated = sum(1 for key in CAPITAL_IQ_DEFAULT_MNEMONICS if record.get(key) not in (None, ""))
    return min(0.25, populated * 0.05)


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
