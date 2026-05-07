from __future__ import annotations

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator

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
def fetch_us_indices() -> pd.DataFrame:
    tickers = list(US_INDICES.keys())
    try:
        raw = yf.download(
            tickers, period="5d", interval="1d",
            auto_adjust=True, progress=False,
        )
        close = raw["Close"]
        latest = close.iloc[-1]
        prev = close.iloc[-2]
        rows = []
        for t in tickers:
            cur = float(latest[t]) if t in latest else float("nan")
            prv = float(prev[t]) if t in prev else float("nan")
            chg = (cur - prv) / prv * 100 if prv else float("nan")
            rows.append({"지수": US_INDICES[t], "현재가": cur, "등락률(%)": round(chg, 2)})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


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
            "ETF":    tickers,
            "섹터":   list(SECTOR_ETFS.values()),
            "1일(%)": [round(float(p1d[t]), 2) for t in tickers],
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
            close = hist["Close"]
            rsi_val = float(RSIIndicator(close=close, window=14).rsi().iloc[-1])
            sma50   = float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1])
            sma200  = float(SMAIndicator(close=close, window=200).sma_indicator().iloc[-1])
            price   = float(close.iloc[-1])

            buy_cnt = sell_cnt = 0
            signals = []
            if rsi_val < 30:
                signals.append("RSI 과매도")
                buy_cnt += 1
            elif rsi_val > 70:
                signals.append("RSI 과매수")
                sell_cnt += 1
            if price > sma50:
                signals.append("SMA50 위")
                buy_cnt += 1
            else:
                signals.append("SMA50 아래")
                sell_cnt += 1
            if price > sma200:
                signals.append("SMA200 위")
                buy_cnt += 1
            else:
                signals.append("SMA200 아래")
                sell_cnt += 1

            rows.append({
                "티커":     ticker,
                "현재가":   round(price, 2),
                "RSI(14)":  round(rsi_val, 1),
                "SMA50":    round(sma50, 2),
                "SMA200":   round(sma200, 2),
                "신호":     " | ".join(signals),
                "매수신호": buy_cnt,
                "매도신호": sell_cnt,
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=600)
def fetch_korean_indices() -> dict:
    result: dict[str, dict] = {}
    for symbol, name in [("KS11", "KOSPI"), ("KQ11", "KOSDAQ")]:
        try:
            df = fdr.DataReader(symbol, start=(pd.Timestamp.today() - pd.Timedelta(days=14)).strftime("%Y-%m-%d"))
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
        cols = [c for c in ["Code", "Name", "Close", "Marcap"] if c in listing.columns]
        top10 = listing.head(10)[cols].copy()
        if "Marcap" in top10.columns:
            top10["시총(조)"] = (top10["Marcap"] / 1e12).round(1)
            top10 = top10.drop(columns=["Marcap"])
        top10 = top10.rename(columns={"Code": "코드", "Name": "종목명", "Close": "현재가"})
        return top10.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


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
            text-align:center;
            padding:24px 16px;
            background:{color}18;
            border:2px solid {color};
            border-radius:14px;
            margin-bottom:16px;
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


def color_val(val: float) -> str:
    if val > 0:
        return f"<span style='color:#00C851'>+{val:.2f}%</span>"
    elif val < 0:
        return f"<span style='color:#FF3547'>{val:.2f}%</span>"
    return f"{val:.2f}%"


def highlight_signals(row: pd.Series) -> list[str]:
    if row.get("매수신호", 0) >= 2:
        return ["background-color:#0d3b1f"] * len(row)
    if row.get("매도신호", 0) >= 2:
        return ["background-color:#3b0d0d"] * len(row)
    return [""] * len(row)


def fg_score_bar(score: float) -> str:
    pct = int(score)
    if score < 25:
        bar_color = "#FF3547"
    elif score < 45:
        bar_color = "#FF8800"
    elif score < 55:
        bar_color = "#FFD700"
    elif score < 75:
        bar_color = "#90EE90"
    else:
        bar_color = "#00C851"
    return (
        f"<div style='background:#333;border-radius:6px;height:12px;width:100%;'>"
        f"<div style='background:{bar_color};width:{pct}%;height:100%;border-radius:6px;'></div>"
        f"</div>"
    )


# ── Tabs ──────────────────────────────────────────────────────────────────────


def tab_overview() -> str | None:
    st.subheader("글로벌 시장 국면")

    fg   = fetch_fear_greed()
    mac  = fetch_macro_data()
    sp   = fetch_sp500_ma()

    if not fg or not mac or not sp:
        st.error("핵심 데이터를 로드할 수 없습니다. 잠시 후 다시 시도하세요.")
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
    c2.metric("VIX", f"{vix:.1f}", "위험" if vix > 30 else ("주의" if vix > 20 else "안정"), delta_color="inverse")
    spread = mac.get("yield_spread", 0)
    c3.metric("금리차 10Y-2Y", f"{spread:.2f}%", "역전" if spread < 0 else "정상", delta_color="inverse" if spread < 0 else "normal")
    c4.metric("DXY 달러지수", f"{mac.get('dxy', 0):.2f}")
    gap = sp.get("gap_pct", 0)
    c5.metric("S&P500 vs 200MA", f"{gap:+.2f}%", "위" if gap > 0 else "아래", delta_color="normal" if gap > 0 else "inverse")

    st.divider()

    # Fear & Greed gauge
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
            template="plotly_dark",
            height=260,
            margin=dict(t=40, b=0, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_history:
        st.markdown("##### 기간별 비교")
        h_data = {
            "기간": ["현재", "1주 전", "1개월 전", "1년 전"],
            "점수": [fg["score"], fg["prev_1w"], fg["prev_1m"], fg["prev_1y"]],
        }
        h_df = pd.DataFrame(h_data)
        fig2 = go.Figure(go.Bar(
            x=h_df["기간"],
            y=h_df["점수"],
            marker_color=["#00D4FF", "#5588aa", "#336688", "#224455"],
            text=h_df["점수"],
            textposition="outside",
        ))
        fig2.update_layout(
            template="plotly_dark",
            height=260,
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
            sub_df = pd.DataFrame(rows)
            st.dataframe(sub_df, use_container_width=True, hide_index=True)

    return phase


def tab_us(phase: str | None) -> None:
    st.subheader("미국 주요 지수")

    col_idx, col_sec = st.columns([1, 2])

    with col_idx:
        idx_df = fetch_us_indices()
        if not idx_df.empty:
            def color_row(row: pd.Series) -> list[str]:
                chg = row.get("등락률(%)", 0)
                if chg > 0:
                    return ["", "", "color:#00C851"]
                elif chg < 0:
                    return ["", "", "color:#FF3547"]
                return ["", "", ""]
            st.dataframe(
                idx_df.style.apply(color_row, axis=1),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("지수 데이터를 불러오는 중입니다...")

    with col_sec:
        st.markdown("##### 섹터 ETF 1일 등락률")
        sec_df = fetch_sector_performance()
        if not sec_df.empty:
            bar_colors = ["#00C851" if v > 0 else "#FF3547" for v in sec_df["1일(%)"]]
            fig = go.Figure(go.Bar(
                x=sec_df["ETF"],
                y=sec_df["1일(%)"],
                marker_color=bar_colors,
                text=[f"{v:+.2f}%" for v in sec_df["1일(%)"]],
                textposition="outside",
                hovertext=sec_df["섹터"],
            ))
            fig.update_layout(
                template="plotly_dark",
                height=300,
                margin=dict(t=20, b=0, l=0, r=0),
                yaxis_title="등락률(%)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    # Sector 1-month comparison
    if not sec_df.empty:
        st.markdown("##### 섹터 1개월 성과")
        fig2 = go.Figure(go.Bar(
            x=sec_df["ETF"],
            y=sec_df["1개월(%)"],
            marker_color=["#00C851" if v > 0 else "#FF3547" for v in sec_df["1개월(%)"]],
            text=[f"{v:+.2f}%" for v in sec_df["1개월(%)"]],
            textposition="outside",
        ))
        fig2.update_layout(
            template="plotly_dark",
            height=280,
            margin=dict(t=20, b=0, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("##### 워치리스트 + 섹터 ETF 기술분석 신호")
    st.caption("초록 배경: 매수신호 ≥2 | 빨강 배경: 매도신호 ≥2")

    with st.spinner("RSI·SMA 계산 중..."):
        all_tickers = tuple(WATCHLIST + list(SECTOR_ETFS.keys()))
        tech_df = fetch_technical_signals(all_tickers)

    if not tech_df.empty:
        display = tech_df[["티커", "현재가", "RSI(14)", "SMA50", "SMA200", "신호", "매수신호", "매도신호"]].copy()
        st.dataframe(
            display.style.apply(highlight_signals, axis=1),
            use_container_width=True,
            hide_index=True,
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

    if not top10.empty:
        st.dataframe(top10, use_container_width=True, hide_index=True)

        codes = tuple(top10["코드"].tolist()) if "코드" in top10.columns else ()
        if codes:
            yf_tickers = tuple(f"{c}.KS" for c in codes)
            st.markdown("##### 기술분석 신호 (시총 TOP10)")
            with st.spinner("기술지표 계산 중..."):
                kr_tech = fetch_technical_signals(yf_tickers)
            if not kr_tech.empty:
                kr_display = kr_tech[["티커", "현재가", "RSI(14)", "SMA50", "SMA200", "신호", "매수신호", "매도신호"]].copy()
                st.dataframe(
                    kr_display.style.apply(highlight_signals, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("##### 외국인/기관 순매매 (최근 5일 합계)")
            flow_rows = []
            for _, row in top10.iterrows():
                code = row.get("코드", "")
                if not code:
                    continue
                flow = fetch_investor_flow(str(code))
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
                    for i, col in enumerate(row.index):
                        if col in ("외국인(5일)", "기관(5일)"):
                            styles[i] = "color:#00C851" if row[col] > 0 else "color:#FF3547"
                    return styles

                st.dataframe(
                    flow_df.style.apply(color_flow, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("외국인/기관 순매매 데이터를 일시적으로 불러올 수 없습니다 (Naver Finance 의존).")
    else:
        st.info("KOSPI 종목 데이터를 불러오는 중입니다...")

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

    # US recommendations
    st.markdown("#### 미국 추천")
    all_tickers = tuple(WATCHLIST + list(SECTOR_ETFS.keys()))
    with st.spinner("분석 중..."):
        us_tech = fetch_technical_signals(all_tickers)

    if not us_tech.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**매수 추천** (매수신호 ≥ 2)")
            buy_us = us_tech[us_tech["매수신호"] >= 2][["티커", "RSI(14)", "신호"]].copy()
            if not buy_us.empty:
                st.dataframe(buy_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매수신호 ≥2 종목 없음")

        with col2:
            st.markdown("**매도/경계** (매도신호 ≥ 2)")
            sell_us = us_tech[us_tech["매도신호"] >= 2][["티커", "RSI(14)", "신호"]].copy()
            if not sell_us.empty:
                st.dataframe(sell_us, use_container_width=True, hide_index=True)
            else:
                st.info("현재 매도신호 ≥2 종목 없음")

    st.divider()

    # Korean recommendations
    st.markdown("#### 한국 추천")
    if not top10.empty and not kr_tech.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**한국 매수 추천** (외국인 순매수 + 기술매수신호 ≥2)")
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
                match = kr_tech[kr_tech["티커"] == yf_ticker]
                if not match.empty and match.iloc[0]["매수신호"] >= 2:
                    buy_kr_rows.append({
                        "종목": row.get("종목명", code),
                        "외국인": "순매수",
                        "기술신호": match.iloc[0]["신호"],
                    })
            if buy_kr_rows:
                st.dataframe(pd.DataFrame(buy_kr_rows), use_container_width=True, hide_index=True)
            else:
                st.info("교차 조건(외국인 순매수 + 기술매수 ≥2) 충족 종목 없음")

        with col2:
            st.markdown("**한국 매도/경계** (기술매도신호 ≥2)")
            if not kr_tech.empty:
                sell_kr = kr_tech[kr_tech["매도신호"] >= 2][["티커", "RSI(14)", "신호"]].copy()
                if not sell_kr.empty:
                    st.dataframe(sell_kr, use_container_width=True, hide_index=True)
                else:
                    st.info("현재 기술매도신호 ≥2 한국 종목 없음")
    else:
        st.info("한국장 탭을 먼저 로드해주세요.")

    st.divider()

    # Sector rotation
    st.markdown("#### 섹터 로테이션 제안")
    rotation = PHASE_SECTORS.get(phase, {})
    c1, c2 = st.columns(2)
    with c1:
        buy_list = rotation.get("buy", [])
        buy_names = [SECTOR_ETFS.get(t, t) for t in buy_list]
        st.success(f"**비중 확대 권장**\n\n" + "\n".join(
            f"- {t} ({n})" for t, n in zip(buy_list, buy_names)
        ))
    with c2:
        sell_list = rotation.get("sell", [])
        sell_names = [SECTOR_ETFS.get(t, t) for t in sell_list]
        st.error(f"**비중 축소 권장**\n\n" + "\n".join(
            f"- {t} ({n})" for t, n in zip(sell_list, sell_names)
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
