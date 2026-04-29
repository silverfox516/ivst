# IVST 명령 레퍼런스

코드에 실제 구현된 메뉴·옵션·평가 기준을 한 곳에 정리한 문서입니다.
설계 의도는 [plan.md](plan.md), 이 문서는 **"지금 코드가 뭘 하느냐"** 만 기술합니다.

---

## 명령 트리

```
ivst                          # = ivst (no args) → 통합 dashboard
├── market                    # 시장 타이밍 판정 (US verdict)
├── signal [TICKER]           # 종목 매수/매도 판정
├── recommend                 # 유망 종목 추천 (KR 동적 + US 정적)
│   ├── --market KR|US|ALL
│   ├── --mode momentum|value|balanced
│   └── --reason
├── watch                     # 관심종목 관리
│   ├── add <종목명/코드> ...
│   ├── list
│   └── remove <종목>
├── portfolio                 # 보유 종목 관리
│   ├── add <종목> <수량> <매수가> [--date --memo]
│   ├── list
│   └── perf
├── note                      # 리서치 노트
│   ├── add <제목> <내용> [--ticker]
│   ├── list [TICKER]
│   └── search <검색어>
└── news [--all]              # 뉴스 + 호재/악재 분류
```

---

## 데이터 소스

| 데이터 | 출처 | 인증 | 모듈 |
|---|---|:---:|---|
| 미국 거시 (Fed BS, RRP, TGA, HY OAS 등) | **FRED** `fredgraph.csv` 공개 엔드포인트 | X | `data/macro.py` |
| CNN Fear & Greed Index | **CNN** production API (브라우저 헤더 위장) | X | `data/sentiment_index.py` |
| 미국 주가·시총·재무 | **yfinance** (Yahoo Finance 비공식) | X | `data/us_stock.py`, `analysis/recommend.py` |
| 환율·국내외 지수 | **yfinance** | X | `data/fx.py` |
| 한국 종목 OHLCV | **pykrx** (KRX 공식 데이터) | KRX 로그인 (env `KRX_ID/KRX_PW`) | `data/kr_stock.py` |
| 한국 전종목 스크리닝 | **pykrx** market-wide API | 동일 | `analysis/discovery.py` |
| 뉴스 | RSS (httpx + feedparser) | X | `data/news.py` |

캐시: 원칙적으로 실시간 조회. 단 KR 전종목 스크리닝(`screening_cache`)은 12 시간 SQLite 캐시 (~3,000 종목 호출 비용 회피).

---

## `ivst` (dashboard)

인자 없이 실행 시 호출 (`app.py:36`). 4개 패널 순차 출력:

1. **Watchlist Signals** — 관심종목 전체 시그널 요약 (signal 명령과 동일 로직)
2. **Latest News** — 관심종목 매칭 뉴스 5건, 매칭 없으면 전체 뉴스
3. **Market Summary** — KOSPI/KOSDAQ/S&P/NASDAQ/USD-KRW/10Y UST 가격
4. (관심종목이 없으면 watchlist 추가 안내)

---

## `ivst market`

미국 시장 타이밍 판정 (목적 1). 6개 코어 지표를 가중 합산해 총점 산출 → 3단계 판정 → 모드 결정.

### 평가 기준 (코드: `analysis/market_adapters.py`, 가중치: `analysis/market.py:76`)

| 코드 | 지표 | 가중 | 원천 | +1 조건 | -1 조건 |
|---|---|---:|---|---|---|
| **C1_BS** | Fed 대차대조표 4주 Δ | 0.10 | FRED WALCL | Δ ≥ +50B | Δ ≤ -50B |
| **C1_TGA** | TGA 잔량 + 방향 | 0.10 | FRED WTREGEN | 잔량 ≥700B 또는 4주 Δ ≤ -100B (둘 다면 강한 ±1, 엇갈리면 0) | 잔량 ≤200B 또는 4주 Δ ≥ +100B |
| **C1_RRP** | RRP 잔량 + 방향 | 0.10 | FRED RRPONTSYD | 잔량 ≥500B 또는 4주 Δ ≤ -50B | 잔량 ≤50B 또는 4주 Δ ≥ +50B |
| **C2** | S&P500 vs 200일선 | 0.30 | yfinance `^GSPC` | 가격/200DMA - 1 ≥ +0.5% | ≤ -0.5% |
| **C3** | HY OAS 크레딧 스프레드 | 0.25 | FRED BAMLH0A0HYM2 | < 400bp | > 600bp |
| **C4** | 섹터 로테이션 (공격-방어) | 0.15 | yfinance 섹터 ETF | 공격 평균 - 방어 평균 ≥ +1.0%p | ≤ -1.0%p |

공격 섹터: Technology(XLK)·Consumer Disc.(XLY)·Industrials(XLI)
방어 섹터: Utilities(XLU)·Consumer Staples(XLP)·Healthcare(XLV)

### 총점 → 판정 → 모드 (`analysis/market.py:88, 100, 108`)

| 총점 | 판정 | 모드 |
|---|---|---|
| ≥ +0.4 | 🟢 매수 우위 | 중장기 |
| -0.4 ~ +0.4 | 🟡 혼조 | 스윙 |
| ≤ -0.4 | 🔴 하락장 | 관망 |

**누락 처리**: 공급된 지표만의 가중 합을 분모로 정규화 (`analysis/market.py:125`). 전부 누락이면 총점 0 → MIXED.

**맥락 패널** (판정에 기여 X, 참고용): F&G, 10Y UST, 10Y-2Y, HY OAS, Fed BS, RRP, TGA.

---

## `ivst signal [TICKER]`

종목 매수/매도 판정 (목적 2). 4개 블록을 모드별 가중치로 조합해 총점 → 5단계 시그널.

- 인자 없음: 관심종목 전체를 요약 테이블로
- 인자 있음: 단일 종목 상세 패널

모드는 `build_us_verdict()` 결과의 모드를 그대로 사용 (`signal_cmd.py:63`). KR 종목도 같은 모드 적용 (KR 시장 verdict는 미구현 — 데이터 신뢰 이슈로 제거됨).

### 4개 블록 (`analysis/stock_adapters.py`)

| 블록 | 서브 지표 | 평가 기준 |
|---|---|---|
| **TREND** (추세·가격) | 주가/200일선 | ≥ +3% (+1) / ≤ -3% (-1) (`PRICE_VS_200DMA_MARGIN=0.03`) |
| | RSI(14) | ≤30 (+1) / ≥70 (-1) |
| | MACD 크로스 | 골든크로스(+1) / 데드크로스(-1), 유지 방향 ±1 |
| | 거래량 5d/20d | ≥1.30 (+1 매집) / ≤0.70 (-1 건조) |
| **VALUE** (밸류·퀄리티) | PER vs 섹터 중앙값 | ratio ≤ 0.80 (+1) / ≥ 1.30 (-1). PER ≤0이면 0 |
| | ROE | ≥15% (+1) / ≤8% (-1) |
| | 부채비율 (D/E) | <50% (+1) / >100% (-1) |
| | 매출·이익 YoY 성장 | ≥10% (+1) / ≤0% (-1) |
| **EVENT** (이벤트·엣지) | (미구현 — yfinance 스키마 불안정) | 항상 "데이터 없음" |
| **SECTOR** (섹터 맥락) | 전체 섹터 1M 평균 모멘텀 | 평균 > +2 (+1) / < -2 (-1) |

블록 점수 = 서브 지표 평균. 총점 = 블록 점수 × 모드 가중치 합.

### 모드별 블록 가중치 (`analysis/stock.py:71`)

| 모드 | VALUE | EVENT | TREND | SECTOR |
|---|---:|---:|---:|---:|
| 중장기 | 0.45 | 0.30 | 0.15 | 0.10 |
| 스윙 | 0.15 | 0.25 | 0.45 | 0.15 |
| 관망 | 0.25 | 0.25 | 0.25 | 0.25 |

### 총점 → 5단계 시그널 (`analysis/stock.py:93`)

| 총점 | 시그널 |
|---|---|
| ≥ +0.6 | STRONG BUY |
| ≥ +0.2 | BUY |
| -0.2 ~ +0.2 | HOLD |
| ≤ -0.2 | SELL |
| ≤ -0.6 | STRONG SELL |

관망 모드(WATCH)에서는 매수 신호를 1단계 하향 (STRONG_BUY → BUY → HOLD) 후 ⚠ 모드 불일치 경고 표시.

---

## `ivst recommend`

유망 종목 추천. KR은 pykrx 전종목 스크리닝(동적), US는 sector ETF + 대표주(정적).

### 옵션

| 옵션 | 값 | 기본 | 동작 |
|---|---|---|---|
| `--market` | KR / US / ALL | ALL | 시장 선택. ALL 은 KR/US 슬롯 균등 분할 |
| `--mode` | momentum / value / balanced | balanced | KR 스크리닝 모드 (US 슬레이트엔 영향 없음) |
| `--reason` | flag | False | 추천 근거(섹터/모멘텀/PER/PBR) 컬럼 표시 |

출력 컬럼: `#`, `종목`, `섹터`, `점수`, `정책`, `주의`, (`추천 근거`).

### KR 동적 스크리너 (`analysis/discovery.py`)

**1단계 — 풀 구성 (mode 무관, 12h 캐시)**

| 필터 | 임계 |
|---|---|
| 시가총액 | ≥ 2,000억원 (`DEFAULT_MIN_MARKET_CAP_WON = 200_000_000_000`) |
| 일 거래대금 | ≥ 10억원 (`DEFAULT_MIN_TRADING_VALUE_WON = 1_000_000_000`) |

대상: KOSPI + KOSDAQ 전 종목. 호출:
- `get_market_price_change_by_ticker(start_1m, end, market)` × 2 (1M/3M)
- `get_market_cap_by_ticker(end, market)`
- `get_market_fundamental_by_ticker(end, market)` (PER/PBR/EPS/BPS/DIV/DPS)
- `get_market_sector_classifications(end, market)` (KRX 업종명)

**2단계 — 모드별 스코어링**

#### `momentum` 모드 (`_score_momentum`)
```
score = 0.6 × return_1m + 0.4 × return_3m
```
필터 없음. 폭등주가 상단에 옴 → ⚠ 경고 다수.

#### `balanced` 모드 (`_score_balanced`, **기본값**)
모멘텀 점수에 다음 페널티 곱:

| 조건 | 곱 |
|---|---:|
| return_1m > 100% | × 0.20 |
| 50% < return_1m ≤ 100% | × 0.50 |
| 30% < return_1m ≤ 50% | × 0.80 |
| PER ≤ 0 또는 PER > 50 | × 0.50 |
| 30 < PER ≤ 50 | × 0.80 |
| PBR > 5 | × 0.70 |
| 3 < PBR ≤ 5 | × 0.90 |
| trading_value / market_cap > 0.20 (펌프 신호) | × 0.50 |

#### `value` 모드 (`_score_value`)

**필터** (모두 통과해야 후보):
- 3.0 ≤ PER ≤ 25.0
- 0 < PBR ≤ 2.0
- return_1m ≥ -15%

**점수**:
```
per_pts      = (25 - per) / 25 × 40        # 0~40
pbr_pts      = (2.0 - pbr) / 2.0 × 30      # 0~30
r1m_pts      = max(0, return_1m)
turnaround   = +15 if return_3m < 0 < return_1m else 0
score = per_pts + pbr_pts + r1m_pts + turnaround
```

### 정책 부스트 (mode 무관, KR 전용)

뉴스 텍스트에서 `POLICY_SECTOR_MAP` 키워드(예: "반도체 지원", "금리 인하", "친환경", "rate cut", ...) 매칭 → 매핑된 정책 섹터 토큰을 `_POLICY_TO_KRX_SECTOR` 동의어 표를 통해 KRX 업종명에 대조 → 일치 시 score × 1.3.

KRX 업종 매핑(`analysis/recommend.py:_POLICY_TO_KRX_SECTOR`):

| 정책 키워드 | KRX 업종명 (substring) |
|---|---|
| 반도체 | 전기·전자, 전기전자 |
| IT | 서비스, 통신, 전기·전자 |
| 2차전지 | 화학, 전기·전자 |
| 자동차 | 운수장비, 자동차 |
| 건설 | 건설 |
| 은행 | 금융, 은행 |
| 바이오 | 의약품, 바이오 |
| 방산 | 운수장비, 기계 |

### 위험 경고 태그 (`_warnings_for`, 모든 모드 공통)

| 태그 | 트리거 |
|---|---|
| `⚠1M+100%` | return_1m > 100% |
| `⚠1M+50%` | 50% < return_1m ≤ 100% |
| `⚠적자` | PER ≤ 0 |
| `⚠고PER` | PER > 50 |
| `⚠고PBR` | PBR > 5 |
| `⚠회전율↑` | trading_value / market_cap > 15% |

### US 정적 슬레이트 (`analysis/recommend.py:US_SECTOR_ETFS`, `US_SECTOR_STOCKS`)

11 개 섹터 ETF의 1M/3M 모멘텀(`0.6×r1m + 0.4×r3m`)으로 섹터 정렬 → 상위 5 개 섹터 → 각 섹터 대표 2 종목 (하드코딩).

| 섹터 | ETF | 대표 종목 (구현된 매핑만) |
|---|---|---|
| Technology | XLK | AAPL, MSFT, NVDA, GOOGL |
| Financials | XLF | JPM, BAC, GS |
| Energy | XLE | XOM, CVX, COP |
| Healthcare | XLV | UNH, JNJ, LLY |
| Industrials | XLI | CAT, HON, UPS |
| Consumer Disc. / Staples / Utilities / Real Estate / Materials / Communication | XLY/XLP/XLU/XLRE/XLB/XLC | (대표 종목 매핑 없음 — 섹터 ETF만 점수에 기여) |

정책 부스트는 US 측에서도 적용 (`POLICY_SECTOR_MAP`에 매핑된 섹터 점수 × 1.3).

---

## `ivst watch`

| 서브 | 인자 | 동작 |
|---|---|---|
| `add` | `<종목명/코드> ...` (다수 가능) | `resolve_ticker`로 검색 → 다중 매칭이면 인터랙티브 선택 → DB `watchlist` 추가 |
| `list` | — | DB watchlist 표시 |
| `remove` | `<종목>` | 코드 또는 이름으로 삭제 |

`resolve_ticker` 폴백 순서 (`data/resolver.py`):
1. DB `ticker_cache` 조회
2. (없으면) 6자리면 pykrx 검증, 영문이면 yfinance 검증

---

## `ivst portfolio`

| 서브 | 인자 | 동작 |
|---|---|---|
| `add` | `<종목> <수량> <매수가> [--date --memo]` | `--date` 미입력 시 오늘 날짜 (`YYYY-MM-DD`) |
| `list` | — | 보유 목록 |
| `perf` | — | 종목별 현재가 조회(KR=pykrx, US=yfinance) → 수익률·평가손익. 합계 라인 출력 |

---

## `ivst note`

| 서브 | 인자 | 동작 |
|---|---|---|
| `add` | `<제목> <내용> [--ticker]` | DB `notes` 삽입 |
| `list` | `[TICKER]` | 종목별 또는 전체. 50자 미리보기 |
| `search` | `<검색어>` | 제목·내용 LIKE 검색 |

---

## `ivst news`

| 옵션 | 기본 | 동작 |
|---|---|---|
| `--all` | False | False면 관심종목 매칭 뉴스 위주, 없으면 전체. True면 전체 뉴스 20건 |

키워드 기반 호재/악재 분류 (`analysis/sentiment.py`). 매칭된 키워드의 가중치 합계가 양수→호재, 음수→악재, 0→중립.

호재 키워드 예 (가중): "어닝서프라이즈"(+3), "흑자 전환"(+3), "상한가"(+3), "실적 개선"(+2), "목표가 상향"(+2), "beat"(+2), "upgrade"(+2), "all-time high"(+2), …

악재 키워드 예: "어닝쇼크"(-3), "적자"(-3), "폭락"(-3), "하한가"(-3), "리콜"(-2), "downgrade"(-2), "miss"(-2), …

전체 목록은 `analysis/sentiment.py:13, 26`.

---

## 데이터베이스 스키마 (`data/ivst.db`, `db/engine.py`)

| 테이블 | 컬럼 |
|---|---|
| `watchlist` | id, ticker (UNIQUE), name, market, added_at |
| `price_cache` | ticker, date, OHLCV (PK: ticker+date) |
| `ticker_cache` | ticker (PK), name, market, updated_at |
| `portfolio` | id, ticker, name, market, buy_price, quantity, buy_date, memo |
| `notes` | id, ticker?, title, content, created_at |
| `news_cache` | id, ticker?, title, url, source, sentiment, sentiment_score, published_at, fetched_at |
| `screening_cache` | key (PK), payload (JSON), cached_at |

날짜 형식: 모두 SQLite `datetime('now')` (UTC `YYYY-MM-DD HH:MM:SS`). 매수일은 `YYYY-MM-DD`.

---

## 임계치 한 곳 모음

수정 시 해당 파일에서 상수 값을 바꾸면 됩니다 (`config/thresholds.yaml` 추출은 [plan.md] 남은 할 일 #6).

- 시장 verdict 임계: `analysis/market_adapters.py:18~47`
- 시장 verdict → 모드 매핑: `analysis/market.py:88` (`BULLISH/BEARISH_THRESHOLD`)
- 종목 시그널 임계: `analysis/stock_adapters.py:11~40`
- 종목 시그널 5단계 매핑: `analysis/stock.py:93`
- KR 추천 시총·거래대금 필터: `analysis/discovery.py:24` (`DEFAULT_MIN_*`)
- KR 추천 모드별 스코어 페널티/필터: `analysis/discovery.py:_score_balanced`, `_score_value`
- 위험 경고 태그 임계: `analysis/discovery.py:_warnings_for`
- 정책-섹터 매핑: `analysis/recommend.py:POLICY_SECTOR_MAP`, `_POLICY_TO_KRX_SECTOR`
- 뉴스 감성 키워드/가중: `analysis/sentiment.py:13, 26`
- 캐시 TTL: `analysis/discovery.py:CACHE_TTL_HOURS` (현재 12h)
