"""Base class for Autonomous AI Swarm Agents."""
import asyncio
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.db.models_sqla import AppSetting
from app.core.security import decrypt_secret

class BaseAgent:
    """Base class for all AI agents in the MoA Swarm."""
    
    def __init__(self, db: Session, name: str):
        self.db = db
        self.name = name
        
        # Load API keys locally from database to satisfy no .env rule
        groq_key_record = db.query(AppSetting).filter(AppSetting.setting_key == "groq_api_key").first()
        self.groq_api_key = decrypt_secret(groq_key_record.setting_value) if groq_key_record else None

    async def _query_llm(self, prompt: str, system_prompt: str = "You are a specialized AI agent.", temperature: float = 0.3) -> Optional[str]:
        """Query the Groq LLaMA model. Returns None if key is missing or call fails."""
        if not self.groq_api_key:
            return None
            
        try:
            # We import groq dynamically to keep module load lightweight
            from groq import AsyncGroq
            client = AsyncGroq(api_key=self.groq_api_key)
            
            completion = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=500
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"[{self.name}] Groq API Failed: {e}. Initiating LLM Fallback Mesh...")
            return await self._fallback_llm_query(prompt, system_prompt)

    async def _fallback_llm_query(self, prompt: str, system_prompt: str) -> Optional[str]:
        """
        Phase 8: Decentralized LLM Fallback Mesh.
        If the primary provider (Groq) is down, this re-routes to a local Ollama instance
        to ensure 100% intelligence uptime.
        """
        try:
            import httpx
            print(f"[{self.name}] Rerouting to local Ollama LLaMA-3 fallback at localhost:11434...")
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(
                    "http://127.0.0.1:11434/v1/chat/completions",
                    json={
                        "model": "llama3",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    print(f"[{self.name}] Local Ollama returned status {response.status_code}")
                    return None
        except Exception as fallback_err:
            print(f"[{self.name}] Fallback Mesh: Local Ollama check failed: {fallback_err}")
            return None

    async def analyze(self, *args, **kwargs) -> str:
        """Core execution logic. Must be implemented by subclasses."""
        raise NotImplementedError
