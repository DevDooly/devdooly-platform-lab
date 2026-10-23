import { useEffect, useMemo, useState } from 'react';
import { closedFormWindow, parseWindowEvidence, windowSizes } from '../lib/ai-window';
import type { WindowProfile, WindowSize } from '../lib/ai-window';
import '../styles/ai-window.css';

const repo = 'https://github.com/DevDooly/devdooly-platform-lab';
const javaSource = `${repo}/blob/main/examples/java-window-analysis/src/main/java/io/github/devdooly/examples/window/`;
const number = (value: number, digits = 2) => value.toLocaleString('ko-KR', { maximumFractionDigits: digits });
const snippets = {
  broken: `// 입력의 +09:00을 버린 뒤 UTC로 다시 붙이는 의도적 오류
OffsetDateTime.parse(text)
    .toLocalDateTime()
    .toInstant(ZoneOffset.UTC);`,
  fixed: `// 명시적인 offset을 실제 UTC 시점으로 변환한 뒤 알려진 오차를 뺀다.
Instant start = OffsetDateTime.parse(startedAt).toInstant()
    .minusNanos(knownClockSkewNanos);
Instant end = OffsetDateTime.parse(endedAt).toInstant()
    .minusNanos(knownClockSkewNanos);
// 창에 걸친 구간은 자르고, 창 밖 구간은 제외한다.`,
  quadratic: `// 정렬한 각 경계 사이 구간마다 모든 세션을 다시 검사한다.
for (long boundary : boundaries) {
    if (previous != null) {
        int active = 0;
        for (var session : input.sessions()) {
            if (session.startNanos() <= previous
                    && session.endNanos() > previous) active++;
        }
        if (active > 0) covered += boundary - previous;
        peak = Math.max(peak, active);
    }
    previous = boundary;
}`,
  sweep: `// 동일 시점의 시작/종료를 합친 뒤 한 번 순회한다.
var deltas = new TreeMap<Long, Integer>();
for (var session : input.sessions()) {
    deltas.merge(session.startNanos(), 1, Integer::sum);
    deltas.merge(session.endNanos(), -1, Integer::sum);
}
for (var boundary : deltas.entrySet()) {
    if (active > 0) covered += boundary.getKey() - previous;
    active += boundary.getValue();
    peak = Math.max(peak, active);
    previous = boundary.getKey();
}`,
};

function Code({ title, text, file }: { title: string; text: string; file: string }) {
  return <details className="ai-window-code"><summary>{title}</summary><pre><code>{text}</code></pre>
    <a href={`${javaSource}${file}.java`} target="_blank" rel="noreferrer">발췌한 Java 전체 소스 ↗</a></details>;
}

/** A static personal case study. Selectors only choose recorded/closed-form data. */
export default function AiWindowCase({ record, observationUrl }: { record?: unknown; observationUrl?: string }) {
  const [interactive, setInteractive] = useState(false);
  useEffect(() => { setInteractive(true); }, []);
  const [loadedRecord, setLoadedRecord] = useState<unknown>(record);
  useEffect(() => {
    if (record !== undefined || !observationUrl) { setLoadedRecord(record); return; }
    const controller = new AbortController(); const timer = window.setTimeout(() => controller.abort(), 8000);
    async function load() {
      try {
        const response = await fetch(observationUrl!, { signal: controller.signal, redirect: 'error', credentials: 'omit' });
        if (!response.ok || !response.body) throw new Error('STATIC_RECORD_UNAVAILABLE');
        const reader = response.body.getReader(); const chunks: Uint8Array[] = []; let size = 0;
        try {
          for (;;) {
            const next = await reader.read(); if (next.done) break;
            size += next.value.length; if (size > 65_536) throw new Error('STATIC_RECORD_OVERSIZE'); chunks.push(next.value);
          }
        } finally { await reader.cancel(); }
        const bytes = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
        const parsed: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
        if (!controller.signal.aborted) setLoadedRecord(parsed);
      } catch { if (!controller.signal.aborted) setLoadedRecord(null); }
      finally { window.clearTimeout(timer); }
    }
    void load(); return () => { controller.abort(); window.clearTimeout(timer); };
  }, [record, observationUrl]);
  const evidence = useMemo(() => parseWindowEvidence(loadedRecord), [loadedRecord]);
  const [profile, setProfile] = useState<WindowProfile>('sparse');
  const [size, setSize] = useState<WindowSize>(128);
  const expected = closedFormWindow(profile, size);
  const measured = evidence?.measurements.find(row => row.profile === profile && row.size === size);
  const maximum = measured ? Math.max(measured.quadratic.meanMicros, measured.sweep.meanMicros) : 1;
  const largeError = measured && (measured.quadratic.errorMicros / measured.quadratic.meanMicros >= .25
    || measured.sweep.errorMicros / measured.sweep.meanMicros >= .25);
  const conditions = evidence?.conditions;
  return <section id="ai-window" className="section ai-window-section" aria-labelledby="ai-window-title">
    <div className="section-heading ai-window-heading"><div><span className="eyebrow">05 / AI SUGGESTION → TEST → MEASURE</span>
      <h2 id="ai-window-title">같은 시간을 가리키는지부터,<br/>더 적게 계산하는 방법까지.</h2>
      <p>시간대 오류를 고친 뒤, 같은 답을 구하는 두 Java 알고리즘을 별도 JMH로 비교합니다.</p></div>
      <span className="tag">독립 합성 예제 · 운영 ETL과 구분</span></div>
    <p className="ai-window-scope">개인 Java 예제입니다. 회사 코드·반도체 수율 공식·실제 제조 데이터는 사용하지 않습니다.
      AI 제안의 채택 여부는 개발자의 검토와 독립적인 기대 결과로 판단하며, 아래 공개 기록의 사람 검토 상태는
      <strong> {evidence?.humanReview === 'REVIEWED' ? '검토 기록 있음' : '검토 대기'}</strong>입니다.</p>

    <div className="ai-window-cards">
      <article className="ai-window-card"><span className="code-label">01 / FIX THE UTC TIMELINE</span><h3>09시 +09:00은 UTC 00시</h3>
        <p><code>2026-10-15T09:00:00+09:00</code>부터 10초간의 세션을 UTC 00시의 1분 창에서 찾습니다.</p>
        <dl className="ai-window-before-after"><div><dt>offset을 버린 오류 코드</dt><dd>합집합 0초 · 동시 세션 0</dd></div>
          <div><dt>UTC 시점을 유지한 코드</dt><dd>합집합 10초 · 동시 세션 1</dd></div></dl>
        <p className="ai-window-note">Java 회귀 테스트에 고정한 사례입니다. 브라우저에서 Java를 실행한 결과가 아닙니다.
          주어진 시계 오차를 빼는 보정이며 NTP·오차 추정기는 구현하지 않습니다.</p>
        <Code title="의도적으로 잘못된 UTC 코드 펼치기" text={snippets.broken} file="DeliberatelyBrokenUtcNormalizer"/>
        <Code title="UTC 정규화 수정 코드 펼치기" text={snippets.fixed} file="UtcNormalizer"/>
      </article>
      <article className="ai-window-card"><span className="code-label">02 / PRESERVE THE SAME ANSWER</span><h3>경계마다 전부 검사 → 변화량 한 번 순회</h3>
        <p>시간창을 <code>[시작, 종료)</code>로 다룹니다. 서로 맞닿은 세션은 겹치지 않으며 같은 시점의 시작·종료를 함께 반영합니다.</p>
        <dl className="ai-window-before-after"><div><dt>정확한 기준 구현</dt><dd>O(n²) · 경계마다 전체 세션 검사</dd></div>
          <div><dt>개선 구현</dt><dd>O(n log n) · TreeMap 경계 집계</dd></div></dl>
        <p className="ai-window-note">둘 다 추가 메모리는 O(n)입니다. 비교 대상은 동일한 정규화 입력이며 문자열 파싱·정규화 시간은 JMH 측정에서 제외합니다.</p>
        <Code title="기준 알고리즘 펼치기" text={snippets.quadratic} file="QuadraticBoundaryScan"/>
        <Code title="개선 알고리즘 펼치기" text={snippets.sweep} file="SweepLineAnalysis"/>
      </article>
    </div>

    <div className="ai-window-fixture"><div className="ai-window-fixture-heading"><div><span className="code-label">03 / FIXTURE & RECORDED JMH</span>
      <h3>입력 분포와 크기를 골라 비교하기</h3></div><div className="ai-window-controls" aria-busy={!interactive}>
        <label htmlFor="ai-window-profile">분포<select id="ai-window-profile" value={profile} disabled={!interactive} aria-describedby="ai-window-input-help" onChange={event => setProfile(event.target.value as WindowProfile)}>
          <option value="sparse">떨어진 구간 · sparse</option><option value="nested">중첩 구간 · nested</option></select></label>
        <label htmlFor="ai-window-size">세션 수<select id="ai-window-size" value={size} disabled={!interactive} aria-describedby="ai-window-input-help" onChange={event => setSize(Number(event.target.value) as WindowSize)}>
          {windowSizes.map(value => <option key={value} value={value}>{number(value, 0)}개</option>)}</select></label>
      </div></div>
      <p id="ai-window-input-help" className="ai-window-note">{!interactive && '화면 조작 준비 중입니다. '}선택은 정적 기대 결과와 이미 측정한 기록만 바꿉니다. 새 benchmark·서버 작업을 실행하지 않습니다.</p>
      <p>{profile === 'sparse' ? '11ms 구간을 17ms 간격으로 배치합니다. 겹침이 없어 합집합은 n×11ms, 최대 동시는 1입니다.' : '모든 세션이 동시에 시작하고 종료를 1ms씩 늘립니다. 합집합은 n×1ms, 최대 동시는 n입니다.'}</p>
      <dl className="ai-window-expectation" aria-live="polite"><div><dt>합집합 길이 · 닫힌 형태 기대값</dt><dd>{number(expected.coveredNanos / 1_000_000)}<small> ms</small></dd></div>
        <div><dt>최대 동시 관측 세션 · 기대값</dt><dd>{number(expected.peakConcurrentSessions, 0)}<small>개</small></dd></div></dl>
      <p className="ai-window-note">최대 동시는 관측 세션 수이며 고유 물리 센서 수가 아닙니다. 기대값은 Java fixture의 수학적 정의를 표시한 것입니다.</p>
      {measured && evidence && conditions ? <>
        <div className="ai-window-chart" aria-hidden="true">{([['기준 · 전체 경계 검사', measured.quadratic], ['개선 · sweep line', measured.sweep]] as const).map(([label, metric], index) =>
          <div className="ai-window-bar-row" key={label}><span>{label}</span><div className="ai-window-bar-track"><i className={index === 0 ? 'ai-window-bar-baseline' : 'ai-window-bar-sweep'} style={{ width: `${metric.meanMicros / maximum * 100}%` }}/></div><strong>{number(metric.meanMicros * 1000)} ns/op</strong></div>)}</div>
        <div className="ai-window-table-wrap" tabIndex={0} role="region" aria-label="JMH 측정 표 · 작은 화면에서 가로로 스크롤"><table className="ai-window-table"><caption>기록된 JMH 평균 시간 · op는 선택한 fixture 전체 한 번의 분석</caption>
          <thead><tr><th scope="col">구현</th><th scope="col">평균 ± JMH 오차 (ns/op)</th><th scope="col">할당량 (B/op)</th></tr></thead>
          <tbody><tr><th scope="row">기준 O(n²)</th><td>{number(measured.quadratic.meanMicros * 1000)} ± {number(measured.quadratic.errorMicros * 1000)}</td><td>{number(measured.quadratic.allocationBytesPerOp)}</td></tr>
            <tr><th scope="row">개선 O(n log n)</th><td>{number(measured.sweep.meanMicros * 1000)} ± {number(measured.sweep.errorMicros * 1000)}</td><td>{number(measured.sweep.allocationBytesPerOp)}</td></tr></tbody></table></div>
        <p className="ai-window-ratio">평균 시간 비율 · 기준 ÷ 개선 <strong>{number(measured.ratio)}배</strong></p>
        <p className="ai-window-note">작을수록 빠른 시간 지표입니다. 평균의 비율은 운영 처리량·개별 호출의 지연·p95·SLA를 뜻하지 않습니다.</p>
        {largeError && <p className="ai-window-uncertainty">이 조합은 보고된 JMH 오차 폭이 평균의 25% 이상인 구현을 포함합니다.
          짧은 측정에서 큰 오차가 관측되었으므로, 위 배수를 안정적인 성능 개선율로 일반화하지 않습니다.</p>}
        <details className="ai-window-code"><summary>실제 측정 조건과 출처 펼치기</summary><dl className="ai-window-conditions">
          <div><dt>실행 환경</dt><dd>Windows · Java {conditions.javaVersion} · JMH {conditions.jmhVersion}</dd></div>
          <div><dt>측정 종료 UTC</dt><dd><time dateTime={evidence.measuredAt}>{evidence.measuredAt}</time></dd></div>
          <div><dt>JVM과 반복</dt><dd>fork {conditions.forks}개 · thread {conditions.threads}개 · G1 · heap {conditions.heapMiB}MiB · {conditions.timezone}</dd></div>
          <div><dt>warmup / measurement</dt><dd>{conditions.warmupIterations} × {conditions.warmupMillis}ms / {conditions.measurementIterations} × {conditions.measurementMillis}ms</dd></div>
          <div><dt>출처 커밋</dt><dd>{evidence.sourceCommit ? <code>{evidence.sourceCommit}</code> : '측정 당시 미커밋 예제 · 실제 소스 트리 해시로 식별'}</dd></div>
          <div><dt>소스 트리 / benchmark JAR SHA-256</dt><dd><code>{evidence.sourceTreeSha256}</code><br/><code>{evidence.jarSha256}</code></dd></div>
          <div><dt>fixture manifest SHA-256</dt><dd><code>{evidence.fixtureManifestSha256}</code></dd></div>
          <div><dt>비공개 원본 JMH JSON SHA-256</dt><dd><code>{evidence.rawResultSha256}</code></dd></div>
          <div><dt>선택 입력 / 정규화 입력 / 결과 SHA-256</dt><dd><code>{measured.rawSha256}</code><br/><code>{measured.normalizedSha256}</code><br/><code>{measured.resultSha256}</code></dd></div>
        </dl><p className="ai-window-note">짧은 warmup과 세 fork는 모든 JIT·OS 잡음을 제거하지 않습니다. 이 고정 분포·환경의 관측으로만 해석합니다. 원본 측정 파일은 비공개 보존하고 공개 요약을 별도로 제공합니다.</p></details>
        <div className="ai-window-links"><a href={evidence.evidenceLinks.readme} target="_blank" rel="noreferrer">실제 검증·측정 근거 ↗</a><a href={evidence.evidenceLinks.source} target="_blank" rel="noreferrer">fixture·테스트·JMH 소스 ↗</a></div>
      </> : <p className="ai-window-pending" role="status">JMH 측정 기록이 아직 연결되지 않았거나 공개 형식을 확인하지 못했습니다. 기대 결과만 표시하며 측정 시간·개선율을 대신 만들지 않습니다.</p>}
    </div>
  </section>;
}
