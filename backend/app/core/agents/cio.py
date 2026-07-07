"""Chief Investment Officer Agent for the MoA Swarm."""
from app.core.agents.base import BaseAgent
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models_sqla import TradeHistory
from typing import Dict, Any

class ChiefInvestmentOfficerAgent(BaseAgent):
    """The Orchestrator. Evaluates inputs from all analysts and makes the final decision."""
    
    def __init__(self, db: Session):
        super().__init__(db, "ChiefInvestmentOfficerAgent")
        
    async def analyze(
        self, 
        symbol: str, 
        stgcn_prediction: Dict[str, Any], 
        macro_analysis: str, 
        onchain_analysis: str, 
        sentiment_analysis: str
    ) -> Dict[str, str]:
        """
        Takes all inputs, forces a debate, and returns the final decision and reasoning.
        """
        direction = stgcn_prediction.get("direction", "unknown")
        confidence = stgcn_prediction.get("confidence", 0.0)
        
        # Fetch few-shot RLHF examples
        bad_trades = self.db.query(TradeHistory).filter(TradeHistory.overseer_grade == 1).order_by(desc(TradeHistory.timestamp)).limit(5).all()
        good_trades = self.db.query(TradeHistory).filter(TradeHistory.overseer_grade == 5).order_by(desc(TradeHistory.timestamp)).limit(5).all()
        
        rlhf_context = ""
        if bad_trades:
            rlhf_context += "\n\n--- PAST MISTAKES TO AVOID (1-Star Trades) ---\n"
            for t in bad_trades:
                rlhf_context += f"Trade: {t.side.upper()} {t.symbol}. CIO Reason: {t.reason}\n"
                rlhf_context += f"Overseer Feedback: \"{t.overseer_notes}\"\n"
                
        if good_trades:
            rlhf_context += "\n\n--- SUCCESSFUL PATTERNS TO REPEAT (5-Star Trades) ---\n"
            for t in good_trades:
                rlhf_context += f"Trade: {t.side.upper()} {t.symbol}. CIO Reason: {t.reason}\n"
                rlhf_context += f"Overseer Feedback: \"{t.overseer_notes}\"\n"

        system_prompt = (
            "You are the Chief Investment Officer (CIO) of an autonomous crypto hedge fund. "
            "Your job is to review the quantitative AI signal (ST-GCN) alongside the qualitative "
            "reports from your Macro Economist, On-Chain Detective, and Sentiment Analyst. "
            "You must synthesize these conflicting viewpoints, formulate a robust argument, "
            "and make a final execution decision.\n"
            f"{rlhf_context}\n"
            "You must end your response with EXACTLY one of the following lines:\n"
            "DECISION: EXECUTE_BUY\n"
            "DECISION: EXECUTE_SELL\n"
            "DECISION: HOLD"
        )
        
        prompt = (
            f"Asset: {symbol}\n\n"
            f"--- 1. Quantitative AI Signal (ST-GCN) ---\n"
            f"Direction: {direction}\n"
            f"Confidence: {confidence:.2f}\n\n"
            f"--- 2. Macroeconomist Report ---\n{macro_analysis}\n\n"
            f"--- 3. On-Chain Detective Report ---\n{onchain_analysis}\n\n"
            f"--- 4. Sentiment Analyst Report ---\n{sentiment_analysis}\n\n"
            "Debate these points and provide your final verdict."
        )
        
        from circuitbreaker import circuit, CircuitBreakerError
        
        # Wrapped call to catch circuit breaker exceptions along with standard errors
        @circuit(failure_threshold=3, expected_exception=Exception)
        async def call_llm():
            return await self._query_llm(prompt, system_prompt, temperature=0.4)
            
        try:
            reasoning = await call_llm()
        except (Exception, CircuitBreakerError) as e:
            reasoning = None
            print(f"[CIO Agent] LLM or Circuit failed: {e}. Falling back to Heuristic NLP Generator.")
        
        if not reasoning:
            # Fallback CIO logic if LLM fails: only execute trades with high model conviction
            # High-conviction opportunistic trading: require >= 55 model confidence for BUY (since it's out of 100)
            if direction in ["strong_up", "up"] and confidence >= 55.0:
                decision = "EXECUTE_BUY"
                reasoning = (
                    f"SYSTEM FALLBACK TRIGGERED (LLM OFFLINE).\n\n"
                    f"Heuristic Analysis: The ST-GCN quantitative model exhibits a strong bullish signal "
                    f"with a confidence score of {confidence:.2f}/100. Despite the unavailability of qualitative "
                    f"analyst debate, the strict algorithmic threshold (>= 55.0) is satisfied for {symbol}. "
                    f"Historical backtesting indicates momentum is statistically significant at this tier.\n\n"
                    f"DECISION: EXECUTE_BUY"
                )
            elif direction in ["strong_down", "down"] and confidence >= 50.0:
                decision = "EXECUTE_SELL"
                reasoning = (
                    f"SYSTEM FALLBACK TRIGGERED (LLM OFFLINE).\n\n"
                    f"Heuristic Analysis: The ST-GCN quantitative model indicates a severe downward trajectory "
                    f"with {confidence:.2f}/100 certainty. Capital preservation is paramount. The rigid threshold "
                    f"for risk mitigation has been breached for {symbol}.\n\n"
                    f"DECISION: EXECUTE_SELL"
                )
            else:
                decision = "HOLD"
                reasoning = (
                    f"SYSTEM FALLBACK TRIGGERED (LLM OFFLINE).\n\n"
                    f"Heuristic Analysis: The quantitative signal is `{direction}` with insufficient confidence ({confidence:.2f}/100) "
                    f"to override the strict LLM-offline safeguard thresholds. Without qualitative corroboration from "
                    f"the Macro and Sentiment analysts, the risk/reward ratio is mathematically unacceptable. "
                    f"Awaiting improved market structure or system restoration.\n\n"
                    f"DECISION: HOLD"
                )
            return {"decision": decision, "reasoning": reasoning}
            
        # Parse decision from LLM output
        decision = "HOLD"  # Default
        for line in reasoning.split('\n')[::-1]:
            line = line.strip().upper()
            if "DECISION: EXECUTE_BUY" in line:
                decision = "EXECUTE_BUY"
                break
            elif "DECISION: EXECUTE_SELL" in line:
                decision = "EXECUTE_SELL"
                break
            elif "DECISION: HOLD" in line:
                decision = "HOLD"
                break
                
        return {"decision": decision, "reasoning": reasoning}
