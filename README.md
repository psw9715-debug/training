# training

아이폰에서 쓰는 훈련일지 웹앱. 서버 없이 GitHub 저장소를 데이터베이스로 쓴다.

- `index.html` — 앱 전체 (단일 파일)
- `config/` — 종목 라이브러리, 루틴, 세트 템플릿, 목표, 음성 설정, 인바디 측정값
- `logs/YYYY-MM-DD.json` — 하루치 기록

## 인바디 자동 기록

헬스장에서 인바디를 재면 아이폰 **건강(Apple Health)** 앱에 체중·체지방률·근육량이
쌓인다. 아이폰 **단축어** 자동화가 하루 한 번 그 값을 `config/inbody/날짜.json` 으로
올리고, 앱은 그 폴더와 `config/inbody.json` 을 함께 읽어 오늘 탭 컨디션을 채운다.
인바디 비밀번호는 쓰지 않는다. 만드는 법: [`docs/inbody-shortcut.md`](docs/inbody-shortcut.md).

### 서버 직접 로그인(보류)

`scripts/inbody_sync.py` + `.github/workflows/inbody.yml` 은 인바디 앱의 REST API 로
직접 받아오는 방식이다. 한국 서버(appapikrv3)가 올바른 비밀번호도 `PW_FAIL` 로
거부한다 — 비밀번호를 평문이 아닌 방식으로 받는 것으로 보인다. 자동 실행(schedule)은
꺼 두었고(실패 메일 방지), 인코딩이 확인되면 다시 켤 수 있다. Actions 탭에서 `diag`
모드로 손수 돌려 오류 코드만 확인할 수 있다.
