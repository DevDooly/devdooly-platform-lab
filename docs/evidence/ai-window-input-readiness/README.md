# AI 예제의 초기 선택 입력 보호

2026-10-23 KST. Java 예제와 측정 기록을 바꾸지 않고 공개 화면의 입력 준비 상태만 보완했습니다.

## 문제와 변경

빌드 HTML에서 script 요소만 제거한 임시 사본을 로컬 브라우저에서 열었습니다. 분포와 세션 수는 활성 상태였고, native 입력으로 `nested`·`512`를 선택해도 기대값은 초기 `sparse`·`128`의 **1,408ms·동시 1개**로 남았습니다. 이 사본은 JavaScript 실행 전 SSR 상태이며 실제 느린 통신의 전환 시간을 측정한 시험은 아닙니다.

두 선택 입력은 서버 렌더와 첫 클라이언트 렌더에서 같은 준비 전 상태로 출력하고, mount 후 활성화합니다. 준비 중에는 설명과 `aria-busy`를 표시합니다. 측정 기록 다운로드 완료를 기다리지 않으므로 선택 입력과 기록 로딩은 분리됩니다. 코드 펼치기와 원본 링크는 native 기능으로 유지합니다.

Java 코드·계산 함수·기대값 정의·측정 JSON·사람 검토 상태·기록 요청은 변경하지 않았습니다. 새 benchmark나 서버 작업도 실행하지 않았습니다. JavaScript를 실행하지 못하면 고정 기대값을 읽을 수 있고 선택은 비활성 상태로 남습니다.

## 로컬 검증

- 변경 후 SSR 사본에서 두 select가 모두 disabled, 준비 안내·`aria-busy=true`, 초기 기대값·‘검토 대기’가 유지됨을 실제 DOM으로 확인했습니다. 코드 펼치기는 JavaScript 없이도 작동했고 원본 링크 4개를 유지했습니다. 임시 사본은 Git·Pages 배포 출력에 넣지 않았습니다.
- 실제 앱에서 준비 완료 후 두 입력 활성화·`aria-busy=false`·준비 안내 해제를 확인했습니다. `nested`·`512`는 **512ms·동시 512개**, `sparse`·`4096`은 **45,056ms·동시 1개**를 표시했습니다. 측정 기록 표와 사람 검토 대기도 유지됐습니다.
- 390px 화면에서 두 입력을 실제로 바꾸어 기대값을 확인했습니다. 문서 폭과 scrollWidth는 모두 375px였습니다.
- 기존 웹 273개 통과·skip 0, Astro 50파일의 오류·경고·힌트 0, 프로젝트 경로의 2페이지 빌드를 통과했습니다.
- 다른 세션의 Job PR226 main을 통합한 뒤 웹 278개·skip 0, Astro 51파일의 진단 0, 2페이지 빌드도 통과했습니다. Job 수신부의 변경과 검증은 해당 PR의 별도 범위입니다.

이는 화면의 선택과 기대값 표시를 확인한 결과입니다. 측정 재실행·성능 향상·운영 ETL·사람의 알고리즘 검토 완료를 뜻하지 않습니다. Pages 토큰 교체·별도 환경 기동 복원·예산 정책·PR102는 계속 보류하며 운영 서비스·데이터·이미지 pin은 변경하지 않습니다.

## 공개 반영

[PR227](https://github.com/DevDooly/devdooly-platform-lab/pull/227)의 main `4414cb2a0e32eedf9c6ddee8802fb95b905072ae`에서 [Linux CI39968236060](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39968236060)의 verify·public-read-gateway와 [Pages39968236604](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39968236604)의 build·deploy가 성공했습니다. 별도 Spark·S3·Cloud·Iceberg capture 작업은 선택 조건에 따라 생략됐습니다.

2026-10-23 KST 공개 HTML·AI JS를 각각 한 번 읽어 SSR의 두 select disabled·준비 안내·`aria-busy=true`·사람 검토 대기를 확인했습니다. `AiWindowCase.BI1e3sER.js` 17,580바이트가 로컬 빌드와 전체 bytes·SHA256 `e2b6c655cf035e82215921fb3a4a35bb203dc960191e139df2e00ec8abe51105`까지 일치했습니다.

공개 브라우저에서 새 파일을 참조하는지 확인한 뒤, 측정 표가 아직 없을 때도 입력이 활성화돼 `nested`·`512`의 512ms·동시512개가 표시됨을 확인했습니다. 이후 기존 측정 표 2행이 로드됐고, `sparse`·`4096`의 45,056ms·동시1개도 확인했습니다. native 코드 펼치기와 원본 링크 4개·사람 검토 대기는 유지됐습니다. 모바일390px의 실제 선택과 기대값을 확인했고 문서 폭·scrollWidth는 모두375px였습니다. 이는 화면 동작과 기존 기록 표시 확인이며 새 Java 실행·benchmark·사람 승인 결과가 아닙니다.
