"""AI explanation routes using Groq LLM."""
from fastapi import APIRouter, Depends
from groq import Groq
from app.api.deps import get_supabase
from app.core.config import settings
from app.db.models import ExplainResponse

router = APIRouter(prefix="/explain", tags=["explain"])

@router.get("/{symbol}", response_model=ExplainResponse)
async def explain_prediction(symbol: str, db=Depends(get_supabase)):
    """
    Returns AI-generated explanation for latest prediction using Groq LLaMA.
    """
    # 1. Query latest predictions
    asset_res = db.table("assets").select("id").eq("symbol", symbol).execute()
    if not asset_res.data:
        return ExplainResponse(symbol=symbol, explanation="Asset not found.", direction="unknown", confidence=0.0, top_features={})
        
    asset_id = asset_res.data[0]['id']
    pred_res = db.table("predictions").select("*").eq("asset_id", asset_id).order("predicted_at", desc=True).limit(1).execute()
    
    if not pred_res.data:
        return ExplainResponse(symbol=symbol, explanation="No predictions available.", direction="unknown", confidence=0.0, top_features={})
        
    pred = pred_res.data[0]
    direction = pred.get("direction", "unknown")
    confidence = pred.get("confidence", 0.0)
    shap_values = pred.get("shap_values")
    
    if shap_values:
        # Format SHAP features
        shap_str = "\n".join([f"- {k}: {v:.4f}" for k, v in shap_values.items()])
        prompt = f"""You are a crypto market analyst. The ST-GCN model predicts {symbol} will go {direction} with {confidence:.1f}% confidence over the next 24 hours.
The top contributing factors from the model are:
{shap_str}

Explain in exactly 3-4 sentences why the model made this prediction in plain language for a non-technical investor. Be specific about which features matter most and what they signal about market conditions."""
    else:
        # No SHAP data – generate a generic explanation
        shap_values = {}
        prompt = f"The model predicts {symbol} will go {direction} with {confidence:.1f}% confidence based on recent price action and market conditions. Explain in 2-3 sentences what this means for a non-technical investor."

    # 5. Call Groq
    try:
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300
        )
        explanation = completion.choices[0].message.content
    except Exception as e:
        explanation = f"Failed to generate explanation: {str(e)}"
        
    return ExplainResponse(
        symbol=symbol,
        explanation=explanation,
        direction=direction,
        confidence=confidence,
        top_features=shap_values
    )
