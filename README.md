# stock-news-bot

한국 주식 관심종목 뉴스를 시간 단위로 모니터링해 **AI 중요도 7점 이상**의 뉴스 1건만 텔레그램으로 받는 봇. GitHub Actions로 무인 운영.

## 동작

| 시각 (KST) | 수집 범위 |
|---|---|
| 평일 09:00 | 전일 15:30 ~ 09:00 (장 시작 전 종합) |
| 평일 10:00~15:00 매시 | 직전 1시간 |
| 일요일 21:00 | 금 15:30 ~ 일 21:00 (주말 종합) |

뉴스 소스: 네이버 종목 뉴스 + Google News RSS · 평가: Cerebras Llama 3.3 70B (무료) · 알림: Telegram Bot.

## 초기 설정

### 1. 텔레그램 봇 만들기

1. 텔레그램에서 [`@BotFather`](https://t.me/BotFather) 검색 → `/newbot`
2. 봇 이름과 username 입력 → **봇 토큰** 발급 (`123456:ABC-DEF...`)
3. 만든 봇과 대화 시작 → 아무 메시지 1개 전송
4. 브라우저에서 다음 URL 열기:
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
5. JSON 응답에서 `"chat":{"id": ... }` 값이 **chat id**

### 2. Cerebras API 키 발급

1. [cloud.cerebras.ai](https://cloud.cerebras.ai) 가입
2. **API Keys** 메뉴 → **Create API Key**

### 3. GitHub 레포 + Secrets

1. 이 디렉토리를 GitHub에 push (public 레포로 만들면 Actions 무제한 무료)
2. 레포 **Settings → Secrets and variables → Actions** 에서 추가:
   - `CEREBRAS_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

### 4. 관심종목 등록

봇이 자동 실행되기 시작하면 텔레그램에서 직접 명령:

```
/add 삼성전자
/add 005930
/threshold 7
/list
```

또는 `watchlist.json`을 직접 편집해 첫 커밋.

## 텔레그램 명령

| 명령 | 설명 |
|---|---|
| `/add <종목명\|티커>` | 관심종목 추가 |
| `/remove <종목명\|티커>` | 관심종목 제거 |
| `/list` | 현재 목록 + 임계값 |
| `/threshold <0~10>` | 알림 임계값 변경 (기본 7) |
| `/status` | 마지막 실행 시각 확인 |
| `/help` | 명령 도움말 |

명령은 다음 cron 실행 시점(최대 1시간 후)에 일괄 처리. 즉시 적용하려면 GitHub **Actions → monitor → Run workflow** 수동 실행.

## 로컬 테스트

```bash
cd C:\Users\loknr\Desktop\stock-news-bot
python -m venv .venv
.venv\Scripts\activate     # PowerShell
pip install -r requirements.txt
copy .env.example .env
# .env에 토큰 3개 입력
python main.py
```

로컬 실행 시에는 `watchlist.json` 변경분이 자동 git push되지 않음.

## 운영 메모

- **임계값 캘리브레이션**: 1~2주 운영 후 점수 분포 보고 6/8로 조정
- **종목 수**: 한 프롬프트가 너무 길어지지 않도록 10개 이하 권장
- **GitHub Actions 지연**: cron이 5~15분 늦게 트리거되는 경우가 흔함 (정상)

## 디렉토리 구조

```
stock-news-bot/
├── main.py
├── requirements.txt
├── watchlist.json
├── .github/workflows/monitor.yml
└── src/
    ├── window.py             # 시각별 윈도우 계산
    ├── state.py              # watchlist.json + git
    ├── telegram_bot.py       # getUpdates + 명령 + 전송
    ├── news_fetcher.py       # 네이버 + Google News
    ├── dedup.py              # URL + 제목 유사도
    └── importance_scorer.py  # Cerebras
```
