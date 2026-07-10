import argparse
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List

# DB imports are intentionally delayed (inside functions) because:
# - unit validation of TOP_100_SYMBOLS should work even when DB/ORM import paths aren't configured
# - repo entrypoints differ (kaggle vs local), and backend/app uses `app.*` imports

# Deterministic canonical 100-asset list (authoritative ordering provided by user).
# NOTE: This list must resolve to exactly 100 UNIQUE symbols after sanitization.
_RAW_ASSET_SYMBOLS = [
    # Tier 1 — Foundational L1 (21)
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "TRX", "TON",
    "NEAR", "ATOM", "APT", "SUI", "HBAR", "ICP", "ALGO", "XLM", "SEI", "TIA", "XMR",

    # Tier 2 — L2 / Scaling (7)
    "ARB", "OP", "POL", "IMX", "STRK", "MNT", "ZK",

    # Tier 3 — DeFi Blue Chip (14)
    "LINK", "UNI", "AAVE", "MKR", "LDO", "CRV", "SNX",
    "COMP", "SUSHI", "GMX", "PENDLE", "ENA", "FXS", "ENS",

    # Tier 4 — Exchange Tokens (4)
    "CRO", "OKB", "LEO", "HYPE",

    # Tier 5 — Meme / Momentum (12)
    "DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI",
    "CAKE", "1INCH", "ANKR", "MEW", "RSR", "OCEAN",

    # Tier 6 — AI / DePIN (8)
    "FET", "RENDER", "AUDIO", "AKT", "WLD", "GRT", "IO", "HNT",

    # Tier 7 — Stablecoins (5)
    "USDT", "USDC", "DAI", "FDUSD", "PYUSD",

    # Tier 8 — Oracle / Storage / Infra (5)
    "FIL", "AR", "PYTH", "INJ", "QNT",

    # Tier 9 — Legacy Forks / Majors (6)
    "LTC", "BCH", "ETC", "ZEC", "XTZ", "EOS",

    # Tier 10 — Bitcoin-Ecosystem Expansion (2)
    "CORE", "ORDI",

    # Tier 11 — RWA (1)
    "ONDO",

    # Tier 12 — Gaming / Metaverse (4)
    "SAND", "MANA", "AXS", "GALA",

    # Tier 13 — Solana Ecosystem (2)
    "JUP", "RAY",

    # Tier 14 — Interop (1)
    "W",

    # Tier 15 — Index-Grade Majors (8)
    "DYDX", "EGLD", "FLOW", "FTM", "KAS", "RUNE", "THETA", "VET",
]

def _sanitize_symbol(sym: str) -> str:
    sym = sym.strip().upper()
    # keep A-Z, 0-9 only (common crypto tickers are alnum)
    sym = re.sub(r"[^A-Z0-9]", "", sym)
    return sym

def _build_canonical_list() -> List[str]:
    syms = [_sanitize_symbol(s) for s in _RAW_ASSET_SYMBOLS if s and s.strip()]
    # Remove empties
    syms = [s for s in syms if s]
    # Enforce uniqueness while preserving order:
    # Since the provided list includes repeats (e.g., DOGE/PEPE/BONK/WIF/FLOKI),
    # we must dedupe to get exactly 100 unique assets.
    seen = set()
    uniq = []
    for s in syms:
        if s not in seen:
            seen.add(s)
            uniq.append(s)

    if len(uniq) != 100:
        raise ValueError(
            f"TOP_100_SYMBOLS must resolve to exactly 100 UNIQUE symbols after sanitization/dedup.\n"
            f"Got unique={len(uniq)} (total raw={len(syms)})."
        )

    return uniq

# Exported canonical list for use across repo.
TOP_100_SYMBOLS: List[str] = _build_canonical_list()

def _ensure_backend_imports() -> None:
    # training_pipeline_enterprise.py uses the same sys.path strategy:
    # repo root + repo root/backend so `backend.app.*` can resolve `app.*`.
    repo_root = Path(__file__).resolve()
    for parent in repo_root.parents:
        if (parent / "backend").exists() and (parent / "README.md").exists():
            repo_root = parent
            break

    backend_dir = repo_root / "backend"
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))
    if str(backend_dir) not in sys.path:
        sys.path.append(str(backend_dir))


def seed_assets(symbols: List[str]) -> int:
    _ensure_backend_imports()

    # Delayed ORM imports (avoid import-time failures when only validating TOP_100_SYMBOLS).
    from backend.app.db.database import Base, engine, SessionLocal
    from backend.app.db.models import Asset

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        inserted_or_updated = 0

        for sym in symbols:
            asset = db.query(Asset).filter_by(symbol=sym).first()
            if asset is None:
                asset = Asset(
                    symbol=sym,
                    name=sym,
                    sector=None,
                    market_cap_usd=0.0,
                )
                db.add(asset)
                inserted_or_updated += 1
            else:
                if getattr(asset, "name", None) is None:
                    asset.name = sym
                    inserted_or_updated += 1

        db.commit()
        return inserted_or_updated
    finally:
        db.close()

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/update top-100 crypto assets in cryptograph.db.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing.")
    parser.add_argument("--count", type=int, default=0, help="Optional: use first N symbols from the canonical list.")
    args = parser.parse_args()

    symbols = TOP_100_SYMBOLS
    if args.count and args.count > 0:
        symbols = symbols[: args.count]

    if len(symbols) != len(set(symbols)):
        raise ValueError("Canonical symbols contain duplicates (should be impossible).")

    if args.dry_run:
        print(f"[dry-run] Would upsert {len(symbols)} assets.")
        return

    n = seed_assets(symbols)
    print(f"Seeded/updated assets: {n} (symbols total={len(symbols)})")

if __name__ == "__main__":
    main()
