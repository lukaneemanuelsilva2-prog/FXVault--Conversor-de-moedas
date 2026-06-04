import time
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="FXVault API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache: dict = {}

def cache_get(key: str, ttl: int = 60):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < ttl:
        return entry["data"]
    return None

def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


@app.get("/api/rates/{base}")
async def get_fiat_rates(base: str = "USD"):
    base = base.upper()
    cached = cache_get(f"rates_{base}")
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"https://open.er-api.com/v6/latest/{base}")
            r.raise_for_status()
            data = r.json()
            rates = data.get("rates", {})

            # Moedas africanas não cobertas pela API — taxas aproximadas vs USD
            extra = {
                "AOA": 910.0,   # Kwanza angolano
                "CDF": 2800.0,  # Franco congolês
                "ZMW": 26.5,    # Kwacha zambiano
                "MZN": 63.8,    # Metical moçambicano
                "NAD": 18.6,    # Dólar namibiano
                "BWP": 13.7,    # Pula botswaniana
                "RWF": 1320.0,  # Franco ruandês
                "UGX": 3750.0,  # Xelim ugandês
                "MUR": 45.2,    # Rúpia mauriciana
                "SCR": 13.9,    # Rúpia seichelense
                "LSL": 18.6,    # Loti lesotiano
                "SZL": 18.6,    # Lilangeni suazi
            }

            if base != "USD" and base in rates:
                usd_to_base = rates[base]
                for sym, usd_rate in extra.items():
                    if sym not in rates:
                        rates[sym] = round(usd_rate * usd_to_base, 4)
            else:
                for sym, usd_rate in extra.items():
                    if sym not in rates:
                        rates[sym] = usd_rate

            result = {
                "base": base,
                "rates": rates,
                "updated": data.get("time_last_update_utc", ""),
                "source": "open.er-api.com"
            }
            cache_set(f"rates_{base}", result)
            return result
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Erro ao buscar taxas: {e}")


@app.get("/api/crypto")
async def get_crypto_rates():
    cached = cache_get("crypto", ttl=60)
    if cached:
        return cached
    ids = "bitcoin,ethereum,binancecoin,ripple,solana,cardano,avalanche-2,dogecoin,polkadot,chainlink,uniswap,litecoin,bitcoin-cash,matic-network,cosmos,stellar,algorand,filecoin,vechain,near"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}
            )
            r.raise_for_status()
            raw = r.json()
            symbol_map = {
                "bitcoin":"BTC","ethereum":"ETH","binancecoin":"BNB","ripple":"XRP",
                "solana":"SOL","cardano":"ADA","avalanche-2":"AVAX","dogecoin":"DOGE",
                "polkadot":"DOT","chainlink":"LINK","uniswap":"UNI","litecoin":"LTC",
                "bitcoin-cash":"BCH","matic-network":"MATIC","cosmos":"ATOM",
                "stellar":"XLM","algorand":"ALGO","filecoin":"FIL","vechain":"VET","near":"NEAR"
            }
            result = {}
            for coin_id, sym in symbol_map.items():
                if coin_id in raw:
                    result[sym] = {
                        "usd": raw[coin_id].get("usd", 0),
                        "change_24h": raw[coin_id].get("usd_24h_change", 0)
                    }
            out = {"crypto": result, "source": "coingecko.com"}
            cache_set("crypto", out)
            return out
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Erro ao buscar criptos: {e}")


@app.get("/api/history")
async def get_history(from_cur: str = "USD", to_cur: str = "BRL", days: int = 30):
    from_cur = from_cur.upper()
    to_cur   = to_cur.upper()
    key = f"hist_{from_cur}_{to_cur}_{days}"
    cached = cache_get(key, ttl=3600)
    if cached:
        return cached
    from datetime import datetime, timedelta
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(
                f"https://api.frankfurter.app/{start}..{end}",
                params={"from": from_cur, "to": to_cur}
            )
            r.raise_for_status()
            data = r.json()
            rates_series = {
                date: vals.get(to_cur)
                for date, vals in data.get("rates", {}).items()
                if vals.get(to_cur)
            }
            result = {"from": from_cur, "to": to_cur, "series": rates_series}
            cache_set(key, result)
            return result
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Histórico indisponível: {e}")


@app.get("/api/status")
async def status():
    return {"status": "online", "cache_keys": len(_cache)}


app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("../frontend/index.html")


    #127.0.0.1
#127.0.0.1:8000

#python backend.py
#py backend.py