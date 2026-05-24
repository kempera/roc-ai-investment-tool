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

The app includes a beta enterprise data-provider layer for S&P Global / Capital IQ universe research. Credentials must be configured through Streamlit secrets or local `.streamlit/secrets.toml`; never commit real credentials to GitHub.

Example:

```toml
[spglobal]
base_url = "https://your-spglobal-api-host.example"
universe_endpoint = "/your/universe/search/endpoint"

# Use either api_key or username/password.
api_key = ""
api_key_header = "" # optional, e.g. "Ocp-Apim-Subscription-Key"; default is bearer token
token_url = ""
username = ""
password = ""

timeout = "20"
```

The provider expects the configured universe endpoint to return JSON records with fields such as `name`, `ticker`, `isin`, `wkn`, `assetClass`, `exchange`, `currency`, `yahooTicker`, `expectedReturn`, `expectedVolatility`, `maxDrawdown`, `themeExposure`, `liquidityScore`, and `confidence`. If the endpoint is missing, credentials are absent, or a request fails, the app falls back to the built-in UCITS/EUR universe.

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
