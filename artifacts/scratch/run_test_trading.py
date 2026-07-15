import sys
import os
import asyncio
import logging

# Add backend to python path
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

# Configure logging
logging.basicConfig(level=logging.INFO)

from app.services.trading_agent import execute_daily_trades

async def main():
    print("Running execute_daily_trades()...")
    res = await execute_daily_trades()
    print("Result:", res)

if __name__ == "__main__":
    asyncio.run(main())
