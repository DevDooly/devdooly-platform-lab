# Iceberg closed-copy capture 후보

**실제 source613의 Linux84 통과, decoder lifecycle 검증 단계 미확인.** [여섯 번째 실행](../../docs/evidence/iceberg-capture/ATTEMPT_6.md)은 prep·원래 main 한 번/반환0·새 decoder 정지/CLI 회수를 확인했지만 SUMMARY_NOT_VERIFIED로 실패했습니다. NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED는 시도한 guard 구간이며 정확한 원인·decoder 종료 코드·graph를 특정하지 않습니다. 통합 actors/clock·inventory·전체 KEEP은 미확인이고 관측 count·정규화 hash는 null입니다. [다섯 번째 새 실행](../../docs/evidence/iceberg-capture/ATTEMPT_5.md)은 compiler prep, 원래 main 한 번·반환 0, 새 decoder 컨테이너 정지·attach CLI 회수를 확인했지만 `SUMMARY_NOT_VERIFIED`·`UNKNOWN`으로 실패했습니다. 통합 stopped actors·clock, inventory·전체 KEEP 검증과 decoder exit 0·유효 graph는 미확인이며 다섯 관측 count는 null입니다. 첫 실제 capture 실행 `38876152951`(source `48a7fee222c8a25a70c446ac55b9b458be2ccab2`)은 Linux 56개·skip0을 통과한 뒤 `PREP_NOT_VERIFIED`로 실패했습니다. [첫 실행 기록](../../docs/evidence/iceberg-capture/ATTEMPT_1.md)을 보존하며, prep 실패의 구체적 원인과 원래 main·decoder 실행 및 자원 정리 여부는 이 기록으로 확인되지 않았습니다. [두 번째 새 실행](../../docs/evidence/iceberg-capture/ATTEMPT_2.md)(source `b91a7324a831454554cc6d5293aa4142fd0ba812`, run `38881661893`)은 Linux 62개·skip0 이후 `JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED`로 prep에 실패했고 해당 prep cold 컨테이너 제거·부재를 확인했습니다. 이 사실은 첫 실패의 원인이나 원래 main·decoder·inventory 성공으로 소급하지 않습니다. [세 번째 새 실행](../../docs/evidence/iceberg-capture/ATTEMPT_3.md)(source `a03f87837af66fd3770063d9c712c4080e15d9fa`, run `38886641237`)은 Linux 67개·skip0 이후 `JAR_MANIFEST_BYTES_BOUND`로 prep에 실패했고 해당 prep cold 컨테이너 제거·부재를 확인했습니다. 빈 manifest·선언 크기 초과·읽은 길이 불일치 중 어느 분기인지는 미확인이며 실제 Class-Path closure·prep·decoder·inventory 성공은 확인되지 않았습니다. [네 번째 새 실행](../../docs/evidence/iceberg-capture/ATTEMPT_4.md)(source `a00ddbccf859c249637f65303654dee659130bdc`, run `38890545126`)은 Linux 73개·skip0 이후 `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`으로 prep에 실패했고 해당 prep cold 컨테이너 제거·부재를 확인했습니다. 특정 JAR·token·경로는 미확인이며 실제 전체 closure·prep·compile·decoder·inventory 성공으로 확대하지 않습니다. 이 결과를 세 번째 바이트 guard 실패의 원인으로 소급하지 않습니다. 이 디렉터리는 동결된 observer·loader·composite·Java decoder와 전체 classpath 트리·실제 부재 검증 helper·진단 CLI의 검증 소스입니다. 원래 Cloud producer `73e229…`, runtime manifest `c63aded…`, 기존 성공 기록 `127168…`과 retention planner `ec1ff5…`는 변경하지 않습니다. 기존 성공이 이 새 capture/decoder의 성공을 뜻하지 않습니다.

모듈 import는 workload를 실행하지 않습니다. 명시적인 `composite_entry.run(...)`은 source-pinned CLI가 원래 main을 observer 안에서 한 번 호출하고, 같은 실행의 기록과 실제 stopped actor를 검사한 뒤 승인된 whole copies만 RAM decoder에 전달하는 경계입니다. 임의 caller/module을 격리하는 sandbox가 아닙니다. 이전 source316은 다섯 번째 실행에서 Linux 80개·skip0과 compiler prep 검증을 통과했습니다. 원래 main 한 번·반환 0과 새 decoder 정지·CLI 회수도 확인했지만 normalization·inventory·전체 capture는 실패/미확인으로 남습니다. 이후 [진단 변경](NORMALIZATION_PHASES.md)을 포함한 source613은 Linux84·skip0을 통과했고 이번 정규화 guard 구간을 기록했습니다. 정확한 원인이나 해결·전체 capture 성공을 주장하지 않으며 다음 수정 범위·검사 수는 미정입니다.

현재 **runtime 11개, 테스트 파일 8개, WIRE 계약과 runtime manifest**를 원본 동결본에서 모았습니다. Prep 실행기·classpath archive·bounded process·명시적 CLI는 포함되지만 source 준비가 실제 Linux/Cloud 성공을 뜻하지 않습니다. 합성 Java fixture, Windows 검증 runner, private 실제 artifact 또는 자격증명은 runtime payload에 넣지 않습니다.

CLI는 첫 번째 시도인 GitHub-hosted Linux job에서 actual checkout/SOURCE_COMMIT/GITHUB_SHA와 모든 source pin을 확인한 뒤에만 동작합니다. `--ack-fresh-closed-copy-capture`가 필요하며, 과거 workflow run의 재실행을 받아들이지 않습니다. 준비는 원래 main/clock 전에 별도 최대600초로 제한하고 원래 workload600초는 유지합니다. [워크플로우 후보](../../.github/workflows/lab-ci.yml)의 `run_iceberg_capture_trial`은 기본false이며 기존 세 시험 플래그가 false인 경우 새 job만 선택합니다.

```text
python3 -I -B infra/iceberg-retention-ci/run_capture.py \
  --source-manifest-sha256 8c0dd76a436a5c5b8554015fbd90192e8514a8d261be67382335da9bbbcf1098 \
  --ack-fresh-closed-copy-capture
```

업로드 대상은 새 `.local/iceberg-closed-copy-public/summary.json` 하나입니다. Private tree·원래 producer summary·descriptor·graph·로그·Env를 업로드하지 않습니다. 관측되지 않은 count는 null이며 objectCandidate0은 KEEP-only 정책입니다. Schema2의 공개 필드와 PASS 조건은 유지합니다. 기존 129/134/138/144개 prep·CLI 리터럴은 각각의 정확한 runtime manifest에 연결합니다. 새 runtime `8c0dd76a436a5c5b8554015fbd90192e8514a8d261be67382335da9bbbcf1098`만 기존144개와 별도의 정규화 단계11개를 합한 고정155개를 허용하며 UNKNOWN fallback을 유지합니다. 단계11개는 정확한 실패 NORMALIZE 영수증의 출처·타입·유한값이 검증될 때만 쓰고, 원래 예외·provider 문구를 공개하지 않습니다. [Manifest 한도](MANIFEST_BOUNDS.md)는 unpack 경로만 8MiB·export 합계32MiB로 제한하고 기본 locked-JAR 64KiB 검사는 유지합니다. [Closed Class-Path 경계](CLASSPATH_CLOSURE.md)의 기본 strict map과 locked-JAR 검사는 유지합니다. 새 [트리·부재 경계](ABSENT_CLASSPATH.md)는 unpack에서 전체 추출 트리를 검증하고 안전한 참조의 실제 ENOENT만 별도로 기록하며 javac 전후 같은 트리·부재 digest를 비교합니다. 모든 참조가 존재하거나 dependency가 해결됐다고 주장하지 않습니다. JAR bytes·prep 실행 명령·원래 producer·SQL·자원 한도·실행/정리 명령·600초 clock은 바꾸지 않습니다. 명령 프로세스의 시작·reap은 Docker 컨테이너 lifecycle 증거가 아닙니다. 정확한 허용 필드와 미확인 처리는 [SCHEMA2.md](SCHEMA2.md)에 기록합니다. `normalizationReceiptCanonicalSha256`는 private receipt 하위 객체의 canonical SHA로서 전체 private 파일 SHA가 아닙니다.

## 보수적 범위

세 named JDBC checkpoint만으로 writer quiescence·전체 closure·pin authority를 추론하지 않습니다. source-bound 원래 summary, Spark/reader/clock, SELECT intent, stop 기록과 별도 actor 증거를 다시 묶습니다. enclosing root0700 안의 원래 proof0777/copy 소유권은 변경하지 않고 Linux held-FD/nofollow/whole SHA reader로 검사합니다.

Decoder는 format2 current metadata와 승인된 map 안의 manifest-list/manifest를 읽습니다. ADDED/EXISTING/**DELETED**, shared manifest 및 position-delete reference도 snapshot closure에 남깁니다. old metadata와 target 밖의 객체는 KEEP입니다. 미지원/누락/충돌은 UNDETERMINED이며 가짜 inventory를 만들지 않습니다. Parquet 내용·과거 metadata 복원·live table 독립검증은 하지 않습니다. Planner 후보도 **expiry/GC/apply/객체삭제를 실행하지 않고 모든 객체를 KEEP**합니다.

새 decoder의 예정 제한은 CPU1/512MiB/PID64, heap256MiB, user185, network-none/readonly-root와 readonly class/JAR mount 두 개입니다. 입력은 최대128객체·개별4MiB·합계32MiB, descriptor512KiB, reply4MiB, private stderr64KiB입니다. 기존 단일600초 안에서 `min(now+60, started+600-40)` cutoff를 사용하고 새 exact CID의 stop/wait/inspect 및 CLI reap을 별도로 확인합니다. Java relative watchdog만으로 컨테이너 종료를 주장하지 않습니다. [WIRE_CONTRACT.md](WIRE_CONTRACT.md)가 정확한 형식입니다.

## 검증 상태

새 진단 후보의 CLI14개+정규화4개는 root의 Windows 한 번에서 17개 PASS·POSIX 전용1개 skip·실패/오류0을 기록했습니다. 원본 source3b59의 테스트 미실행 표시는 동결 당시 상태입니다. 전체 Linux84개(base27+archive24+bounded7+prep8+CLI14+normalization4)는 실제6에서 UID0·skip0·source 전후 동일로 통과했습니다. 해당 Cloud 결과는 SUMMARY_NOT_VERIFIED 실패이며 decoder lifecycle guard 구간만 구분됐습니다. 새 gate는 테스트8개의 literal SHA를 import 전에 확인하고 UID0·84개·skip0·source 전후 동일을 요구합니다. 이 focused 결과로 graph·inventory·capture 성공을 채우지 않습니다.

원본 Windows 합성 suite는 observer6·loader8·composite10 PASS이며 Linux 전용3개는 skip입니다. Portable 복사본은 경로 식만 바꾸고 역치환 byte equality 및 나머지 AST equality를 확인했으며 숫자 재현 목적으로 재실행하지 않았습니다. Base27의 UID185 fixture에는 실제 격리 Linux 소유권 조건이 필요합니다.

기존 Linux 전체56개는 첫 실행에서, 진단 추가 뒤 전체62개는 두 번째 새 실행에서 각각 실제 UID0·skip0으로 통과했습니다. 이전 archive13개 검사는 Windows에서 10개 PASS·POSIX 전용3개 skip이며, CLI14개는 기존 13개 PASS·POSIX 전용1개 skip을 보존하고 literal-only 확장 뒤 반복하지 않았습니다. 이 합성 검사는 실제 Docker·Java·download를 실행하지 않았습니다. **Linux 전체67개(base27+archive13+bounded7+prep6+CLI14)는 세 번째 실행에서 실제 skip0으로 통과**했습니다. 이 결과를 현재 manifest 호환 후보의 검사나 prep 성공으로 채택하지 않습니다. 새 archive19개는 Windows에서 15개 PASS·POSIX 전용4개 skip이며, **이전 a00 source의 Linux 전체73개(base27+archive19+bounded7+prep6+CLI14)는 네 번째 실행에서 실제 skip0으로 통과**했습니다. 다음 호환 정책·새 source의 성공을 뜻하지 않습니다. 새 archive24개·prep8개 합성 검사는 허가된 Windows 한 번에서 합계32개 중 24개 PASS·POSIX 전용8개 skip·실패/오류0을 기록했습니다. 이 결과는 실제 POSIX 부재 검증이나 새 Linux 성공이 아닙니다. 해당 CI gate는 CLI와 runtime/원래 source 전체 및 테스트7개의 literal SHA를 import 전에 확인했고 UID0·80개(base27+archive24+bounded7+prep8+CLI14)·skip0을 다섯 번째 실행에서 실제 통과했습니다. 이 통과를 다음 source나 전체 normalization 성공으로 채택하지 않습니다. `sudo -n env -i` 검사는 새 temp fixture만 쓰며 저장소의 `.local`을 root 소유로 만들지 않습니다.

Java는 기존 locked Iceberg1.11 JAR와 로컬 JDK21의 실제 metadata/Avro writer 합성7그룹, clean compile(stderr0), blocked-stdin watchdog124, Python frame→Java→Python graph 및 closure 변조 거부를 통과했습니다. 실패1~5와 성공6~7은 원래 패킷에 보존됩니다. 로컬 SLF4J 지원은 Cloud payload가 아니며, 시도5의 compilerPrepVerified는 true지만 공개 요약만으로 전체 참조 graph·normalization 성공이나 개별 JAR 정체를 확인하지 않습니다. 이 로컬 fixture 검증은 새 dependency 다운로드·실제 warehouse artifact 읽기·Cloud 실행을 포함하지 않습니다.

## 고정 source provenance

다음 runtime bytes 중 `normalize_graph.py`·`composite_entry.py`·`run_capture.py`만 새 정규화 단계 진단 후보이며, 나머지 여덟 개는 source316과 정확히 같습니다. 기존 검증 본문·PASS gate·600초 clock·자원·정리·retry 정책은 변경하지 않습니다.

| 파일 | SHA-256 |
| --- | --- |
| `named_observer.py` | `39c4330db7b5b0ce78deb7bf1607aa540e3d3fa94c3a78e70bb8fcbd5bbf9840` |
| `copy_loader.py` | `7e894d29204271d75dd086d1901f9893e983a56f598599c5b37ca768b55c87c0` |
| `normalize_graph.py` | `4e2b0766df48bf5b31bfe8aa437f0b051597ac6455c26af48b5f326340e80a0d` |
| `composite_entry.py` | `0ef5ca6758ae37d43c27cddf7fa4fe344c2a8020ab88885c60d9349fa4047a4b` |
| `lifecycle.py` | `0186c34faaaa516f2935ba4bf5ff578277c005950ac2e5dc7de3d6ae82836a36` |
| `decoder_lifecycle.py` | `4b6a2e061d1b92d828520d0b99fb81a63f102d68ca953ee7186f6141cb553d96` |
| `src/org/apache/iceberg/ClosedCopyDecoder.java` | `d7f9fbab4e1951e5364dcec7e78b8aa1b86531ba034a4c1748b47158a80399d9` |
| `prep_decoder.py` | `f4eba5fdfb31020da9e4a68a64be8961abfea955c97f941eac7bdae8c20bd61a` |
| `archive_classes.py` | `cafc02e4c55779e7b7062108c64cc4aaf33c452e03a1b9b04144e271c01e3f68` |
| `bounded_process.py` | `87ec98e6f4df8de69a413eeb01ccff30135e4d72b02675d9be6627564fe1ddc6` |
| `run_capture.py` | `fa8c0d6d01eddef3f6ed39036ae99dd3c1f9bc0409f13c384b61d1b31f78897b` |

Upstream manifest SHA는 observer `801f6aa7bbe7717ff26a9d925478d7608256741537cf6f0cf52381ccaca0c4c3`, loader `3241fc55b1d2b0c041cccba98c93456a1170152abdf774daf733a60f8bce2d5e`, composite `08a1d9d107f3c726b1c48ec429b5ba1647325c1ec9ff7b24a945087fb134709b`, Java `418ba424383bf2385929b4654f7e24b7319e757ee7b1988176e974e2844f7d8c`입니다. WIRE SHA는 `cf50399646013459b4ad71f882d387b6d9a2bcba1263c2b30ca6af3d6168dc34`입니다.

추가 prep source/test의 upstream manifest SHA는 `d8443327515812c401edcfe494be2c762afc4057c160089dc76c47774a403f50`입니다. 이 원본 prep 패킷은 보존합니다. `bounded_process.py`와 그 테스트는 원본 bytes 그대로이며, 이전 prep와 closed Class-Path helper/test manifest `d52b83c712ed57f231b58bce528d59441c6a282477a30c992157e4324c07b0f6`를 보존하고, 이전 bounded manifest helper/test manifest `e08d17096aec440429f5520bfeb51ac163e8699478f1e722c3c611073d8b14ce`도 보존합니다. 새 archive/prep와 두 테스트는 manifest `7a1c34c1e7d022be292ffc8996f069a93ed59528f3deeb6461b55bee2c523543`에 묶습니다. 이 source 패킷의 미실행 상태는 동결 당시 기록입니다. 이후 시도5의 compiler prep 검증 결과는 상단에서 별도로 구분합니다.

이전 CLI source/test manifest `d26b6ede7b8de02204cc48ff6d87f27b403e3d549b414308442e2b72a19f0fa1`, CLI `9338364fc5563f6d7bec63f39519b0b03364e82e2f74de22f2caa83cc76ba216`, runtime manifest `c8cecad8fc09ab20a78382c4a96daf5c9e761065cb774abd6cd9b65d0ee8be28`과 첫 실제 실패 기록은 보존됩니다. 이전 schema2 CLI `2408512f8373713ba6766364177472cfddb2d35c3210e0868cbfa2f2a77b1917`, 패킷 `484a08a6e94ad9cde6f0fcfeb3b15d40f3a371041c22efd8bfed77c2866369b5`, runtime manifest `53493f2dfeedee530ad152b5dc08f2c08b3d560ac39fac887820129913c8db3d`과 두 번째 실제 실패 원문 `a88f6ef6bd012e9858554fd0c44d22a834141940da9b61381998ef16b7a585b9`도 보존합니다. 이전 Class-Path CLI manifest `7e0944de8e1d32a5cd66628228a7cd071f2cc2d8371d9937d6c64eb8f3087d80`·runtime `a9704dce98583b3935e05ac759a3b0e9c8af839fb9b3fa141ad1d96a13708f18`·시도3 원문 `7b5cd2213e8beb6cf988932eb54465828205c81eeb979aef58044f75cd882340`도 보존합니다. 이전 bounded manifest CLI upstream `5752359eb0a8551f113999250dfdbc237cc30000437ff37de95391b6add648a3`·runtime `6aea1d3987d4a258718f4fd242d05ff1364a73cf4772272260975fce7eb172cd`·시도4 원문 `78e07be0b1116224507481de08f15a8792b26277d7734e79b2b6e8883d4dd1af`도 보존합니다. 이전 6리터럴 CLI upstream manifest SHA는 `bdd22dfdbdce59e3d333abd7a541404f5bc903d64c18a586fe94da1d74bc218c`이며 CLI test bytes는 이전과 같습니다. 이전 runtime `c8a3d89458bca95a98547472816c5fb35f922aea934cd7da1a0cd4534c0c6fbf`와 실제5 원문 `a7976a9cb3d81c349be87be4e3959d982f0b4adadef758d1615228f9cbe48fa5`는 보존합니다. 새 진단 source3+test2 manifest는 `3b59cae846b2ea63f88215a6721451018d1ab2345e6e2eebe673eaf14938f430`, 통합 runtime manifest SHA는 `8c0dd76a436a5c5b8554015fbd90192e8514a8d261be67382335da9bbbcf1098`입니다. 기존 testCLI는 영수증 fixture UNKNOWN 한 필드만 추가했고 새 focused 파일4개 메서드를 포함합니다. 원래 producer/runtime/planner/lock/역사적 성공 summary는 immutable input 다섯 개로 묶으며 새 결과로 덮지 않습니다.

Portable 테스트는 원본과 다른 SHA입니다. `PLATFORM_LAB_SOURCE_ROOT` 또는 최종 파일 위치의 저장소 루트에서 `infra/...` source를 찾도록 경로만 바꿨습니다.

| 테스트 | 원본 SHA-256 | Portable SHA-256 |
| --- | --- | --- |
| `test_named_observer.py` | `92b14fff5b2312cba6d325e9587603fd2f1a3cadd094a726e19b33ecd11498a1` | `85ff4307d821dcb0c4ba8a8eb9ec4e4927ac158d887f3899df62ac9cdca8a477` |
| `test_copy_loader.py` | `d796bf3cb7d1a68cd84337b6aa915cee739d4fb494e58787df025b2b4ba062e1` | `fb8ad9febef1d307244d57f4944d043985d1a756a4b5559a8e442fe752423196` |
| `test_composite.py` | `bae7acf4000a5e57cf738adece84e54dd16e56df0cf0d202d1ff48920e322f48` | `2f7080816959573c845281d023e1a7346ced6626593806c1e0a52c5be7e6173c` |
