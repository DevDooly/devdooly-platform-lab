# PostgreSQL 재시작 뒤 같은 catalog와 데이터 읽기

2026-10-20 14:32:11 UTC, 새 hosted Linux의 [첫 실제 실행 39439657631](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39439657631)이 통과했습니다. Spark가 정상 종료하고 Trino가 아직 생성되지 않은 시점에 **같은 PostgreSQL 컨테이너와 볼륨을 한 번 정상 stop/start**했습니다. 새 Trino의 첫 조회와 전체 객체 GET으로 catalog·warehouse 보존을 대조했습니다.

## 실제 관측

| 경계 | 실제 결과 |
| --- | --- |
| 준비 | 새 전용 물리 volume3개·내부 network. 실제 Spark exit0·session 종료 뒤 writer 부재 확인 |
| 정상 종료 | 실제 `StopSignal=SIGINT` 설정의 소유 PG만 stop. stopped·non-OOM·실제 exit0·원 postmaster 소멸 확인 |
| 같은 대상의 시작 | 명시 start1회, 같은 full CID·Created/config·volume·DB system identifier. 새 StartedAt·postmaster와 실제 Docker RestartCount0 확인 |
| catalog | 두 catalog 테이블의 전체6+4열 schema·PK/index·logical rows 보존. Iceberg 테이블 등록 행2개와 namespace property 행6개 대조 |
| fresh Trino | SELECT10개, Bronze 시점별6/12/12·Silver12(성공7/실패3/중복2), snapshot3·현재 data file1과 독립 golden·Spark fingerprint 일치 |
| 전체 객체 | 두 heavy JVM 종료 뒤 read-only reader의 전체20객체 bytes·기존14객체 보존 및 stable LIST 대조 |
| 다른 자원 | Garage process·정상 종료한 Spark·initializer의 identity 보존. source·Docker/Compose tool 지문 불변 |
| 작업·정리 시간 | 실제106,252ms, 단일600초 조건 통과. image pull·JAR 준비·build는 이 값에서 제외 |
| 정리 | 검증한 자기 컨테이너·initializer의 stopped 상태 확인. volume 삭제·snapshot 만료·object GC 없음 |

PG 실제 exit는 **0**, Trino의 별도 TERM 요청 뒤 실제 exit는 **143**이었습니다. 두 값을 같은 종료 코드로 정규화하지 않았습니다. 수동 start1회와 자동 restart counter0도 별개로 기록했습니다. SIGINT 설정·stop 요청과 실제 종료를 확인했으며 signal 전달 자체를 직접 관측했다고 주장하지 않습니다.

이번 시험은 writer가 없는 새 격리 환경의 정상 catalog 재시작입니다. 운영 DB·기존 warehouse·미니 PC·SSH를 사용하지 않았습니다. 진행 중 transaction·끊긴 connection pool의 투명 재연결·crash/WAL 복구·host 재부팅·backup restore·HA·현재 가용성이나 SLA는 이 결과의 범위가 아닙니다. 자원 설정과 시간은 이 실행의 조건·관측값이며 운영 예산 정책을 정하지 않습니다.

## 변경 없는 원문과 출처

- [실제 summary](summary.json), [실행 metadata](run-metadata.json)
- 실제 source: [`a2a22048`의 실행기](https://github.com/DevDooly/devdooly-platform-lab/blob/a2a22048d47c534ae4322236dab254993c4abdfe/infra/cloud-catalog-restart/run_catalog_restart.py), [catalog adapter](https://github.com/DevDooly/devdooly-platform-lab/blob/a2a22048d47c534ae4322236dab254993c4abdfe/infra/cloud-catalog-restart/catalog_lifecycle.py)
- raw summary SHA-256: `2e12362df7affa89893c4c275c27dde8d8209bf8f0119136ee8d11c024aed297`
- runtime manifest SHA-256: `5d0bacc9bfc68814c83f08faee091cb8d05c94798e911ba5801284a7b83134aa`
- [PR146 CI 39439437002](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39439437002): Linux의 순수 경계 검사22개·skip0을 먼저 통과했습니다. 실제 Docker/SQL 시험과 구분합니다.

summary의 정확28필드, 검사18개, 결과7필드·catalog19필드·조회7필드와 metadata를 전체 대조했습니다. 실패·진단은 null, source/tool 불변·소유 자원 중지·단일 clock 조건이 모두 통과했습니다. 동결 소스의 README는 실행 전 상태를 그대로 보존하며, 실제 실행 결과는 이 문서를 따릅니다.

개인 합성 데이터만 사용했습니다. raw inspect·SQL/proof·PID/CID·DB system identifier·volume명·credential·object full copies는 공개하지 않습니다. 기존 source/helper/manifest·과거 증거는 변경하지 않았습니다. 토큰 교체·예산 정책·PR102는 보류합니다.

공개 기술별 근거 목록에 연결을 준비했습니다. 검색과 표시 개수 개선을 함께 검증한 뒤 게시합니다.
