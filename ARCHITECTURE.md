# 글로벌 시장 분석 대시보드 — 아키텍처 문서

> 저장소: `github.com/sunchoi0130-EB/market-dashboard`  
> 배포: Streamlit Cloud (Python 3.14, uv 패키지 매니저)  
> 로컬 개발: macOS, Python 3.9.6

---

## 1. 파일 구조

```
market-dashboard/
├── app.py                  # 전체 앱 (단일 파일, ~840줄)
├── requirements.txt        # 의존성 패키지 (버전 핀 최소화)
├── runtime.txt             # python-3.11 (Streamlit Cloud 힌트용, 실제 3.14 사용)
├── .streamlit/
│   └── config.toml         # 다크 테마, 포트 설정
└── .gitignore
```

---

## 2. 데이터 소스 및 캐시 전략

| 데이터 | 소스 | 캐시 TTL | 함수 |
|---|---|---|---|
| 공포탐욕지수 (7개 세부지표) | CNN Markets API (직접 호출) | 1시간 | `fetch_fear_greed()` |
| VIX, 10Y금리, 2Y금리, DXY | yfinance (`^VIX`, `^TNX`, `^IRX`, `DX-Y.NYB`) | 15분 | `fetch_macro_data()` |
| S&P500 vs 200일선 | yfinance (`^GSPC`, 1년 일봉) | 5분 | `fetch_sp500_ma()` |
| 미국 주요 지수 5개 | yfinance (5일 일봉) | 5분 | `fetch_us_indices()` |
| SPDR 섹터 ETF 11개 | yfinance (1개월 일봉) | 5분 | `fetch_sector_performance()` |
| 기술분석 신호 (미국/한국) | yfinance (1년 일봉, 개별 ticker) | 5분 | `fetch_technical_signals()` |
| KOSPI / KOSDAQ 지수 | FinanceDataReader (`KS11`, `KQ11`) | 10분 | `fetch_korean_indices()` |
| KOSPI 시총 상위 10 | FinanceDataReader `StockListing("KOSPI")` | 10분 | `fetch_kospi_top10()` |
| 외국인/기관 순매매 | FinanceDataReader `SnapDataReader("NAVER/INVESTORS/코드")` | 10분 | `fetch_investor_flow()` |

### 중요 설계 결정사항

- **공포탐욕 패키지 미사용**: `fear-greed` PyPI 패키지는 Python 3.9에서 `str | None` 타입힌트 버그로 import 불가. CNN API를 `requests`로 직접 호출하여 동일한 데이터 획득.
- **pandas-ta 미사용**: PyPI에 존재하지 않음. `ta==0.11.0` 패키지로 대체 (RSIIndicator, SMAIndicator).
- **yfinance 버전 고정 0.2.66**: 1.x는 `curl_cffi>=0.15` 요구 → Python 3.9에서 최대 0.13.0만 설치 가능하여 충돌. 0.2.66은 `curl_cffi>=0.7`만 요구.
- **streamlit 버전 미핀**: Streamlit Cloud는 자체 관리 버전 사용. requirements.txt에 핀하면 Python 3.14 환경에서 컴파일 시도 → 빌드 타임아웃.
- **한국 종목 fallback**: `fdr.StockListing("KOSPI")`가 클라우드에서 실패할 경우 KOSPI 시총 상위 10 하드코딩 사용.
- **한국 기술분석**: yfinance `.KS` 접미사 사용 (예: `005930.KS`). fdr 코드 → yfinance 티커 변환 필요.

---

## 3. 앱 구조 (코드 레이아웃)

```
app.py
├── [상수 블록]
│   ├── CNN_FG_URL, CNN_HEADERS         # Fear & Greed API 엔드포인트
│   ├── US_INDICES                       # 지수 티커 → 한글명 매핑
│   ├── SECTOR_ETFS                      # 11개 SPDR 섹터 ETF → 한글 섹터명
│   ├── WATCHLIST                        # 미국 워치리스트 10종목
│   ├── TICKER_NAMES                     # 티커 → 종목명 (워치리스트 + 섹터 ETF)
│   ├── KOSPI_FALLBACK                   # 한국 시총 상위 10 하드코딩 (fallback)
│   ├── PHASE_COLORS / SUMMARIES         # 국면별 색상·요약 문구
│   ├── PHASE_SECTORS                    # 국면별 섹터 로테이션 룰 (하드코딩)
│   ├── FG_INDICATOR_NAMES               # 7개 세부지표 영어키 → 한글명
│   └── FG_RATING_KR                     # Fear/Greed 등급 영어 → 한글
│
├── [데이터 패처] (모두 @st.cache_data 적용)
│   ├── fetch_fear_greed()               # TTL 3600s
│   ├── fetch_macro_data()               # TTL 900s
│   ├── fetch_sp500_ma()                 # TTL 300s
│   ├── fetch_us_indices()               # TTL 300s
│   ├── fetch_sector_performance()       # TTL 300s
│   ├── fetch_technical_signals(tickers) # TTL 300s, tuple 인자 (hashable)
│   ├── fetch_korean_indices()           # TTL 600s
│   ├── fetch_kospi_top10()              # TTL 600s
│   └── fetch_investor_flow(code)        # TTL 600s
│
├── [국면 판정]
│   └── determine_phase(fg, vix, spread, sp_above) → str
│       # 우선순위: 공포 > 강세 > 조정 > 경계 (default)
│
├── [UI 헬퍼]
│   ├── phase_badge(phase)               # 국면 대형 배지 (HTML)
│   ├── highlight_signals(row)           # 테이블 행 배경색 (초록/빨강)
│   ├── signal_legend()                  # 신호 설명 expander
│   └── fg_guide()                       # 공포탐욕지수 해석 expander
│
├── [탭 렌더러]
│   ├── tab_overview() → phase: str|None
│   ├── tab_us(phase)
│   ├── tab_korea() → (top10, kr_tech): tuple[DataFrame, DataFrame]
│   └── tab_recommendations(phase, top10, kr_tech)
│
└── main()
    # set_page_config → sidebar → 4탭 순서대로 렌더링
    # phase, top10, kr_tech를 탭 간 공유 (세션스테이트 대신 변수 전달)
```

---

## 4. 국면 판정 로직

```python
# 우선순위 순서로 평가
if vix >= 40 and fg_score < 20:          → "공포"
if fg >= 50 and vix < 20 and spread >= 0
   and sp_above_200ma:                    → "강세"
if fg < 30 and (30 <= vix <= 40):        → "조정"
if fg < 30 and not sp_above_200ma:       → "조정"
else:                                     → "경계"  # default
```

**입력 지표 4개**: 공포탐욕점수, VIX, 10Y-2Y 금리차, S&P500 vs 200일선

---

## 5. 기술분석 신호 계산

`fetch_technical_signals(tickers: tuple)` 함수가 각 ticker에 대해:

1. yfinance로 1년 일봉 다운로드
2. `ta.RSIIndicator(window=14)` → RSI 값
3. `ta.SMAIndicator(window=50)` → SMA50
4. `ta.SMAIndicator(window=200)` → SMA200

**신호 카운팅**:
| 조건 | 매수신호 +1 | 매도신호 +1 |
|---|---|---|
| RSI | < 30 (과매도) | > 70 (과매수) |
| SMA50 | 현재가 위 | 현재가 아래 |
| SMA200 | 현재가 위 | 현재가 아래 |

- 매수신호 ≥ 2 → 초록 하이라이트
- 매도신호 ≥ 2 → 빨강 하이라이트

---

## 6. 섹터 로테이션 룰 (하드코딩)

| 국면 | 비중 확대 | 비중 축소 |
|---|---|---|
| 강세 | XLK(기술), XLY(임의소비재), XLI(산업) | XLU(유틸), XLP(필수소비재), XLRE(부동산) |
| 경계 | XLV(헬스케어), XLP(필수소비재), XLU(유틸) | XLK(기술), XLY(임의소비재) |
| 조정 | XLV(헬스케어), XLP(필수소비재), GLD(금) | XLK(기술), XLY(임의소비재), XLI(산업) |
| 공포 | XLU(유틸), XLP(필수소비재), GLD(금) | XLK(기술), XLY(임의소비재), XLF(금융) |

---

## 7. 알려진 제약 및 한계

| 항목 | 현황 | 원인 |
|---|---|---|
| 외국인/기관 순매매 | 클라우드에서 불안정 | SnapDataReader가 Naver Finance HTML 스크래핑 → 클라우드 IP 차단 |
| 한국 시총 TOP10 | fdr 실패 시 2025년 기준 하드코딩 | StockListing 클라우드 접근 불안정 |
| 한국 기술분석 | 약 30초 소요 | yfinance 개별 종목 10회 순차 호출 |
| 국면 판정 | 단순 규칙 기반 (4변수) | 머신러닝/가중치 미적용 |
| 종목 추천 | 신호 개수 카운팅만 사용 | 모멘텀·거래량·추세 강도 미반영 |

---

---

# 고도화 로드맵

## Phase 1 — 기술분석 지표 확장 (난이도: 하)

현재 RSI + SMA 2개만 사용. 아래 지표를 `ta` 패키지로 추가 가능.

```python
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator

# MACD 골든크로스/데드크로스
macd = MACD(close=close)
macd_signal = macd.macd_signal()
macd_line   = macd.macd()
golden_cross = macd_line.iloc[-1] > macd_signal.iloc[-1]  # 매수

# 볼린저밴드 이탈
bb = BollingerBands(close=close, window=20, window_dev=2)
bb_low  = float(bb.bollinger_lband().iloc[-1])   # 하단 이탈 → 과매도
bb_high = float(bb.bollinger_hband().iloc[-1])   # 상단 이탈 → 과매수

# OBV (거래량 기반 추세 확인)
obv = OnBalanceVolumeIndicator(close=close, volume=hist["Volume"]).on_balance_volume()
obv_rising = obv.iloc[-1] > obv.iloc[-5]  # 5일 전보다 OBV 상승 → 매수세 유입
```

**추가하면 신호 카운팅이 3개 → 6개로 확장됨. 임계값도 ≥3 으로 조정 권장.**

---

## Phase 2 — 신호 스코어링 시스템 (난이도: 중)

현재 단순 카운팅(0/1/2/3) 방식을 가중치 점수제로 전환.

```python
SIGNAL_WEIGHTS = {
    "RSI 과매도":      2.0,   # RSI는 신뢰도 높음
    "SMA200 위":       1.5,   # 장기 추세가 단기보다 중요
    "SMA50 위":        1.0,
    "MACD 골든크로스": 1.5,
    "BB 하단 이탈":    1.0,
    "OBV 상승":        0.5,   # 거래량은 보조 확인용
}

# 총점 계산 → 0~10 정규화 → "매수강도" 컬럼
buy_score = sum(SIGNAL_WEIGHTS[s] for s in signals if s in BUY_SIGNALS)
sell_score = sum(SIGNAL_WEIGHTS[s] for s in signals if s in SELL_SIGNALS)
```

**결과**: 종목별 매수강도 점수로 정렬 가능. 단순 2개 이상 필터보다 세밀한 추천.

---

## Phase 3 — 모멘텀 및 상대강도 (난이도: 중)

섹터/종목의 **상대적** 강도를 측정해 "지금 뭐가 제일 강한가"를 찾는 방식.

```python
# 52주 모멘텀 (현재가 / 52주 전 가격 - 1)
price_52w_ago = float(hist["Close"].iloc[0])
momentum_52w  = (price - price_52w_ago) / price_52w_ago * 100

# 3개월 모멘텀
price_3m_ago = float(hist["Close"].iloc[-63])
momentum_3m  = (price - price_3m_ago) / price_3m_ago * 100

# 상대강도 (vs S&P500)
sp_return = (sp_hist["Close"].iloc[-1] - sp_hist["Close"].iloc[-63]) / sp_hist["Close"].iloc[-63]
relative_strength = momentum_3m - sp_return * 100
```

**활용**: 섹터 ETF에 적용 → "S&P500보다 강한 섹터"를 자동 정렬하면 로테이션 신호 자동화 가능.

---

## Phase 4 — 멀티타임프레임 분석 (난이도: 중)

현재는 일봉(1d)만 사용. 주봉(1wk)을 추가하면 노이즈 감소.

```python
@st.cache_data(ttl=3600)  # 주봉은 캐시 1시간으로 충분
def fetch_weekly_signals(tickers: tuple) -> pd.DataFrame:
    for ticker in tickers:
        hist_w = yf.Ticker(ticker).history(period="2y", interval="1wk")
        rsi_w  = RSIIndicator(close=hist_w["Close"], window=14).rsi().iloc[-1]
        # 일봉 RSI와 주봉 RSI가 모두 과매도일 때만 강한 매수신호
```

**매매 원칙**: 주봉 방향 = 큰 그림 / 일봉 신호 = 진입 타이밍. 두 타임프레임이 일치할 때만 추천.

---

## Phase 5 — 한국 데이터 안정화 (난이도: 중)

### 외국인/기관 순매매 대안

```python
# KRX OpenAPI (무료, 인증 불필요)
KRX_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

def fetch_krx_investor_flow(code: str) -> dict:
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT02302",
        "isuCd": code,
        "strtDd": (pd.Timestamp.today() - pd.Timedelta(days=10)).strftime("%Y%m%d"),
        "endDd": pd.Timestamp.today().strftime("%Y%m%d"),
    }
    r = requests.post(KRX_URL, data=params, timeout=10)
    return r.json()
```

Naver Finance 의존 제거 → KRX 공식 API로 대체하면 클라우드에서도 안정적.

### 한국 시총 TOP10 동적 업데이트

```python
# KRX 전체 시장 데이터 (일별 갱신)
KRX_MARKET_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
# bld: dbms/MDC/STAT/standard/MDCSTAT01501 → 시가총액 순위
```

하드코딩 대신 KRX에서 실시간 시총 순위를 가져오면 종목 변경에도 자동 대응.

---

## Phase 6 — 추천 고도화: 국면 × 기술신호 복합 필터 (난이도: 중-상)

현재 추천 로직: `매수신호 ≥ 2`
개선 추천 로직: **국면 × 섹터 방향 × 기술신호 × 모멘텀** 복합 필터

```python
def score_ticker(ticker: str, phase: str, tech: dict, momentum: float) -> float:
    score = 0.0

    # 1. 국면 적합성 (섹터 로테이션 룰과 일치 여부)
    if ticker in PHASE_SECTORS[phase]["buy"]:
        score += 3.0
    elif ticker in PHASE_SECTORS[phase]["sell"]:
        score -= 3.0

    # 2. 기술신호 가중합
    score += tech["buy_score"] - tech["sell_score"]

    # 3. 모멘텀 (3개월 수익률 기준, S&P500 초과분)
    score += min(max(momentum / 10, -2.0), 2.0)  # -2 ~ +2 클리핑

    # 4. 공포탐욕 극단값 보정 (극도의 공포 → 매수 가중, 극도의 탐욕 → 매도 가중)
    fg = fetch_fear_greed()
    if fg:
        if fg["score"] < 20:   score += 1.0   # 극도의 공포 = 매수 프리미엄
        elif fg["score"] > 80: score -= 1.0   # 극도의 탐욕 = 매도 프리미엄

    return score

# 최종 출력: 점수 내림차순 정렬 → 상위 3개 "강력 매수", 하위 3개 "경계"
```

---

## Phase 7 — 알림 시스템 (난이도: 상)

Streamlit Cloud는 상시 실행이 아니라 접속 시에만 작동함. 정기 알림을 위해선 별도 스케줄러 필요.

**옵션 A — GitHub Actions 크론**
```yaml
# .github/workflows/alert.yml
on:
  schedule:
    - cron: '0 1 * * 1-5'  # 평일 오전 10시 KST (UTC 01:00)
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install yfinance requests
      - run: python alert.py  # VIX > 30 또는 RSI < 30 종목 → 슬랙/이메일 발송
```

**옵션 B — Streamlit + st.session_state 폴링**
앱이 열려있는 동안만 동작하지만, `time.sleep` + `st.rerun()`으로 실시간 모니터링 탭 추가 가능.

---

## Phase 8 — 백테스트 탭 추가 (난이도: 상)

"이 신호 조합이 과거에 실제로 유효했는가" 검증.

```python
# vectorbt 라이브러리 (pip install vectorbt)
import vectorbt as vbt

def backtest_rsi_sma(ticker: str) -> dict:
    hist = yf.Ticker(ticker).history(period="5y", interval="1d")
    close = hist["Close"]

    rsi = RSIIndicator(close=close, window=14).rsi()
    sma200 = SMAIndicator(close=close, window=200).sma_indicator()

    entries = (rsi < 30) & (close > sma200)   # RSI 과매도 + 200일선 위
    exits   = (rsi > 70) | (close < sma200)   # RSI 과매수 또는 200일선 이탈

    pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=10000)
    return {
        "total_return": pf.total_return(),
        "sharpe": pf.sharpe_ratio(),
        "max_drawdown": pf.max_drawdown(),
        "win_rate": pf.trades.win_rate(),
    }
```

---

## 우선순위 추천 로드맵

```
지금 버전 (v1.0)
    ↓
Phase 1: MACD + 볼린저밴드 추가          ← 가장 빠른 개선, 코드 30줄
    ↓
Phase 3: 3개월 모멘텀 + 상대강도         ← 섹터 로테이션 자동화 핵심
    ↓
Phase 6: 복합 스코어링 시스템            ← 추천 품질 대폭 향상
    ↓
Phase 5: KRX API로 한국 데이터 안정화   ← 한국장 신뢰도 확보
    ↓
Phase 8: 백테스트 탭                     ← 신호 검증 및 신뢰도 구축
    ↓
Phase 7: GitHub Actions 알림            ← 모니터링 자동화
```
