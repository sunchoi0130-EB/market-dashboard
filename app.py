from __future__ import annotations

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

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

# 미국 시총 상위 10 (2026년 기준)
WATCHLIST = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "BRK-B", "TSM"]

TICKER_NAMES = {
    # 미국 시총 TOP10
    "NVDA":  "NVIDIA",
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "AMZN":  "Amazon",
    "GOOGL": "Alphabet (Google)",
    "META":  "Meta",
    "TSLA":  "Tesla",
    "AVGO":  "Broadcom",
    "BRK-B": "Berkshire Hathaway",
    "TSM":   "TSMC",
    # Claude 섹터 추천
    "PLTR":  "Palantir",
    "AMD":   "AMD",
    "CRWD":  "CrowdStrike",
    "PANW":  "Palo Alto Networks",
    "LLY":   "Eli Lilly",
    "ISRG":  "Intuitive Surgical",
    "GS":    "Goldman Sachs",
    "V":     "Visa",
    "NEE":   "NextEra Energy",
    "CVX":   "Chevron",
    "COST":  "Costco",
    **{k: f"{v} ETF" for k, v in SECTOR_ETFS.items()},
}

# ── Claude's Market Picks ─────────────────────────────────────────────────────
# 마지막 업데이트: 2026-05-08 (웹 검색 기반 갱신)
# 시황: KOSPI 7,000 최초 돌파(5/6), S&P 500 7,500 목표 / 경계→강세 전환 구간
# 미국 — AI 실적 서프라이즈(PLTR +85% 매출, AMD +38%) + 방산·소비방어·에너지 로테이션
# 한국 — '조·방·원·전력' 4대 테마 주도
#   LS ELECTRIC Q1 매출 +72.4%·영업익 +152.2% / HD현대중공업 Q1 영업익 +108.7%
#   두산에너빌리티 SMR·원전 수주 가시화 / 한화에어로스페이스 목표가 170만원대

US_CLAUDE_PICKS: dict[str, list[str]] = {
    "AI·데이터":   ["PLTR", "AMD"],    # PLTR Q1 85% 매출성장·가이던스 대폭상향 / AMD Q1 +38% 서프라이즈
    "사이버보안":  ["CRWD", "PANW"],   # AI 보안 수요 급증, CRWD 5/7 +6.7%
    "헬스케어":    ["LLY", "ISRG"],    # GLP-1 구조적 성장 / 로봇수술 확장
    "금융":        ["GS", "V"],        # 강세장 IB 회복 / 결제 인프라
    "에너지":      ["CVX", "NEE"],     # 전통에너지 헤지 / AI 데이터센터 전력 수요
    "소비재·방어": ["COST"],           # 경기방어·리테일 강자
}

KR_CLAUDE_PICKS: dict[str, list[str]] = {
    "반도체·장비":   ["042700", "058470"],   # 한미반도체(HBM 패키징 장비), 리노공업(테스트소켓)
    "방산":          ["012450", "079550"],   # 한화에어로스페이스(목표가 170만·전원매수), LIG넥스원(천궁-II 양산)
    "전력인프라":    ["010120"],             # LS ELECTRIC — AI 데이터센터 전력 수혜, Q1 매출 +72.4%·영업익 +152.2%
    "조선":          ["329180"],             # HD현대중공업 — LNG선 슈퍼사이클, Q1 영업익 +108.7%
    "원전·에너지":   ["034020"],             # 두산에너빌리티 — SMR·가스터빈·원전 수주 확대
    "바이오·제약":   ["128940", "000100"],   # 한미약품(GLP-1 파이프라인), 유한양행(레이저티닙 글로벌)
    "인터넷·플랫폼": ["035420"],             # NAVER(AI 검색 전환)
    "금융":          ["032830", "086790"],   # 삼성생명, 하나금융지주
}

KR_CLAUDE_PICK_NAMES: dict[str, str] = {
    "042700": "한미반도체",
    "058470": "리노공업",
    "012450": "한화에어로스페이스",
    "079550": "LIG넥스원",
    "010120": "LS ELECTRIC",
    "329180": "HD현대중공업",
    "034020": "두산에너빌리티",
    "128940": "한미약품",
    "000100": "유한양행",
    "035420": "NAVER",
    "032830": "삼성생명",
    "086790": "하나금융지주",
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

# ── Phase별 신호 가중치 ────────────────────────────────────────────────────────
# 근거: 추세장(강세)에서 모멘텀 신호 신뢰도↑, 반전 신호(볼린저 과매수 경고 등) 신뢰도↓
#       공포/조정에서 평균회귀 신호(RSI 과매도, 강세 다이버전스) 신뢰도↑
#       ADX는 추세 강도 필터로 사용 — ADX<20 횡보장에서 RSI 과매수/과매도 신뢰도 50% 하향
PHASE_SIGNAL_WEIGHTS: dict[str, dict[str, float]] = {
    "강세": {
        "rsi_oversold":    0.7,   # 추세장에서 RSI 30 이하는 드물고, 나와도 추세 강해 반등 약함
        "rsi_overbought":  0.5,   # 추세장에서 과매수는 경고보다 강세 지속 신호에 가까움
        "sma50":           1.0,
        "sma200":          1.0,
        "macd":            1.3,   # 추세 확인 지표 — 강세장에서 신뢰도 높음
        "bb_lower":        1.0,
        "bb_upper":        0.5,   # 추세장 상단 이탈은 매도보다 강세 지속 가능성
        "volume":          1.3,   # 거래량 동반 상승 — 추세장에서 더 의미 있음
        "high52w":         1.5,   # 52주 신고가 — 모멘텀 지속 효과 강세장에서 강함
    },
    "경계": {
        "rsi_oversold":    1.0,
        "rsi_overbought":  1.2,
        "sma50":           1.0,
        "sma200":          1.0,
        "macd":            0.8,   # 경계장 MACD는 후행 — 다이버전스 신뢰도가 더 높음
        "bb_lower":        1.2,
        "bb_upper":        1.5,   # 경계장 상단 이탈은 조정 경고로 신뢰도 높음
        "volume":          1.0,
        "high52w":         0.8,   # 경계장 신고가 돌파는 지속성 불확실
    },
    "조정": {
        "rsi_oversold":    1.5,   # 조정장 RSI 과매도 = 강한 반등 신호
        "rsi_overbought":  1.3,
        "sma50":           0.8,   # 조정장 SMA 이탈은 흔함 — 신뢰도 낮춤
        "sma200":          1.2,   # 장기선은 여전히 중요
        "macd":            0.8,
        "bb_lower":        1.5,
        "bb_upper":        1.3,
        "volume":          1.2,
        "high52w":         0.5,   # 조정장 신고가는 거의 없고 의미 약함
    },
    "공포": {
        "rsi_oversold":    1.5,
        "rsi_overbought":  0.7,   # 공포장 RSI 과매수는 드문 케이스
        "sma50":           0.7,
        "sma200":          1.0,
        "macd":            0.7,
        "bb_lower":        1.5,
        "bb_upper":        0.7,
        "volume":          1.3,   # 공포 바닥에서 거래량 급증은 반전 신호
        "high52w":         0.3,
    },
}

# 기술분석 테이블 숫자 컬럼 표시 포맷 (소수점 1자리 강제)
TECH_COL_FMT: dict[str, str] = {
    "현재가":          "{:.1f}",
    "RSI(14)":         "{:.1f}",
    "주봉RSI":         "{:.1f}",
    "1개월(%)":        "{:.1f}",
    "3개월(%)":        "{:.1f}",
    "12개월(%)":       "{:.1f}",
    "RS vs S&P(3M)":   "{:.1f}",
    "RS vs S&P(12M)":  "{:.1f}",
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
            result["yield_spread"] = round(result["y10"] - result["y2"], 1)
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
            "gap_pct": round((price - ma200) / ma200 * 100, 1),
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
            "1m":  round((price / float(c.iloc[-22]) - 1) * 100, 1) if len(c) >= 22 else 0.0,
            "3m":  round((price / float(c.iloc[-63]) - 1) * 100, 1) if len(c) >= 63 else 0.0,
            "12m": round((price / float(c.iloc[0])   - 1) * 100, 1),
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
            rows.append({"지수": US_INDICES[t], "현재가": f"{cur:,.1f}", "등락률(%)": round(chg, 1)})
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
            "1일(%)":   [round(float(p1d[t]), 1) for t in tickers],
            "1개월(%)": [round(float(p1m[t]), 1) for t in tickers],
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
            rsi_trend  = rsi_context(rsi_val, rsi_delta)
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
            ret_1m  = round((price / float(close.iloc[-22]) - 1) * 100, 1) if len(close) >= 22 else float("nan")
            ret_3m  = round((price / float(close.iloc[-63]) - 1) * 100, 1) if len(close) >= 63 else float("nan")
            ret_12m = round((price / float(close.iloc[0])   - 1) * 100, 1)

            # RSI 다이버전스 (OHLC 활용 — Low/High로 피봇 탐색)
            divergence = detect_rsi_divergence(hist, rsi_series)

            # 종목명 조회 (섹터 ETF 또는 워치리스트)
            base = ticker.replace(".KS", "")
            name = TICKER_NAMES.get(base, base)

            rows.append({
                "티커":        ticker.replace(".KS", ""),
                "종목명":      name,
                "현재가":      round(price, 1),
                "RSI(14)":     round(rsi_val, 1),
                "RSI해석":      rsi_trend,
                "RSI다이버전스": divergence,
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
                    "price": round(float(series.iloc[-1]), 1),
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
                "price":      round(latest, 1),
                "change_pct": round((latest - prev) / prev * 100, 1),
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
            # 우선주 제외: 코드 끝자리가 5이거나 종목명에 '우' '우B' 포함
            listing = listing[~listing[code_col].astype(str).str.endswith("5")]
            listing = listing[~listing[name_col].astype(str).str.endswith(("우", "우B", "우C"))]
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
def fetch_korean_prices_fdr(codes: tuple[str, ...]) -> dict[str, dict]:
    """fdr(Naver Finance → KRX)로 한국 종목 최신 종가 조회.
    yfinance .KS는 Yahoo 서버 경유로 최대 1일 지연이 발생할 수 있어 fdr을 우선 사용."""
    result: dict[str, dict] = {}
    start = (pd.Timestamp.today() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    for code in codes:
        try:
            df = fdr.DataReader(code, start=start)
            if not df.empty:
                result[code] = {
                    "price": round(float(df["Close"].iloc[-1]), 1),
                    "date":  df.index[-1].strftime("%Y-%m-%d"),
                }
        except Exception:
            continue
    return result


@st.cache_data(ttl=600)
def fetch_investor_flow(code: str) -> pd.DataFrame | None:
    """Naver Finance frgn 페이지 직접 파싱 — fdr.SnapDataReader가 컬럼 수 변화로 깨짐."""
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}&page=1"
        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers=hdrs, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.find_all("table")
        if len(tables) < 4:
            return None
        rows = tables[3].find_all("tr")
        records = []
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            # 데이터 행: 날짜(YYYY.MM.DD), 종가, 전일비, 등락률, 거래량, 기관순매매, 외국인순매매, 보유주수, 보유율
            if len(cells) >= 7 and "." in cells[0] and len(cells[0]) == 10:
                def _parse(s: str) -> int:
                    return int(s.replace(",", "").replace("+", "").replace("-", "-") or 0)
                try:
                    def _to_int(s: str) -> int:
                        s = s.replace(",", "").replace("+", "")
                        return int(s) if s and s != "-" else 0
                    records.append({
                        "날짜":           cells[0],
                        "기관순매매량":   _to_int(cells[5]),
                        "외국인순매매량": _to_int(cells[6]),
                    })
                except (ValueError, IndexError):
                    continue
        if not records:
            return None
        df = pd.DataFrame(records).set_index("날짜")
        return df.head(5)
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


def rsi_context(rsi: float, delta: float) -> str:
    """RSI 현재 구간 + 5일 방향을 결합한 맥락 해석."""
    up = delta > 0
    if rsi > 70:
        return f"{'🔴 과매수 심화' if up else '🔴 과매수 완화'} ({delta:+.1f})"
    elif rsi >= 60:
        return f"⚠️ 과매수 접근 ({delta:+.1f})" if up else f"고점 이탈 중 ({delta:+.1f})"
    elif rsi >= 50:
        return "모멘텀 강세" if up else "모멘텀 약화"
    elif rsi >= 40:
        return "회복 중" if up else "하락세"
    elif rsi >= 30:
        return f"↑ 반등 시도 ({delta:+.1f})" if up else "과매도 근접"
    else:
        return f"↑ 바닥 반등 중 ({delta:+.1f})" if up else "바닥 하락 지속"


def _swing_lows(vals: list, window: int = 5) -> list[int]:
    idxs, n = [], len(vals)
    for i in range(window, n - window):
        if (all(vals[i] <= vals[i - j] for j in range(1, window + 1)) and
                all(vals[i] <= vals[i + j] for j in range(1, window + 1))):
            idxs.append(i)
    return idxs


def _swing_highs(vals: list, window: int = 5) -> list[int]:
    idxs, n = [], len(vals)
    for i in range(window, n - window):
        if (all(vals[i] >= vals[i - j] for j in range(1, window + 1)) and
                all(vals[i] >= vals[i + j] for j in range(1, window + 1))):
            idxs.append(i)
    return idxs


def detect_rsi_divergence(hist: pd.DataFrame, rsi_series: pd.Series,
                          lookback: int = 63, window: int = 5) -> str:
    """
    RSI 다이버전스 4종 감지 (최근 3개월, OHLC 기준).
    스윙 저점은 Low, 스윙 고점은 High로 탐색 — 종가만 쓸 때보다 피봇 정확도 향상.
    RSI 차이 2p 이상 요구해 노이즈 억제. 일반(반전) 신호 우선 반환.

    일반강세 : Low↓ + RSI_at_low↑  → 하락 모멘텀 약화, 반등 가능성
    일반약세 : High↑ + RSI_at_high↓ → 상승 모멘텀 약화, 조정 가능성
    숨겨진강세: Low↑ + RSI_at_low↓  → 상승 추세 지속 확인
    숨겨진약세: High↓ + RSI_at_high↑ → 하락 추세 지속 확인
    """
    if len(hist) < lookback + window or len(rsi_series) < lookback + window:
        return "-"

    h = hist.iloc[-lookback:]
    r = rsi_series.iloc[-lookback:].ffill()

    low_v  = h["Low"].values.tolist()
    high_v = h["High"].values.tolist()
    rsi_v  = r.values.tolist()

    # ── 저점 계열 (Low 기준) ──
    lows = _swing_lows(low_v, window)
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        pl1, pl2 = low_v[i1], low_v[i2]
        rl1, rl2 = rsi_v[i1], rsi_v[i2]
        if pl2 < pl1 and rl2 > rl1 + 2:   # 일반 강세
            return "🟢 일반강세"
        if pl2 > pl1 and rl2 < rl1 - 2:   # 숨겨진 강세
            return "🔵 숨겨진강세"

    # ── 고점 계열 (High 기준) ──
    highs = _swing_highs(high_v, window)
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        ph1, ph2 = high_v[i1], high_v[i2]
        rh1, rh2 = rsi_v[i1], rsi_v[i2]
        if ph2 > ph1 and rh2 < rh1 - 2:   # 일반 약세
            return "🔴 일반약세"
        if ph2 < ph1 and rh2 > rh1 + 2:   # 숨겨진 약세
            return "🟠 숨겨진약세"

    return "-"


def add_relative_strength(tech_df: pd.DataFrame, sp_ret: dict[str, float]) -> pd.DataFrame:
    """S&P500 대비 상대강도(RS) 컬럼 추가. RS > 0 = 시장 대비 초과 성과."""
    df = tech_df.copy()
    if "3개월(%)" in df.columns:
        df["RS vs S&P(3M)"] = (df["3개월(%)"] - sp_ret.get("3m", 0)).round(1)
    if "12개월(%)" in df.columns:
        df["RS vs S&P(12M)"] = (df["12개월(%)"] - sp_ret.get("12m", 0)).round(1)
    return df


def highlight_signals(row: pd.Series) -> list[str]:
    if row.get("매수신호", 0) >= 3:
        return ["background-color:#0d3b1f"] * len(row)
    if row.get("매도신호", 0) >= 3:
        return ["background-color:#3b0d0d"] * len(row)
    return [""] * len(row)


def position_guidance(row: pd.Series) -> tuple[str, str]:
    """매수/매도신호 + RSI + 다이버전스를 종합해 신규진입·보유판단 레이블 반환."""
    buy  = int(row.get("매수신호", 0))
    sell = int(row.get("매도신호", 0))
    rsi  = float(row.get("RSI(14)", 50))
    div  = str(row.get("RSI다이버전스", "-"))

    bearish    = div in ("🔴 일반약세", "🟠 숨겨진약세")
    bullish    = div in ("🟢 일반강세", "🔵 숨겨진강세")
    overbought = rsi >= 70
    oversold   = rsi <= 30

    # 신규 진입
    if sell >= 4 or (bearish and sell >= 2):
        entry = "⛔ 진입 보류"
    elif buy >= 4 and not overbought:
        entry = "✅ 진입 적합"
    elif buy >= 3 and overbought:
        entry = "⏳ 조정 후 진입"
    elif oversold and bullish:
        entry = "🔍 분할 매수 검토"
    elif buy >= 3:
        entry = "✅ 진입 적합"
    else:
        entry = "👀 관망"

    # 보유 판단 — 강세 다이버전스는 과매수 경고보다 우선
    if (bearish and sell >= 3) or sell >= 4:
        hold = "🚨 매도 검토"
    elif overbought and sell >= 2 and not bullish:
        hold = "⚠️ 부분 차익 검토"
    elif bullish or buy >= 3:
        hold = "✊ 보유 유지"
    elif sell >= 3:
        hold = "🚨 매도 검토"
    else:
        hold = "✊ 보유 유지"

    return entry, hold


@st.cache_data(ttl=300)
def compute_checkup(ticker_input: str, phase: str) -> dict | None:
    """단일 종목 종합 검진 — ADX·거래량·OBV·ATR·52주 신호 + Phase 가중치 적용."""
    is_korean = ticker_input.isdigit() and len(ticker_input) == 6
    yf_ticker = f"{ticker_input}.KS" if is_korean else ticker_input.upper()
    try:
        hist = yf.Ticker(yf_ticker).history(period="1y", interval="1d", auto_adjust=True)
        if len(hist) < 60:
            return None
        close  = hist["Close"]
        high_s = hist["High"]
        low_s  = hist["Low"]
        vol_s  = hist["Volume"]
        price  = float(close.iloc[-1])

        # ── 기간별 수익률 ────────────────────────────────────────────────────
        def _ret(n: int) -> float:
            return round((price / float(close.iloc[-n]) - 1) * 100, 1) if len(close) >= n else float("nan")

        # ── 52주 고저 ────────────────────────────────────────────────────────
        high52 = float(high_s.max())
        low52  = float(low_s.min())
        pos52  = round((price - low52) / (high52 - low52) * 100, 1) if high52 != low52 else 50.0
        near_high = price >= high52 * 0.95

        # ── RSI ──────────────────────────────────────────────────────────────
        rsi_series = RSIIndicator(close=close, window=14).rsi()
        rsi_val    = float(rsi_series.iloc[-1])
        rsi_5d_ago = float(rsi_series.iloc[-6]) if len(rsi_series) >= 6 else rsi_val
        rsi_delta  = round(rsi_val - rsi_5d_ago, 1)
        divergence = detect_rsi_divergence(hist, rsi_series)

        # ── MACD ─────────────────────────────────────────────────────────────
        macd_obj  = MACD(close=close)
        macd_line = float(macd_obj.macd().iloc[-1])
        macd_sig  = float(macd_obj.macd_signal().iloc[-1])
        macd_hist = round(macd_line - macd_sig, 2)

        # ── 볼린저 ───────────────────────────────────────────────────────────
        bb      = BollingerBands(close=close, window=20, window_dev=2)
        bb_low  = float(bb.bollinger_lband().iloc[-1])
        bb_high = float(bb.bollinger_hband().iloc[-1])
        bb_mid  = float(bb.bollinger_mavg().iloc[-1])
        bb_pct  = round((price - bb_low) / (bb_high - bb_low) * 100, 1) if bb_high != bb_low else 50.0

        # ── SMA ──────────────────────────────────────────────────────────────
        sma20  = float(SMAIndicator(close=close, window=20).sma_indicator().iloc[-1])
        sma50  = float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1])
        sma200 = float(SMAIndicator(close=close, window=200).sma_indicator().iloc[-1])

        # ── ADX (추세 강도 필터) ─────────────────────────────────────────────
        adx_obj  = ADXIndicator(high=high_s, low=low_s, close=close, window=14)
        adx_val  = float(adx_obj.adx().iloc[-1])
        adx_pos  = float(adx_obj.adx_pos().iloc[-1])
        adx_neg  = float(adx_obj.adx_neg().iloc[-1])
        trending = adx_val >= 25

        # ── 거래량 ───────────────────────────────────────────────────────────
        vol_now   = float(vol_s.iloc[-1])
        vol_avg20 = float(vol_s.iloc[-20:].mean()) if len(vol_s) >= 20 else vol_now
        vol_ratio = round(vol_now / vol_avg20, 2) if vol_avg20 > 0 else 1.0
        high_vol  = vol_ratio >= 1.5
        ret_1w    = _ret(5)

        # ── OBV ─────────────────────────────────────────────────────────────
        obv_series = OnBalanceVolumeIndicator(close=close, volume=vol_s).on_balance_volume()
        obv_rising = bool(obv_series.iloc[-1] > obv_series.rolling(20).mean().iloc[-1])

        # ── ATR ──────────────────────────────────────────────────────────────
        atr_val = float(AverageTrueRange(high=high_s, low=low_s, close=close, window=14).average_true_range().iloc[-1])
        atr_pct = round(atr_val / price * 100, 2)

        # ── Phase 가중치 + 신호 계산 ─────────────────────────────────────────
        wt = PHASE_SIGNAL_WEIGHTS.get(phase, PHASE_SIGNAL_WEIGHTS["경계"])
        adx_factor = 0.5 if not trending else 1.0  # 횡보장에서 RSI 극단 신호 신뢰도 하향

        buy_score = sell_score = 0.0
        signal_rows: list[tuple] = []

        def _add(label: str, interp: str, direction: int, key: str, extra_factor: float = 1.0) -> None:
            nonlocal buy_score, sell_score
            w = round(wt[key] * extra_factor, 2)
            ws = round(direction * w, 2)
            signal_rows.append((label, interp, direction, w, ws))
            if direction > 0:
                buy_score += w
            else:
                sell_score += w

        def _neutral(label: str, interp: str) -> None:
            signal_rows.append((label, interp, 0, "-", 0))

        # RSI
        if rsi_val < 30:
            _add(f"RSI {rsi_val:.1f}", "과매도 → 반등 가능", +1, "rsi_oversold", adx_factor)
        elif rsi_val > 70:
            _add(f"RSI {rsi_val:.1f}", "과매수 → 조정 가능", -1, "rsi_overbought", adx_factor)
        else:
            _neutral(f"RSI {rsi_val:.1f}", rsi_context(rsi_val, rsi_delta))

        # SMA50
        if price > sma50:
            _add(f"SMA50 {sma50:,.0f}", "현재가 위 → 단기 상승 추세", +1, "sma50")
        else:
            _add(f"SMA50 {sma50:,.0f}", "현재가 아래 → 단기 하락 추세", -1, "sma50")

        # SMA200
        if price > sma200:
            _add(f"SMA200 {sma200:,.0f}", "현재가 위 → 장기 상승 추세", +1, "sma200")
        else:
            _add(f"SMA200 {sma200:,.0f}", "현재가 아래 → 장기 하락 추세", -1, "sma200")

        # MACD
        if macd_line > macd_sig:
            _add(f"MACD {macd_hist:+.1f}", "골든크로스 → 상승 모멘텀", +1, "macd")
        else:
            _add(f"MACD {macd_hist:+.1f}", "데드크로스 → 하락 모멘텀", -1, "macd")

        # 볼린저
        if price < bb_low:
            _add(f"BB {bb_pct:.0f}%", "하단 이탈 → 과매도 극단", +1, "bb_lower")
        elif price > bb_high:
            _add(f"BB {bb_pct:.0f}%", "상단 이탈 → 단기 과열", -1, "bb_upper")
        else:
            _neutral(f"BB {bb_pct:.0f}%", "밴드 내 정상 범위")

        # 거래량 (가격 방향 결합)
        if high_vol:
            if pd.notna(ret_1w) and ret_1w > 0:
                _add(f"거래량 {vol_ratio:.1f}배", "고거래량 상승 → 신뢰도 강화", +1, "volume")
            elif pd.notna(ret_1w) and ret_1w < 0:
                _add(f"거래량 {vol_ratio:.1f}배", "고거래량 하락 → 매도 압력", -1, "volume")
            else:
                _neutral(f"거래량 {vol_ratio:.1f}배", "고거래량 (방향 불명)")
        else:
            _neutral(f"거래량 {vol_ratio:.1f}배", "평균 수준 (중립)")

        # 52주 신고가권
        if near_high:
            _add(f"52주 위치 {pos52:.0f}%", "신고가권 → 모멘텀 지속 가능성", +1, "high52w")
        else:
            _neutral(f"52주 위치 {pos52:.0f}%", "신고가 미도달 (중립)")

        buy_score  = round(buy_score, 2)
        sell_score = round(sell_score, 2)

        # ── 종합 진단 ────────────────────────────────────────────────────────
        synth = pd.Series({
            "매수신호":    round(buy_score),
            "매도신호":    round(sell_score),
            "RSI(14)":    rsi_val,
            "RSI다이버전스": divergence,
        })
        entry, hold = position_guidance(synth)

        # 코멘트
        parts = []
        if not trending:
            parts.append(f"ADX {adx_val:.0f} 횡보장 — RSI 신호 신뢰도 낮음")
        elif adx_val >= 30:
            parts.append(f"ADX {adx_val:.0f} 강한 추세 진행 중")
        if rsi_val > 70:
            parts.append(f"RSI {rsi_val:.1f} 과매수")
        elif rsi_val < 30:
            parts.append(f"RSI {rsi_val:.1f} 과매도")
        if bb_pct > 100:
            parts.append(f"BB {bb_pct:.0f}% 상단 이탈 — 단기 과열")
        elif bb_pct < 0:
            parts.append(f"BB {bb_pct:.0f}% 하단 이탈 — 단기 과매도")
        if high_vol:
            parts.append(f"거래량 {vol_ratio:.1f}배 {'상승' if pd.notna(ret_1w) and ret_1w > 0 else '하락'} 동반")
        if divergence != "-":
            parts.append(f"RSI 다이버전스 {divergence}")
        comment = " / ".join(parts) if parts else "신호 혼재 — 방향 불명확"

        return {
            "is_korean":   is_korean,
            "price":       price,
            "ret_1w":      _ret(5),
            "ret_1m":      _ret(22),
            "ret_3m":      _ret(63),
            "ret_6m":      _ret(126),
            "ret_1y":      _ret(252) if len(close) >= 252 else round((price / float(close.iloc[0]) - 1) * 100, 1),
            "high52":      high52,
            "low52":       low52,
            "pos52":       pos52,
            "near_high":   near_high,
            "rsi_val":     round(rsi_val, 1),
            "rsi_delta":   rsi_delta,
            "divergence":  divergence,
            "macd_hist":   macd_hist,
            "bb_pct":      bb_pct,
            "bb_low":      round(bb_low, 1),
            "bb_mid":      round(bb_mid, 1),
            "bb_high":     round(bb_high, 1),
            "sma20":       round(sma20, 1),
            "sma50":       round(sma50, 1),
            "sma200":      round(sma200, 1),
            "adx_val":     round(adx_val, 1),
            "adx_pos":     round(adx_pos, 1),
            "adx_neg":     round(adx_neg, 1),
            "trending":    trending,
            "vol_ratio":   vol_ratio,
            "obv_rising":  obv_rising,
            "atr_val":     round(atr_val, 1),
            "atr_pct":     atr_pct,
            "buy_score":   buy_score,
            "sell_score":  sell_score,
            "signal_rows": signal_rows,
            "entry":       entry,
            "hold":        hold,
            "comment":     comment,
        }
    except Exception:
        return None


def tab_checkup(phase: str | None) -> None:
    effective_phase = phase or "경계"
    color = PHASE_COLORS[effective_phase]
    st.markdown(
        f"<div style='padding:10px 14px;background:{color}18;border-left:4px solid {color};"
        f"border-radius:6px;margin-bottom:16px;'>"
        f"현재 국면 <b style='color:{color}'>{effective_phase}</b> 기준 신호 가중치 적용"
        + ("" if phase else " &nbsp;—&nbsp; 시장 개요 탭을 먼저 로드하면 자동 갱신됩니다")
        + "</div>",
        unsafe_allow_html=True,
    )

    col_inp, col_btn = st.columns([5, 1])
    with col_inp:
        ticker_raw = st.text_input(
            "ticker",
            placeholder="미국: AAPL · NVDA · TSLA    한국: 005380 · 005930 · 000660",
            label_visibility="collapsed",
        )
    with col_btn:
        run = st.button("검진 시작", use_container_width=True)

    st.caption("한국 종목은 6자리 숫자 코드 입력 (예: 005930 = 삼성전자, 005380 = 현대차)")

    if not run or not ticker_raw.strip():
        st.info("종목 코드를 입력 후 [검진 시작] 버튼을 누르세요.")
        return

    ticker_input = ticker_raw.strip()
    with st.spinner(f"{ticker_input} 분석 중..."):
        r = compute_checkup(ticker_input, effective_phase)

    if r is None:
        st.error(f"**{ticker_input}** 데이터를 불러올 수 없습니다. 종목 코드를 확인해주세요.")
        return

    is_kr = r["is_korean"]

    def fmt_p(v: float) -> str:
        return f"{v:,.0f}원" if is_kr else f"${v:,.2f}"

    def fmt_ret(v: float) -> str:
        return f"{v:+.1f}%" if pd.notna(v) else "-"

    # ── 1. 가격 현황 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### {ticker_input.upper()} 검진 결과")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("현재가", fmt_p(r["price"]))
    c2.metric("1주", fmt_ret(r["ret_1w"]))
    c3.metric("1개월", fmt_ret(r["ret_1m"]))
    c4.metric("3개월", fmt_ret(r["ret_3m"]))
    c5.metric("6개월", fmt_ret(r["ret_6m"]))
    c6.metric("1년", fmt_ret(r["ret_1y"]))

    pos52 = r["pos52"]
    filled = int(pos52 / 10)
    bar = "▓" * filled + "░" * (10 - filled)
    h_fmt = f"{r['high52']:,.0f}" if is_kr else f"{r['high52']:,.2f}"
    l_fmt = f"{r['low52']:,.0f}" if is_kr else f"{r['low52']:,.2f}"
    st.markdown(
        f"**52주 구간** &nbsp; 최저 `{l_fmt}` &nbsp; {bar} &nbsp; 최고 `{h_fmt}` "
        f"&nbsp; 현재 위치 **{pos52:.0f}%**"
        + (" &nbsp; ⚡ **52주 신고가권**" if r["near_high"] else "")
    )

    # ── 2. 기술 신호 테이블 ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"#### 기술 신호 &nbsp; `{effective_phase}` 국면 가중치 적용")

    if not r["trending"]:
        st.warning(f"ADX {r['adx_val']:.1f} — **횡보장** 감지. RSI 극단 신호(과매수/과매도) 가중치 50% 하향 적용됨.")

    sig_df = pd.DataFrame(
        r["signal_rows"],
        columns=["신호", "해석", "원점수", "가중치", "가중점수"],
    )

    def _color_sig(row: pd.Series) -> list[str]:
        if row["원점수"] == 1:
            return ["background-color:#0d3b1f"] * len(row)
        if row["원점수"] == -1:
            return ["background-color:#3b0d0d"] * len(row)
        return [""] * len(row)

    st.dataframe(
        sig_df.style.apply(_color_sig, axis=1),
        use_container_width=True, hide_index=True,
    )

    di_dir = "DI+ 우세 (상승 추세)" if r["adx_pos"] > r["adx_neg"] else "DI- 우세 (하락 추세)"
    trend_label = "추세장 ✓" if r["trending"] else "횡보장 ⚠"
    st.caption(
        f"ADX {r['adx_val']:.1f} ({trend_label}) | {di_dir} "
        f"(DI+ {r['adx_pos']:.1f} / DI- {r['adx_neg']:.1f})"
    )

    # ── 3. 보조 지표 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 보조 지표 (정보용 — 점수 미포함)")

    b1, b2, b3, b4 = st.columns(4)
    b1.metric(
        "OBV 추세",
        "📈 상승 (매집)" if r["obv_rising"] else "📉 하락 (분산)",
    )
    atr_str = f"{r['atr_val']:,.0f}원" if is_kr else f"{r['atr_val']:.2f}"
    b2.metric("ATR — 일 변동폭", f"{atr_str} ({r['atr_pct']:.1f}%)")
    b3.metric(
        "볼린저 위치",
        f"{r['bb_pct']:.0f}%",
        "상단 이탈 과열" if r["bb_pct"] > 100 else (
            "하단 이탈 과매도" if r["bb_pct"] < 0 else "밴드 내 정상"),
        delta_color="inverse" if r["bb_pct"] > 100 else (
            "normal" if r["bb_pct"] < 0 else "off"),
    )
    b4.metric("SMA20", f"{r['sma20']:,.0f}" if is_kr else f"{r['sma20']:.2f}",
              "위 ↑" if r["price"] > r["sma20"] else "아래 ↓")

    # ── 4. 종합 진단 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 종합 진단")

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("가중 매수점수", f"{r['buy_score']:.1f}",
              "≥3.0 진입 고려" if r["buy_score"] >= 3.0 else "3.0 미달")
    g2.metric("가중 매도점수", f"{r['sell_score']:.1f}",
              "≥3.0 경계 요망" if r["sell_score"] >= 3.0 else "3.0 미달",
              delta_color="inverse")
    g3.metric("신규진입 판단", r["entry"])
    g4.metric("보유 판단", r["hold"])

    entry_color = {
        "✅ 진입 적합":      "#00C851",
        "⏳ 조정 후 진입":   "#FFD700",
        "🔍 분할 매수 검토": "#00D4FF",
        "⛔ 진입 보류":      "#FF3547",
        "👀 관망":           "#888888",
    }.get(r["entry"], "#888888")

    st.markdown(
        f"<div style='padding:12px 16px;background:{entry_color}18;"
        f"border-left:4px solid {entry_color};border-radius:6px;margin-top:8px;'>"
        f"<b>진단 요약:</b> {r['comment']}</div>",
        unsafe_allow_html=True,
    )

    if r["divergence"] != "-":
        st.info(f"**RSI 다이버전스**: {r['divergence']} — 추세 전환/지속 선행 신호 감지")

    # ── 5. 한국 종목 수급 ─────────────────────────────────────────────────────
    if is_kr:
        st.markdown("---")
        st.markdown("#### 외국인/기관 순매매 (최근 5일)")
        code = ticker_input.zfill(6)
        with st.spinner("수급 데이터 조회 중..."):
            flow = fetch_investor_flow(code)

        if flow is not None and not flow.empty:
            fgn_5d = int(flow["외국인순매매량"].sum())
            ins_5d = int(flow["기관순매매량"].sum())
            f1, f2 = st.columns(2)
            f1.metric("외국인 5일 누계", f"{fgn_5d:+,}",
                      "순매수 ↑" if fgn_5d > 0 else "순매도 ↓",
                      delta_color="normal" if fgn_5d > 0 else "inverse")
            f2.metric("기관 5일 누계", f"{ins_5d:+,}",
                      "순매수 ↑" if ins_5d > 0 else "순매도 ↓",
                      delta_color="normal" if ins_5d > 0 else "inverse")

            def _color_flow(row: pd.Series) -> list[str]:
                return [
                    ("color:#00C851" if row[c] > 0 else "color:#FF3547")
                    if c in ("기관순매매량", "외국인순매매량") else ""
                    for c in row.index
                ]
            st.dataframe(flow.style.apply(_color_flow, axis=1), use_container_width=True)
        else:
            st.info("외국인/기관 수급 데이터를 불러올 수 없습니다.")


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
| RSI해석 | RSI 현재 구간 + 5일 방향을 결합한 맥락 해석 (아래 표 참고) |
| RSI다이버전스 | 가격 방향과 RSI 방향이 엇갈릴 때 추세 전환 선행 신호 (아래 표 참고) |
| 신규진입 | 지금 처음 매수하는 경우의 타이밍 판단 (아래 표 참고) |
| 보유판단 | 이미 보유 중인 경우의 매도/유지 판단 (아래 표 참고) |

**신규진입 / 보유판단 해석 기준**

| 신규진입 | 조건 | 보유판단 | 조건 |
|---|---|---|---|
| ✅ 진입 적합 | 매수신호 ≥ 3, RSI 정상 범위 | ✊ 보유 유지 | 강세 다이버전스 or 매수신호 ≥ 3 |
| ⏳ 조정 후 진입 | 매수신호 ≥ 3, RSI 과매수 (지금 아닌 눌릴 때 진입) | ⚠️ 부분 차익 검토 | RSI 과매수 + 매도신호 ≥ 2 (다이버전스 없음) |
| 🔍 분할 매수 검토 | 과매도 + 강세 다이버전스 | 🚨 매도 검토 | 약세 다이버전스 + 매도신호 ≥ 3, or 매도신호 4~5 |
| ⛔ 진입 보류 | 매도신호 ≥ 4, or 약세 다이버전스 + 매도신호 ≥ 2 | | |
| 👀 관망 | 신호 혼재, 방향 불명확 | | |

> **신규진입과 보유판단은 다른 기준입니다.** 보유 중이라면 추세가 살아있는 한 계속 들고 가는 것이 유리하고, 신규 진입은 과매수 구간을 피해야 합니다. 같은 종목이라도 두 판단이 다를 수 있습니다.

**RSI 다이버전스 4종 해석** (가격 피봇은 Low/High 기준, RSI는 종가 기준)

| 신호 | 가격 | RSI | 의미 |
|---|---|---|---|
| 🟢 일반강세 | 저점(Low) **낮아짐** | RSI 저점 **높아짐** | 하락 모멘텀 약화 → **반등** 선행 신호 |
| 🔴 일반약세 | 고점(High) **높아짐** | RSI 고점 **낮아짐** | 상승 모멘텀 약화 → **조정** 선행 신호 |
| 🔵 숨겨진강세 | 저점(Low) **높아짐** | RSI 저점 **낮아짐** | 조정 중 RSI 눌림 → **상승 추세 지속** |
| 🟠 숨겨진약세 | 고점(High) **낮아짐** | RSI 고점 **높아짐** | 반등 중 RSI 과열 → **하락 추세 지속** |
| - | 해당 없음 | — | 가격·RSI 방향 일치, 현재 추세 유효 |

> **일반 다이버전스**는 추세 반전 신호, **숨겨진 다이버전스**는 추세 지속 신호입니다. 최근 3개월(63거래일) 스윙 기준. 반드시 다른 지표와 교차 확인하세요.

**RSI해석 구간 기준**

| RSI 구간 | 방향 ↑ | 방향 ↓ |
|---|---|---|
| > 70 (과매수) | 🔴 과매수 심화 | 🔴 과매수 완화 |
| 60~70 | ⚠️ 과매수 접근 | 고점 이탈 중 |
| 50~60 | 모멘텀 강세 | 모멘텀 약화 |
| 40~50 | 회복 중 | 하락세 |
| 30~40 | ↑ 반등 시도 | 과매도 근접 |
| < 30 (과매도) | ↑ 바닥 반등 중 | 바닥 하락 지속 |

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
    c3.metric("금리차 10Y-2Y", f"{spread:.1f}%",
              "역전 (경기침체 경고)" if spread < 0 else "정상",
              delta_color="inverse" if spread < 0 else "normal")
    c4.metric("DXY 달러지수", f"{mac.get('dxy', 0):.1f}")
    gap = sp.get("gap_pct", 0)
    c5.metric("S&P500 vs 200MA",
              f"{gap:+.1f}%",
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
                text=[f"{v:+.1f}%" for v in sec_df["1일(%)"]],
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

        # 주봉 RSI 병합
        weekly = fetch_weekly_rsi(all_tickers)
        tech_df["주봉RSI"] = tech_df["티커"].map(weekly)

        # 신규진입 / 보유판단 종합 해석
        tech_df[["신규진입", "보유판단"]] = tech_df.apply(
            lambda r: pd.Series(position_guidance(r)), axis=1
        )

        ts_label = f"현재가: {rt_ts} 기준 (분봉 15분 지연)" if rt_ts else "현재가: 전일 종가 기준"
        st.caption(
            f"{ts_label} | S&P500 — 1개월: {sp_ret['1m']:+.1f}%  "
            f"3개월: {sp_ret['3m']:+.1f}%  12개월: {sp_ret['12m']:+.1f}%"
        )
        display_cols = [
            "티커", "종목명", "현재가",
            "RSI(14)", "RSI해석", "RSI다이버전스", "신규진입", "보유판단",
            "1개월(%)", "3개월(%)",
            "매수신호", "매도신호", "신호 내역",
        ]
        display_cols = [c for c in display_cols if c in tech_df.columns]
        fmt = {k: v for k, v in TECH_COL_FMT.items() if k in display_cols}
        st.dataframe(
            tech_df[display_cols]
            .style.apply(highlight_signals, axis=1)
            .format(fmt, na_rep="-"),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("기술분석 데이터를 불러오는 중입니다...")

    # ── Claude 섹터별 추천 ────────────────────────────────────────────────────
    st.divider()
    st.markdown("##### Claude 섹터별 추천 (시황 기반)")
    st.caption("2026-05-08 웹검색 갱신 | PLTR Q1 +85%·AMD +38% 어닝 서프라이즈, AI·사이버보안·헬스케어 유지. S&P 7,500 목표.")

    us_extra_tickers = tuple(t for picks in US_CLAUDE_PICKS.values() for t in picks)
    with st.spinner("추천 종목 분석 중..."):
        extra_us_df = fetch_technical_signals(us_extra_tickers)

    if not extra_us_df.empty:
        ticker_to_sector = {t: s for s, tickers in US_CLAUDE_PICKS.items() for t in tickers}
        extra_us_df["섹터"] = extra_us_df["티커"].map(ticker_to_sector)
        extra_us_df[["신규진입", "보유판단"]] = extra_us_df.apply(
            lambda r: pd.Series(position_guidance(r)), axis=1
        )
        rt_extra = fetch_realtime_prices(us_extra_tickers)
        for ticker, d in rt_extra.items():
            mask = extra_us_df["티커"] == ticker
            if mask.any():
                extra_us_df.loc[mask, "현재가"] = d["price"]

        ecols = [
            "섹터", "티커", "종목명", "현재가",
            "RSI(14)", "RSI해석", "RSI다이버전스", "신규진입", "보유판단",
            "1개월(%)", "3개월(%)", "매수신호", "매도신호", "신호 내역",
        ]
        ecols = [c for c in ecols if c in extra_us_df.columns]
        efmt  = {k: v for k, v in TECH_COL_FMT.items() if k in ecols}
        st.dataframe(
            extra_us_df[ecols]
            .style.apply(highlight_signals, axis=1)
            .format(efmt, na_rep="-"),
            use_container_width=True, hide_index=True,
        )


def tab_korea() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    st.subheader("한국 시장")

    kr_idx = fetch_korean_indices()
    c1, c2 = st.columns(2)
    for col, name in zip([c1, c2], ["KOSPI", "KOSDAQ"]):
        d = kr_idx.get(name, {})
        price = d.get("price", 0)
        chg   = d.get("change_pct", 0)
        col.metric(
            name,
            f"{price:,.1f}",
            f"{chg:+.1f}%",
            delta_color="normal" if chg >= 0 else "inverse",
        )

    st.divider()
    st.markdown("##### KOSPI 시가총액 상위 10")
    top10 = fetch_kospi_top10()
    kr_tech = pd.DataFrame()
    kr_extra_df = pd.DataFrame()

    if top10.empty:
        st.warning("종목 데이터를 불러올 수 없습니다.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

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
        # 상대강도 + 주봉RSI
        sp_ret = fetch_sp500_returns()
        kr_tech = add_relative_strength(kr_tech, sp_ret)
        weekly_kr = fetch_weekly_rsi(yf_tickers)
        kr_tech["주봉RSI"] = kr_tech["티커"].map(weekly_kr)

        # 현재가: KRX 직접(fdr) 우선 — yfinance .KS는 Yahoo 경유로 최대 1일 지연
        kr_prices = fetch_korean_prices_fdr(tuple(codes))
        price_date = ""
        for code, d in kr_prices.items():
            mask = kr_tech["티커"] == code
            if mask.any():
                kr_tech.loc[mask, "현재가"] = d["price"]
            price_date = d.get("date", "")
        if not kr_prices:
            # fdr 실패 시 yfinance 분봉 fallback
            rt_kr = fetch_realtime_prices(yf_tickers)
            for yf_t, d in rt_kr.items():
                base = yf_t.replace(".KS", "")
                mask = kr_tech["티커"] == base
                if mask.any():
                    kr_tech.loc[mask, "현재가"] = d["price"]

        # 신규진입 / 보유판단
        kr_tech[["신규진입", "보유판단"]] = kr_tech.apply(
            lambda r: pd.Series(position_guidance(r)), axis=1
        )

        if price_date:
            st.caption(f"현재가: {price_date} KRX 종가 기준 (Naver Finance 직접 조회)")

        display_cols = [
            "티커", "종목명", "현재가",
            "RSI(14)", "RSI해석", "RSI다이버전스", "신규진입", "보유판단",
            "1개월(%)", "3개월(%)",
            "매수신호", "매도신호", "신호 내역",
        ]
        display_cols = [c for c in display_cols if c in kr_tech.columns]
        fmt = {k: v for k, v in TECH_COL_FMT.items() if k in display_cols}
        fmt["현재가"] = "{:,.0f}"  # 원화 — 정수 + 천단위 콤마
        st.dataframe(
            kr_tech[display_cols]
            .style.apply(highlight_signals, axis=1)
            .format(fmt, na_rep="-"),
            use_container_width=True, hide_index=True,
        )
    else:
        st.warning("yfinance에서 한국 종목 데이터를 가져오지 못했습니다.")

    # ── Claude 한국 섹터별 추천 ───────────────────────────────────────────────
    st.divider()
    st.markdown("##### Claude 한국 섹터별 추천 (시황 기반)")
    st.caption("2026-05-08 웹검색 갱신 | KOSPI 7,000 돌파(5/6). 한화에어로스페이스 목표가 170만·전원매수, LIG넥스원 천궁-II 양산 본격화.")

    kr_extra_codes  = [c for picks in KR_CLAUDE_PICKS.values() for c in picks]
    kr_extra_tickers = tuple(f"{c}.KS" for c in kr_extra_codes)
    code_to_sector  = {c: s for s, codes in KR_CLAUDE_PICKS.items() for c in codes}

    with st.spinner("한국 추천 종목 분석 중..."):
        kr_extra_df = fetch_technical_signals(kr_extra_tickers)

    if not kr_extra_df.empty:
        kr_extra_df["종목명"] = kr_extra_df["티커"].map(KR_CLAUDE_PICK_NAMES).fillna(kr_extra_df["종목명"])
        kr_extra_df["섹터"]   = kr_extra_df["티커"].map(code_to_sector)
        kr_extra_df[["신규진입", "보유판단"]] = kr_extra_df.apply(
            lambda r: pd.Series(position_guidance(r)), axis=1
        )
        # fdr 현재가 덮어쓰기
        kr_extra_prices = fetch_korean_prices_fdr(tuple(kr_extra_codes))
        for code, d in kr_extra_prices.items():
            mask = kr_extra_df["티커"] == code
            if mask.any():
                kr_extra_df.loc[mask, "현재가"] = d["price"]

        kecols = [
            "섹터", "티커", "종목명", "현재가",
            "RSI(14)", "RSI해석", "RSI다이버전스", "신규진입", "보유판단",
            "1개월(%)", "3개월(%)", "매수신호", "매도신호", "신호 내역",
        ]
        kecols = [c for c in kecols if c in kr_extra_df.columns]
        kefmt  = {k: v for k, v in TECH_COL_FMT.items() if k in kecols}
        kefmt["현재가"] = "{:,.0f}"
        st.dataframe(
            kr_extra_df[kecols]
            .style.apply(highlight_signals, axis=1)
            .format(kefmt, na_rep="-"),
            use_container_width=True, hide_index=True,
        )

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

    return top10, kr_tech, kr_extra_df


def tab_recommendations(phase: str | None, top10: pd.DataFrame, kr_tech: pd.DataFrame, kr_extra: pd.DataFrame | None = None) -> None:
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
        us_tech[["신규진입", "보유판단"]] = us_tech.apply(
            lambda r: pd.Series(position_guidance(r)), axis=1
        )
        rec_cols = ["티커", "종목명", "RSI(14)", "3개월(%)", "신규진입", "보유판단", "신호 내역"]
        rec_cols = [c for c in rec_cols if c in us_tech.columns]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**매수 관심** (매수신호 ≥ 3) — 3개월 수익률순")
            buy_us = (
                us_tech[us_tech["매수신호"] >= 3][rec_cols]
                .sort_values("3개월(%)", ascending=False)
                .copy()
            )
            if not buy_us.empty:
                st.dataframe(buy_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매수신호 ≥3 종목 없음")
        with col2:
            st.markdown("**매도/경계** (매도신호 ≥ 3) — 3개월 수익률 약세순")
            sell_us = (
                us_tech[us_tech["매도신호"] >= 3][rec_cols]
                .sort_values("3개월(%)", ascending=True)
                .copy()
            )
            if not sell_us.empty:
                st.dataframe(sell_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매도신호 ≥3 종목 없음")

    st.divider()

    st.markdown("#### 한국 추천 요약")

    # ── 시총TOP10 + Claude추천 통합 ───────────────────────────────────────────
    combined_parts = []
    if not kr_tech.empty:
        tmp = kr_tech.copy()
        tmp["출처"] = "시총TOP10"
        tmp["섹터"] = ""
        combined_parts.append(tmp)
    if kr_extra is not None and not kr_extra.empty:
        tmp = kr_extra.copy()
        tmp["출처"] = "Claude추천"
        if "섹터" not in tmp.columns:
            tmp["섹터"] = ""
        combined_parts.append(tmp)

    if not combined_parts:
        st.info("한국장 탭을 먼저 로드해주세요.")
    else:
        all_kr = pd.concat(combined_parts, ignore_index=True)

        # ── 외국인 순매매 방향 (참고 컬럼) ──────────────────────────────────
        flow_sign: dict[str, str] = {}
        for code in all_kr["티커"].tolist():
            flow = fetch_investor_flow(str(code))
            if flow is not None and "외국인순매매량" in flow.columns:
                s = flow["외국인순매매량"].sum()
                flow_sign[code] = "▲순매수" if s > 0 else "▼순매도"
        all_kr["외국인(5일)"] = all_kr["티커"].map(flow_sign).fillna("정보없음")

        rec_cols = [
            "출처", "섹터", "종목명",
            "RSI(14)", "RSI해석", "RSI다이버전스", "신규진입", "보유판단",
            "외국인(5일)", "1개월(%)", "3개월(%)", "신호 내역",
        ]
        rec_cols = [c for c in rec_cols if c in all_kr.columns]
        rec_fmt = {k: v for k, v in TECH_COL_FMT.items() if k in rec_cols}

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**매수 관심** (기술매수신호 ≥ 3) — 외국인 방향 참고")
            buy_kr = (
                all_kr[all_kr["매수신호"] >= 3][rec_cols]
                .sort_values("3개월(%)", ascending=False)
                .copy()
            ) if "매수신호" in all_kr.columns else pd.DataFrame()
            if not buy_kr.empty:
                st.dataframe(
                    buy_kr.style.apply(highlight_signals, axis=1).format(rec_fmt, na_rep="-"),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("현재 기술매수신호 ≥3 종목 없음")

        with col2:
            st.markdown("**경계/매도** (기술매도신호 ≥ 3)")
            sell_kr = (
                all_kr[all_kr["매도신호"] >= 3][rec_cols]
                .sort_values("3개월(%)", ascending=True)
                .copy()
            ) if "매도신호" in all_kr.columns else pd.DataFrame()
            if not sell_kr.empty:
                st.dataframe(
                    sell_kr.style.apply(highlight_signals, axis=1).format(rec_fmt, na_rep="-"),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("현재 기술매도신호 ≥3 종목 없음")

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

    with st.expander("⚠️ 데이터 한계 · Claude 추천 기준 · 업데이트 방법 (필독)"):
        st.markdown("""
### 데이터 출처 및 한계

| 항목 | 출처 | 한계 |
|---|---|---|
| 미국 현재가 | Yahoo Finance 분봉 | 약 **15분 지연** — 실시간 매매 참고 부적합 |
| 한국 현재가 | Naver Finance / Yahoo Finance | KRX 공식 동시호가 종가와 **수백~수천 원 차이** 발생 가능. 증권사 앱 가격이 공식 가격 |
| 기술지표 (RSI·MACD·SMA) | Yahoo Finance 일봉 | 현재가 차이가 있어도 장기 추세 분석에 미치는 영향은 미미함 |
| 공포탐욕지수 | CNN Markets API | 실시간이나 간헐적 응답 지연 가능 |

### Claude 섹터 추천 기준

Claude의 추천 종목은 **웹 검색 + 기술적 신호**를 바탕으로 판단합니다.

- 섹터 구조적 트렌드 (성장 산업, 정책 수혜, 사이클)
- 개별 기업 펀더멘털 (파이프라인, 수주, 실적 방향성)
- 대시보드 기술 신호 (RSI·MACD·다이버전스) 교차 확인

> **중요**: Claude의 추천보다 대시보드의 기술적 신호가 **항상 우선**합니다.
> 추천 종목이라도 매도신호 ≥ 3이거나 일반약세 다이버전스가 나타나면 그 신호를 따르세요.

### 추천 종목 업데이트 방법

**Claude Code** (이 환경)에서 아래와 같이 요청하면 됩니다:

```
"추천 종목 업데이트해줘"
"시황 반영해서 Claude 픽 바꿔줘"
"한국 추천 종목 최신화해줘"
```

Claude가 웹 검색으로 현재 시황·뉴스·섹터 흐름을 파악한 후
`US_CLAUDE_PICKS` / `KR_CLAUDE_PICKS` 딕셔너리를 수정하고 GitHub에 자동 배포합니다.
업데이트 주기는 정해진 것 없이 **요청할 때마다** 갱신됩니다.

---
*본 대시보드는 공개 데이터 기반 분석 도구입니다. 투자 조언이 아니며 모든 투자 결정의 책임은 투자자 본인에게 있습니다.*
        """)


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
- 미국: yfinance (15분 지연)
- 한국: Naver Finance / yfinance
- F&G: CNN Markets API
- 기술지표: ta 라이브러리
        """)
        st.divider()
        st.markdown("""
**Claude 추천 업데이트**

Claude Code에서 요청:
> "추천 종목 업데이트해줘"
> "시황 반영해서 픽 바꿔줘"

→ 웹 검색 후 자동 재배포
        """)

    st.title("📊 글로벌 시장 분석 대시보드")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🌐 시장 개요", "🇺🇸 미국장", "🇰🇷 한국장", "📈 매수/매도 추천", "🔍 종목 검진"])

    phase: str | None = None
    top10 = pd.DataFrame()
    kr_tech = pd.DataFrame()
    kr_extra = pd.DataFrame()

    with tab1:
        phase = tab_overview()

    with tab2:
        tab_us(phase)

    with tab3:
        top10, kr_tech, kr_extra = tab_korea()

    with tab4:
        tab_recommendations(phase, top10, kr_tech, kr_extra)

    with tab5:
        st.subheader("종목 검진")
        tab_checkup(phase)


if __name__ == "__main__":
    main()
