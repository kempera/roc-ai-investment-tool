from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.self_driving_portfolio.engine import run_committee, run_single_asset_review
from src.self_driving_portfolio.models import InvestmentRequest, SingleAssetRequest
from src.self_driving_portfolio.providers import (
    _capital_iq_assets_from_values,
    _extract_capital_iq_values,
    check_capital_iq_api,
)


SPGLOBAL_ENV_KEYS = [
    "SPGLOBAL_BASE_URL",
    "SPGLOBAL_UNIVERSE_ENDPOINT",
    "SPGLOBAL_TOKEN_URL",
    "SPGLOBAL_API_KEY",
    "SPGLOBAL_API_KEY_HEADER",
    "SPGLOBAL_USERNAME",
    "SPGLOBAL_PASSWORD",
    "SPGLOBAL_CLIENTSERVICE_URL",
    "SPGLOBAL_CIQ_MNEMONICS",
    "SPGLOBAL_CIQ_IDENTIFIER_MAP",
    "SPGLOBAL_TIMEOUT",
]


def restore_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def main() -> None:
    portfolio = run_committee(
        InvestmentRequest(
            investment_hypothesis="AI infrastructure will outperform over 3 years",
            budget=100000,
            currency="EUR",
            risk_level="balanced",
            max_drawdown_tolerance=-0.20,
        )
    )
    assert portfolio.recommended_portfolio
    assert round(sum(item.weight for item in portfolio.recommended_portfolio), 4) == 1
    assert portfolio.max_drawdown_scenario >= -0.20
    assert portfolio.investment_memo.startswith("# Self-Driving Portfolio Investment Memo")
    assert portfolio.selected_method == "committee_blend"
    assert portfolio.data_provider_status["provider"] == "Built-in universe"
    weights_by_ticker = {item.ticker: item.weight for item in portfolio.recommended_portfolio}
    assert weights_by_ticker["EUNL"] > 0.10
    assert weights_by_ticker["VVSM"] > 0.05
    assert weights_by_ticker["EUNA"] > 0.10
    assert weights_by_ticker["Cash"] >= 0.05
    assert len({round(weight, 3) for weight in weights_by_ticker.values()}) > 3
    assert max(weights_by_ticker.values()) - min(weights_by_ticker.values()) > 0.05
    assert any(item["method"] == "equal_weight_benchmark" for item in portfolio.candidate_diagnostics)
    assert portfolio.candidate_diagnostics[0]["method"] == "committee_blend"
    assert portfolio.allocation_check["weights_match_selected_method"] is True
    assert portfolio.allocation_check["amount_sum_ok"] is True
    assert portfolio.allocation_check["drawdown_within_tolerance"] is True
    assert portfolio.allocation_check["volatility_within_target"] is True
    assert portfolio.risk_return_assessment
    assert "## Allocation Check" in portfolio.investment_memo
    assert "## Risk And Return Evaluation" in portfolio.investment_memo
    assert portfolio.pros
    assert portfolio.cons
    assert portfolio.final_judgement
    assert "## Critical Review" in portfolio.investment_memo
    assert "### Final Judgement" in portfolio.investment_memo
    assert all(item.isin or item.asset == "Cash" for item in portfolio.recommended_portfolio)
    assert any(item.yahoo_url and "finance.yahoo.com" in item.yahoo_url for item in portfolio.recommended_portfolio)

    saved_env = {key: os.getenv(key) for key in SPGLOBAL_ENV_KEYS}
    try:
        for key in SPGLOBAL_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["SPGLOBAL_BASE_URL"] = "https://REAL_SPGLOBAL_API_HOST"
        os.environ["SPGLOBAL_UNIVERSE_ENDPOINT"] = "/REAL_UNIVERSE_SEARCH_ENDPOINT"
        os.environ["SPGLOBAL_TOKEN_URL"] = "https://your-token-endpoint-if-you-have-one"
        os.environ["SPGLOBAL_USERNAME"] = "YOUR_USERNAME"
        os.environ["SPGLOBAL_PASSWORD"] = "YOUR_PASSWORD"

        enterprise_fallback = run_committee(
            InvestmentRequest(
                investment_hypothesis="AI infrastructure will outperform over 3 years",
                budget=100000,
                data_provider="spglobal_capital_iq",
            )
        )
        capital_iq_check = check_capital_iq_api(["IBM:NYSE"])
    finally:
        restore_env(saved_env)

    assert enterprise_fallback.recommended_portfolio
    assert enterprise_fallback.data_provider_status["provider"] == "S&P Capital IQ API"
    assert enterprise_fallback.data_provider_status.get("fallback") is True
    assert "your-token-endpoint" not in enterprise_fallback.data_provider_status["message"]
    assert "REAL_SPGLOBAL_API_HOST" not in enterprise_fallback.data_provider_status["message"]
    assert capital_iq_check["ok"] is False
    assert capital_iq_check["auth_ok"] is False

    capital_iq_payload = {
        "GDSSDKResponse": [
            {
                "Identifier": "NVDA:NASDAQ",
                "Mnemonic": "IQ_COMPANY_NAME",
                "Rows": [{"Row": ["NVIDIA Corporation"]}],
                "ErrMsg": "",
            },
            {
                "Identifier": "NVDA:NASDAQ",
                "Mnemonic": "IQ_MARKETCAP",
                "Rows": [{"Row": ["3000000000000"]}],
                "ErrMsg": "",
            },
            {
                "Identifier": "NVDA:NASDAQ",
                "Mnemonic": "IQ_TOTAL_REV",
                "Rows": [{"Row": ["60922000000"]}],
                "ErrMsg": "",
            },
        ]
    }
    capital_iq_values = _extract_capital_iq_values(capital_iq_payload)
    capital_iq_assets = _capital_iq_assets_from_values(
        ["NVDA:NASDAQ"],
        capital_iq_values,
        InvestmentRequest(
            investment_hypothesis="AI infrastructure will outperform",
            budget=100000,
            candidate_assets=["NVDA:NASDAQ"],
        ),
    )
    assert capital_iq_assets[0].name == "NVIDIA Corporation"
    assert capital_iq_assets[0].exchange == "NASDAQ"
    assert capital_iq_assets[0].liquidity_score >= 90

    single = run_single_asset_review(
        SingleAssetRequest(
            asset="NVDA",
            idea_type="stock",
            hypothesis="AI data center demand can support above-market earnings growth.",
            catalyst="earnings revisions",
        )
    )
    assert single.decision

    distressed = run_single_asset_review(
        SingleAssetRequest(
            asset="Example Distressed Bond",
            idea_type="distressed",
            hypothesis="Forced selling creates a mispriced recovery opportunity.",
            catalyst="refinancing or asset sale",
            distressed=True,
        )
    )
    assert distressed.decision in {"watchlist", "avoid"}

    print("Smoke tests passed.")
    print(portfolio.decision)


if __name__ == "__main__":
    main()
