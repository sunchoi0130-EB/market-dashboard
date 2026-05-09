# 글로벌 시장 분석 대시보드 — 아키텍처 문서

> 저장소: `github.com/sunchoi0130-EB/market-dashboard`  
> 배포: Streamlit Cloud (Python 3.11)  
> 로컬 개발: macOS, Python 3.9.6

---

## 1. 파일 구조

```
market-dashboard/
├── app.py                  # 전체 앱 (단일 파일, ~2,440줄)
├── requirements.txt        # 의존성 패키지
├── runtime.txt             # python-3.11 (Streamlit Cloud 힌트)
├── ARCHITECTURE.md
├── .streamlit/
│   └── config.toml         # 다크 테마, 포트 8501
└── .gitignore
```

---

## 2. 데이터 소스 및 캐시 전략

| 데이터 | 소스 | TTL | 함수 |
|---|---|---|---|
| 공포탐욕지수 (7개 세부지표) | CNN Markets API (직접 호출) | 3600s | `fetch_fear_greed()` |
| VIX, 10Y·2Y금리, DXY + VIX 방향 | yfinance (3개월 일봉) | 900s | `fetch_macro_data()` |
| S&P500 vs 200일선 | yfinance (1년 일봉) | 300s | `fetch_sp500_ma()` |
| S&P500 1·3·12개월 수익률 | yfinance | 3600s | `fetch_sp500_returns()` |
| 미국 주요 지수 5개 + 분봉 현재가 | yfinance (분봉 1m 오버레이) | 60s | `fetch_us_indices()` |
| SPDR 섹터 ETF 11개 | yfinance (1개월 일봉) | 300s | `fetch_sector_performance()` |
| 기술분석 신호 10개 (미국/한국) | yfinance (1년 일봉) | 300s | `fetch_technical_signals()` |
| 주봉 RSI(14) | yfinance (2년 주봉) | 3600s | `fetch_weekly_rsi()` |
| 분봉 현재가 (미국/한국) | yfinance (1d, 1m 인터벌) | 60s | `fetch_realtime_prices()` |
| KOSPI / KOSDAQ 지수 | FinanceDataReader (`KS11`, `KQ11`) | 600s | `fetch_korean_indices()` |
| KOSPI 시총 상위 10 | FinanceDataReader `StockListing("KOSPI")` | 600s | `fetch_kospi_top10()` |
| 한국 종목 현재가 | FinanceDataReader | 600s | `fetch_korean_prices_fdr()` |
| 외국인/기관 순매매 | FinanceDataReader `SnapDataReader("NAVER/INVESTORS/...")` | 600s | `fetch_investor_flow()` |
| 단일 종목 종합 검진 | yfinance + yf.info (Quality) | 300s | `compute_checkup()` |
| 티커 검색 (코드·이름 모두) | 하드코딩 딕셔너리 + yfinance fallback | 3600s | `resolve_ticker()` |

### 주요 설계 결정

- **공포탐욕 패키지 미사용**: `fear-greed` PyPI 패키지가 `str | None` 타입힌트 버그로 Python 3.9에서 import 불가. CNN API를 `requests`로 직접 호출.
- **pandas-ta 미사용**: PyPI 존재하지 않음. `ta==0.11.0`으로 대체.
- **yfinance 버전 고정 0.2.66**: 1.x는 `curl_cffi>=0.15` 요구 → Python 3.9 충돌. 0.2.66은 0.7만 요구.
- **streamlit 버전 미핀**: Streamlit Cloud 자체 관리. requirements.txt에 핀하면 빌드 타임아웃 발생.
- **tuple 인자 강제**: `@st.cache_data`는 list를 캐시 키로 사용 불가 → 모든 tickers 인자를 `tuple[str, ...]`로 통일.
- **분봉 현재가 fallback**: 장 마감·데이터 없으면 일봉 종가로 자동 대체.

---

## 3. 앱 구조 (코드 레이아웃)

```
app.py
├── [상수 블록]
│   ├── CNN_FG_URL, CNN_HEADERS
│   ├── US_INDICES                       # 지수 티커 → 한글명
│   ├── SECTOR_ETFS                      # 11개 SPDR ETF → 섹터명
│   ├── WATCHLIST                        # 미국 워치리스트 10종목
│   ├── TICKER_NAMES                     # 티커 → 종목명 전체 매핑
│   ├── US_CLAUDE_PICKS                  # 섹터별 Claude 추천 미국 종목
│   ├── KR_CLAUDE_PICKS                  # 섹터별 Claude 추천 한국 종목
│   ├── KOSPI_FALLBACK                   # 시총 상위 10 하드코딩 (API 실패 시)
│   ├── PHASE_COLORS / SUMMARIES         # 6개 국면별 색상·요약 문구
│   ├── PHASE_SECTORS                    # 국면별 섹터 로테이션 룰
│   ├── TECH_COL_FMT                     # 테이블 컬럼 포맷 딕셔너리
│   └── FG_INDICATOR_NAMES / RATING_KR   # F&G 세부지표 한글 매핑
│
├── [데이터 패처] (@st.cache_data 일괄 적용)
│   └── (위 섹션 2 참조)
│
├── [분석 헬퍼]
│   ├── weinstein_stage(close)           # 150일 SMA + 방향 → Stage 1~4
│   ├── detect_rsi_divergence(hist, rsi) # 63봉 스윙 피봇 기반 4종 다이버전스
│   ├── rsi_context(rsi, delta)          # RSI 구간 + 5일 방향 → 문장
│   └── add_relative_strength(df, sp)   # 1·3·12M 수익률 - S&P500 수익률
│
├── [국면 판정]
│   └── determine_phase(fg, vix, spread, sp_above, vix_falling) → str
│
├── [UI 헬퍼]
│   ├── phase_badge(phase)               # 국면 대형 배지 (HTML)
│   ├── highlight_signals(row)           # 행 배경색 (≥5=연색, ≥6=진색)
│   ├── position_guidance(row)           # 신규진입·보유판단 레이블
│   ├── signal_legend()                  # 10개 신호 설명 expander
│   └── fg_guide()                       # 공포탐욕지수 해석 expander
│
├── [탭 렌더러]
│   ├── tab_overview()         → phase: str|None
│   ├── tab_us(phase)
│   ├── tab_korea()            → (top10, kr_tech, kr_extra): tuple[DF, DF, DF]
│   ├── tab_checkup(phase)     # 단일 종목 종합 검진
│   └── tab_recommendations(phase, top10, kr_tech, kr_extra)
│
└── main()
    # set_page_config → sidebar → 5탭 순서대로 렌더링
    # phase, top10, kr_tech, kr_extra를 탭 간 변수로 공유
```

---

## 4. 국면 판정 로직 (6단계)

**입력 지표 5개**: 공포탐욕점수, VIX, 10Y-2Y 금리차, S&P500 vs 200일선, VIX 방향(5d MA vs 20d MA)

```
우선순위 순서로 평가:
VIX ≥ 30 & F&G < 20                           → "공포"
VIX < 15 & F&G > 75                           → "과열"
F&G ≥ 50 & VIX < 20 & spread ≥ 0 & SP위      → "강세"
20 ≤ VIX ≤ 30 & VIX하락중(5dMA<20dMA) & F&G≥30 → "회복"
F&G < 30 & SP아래  또는  F&G < 30 & VIX 30~40  → "조정"
(해당 없음)                                    → "경계"
```

| 국면 | 요약 |
|---|---|
| 강세 | 성장주·경기민감 비중 확대 |
| 과열 | 신규 진입 신중, 일부 차익 고려 |
| 회복 | 공포 해소 중 — 선별적 분할 매수 |
| 경계 | 방향 불명확 — 방어 섹터 유지 |
| 조정 | 안전자산 선호, 방어적 대응 |
| 공포 | 현금 확보 및 분할 매수 기회 탐색 |

---

## 5. 기술분석 신호 11개

`fetch_technical_signals(tickers)` 및 `compute_checkup()`이 동일한 11개 신호를 사용.

| # | 지표 | 매수 +1 | 매도 +1 | 비고 |
|---|---|---|---|---|
| 1 | RSI(14) | < 30 | > 70 | 중립 구간은 카운팅 없음 |
| 2 | SMA50 | 현재가 위 | 현재가 아래 | 항상 1개 발생 |
| 3 | SMA200 | 현재가 위 | 현재가 아래 | 항상 1개 발생 |
| 4 | MACD | 골든크로스 | 데드크로스 | 항상 1개 발생 |
| 5 | 볼린저밴드(20,2σ) | 하단 이탈 | 상단 이탈 | 밴드 내는 카운팅 없음 |
| 6 | Ichimoku TK크로스 | 전환선 > 기준선 | 전환선 < 기준선 | 데이터 ≥52봉 필요 |
| 7 | Ichimoku 구름 위치 | 구름 위 | 구름 아래 | 구름 내는 카운팅 없음 |
| 8 | MFI(14) | < 20 | > 80 | 중립 구간은 카운팅 없음 |
| 9 | OBV (누적 거래량) | OBV > 20일 MA (매집) | OBV < 20일 MA (분산) | 항상 1개 발생 |
| 10 | 거래량 (20일 평균 1.5배↑) | 고거래량 + 가격 상승 | 고거래량 + 가격 하락 | 조건 미충족 시 없음 |
| 11 | 52주 신고가권 (현재가 ≥ 고가×95%) | 매수만 | — | 매도 신호 없음 |

> 이론적 최대: 매수 11개, 매도 10개.  
> SMA50·SMA200·MACD·OBV는 항상 buy/sell 중 하나 발생 → 최소 매수 또는 매도 4개 보장.

### 참고 컬럼 (신호 카운팅 미포함)

| 컬럼 | 계산 방식 |
|---|---|
| Weinstein Stage | 150일(30주) SMA 위치·방향 → Stage 1~4 |
| RSI해석 | RSI 구간 + 5일 전 대비 방향(rsi_delta) 조합 문장 |
| RSI다이버전스 | 63봉 스윙 피봇 기반 4종: 일반강세·일반약세·숨겨진강세·숨겨진약세 |
| 주봉RSI | 2년 주봉 RSI(14) — 장기 과매수/과매도 참고 |
| RS vs S&P | 1·3·12개월 수익률에서 S&P500 동기간 수익률 차감 |

---

## 6. 포지션 판단 (position_guidance)

`MAX_SIGNALS = 11` 기준 비율로 판단. 절대값이 아닌 비율(%) 사용 — 신호 수 변경 시에도 스케일 불변.

```
buy_pct  = 매수신호 / 10
sell_pct = 매도신호 / 10

신규진입:
  sell_pct ≥ 60% or (약세다이버전스 & sell_pct ≥ 40%)  → ⛔ 진입 보류
  buy_pct  ≥ 70% & RSI 정상                             → ✅ 진입 적합
  buy_pct  ≥ 60% & RSI 과매수                           → ⏳ 조정 후 진입
  buy_pct  ≥ 60% & RSI 정상                             → ✅ 진입 적합
  RSI 과매도 & 강세다이버전스                            → 🔍 분할 매수 검토
  그 외                                                  → 👀 관망

보유판단:
  sell_pct ≥ 60% or (약세다이버전스 & sell_pct ≥ 40%)  → 🚨 매도 검토
  RSI 과매수 & sell_pct ≥ 30% & 다이버전스 없음         → ⚠️ 부분 차익 검토
  buy_pct ≥ 30% & sell_pct ≥ 30%                       → 👀 신호 혼재
  buy_pct ≥ 50% or 강세다이버전스                       → ✊ 보유 유지
  sell_pct ≥ 40%                                        → 🚨 매도 검토
  그 외                                                  → ✊ 보유 유지
```

> ⚠️ 임계값은 휴리스틱 — 백테스팅 미검증. 참고용으로만 사용.

---

## 7. 개별 종목 검진 (compute_checkup)

`tab_checkup()` → `compute_checkup(ticker_input, phase)` 호출.

- 종목 입력: 미국 티커(AAPL) 또는 한국 6자리 코드(005930) → `resolve_ticker()`로 yfinance 형식 변환
- 신호 10개 동일 계산 (fetch_technical_signals과 동일 로직)
- 추가 계산: ADX(추세 강도), OBV, ATR(변동성%), 52주 고저 위치바, PER·PBR·ROE(Quality)
- 결과: 신호별 방향(+1/0/-1) 테이블 + Weinstein 배지 + 종합 진단 문장 + 포지션 카드

---

## 8. 섹터 로테이션 룰 (하드코딩)

| 국면 | 비중 확대 | 비중 축소 |
|---|---|---|
| 강세 | XLK(기술), XLY(임의소비재), XLI(산업) | XLU(유틸), XLP(필수소비재), XLRE(부동산) |
| 과열 | XLV(헬스케어), XLP(필수소비재) | XLK(기술), XLY(임의소비재), XLI(산업) |
| 회복 | XLK(기술), XLF(금융), XLI(산업) | XLU(유틸), XLP(필수소비재) |
| 경계 | XLV(헬스케어), XLP(필수소비재), XLU(유틸) | XLK(기술), XLY(임의소비재) |
| 조정 | XLV(헬스케어), XLP(필수소비재), GLD(금) | XLK(기술), XLY(임의소비재), XLI(산업) |
| 공포 | XLU(유틸), XLP(필수소비재), GLD(금) | XLK(기술), XLY(임의소비재), XLF(금융) |

---

## 9. 알려진 제약 및 한계

| 항목 | 현황 | 원인 |
|---|---|---|
| 외국인/기관 순매매 | 클라우드에서 불안정 | SnapDataReader가 Naver Finance HTML 스크래핑 → 클라우드 IP 차단 가능 |
| 한국 시총 TOP10 | fdr 실패 시 하드코딩 fallback | StockListing 클라우드 접근 불안정 |
| 한국 기술분석 | 약 30초 소요 | yfinance 개별 종목 순차 호출 |
| 국면 판정 | 단순 규칙 기반 (5변수) | 머신러닝/가중치 미적용 |
| 신호 임계값 | 휴리스틱 (60%, 50%) | 백테스팅 미검증 |
| 신호 독립성 | SMA50·SMA200·MACD 추세 상관 높음 | "3개 독립 확인"이 실제론 1가지 추세의 3번 반복일 수 있음 |
| RSI 다이버전스 | 63봉 미만·스윙 피봇 부족 시 "-" | 탐지 조건 미충족 (데이터 부족 아님) |

---

## 로드맵 (미구현)

### Phase A — 한국 데이터 안정화

외국인/기관 순매매와 시총 순위를 KRX 공식 API로 대체해 클라우드 IP 차단 문제 해결.

```python
# KRX OpenAPI (무료, 인증 불필요)
KRX_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

# 외국인 순매매: bld=dbms/MDC/STAT/standard/MDCSTAT02302
# 시가총액 순위: bld=dbms/MDC/STAT/standard/MDCSTAT01501
```

Naver Finance HTML 스크래핑 의존 제거 → 클라우드 안정성 확보.

---

### Phase B — 알림 시스템

Streamlit Cloud는 접속 시에만 실행 → 정기 알림은 별도 스케줄러 필요.

**옵션 A — GitHub Actions 크론**
```yaml
# .github/workflows/alert.yml
on:
  schedule:
    - cron: '0 1 * * 1-5'  # 평일 오전 10시 KST
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install yfinance requests
      - run: python alert.py  # VIX > 30 또는 RSI < 30 종목 → 이메일/슬랙 발송
```

**옵션 B — st.rerun() 폴링**  
앱이 열려있는 동안만 작동하지만, `time.sleep` + `st.rerun()`으로 실시간 모니터링 탭 추가 가능.

---

### Phase C — 백테스트 탭

"이 신호 조합이 과거에 실제로 유효했는가" 검증. 신호 임계값 휴리스틱을 데이터 기반으로 교체하는 핵심 작업.

```python
# vectorbt 라이브러리
import vectorbt as vbt

def backtest_signal(ticker: str, buy_pct_threshold: float = 0.6) -> dict:
    hist  = yf.Ticker(ticker).history(period="5y", interval="1d")
    # fetch_technical_signals 로직으로 일별 buy_cnt/sell_cnt 계산
    entries = daily_buy_pct >= buy_pct_threshold
    exits   = daily_sell_pct >= buy_pct_threshold

    pf = vbt.Portfolio.from_signals(hist["Close"], entries, exits, init_cash=10000)
    return {
        "total_return": pf.total_return(),
        "sharpe":       pf.sharpe_ratio(),
        "max_drawdown": pf.max_drawdown(),
        "win_rate":     pf.trades.win_rate(),
    }
```

결과를 바탕으로 60%·50% 임계값의 실증적 근거 확보 또는 조정.
