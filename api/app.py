"""FastAPI app for HKJC quinella prediction system."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from service import PredictionService

service = PredictionService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.load()
    logger.info("Prediction service started")
    yield


app = FastAPI(title="HKJC Quinella Prediction API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "models": service.model_info(),
        "features_loaded": service.features_df is not None,
        "bets_loaded": service.bets_detail is not None,
    }


@app.get("/dates")
def list_dates():
    return {"dates": service.list_dates()}


@app.get("/races")
def list_races(date: str = Query(..., description="YYYY-MM-DD")):
    races = service.list_races(date)
    if not races:
        raise HTTPException(status_code=404, detail="no races for date")
    return {"races": races}


@app.get("/predict")
def predict(date: str, venue: str = "ST", race_no: int = 1):
    result = service.predict_race(date, venue, race_no)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/live/races")
def live_races(date: str = Query(..., description="YYYY-MM-DD")):
    races = service.list_live_races(date)
    return {"races": races}


@app.get("/live/predict")
def live_predict(date: str, venue: str = "ST", race_no: int = 1):
    result = service.live_predict(date, venue, race_no)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/live/status")
def live_status():
    return {
        "mode": "synthetic" if service.LIVE_SOURCE_DATE else "live",
        "source_date": service.LIVE_SOURCE_DATE,
        "season_note": "HK off-season (Jul-Sep). Synthetic race cards until Sept season start.",
    }


@app.get("/backtest/summary")
def backtest_summary():
    return service.backtest_summary()


@app.get("/backtest/bets")
def backtest_bets(
    result: str = Query("all"),
    venue: str = Query("all"),
    search: str = Query(None),
    min_div: float = Query(None),
    limit: int = Query(500, le=5000),
    offset: int = Query(0),
):
    return service.backtest_bets(result, venue, search, min_div, limit, offset)


@app.get("/models/importance")
def feature_importance(model: str = Query("top2")):
    return {"model": model, "features": service.feature_importance(model)}


@app.get("/models/info")
def model_info():
    return service.model_info()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
