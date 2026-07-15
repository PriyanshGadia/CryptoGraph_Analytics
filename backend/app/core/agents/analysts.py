import logging
logger = logging.getLogger(__name__)
"""Specialized Analyst Agents for the MoA Swarm."""
from app.core.agents.base import BaseAgent
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from app.db.models import Asset, AssetNews, OnchainMetric

class MacroEconomistAgent(BaseAgent):
    """Analyzes global macroeconomic conditions and systemic risk."""
    
    def __init__(self, db: Session):
        super().__init__(db, "MacroEconomistAgent")
        
    async def analyze(self, symbol: str) -> str:
        try:
            # Ensure the macro_indicators table exists and has baseline data
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS macro_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fed_rate FLOAT,
                    vix FLOAT,
                    cpi FLOAT,
                    inflation FLOAT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            self.db.commit()
            
            res = self.db.execute(text("SELECT fed_rate, vix, cpi, inflation FROM macro_indicators ORDER BY timestamp DESC LIMIT 1")).fetchone()
            if not res:
                self.db.execute(text("""
                    INSERT INTO macro_indicators (fed_rate, vix, cpi, inflation)
                    VALUES (5.25, 14.50, 3.10, 2.50)
                """))
                self.db.commit()
                res = self.db.execute(text("SELECT fed_rate, vix, cpi, inflation FROM macro_indicators ORDER BY timestamp DESC LIMIT 1")).fetchone()

            if not res:
                return "MACRO_FALLBACK: No macroeconomic data available in the system."
                
            fed_rate = res[0]
            vix = res[1]
            cpi = res[2]
            inflation = res[3]
            
            if None in (fed_rate, vix, cpi, inflation):
                return "MACRO_FALLBACK: Incomplete macroeconomic data available in the system."
                
        except Exception as e:
            logger.info(f"[MacroEconomistAgent] Database query error: {e}")
            return "MACRO_FALLBACK: Macroeconomic data query failed."
            
        system_prompt = (
            "You are a seasoned Macroeconomist. You evaluate systemic risk "
            "and liquidity conditions. Provide a brief 2-sentence macro analysis "
            "for the crypto market."
        )
        prompt = (
            f"Assess the current macroeconomic risk for trading {symbol}.\n"
            f"Current Macro Indicators:\n"
            f"- Effective Federal Funds Rate: {fed_rate:.2f}%\n"
            f"- VIX Volatility Index: {vix:.2f}\n"
            f"- CPI: {cpi:.2f}%\n"
            f"- Expected Inflation: {inflation:.2f}%\n"
        )
        
        response = await self._query_llm(prompt, system_prompt)
        if response:
            return response
            
        return f"MACRO_SAFE_FALLBACK: Fed Rate is {fed_rate:.2f}%, VIX is {vix:.2f}. Macro conditions appear neutral."


class OnChainDetectiveAgent(BaseAgent):
    """Analyzes DefiLlama data for liquidity and network health."""
    
    def __init__(self, db: Session):
        super().__init__(db, "OnChainDetectiveAgent")
        
    async def analyze(self, symbol: str) -> str:
        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            return f"ONCHAIN_FALLBACK: No on-chain data available for {symbol}."
            
        # Fetch latest onchain metrics
        metrics = self.db.query(OnchainMetric).filter(
            OnchainMetric.asset_id == asset.id
        ).order_by(desc(OnchainMetric.timestamp)).limit(7).all()
        
        if not metrics:
            return f"ONCHAIN_FALLBACK: No on-chain TVL/Revenue data found for {symbol}."
            
        latest = metrics[0]
        tvl_str = f"${latest.tvl:,.2f}" if latest.tvl else "N/A"
        rev_str = f"${latest.revenue:,.2f}" if latest.revenue else "N/A"
        
        system_prompt = (
            "You are a blockchain data analyst. You look at TVL and Revenue "
            "to determine network adoption and liquidity health. Keep it to 2 sentences."
        )
        
        prompt = (
            f"Asset: {symbol}\n"
            f"Latest TVL: {tvl_str}\n"
            f"Latest 24h Revenue: {rev_str}\n"
            f"Evaluate the on-chain health of this asset."
        )
        
        response = await self._query_llm(prompt, system_prompt)
        if response:
            return response
            
        return f"ONCHAIN_SAFE_FALLBACK: TVL is {tvl_str}, Revenue is {rev_str}. Liquidity appears stable."


class SentimentAnalystAgent(BaseAgent):
    """Analyzes news headlines for market euphoria or panic."""
    
    def __init__(self, db: Session):
        super().__init__(db, "SentimentAnalystAgent")
        
    async def analyze(self, symbol: str) -> str:
        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        news = []
        if asset:
            news = self.db.query(AssetNews).filter(
                AssetNews.asset_id == asset.id
            ).order_by(desc(AssetNews.published_at)).limit(5).all()
            
        if not news:
            # Fallback to general market news headlines if symbol-specific news is empty
            news = self.db.query(AssetNews).order_by(desc(AssetNews.created_at)).limit(5).all()
            
        if not news:
            return f"SENTIMENT_FALLBACK: No news available for {symbol}."
            
        news_text = "\n".join([f"- [{n.source}] {n.headline}" for n in news])
        
        system_prompt = (
            "You are a crypto sentiment analyst. Read the headlines and "
            "determine if the market is in euphoria, panic, or neutral consolidation. "
            "Keep your assessment to 2 sentences."
        )
        
        prompt = (
            f"Asset: {symbol}\n"
            f"Recent Headlines:\n{news_text}\n\n"
            f"Provide your sentiment assessment."
        )
        
        response = await self._query_llm(prompt, system_prompt)
        if response:
            return response
            
        return "SENTIMENT_SAFE_FALLBACK: Headlines are mixed. No extreme panic or euphoria detected."
