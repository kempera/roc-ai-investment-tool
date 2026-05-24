# ROC AI Investment Tool

An MVP implementation of **The Self-Driving Portfolio**: an agentic investment decision-support tool that converts an investment hypothesis, budget, and investor constraints into a concrete portfolio recommendation.

This tool is for research and decision support only. It does not provide guaranteed results or personalized regulated financial advice.

## Live App

The deployed Streamlit app is available at:

https://roc-ai-investment-tool-cjojrb3twn3xknxxmmkehy.streamlit.app/

## What It Does

- Converts investor inputs into an investment policy statement.
- Builds a simple investable universe from the hypothesis and allowed asset classes.
- Estimates risk and return assumptions.
- Generates competing portfolios.
- Applies risk constraints.
- Produces a CIO-style recommendation with weights, EUR amounts, stress tests, invalidation rules, and rebalancing rules.
- Adds execution-ready instrument identifiers including ticker, ISIN, WKN, exchange, trading currency, and Yahoo Finance quote links.
- Evaluates individual investment ideas, including distressed opportunities.
- Exports a Markdown investment memo and structured JSON result.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

If you use the local virtual environment created during setup:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

Run a quick validation:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

On Windows, you can also start the app with:

```powershell
.\scripts\start_app.ps1
```

or double-click:

```text
scripts\start_app.bat
```

## Internet Deployment

The project is prepared for Streamlit Community Cloud deployment from GitHub.

- Entrypoint: `app.py`
- Branch: `main`
- Python: `3.12`
- Dependencies: `requirements.txt`
- GitHub repository: `https://github.com/kempera/roc-ai-investment-tool`
- Streamlit app: `https://roc-ai-investment-tool-cjojrb3twn3xknxxmmkehy.streamlit.app/`

See [DEPLOYMENT.md](DEPLOYMENT.md) for the deployment checklist.

## Project Structure

```text
app.py                         Streamlit UI
src/self_driving_portfolio/    Investment engine and agent modules
scripts/smoke_test.py          Runtime validation check
scripts/start_app.ps1          Windows app launcher
MASTER_PROMPT.md               Optimized master prompt and product blueprint
```

## MVP Design

The app implements six agents:

1. Investment Policy Agent
2. Macro Regime Agent
3. Theme and Asset Return Agent
4. Portfolio Optimizer Agent
5. Risk Agent
6. CIO Decision Agent

The LLM-style reasoning layer is represented as deterministic Python agent classes for the MVP. Future versions can connect these stages to LangGraph or another orchestration framework while preserving the same typed data contracts.
