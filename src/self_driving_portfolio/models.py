from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


RiskLevel = Literal["conservative", "balanced", "growth"]
LiquidityNeed = Literal["high", "medium", "low"]
DataProvider = Literal["builtin", "spglobal_capital_iq"]


class InvestmentRequest(BaseModel):
    investment_hypothesis: str
    budget: float = Field(gt=0)
    currency: str = "EUR"
    time_horizon_months: int = Field(default=36, ge=1)
    risk_level: RiskLevel = "balanced"
    max_drawdown_tolerance: float = Field(default=-0.20, le=0)
    liquidity_need: LiquidityNeed = "high"
    allowed_assets: list[str] = Field(default_factory=lambda: ["ETFs", "stocks", "bonds", "cash"])
    excluded_assets: list[str] = Field(default_factory=list)
    benchmark: str = "60/40 global equity/bond"
    candidate_assets: list[str] = Field(default_factory=list)
    single_name_limit: float = Field(default=0.10, gt=0, le=1)
    theme_limit: float = Field(default=0.35, gt=0, le=1)
    minimum_cash_buffer: float = Field(default=0.05, ge=0, le=1)
    rebalance_frequency: str = "quarterly"
    use_live_data: bool = False
    data_provider: DataProvider = "builtin"
    universe_limit: int = Field(default=25, ge=1, le=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper().strip()


class Policy(BaseModel):
    portfolio_mode: str
    base_currency: str
    budget: float
    target_volatility: tuple[float, float]
    max_drawdown_tolerance: float
    single_position_limit: float
    theme_limit: float
    minimum_cash: float
    excluded_assets: list[str]
    benchmark: str
    rebalance_frequency: str


class MacroRegime(BaseModel):
    macro_regime: str
    confidence: float
    risk_implications: list[str]
    portfolio_tilts: dict[str, str]


class AssetAssumption(BaseModel):
    ticker: str
    name: str
    asset_class: str
    isin: str | None = None
    wkn: str | None = None
    security_type: str = "ETF"
    exchange: str | None = None
    trading_currency: str | None = None
    yahoo_ticker: str | None = None
    yahoo_url: str | None = None
    execution_note: str | None = None
    theme_exposure: float
    expected_return: float
    expected_volatility: float
    max_drawdown_estimate: float
    liquidity_score: float
    confidence: float
    key_risks: list[str]


class PortfolioCandidate(BaseModel):
    method: str
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    estimated_max_drawdown: float
    sharpe_estimate: float
    theme_exposure: float


class RiskReview(BaseModel):
    approved_portfolios: list[str]
    rejected_portfolios: list[dict[str, str]]
    stress_test_summary: dict[str, float | str]


class AllocationItem(BaseModel):
    asset: str
    weight: float
    amount: float
    ticker: str | None = None
    isin: str | None = None
    wkn: str | None = None
    security_type: str | None = None
    exchange: str | None = None
    trading_currency: str | None = None
    yahoo_ticker: str | None = None
    yahoo_url: str | None = None
    execution_note: str | None = None


class CommitteeResult(BaseModel):
    decision: str
    selected_method: str
    recommended_portfolio: list[AllocationItem]
    expected_return: float
    expected_volatility: float
    max_drawdown_scenario: float
    approved_portfolios: list[str]
    rejected_portfolios: list[dict[str, str]]
    stress_test_summary: dict[str, float | str]
    rationale: list[str]
    pros: list[str]
    cons: list[str]
    final_judgement: str
    risks_to_monitor: list[str]
    invalid_if: list[str]
    rebalance_rule: str
    investment_memo: str
    data_provider_status: dict[str, str | int | bool | None] = Field(default_factory=dict)
    policy: Policy
    macro_regime: MacroRegime
    asset_assumptions: list[AssetAssumption]


class SingleAssetRequest(BaseModel):
    asset: str
    idea_type: str = "stock"
    hypothesis: str
    catalyst: str = ""
    maximum_position_size: float = Field(default=0.05, gt=0, le=1)
    distressed: bool = False


class SingleAssetReview(BaseModel):
    asset: str
    decision: str
    suggested_position_size: str
    thesis_fit: str
    expected_return_range: str
    downside_risk: str
    portfolio_role: str
    required_margin_of_safety: str
    key_risks: list[str]
    invalid_if: list[str]
    watchlist_conditions: list[str]
