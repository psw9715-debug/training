# training

아이폰에서 쓰는 훈련일지 웹앱. 서버 없이 GitHub 저장소를 데이터베이스로 쓴다.

- `index.html` — 앱 전체 (단일 파일)
- `config/` — 종목 라이브러리, 루틴, 세트 템플릿, 목표, 음성 설정, 인바디 측정값
- `logs/YYYY-MM-DD.json` — 하루치 기록

## 인바디 자동 기록

헬스장에서 인바디를 재면 등록한 전화번호의 인바디 앱 계정으로 결과가 올라간다.
`.github/workflows/inbody.yml` 이 하루 한 번(22:14 KST) `scripts/inbody_sync.py` 를
돌려 그 값을 `config/inbody.json` 에 쌓고, 앱은 그 날짜의 컨디션 칸(체중·골격근량·
체지방량)을 자동으로 채운다.

처음 한 번만 저장소 **Settings › Secrets and variables › Actions › New repository secret** 에
아래 두 개를 넣는다. (비밀 값은 저장소가 공개여도 밖으로 노출되지 않는다)

| 이름 | 값 |
| --- | --- |
| `INBODY_LOGIN_ID` | 인바디 앱 가입 전화번호, 숫자만 (예: `01027665942`) |
| `INBODY_LOGIN_PW` | 인바디 앱 비밀번호 |

한국이 아닌 계정이면 **Variables** 탭에 `INBODY_COUNTRY_CODE` 를 ISO 코드로 넣는다 (기본 `KR`).

손으로 돌릴 때는 Actions 탭 › 인바디 동기화 › Run workflow. 앱 설정 탭의
'지금 받아오기' 버튼이 이 화면을 열어 준다.

인바디는 개인용 공개 API 를 내놓지 않는다. 이 스크립트는 인바디 앱이 쓰는 REST
엔드포인트를 그대로 호출한다. 인바디가 바꾸면 멈출 수 있고, 그때는 Actions 로그에
실패가 남는다. 받아 오는 값은 읽기만 하고 아무것도 바꾸지 않는다.
