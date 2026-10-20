# 비동기 로딩 뒤 초기 직접 링크 위치

2026-10-21 KST, 화면의 초기 fragment 진입만 수정하고 로컬 브라우저에서 확인했습니다.

## 기존 공개 화면에서 확인한 문제

새390×844 탭에서 `#tls-certificate`로 바로 접속한 뒤 입력 없이 작업 조회 완료까지 기다렸습니다. hash는 같았지만 TLS 대상의 viewport top은16,413.27px로 화면 밖이었습니다. 위쪽의 비동기 카드가 늘어나 초기 fragment 위치와 달라질 수 있는 구조입니다. fetch·폰트·브라우저 scroll anchoring 각각의 기여도를 따로 측정한 것은 아닙니다.

## 적용 범위

head의 짧은 inline script가 새 문서 navigation의 초기 hash 한 개만 처리합니다. 유효하고 보이는 대상의 위치를 초기10초 동안 최대4회 정렬합니다. 첫 위치 확인 뒤에는 대상의 document 좌표가1px 넘게 바뀐 경우만 확인하며, CSS scroll padding·margin을 따르고 애니메이션·초점 이동은 추가하지 않습니다.

사용자의 trusted wheel·touch·pointer·key 입력이나 resize·hash/history 변경·pagehide가 오면 즉시 종료합니다. 한 개의 ResizeObserver와 최대 한 개의 대기 frame을 사용하고 종료 시 timer·listener까지 정리합니다. hash 없는 진입·reload·뒤로/앞으로 복귀는 대상이 아닙니다. API 요청·관측 데이터·시각·출처는 바꾸지 않습니다.

## 실제 브라우저 확인

실제 앱의 새 직접 진입을 입력 없이 확인했습니다. 로컬390px에서는 TLS top119.59px·문서 폭375px, 1280px에서는 top119.33px·문서 폭1265px로 제목이 화면에 남았습니다. hash는 같고 focus는 BODY였습니다.

동일 script를 head에 그대로 넣은 임시 로컬 HTML에서 위쪽 높이를160px씩 늘려 제한 조건도 대조했습니다. fixture는 성공이나 보정 횟수를 출력하지 않으며 아래 수치는 브라우저 DOM에서 읽었습니다.

| 경우 | 관측 결과 |
| --- | --- |
| 초기 두 높이 증가 | top80px 유지, scrollY720→1040 |
| 10초 이후의 높이 증가 | top240px로 이동, scrollY1040 유지: 자동 보정 없음 |
| 다섯 번 증가·최대4회 | top240px, scrollY720→1360: 마지막160px는 보정하지 않음 |
| 첫 증가 전 실제 pointer 클릭 | 세 번 증가 뒤 scrollY720 유지·top560px, 버튼 초점 유지 |
| 첫 증가 전 실제 Tab 입력 | 원래 입력의 scrollY730·top70에서 세 번 증가 뒤 scrollY730·top550, 버튼 초점 유지 |
| hash 없는 진입 | 다섯 번 증가 뒤 scrollY0 유지·top1600px |
| reload | 다섯 번 증가 뒤 scrollY720 유지·top880px |

임시 fixture는 빌드 출력의 단일 파일로만 배치했고 검증 뒤 제거했습니다. 공개 소스·운영 자료·통과 표시로 게시하지 않습니다. wheel·touch 및 DOM 준비 전 입력은 취소 코드의 정적 검토 범위이며 별도의 실제 기기 시험으로 확대하지 않습니다.

기존 웹207개 검사·skip0, Astro47파일 오류0·경고0, 루트/프로젝트 경로 두 빌드를 통과했습니다. 207개는 기존 데이터·관측 계약 검사이며 위 브라우저 동작과 구분합니다.

## 공개 확인

PR161의 main `b23b3800349c0f577933d2907bf8c7e0ead62078`에서 [Pages39469520695](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39469520695)·[컨테이너CI39469520692](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39469520692) 성공을 확인했습니다. 공개 페이지의 새 직접 진입에서도 입력 없이 작업 조회를 마친 뒤390px target top120.27px·문서375px, 1280px top120.86px·문서1265px였습니다. hash는 같고 focus는 BODY, details는 기본 닫힘을 유지했으며 기존 클릭·Enter 토글도 확인했습니다. 이는 공개 웹 수정 확인이며 TLS 재관측·자연 갱신·운영 worker 배포를 수행한 결과는 아닙니다.
