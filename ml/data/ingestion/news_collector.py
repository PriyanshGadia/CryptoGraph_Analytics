"""
News Collector for ST-GCN RAG Explainability.
Fetches recent crypto news via Google News RSS to provide context for LLM explanations.
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict
import re
from sqlalchemy.orm import Session
from backend.app.db.database import SessionLocal
from backend.app.db.models_sqla import Asset, AssetNews
from backend.app.core.data_sanitizer import sanitize_news_records

def fetch_crypto_news_rss(symbol: str, asset_name: str, limit: int = 3) -> List[Dict[str, str]]:
    """
    Fetches the latest news for a specific crypto asset using Google News RSS.
    Returns a list of dictionaries with headline, source, and published_at.
    """
    # Clean up asset name for search
    query = f"{asset_name} OR {symbol} crypto"
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    news_items = []
    
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        
        if channel is None:
            return []
            
        for item in channel.findall("item")[:limit]:
            title = item.findtext("title") or ""
            # Google news titles often end with " - Source Name", let's separate it
            match = re.search(r'(.*)\s+-\s+(.*)$', title)
            if match:
                headline = match.group(1).strip()
                source = match.group(2).strip()
            else:
                headline = title
                source = item.findtext("source") or "Google News"
                
            pubDate_str = item.findtext("pubDate")
            
            try:
                # pubDate format: Tue, 13 Jun 2026 12:00:00 GMT
                pubDate = datetime.strptime(pubDate_str, "%a, %d %b %Y %H:%M:%S %Z")
                pubDate = pubDate.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pubDate = datetime.now(timezone.utc)
                
            news_items.append({
                "headline": headline,
                "source": source,
                "published_at": pubDate
            })
            
    except Exception as e:
        print(f"[NewsCollector] Failed to fetch RSS for {symbol}: {e}")
        
    return news_items

def collect_news_for_all_assets():
    """
    Iterates through all assets in the DB and updates their recent news.
    """
    db: Session = SessionLocal()
    try:
        assets = db.query(Asset).all()
        print(f"[NewsCollector] Starting news collection for {len(assets)} assets...")
        
        total_news = 0
        for asset in assets:
            print(f"Fetching news for {asset.symbol} ({asset.name})...")
            # Fetch top 5 to have a good variety
            raw_news_items = fetch_crypto_news_rss(asset.symbol, asset.name, limit=5)
            
            # Apply Zero-Trust LLM Firewall to strip prompt injections
            news_items = sanitize_news_records(raw_news_items)
            
            # Avoid inserting duplicates by checking recent headlines
            existing_news = db.query(AssetNews.headline).filter(
                AssetNews.asset_id == asset.id
            ).all()
            existing_headlines = {n[0] for n in existing_news}
            
            new_inserts = 0
            for item in news_items:
                if item["headline"] not in existing_headlines:
                    db.add(AssetNews(
                        asset_id=asset.id,
                        headline=item["headline"],
                        source=item["source"],
                        published_at=item["published_at"]
                    ))
                    existing_headlines.add(item["headline"])
                    new_inserts += 1
                    total_news += 1
                    
            if new_inserts > 0:
                db.commit()
                
            # Optionally, clean up old news (keep only last 10 per asset)
            all_asset_news = db.query(AssetNews).filter(AssetNews.asset_id == asset.id).order_by(AssetNews.published_at.desc()).all()
            if len(all_asset_news) > 10:
                for old_news in all_asset_news[10:]:
                    db.delete(old_news)
                db.commit()
                
        print(f"[NewsCollector] Finished. Inserted {total_news} new headlines.")
    finally:
        db.close()

if __name__ == "__main__":
    collect_news_for_all_assets()
