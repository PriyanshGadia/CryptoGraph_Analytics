"""AI explanation routes using Groq LLM with fallback."""
from fastapi import APIRouter, Depends
from groq import Groq
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.database import get_db
from app.db.models_sqla import Asset, Prediction, AppSetting, AssetNews
from app.db.models import ExplainResponse
from app.core.security import decrypt_secret

router = APIRouter(prefix="/explain", tags=["explain"])

def generate_fallback_explanation(symbol: str, direction: str, confidence: float, shap_values: dict) -> str:
    """Rule-based explanation when API key is missing."""
    if not shap_values:
        return f"The model predicts {symbol} will go {direction} with {confidence:.1f}% confidence based on quantitative analysis."
        
    top_feature = max(shap_values, key=shap_values.get) if shap_values else "recent price action"
    return (
        f"The ST-GCN model predicts {symbol} will move {direction} ({confidence:.1f}% confidence). "
        f"This is primarily driven by '{top_feature}', which showed the strongest signal in recent trading data. "
        f"Secondary factors include the broader market regime and technical patterns."
    )

@router.get("/{symbol}", response_model=ExplainResponse)
def explain_prediction(symbol: str, db: Session = Depends(get_db)):
    """
    Returns AI-generated explanation for latest prediction using Groq LLaMA,
    with a graceful fallback to rule-based templates if the key is missing.
    """
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        return ExplainResponse(symbol=symbol, explanation="Asset not found.", direction="unknown", confidence=0.0, top_features={})
        
    pred = db.query(Prediction).filter(Prediction.asset_id == asset.id).order_by(desc(Prediction.predicted_at)).first()
    
    if not pred:
        return ExplainResponse(symbol=symbol, explanation="No predictions available.", direction="unknown", confidence=0.0, top_features={})
        
    direction = pred.direction or "unknown"
    confidence = pred.confidence or 0.0
    shap_values = pred.shap_values or {}
    
    # Fetch recent news
    news_records = db.query(AssetNews).filter(AssetNews.asset_id == asset.id).order_by(desc(AssetNews.published_at)).limit(3).all()
    news_headlines = []
    news_sources = []
    for record in news_records:
        news_headlines.append(f"[{record.source}] {record.headline}")
        if record.source and record.source not in news_sources:
            news_sources.append(record.source)
    
    groq_key_record = db.query(AppSetting).filter(AppSetting.setting_key == "groq_api_key").first()
    groq_api_key = decrypt_secret(groq_key_record.setting_value) if groq_key_record else None

    if not groq_api_key:
        explanation = generate_fallback_explanation(symbol, direction, confidence, shap_values)
    else:
        if shap_values:
            shap_str = "\n".join([f"- {k}: {v:.4f}" for k, v in shap_values.items()])
            
            news_str = ""
            if news_headlines:
                news_str = "\nRecent news for this asset includes:\n" + "\n".join([f"- {h}" for h in news_headlines]) + "\nSynthesize the quantitative signal with the qualitative news."
                
            prompt = f"""You are a crypto market analyst. The ST-GCN model predicts {symbol} will go {direction} with {confidence:.1f}% confidence over the next 24 hours.
The top contributing factors from the model are:
{shap_str}
{news_str}
Explain in exactly 3-4 sentences why the model made this prediction in plain language for a non-technical investor. Be specific about which features matter most and what they signal about market conditions."""
        else:
            prompt = f"The model predicts {symbol} will go {direction} with {confidence:.1f}% confidence based on recent price action and market conditions. Explain in 2-3 sentences what this means for a non-technical investor."

        try:
            client = Groq(api_key=groq_api_key)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            explanation = completion.choices[0].message.content
        except Exception as e:
            explanation = f"Failed to generate explanation (API Error): {str(e)}. Fallback: " + generate_fallback_explanation(symbol, direction, confidence, shap_values)
            
    return ExplainResponse(
        symbol=symbol,
        explanation=explanation,
        direction=direction,
        confidence=confidence,
        top_features=shap_values,
        news_sources=news_sources
    )
