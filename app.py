from __future__ import annotations

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

# ── Constants ─────────────────────────────────────────────────────────────────

CNN_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://edition.cnn.com/",
    "Accept": "application/json",
}

US_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "나스닥",
    "^DJI": "다우존스",
    "^VIX": "VIX",
    "^RUT": "러셀 2000",
}

SECTOR_ETFS = {
    "XLE": "에너지",
    "XLK": "기술",
    "XLV": "헬스케어",
    "XLF": "금융",
    "XLI": "산업",
    "XLU": "유틸리티",
    "XLRE": "부동산",
    "XLP": "필수소비재",
    "XLY": "임의소비재",
    "XLB": "소재",
    "XLC": "통신",
}

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "JPM", "XOM", "GLD"]

TICKER_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
    "META": "Meta",
    "GOOGL": "Alphabet (Google)",
    "JPM": "JP Morgan",
    "XOM": "ExxonMobil",
    "GLD": "금 ETF",
    **{k: f"{v} ETF" for k, v in SECTOR_ETFS.items()},
}

# 한국 시총 상위 10 — fdr.StockListing 실패 시 fallback
KOSPI_FALLBACK = [
    {"코드": "005930", "종목명": "삼성전자"},
    {"코드": "000660", "종목명": "SK하이닉스"},
    {"코드": "373220", "종목명": "LG에너지솔루션"},
    {"코드": "207940", "종목명": "삼성바이오로직스"},
    {"코드": "005380", "종목명": "현대차"},
    {"코드": "000270", "종목명": "기아"},
    {"코드": "068270", "종목명": "셀트리온"},
    {"코드": "105560", "종목명": "KB금융"},
    {"코드": "055550", "종목명": "신한지주"},
    {"코드": "028260", "종목명": "삼성물산"},
]

PHASE_COLORS = {
    "강세": "#00C851",
    "경계": "#FFD700",
    "조정": "#FF8800",
    "공포": "#FF3547",
}

PHASE_SUMMARIES = {
    "강세": "전반적 강세장. 성장주 및 경기민감 섹터 비중 확대가 유효합니다.",
    "경계": "시장 불안 신호 감지. 방어 섹터 비중 확대 및 리스크 관리를 권장합니다.",
    "조정": "조정 국면 진입. 안전자산(금, 헬스케어) 선호 전략을 권장합니다.",
    "공포": "극도의 공포 국면. 현금 확보 및 방어적 자산 집중을 권장합니다.",
}

PHASE_SECTORS = {
    "강세": {"buy": ["XLK", "XLY", "XLI"],    "sell": ["XLU", "XLP", "XLRE"]},
    "경계": {"buy": ["XLV", "XLP", "XLU"],    "sell": ["XLK", "XLY"]},
    "조정": {"buy": ["XLV", "XLP", "GLD"],    "sell": ["XLK", "XLY", "XLI"]},
    "공포": {"buy": ["XLU", "XLP", "GLD"],    "sell": ["XLK", "XLY", "XLF"]},
}

FG_INDICATOR_NAMES = {
    "market_momentum_sp500": "시장 모멘텀 (S&P500 vs 125MA)",
    "stock_price_strength":  "주가 강도 (52주 신고/저가)",
    "stock_price_breadth":   "주가 폭 (McClellan Oscillator)",
    "put_call_options":      "풋/콜 비율",
    "market_volatility_vix": "시장 변동성 (VIX)",
    "junk_bond_demand":      "정크본드 수요",
    "safe_haven_demand":     "안전자산 수요",
}

FG_RATING_KR = {
    "Extreme Fear": "극도의 공포",
    "Fear": "공포",
    "Neutral": "중립",
    "Greed": "탐욕",
    "Extreme Greed": "극도의 탐욕",
}

# ── Data Fetchers ──────────────────────────────────────────────────────────────


@st.cache_data(ttl=3600)
def fetch_fear_greed() -> dict | None:
    try:
        r = requests.get(CNN_FG_URL, headers=CNN_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        fg = data.get("fear_and_greed", {})

        indicators: dict[str, dict] = {}
        for key in FG_INDICATOR_NAMES:
            raw = data.get(key, {})
            if raw:
                indicators[key] = {
                    "score": round(float(raw.get("score", 0)), 1),
                    "rating": raw.get("rating", ""),
                }

        return {
            "score": round(float(fg.get("score", 0)), 1),
            "rating": fg.get("rating", ""),
            "prev_1w": round(float(fg.get("previous_1_week", 0)), 1),
            "prev_1m": round(float(fg.get("previous_1_month", 0)), 1),
            "prev_1y": round(float(fg.get("previous_1_year", 0)), 1),
            "indicators": indicators,
        }
    except Exception as e:
        st.warning(f"공포탐욕지수 로드 실패: {e}")
        return None


@st.cache_data(ttl=900)
def fetch_macro_data() -> dict:
    result: dict[str, float] = {}
    tickers_map = {"^VIX": "vix", "^TNX": "y10", "^IRX": "y2", "DX-Y.NYB": "dxy"}
    try:
        raw = yf.download(
            list(tickers_map.keys()),
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        close = raw["Close"] if isinstance(raw["Close"], pd.DataFrame) else raw[["Close"]]
        for ticker, key in tickers_map.items():
            if ticker in close.columns:
                result[key] = float(close[ticker].dropna().iloc[-1])
        if "y10" in result and "y2" in result:
            result["yield_spread"] = round(result["y10"] - result["y2"], 3)
    except Exception as e:
        st.warning(f"매크로 데이터 로드 실패: {e}")
    return result


@st.cache_data(ttl=300)
def fetch_sp500_ma() -> dict:
    try:
        hist = yf.Ticker("^GSPC").history(period="1y", interval="1d", auto_adjust=True)
        price = float(hist["Close"].iloc[-1])
        ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        return {
            "price": price,
            "ma200": ma200,
            "gap_pct": round((price - ma200) / ma200 * 100, 2),
            "above": price > ma200,
        }
    except Exception:
        return {}


@st.cache_data(ttl=300)
def fetch_sp500_returns() -> dict[str, float]:
    """S&P500의 1개월/3개월/12개월 수익률 — 상대강도 계산 벤치마크."""
    try:
        hist = yf.Ticker("^GSPC").history(period="1y", interval="1d", auto_adjust=True)
        c = hist["Close"]
        price = float(c.iloc[-1])
        return {
            "1m":  round((price / float(c.iloc[-22]) - 1) * 100, 2) if len(c) >= 22 else 0.0,
            "3m":  round((price / float(c.iloc[-63]) - 1) * 100, 2) if len(c) >= 63 else 0.0,
            "12m": round((price / float(c.iloc[0])   - 1) * 100, 2),
        }
    except Exception:
        return {"1m": 0.0, "3m": 0.0, "12m": 0.0}


@st.cache_data(ttl=60)
def fetch_us_indices() -> tuple[pd.DataFrame, str]:
    """지수 현재가: 분봉 최신가(15분 지연). 등락률은 전일 종가 대비."""
    tickers = list(US_INDICES.keys())
    price_ts = ""
    try:
        # 등락률용 전일 종가
        daily = yf.download(tickers, period="5d", interval="1d",
                            auto_adjust=True, progress=False)
        daily_close = daily["Close"]
        prev_close = daily_close.iloc[-2]

        # 분봉 최신가
        rt = fetch_realtime_prices(tuple(tickers))
        if rt:
            sample_ts = next(iter(rt.values()))["ts"]
            price_ts = pd.Timestamp(sample_ts).tz_convert("America/New_York").strftime("%H:%M ET")

        rows = []
        for t in tickers:
            prv = float(prev_close[t]) if t in prev_close else float("nan")
            # 분봉 현재가 우선, 없으면 일봉 최신가
            if t in rt:
                cur = rt[t]["price"]
            else:
                cur = float(daily_close.iloc[-1][t]) if t in daily_close.columns else float("nan")
            chg = (cur - prv) / prv * 100 if prv else float("nan")
            rows.append({"지수": US_INDICES[t], "현재가": f"{cur:,.2f}", "등락률(%)": round(chg, 2)})
        return pd.DataFrame(rows), price_ts
    except Exception:
        return pd.DataFrame(), ""


@st.cache_data(ttl=300)
def fetch_sector_performance() -> pd.DataFrame:
    tickers = list(SECTOR_ETFS.keys())
    try:
        raw = yf.download(
            tickers, period="1mo", interval="1d",
            auto_adjust=True, progress=False,
        )
        close = raw["Close"]
        p1d = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
        p1m = (close.iloc[-1] - close.iloc[0])  / close.iloc[0]  * 100
        return pd.DataFrame({
            "ETF":      tickers,
            "섹터":     list(SECTOR_ETFS.values()),
            "1일(%)":   [round(float(p1d[t]), 2) for t in tickers],
            "1개월(%)": [round(float(p1m[t]), 2) for t in tickers],
        })
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_technical_signals(tickers: tuple[str, ...]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=True)
            if len(hist) < 52:
                continue
            close      = hist["Close"]
            rsi_series = RSIIndicator(close=close, window=14).rsi()
            rsi_val    = float(rsi_series.iloc[-1])
            rsi_5d_ago = float(rsi_series.iloc[-6]) if len(rsi_series) >= 6 else rsi_val
            rsi_delta  = round(rsi_val - rsi_5d_ago, 1)
            rsi_trend  = f"↑+{rsi_delta}" if rsi_delta > 0 else f"↓{rsi_delta}"
            sma50   = float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1])
            sma200  = float(SMAIndicator(close=close, window=200).sma_indicator().iloc[-1])
            price   = float(close.iloc[-1])

            # MACD
            macd_obj  = MACD(close=close)
            macd_line = float(macd_obj.macd().iloc[-1])
            macd_sig  = float(macd_obj.macd_signal().iloc[-1])

            # Bollinger Bands (20, 2σ)
            bb        = BollingerBands(close=close, window=20, window_dev=2)
            bb_low    = float(bb.bollinger_lband().iloc[-1])
            bb_high   = float(bb.bollinger_hband().iloc[-1])

            buy_cnt = sell_cnt = 0
            signals = []

            # RSI
            if rsi_val < 30:
                signals.append("RSI 과매도")
                buy_cnt += 1
            elif rsi_val > 70:
                signals.append("RSI 과매수")
                sell_cnt += 1

            # SMA50
            if price > sma50:
                signals.append("SMA50 위")
                buy_cnt += 1
            else:
                signals.append("SMA50 아래")
                sell_cnt += 1

            # SMA200
            if price > sma200:
                signals.append("SMA200 위")
                buy_cnt += 1
            else:
                signals.append("SMA200 아래")
                sell_cnt += 1

            # MACD 골든/데드크로스
            if macd_line > macd_sig:
                signals.append("MACD 골든크로스")
                buy_cnt += 1
            else:
                signals.append("MACD 데드크로스")
                sell_cnt += 1

            # 볼린저밴드 이탈 (중간 구간은 신호 없음)
            if price < bb_low:
                signals.append("BB 하단 이탈")
                buy_cnt += 1
            elif price > bb_high:
                signals.append("BB 상단 이탈")
                sell_cnt += 1

            # 모멘텀 수익률 (이미 받은 hist 활용)
            ret_1m  = round((price / float(close.iloc[-22]) - 1) * 100, 2) if len(close) >= 22 else float("nan")
            ret_3m  = round((price / float(close.iloc[-63]) - 1) * 100, 2) if len(close) >= 63 else float("nan")
            ret_12m = round((price / float(close.iloc[0])   - 1) * 100, 2)

            # 종목명 조회 (섹터 ETF 또는 워치리스트)
            base = ticker.replace(".KS", "")
            name = TICKER_NAMES.get(base, base)

            rows.append({
                "티커":        ticker.replace(".KS", ""),
                "종목명":      name,
                "현재가":      round(price, 2),
                "RSI(14)":     round(rsi_val, 1),
                "RSI추세(5일)": rsi_trend,
                "1개월(%)":    ret_1m,
                "3개월(%)":    ret_3m,
                "12개월(%)":   ret_12m,
                "매수신호":    buy_cnt,
                "매도신호":    sell_cnt,
                "신호 내역":   " | ".join(signals),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def fetch_weekly_rsi(tickers: tuple[str, ...]) -> dict[str, float]:
    """주봉(1wk) RSI(14) — 장기 과매수/과매도 판단용. 일봉 RSI와 병행 확인."""
    result: dict[str, float] = {}
    for ticker in tickers:
        try:
            hist_w = yf.Ticker(ticker).history(period="2y", interval="1wk", auto_adjust=True)
            if len(hist_w) >= 14:
                rsi_w = RSIIndicator(close=hist_w["Close"], window=14).rsi()
                result[ticker.replace(".KS", "")] = round(float(rsi_w.iloc[-1]), 1)
        except Exception:
            continue
    return result


@st.cache_data(ttl=60)
def fetch_realtime_prices(tickers: tuple[str, ...]) -> dict[str, dict]:
    """분봉(1m) 기반 최신 현재가. 장중 15분 지연, 장외 시 전일 종가 fallback."""
    result: dict[str, dict] = {}
    try:
        raw = yf.download(
            list(tickers), period="1d", interval="1m",
            auto_adjust=True, progress=False,
        )
        if raw.empty:
            return result
        close = raw["Close"] if isinstance(raw["Close"], pd.DataFrame) else raw[["Close"]]
        ts = close.index[-1]
        for ticker in tickers:
            col = ticker if ticker in close.columns else None
            if col is None:
                continue
            series = close[col].dropna()
            if not series.empty:
                result[ticker] = {
                    "price": round(float(series.iloc[-1]), 2),
                    "ts":    ts,
                }
    except Exception:
        pass
    return result


@st.cache_data(ttl=600)
def fetch_korean_indices() -> dict:
    result: dict[str, dict] = {}
    for symbol, name in [("KS11", "KOSPI"), ("KQ11", "KOSDAQ")]:
        try:
            df = fdr.DataReader(
                symbol,
                start=(pd.Timestamp.today() - pd.Timedelta(days=14)).strftime("%Y-%m-%d"),
            )
            latest = float(df["Close"].iloc[-1])
            prev   = float(df["Close"].iloc[-2])
            result[name] = {
                "price":      round(latest, 2),
                "change_pct": round((latest - prev) / prev * 100, 2),
            }
        except Exception:
            result[name] = {"price": 0.0, "change_pct": 0.0}
    return result


@st.cache_data(ttl=600)
def fetch_kospi_top10() -> pd.DataFrame:
    try:
        listing = fdr.StockListing("KOSPI")
        # 컬럼명 정규화
        listing.columns = [c.strip() for c in listing.columns]
        code_col = next((c for c in listing.columns if c in ("Code", "Symbol", "code")), None)
        name_col = next((c for c in listing.columns if c in ("Name", "name", "종목명")), None)
        cap_col  = next((c for c in listing.columns if c in ("Marcap", "MarCap", "시가총액")), None)

        if code_col and name_col:
            top10 = listing.head(10)[[code_col, name_col]].copy()
            top10 = top10.rename(columns={code_col: "코드", name_col: "종목명"})
            if cap_col:
                top10["시총(조)"] = (listing.head(10)[cap_col] / 1e12).round(1).values
            return top10.reset_index(drop=True)
    except Exception:
        pass

    # fallback: 하드코딩된 시총 상위 10
    return pd.DataFrame(KOSPI_FALLBACK)


@st.cache_data(ttl=600)
def fetch_investor_flow(code: str) -> pd.DataFrame | None:
    try:
        df = fdr.SnapDataReader(f"NAVER/INVESTORS/{code}")
        cols = [c for c in ["기관순매매량", "외국인순매매량"] if c in df.columns]
        if not cols:
            return None
        return df[cols].tail(5)
    except Exception:
        return None


# ── Market Phase ──────────────────────────────────────────────────────────────


def determine_phase(fg_score: float, vix: float, yield_spread: float, sp_above_200ma: bool) -> str:
    if vix >= 40 and fg_score < 20:
        return "공포"
    if fg_score >= 50 and vix < 20 and yield_spread >= 0 and sp_above_200ma:
        return "강세"
    if fg_score < 30 and (30 <= vix <= 40):
        return "조정"
    if fg_score < 30 and not sp_above_200ma:
        return "조정"
    return "경계"


# ── UI Helpers ────────────────────────────────────────────────────────────────


def phase_badge(phase: str) -> None:
    color = PHASE_COLORS[phase]
    st.markdown(
        f"""
        <div style="
            text-align:center; padding:24px 16px;
            background:{color}18; border:2px solid {color};
            border-radius:14px; margin-bottom:16px;
        ">
          <div style="color:{color}; font-size:3rem; font-weight:900; letter-spacing:4px;">
            {phase}
          </div>
          <div style="color:#ccc; margin-top:8px; font-size:0.95rem;">
            {PHASE_SUMMARIES[phase]}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_relative_strength(tech_df: pd.DataFrame, sp_ret: dict[str, float]) -> pd.DataFrame:
    """S&P500 대비 상대강도(RS) 컬럼 추가. RS > 0 = 시장 대비 초과 성과."""
    df = tech_df.copy()
    if "3개월(%)" in df.columns:
        df["RS vs S&P(3M)"] = (df["3개월(%)"] - sp_ret.get("3m", 0)).round(2)
    if "12개월(%)" in df.columns:
        df["RS vs S&P(12M)"] = (df["12개월(%)"] - sp_ret.get("12m", 0)).round(2)
    return df


def highlight_signals(row: pd.Series) -> list[str]:
    if row.get("매수신호", 0) >= 3:
        return ["background-color:#0d3b1f"] * len(row)
    if row.get("매도신호", 0) >= 3:
        return ["background-color:#3b0d0d"] * len(row)
    return [""] * len(row)


def signal_legend() -> None:
    with st.expander("신호 읽는 법 (클릭해서 열기)"):
        st.markdown("""
**매수신호 / 매도신호** 숫자는 아래 **5가지** 조건 중 몇 개가 해당되는지를 나타냅니다.

| 조건 | 매수 신호 | 매도 신호 |
|---|---|---|
| RSI(14) | **< 30** 과매도 → 반등 가능성 | **> 70** 과매수 → 조정 가능성 |
| SMA50 (50일 이평선) | 현재가 **위** → 단기 상승 추세 | 현재가 **아래** → 단기 하락 추세 |
| SMA200 (200일 이평선) | 현재가 **위** → 장기 상승 추세 | 현재가 **아래** → 장기 하락 추세 |
| MACD | **골든크로스** (MACD > 시그널) → 상승 모멘텀 | **데드크로스** (MACD < 시그널) → 하락 모멘텀 |
| 볼린저밴드 (20일, 2σ) | **하단 이탈** → 극단적 과매도 | **상단 이탈** → 극단적 과매수 |

> 볼린저밴드는 밴드 내에 있을 때는 신호 없음 (중립). 최대 매수/매도신호는 각 5개.

- **매수신호 3~5** = 초록 배경 → 과반수 지표가 매수 신호
- **매수신호 1~2** = 중립
- **매도신호 3~5** = 빨강 배경 → 과반수 지표가 매도 신호

**참고 컬럼 (신호 카운팅 미포함)**

| 컬럼 | 해석 |
|---|---|
| RSI추세(5일) | ↑+4.1 = 5일 전보다 RSI 4.1 상승 → 반등 모멘텀 강화 중 / ↓-3.8 = 하락 → 낙폭 확대 경고 |
| 주봉RSI | 주봉 기준 RSI. 일봉 RSI < 30 이면서 주봉 RSI도 < 40 이면 **장기 과매도** (강한 매수 후보) |
| RS vs S&P(3M) | +10 = S&P500보다 3개월간 10%p 더 올랐음 / -5 = 5%p 덜 올랐음 |

> 단독 지표로 매매 결정 금지. 국면(탭1)과 함께 종합 판단하세요.
        """)


def fg_guide() -> None:
    with st.expander("공포탐욕지수 해석 가이드 (클릭해서 열기)"):
        st.markdown("""
**공포탐욕지수(Fear & Greed Index)** 는 CNN이 7가지 시장 지표를 종합해 0~100으로 표현한 **역발상 지표**입니다.

| 점수 | 등급 | 시장 상태 | 역발상 해석 |
|---|---|---|---|
| 0 ~ 24 | 극도의 공포 | 투자자 패닉, 과매도 | **매수 기회** 탐색 시기 |
| 25 ~ 44 | 공포 | 불안 심리 우세 | 분할 매수 고려 |
| 45 ~ 55 | 중립 | 균형 상태 | 관망 또는 현상 유지 |
| 56 ~ 74 | 탐욕 | 낙관 심리 우세 | 일부 차익실현 고려 |
| 75 ~ 100 | 극도의 탐욕 | 시장 과열, 과매수 | **매도/비중 축소** 시기 |

> **핵심 원칙**: "남들이 탐욕스러울 때 두려워하고, 남들이 두려워할 때 탐욕스러워져라" — 워런 버핏
> 즉, 지수가 **낮을수록(공포) 매수 기회**, **높을수록(탐욕) 매도 신호**로 해석합니다.
        """)


# ── Tabs ──────────────────────────────────────────────────────────────────────


def tab_overview() -> str | None:
    st.subheader("글로벌 시장 국면")

    fg   = fetch_fear_greed()
    mac  = fetch_macro_data()
    sp   = fetch_sp500_ma()

    if not fg or not mac or not sp:
        st.error("핵심 데이터를 로드할 수 없습니다. 잠시 후 새로고침하세요.")
        return None

    phase = determine_phase(
        fg["score"],
        mac.get("vix", 25),
        mac.get("yield_spread", 0),
        sp.get("above", True),
    )
    phase_badge(phase)

    # Metric cards
    c1, c2, c3, c4, c5 = st.columns(5)
    fg_rating_kr = FG_RATING_KR.get(fg["rating"], fg["rating"])
    c1.metric("공포탐욕지수", f"{fg['score']}", fg_rating_kr)
    vix = mac.get("vix", 0)
    c2.metric("VIX", f"{vix:.1f}",
              "위험" if vix > 30 else ("주의" if vix > 20 else "안정"),
              delta_color="inverse")
    spread = mac.get("yield_spread", 0)
    c3.metric("금리차 10Y-2Y", f"{spread:.2f}%",
              "역전 (경기침체 경고)" if spread < 0 else "정상",
              delta_color="inverse" if spread < 0 else "normal")
    c4.metric("DXY 달러지수", f"{mac.get('dxy', 0):.2f}")
    gap = sp.get("gap_pct", 0)
    c5.metric("S&P500 vs 200MA",
              f"{gap:+.2f}%",
              "200일선 위 (강세)" if gap > 0 else "200일선 아래 (약세)",
              delta_color="normal" if gap > 0 else "inverse")

    fg_guide()
    st.divider()

    # Gauge + history
    col_gauge, col_history = st.columns([1, 1])
    with col_gauge:
        st.markdown("##### 공포탐욕지수 게이지")
        score = fg["score"]
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": fg_rating_kr, "font": {"color": "#fff"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#aaa"},
                "bar": {"color": "#00D4FF"},
                "steps": [
                    {"range": [0, 25],  "color": "#3b0d0d"},
                    {"range": [25, 45], "color": "#3b2200"},
                    {"range": [45, 55], "color": "#3b3b00"},
                    {"range": [55, 75], "color": "#0d3b0d"},
                    {"range": [75, 100],"color": "#003b1f"},
                ],
                "threshold": {
                    "line": {"color": "#fff", "width": 3},
                    "thickness": 0.8,
                    "value": score,
                },
            },
        ))
        fig.update_layout(
            template="plotly_dark", height=260,
            margin=dict(t=40, b=0, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_history:
        st.markdown("##### 기간별 비교")
        h_df = pd.DataFrame({
            "기간": ["현재", "1주 전", "1개월 전", "1년 전"],
            "점수": [fg["score"], fg["prev_1w"], fg["prev_1m"], fg["prev_1y"]],
        })
        fig2 = go.Figure(go.Bar(
            x=h_df["기간"], y=h_df["점수"],
            marker_color=["#00D4FF", "#5588aa", "#336688", "#224455"],
            text=h_df["점수"], textposition="outside",
        ))
        fig2.update_layout(
            template="plotly_dark", height=260,
            margin=dict(t=40, b=0, l=20, r=20),
            yaxis=dict(range=[0, 100]),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # 7 sub-indicators
    if fg.get("indicators"):
        st.markdown("##### 공포탐욕 7개 세부 지표")
        rows = []
        for key, name in FG_INDICATOR_NAMES.items():
            ind = fg["indicators"].get(key)
            if ind:
                rating_kr = FG_RATING_KR.get(ind["rating"], ind["rating"])
                rows.append({"지표": name, "점수": ind["score"], "등급": rating_kr})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    return phase


def tab_us(phase: str | None) -> None:
    st.subheader("미국 주요 지수")

    col_idx, col_sec = st.columns([1, 2])

    with col_idx:
        idx_df, price_ts = fetch_us_indices()
        if not idx_df.empty:
            if price_ts:
                st.caption(f"현재가 기준: {price_ts} (분봉 최신, 약 15분 지연)")
            else:
                st.caption("현재가 기준: 전일 종가 (장 마감)")
            def color_row(row: pd.Series) -> list[str]:
                chg = row.get("등락률(%)", 0)
                if chg > 0:
                    return ["", "", "color:#00C851"]
                elif chg < 0:
                    return ["", "", "color:#FF3547"]
                return ["", "", ""]
            st.dataframe(
                idx_df.style.apply(color_row, axis=1),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("지수 데이터를 불러오는 중입니다...")

    with col_sec:
        st.markdown("##### 섹터 ETF 1일 등락률")
        sec_df = fetch_sector_performance()
        if not sec_df.empty:
            fig = go.Figure(go.Bar(
                x=sec_df["ETF"],
                y=sec_df["1일(%)"],
                marker_color=["#00C851" if v > 0 else "#FF3547" for v in sec_df["1일(%)"]],
                text=[f"{v:+.2f}%" for v in sec_df["1일(%)"]],
                textposition="outside",
                customdata=sec_df["섹터"],
                hovertemplate="%{customdata}<br>%{text}<extra></extra>",
            ))
            fig.update_layout(
                template="plotly_dark", height=300,
                margin=dict(t=20, b=0, l=0, r=0),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    # Sector table with names
    if not sec_df.empty:
        with st.expander("섹터 성과 상세 (클릭해서 열기)"):
            st.dataframe(sec_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("##### 워치리스트 + 섹터 ETF 기술분석 신호")
    signal_legend()

    all_tickers = tuple(WATCHLIST + list(SECTOR_ETFS.keys()))
    with st.spinner("RSI·SMA·MACD·볼린저·모멘텀 계산 중..."):
        tech_df = fetch_technical_signals(all_tickers)

    if not tech_df.empty:
        sp_ret = fetch_sp500_returns()
        tech_df = add_relative_strength(tech_df, sp_ret)

        # 분봉 현재가 덮어쓰기
        rt = fetch_realtime_prices(all_tickers)
        rt_ts = ""
        for ticker, d in rt.items():
            mask = tech_df["티커"] == ticker
            if mask.any():
                tech_df.loc[mask, "현재가"] = d["price"]
            rt_ts = pd.Timestamp(d["ts"]).tz_convert("America/New_York").strftime("%H:%M ET")

        # 주봉 RSI 병합 (백그라운드에서 캐시 있으면 즉시)
        weekly = fetch_weekly_rsi(all_tickers)
        tech_df["주봉RSI"] = tech_df["티커"].map(weekly)

        ts_label = f"현재가: {rt_ts} 기준 (분봉 15분 지연)" if rt_ts else "현재가: 전일 종가 기준"
        st.caption(
            f"{ts_label} | S&P500 — 1개월: {sp_ret['1m']:+.1f}%  "
            f"3개월: {sp_ret['3m']:+.1f}%  12개월: {sp_ret['12m']:+.1f}%"
        )
        st.caption("RS vs S&P(3M): +10 = S&P500보다 3개월간 10%p 초과 성과 / -5 = 5%p 하회")

        display_cols = [
            "티커", "종목명", "현재가",
            "RSI(14)", "RSI추세(5일)", "주봉RSI",
            "1개월(%)", "3개월(%)", "RS vs S&P(3M)",
            "매수신호", "매도신호", "신호 내역",
        ]
        display_cols = [c for c in display_cols if c in tech_df.columns]
        st.dataframe(
            tech_df[display_cols].style.apply(highlight_signals, axis=1),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("기술분석 데이터를 불러오는 중입니다...")


def tab_korea() -> tuple[pd.DataFrame, pd.DataFrame]:
    st.subheader("한국 시장")

    kr_idx = fetch_korean_indices()
    c1, c2 = st.columns(2)
    for col, name in zip([c1, c2], ["KOSPI", "KOSDAQ"]):
        d = kr_idx.get(name, {})
        price = d.get("price", 0)
        chg   = d.get("change_pct", 0)
        col.metric(
            name,
            f"{price:,.2f}",
            f"{chg:+.2f}%",
            delta_color="normal" if chg >= 0 else "inverse",
        )

    st.divider()
    st.markdown("##### KOSPI 시가총액 상위 10")
    top10 = fetch_kospi_top10()
    kr_tech = pd.DataFrame()

    if top10.empty:
        st.warning("종목 데이터를 불러올 수 없습니다.")
        return pd.DataFrame(), pd.DataFrame()

    st.dataframe(top10, use_container_width=True, hide_index=True)

    codes = top10["코드"].tolist()
    yf_tickers = tuple(f"{c}.KS" for c in codes)

    st.markdown("##### 기술분석 신호 (시총 TOP10)")
    signal_legend()
    with st.spinner("한국 종목 기술지표 계산 중... (약 30초 소요)"):
        kr_tech = fetch_technical_signals(yf_tickers)

    if not kr_tech.empty:
        # 종목명 보강
        code_to_name = dict(zip(top10["코드"], top10["종목명"]))
        kr_tech["종목명"] = kr_tech["티커"].map(code_to_name).fillna(kr_tech["종목명"])
        # 상대강도 + 분봉 현재가 + 주봉RSI
        sp_ret = fetch_sp500_returns()
        kr_tech = add_relative_strength(kr_tech, sp_ret)
        rt_kr = fetch_realtime_prices(yf_tickers)
        for yf_t, d in rt_kr.items():
            base = yf_t.replace(".KS", "")
            mask = kr_tech["티커"] == base
            if mask.any():
                kr_tech.loc[mask, "현재가"] = d["price"]
        weekly_kr = fetch_weekly_rsi(yf_tickers)
        kr_tech["주봉RSI"] = kr_tech["티커"].map(weekly_kr)

        display_cols = [
            "티커", "종목명", "현재가",
            "RSI(14)", "RSI추세(5일)", "주봉RSI",
            "1개월(%)", "3개월(%)", "RS vs S&P(3M)",
            "매수신호", "매도신호", "신호 내역",
        ]
        display_cols = [c for c in display_cols if c in kr_tech.columns]
        st.dataframe(
            kr_tech[display_cols].style.apply(highlight_signals, axis=1),
            use_container_width=True, hide_index=True,
        )
    else:
        st.warning("yfinance에서 한국 종목 데이터를 가져오지 못했습니다.")

    st.markdown("##### 외국인/기관 순매매 (최근 5일 합계)")
    st.caption("외국인·기관이 5일간 얼마나 사고 팔았는지 합계. 양수(+) = 순매수, 음수(-) = 순매도")
    flow_rows = []
    for _, row in top10.iterrows():
        code = str(row.get("코드", ""))
        if not code:
            continue
        flow = fetch_investor_flow(code)
        if flow is not None and not flow.empty:
            fgn = int(flow["외국인순매매량"].sum()) if "외국인순매매량" in flow.columns else 0
            ins = int(flow["기관순매매량"].sum())   if "기관순매매량"   in flow.columns else 0
            flow_rows.append({
                "종목": row.get("종목명", code),
                "코드": code,
                "외국인(5일)": fgn,
                "기관(5일)":   ins,
            })

    if flow_rows:
        flow_df = pd.DataFrame(flow_rows)

        def color_flow(row: pd.Series) -> list[str]:
            styles = [""] * len(row)
            for i, col_name in enumerate(row.index):
                if col_name in ("외국인(5일)", "기관(5일)"):
                    styles[i] = "color:#00C851" if row[col_name] > 0 else "color:#FF3547"
            return styles

        st.dataframe(
            flow_df.style.apply(color_flow, axis=1),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("외국인/기관 순매매 데이터를 현재 불러올 수 없습니다 (Naver Finance 접근 제한).")

    return top10, kr_tech


def tab_recommendations(phase: str | None, top10: pd.DataFrame, kr_tech: pd.DataFrame) -> None:
    st.subheader("매수/매도 추천")

    if not phase:
        st.warning("시장 개요(탭1) 데이터가 필요합니다.")
        return

    color = PHASE_COLORS[phase]
    st.markdown(
        f"<div style='padding:14px;background:{color}18;border-left:4px solid {color};"
        f"border-radius:6px;margin-bottom:16px;'>"
        f"<b style='color:{color};font-size:1.2rem;'>현재 국면: {phase}</b><br>"
        f"<span style='color:#ccc;'>{PHASE_SUMMARIES[phase]}</span></div>",
        unsafe_allow_html=True,
    )

    signal_legend()

    st.markdown("#### 미국 추천")
    all_tickers = tuple(WATCHLIST + list(SECTOR_ETFS.keys()))
    with st.spinner("분석 중..."):
        us_tech = fetch_technical_signals(all_tickers)

    if not us_tech.empty:
        sp_ret = fetch_sp500_returns()
        us_tech = add_relative_strength(us_tech, sp_ret)
        rec_cols = ["티커", "종목명", "RSI(14)", "3개월(%)", "RS vs S&P(3M)", "신호 내역"]
        rec_cols = [c for c in rec_cols if c in us_tech.columns]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**매수 관심** (매수신호 ≥ 3) — RS 강도순 정렬")
            buy_us = (
                us_tech[us_tech["매수신호"] >= 3][rec_cols]
                .sort_values("RS vs S&P(3M)", ascending=False)
                .copy()
            )
            if not buy_us.empty:
                st.dataframe(buy_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매수신호 ≥3 종목 없음")
        with col2:
            st.markdown("**매도/경계** (매도신호 ≥ 3) — RS 약세순 정렬")
            sell_us = (
                us_tech[us_tech["매도신호"] >= 3][rec_cols]
                .sort_values("RS vs S&P(3M)", ascending=True)
                .copy()
            )
            if not sell_us.empty:
                st.dataframe(sell_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매도신호 ≥3 종목 없음")

    st.divider()

    st.markdown("#### 한국 추천")
    if not top10.empty and not kr_tech.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**한국 매수 관심** (외국인 순매수 + 기술매수신호 ≥3)")
            buy_kr_rows = []
            for _, row in top10.iterrows():
                code = str(row.get("코드", ""))
                yf_ticker = f"{code}.KS"
                flow = fetch_investor_flow(code)
                foreign_buy = False
                if flow is not None and "외국인순매매량" in flow.columns:
                    foreign_buy = flow["외국인순매매량"].sum() > 0
                if not foreign_buy:
                    continue
                match = kr_tech[kr_tech["티커"] == code]
                if not match.empty and match.iloc[0]["매수신호"] >= 3:
                    buy_kr_rows.append({
                        "종목": row.get("종목명", code),
                        "외국인": "순매수",
                        "신호 내역": match.iloc[0]["신호 내역"],
                    })
            if buy_kr_rows:
                st.dataframe(pd.DataFrame(buy_kr_rows), use_container_width=True, hide_index=True)
            else:
                st.info("교차 조건(외국인 순매수 + 기술매수 ≥2) 충족 종목 없음")

        with col2:
            st.markdown("**한국 경계** (기술매도신호 ≥3)")
            sell_kr = kr_tech[kr_tech["매도신호"] >= 3][["티커", "종목명", "RSI(14)", "신호 내역"]].copy()
            if not sell_kr.empty:
                st.dataframe(sell_kr, use_container_width=True, hide_index=True)
            else:
                st.info("현재 기술매도신호 ≥2 한국 종목 없음")
    else:
        st.info("한국장 탭을 먼저 로드해주세요.")

    st.divider()

    st.markdown("#### 섹터 로테이션 제안")
    st.caption("현재 국면에서 역사적으로 유리/불리한 섹터 방향입니다.")
    rotation = PHASE_SECTORS.get(phase, {})
    c1, c2 = st.columns(2)
    with c1:
        buy_list = rotation.get("buy", [])
        st.success("**비중 확대 권장**\n\n" + "\n".join(
            f"- **{t}** ({SECTOR_ETFS.get(t, t)})" for t in buy_list
        ))
    with c2:
        sell_list = rotation.get("sell", [])
        st.error("**비중 축소 권장**\n\n" + "\n".join(
            f"- **{t}** ({SECTOR_ETFS.get(t, t)})" for t in sell_list
        ))

    st.caption(
        "※ 본 대시보드는 공개 데이터 기반 자동 분석 도구입니다. "
        "투자 조언이 아니며 모든 투자 결정은 본인 책임입니다."
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="글로벌 시장 분석 대시보드",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    with st.sidebar:
        st.markdown("## 글로벌 시장 분석")
        st.caption(f"업데이트: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
        st.divider()
        if st.button("전체 데이터 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown("""
**캐시 주기**
- 주가 / 지수 / 섹터: 5분
- VIX / 금리차 / DXY: 15분
- 공포탐욕지수: 1시간
- 한국 시장: 10분
        """)
        st.divider()
        st.markdown("""
**데이터 출처**
- 미국: yfinance
- 한국: FinanceDataReader
- F&G: CNN Markets API
- 기술지표: ta (RSI, SMA)
        """)

    st.title("📊 글로벌 시장 분석 대시보드")

    tab1, tab2, tab3, tab4 = st.tabs(["🌐 시장 개요", "🇺🇸 미국장", "🇰🇷 한국장", "📈 매수/매도 추천"])

    phase: str | None = None
    top10 = pd.DataFrame()
    kr_tech = pd.DataFrame()

    with tab1:
        phase = tab_overview()

    with tab2:
        tab_us(phase)

    with tab3:
        top10, kr_tech = tab_korea()

    with tab4:
        tab_recommendations(phase, top10, kr_tech)


if __name__ == "__main__":
    main()
