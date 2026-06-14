"""Specialized Analyst Agents for the MoA Swarm."""
from app.core.agents.base import BaseAgent
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models_sqla import Asset, AssetNews, OnchainMetric
from typing import Optional

class MacroEconomistAgent(BaseAgent):
    """Analyzes global macroeconomic conditions and systemic risk."""
    
    def __init__(self, db: Session):
        super().__init__(db, "MacroEconomistAgent")
        
    async def analyze(self, symbol: str) -> str:
        # In a fully fleshed out system, we would query the FRED tables here.
        # For now, we provide a generic macro context prompt to the LLM.
        system_prompt = (
            "You are a seasoned Macroeconomist. You evaluate systemic risk "
            "and liquidity conditions. Provide a brief 2-sentence macro analysis "
            "for the crypto market."
        )
        prompt = f"Assess the current macroeconomic risk for trading {symbol}."
        
        response = await self._query_llm(prompt, system_prompt)
        if response:
            return response
            
        return "MACRO_SAFE_FALLBACK: Macro conditions appear neutral. No immediate systemic risk detected."


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
        if not asset:
            return f"SENTIMENT_FALLBACK: No news available for {symbol}."
            
        news = self.db.query(AssetNews).filter(
            AssetNews.asset_id == asset.id
        ).order_by(desc(AssetNews.published_at)).limit(5).all()
        
        if not news:
            return f"SENTIMENT_FALLBACK: No recent news found for {symbol}."
            
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
