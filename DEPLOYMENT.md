# Streamlit Community Cloud Deployment

This project is ready for Streamlit Community Cloud.

## Live Deployment

- GitHub: https://github.com/kempera/roc-ai-investment-tool
- Streamlit: https://roc-ai-investment-tool-cjojrb3twn3xknxxmmkehy.streamlit.app/

## Repository Layout

Streamlit Community Cloud runs the app from the repository root. Use:

- Repository: your GitHub repository for this project
- Branch: `main`
- Main file path: `app.py`
- Python version: `3.12`

The required Python dependencies are declared in `requirements.txt`.

## Deploy

1. Push this repository to GitHub.
2. Open https://share.streamlit.io.
3. Click **Create app**.
4. Choose **Yup, I have an app**.
5. Select the GitHub repository, branch `main`, and file path `app.py`.
6. In **Advanced settings**, select Python `3.12`.
7. Click **Deploy**.

No secrets are required for the MVP. The Yahoo Finance toggle uses public market data through `yfinance`; if the data request fails, the app falls back to built-in conservative assumptions.

## Optional S&P Global / Capital IQ Data Provider

The app includes an enterprise data-provider layer for S&P Global / Capital IQ universe research. Credentials must be configured through Streamlit secrets or local `.streamlit/secrets.toml`; never commit real credentials to GitHub.

For the official S&P Capital IQ API, enter your Capital IQ API username and password. The app defaults to:

- Token endpoint: `https://api-ciq.marketintelligence.spglobal.com/gdsapi/rest/authenticate/api/v1/token`
- Web Service Direct endpoint: `https://api-ciq.marketintelligence.spglobal.com/gdsapi/rest/v3/clientservice.json`
- Default mnemonics: `IQ_COMPANY_NAME`, `IQ_MARKETCAP`, `IQ_TOTAL_REV`, `IQ_EBITDA`

Example:

```toml
[spglobal]
base_url = ""
token_url = ""
clientservice_url = ""

username = ""
password = ""

ciq_mnemonics = "IQ_COMPANY_NAME,IQ_MARKETCAP,IQ_TOTAL_REV,IQ_EBITDA"
ciq_identifier_map = '{"EUNL.DE":"EUNL:DB","VVSM.DE":"VVSM:DB","GRID.DE":"GRID:DB","EUNA.DE":"EUNA:DB","PPFB.DE":"PPFB:DB"}'

timeout = "20"
```

Capital IQ identifiers work best in `TICKER:EXCHANGE` format, such as `IBM:NYSE` or `NVDA:NASDAQ`. If the app input uses Yahoo tickers like `EUNL.DE`, configure `ciq_identifier_map` to translate them into your Capital IQ identifiers.

After saving secrets, select **S&P Global / Capital IQ beta** in the app and click **Check Capital IQ API**. A healthy configuration returns both `auth_ok: true` and `query_ok: true`. If authentication succeeds but query fails, the most common causes are an unsupported identifier, missing mnemonic entitlement, or a custom endpoint requirement from S&P support.

For a custom S&P/Capital IQ enterprise universe endpoint, set `base_url`, `universe_endpoint`, and either `api_key` or `username`/`password`. That endpoint should return JSON records with fields such as `name`, `ticker`, `isin`, `wkn`, `assetClass`, `exchange`, `currency`, `yahooTicker`, `expectedReturn`, `expectedVolatility`, `maxDrawdown`, `themeExposure`, `liquidityScore`, and `confidence`.

If credentials are absent or a request fails, the app falls back to the built-in UCITS/EUR universe.

## Update

After deployment, Streamlit Community Cloud watches the GitHub repository. Push changes to `main` and the app should update automatically.

## Local Verification

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
.\scripts\start_app.ps1
```

Then open:

```text
http://localhost:8501
```
