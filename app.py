from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

from src.self_driving_portfolio.engine import run_committee, run_single_asset_review
from src.self_driving_portfolio.models import InvestmentRequest, SingleAssetRequest
from src.self_driving_portfolio.reports import render_single_asset_memo


st.set_page_config(
    page_title="Self-Driving Portfolio",
    layout="wide",
)


def as_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def json_bytes(payload) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


def configure_spglobal_from_streamlit_secrets() -> None:
    try:
        secrets = st.secrets.get("spglobal", {})
    except Exception:
        secrets = {}

    mapping = {
        "SPGLOBAL_BASE_URL": "base_url",
        "SPGLOBAL_UNIVERSE_ENDPOINT": "universe_endpoint",
        "SPGLOBAL_TOKEN_URL": "token_url",
        "SPGLOBAL_API_KEY": "api_key",
        "SPGLOBAL_API_KEY_HEADER": "api_key_header",
        "SPGLOBAL_USERNAME": "username",
        "SPGLOBAL_PASSWORD": "password",
        "SPGLOBAL_TIMEOUT": "timeout",
    }
    for env_key, secret_key in mapping.items():
        value = secrets.get(secret_key) if hasattr(secrets, "get") else None
        if value:
            os.environ[env_key] = str(value)


def spglobal_is_configured() -> bool:
    has_endpoint = bool(os.getenv("SPGLOBAL_BASE_URL") and os.getenv("SPGLOBAL_UNIVERSE_ENDPOINT"))
    has_auth = bool(os.getenv("SPGLOBAL_API_KEY") or (os.getenv("SPGLOBAL_USERNAME") and os.getenv("SPGLOBAL_PASSWORD")))
    return has_endpoint and has_auth


configure_spglobal_from_streamlit_secrets()


st.title("The Self-Driving Portfolio")
st.caption("Agentic investment committee for portfolio construction and single-idea evaluation.")

tab_portfolio, tab_single = st.tabs(["Portfolio Committee", "Single Idea Review"])

with tab_portfolio:
    left, right = st.columns([0.58, 0.42])

    with left:
        hypothesis = st.text_area(
            "Investment hypothesis",
            value="AI infrastructure will outperform over 3 years",
            height=100,
        )

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            budget = st.number_input("Budget", min_value=1000, value=100000, step=5000)
        with col_b:
            currency = st.selectbox("Currency", ["EUR", "USD", "CHF", "GBP"], index=0)
        with col_c:
            horizon = st.slider("Time horizon, months", 6, 120, 36, step=6)

        col_d, col_e, col_f = st.columns(3)
        with col_d:
            risk_level = st.selectbox("Risk level", ["conservative", "balanced", "growth"], index=1)
        with col_e:
            max_drawdown = st.slider("Max drawdown tolerance", -60, -5, -20, step=5) / 100
        with col_f:
            liquidity_need = st.selectbox("Liquidity need", ["high", "medium", "low"], index=0)

        allowed_assets = st.multiselect(
            "Allowed assets",
            ["ETFs", "stocks", "bonds", "cash", "gold", "commodities"],
            default=["ETFs", "stocks", "bonds", "cash", "gold"],
        )
        excluded_assets = st.multiselect(
            "Excluded assets",
            ["leverage", "crypto", "illiquid private assets", "options", "short selling"],
            default=["leverage", "crypto", "illiquid private assets"],
        )
        benchmark = st.text_input("Benchmark", value="60/40 global equity/bond")

        candidate_text = st.text_area(
            "Optional candidate tickers or asset labels, comma separated",
            value="EUNL.DE, VVSM.DE, GRID.DE, EUNA.DE, PPFB.DE, Cash",
        )

    with right:
        st.subheader("Research Data")
        data_provider_label = st.selectbox(
            "Financial universe source",
            [
                "Built-in UCITS universe",
                "S&P Global / Capital IQ beta",
            ],
        )
        data_provider = "spglobal_capital_iq" if data_provider_label.startswith("S&P") else "builtin"
        universe_limit = st.slider("Universe candidate limit", 5, 100, 25, step=5)

        if data_provider == "spglobal_capital_iq":
            if spglobal_is_configured():
                st.success("S&P Global / Capital IQ provider is configured through secrets.")
            else:
                st.warning(
                    "S&P Global / Capital IQ is selected but not configured. The app will fall back to "
                    "the built-in universe until Streamlit secrets are added."
                )
                with st.expander("Required secrets"):
                    st.code(
                        """[spglobal]
base_url = "https://your-spglobal-api-host.example"
universe_endpoint = "/your/universe/search/endpoint"
api_key = ""
api_key_header = ""
token_url = ""
username = ""
password = ""
timeout = "20"
""",
                        language="toml",
                    )

        st.subheader("Risk Policy")
        single_name_limit = st.slider("Single-position limit", 2, 25, 10, step=1) / 100
        theme_limit = st.slider("Theme exposure limit", 10, 70, 35, step=5) / 100
        minimum_cash = st.slider("Minimum cash", 0, 25, 5, step=1) / 100
        rebalance_frequency = st.selectbox("Rebalance frequency", ["monthly", "quarterly", "semiannual"], index=1)
        use_live_data = st.toggle("Try live Yahoo Finance data", value=False)

        st.info(
            "Live data is optional. If unavailable, the MVP uses conservative built-in assumptions "
            "so the investment committee can still run."
        )

    if st.button("Run Investment Committee", type="primary"):
        candidate_assets = [item.strip() for item in candidate_text.split(",") if item.strip()]
        request = InvestmentRequest(
            investment_hypothesis=hypothesis,
            budget=float(budget),
            currency=currency,
            time_horizon_months=int(horizon),
            risk_level=risk_level,
            max_drawdown_tolerance=float(max_drawdown),
            liquidity_need=liquidity_need,
            allowed_assets=allowed_assets,
            excluded_assets=excluded_assets,
            benchmark=benchmark,
            candidate_assets=candidate_assets,
            single_name_limit=single_name_limit,
            theme_limit=theme_limit,
            minimum_cash_buffer=minimum_cash,
            rebalance_frequency=rebalance_frequency,
            use_live_data=use_live_data,
            data_provider=data_provider,
            universe_limit=universe_limit,
        )

        result = run_committee(request)

        st.subheader("Executive Decision")
        st.success(result.decision)
        provider_status = result.data_provider_status
        provider_message = provider_status.get("message", "No provider status available.")
        if provider_status.get("configured") and not provider_status.get("fallback"):
            st.info(f"Data provider: {provider_status.get('provider')} - {provider_message}")
        else:
            st.warning(f"Data provider: {provider_status.get('provider')} - {provider_message}")

        metrics = st.columns(4)
        metrics[0].metric("Expected Return", as_percent(result.expected_return))
        metrics[1].metric("Expected Volatility", as_percent(result.expected_volatility))
        metrics[2].metric("Bear Drawdown", as_percent(result.max_drawdown_scenario))
        metrics[3].metric("Approved Portfolios", str(len(result.approved_portfolios)))

        allocation = pd.DataFrame([item.model_dump() for item in result.recommended_portfolio])
        st.subheader("Recommended Allocation")
        allocation_display = allocation[["asset", "weight", "amount"]].copy()
        allocation_display["weight"] = allocation_display["weight"].map(as_percent)
        allocation_display["amount"] = allocation_display["amount"].map(lambda value: f"{value:,.2f} {currency}")
        st.dataframe(allocation_display, use_container_width=True, hide_index=True)

        st.bar_chart(allocation.set_index("asset")["weight"] * 100)

        st.subheader("Execution Details")
        execution_columns = [
            "asset",
            "ticker",
            "isin",
            "wkn",
            "security_type",
            "exchange",
            "trading_currency",
            "amount",
            "yahoo_url",
            "execution_note",
        ]
        execution_display = allocation[execution_columns].copy()
        execution_display["amount"] = execution_display["amount"].map(lambda value: f"{value:,.2f} {currency}")
        st.dataframe(
            execution_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "asset": "Instrument",
                "ticker": "Ticker",
                "isin": "ISIN",
                "wkn": "WKN",
                "security_type": "Type",
                "exchange": "Exchange",
                "trading_currency": "Trading Currency",
                "amount": "Target Amount",
                "yahoo_url": st.column_config.LinkColumn("Yahoo Finance"),
                "execution_note": "Broker Note",
            },
        )

        st.caption(
            "Use the ISIN/WKN in your broker search and verify the final quote, spread, tax treatment, "
            "and order venue before execution."
        )

        col_1, col_2 = st.columns(2)
        with col_1:
            st.subheader("Macro Regime")
            st.write(f"**{result.macro_regime.macro_regime}** ({as_percent(result.macro_regime.confidence)} confidence)")

            st.subheader("Rationale")
            for item in result.rationale:
                st.write(f"- {item}")

            st.subheader("Risks To Monitor")
            for item in result.risks_to_monitor:
                st.write(f"- {item}")

        with col_2:
            st.subheader("Invalidation Rules")
            for item in result.invalid_if:
                st.write(f"- {item}")

            st.subheader("Rebalancing")
            st.write(result.rebalance_rule)

        st.subheader("Investment Memo")
        st.markdown(result.investment_memo)

        download_col_1, download_col_2 = st.columns(2)
        with download_col_1:
            st.download_button(
                "Download memo",
                data=result.investment_memo,
                file_name="self_driving_portfolio_memo.md",
                mime="text/markdown",
            )
        with download_col_2:
            st.download_button(
                "Download JSON",
                data=json_bytes(json.loads(result.model_dump_json())),
                file_name="self_driving_portfolio_result.json",
                mime="application/json",
            )

        with st.expander("Committee JSON"):
            st.json(json.loads(result.model_dump_json()))

with tab_single:
    st.subheader("Single Investment Idea")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ticker = st.text_input("Ticker or asset", value="NVDA")
    with col_b:
        idea_type = st.selectbox("Idea type", ["stock", "ETF", "bond", "distressed", "special situation"])
    with col_c:
        max_position = st.slider("Max position size", 1, 20, 5, step=1) / 100

    idea_hypothesis = st.text_area(
        "Investment thesis",
        value="AI data-center demand can continue to support above-market earnings growth.",
        height=100,
    )
    catalyst = st.text_input("Expected catalyst", value="Earnings revisions and sustained AI capex")
    distressed = st.checkbox("Evaluate as distressed opportunity")

    if st.button("Review Investment Idea", type="primary"):
        single_request = SingleAssetRequest(
            asset=ticker,
            idea_type=idea_type,
            hypothesis=idea_hypothesis,
            catalyst=catalyst,
            maximum_position_size=max_position,
            distressed=distressed,
        )
        review = run_single_asset_review(single_request)
        memo = render_single_asset_memo(review)
        st.subheader("Decision")
        st.success(review.decision)

        c1, c2, c3 = st.columns(3)
        c1.metric("Suggested Position", review.suggested_position_size)
        c2.metric("Thesis Fit", review.thesis_fit)
        c3.metric("Downside Risk", review.downside_risk)

        st.subheader("Review")
        for key, value in review.model_dump().items():
            if isinstance(value, list):
                st.write(f"**{key.replace('_', ' ').title()}**")
                for item in value:
                    st.write(f"- {item}")
            else:
                st.write(f"**{key.replace('_', ' ').title()}:** {value}")

        st.subheader("Investment Memo")
        st.markdown(memo)
        st.download_button(
            "Download review memo",
            data=memo,
            file_name=f"{review.asset.lower()}_investment_review.md",
            mime="text/markdown",
        )
