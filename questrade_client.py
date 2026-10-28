"""
Questrade REST API Client for MAPLE
Handles OAuth2 refresh-token rotation, account discovery,
balance fetching, position monitoring, and safe limit-order execution.
"""

import os
import json
import time
import requests
from typing import Dict, Any, List, Optional

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_STORE_FILE = os.path.join(MAPLE_DIR, "questrade_token_store.json")
ENV_FILE = os.path.join(MAPLE_DIR, ".env")


def load_env_vars() -> Dict[str, str]:
    env_vars = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars


class QuestradeClient:
    AUTH_URL = "https://login.questrade.com/oauth2/token"

    def __init__(self):
        self.access_token = None
        self.api_server = None
        self.refresh_token = None
        self.expires_at = 0
        self._load_cached_tokens()

    def _load_cached_tokens(self):
        if os.path.exists(TOKEN_STORE_FILE):
            try:
                with open(TOKEN_STORE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.api_server = data.get("api_server")
                    self.refresh_token = data.get("refresh_token")
                    self.expires_at = data.get("expires_at", 0)
            except Exception:
                pass

        if not self.refresh_token:
            env_vars = load_env_vars()
            self.refresh_token = env_vars.get("QUESTRADE_REFRESH_TOKEN")

    def _save_tokens(self, data: Dict[str, Any]):
        self.access_token = data["access_token"]
        self.api_server = data["api_server"]
        self.refresh_token = data["refresh_token"]
        # expires_in is in seconds (typically 1800)
        self.expires_at = time.time() + data.get("expires_in", 1800) - 60

        with open(TOKEN_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": self.access_token,
                "api_server": self.api_server,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at
            }, f, indent=2)

    def authenticate(self) -> bool:
        """Exchanges refresh token for an access token and new refresh token."""
        # If access token is still valid, reuse
        if self.access_token and self.api_server and time.time() < self.expires_at:
            return True

        if not self.refresh_token or self.refresh_token == "your_refresh_token_here":
            raise ValueError(
                "No valid Questrade refresh token found! Please paste your token in C:\\Users\\Aamir\\OneDrive\\AI Projects\\MAPLE\\.env"
            )

        params = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        res = requests.get(self.AUTH_URL, params=params, timeout=15)
        if res.status_code != 200:
            raise ConnectionError(
                f"Questrade OAuth authentication failed ({res.status_code}): {res.text}"
            )

        data = res.json()
        self._save_tokens(data)
        return True

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        self.authenticate()
        url = f"{self.api_server.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        res = requests.request(method, url, headers=headers, timeout=15, **kwargs)
        if res.status_code == 401:
            # Token might have expired early, force refresh once
            self.expires_at = 0
            self.authenticate()
            headers["Authorization"] = f"Bearer {self.access_token}"
            res = requests.request(method, url, headers=headers, timeout=15, **kwargs)

        if not res.ok:
            raise RuntimeError(f"Questrade API error ({res.status_code}) on {endpoint}: {res.text}")
        return res.json()

    def get_accounts(self) -> List[Dict[str, Any]]:
        """Returns list of user accounts."""
        res = self._request("GET", "v1/accounts")
        return res.get("accounts", [])

    def get_primary_account_id(self) -> str:
        env_vars = load_env_vars()
        configured = env_vars.get("QUESTRADE_ACCOUNT_ID")
        if configured:
            return configured

        accounts = self.get_accounts()
        if not accounts:
            raise RuntimeError("No Questrade accounts found for this user.")
        # Filter for active trading accounts
        for acc in accounts:
            if acc.get("status") == "Active":
                return acc["number"]
        return accounts[0]["number"]

    def get_balances(self, account_id: str) -> Dict[str, Any]:
        """Fetches CAD & USD cash balances and total equity."""
        res = self._request("GET", f"v1/accounts/{account_id}/balances")
        combined = res.get("combinedBalances", [])
        cad_entry = next((b for b in combined if b.get("currency") == "CAD"), {})
        
        # Per-currency balances
        per_currency = res.get("perCurrencyBalances", [])
        cad_cash = next((b for b in per_currency if b.get("currency") == "CAD"), {})

        return {
            "cash": cad_cash.get("cash", 0.0),
            "total_equity": cad_entry.get("totalEquity", 0.0),
            "market_value": cad_entry.get("marketValue", 0.0),
            "buying_power": cad_cash.get("buyingPower", 0.0)
        }

    def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetches current open equity positions."""
        res = self._request("GET", f"v1/accounts/{account_id}/positions")
        return res.get("positions", [])

    def search_symbol(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Resolves ticker symbol (e.g. SHOP.TO or SHOP) to Questrade symbol details with caching."""
        cache_file = os.path.join(MAPLE_DIR, "questrade_symbols_cache.json")
        cached = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
            except Exception:
                cached = {}

        ticker_upper = ticker.upper()
        if ticker_upper in cached:
            return cached[ticker_upper]

        alt_ticker = ticker_upper.replace("-", ".")
        clean_prefix = ticker.replace(".TO", "").split("-")[0]
        res = self._request("GET", f"v1/symbols/search?prefix={clean_prefix}")
        symbols = res.get("symbols", [])
        matched = None
        # 1. Exact match on TSX that is common Stock (either ticker_upper or alt_ticker)
        for s in symbols:
            sym_u = s.get("symbol", "").upper()
            if (sym_u == ticker_upper or sym_u == alt_ticker) and s.get("listingExchange", "").upper() == "TSX" and s.get("securityType", "").upper() == "STOCK":
                matched = s
                break
        # 2. Exact match on symbol
        if not matched:
            for s in symbols:
                sym_u = s.get("symbol", "").upper()
                if sym_u == ticker_upper or sym_u == alt_ticker:
                    matched = s
                    break
        # 3. TSX Stock starting with prefix
        if not matched:
            for s in symbols:
                sym_name = s.get("symbol", "").upper()
                listing = s.get("listingExchange", "").upper()
                sec_type = s.get("securityType", "").upper()
                if sym_name.startswith(clean_prefix) and "TSX" in listing and sec_type == "STOCK":
                    matched = s
                    break
        if not matched and symbols:
            matched = symbols[0]

        if matched:
            cached[ticker_upper] = matched
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cached, f, indent=2)
            except Exception:
                pass

        return matched

    def get_quote(self, symbol_id: int) -> Dict[str, Any]:
        """Fetches live Ask, Bid, and Last price for limit order sizing."""
        res = self._request("GET", f"v1/markets/quotes/{symbol_id}")
        quotes = res.get("quotes", [])
        if quotes:
            return quotes[0]
        return {}

    def get_order_status(self, account_id: str, order_id: int) -> Dict[str, Any]:
        """Fetches status of a specific order."""
        res = self._request("GET", f"v1/accounts/{account_id}/orders/{order_id}")
        orders = res.get("orders", [])
        if orders:
            return orders[0]
        return {}

    def cancel_order(self, account_id: str, order_id: int) -> Dict[str, Any]:
        """Cancels an open order."""
        return self._request("DELETE", f"v1/accounts/{account_id}/orders/{order_id}")

    def place_limit_order(
        self,
        account_id: str,
        symbol_id: int,
        action: str,  # "Buy" or "Sell"
        quantity: int,
        limit_price: float,
    ) -> Dict[str, Any]:
        """Submits a Limit Day order on Questrade."""
        if quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {quantity}")
        if limit_price <= 0:
            raise ValueError(f"Limit price must be positive, got {limit_price}")

        payload = {
            "symbolId": symbol_id,
            "quantity": quantity,
            "limitPrice": round(limit_price, 2),
            "isAnonymous": False,
            "icebergQuantity": None,
            "timeInForce": "Day",
            "action": action.capitalize(),
            "orderType": "Limit",
            "primaryRoute": "AUTO",
            "secondaryRoute": "AUTO"
        }

        res = self._request("POST", f"v1/accounts/{account_id}/orders", json=payload)
        return res

