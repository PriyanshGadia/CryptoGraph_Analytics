"""
Enriches the assets table with sector classification and market cap from CoinGecko.
Run once. No API key required.
"""
import os, time, requests
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "cryptograph.db"

BASE = "https://api.coingecko.com/api/v3"

SECTOR_MAP = {
    "BTC":"layer1","ETH":"layer1","SOL":"layer1","ADA":"layer1",
    "AVAX":"layer1","DOT":"layer1","NEAR":"layer1","FTM":"layer1",
    "UNI":"defi","AAVE":"defi","MKR":"defi","COMP":"defi",
    "CRV":"defi","SUSHI":"defi","BAL":"defi","YFI":"defi","SNX":"defi",
    "BNB":"exchange","ZRX":"exchange","LRC":"exchange",
    "XRP":"payment","XLM":"payment","LTC":"payment",
    "BCH":"payment","DASH":"payment","XMR":"payment",
    "SAND":"gaming","MANA":"gaming","AXS":"gaming","THETA":"gaming",
    "ZEC":"privacy",
    "FIL":"storage","IOTA":"storage",
    "DOGE":"other","LINK":"other","ATOM":"other","VET":"other",
    "TRX":"other","ALGO":"other","EOS":"other","WAVES":"other",
    "ICX":"other","QTUM":"other","ONT":"other","ZIL":"other",
    "DGB":"other","1INCH":"other","BAT":"other","REN":"other","MATIC":"other"
}

COIN_IDS = {
    "BTC":"bitcoin","ETH":"ethereum","BNB":"binancecoin","SOL":"solana",
    "XRP":"ripple","ADA":"cardano","DOGE":"dogecoin","AVAX":"avalanche-2",
    "LINK":"chainlink","DOT":"polkadot","MATIC":"matic-network","UNI":"uniswap",
    "ATOM":"cosmos","LTC":"litecoin","BCH":"bitcoin-cash","XLM":"stellar",
    "ALGO":"algorand","AAVE":"aave","MKR":"maker",
    "COMP":"compound-governance-token","CRV":"curve-dao-token","NEAR":"near",
    "SAND":"the-sandbox","MANA":"decentraland","AXS":"axie-infinity",
    "SUSHI":"sushi","BAL":"balancer","SNX":"havven","YFI":"yearn-finance",
    "ZRX":"0x","VET":"vechain","FIL":"filecoin","TRX":"tron",
    "THETA":"theta-token","XMR":"monero","EOS":"eos","LRC":"loopring",
    "BAT":"basic-attention-token","ZEC":"zcash","DASH":"dash","ICX":"icon",
    "QTUM":"qtum","ONT":"ontology","ZIL":"zilliqa","IOTA":"iota",
    "WAVES":"waves","DGB":"digibyte","1INCH":"1inch","FTM":"fantom",
    "REN":"republic-protocol"
}

def enrich_assets():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, symbol FROM assets")
    assets = cursor.fetchall()

    for asset in assets:
        symbol = asset["symbol"]
        coin_id = COIN_IDS.get(symbol)
        sector  = SECTOR_MAP.get(symbol, "other")

        market_cap = None
        if coin_id:
            try:
                r = requests.get(
                    f"{BASE}/coins/{coin_id}",
                    params={"localization":"false","market_data":"true",
                            "community_data":"false","developer_data":"false"},
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    market_cap = data.get("market_data",{}).get(
                        "market_cap",{}).get("usd")
                elif r.status_code == 429:
                    print("Rate limited, sleeping 60s...")
                    time.sleep(60)
                    r2 = requests.get(
                        f"{BASE}/coins/{coin_id}",
                        params={"localization":"false","market_data":"true",
                                "community_data":"false","developer_data":"false"},
                        timeout=10
                    )
                    if r2.status_code == 200:
                        data = r2.json()
                        market_cap = data.get("market_data",{}).get(
                            "market_cap",{}).get("usd")
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")

        cursor.execute(
            "UPDATE assets SET sector = ?, market_cap_usd = ?, name = ? WHERE id = ?",
            (sector, market_cap, symbol, asset["id"])
        )
        conn.commit()

        print(f"Updated {symbol}: sector={sector}, market_cap=${market_cap:,.0f}"
              if market_cap else f"Updated {symbol}: sector={sector}, market_cap=None")
        time.sleep(1.5)

    print("Asset enrichment complete")
    conn.close()

if __name__ == "__main__":
    enrich_assets()
