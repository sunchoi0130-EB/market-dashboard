from __future__ import annotations

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, ADXIndicator, IchimokuIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, MFIIndicator

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
    "과열": "#FF8800",
    "회복": "#00D4FF",
    "경계": "#FFD700",
    "조정": "#FF6600",
    "공포": "#FF3547",
}

PHASE_SUMMARIES = {
    "강세": "VIX<20·F&G>50·S&P 200MA 위. 성장주·경기민감 섹터 비중 확대 유효.",
    "과열": "VIX<15·F&G>75. 시장 과열 구간. 신규 진입 신중, 일부 차익 고려.",
    "회복": "VIX 20~30 하락 중. 공포 해소 국면. 선별적 분할 매수 검토.",
    "경계": "VIX 방향 불명확. 방어 섹터 비중 유지, 리스크 관리 권장.",
    "조정": "S&P 200MA 하회 또는 VIX 급등. 안전자산 선호, 방어적 대응.",
    "공포": "VIX>30·F&G<20. 극도의 공포. 현금 확보 및 분할 매수 기회 탐색.",
}

PHASE_SECTORS = {
    "강세": {"buy": ["XLK", "XLY", "XLI"],    "sell": ["XLU", "XLP", "XLRE"]},
    "과열": {"buy": ["XLV", "XLP"],            "sell": ["XLK", "XLY", "XLI"]},
    "회복": {"buy": ["XLK", "XLF", "XLI"],    "sell": ["XLU", "XLP"]},
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
            period="3mo",   # VIX 방향 계산에 20거래일 필요
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        close = raw["Close"] if isinstance(raw["Close"], pd.DataFrame) else raw[["Close"]]
        for ticker, key in tickers_map.items():
            if ticker in close.columns:
                series = close[ticker].dropna()
                result[key] = float(series.iloc[-1])
                if key == "vix" and len(series) >= 20:
                    result["vix_5d_ma"]  = float(series.iloc[-5:].mean())
                    result["vix_20d_ma"] = float(series.iloc[-20:].mean())
                    result["vix_falling"] = bool(result["vix_5d_ma"] < result["vix_20d_ma"])
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
            hist = hist.dropna(subset=["Close", "High", "Low", "Volume"])
            # .KS 데이터 부족 시 .KQ(KOSDAQ)로 재시도
            if len(hist) < 52 and ticker.endswith(".KS"):
                alt = ticker.replace(".KS", ".KQ")
                hist = yf.Ticker(alt).history(period="1y", interval="1d", auto_adjust=True)
                hist = hist.dropna(subset=["Close", "High", "Low", "Volume"])
                ticker = alt  # 이후 base 계산에 반영
            if len(hist) < 52:
                continue
            close  = hist["Close"]
            high_s = hist["High"]
            low_s  = hist["Low"]
            vol_s  = hist["Volume"]

            rsi_series = RSIIndicator(close=close, window=14).rsi()
            rsi_val    = float(rsi_series.iloc[-1])
            rsi_5d_ago = float(rsi_series.iloc[-6]) if len(rsi_series) >= 6 else rsi_val
            rsi_delta  = round(rsi_val - rsi_5d_ago, 1)
            rsi_trend  = rsi_context(rsi_val, rsi_delta)
            sma50   = float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1])
            sma200  = float(SMAIndicator(close=close, window=200).sma_indicator().iloc[-1])
            price   = float(close.iloc[-1])

            macd_obj  = MACD(close=close)
            macd_line = float(macd_obj.macd().iloc[-1])
            macd_sig  = float(macd_obj.macd_signal().iloc[-1])

            bb      = BollingerBands(close=close, window=20, window_dev=2)
            bb_low  = float(bb.bollinger_lband().iloc[-1])
            bb_high = float(bb.bollinger_hband().iloc[-1])

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

            # MACD
            if macd_line > macd_sig:
                signals.append("MACD 골든크로스")
                buy_cnt += 1
            else:
                signals.append("MACD 데드크로스")
                sell_cnt += 1

            # 볼린저밴드
            if price < bb_low:
                signals.append("BB 하단 이탈")
                buy_cnt += 1
            elif price > bb_high:
                signals.append("BB 상단 이탈")
                sell_cnt += 1

            # Ichimoku TK 크로스 + 구름 위치
            if len(close) >= 52:
                try:
                    ich = IchimokuIndicator(high=high_s, low=low_s, window1=9, window2=26, window3=52)
                    tenkan = float(ich.ichimoku_conversion_line().iloc[-1])
                    kijun  = float(ich.ichimoku_base_line().iloc[-1])
                    span_a = float(ich.ichimoku_a().iloc[-1])
                    span_b = float(ich.ichimoku_b().iloc[-1])
                    if not (pd.isna(tenkan) or pd.isna(kijun)):
                        if tenkan > kijun:
                            signals.append("Ichimoku 골든TK")
                            buy_cnt += 1
                        else:
                            signals.append("Ichimoku 데드TK")
                            sell_cnt += 1
                    if not (pd.isna(span_a) or pd.isna(span_b)):
                        cloud_top    = max(span_a, span_b)
                        cloud_bottom = min(span_a, span_b)
                        if price > cloud_top:
                            signals.append("구름 위")
                            buy_cnt += 1
                        elif price < cloud_bottom:
                            signals.append("구름 아래")
                            sell_cnt += 1
                except Exception:
                    pass

            # MFI
            if len(close) >= 14:
                try:
                    mfi = float(MFIIndicator(
                        high=high_s, low=low_s, close=close, volume=vol_s, window=14
                    ).money_flow_index().iloc[-1])
                    if not pd.isna(mfi):
                        if mfi < 20:
                            signals.append(f"MFI 과매도({mfi:.0f})")
                            buy_cnt += 1
                        elif mfi > 80:
                            signals.append(f"MFI 과매수({mfi:.0f})")
                            sell_cnt += 1
                except Exception:
                    pass

            # 거래량 (20일 평균 대비)
            if len(vol_s) >= 20:
                vol_avg20 = float(vol_s.iloc[-20:].mean())
                if vol_avg20 > 0:
                    vol_ratio = float(vol_s.iloc[-1]) / vol_avg20
                    if vol_ratio >= 1.5:
                        ret_1w = (price / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0.0
                        if ret_1w > 0:
                            signals.append(f"고거래량 상승({vol_ratio:.1f}x)")
                            buy_cnt += 1
                        elif ret_1w < 0:
                            signals.append(f"고거래량 하락({vol_ratio:.1f}x)")
                            sell_cnt += 1

            # 52주 신고가권
            high52 = float(high_s.max())
            low52  = float(low_s.min())
            pos52  = round((price - low52) / (high52 - low52) * 100, 1) if high52 != low52 else 50.0
            if price >= high52 * 0.95:
                signals.append(f"52주신고가권({pos52:.0f}%)")
                buy_cnt += 1

            # OBV (On Balance Volume) — 누적 거래량 추세
            try:
                obv_series = OnBalanceVolumeIndicator(close=close, volume=vol_s).on_balance_volume()
                if len(obv_series) >= 20:
                    obv_ma20 = float(obv_series.rolling(20).mean().iloc[-1])
                    if not pd.isna(obv_ma20):
                        if float(obv_series.iloc[-1]) > obv_ma20:
                            signals.append("OBV 상승(매집)")
                            buy_cnt += 1
                        else:
                            signals.append("OBV 하락(분산)")
                            sell_cnt += 1
            except Exception:
                pass

            # 모멘텀 수익률
            ret_1m  = round((price / float(close.iloc[-22]) - 1) * 100, 1) if len(close) >= 22 else float("nan")
            ret_3m  = round((price / float(close.iloc[-63]) - 1) * 100, 1) if len(close) >= 63 else float("nan")
            ret_12m = round((price / float(close.iloc[0])   - 1) * 100, 1)

            divergence = detect_rsi_divergence(hist, rsi_series)

            # Weinstein Stage (참고 컬럼 — 신호 카운팅 미포함)
            ws = weinstein_stage(close)
            ws_label = {1: "Stage1-대기", 2: "Stage2-매수", 3: "Stage3-주의", 4: "Stage4-회피"}.get(ws, "-")

            base = ticker.replace(".KS", "").replace(".KQ", "")
            name = TICKER_NAMES.get(base, base)

            rows.append({
                "티커":         ticker.replace(".KS", ""),
                "종목명":       name,
                "현재가":       round(price, 1),
                "RSI(14)":      round(rsi_val, 1),
                "RSI해석":      rsi_trend,
                "RSI다이버전스": divergence,
                "Weinstein":    ws_label,
                "1개월(%)":     ret_1m,
                "3개월(%)":     ret_3m,
                "12개월(%)":    ret_12m,
                "매수신호":     buy_cnt,
                "매도신호":     sell_cnt,
                "신호 내역":    " | ".join(signals),
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
            if len(hist_w) < 14 and ticker.endswith(".KS"):
                alt = ticker.replace(".KS", ".KQ")
                hist_w = yf.Ticker(alt).history(period="2y", interval="1wk", auto_adjust=True)
                ticker = alt
            if len(hist_w) >= 14:
                rsi_w = RSIIndicator(close=hist_w["Close"], window=14).rsi()
                result[ticker.replace(".KS", "").replace(".KQ", "")] = round(float(rsi_w.iloc[-1]), 1)
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


def weinstein_stage(close: pd.Series) -> int | None:
    """
    Stan Weinstein 4단계 분석 (30주 ≈ 150거래일 MA 기반).
    Stage 1: 가격 < MA, MA 횡보/상승 — 바닥 다지기 (대기)
    Stage 2: 가격 > MA, MA 상승     — 상승 추세 (매수 구간)
    Stage 3: 가격 > MA, MA 하락     — 천정 형성 (주의)
    Stage 4: 가격 < MA, MA 하락     — 하락 추세 (매수 금지)
    None: 데이터 170봉 미만으로 계산 불가
    """
    if len(close) < 170:
        return None
    sma150     = SMAIndicator(close=close, window=150).sma_indicator()
    current_ma = float(sma150.iloc[-1])
    past_ma    = float(sma150.iloc[-21])   # 20거래일 전 MA
    above_ma   = float(close.iloc[-1]) > current_ma
    ma_rising  = current_ma > past_ma
    if above_ma and ma_rising:
        return 2
    if above_ma and not ma_rising:
        return 3
    if not above_ma and not ma_rising:
        return 4
    return 1


def determine_phase(
    fg_score: float,
    vix: float,
    yield_spread: float,
    sp_above_200ma: bool,
    vix_falling: bool = False,
) -> str:
    """
    Phase 6 적용: VIX 5d MA vs 20d MA 방향으로 '회복'·'과열' 국면 추가.
    VIX 방향은 CBOE 문서에서 검증된 지표 — 방향성만 사용, 임계값은 보수적으로 설정.
    """
    # 극도 공포
    if vix >= 30 and fg_score < 20:
        return "공포"
    # 과열 (VIX 매우 낮고 F&G 극도 탐욕)
    if vix < 15 and fg_score > 75:
        return "과열"
    # 강세
    if fg_score >= 50 and vix < 20 and yield_spread >= 0 and sp_above_200ma:
        return "강세"
    # 회복 (VIX 20~30 구간이면서 하락 중)
    if 20 <= vix <= 30 and vix_falling and fg_score >= 30:
        return "회복"
    # 조정
    if fg_score < 30 and not sp_above_200ma:
        return "조정"
    if fg_score < 30 and (30 <= vix <= 40):
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
    if row.get("매수신호", 0) >= 7:
        return ["background-color:#0d3b1f"] * len(row)
    if row.get("매도신호", 0) >= 7:
        return ["background-color:#3b0d0d"] * len(row)
    if row.get("매수신호", 0) >= 6:
        return ["background-color:#0a2a15"] * len(row)
    if row.get("매도신호", 0) >= 6:
        return ["background-color:#2a0a0a"] * len(row)
    return [""] * len(row)


def position_guidance(row: pd.Series) -> tuple[str, str]:
    """
    신규진입·보유판단 레이블 (11개 신호 기준 정수 비교).
    ※ 임계값은 휴리스틱 — 백테스팅 미검증. 참고용으로만 사용.

    신규진입: buy >= 6 (55%) → 진입 적합, sell >= 7 (64%) → 진입 보류
    보유판단: buy >= 6 (55%) → 보유 유지, sell >= 7 (64%) → 매도 검토
    """
    buy  = int(row.get("매수신호", 0))
    sell = int(row.get("매도신호", 0))
    rsi  = float(row.get("RSI(14)", 50))
    div  = str(row.get("RSI다이버전스", "-"))

    bearish    = div in ("🔴 일반약세", "🟠 숨겨진약세")
    bullish    = div in ("🟢 일반강세", "🔵 숨겨진강세")
    overbought = rsi >= 70
    oversold   = rsi <= 30

    # 신규 진입
    if sell >= 7 or (bearish and sell >= 5):
        entry = "⛔ 진입 보류"
    elif buy >= 6 and overbought:
        entry = "⏳ 조정 후 진입"
    elif buy >= 6:
        entry = "✅ 진입 적합"
    elif oversold and bullish:
        entry = "🔍 분할 매수 검토"
    else:
        entry = "👀 관망"

    # 보유 판단
    if sell >= 7 or (bearish and sell >= 5):
        hold = "🚨 매도 검토"
    elif overbought and sell >= 4 and not bullish:
        hold = "⚠️ 부분 차익 검토"
    elif buy >= 4 and sell >= 4:
        hold = "👀 신호 혼재"
    elif buy >= 6 or bullish:
        hold = "✊ 보유 유지"
    elif sell >= 5:
        hold = "🚨 매도 검토"
    else:
        hold = "✊ 보유 유지"

    return entry, hold


@st.cache_data(ttl=3600)
def resolve_ticker(query: str) -> list[tuple[str, str, bool]]:
    """
    종목 코드·티커·회사명 모두 수용 → [(raw_code, display_name, is_korean), ...] 반환.
    raw_code: 한국 6자리 코드 or 미국 티커 심볼 (compute_checkup에 그대로 전달 가능).
    """
    q = query.strip()
    results: list[tuple[str, str, bool]] = []

    # ── Case 1: 6자리 숫자 → 한국 코드 직접 사용 ─────────────────────────────
    if q.isdigit() and len(q) == 6:
        name = KR_CLAUDE_PICK_NAMES.get(q, q)
        return [(q, f"{name} ({q})", True)]

    # ── Case 2: 한국어 포함 → KOSPI / KOSDAQ 이름 검색 ──────────────────────
    has_korean = any("가" <= c <= "힣" for c in q)
    if has_korean:
        try:
            for market in ["KOSPI", "KOSDAQ"]:
                listing = fdr.StockListing(market)
                listing.columns = [c.strip() for c in listing.columns]
                name_col = next((c for c in listing.columns if c in ("Name", "name", "종목명")), None)
                code_col = next((c for c in listing.columns if c in ("Code", "Symbol", "code")), None)
                if not name_col or not code_col:
                    continue
                hits = listing[
                    listing[name_col].str.contains(q, na=False) &
                    ~listing[code_col].astype(str).str.endswith("5") &
                    ~listing[name_col].astype(str).str.endswith(("우", "우B", "우C"))
                ]
                for _, row in hits.head(6).iterrows():
                    code = str(row[code_col])
                    name = str(row[name_col])
                    results.append((code, f"{name} ({code}) [{market}]", True))
        except Exception:
            pass
        return results[:10]

    # ── Case 3: 영문 티커처럼 보이면 직접 우선 추가 ──────────────────────────
    q_up = q.upper()
    if q.replace("-", "").replace(".", "").isalpha() and len(q) <= 6:
        results.append((q_up, q_up, False))

    # ── Case 4: yf.Search로 이름 검색 ────────────────────────────────────────
    try:
        search = yf.Search(q, max_results=10)
        US_EXCHANGES = {"NMS", "NYQ", "NGM", "PCX", "ASE", "BTS"}
        for item in search.quotes:
            sym  = item.get("symbol", "")
            name = item.get("longname") or item.get("shortname", sym)
            exch = item.get("exchange", "")
            if item.get("quoteType") != "EQUITY" or not sym:
                continue
            is_kr = sym.endswith(".KS") or sym.endswith(".KQ")
            raw   = sym.replace(".KS", "").replace(".KQ", "") if is_kr else sym
            label = f"{name} ({sym}) [{exch}]"
            entry = (raw, label, is_kr)
            if entry not in results:
                # 미국 거래소 우선 삽입, 나머지는 뒤에
                if exch in US_EXCHANGES:
                    results.insert(0, entry) if not results else results.append(entry)
                else:
                    results.append(entry)
    except Exception:
        pass

    # 중복 제거 (raw_code 기준)
    seen: set[str] = set()
    deduped = []
    for r in results:
        if r[0] not in seen:
            seen.add(r[0])
            deduped.append(r)
    return deduped[:10]


@st.cache_data(ttl=300)
def compute_checkup(ticker_input: str, phase: str) -> dict | None:
    """단일 종목 종합 검진 — RSI·SMA·MACD·BB·거래량·Ichimoku·MFI·Weinstein·Quality."""
    is_korean = ticker_input.isdigit() and len(ticker_input) == 6
    pf = (lambda v: f"{v:,.0f}") if is_korean else (lambda v: f"{v:.2f}")
    try:
        if is_korean:
            yf_ticker = f"{ticker_input}.KS"
            hist = yf.Ticker(yf_ticker).history(period="1y", interval="1d", auto_adjust=True)
            hist = hist.dropna(subset=["Close", "High", "Low", "Volume"])
            if len(hist) < 60:  # KOSPI 실패 → KOSDAQ 시도
                yf_ticker = f"{ticker_input}.KQ"
                hist = yf.Ticker(yf_ticker).history(period="1y", interval="1d", auto_adjust=True)
                hist = hist.dropna(subset=["Close", "High", "Low", "Volume"])
        else:
            yf_ticker = ticker_input.upper()
            hist = yf.Ticker(yf_ticker).history(period="1y", interval="1d", auto_adjust=True)
            hist = hist.dropna(subset=["Close", "High", "Low", "Volume"])
        if len(hist) < 60:
            return None
        close  = hist["Close"]
        high_s = hist["High"]
        low_s  = hist["Low"]
        vol_s  = hist["Volume"]
        price  = float(close.iloc[-1])

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
        macd_hist = round(macd_line - macd_sig, 4)

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

        # ── ADX ──────────────────────────────────────────────────────────────
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

        # ── OBV ──────────────────────────────────────────────────────────────
        obv_series = OnBalanceVolumeIndicator(close=close, volume=vol_s).on_balance_volume()
        obv_rising = bool(obv_series.iloc[-1] > obv_series.rolling(20).mean().iloc[-1])

        # ── ATR ──────────────────────────────────────────────────────────────
        atr_val = float(AverageTrueRange(high=high_s, low=low_s, close=close, window=14).average_true_range().iloc[-1])
        atr_pct = round(atr_val / price * 100, 2)

        # ── Ichimoku (전환선·기준선·구름) ───────────────────────────────────
        ich_available = False
        ich_tenkan = ich_kijun = ich_span_a = ich_span_b = float("nan")
        if len(close) >= 52:
            try:
                ich_obj   = IchimokuIndicator(high=high_s, low=low_s, window1=9, window2=26, window3=52)
                _tenkan   = ich_obj.ichimoku_conversion_line().iloc[-1]
                _kijun    = ich_obj.ichimoku_base_line().iloc[-1]
                _span_a   = ich_obj.ichimoku_a().iloc[-1]
                _span_b   = ich_obj.ichimoku_b().iloc[-1]
                if not any(pd.isna(v) for v in [_tenkan, _kijun, _span_a, _span_b]):
                    ich_tenkan, ich_kijun = float(_tenkan), float(_kijun)
                    ich_span_a, ich_span_b = float(_span_a), float(_span_b)
                    ich_available = True
            except Exception:
                pass

        # ── MFI ──────────────────────────────────────────────────────────────
        mfi_val: float | None = None
        try:
            _mfi = MFIIndicator(high=high_s, low=low_s, close=close, volume=vol_s, window=14).money_flow_index().iloc[-1]
            if not pd.isna(_mfi):
                mfi_val = round(float(_mfi), 1)
        except Exception:
            pass

        # ── Weinstein Stage ───────────────────────────────────────────────────
        ws = weinstein_stage(close)
        _ws_meta = {
            1: ("Stage 1 — 바닥 다지기", "30주 MA 아래·MA 상승/횡보. 추세 전환 대기. 확인 전 진입 자제."),
            2: ("Stage 2 — 상승 추세",   "30주 MA 위·MA 상승. 가장 유리한 매수 구간 (Weinstein 기준)."),
            3: ("Stage 3 — 천정 형성",   "30주 MA 위·MA 하락. 모멘텀 약화, 조정 또는 하락 전환 가능성."),
            4: ("Stage 4 — 하락 추세",   "30주 MA 아래·MA 하락. Weinstein이 정의한 매수 금지 구간."),
        }
        weinstein_label, weinstein_desc = _ws_meta.get(ws, ("N/A", "데이터 부족 (1년 미만)"))

        # ── Quality factors (표시용 — 신호 카운팅 미포함) ────────────────────
        quality: dict[str, float | None] = {}
        try:
            info = yf.Ticker(yf_ticker).info
            raw_per = info.get("trailingPE")
            raw_pbr = info.get("priceToBook")
            raw_roe = info.get("returnOnEquity")
            if raw_per and raw_per > 0:   quality["PER"] = round(float(raw_per), 1)
            if raw_pbr and raw_pbr > 0:   quality["PBR"] = round(float(raw_pbr), 2)
            if raw_roe is not None:        quality["ROE"] = round(float(raw_roe) * 100, 1)
        except Exception:
            pass

        # ── 신호 계산 (단순 카운팅 — 검증된 방향만 사용) ─────────────────────
        buy_score = sell_score = 0
        signal_rows: list[tuple] = []

        def _add(label: str, interp: str, direction: int) -> None:
            nonlocal buy_score, sell_score
            signal_rows.append((label, interp, direction))
            if direction > 0:
                buy_score += 1
            elif direction < 0:
                sell_score += 1

        def _neutral(label: str, interp: str) -> None:
            signal_rows.append((label, interp, 0))

        # RSI
        if rsi_val < 30:
            _add(f"RSI {rsi_val:.1f}", "과매도 → 반등 가능", +1)
        elif rsi_val > 70:
            _add(f"RSI {rsi_val:.1f}", "과매수 → 조정 가능", -1)
        else:
            _neutral(f"RSI {rsi_val:.1f}", rsi_context(rsi_val, rsi_delta))

        # SMA50
        if price > sma50:
            _add(f"SMA50 {pf(sma50)}", "현재가 위 → 단기 상승 추세", +1)
        else:
            _add(f"SMA50 {pf(sma50)}", "현재가 아래 → 단기 하락 추세", -1)

        # SMA200
        if price > sma200:
            _add(f"SMA200 {pf(sma200)}", "현재가 위 → 장기 상승 추세", +1)
        else:
            _add(f"SMA200 {pf(sma200)}", "현재가 아래 → 장기 하락 추세", -1)

        # MACD
        if macd_line > macd_sig:
            _add(f"MACD {macd_hist:+.4f}", "골든크로스 → 상승 모멘텀", +1)
        else:
            _add(f"MACD {macd_hist:+.4f}", "데드크로스 → 하락 모멘텀", -1)

        # 볼린저
        if price < bb_low:
            _add(f"BB {bb_pct:.0f}%", "하단 이탈 → 과매도 극단", +1)
        elif price > bb_high:
            _add(f"BB {bb_pct:.0f}%", "상단 이탈 → 단기 과열", -1)
        else:
            _neutral(f"BB {bb_pct:.0f}%", "밴드 내 정상 범위")

        # 거래량
        if high_vol:
            if pd.notna(ret_1w) and ret_1w > 0:
                _add(f"거래량 {vol_ratio:.1f}배", "고거래량 상승 → 신뢰도 강화", +1)
            elif pd.notna(ret_1w) and ret_1w < 0:
                _add(f"거래량 {vol_ratio:.1f}배", "고거래량 하락 → 매도 압력", -1)
            else:
                _neutral(f"거래량 {vol_ratio:.1f}배", "고거래량 (방향 불명)")
        else:
            _neutral(f"거래량 {vol_ratio:.1f}배", "평균 수준 (중립)")

        # 52주 신고가권
        if near_high:
            _add(f"52주 위치 {pos52:.0f}%", "신고가권 → 모멘텀 지속 가능성", +1)
        else:
            _neutral(f"52주 위치 {pos52:.0f}%", "신고가 미도달 (중립)")

        # Ichimoku TK 크로스
        if ich_available:
            if ich_tenkan > ich_kijun:
                _add(f"Ichimoku TK({pf(ich_tenkan)}/{pf(ich_kijun)})",
                     "전환선 > 기준선 → 단기 상승 압력", +1)
            else:
                _add(f"Ichimoku TK({pf(ich_tenkan)}/{pf(ich_kijun)})",
                     "전환선 < 기준선 → 단기 하락 압력", -1)

            # 가격 vs 구름
            cloud_top    = max(ich_span_a, ich_span_b)
            cloud_bottom = min(ich_span_a, ich_span_b)
            if price > cloud_top:
                _add(f"Ichimoku 구름 위({pf(cloud_top)})",
                     "구름 위 → 강세 추세. 구름이 지지선 역할", +1)
            elif price < cloud_bottom:
                _add(f"Ichimoku 구름 아래({pf(cloud_bottom)})",
                     "구름 아래 → 약세 추세. 구름이 저항선 역할", -1)
            else:
                _neutral(f"Ichimoku 구름 내({pf(cloud_bottom)}~{pf(cloud_top)})",
                         "구름 안 → 추세 불명확 (방향 확인 필요)")

        # MFI
        if mfi_val is not None:
            if mfi_val < 20:
                _add(f"MFI {mfi_val:.1f}", "과매도 → 자금 유입 가능성", +1)
            elif mfi_val > 80:
                _add(f"MFI {mfi_val:.1f}", "과매수 → 자금 이탈 가능성", -1)
            else:
                _neutral(f"MFI {mfi_val:.1f}", "중립 구간 (20~80)")

        # OBV (On Balance Volume) — 누적 거래량 추세
        obv_ma20 = float(obv_series.rolling(20).mean().iloc[-1]) if len(obv_series) >= 20 else float("nan")
        if not pd.isna(obv_ma20):
            if float(obv_series.iloc[-1]) > obv_ma20:
                _add("OBV 상승", "누적 거래량 20MA 위 → 매집 국면 (매수세 우위)", +1)
            else:
                _add("OBV 하락", "누적 거래량 20MA 아래 → 분산 국면 (매도세 우위)", -1)

        # ── 종합 진단 ────────────────────────────────────────────────────────
        synth = pd.Series({
            "매수신호":      buy_score,
            "매도신호":      sell_score,
            "RSI(14)":      rsi_val,
            "RSI다이버전스": divergence,
        })
        entry, hold = position_guidance(synth)

        parts = []
        if not trending:
            parts.append(f"ADX {adx_val:.0f} 횡보장 — SMA·MACD·Ichimoku 등 추세 추종 신호 위신호 주의")
        elif adx_val >= 30:
            parts.append(f"ADX {adx_val:.0f} 강한 추세 — 추세 추종 신호 신뢰도 높음")
        if ws:
            parts.append(f"Weinstein {weinstein_label.split(' — ')[0]}")
        if rsi_val > 70:
            parts.append(f"RSI {rsi_val:.1f} 과매수")
        elif rsi_val < 30:
            parts.append(f"RSI {rsi_val:.1f} 과매도")
        if bb_pct > 100:
            parts.append("BB 상단 이탈")
        elif bb_pct < 0:
            parts.append("BB 하단 이탈")
        if high_vol:
            parts.append(f"거래량 {vol_ratio:.1f}배")
        if divergence != "-":
            parts.append(f"RSI 다이버전스 {divergence}")
        if mfi_val is not None and (mfi_val < 20 or mfi_val > 80):
            parts.append(f"MFI {'과매도' if mfi_val < 20 else '과매수'}")
        comment = " / ".join(parts) if parts else "신호 혼재 — 방향 불명확"

        return {
            "is_korean":       is_korean,
            "price":           price,
            "ret_1w":          _ret(5),
            "ret_1m":          _ret(22),
            "ret_3m":          _ret(63),
            "ret_6m":          _ret(126),
            "ret_1y":          _ret(252) if len(close) >= 252 else round((price / float(close.iloc[0]) - 1) * 100, 1),
            "high52":          high52,
            "low52":           low52,
            "pos52":           pos52,
            "near_high":       near_high,
            "rsi_val":         round(rsi_val, 1),
            "rsi_delta":       rsi_delta,
            "divergence":      divergence,
            "macd_hist":       macd_hist,
            "bb_pct":          bb_pct,
            "bb_low":          round(bb_low, 2),
            "bb_mid":          round(bb_mid, 2),
            "bb_high":         round(bb_high, 2),
            "sma20":           round(sma20, 2),
            "sma50":           round(sma50, 2),
            "sma200":          round(sma200, 2),
            "adx_val":         round(adx_val, 1),
            "adx_pos":         round(adx_pos, 1),
            "adx_neg":         round(adx_neg, 1),
            "trending":        trending,
            "vol_ratio":       vol_ratio,
            "obv_rising":      obv_rising,
            "atr_val":         round(atr_val, 2),
            "atr_pct":         atr_pct,
            "ich_available":   ich_available,
            "ich_tenkan":      round(ich_tenkan, 2) if ich_available else None,
            "ich_kijun":       round(ich_kijun, 2)  if ich_available else None,
            "ich_span_a":      round(ich_span_a, 2) if ich_available else None,
            "ich_span_b":      round(ich_span_b, 2) if ich_available else None,
            "mfi_val":         mfi_val,
            "weinstein_stage": ws,
            "weinstein_label": weinstein_label,
            "weinstein_desc":  weinstein_desc,
            "quality":         quality,
            "buy_score":       buy_score,
            "sell_score":      sell_score,
            "signal_rows":     signal_rows,
            "entry":           entry,
            "hold":            hold,
            "comment":         comment,
        }
    except Exception:
        return None


def tab_checkup(phase: str | None) -> None:
    effective_phase = phase or "경계"
    color = PHASE_COLORS.get(effective_phase, "#FFD700")
    st.markdown(
        f"<div style='padding:10px 14px;background:{color}18;border-left:4px solid {color};"
        f"border-radius:6px;margin-bottom:16px;'>"
        f"현재 국면 <b style='color:{color}'>{effective_phase}</b>"
        + ("" if phase else " &nbsp;—&nbsp; 시장 개요 탭을 먼저 로드하면 자동 갱신됩니다")
        + "</div>",
        unsafe_allow_html=True,
    )

    col_inp, col_btn = st.columns([5, 1])
    with col_inp:
        ticker_raw = st.text_input(
            "ticker",
            placeholder="종목명·티커·코드 모두 가능: 삼성전자 / 현대차 / Apple / AAPL / 005930",
            label_visibility="collapsed",
        )
    with col_btn:
        run = st.button("검진 시작", use_container_width=True)

    st.caption("한국 종목명(한글) · 미국 회사명(영문) · 티커(AAPL) · 한국 코드(005930) 모두 입력 가능")

    if not ticker_raw.strip():
        st.info("종목명이나 코드를 입력 후 [검진 시작] 버튼을 누르세요.")
        return

    with st.spinner("종목 검색 중..."):
        candidates = resolve_ticker(ticker_raw.strip())

    if not candidates:
        st.error(f"**{ticker_raw}** 에 해당하는 종목을 찾을 수 없습니다. 티커 코드로 직접 입력해보세요.")
        return

    if len(candidates) == 1:
        ticker_input, display_name, _ = candidates[0]
        st.caption(f"검색됨: **{display_name}**")
    else:
        labels = [c[1] for c in candidates]
        idx = st.selectbox(
            f"**{len(candidates)}개** 종목이 검색됐습니다. 분석할 종목을 선택하세요:",
            range(len(labels)),
            format_func=lambda i: labels[i],
        )
        ticker_input, display_name, _ = candidates[idx]

    if not run:
        st.info(f"**{display_name}** 을(를) 분석합니다. [검진 시작] 버튼을 누르세요.")
        return

    with st.spinner(f"{display_name} 분석 중..."):
        r = compute_checkup(ticker_input, effective_phase)

    if r is None:
        st.error(f"**{ticker_input}** 데이터를 불러올 수 없습니다. 종목 코드를 확인해주세요.")
        return

    is_kr = r["is_korean"]

    def fmt_p(v: float) -> str:
        return f"{v:,.0f}원" if is_kr else f"${v:,.2f}"

    def fmt_ret(v: float) -> str:
        return f"{v:+.1f}%" if pd.notna(v) else "-"

    def _card(title: str, value: str, explanation: str, bg: str = "#1A1F2E") -> str:
        return (
            f"<div style='padding:14px 16px;background:{bg};border-radius:8px;"
            f"margin-bottom:10px;line-height:1.6'>"
            f"<div style='color:#aaa;font-size:0.8rem;margin-bottom:4px'>{title}</div>"
            f"<div style='font-size:1.15rem;font-weight:600;margin-bottom:6px'>{value}</div>"
            f"<div style='color:#999;font-size:0.82rem'>{explanation}</div>"
            f"</div>"
        )

    # ── 1. 가격 현황 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### {ticker_input.upper()} 검진 결과")

    st.markdown(
        f"<div style='font-size:2rem;font-weight:700;margin-bottom:4px'>{fmt_p(r['price'])}</div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("1주", fmt_ret(r["ret_1w"]))
    c2.metric("1개월", fmt_ret(r["ret_1m"]))
    c3.metric("3개월", fmt_ret(r["ret_3m"]))
    c4.metric("6개월", fmt_ret(r["ret_6m"]))
    c5.metric("1년", fmt_ret(r["ret_1y"]))

    pos52 = r["pos52"]
    filled = int(pos52 / 10)
    bar52 = "▓" * filled + "░" * (10 - filled)
    h_fmt = f"{r['high52']:,.0f}" if is_kr else f"{r['high52']:,.2f}"
    l_fmt = f"{r['low52']:,.0f}" if is_kr else f"{r['low52']:,.2f}"
    st.markdown(
        f"**52주 구간** &nbsp; 최저 `{l_fmt}` &nbsp; {bar52} &nbsp; 최고 `{h_fmt}` "
        f"&nbsp; 현재 위치 **{pos52:.0f}%**"
        + (" &nbsp; ⚡ **52주 신고가권**" if r["near_high"] else "")
    )

    # ── 1.5 Weinstein Stage — 추세 포지션 ────────────────────────────────────
    st.markdown("---")
    ws = r["weinstein_stage"]
    if ws is not None:
        ws_colors = {1: "#FFD700", 2: "#00C851", 3: "#FF8800", 4: "#FF3547"}
        ws_color  = ws_colors.get(ws, "#888")
        st.markdown(
            f"<div style='padding:12px 16px;background:{ws_color}18;"
            f"border-left:4px solid {ws_color};border-radius:8px;margin-bottom:12px'>"
            f"<span style='color:{ws_color};font-weight:700;font-size:1.1rem'>"
            f"Weinstein {r['weinstein_label']}</span><br>"
            f"<span style='color:#aaa;font-size:0.85rem'>{r['weinstein_desc']}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Weinstein Stage: 데이터 1년 미만 — 계산 불가")

    # ── 2. 기술 신호 테이블 ───────────────────────────────────────────────────
    st.markdown("---")
    total_sig = r["buy_score"] + r["sell_score"]
    st.markdown(
        f"#### 기술 신호 &nbsp;"
        f"<span style='color:#00C851'>매수 {r['buy_score']}개</span> / "
        f"<span style='color:#FF3547'>매도 {r['sell_score']}개</span>"
        f"<small style='color:#888;font-weight:normal'> (총 {total_sig}개 신호)</small>",
        unsafe_allow_html=True,
    )

    with st.expander("📖 신호 읽는 법 (클릭)"):
        st.markdown("""
**방향** — +1(매수 신호), -1(매도 신호), 0(중립)

각 신호는 동등하게 1표씩 카운팅됩니다. 가중치 없음 — 검증되지 않은 수치는 사용하지 않습니다.

| 신호 | 뜻 |
|---|---|
| **RSI** | 최근 14일 상승/하락 비율. 70 초과 = 과매수, 30 미만 = 과매도 |
| **SMA50/200** | 50·200일 이동평균. 현재가가 위 = 상승 추세, 아래 = 하락 추세 |
| **MACD** | 단기·장기 이평선 간격. 골든크로스 = 상승 모멘텀, 데드크로스 = 하락 |
| **BB(볼린저밴드)** | 20일 이평 ±2σ. 상단 이탈 = 과열, 하단 이탈 = 과매도 |
| **거래량** | 20일 평균 대비 1.5배 이상 + 가격 방향 결합 |
| **52주 신고가권** | 최고가 95% 이상 = 모멘텀 지속 가능성 |
| **Ichimoku TK** | 전환선(9) vs 기준선(26). 전환 > 기준 = 단기 상승 압력 |
| **Ichimoku 구름** | 가격이 구름 위 = 강세, 구름 아래 = 약세, 구름 안 = 불명 |
| **MFI** | 거래량 반영 RSI. 80 초과 = 자금 이탈, 20 미만 = 자금 유입 |

**ADX** — 추세 강도 (점수 미포함, 신뢰도 참고용). 방향이 아닌 **강도**를 측정. 25 이상 = 추세장(신호 신뢰↑), 25 미만 = 횡보장(가격이 일정 범위 안에서 등락, 추세 추종 신호 위험↑).

**Weinstein Stage** — 30주(150일) MA 기반 4단계. Stage 2(상승 추세)가 진입 적합 구간.
        """)

    if not r["trending"]:
        st.warning(
            f"**ADX {r['adx_val']:.1f} — 횡보장.** "
            f"가격이 뚜렷한 방향 없이 일정 범위 안에서 등락하는 구간입니다. "
            f"이때 SMA·MACD·Ichimoku 같은 **추세 추종 신호는 위신호(false signal)가 잦아** 신뢰도가 떨어집니다. "
            f"RSI·볼린저밴드처럼 과매수/과매도를 보는 **평균회귀 신호는 상대적으로 유효**합니다. "
            f"매수·매도 신호 개수보다 신호 종류를 함께 확인하세요."
        )

    sig_df = pd.DataFrame(r["signal_rows"], columns=["신호", "해석", "방향"])

    def _color_sig(row: pd.Series) -> list[str]:
        if row["방향"] == 1:
            return ["background-color:#0d3b1f"] * len(row)
        if row["방향"] == -1:
            return ["background-color:#3b0d0d"] * len(row)
        return [""] * len(row)

    st.dataframe(sig_df.style.apply(_color_sig, axis=1), use_container_width=True, hide_index=True)

    di_dir = "DI+ 우세 (상승 추세)" if r["adx_pos"] > r["adx_neg"] else "DI- 우세 (하락 추세)"
    trend_label = "추세장 ✓" if r["trending"] else "횡보장 ⚠"
    st.caption(
        f"ADX {r['adx_val']:.1f} ({trend_label}) | {di_dir} "
        f"(DI+ {r['adx_pos']:.1f} / DI- {r['adx_neg']:.1f})"
    )

    # ── 3. 보조 지표 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 보조 지표 <small style='color:#888;font-weight:normal'>— 신호 점수 미포함 참고 정보</small>",
                unsafe_allow_html=True)

    left_col, right_col = st.columns(2)

    # OBV
    obv_val = "📈 상승 중 (매집)" if r["obv_rising"] else "📉 하락 중 (분산)"
    obv_bg  = "#0d2a18" if r["obv_rising"] else "#2a0d0d"
    obv_exp = (
        "오르는 날 거래량이 더 많음 → 기관·세력이 조용히 사 모으고 있다는 신호입니다."
        if r["obv_rising"] else
        "내리는 날 거래량이 더 많음 → 팔려는 세력이 우세하다는 신호입니다."
    )
    left_col.markdown(_card("OBV (거래량 누적 추세)", obv_val,
        f"가격은 속일 수 있어도 거래량은 속이기 어렵습니다. {obv_exp}"), unsafe_allow_html=True)

    # ATR
    atr_str = f"{r['atr_val']:,.0f}원" if is_kr else f"${r['atr_val']:.2f}"
    left_col.markdown(_card("ATR — 14일 평균 일 변동폭",
        f"{atr_str} &nbsp;(현재가 대비 {r['atr_pct']:.1f}%)",
        f"하루에 평균 <b>{r['atr_pct']:.1f}%</b> 움직이는 종목입니다. "
        "손절 기준선 설정이나 포지션 크기 결정 시 이 폭을 기준으로 잡으세요."), unsafe_allow_html=True)

    # MFI 카드
    if r["mfi_val"] is not None:
        mv = r["mfi_val"]
        if mv > 80:
            mfi_bg, mfi_interp = "#2a0d0d", f"과매수({mv:.1f}) — 자금 이탈 징조. RSI 과매수와 함께 나타나면 조정 신호 강화."
        elif mv < 20:
            mfi_bg, mfi_interp = "#0d2a18", f"과매도({mv:.1f}) — 자금 유입 가능성. RSI 과매도와 함께 나타나면 반등 신호 강화."
        else:
            mfi_bg, mfi_interp = "#1A1F2E", f"중립({mv:.1f}, 20~80) — 자금 흐름 방향성 불명확."
        left_col.markdown(_card(
            "MFI — Money Flow Index (거래량 반영 RSI)",
            f"{mv:.1f}",
            f"거래량을 가격 변화에 곱해 계산한 지표. 순수 가격 기반 RSI보다 수급 흐름을 더 잘 반영합니다. {mfi_interp}",
            mfi_bg), unsafe_allow_html=True)

    # 볼린저 밴드
    bp = r["bb_pct"]
    if bp > 100:
        bb_val_str, bb_bg = f"{bp:.0f}% ― 상단 이탈 (과열)", "#2a0d0d"
        bb_exp = (f"현재가({fmt_p(r['price'])})가 상단({fmt_p(r['bb_high'])}) 초과. "
                  "통계적 과열 구간. 신규 진입보다 밴드 내 복귀 후 진입이 유리합니다.")
    elif bp < 0:
        bb_val_str, bb_bg = f"{bp:.0f}% ― 하단 이탈 (과매도)", "#0d2a18"
        bb_exp = (f"현재가({fmt_p(r['price'])})가 하단({fmt_p(r['bb_low'])}) 하회. "
                  "단기 반등 가능성. 강한 하락 추세에서는 이탈 지속 가능.")
    elif bp >= 70:
        bb_val_str, bb_bg = f"{bp:.0f}% ― 상단 근접", "#1f1a0d"
        bb_exp = "상단 근접 — 추가 상승 시 이탈 가능. 신규 진입 시 리스크 감안."
    elif bp <= 30:
        bb_val_str, bb_bg = f"{bp:.0f}% ― 하단 근접", "#0d1f1a"
        bb_exp = "하단 근접 — 지지선 역할 가능. 이탈 시 하락 가속 가능성도 있습니다."
    else:
        bb_val_str, bb_bg = f"{bp:.0f}% ― 밴드 중앙", "#1A1F2E"
        bb_exp = "중립 구간. 상·하단 어느 쪽에도 치우치지 않음."
    right_col.markdown(_card(
        "볼린저 밴드 위치 (0%=하단, 50%=중간선, 100%=상단)",
        bb_val_str,
        f"밴드: 하단 {fmt_p(r['bb_low'])} / 중간 {fmt_p(r['bb_mid'])} / 상단 {fmt_p(r['bb_high'])}. {bb_exp}",
        bb_bg), unsafe_allow_html=True)

    # SMA 카드
    sma_pos    = "위" if r["price"] > r["sma20"] else "아래"
    sma_bg     = "#0d2a18" if r["price"] > r["sma20"] else "#2a0d0d"
    sma20_fmt  = f"{r['sma20']:,.0f}원"  if is_kr else f"${r['sma20']:.2f}"
    sma50_fmt  = f"{r['sma50']:,.0f}원"  if is_kr else f"${r['sma50']:.2f}"
    sma200_fmt = f"{r['sma200']:,.0f}원" if is_kr else f"${r['sma200']:.2f}"
    right_col.markdown(_card(
        "이동평균선 (SMA)",
        f"현재가 SMA20 {sma_pos} &nbsp;|&nbsp; SMA20: {sma20_fmt}",
        f"SMA(이동평균선)은 추세 방향을 보여줍니다. "
        f"현재가 위 = 해당 기간 평균보다 비싸게 거래 중 (상승 추세).<br>"
        f"SMA20: {sma20_fmt} / SMA50: {sma50_fmt} / SMA200: {sma200_fmt}",
        sma_bg), unsafe_allow_html=True)

    # Ichimoku 카드
    if r["ich_available"]:
        pf2 = (lambda v: f"{v:,.0f}원") if is_kr else (lambda v: f"${v:.2f}")
        cloud_top    = max(r["ich_span_a"], r["ich_span_b"])
        cloud_bottom = min(r["ich_span_a"], r["ich_span_b"])
        if r["price"] > cloud_top:
            ich_pos, ich_bg = f"구름 위 → 강세 추세", "#0d2a18"
            ich_exp = "가격이 구름 위에 있습니다. 구름이 지지선 역할을 합니다."
        elif r["price"] < cloud_bottom:
            ich_pos, ich_bg = f"구름 아래 → 약세 추세", "#2a0d0d"
            ich_exp = "가격이 구름 아래에 있습니다. 구름이 저항선 역할을 합니다."
        else:
            ich_pos, ich_bg = "구름 내부 → 추세 불명", "#1A1F2E"
            ich_exp = "가격이 구름(Kumo) 안에 있습니다. 방향 전환 구간으로 신호가 혼재합니다."
        tk_dir = "전환선 > 기준선 (단기 강세)" if r["ich_tenkan"] > r["ich_kijun"] else "전환선 < 기준선 (단기 약세)"
        right_col.markdown(_card(
            "Ichimoku 일목균형표",
            ich_pos,
            f"TK크로스: {tk_dir}<br>"
            f"전환선(9일): {pf2(r['ich_tenkan'])} / 기준선(26일): {pf2(r['ich_kijun'])}<br>"
            f"구름: 상단 {pf2(cloud_top)} / 하단 {pf2(cloud_bottom)}<br>"
            f"{ich_exp} 한국 기관·외국인 트레이더가 가장 많이 참조하는 지표 중 하나입니다.",
            ich_bg), unsafe_allow_html=True)

    # Quality 카드 (한국 종목 또는 미국 종목 무관하게 표시)
    q = r.get("quality", {})
    if q:
        q_lines = []
        if "PER" in q:
            q_lines.append(f"PER: {q['PER']:.1f}배 — 주가/EPS. 낮을수록 상대적 저평가 가능성 (업종 평균 비교 필요)")
        if "PBR" in q:
            q_lines.append(f"PBR: {q['PBR']:.2f}배 — 주가/장부가. 1 미만이면 청산가치 이하")
        if "ROE" in q:
            q_lines.append(f"ROE: {q['ROE']:.1f}% — 자기자본수익률. 높을수록 자본 효율성 우수")
        if q_lines:
            left_col.markdown(_card(
                "밸류에이션 (참고용 — 기술적 신호와 무관)",
                " / ".join(
                    [f"PER {q['PER']:.1f}배" if "PER" in q else "",
                     f"PBR {q['PBR']:.2f}배" if "PBR" in q else "",
                     f"ROE {q['ROE']:.1f}%" if "ROE" in q else ""]
                ).strip(" /"),
                "<br>".join(q_lines) +
                "<br><span style='color:#666'>출처: Yahoo Finance. 지연 데이터. 투자 조언 아님.</span>",
            ), unsafe_allow_html=True)

    # ── 4. 종합 진단 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 종합 진단")
    st.caption(
        f"총 {total_sig}개 신호 중 매수 {r['buy_score']}개 / 매도 {r['sell_score']}개. "
        "3개 이상이면 해당 방향 신호 우세로 판단. "
        "Weinstein Stage 2 + 매수신호 ≥ 3 조합이 가장 선호되는 진입 조건입니다."
    )

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("매수신호", f"{r['buy_score']}개",
              "✓ 3개 이상 — 진입 고려" if r["buy_score"] >= 3 else "3개 미달")
    g2.metric("매도신호", f"{r['sell_score']}개",
              "⚠ 3개 이상 — 경계 요망" if r["sell_score"] >= 3 else "3개 미달",
              delta_color="inverse")
    g3.metric("신규진입 판단", r["entry"])
    g4.metric("보유 판단", r["hold"])

    st.caption(
        "신규진입: 지금 처음 사는 경우의 타이밍 판단. "
        "보유판단: 이미 보유 중인 경우 매도/유지 판단. "
        "같은 종목이라도 두 판단이 다를 수 있습니다."
    )

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
### 매수/매도 신호 숫자란?

11개 지표 각각이 매수 또는 매도 조건을 충족하면 +1씩 셉니다.
**6개 이상**이면 과반 지표가 같은 방향을 가리키는 것입니다.

> 숫자가 높다고 무조건 좋은 게 아닙니다. 어떤 종류의 신호인지, 시장이 추세장인지 횡보장인지(ADX 참고)를 함께 봐야 합니다.

---

### 신호 11개 — 종류별로 특성이 다릅니다

**🔵 추세 추종 신호 (6개) — 추세장에서 신뢰도 높음, 횡보장에선 위신호 주의**

이 신호들은 "지금 방향이 살아있는가"를 봅니다. 주가가 뚜렷하게 오르거나 내릴 때 잘 맞고, 가격이 옆으로만 횡보할 때는 자주 틀립니다 (ADX < 25면 해당).

| 신호 | 매수 조건 | 매도 조건 | 한 줄 해석 |
|---|---|---|---|
| SMA50 (50일 이평선) | 현재가 위 | 현재가 아래 | 최근 2개월 평균보다 비싸면 단기 추세 살아있음 |
| SMA200 (200일 이평선) | 현재가 위 | 현재가 아래 | 1년 평균보다 비싸면 장기 추세도 살아있음. 가장 중요한 선 |
| MACD | 골든크로스 | 데드크로스 | 단기 이평이 장기 이평을 뚫고 올라오면 상승 모멘텀 시작 신호 |
| Ichimoku TK크로스 | 전환선 > 기준선 | 전환선 < 기준선 | 9일선이 26일선 위면 단기 주도권이 매수 측에 있음 |
| Ichimoku 구름 위치 | 구름 위 | 구름 아래 | 구름은 지지/저항 영역. 구름 위면 추세가 강하고 구름이 버팀목 역할 |
| OBV (누적 거래량) | 20일 MA 위 | 20일 MA 아래 | 거래량을 누적해 매수세·매도세 중 어느 쪽이 더 쌓이고 있는지 확인 |

**🟡 과매수/과매도 신호 (3개) — 추세장·횡보장 모두 유효**

이 신호들은 "지금 너무 오르거나 내려서 반전 가능성이 있는가"를 봅니다. 횡보장에서도 비교적 신뢰할 수 있습니다.

| 신호 | 매수 조건 | 매도 조건 | 한 줄 해석 |
|---|---|---|---|
| RSI(14) | **< 30** 과매도 | **> 70** 과매수 | 14일 기준 상승 에너지 비율. 30 이하면 너무 많이 내려 반등 여지, 70 이상이면 너무 많이 올라 조정 가능성 |
| 볼린저밴드 (20일, 2σ) | 하단 이탈 | 상단 이탈 | 통계적으로 가격의 95%가 밴드 안에 있어야 정상. 이탈은 극단적 과매도/과매수 |
| MFI | **< 20** | **> 80** | RSI에 거래량을 추가한 버전. 자금이 실제로 들어오는지(유입) 빠지는지(이탈) 확인 |

> RSI 중립(30~70)이면 신호 없음. 볼린저밴드 안에 있으면 신호 없음. 조건 충족 시에만 카운팅됩니다.

**🟠 수급·모멘텀 신호 (2개) — 다른 신호를 보완하는 역할**

| 신호 | 매수 조건 | 매도 조건 | 한 줄 해석 |
|---|---|---|---|
| 거래량 (20일 평균 1.5배↑) | 고거래량 + 상승 | 고거래량 + 하락 | 평소보다 거래가 몰리면서 가격이 움직이면 방향 신뢰도 높아짐. 거래 없는 상승은 약함 |
| 52주 신고가권 (≥95%) | 신고가 근처 | — (매수만) | 1년 고점 근처에서도 계속 강하면 모멘텀이 살아있다는 신호. 매도 신호는 없음 |

> 이론적 최대: 매수 11개, 매도 10개 (52주신고가는 매수만).

---

### 배경색 의미

- **진한 초록**: 매수신호 7개↑ (64%) — 강한 매수 우세
- **연한 초록**: 매수신호 6개↑ (55%) — 매수 관심
- **진한 빨강**: 매도신호 7개↑ (64%) — 강한 매도 우세
- **연한 빨강**: 매도신호 6개↑ (55%) — 매도 경계

---

### 신규진입 / 보유판단

**신규진입** — 지금 처음 살 때의 타이밍 판단

| 결과 | 의미 | 조건 |
|---|---|---|
| ✅ 진입 적합 | 과반 신호가 매수, RSI도 과열 아님 | 매수신호 ≥ 6개, RSI < 70 |
| ⏳ 조정 후 진입 | 방향은 좋은데 RSI가 이미 과열 — 눌릴 때 기다릴 것 | 매수신호 ≥ 6개, RSI ≥ 70 |
| 🔍 분할 매수 검토 | 너무 내려 반등 가능성, 단 확신은 낮음 — 한 번에 사지 말고 나눠서 | RSI < 30 + 강세 다이버전스 |
| ⛔ 진입 보류 | 매도 신호가 압도적이거나 추세 약화 조짐 | 매도신호 ≥ 7개, 또는 약세 다이버전스 + 매도신호 ≥ 5개 |
| 👀 관망 | 방향이 불명확 — 기다리는 것도 전략 | 위 조건 모두 미해당 |

**보유판단** — 이미 보유 중일 때의 판단 (진입보다 기준이 너그러움)

| 결과 | 의미 | 조건 |
|---|---|---|
| ✊ 보유 유지 | 추세가 살아있음 — 굳이 팔 이유 없음 | 매수신호 ≥ 6개, 또는 강세 다이버전스 |
| ⚠️ 부분 차익 검토 | 많이 올라 과열 조짐 — 전량 매도 아닌 일부 수익 실현 고려 | RSI ≥ 70 + 매도신호 ≥ 4개 |
| 👀 신호 혼재 | 매수·매도 신호가 동시에 많음 — 추세 전환 구간일 수 있어 주의 | 매수 ≥ 4개 & 매도 ≥ 4개 동시 |
| 🚨 매도 검토 | 대부분 신호가 매도 방향 — 보유 명분이 약해짐 | 매도신호 ≥ 7개, 또는 약세 다이버전스 + 매도신호 ≥ 5개 |

> **신규진입 ≠ 보유판단**: 진입은 타이밍(과열 피하기)이 중요하고, 보유는 추세(살아있는 한 유지)에 초점을 둡니다. 같은 종목도 두 판단이 다를 수 있습니다.

> ⚠️ 임계값(6개, 7개)은 백테스팅 미검증 휴리스틱. 참고용으로만 사용하세요.

---

### Weinstein 단계 (참고용 — 신호 카운팅 미포함)

30주(약 150일) 이동평균선의 위치와 방향으로 종목의 큰 사이클을 4단계로 구분합니다.

| 단계 | 상황 | 진입 판단 |
|---|---|---|
| Stage 1 — 바닥 다지기 | MA 아래지만 MA가 내리지 않고 횡보 중 | 아직 대기. 상승 전환 확인 후 진입 |
| **Stage 2 — 상승 추세** | MA 위에서 MA도 계속 상승 중 | **최적 진입·보유 구간** |
| Stage 3 — 천정 형성 | MA 위지만 MA가 꺾이기 시작 | 모멘텀 약화. 신규 진입 자제, 보유자는 경계 |
| Stage 4 — 하락 추세 | MA 아래에서 MA도 하락 중 | 진입 금지. 보유자는 매도 검토 |

---

### RSI 다이버전스 — 가격과 RSI 방향이 엇갈릴 때 나타나는 선행 신호

가격은 올라가는데 RSI는 내려오고 있다면? 올라가는 힘이 약해지고 있다는 뜻입니다. 반전 신호일 수 있습니다.

| 신호 | 가격 | RSI | 무슨 뜻인가 |
|---|---|---|---|
| 🟢 일반강세 다이버전스 | 저점이 **더 낮아짐** | RSI 저점은 **더 높아짐** | 계속 내려가는데 하락 힘이 약해지고 있음 → **반등 선행 신호** |
| 🔴 일반약세 다이버전스 | 고점이 **더 높아짐** | RSI 고점은 **더 낮아짐** | 계속 올라가는데 상승 힘이 약해지고 있음 → **조정 선행 신호** |
| 🔵 숨겨진강세 다이버전스 | 저점이 **더 높아짐** | RSI 저점은 **더 낮아짐** | 눌림목 중에 RSI가 더 깊이 내려왔지만 가격은 안 내려옴 → **상승 추세 지속 신호** |
| 🟠 숨겨진약세 다이버전스 | 고점이 **더 낮아짐** | RSI 고점은 **더 높아짐** | 반등 중에 RSI가 더 높아졌지만 가격은 안 올라옴 → **하락 추세 지속 신호** |

> 다이버전스는 **선행 신호**라 반드시 실현된다는 보장이 없습니다. 다른 지표와 교차 확인 필수.
> 최근 63거래일(약 3개월) 스윙 피봇 기준으로 감지됩니다.

---

### RSI 해석 구간

RSI 숫자 자체 + 5일 전 대비 방향을 합쳐서 해석합니다.

| RSI 구간 | 방향 상승 중 ↑ | 방향 하락 중 ↓ |
|---|---|---|
| 70 초과 (과매수) | 과열 심화 — 조정 위험 높음 | 과열에서 내려오는 중 — 조정 시작 가능 |
| 60~70 | 강세 지속, 과매수 근접 주의 | 고점 이탈 조짐 |
| 50~60 | 중립에서 강세 방향 | 강세 약화 중 |
| 40~50 | 약세에서 회복 중 | 중립 아래로 밀리는 중 |
| 30~40 | 과매도 근처에서 반등 시도 | 과매도 접근 중 |
| 30 미만 (과매도) | 바닥에서 반등 중 — 반등 가능성 높음 | 과매도 심화 — 추가 하락 주의 |

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
        mac.get("vix_falling", False),
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
            "RSI(14)", "RSI해석", "RSI다이버전스", "Weinstein",
            "신규진입", "보유판단",
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
                base = yf_t.replace(".KS", "").replace(".KQ", "")
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
            "RSI(14)", "RSI해석", "RSI다이버전스", "Weinstein",
            "신규진입", "보유판단",
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
            st.markdown("**매수 관심** (매수신호 ≥ 6, 55%↑) — 3개월 수익률순")
            buy_us = (
                us_tech[us_tech["매수신호"] >= 6][rec_cols]
                .sort_values("3개월(%)", ascending=False)
                .copy()
            )
            if not buy_us.empty:
                st.dataframe(buy_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매수신호 ≥5 종목 없음")
        with col2:
            st.markdown("**매도/경계** (매도신호 ≥ 6, 55%↑) — 3개월 수익률 약세순")
            sell_us = (
                us_tech[us_tech["매도신호"] >= 6][rec_cols]
                .sort_values("3개월(%)", ascending=True)
                .copy()
            )
            if not sell_us.empty:
                st.dataframe(sell_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매도신호 ≥5 종목 없음")

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
            st.markdown("**매수 관심** (기술매수신호 ≥ 6, 55%↑) — 외국인 방향 참고")
            buy_kr = (
                all_kr[all_kr["매수신호"] >= 6][rec_cols]
                .sort_values("3개월(%)", ascending=False)
                .copy()
            ) if "매수신호" in all_kr.columns else pd.DataFrame()
            if not buy_kr.empty:
                st.dataframe(
                    buy_kr.style.apply(highlight_signals, axis=1).format(rec_fmt, na_rep="-"),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("현재 기술매수신호 ≥5 종목 없음")

        with col2:
            st.markdown("**경계/매도** (기술매도신호 ≥ 6, 55%↑)")
            sell_kr = (
                all_kr[all_kr["매도신호"] >= 6][rec_cols]
                .sort_values("3개월(%)", ascending=True)
                .copy()
            ) if "매도신호" in all_kr.columns else pd.DataFrame()
            if not sell_kr.empty:
                st.dataframe(
                    sell_kr.style.apply(highlight_signals, axis=1).format(rec_fmt, na_rep="-"),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("현재 기술매도신호 ≥5 종목 없음")

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
