# MariaDB와 Lab을 함께 실행하기

Docker Engine과 Compose가 있는 환경에서 저장소 루트에서 실행합니다. 이 구성은 로컬 통합 검증용이며 처음에는 localhost에만 바인딩합니다. 운영 서버 구성은 호스트 점검 이후 별도로 적용합니다.

## 시작

```sh
python infra/scripts/prepare-local-env.py
docker compose --env-file .local/compose.env config --quiet
docker compose --env-file .local/compose.env up --build -d
docker compose --env-file .local/compose.env ps
```

`python` 대신 환경에 따라 `python3`를 사용합니다. 비밀번호는 `.local/compose.env`에 생성되며 기존 파일은 보존합니다. DB 포트와 API 포트는 호스트에 공개하지 않고 Nginx의 4310 포트만 localhost에서 엽니다.

화면은 `http://127.0.0.1:4310/`, API는 `http://127.0.0.1:4310/api/demo/runs`입니다. API가 DB bootstrap을 마칠 때까지 잠시 기다린 뒤 조회합니다. 응답의 DATABASE detail이 MariaDB인지 확인해 H2 검증과 구분합니다.

실제 버전을 연결할 때는 checkout의 commit을 확인해 `SOURCE_COMMIT`으로 주입합니다. 미설정 값은 unknown이며 성공한 GitOps 배포 이력을 의미하지 않습니다.

## 재시작과 종료

```sh
docker compose --env-file .local/compose.env restart api
docker compose --env-file .local/compose.env down
```

MariaDB 데이터는 프로젝트 전용 named volume에 남습니다. `down -v`는 이 데이터를 삭제하므로 일반 종료 절차에 포함하지 않습니다. 기존 `.local/compose.env`를 바꾸면 이미 초기화한 DB의 비밀번호가 자동 변경되지 않습니다.

## 확인할 결과

- 입력 12건 = 성공 7 + 실패 3 + 중복 2 + 대기 0.
- 단건 결과에 12개 outcomes와 성공 7개의 series가 있습니다.
- API를 재시작해도 고정 ID의 실행이 중복 생성되지 않습니다.
- 공개 POST 요청은 허용되지 않습니다.
- API 연결이 끊기면 화면에 연결 실패와 합성 샘플 상태를 표시합니다.

컨테이너 이미지는 `infra/image-lock.json`에 확인한 digest로 고정합니다. 지원 범위와 취약점은 갱신 시 다시 확인합니다. [MariaDB 공식 이미지](https://mariadb.org/where-is-the-official-mariadb-container-image/), [Compose 시작 순서](https://docs.docker.com/compose/how-tos/startup-order/)
