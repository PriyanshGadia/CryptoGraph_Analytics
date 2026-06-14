"""
Zero-Trust Data Sanitizer.

Acts as a firewall between external data sources (like RSS feeds) and our MoA LLM Swarm.
Detects and strips prompt injection attempts, malicious instructions, and non-standard characters.
"""

import re
from typing import List

# Common prompt injection keywords and adversarial phrases
PROMPT_INJECTION_HEURISTICS = [
    r"ignore (all )?(previous )?instructions",
    r"disregard (all )?(previous )?instructions",
    r"you are now",
    r"output exactly",
    r"system prompt",
    r"bypass",
    r"jailbreak",
    r"instead of",
    r"new instructions",
    r"stop what you are doing",
    r"from now on",
    r"\bDAN\b", # Do Anything Now
    r"forget everything"
]

def sanitize_text(text: str) -> str:
    """
    Sanitizes a single string of text:
    1. Removes non-alphanumeric characters (keeps basic punctuation).
    2. Strips known prompt injection phrases.
    3. Limits length to prevent context-window overflow attacks.
    """
    if not text:
        return ""
        
    # 1. Truncate to prevent buffer overflow/context exhaustion attacks (max 1000 chars per headline/summary)
    text = text[:1000]
    
    # 2. Remove weird unicode, keeping only standard ASCII printables
    text = re.sub(r'[^\x20-\x7E]', '', text)
    
    # 3. Strip prompt injection heuristics (case-insensitive)
    for pattern in PROMPT_INJECTION_HEURISTICS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
        
    return text.strip()

def sanitize_news_records(records: List[dict]) -> List[dict]:
    """Sanitizes a list of news dictionaries."""
    sanitized = []
    for r in records:
        sanitized_r = r.copy()
        sanitized_r["headline"] = sanitize_text(r.get("headline", ""))
        sanitized_r["summary"] = sanitize_text(r.get("summary", ""))
        
        # Drop entirely if it's completely redacted (high likelihood of being pure attack vector)
        if "[REDACTED]" in sanitized_r["headline"] and len(sanitized_r["headline"]) < 20:
            continue
            
        sanitized.append(sanitized_r)
    return sanitized
