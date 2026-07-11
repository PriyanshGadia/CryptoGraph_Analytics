new_list = [
    # Tier 1 — Foundational L1 (21)
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "TRX", "TON",
    "NEAR", "ATOM", "APT", "SUI", "HBAR", "ICP", "ALGO", "XLM", "SEI", "TIA", "XMR",

    # Tier 2 — L2 / Scaling (7)
    "ARB", "OP", "POL", "LRC", "LSK", "OMG", "ONT",

    # Tier 3 — DeFi Blue Chip (14)
    "LINK", "UNI", "AAVE", "MKR", "LDO", "CRV", "SNX",
    "KAVA", "SUSHI", "ZRX", "BAL", "YFI", "KNC", "ENS",

    # Tier 4 — Exchange Tokens (4)
    "CRO", "OKB", "LEO", "QTUM",

    # Tier 5 — Meme / Momentum (12)
    "DOGE", "SHIB", "WIF", "BONK", "CAKE", "ANKR", "BAT", "RSR", "OCEAN",
    "WAVES", "ZIL", "REN",

    # Tier 6 — AI / DePIN (8)
    "FET", "RENDER", "AKT", "GRT", "HNT", "STORJ", "BAND", "CELR",

    # Tier 7 — Stablecoins (5)
    "USDT", "USDC", "DAI", "SKL", "NMR",

    # Tier 8 — Oracle / Storage / Infra (5)
    "FIL", "AR", "PYTH", "INJ", "QNT",

    # Tier 9 — Legacy Forks / Majors (7)
    "LTC", "BCH", "ETC", "ZEC", "XTZ", "EOS", "DASH",

    # Tier 10 — Bitcoin-Ecosystem Expansion (2)
    "CORE", "ORDI",

    # Tier 11 — RWA (1)
    "ONDO",

    # Tier 12 — Gaming / Metaverse / RWA (4)
    "SAND", "MANA", "IOTA", "FXS",

    # Tier 13 — Solana Ecosystem (2)
    "JUP", "RAY",

    # Tier 15 — Index-Grade Majors (8)
    "DYDX", "EGLD", "FLOW", "FTM", "KAS", "RUNE", "THETA", "VET",
]

print("Total elements:", len(new_list))
print("Unique elements:", len(set(new_list)))
print("Duplicates:", [x for x in set(new_list) if new_list.count(x) > 1])
