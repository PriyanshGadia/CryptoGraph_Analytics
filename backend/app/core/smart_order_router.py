"""
Multi-Exchange Smart Order Router (SOR)
Queries Level 2 Order Book depth across multiple exchanges (Binance, Kraken, Coinbase)
to determine the best execution route and calculate true slippage.
"""

from typing import Dict, Any, List, Optional
import ccxt
import urllib.request
import json
from app.db.database import SessionLocal
from app.db.models_sqla import AppSetting

class SmartOrderRouter:
    def __init__(self):
        self.exchanges = ["binance", "kraken", "coinbase"]
        self.exchange_clients = {}
        for ex in self.exchanges:
            try:
                cls = getattr(ccxt, ex)
                self.exchange_clients[ex] = cls({
                    'enableRateLimit': True,
                    'timeout': 5000,
                })
            except Exception as e:
                print(f"Error initializing CCXT exchange client for {ex}: {e}")

    def _get_rpc_url(self) -> str:
        """Retrieves custom Ethereum RPC URL from DB if set, otherwise cloudflare public RPC."""
        db = SessionLocal()
        try:
            record = db.query(AppSetting).filter(AppSetting.setting_key == "ethereum_rpc_url").first()
            if record and record.setting_value:
                return record.setting_value
        except Exception:
            pass
        finally:
            db.close()
        return "https://cloudflare-eth.com"

    def _estimate_eth_gas_fee_usd(self) -> float:
        """
        Estimates the current Ethereum gas fee in USD by querying a public Ethereum RPC 
        and fetching the current ETH price from Coinbase/Kraken.
        """
        # 1. Fetch current gas price from RPC (default to 30 gwei fallback if fail)
        gas_price_gwei = 30.0
        rpc_url = self._get_rpc_url()
        try:
            req_data = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_gasPrice",
                "params": [],
                "id": 1
            }).encode('utf-8')
            
            req = urllib.request.Request(
                rpc_url, 
                data=req_data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                res = json.loads(response.read().decode('utf-8'))
                if "result" in res:
                    gas_price_wei = int(res["result"], 16)
                    gas_price_gwei = gas_price_wei / 1e9
        except Exception as e:
            print(f"[SOR] Error fetching live gas price: {e}. Using fallback 30 Gwei.")

        # 2. Fetch current ETH price in USD from CCXT
        eth_price = 3000.0
        for client_name in ["coinbase", "kraken", "binance"]:
            client = self.exchange_clients.get(client_name)
            if client:
                try:
                    ticker = client.fetch_ticker("ETH/USDT" if client_name == "binance" else "ETH/USD")
                    if ticker and "last" in ticker:
                        eth_price = float(ticker["last"])
                        break
                except Exception:
                    continue

        # Standard swap gas limit (approx 150,000 gas)
        swap_gas_limit = 150000
        gas_fee_eth = (gas_price_gwei * 1e9 * swap_gas_limit) / 1e18
        gas_fee_usd = gas_fee_eth * eth_price
        
        print(f"[SOR] Live Gas Price: {gas_price_gwei:.2f} Gwei | ETH: ${eth_price:.2f} | Gas Fee: ${gas_fee_usd:.2f}")
        return round(gas_fee_usd, 2)

    def _fetch_real_l2_book(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Attempts to fetch real L2 order book using CCXT.
        """
        client = self.exchange_clients.get(exchange)
        if not client:
            return None
        
        sym = symbol.upper()
        pairs_to_try = [f"{sym}/USDT", f"{sym}/USD", f"{sym}/BTC"]
        
        for pair in pairs_to_try:
            try:
                book = client.fetch_order_book(pair, limit=10)
                bids = [[float(p), float(v)] for p, v in book.get("bids", [])]
                asks = [[float(p), float(v)] for p, v in book.get("asks", [])]
                if bids and asks:
                    return {"bids": bids, "asks": asks}
            except Exception:
                continue
        return None

    def calculate_best_route(self, symbol: str, side: str, order_value_usd: float, current_price: float) -> Dict[str, Any]:
        """
        Finds the best exchange route for a given order size by walking the L2 order book.
        Returns the optimal exchange and the estimated slippage %.
        """
        if order_value_usd <= 0:
            return {"exchange": "binance", "slippage_pct": 0.0, "average_fill_price": current_price}
            
        best_exchange = None
        best_fill_price = float('inf') if side == "buy" else 0.0
        best_slippage = 1.0

        for exchange in self.exchanges:
            book = self._fetch_real_l2_book(exchange, symbol)
            if not book:
                print(f"[SOR] Warning: Order book depth not available for {symbol} on {exchange}.")
                continue
                
            levels = book["asks"] if side == "buy" else book["bids"]
            
            remaining_usd = order_value_usd
            total_cost_or_revenue = 0.0
            total_filled_amount = 0.0
            
            for price, volume in levels:
                level_usd_capacity = price * volume
                
                if remaining_usd <= level_usd_capacity:
                    total_filled_amount += remaining_usd / price
                    total_cost_or_revenue += remaining_usd
                    remaining_usd = 0
                    break
                else:
                    remaining_usd -= level_usd_capacity
                    total_filled_amount += volume
                    total_cost_or_revenue += level_usd_capacity
                    
            if remaining_usd > 0:
                slippage_pct = 0.10
                avg_price = current_price * 1.10 if side == "buy" else current_price * 0.90
            else:
                if total_filled_amount > 0:
                    avg_price = total_cost_or_revenue / total_filled_amount
                else:
                    avg_price = current_price
                    
                if side == "buy":
                    slippage_pct = (avg_price - current_price) / current_price
                else:
                    slippage_pct = (current_price - avg_price) / current_price
                slippage_pct = max(0.0, slippage_pct)

            if side == "buy" and avg_price < best_fill_price:
                best_fill_price = avg_price
                best_exchange = exchange
                best_slippage = slippage_pct
            elif side == "sell" and avg_price > best_fill_price:
                best_fill_price = avg_price
                best_exchange = exchange
                best_slippage = slippage_pct
                
        if best_exchange is None:
            print(f"[SOR] Alert: No live order books reachable for {symbol}. Falling back to zero-slippage mid-market pricing.")
            best_exchange = "binance"
            best_fill_price = current_price
            best_slippage = 0.0

        estimated_gas_usd = self._estimate_eth_gas_fee_usd()
        gas_impact_pct = estimated_gas_usd / order_value_usd
        gas_too_high = gas_impact_pct > 0.01

        return {
            "exchange": best_exchange,
            "slippage_pct": best_slippage,
            "average_fill_price": best_fill_price,
            "estimated_gas_usd": estimated_gas_usd,
            "gas_too_high": gas_too_high
        }

if __name__ == "__main__":
    sor = SmartOrderRouter()
    route = sor.calculate_best_route("BTC", "buy", 500.0, 65000.0)
    print(f"Optimal Route: {route}")
