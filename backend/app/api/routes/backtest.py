from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
import re
from datetime import datetime
from typing import Optional
from app.api.deps import get_db
from sqlalchemy.orm import Session
from app.services.backtest_engine import run_asset_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])

class BacktestRequest(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=10)
    start_date: str = Field(..., min_length=10, max_length=10)
    end_date: str = Field(..., min_length=10, max_length=10)
    model_version: Optional[str] = Field("stgcn-v1.0", max_length=30)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("Symbol must be alphanumeric URL-safe.")
        return v.upper()

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format.")
        return v

@router.post("")
async def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """Run a backtest on a specific asset over a specific time range to calculate simulated performance."""
    res = run_asset_backtest(
        db=db,
        symbol=req.symbol,
        start_date=req.start_date,
        end_date=req.end_date,
        model_version=req.model_version or "stgcn-v1.0"
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

