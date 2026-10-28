"""
Interactive Brokers Client Portal REST API Client for MAPLE
Connects to the local Client Portal Gateway (https://localhost:5000)
Handles account discovery, balance fetching, TSX contract resolution,
Level-1 quote fetching, and limit order placement with auto-confirmation.
"""

import os
import json
import time
import requests
import urllib3
from typing import Dict, Any, List, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(MAPLE_DIR, "ibkr_symbols_cache.json")


class IBKRClient:
    DEFAULT_BASE_URL = "https://localhost:5000/v1/api"

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = False
        self._ensure_connection()

    def is_authenticated(self) -> bool:
        try:
            res = self.session.get(f"{self.base_url}/iserver/auth/status", timeout=5)
            if res.status_code == 200 and res.text:
                return bool(res.json().get("authenticated", False))
            return False
        except Exception:
            return False

    def tickle(self):
        """Keeps the session alive with IBKR."""
        try:
            self.session.post(f"{self.base_url}/tickle", timeout=3)
        except Exception:
            pass

    def _ensure_connection(self):
        try:
            res = self.session.get(f"{self.base_url}/iserver/auth/status", timeout=5)
            if res.status_code == 200 and res.text:
                data = res.json()
                if not data.get("authenticated", False):
                    print("[IBKR WARNING] Gateway connected but not authenticated. Please log in at https://localhost:5000")
            elif res.status_code == 401:
                print("[IBKR WARNING] Gateway session expired or requires login at https://localhost:5000")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to IBKR Client Portal Gateway at {self.base_url}: {e}")

    def get_accounts(self) -> List[Dict[str, Any]]:
        try:
            res = self.session.get(f"{self.base_url}/portfolio/accounts", timeout=5)
            if res.status_code == 200 and res.text:
                data = res.json()
                if isinstance(data, list):
                    return data
            return []
        except Exception:
            return []

    def get_primary_account_id(self) -> str:
        accounts = self.get_accounts()
        if accounts:
            return accounts[0].get("accountId", accounts[0].get("id"))
        # Fallback to configured account in maple_config.json or environment
        from maple_ledger import load_config
        cfg = load_config()
        return cfg.get("account_id", os.getenv("IBKR_ACCOUNT_ID", ""))

    def get_balances(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        if not account_id:
            account_id = self.get_primary_account_id()
        
        try:
            res = self.session.get(f"{self.base_url}/portfolio/{account_id}/ledger", timeout=5)
            if res.status_code == 200 and res.text:
                ledger = res.json()
                cad_entry = ledger.get("CAD", {}) if isinstance(ledger, dict) else {}
                base_entry = ledger.get("BASE", {}) if isinstance(ledger, dict) else {}
                cash = cad_entry.get("cashbalance", base_entry.get("cashbalance", 0.0))
                total_equity = cad_entry.get("netliquidationvalue", base_entry.get("netliquidationvalue", cash))
                stock_val = cad_entry.get("stockmarketvalue", base_entry.get("stockmarketvalue", 0.0))
                
                # Summary for buying power
                bp = cash
                summary_res = self.session.get(f"{self.base_url}/portfolio/{account_id}/summary", timeout=5)
                if summary_res.status_code == 200 and summary_res.text:
                    summary = summary_res.json()
                    if isinstance(summary, dict) and "buyingpower" in summary:
                        bp = summary["buyingpower"].get("amount", cash)

                return {
                    "cash": round(float(cash), 2),
                    "total_equity": round(float(total_equity), 2),
                    "market_value": round(float(stock_val), 2),
                    "buying_power": round(float(bp), 2)
                }
        except Exception:
            pass
        return {"cash": 0.0, "total_equity": 0.0, "market_value": 0.0, "buying_power": 0.0}

    def get_positions(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not account_id:
            account_id = self.get_primary_account_id()
        
        try:
            self.session.post(f"{self.base_url}/portfolio/{account_id}/positions/invalidate", timeout=3)
        except Exception:
            pass

        try:
            res = self.session.get(f"{self.base_url}/portfolio/{account_id}/positions/0", timeout=5)
            if res.status_code == 200 and res.text:
                data = res.json()
            else:
                data = []
        except Exception:
            data = []
        
        if not isinstance(data, list):
            return []
        
        positions = []
        for p in data:
            pos_qty = float(p.get("position", 0.0))
            if pos_qty != 0:
                sym = p.get("ticker", p.get("contractDesc", "")).upper()
                base_sym = sym[:-3] if sym.endswith(".TO") else sym
                base_sym = base_sym.replace(".", "-")
                full_sym = f"{base_sym}.TO" if (sym.endswith(".TO") or p.get("currency") == "CAD") else base_sym
                positions.append({
                    "symbol": full_sym,
                    "ticker": sym,
                    "openQuantity": pos_qty,
                    "averageEntryPrice": float(p.get("avgCost", 0.0)),
                    "currentPrice": float(p.get("mktPrice", p.get("avgCost", 0.0))),
                    "marketValue": float(p.get("mktValue", 0.0)),
                    "symbolId": p.get("conid"),
                    "conid": p.get("conid"),
                    "currency": p.get("currency", "CAD")
                })
        return positions

    def search_symbol(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Resolves TSX ticker (e.g. CNR.TO, CNR, SHOP.TO) to IBKR Contract details with caching."""
        cached = {}
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
            except Exception:
                cached = {}

        ticker_upper = ticker.upper()
        if ticker_upper in cached:
            return cached[ticker_upper]

        clean_syms = [
            ticker_upper.replace(".TO", "").replace("-", " "),
            ticker_upper.replace(".TO", "").replace("-", "."),
            ticker_upper.replace(".TO", "")
        ]
        # Remove duplicates while preserving order
        clean_syms = list(dict.fromkeys(clean_syms))

        matched = None
        for sym_cand in clean_syms:
            try:
                res = self.session.post(
                    f"{self.base_url}/iserver/secdef/search",
                    json={"symbol": sym_cand, "name": True, "secType": "STK"},
                    timeout=8
                ).json()
            except Exception:
                continue

            if isinstance(res, list):
                # Prefer CAD currency on TSE
                for item in res:
                    cid = item.get("conid")
                    try:
                        cid_int = int(cid)
                    except (ValueError, TypeError):
                        continue
                    if cid_int <= 0:
                        continue
                    
                    try:
                        info = self.session.get(f"{self.base_url}/iserver/contract/{cid_int}/info", timeout=5).json()
                    except Exception:
                        continue
                    valid_exchanges = info.get("valid_exchanges", "")
                    currency = info.get("currency", "")
                    if "TSE" in valid_exchanges and currency == "CAD":
                        matched = {
                            "symbol": ticker_upper,
                            "symbolId": cid_int,
                            "conid": cid_int,
                            "company_name": info.get("company_name", item.get("description")),
                            "currency": currency,
                            "exchange": "TSE"
                        }
                        break
                
                # Fallback if no specific TSE match found
                if not matched and res:
                    for item in res:
                        cid = item.get("conid")
                        try:
                            cid_int = int(cid)
                        except (ValueError, TypeError):
                            continue
                        if cid_int > 0:
                            try:
                                info = self.session.get(f"{self.base_url}/iserver/contract/{cid_int}/info", timeout=5).json()
                            except Exception:
                                continue
                            matched = {
                                "symbol": ticker_upper,
                                "symbolId": cid_int,
                                "conid": cid_int,
                                "company_name": info.get("company_name", item.get("description")),
                                "currency": info.get("currency", "CAD"),
                                "exchange": info.get("exchange", "SMART")
                            }
                            break
            if matched:
                break

        if matched:
            cached[ticker_upper] = matched
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cached, f, indent=2)
            except Exception:
                pass

        return matched

    @staticmethod
    def _parse_price(v: Any) -> Optional[float]:
        """Parses IBKR snapshot price strings, stripping status prefixes like 'C' (close) or 'H' (halted)."""
        if v is None:
            return None
        try:
            s = str(v).replace(",", "").strip().lstrip("CcHh")
            return float(s) if s else None
        except Exception:
            return None

    def _parse_quote_snapshot(self, s: Dict[str, Any]) -> Dict[str, Any]:
        """Parses an IBKR snapshot dict including field 6509 market data availability ('R'=real-time, 'D'=delayed)."""
        avail = str(s.get("6509", "")).upper()
        is_realtime = ("R" in avail) and ("D" not in avail)
        return {
            "lastTradePrice": self._parse_price(s.get("31")),
            "bidPrice": self._parse_price(s.get("84")),
            "askPrice": self._parse_price(s.get("86")),
            "highPrice": self._parse_price(s.get("70")),
            "lowPrice": self._parse_price(s.get("71")),
            "openPrice": self._parse_price(s.get("7295")),
            "marketDataAvailability": avail,
            "isDelayed": not is_realtime,
        }

    def get_quote(self, symbol_id: int) -> Dict[str, Any]:
        """Fetches live Ask, Bid, Last, High, Low, Open, and availability flag (6509) for limit order sizing."""
        fields = "31,84,86,70,71,87,7295,6509"
        try:
            # First call triggers subscription
            self.session.get(f"{self.base_url}/iserver/marketdata/snapshot", params={"conids": str(symbol_id), "fields": fields}, timeout=5)
            time.sleep(0.6)
            snap = self.session.get(f"{self.base_url}/iserver/marketdata/snapshot", params={"conids": str(symbol_id), "fields": fields}, timeout=5).json()
            if snap and isinstance(snap, list):
                return self._parse_quote_snapshot(snap[0])
        except Exception:
            pass
        return {}

    def get_quotes(self, symbol_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Fetches live Ask, Bid, Last, High, Low, Open, and availability flag (6509) in a single batch snapshot."""
        if not symbol_ids:
            return {}
        
        fields = "31,84,86,70,71,87,7295,6509"
        conids_str = ",".join(str(s) for s in symbol_ids)
        try:
            # First call registers/triggers subscriptions
            self.session.get(
                f"{self.base_url}/iserver/marketdata/snapshot",
                params={"conids": conids_str, "fields": fields},
                timeout=8
            )
            time.sleep(0.6)
            res = self.session.get(
                f"{self.base_url}/iserver/marketdata/snapshot",
                params={"conids": conids_str, "fields": fields},
                timeout=8
            )
            if res.status_code == 200 and res.text:
                snap_list = res.json()
                results = {}
                if isinstance(snap_list, list):
                    for s in snap_list:
                        cid = s.get("conid")
                        if not cid:
                            continue
                        try:
                            cid_int = int(cid)
                        except (ValueError, TypeError):
                            continue

                        results[cid_int] = self._parse_quote_snapshot(s)
                    if results:
                        return results
        except Exception as e:
            print(f"[IBKR WARNING] Batch quote fetch error: {e}")
        
        # Fallback to individual get_quote
        fallback = {}
        for sid in symbol_ids:
            q = self.get_quote(sid)
            if q:
                fallback[sid] = q
        return fallback

    def place_limit_order(
        self,
        account_id: str,
        symbol_id: int,
        action: str,  # "Buy" or "Sell"
        quantity: int,
        limit_price: float,
    ) -> Dict[str, Any]:
        """Submits a Limit Day order on IBKR and automatically confirms any warning prompts."""
        if quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {quantity}")
        if limit_price <= 0:
            raise ValueError(f"Limit price must be positive, got {limit_price}")

        payload = {
            "orders": [
                {
                    "conid": int(symbol_id),
                    "orderType": "LMT",
                    "price": round(float(limit_price), 2),
                    "side": action.upper(),
                    "tif": "DAY",
                    "quantity": int(quantity)
                }
            ]
        }

        url = f"{self.base_url}/iserver/account/{account_id}/orders"
        try:
            http_res = self.session.post(url, json=payload, timeout=10)
            res = http_res.json()
        except Exception as e:
            raise RuntimeError(f"IBKR order placement request failed: {e}")

        # Handle questions/warnings if returned (replyId loop)
        for _ in range(5):
            reply_id = None
            msg = ""
            if isinstance(res, list) and res and isinstance(res[0], dict) and "id" in res[0]:
                reply_id = res[0]["id"]
                msg = res[0].get("message", [""])[0] if isinstance(res[0].get("message"), list) else str(res[0].get("message"))
            elif isinstance(res, dict) and "id" in res:
                reply_id = res["id"]
                msg = res.get("message", [""])[0] if isinstance(res.get("message"), list) else str(res.get("message"))

            if reply_id:
                print(f"[IBKR CONFIRMATION REQUIRED] {msg} -> Auto-confirming replyId: {reply_id}")
                try:
                    reply_res = self.session.post(f"{self.base_url}/iserver/reply/{reply_id}", json={"confirmed": True}, timeout=10).json()
                    res = reply_res
                except Exception as e:
                    print(f"[IBKR CONFIRMATION ERROR] Failed to confirm replyId {reply_id}: {e}")
                    break
            else:
                break

        # Extract orderId
        order_id = None
        if isinstance(res, list) and res:
            order_id = res[0].get("order_id", res[0].get("orderId"))
        elif isinstance(res, dict):
            order_id = res.get("order_id", res.get("orderId"))

        return {
            "orderId": order_id,
            "orders": [{"id": order_id}],
            "raw_response": res
        }

    def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        return self.session.delete(f"{self.base_url}/iserver/account/{account_id}/order/{order_id}", timeout=5).json()

    def get_order_status(self, account_id: str, order_id: str) -> Dict[str, Any]:
        res = self.session.get(f"{self.base_url}/iserver/account/order/status/{order_id}", timeout=5).json()
        return res

    def get_live_orders(self) -> List[Dict[str, Any]]:
        """Retrieves list of active/working orders on the account."""
        try:
            res = self.session.get(f"{self.base_url}/iserver/account/orders", timeout=5).json()
            if isinstance(res, dict) and "orders" in res:
                return res["orders"]
            elif isinstance(res, list):
                return res
            return []
        except Exception:
            return []
