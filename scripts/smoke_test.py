from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.self_driving_portfolio.engine import run_committee, run_single_asset_review
from src.self_driving_portfolio.models import InvestmentRequest, SingleAssetRequest


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
    assert portfolio.selected_method == "drawdown_constrained"
    assert all(item.isin or item.asset == "Cash" for item in portfolio.recommended_portfolio)
    assert any(item.yahoo_url and "finance.yahoo.com" in item.yahoo_url for item in portfolio.recommended_portfolio)

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
