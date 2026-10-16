"""Explicit future callable entrypoint; import starts no workload or decoder."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys
import time

import decoder_lifecycle as decoder
import lifecycle as life


def persist(folder, name, raw):
    import os
    with (folder / name).open('xb') as stream:
        if os.name == 'posix': os.fchmod(stream.fileno(), 0o600)
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return {'raw': raw, 'sha256': life.sha(raw)}


def utc():
    return datetime.now(timezone.utc).isoformat()


def safe_normalization_failure(error, normalizer, stage):
    """Recognize only the exact source-pinned wrapper and its finite phase."""
    try:
        if stage != 'NORMALIZE': return 'UNKNOWN'
        if type(error) is normalizer.NormalizationFailure:
            code = getattr(error, 'phaseCode', None)
            if type(code) is str and code in normalizer.NORMALIZATION_PHASE_CODES: return code
    except BaseException:
        pass
    return 'UNKNOWN'


def run(producer, observer, loader, normalizer, *, source_commit, output,
        authority_source_sha256, component_source_pins, prep_proof, prep_sha256,
        decoder_source_sha256, classes, iceberg, policy):
    """Trusted source-pinned caller loads modules; no CLI/workflow wiring added."""
    own = life.read_proof(Path(__file__).absolute())
    life.require(own['sha256'] == authority_source_sha256
        and re.fullmatch('[a-f0-9]{40}', source_commit), 'EXACT_COMPOSITE_SOURCE_AUTHORITY')
    life.require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and os.environ.get('SOURCE_COMMIT') == os.environ.get('GITHUB_SHA') == source_commit,
        'SAME_SOURCE_GITHUB_HOSTED_LINUX_ONLY')
    # Caller module bindings are trusted, not a sandbox for hostile Python globals.
    for module in (life, decoder, observer, loader, normalizer):
        path = Path(module.__file__).absolute()
        life.require(path.name in component_source_pins and life.read_proof(path, 262144)['sha256']
            == component_source_pins[path.name], 'EXACT_COMPONENT_SOURCE_BYTES_REQUIRED')
    life.require(sys.argv[1:] == ['--source-manifest-sha256', life.RUNTIME, '--ack-fresh-cloud-trial9'],
        'UNMODIFIED_ORIGINAL_MAIN_ARGUMENTS_REQUIRED')
    planner = life.read_proof(producer.HERE.parents[1] / 'infra/maintenance/iceberg_retention_plan.py')
    life.require(planner['sha256'] == 'ec1ff5dc06d9da666d9ef1d32557937e36e0a63bc124f08ad6ed39edbf0224ae',
        'EXACT_FROZEN_PURE_PLANNER_SOURCE')
    output = Path(output).absolute()
    life.require(output.parent.resolve(strict=True) == output.parent and not output.exists(),
        'FRESH_CANONICAL_COMPOSITE_OUTPUT')
    output.mkdir(mode=0o700)
    summary_path = producer.HERE.parents[1] / '.local/cloud-trial9-public/summary.json'
    life.require(not summary_path.parent.exists(), 'NO_PRIOR_PRODUCER_PUBLIC_DIRECTORY')
    persist(output, 'intent.json', life.encoded({'scope': 'ONE_FROZEN_MAIN_AND_ONE_NEW_DECODER_ONLY',
        'sourceCommit': source_commit, 'authoritySourceSha256': authority_source_sha256,
        'producerSha256': life.PRODUCER, 'runtimeManifestSha256': life.RUNTIME,
        'observerManifestSha256': life.OBSERVER, 'automaticRetry': False}))
    seen = owned_decoder = None
    main_calls = 0; main_return = None; failure = None; result = None; stage = 'PREP'
    normalization_failure_code = 'UNKNOWN'
    try:
        # Only consumes actual prior prep; never builds inside original main/hooks.
        prepared = decoder.prep(prep_proof, prep_sha256, classes, iceberg, source_commit, decoder_source_sha256)
        stage = 'ORIGINAL_MAIN'
        with observer.named_observer(producer, output / 'named', source_commit) as seen:
            main_calls += 1
            main_return = producer.main()
        stage = 'PRODUCER_PROOFS'
        authority = life.validate_producer(producer, seen, main_return, output / 'named', summary_path,
            authority_source_sha256)
        authority['validation'] = persist(output, 'validation.private.json', authority['validation']['raw'])
        stage = 'WRITERS_BEFORE'
        before = life.stopped_snapshot(producer, seen, authority['clock'], utc(), authority_source_sha256)
        authority['lifecycle'] = persist(output, 'writers-before.private.json', life.encoded(before))
        life.remaining(producer, seen, decoder.RESERVE)
        stage = 'LOAD_CLOSED_COPIES'
        request = loader.derive_request(authority, authority_source_sha256)
        loaded = loader.load_closed_copies(seen.attempt.root, request, authority, authority_source_sha256)
        life.require(type(loaded['frameBytes']) is bytes and type(loaded['descriptorBytes']) is bytes,
            'ACTUAL_CLOSED_COPY_FRAME_AND_DESCRIPTOR_REQUIRED')
        owned_decoder = decoder.Decoder(prepared, output / 'decoder', seen.attempt.project, seen.deadline_started,
            canonical_host=producer.canonical_host, canonical_mounts=producer.canonical_mounts)
        stage = 'DECODER'
        decoded = owned_decoder.run(loaded['frameBytes'])
        stage = 'WRITERS_AFTER'
        after = life.stopped_snapshot(producer, seen, authority['clock'], utc(), authority_source_sha256, reserve=0)
        after['scope'] = 'POST_DECODER_EXACT_STOPPED_FRESH_CLOUD_ACTORS'
        life.require(before['roles'] == after['roles'] and before['initializer'] == after['initializer'],
            'SAME_ALL_STOPPED_WRITERS_BEFORE_AND_AFTER_DECODER')
        after_proof = persist(output, 'writers-after.private.json', life.encoded(after))
        receipt = {'schemaVersion': 1, 'scope': 'OWN_DECODER_CONTAINER_BOUNDED_STOPPED_AND_REAPED',
            'authoritySourceSha256': authority_source_sha256, 'sourceCommit': source_commit,
            'producerSha256': life.PRODUCER, 'runtimeManifestSha256': life.RUNTIME,
            'prepProofSha256': prep_sha256, 'decoderSourceSha256': decoder_source_sha256,
            'runtimeImageReference': decoder.SPARK, 'runtimeImageId': prepared['imageId'],
            'icebergJarSha256': decoder.ICEBERG_SHA, 'mainClass': decoder.MAIN,
            'clockSha256': authority['clock']['sha256'], 'originalStartedMonotonic': seen.deadline_started,
            'originalAbsoluteCutoff': owned_decoder.absolute, 'decodeCutoff': owned_decoder.cutoff,
            'cleanupReserveSeconds': decoder.RESERVE, 'capturedAt': utc(), 'finishedMonotonic': time.monotonic(),
            'cid': decoded['cid'], 'exitCode': decoded['exitCode'],
            'ownDecoderStopped': True, 'attachCliReaped': True, 'watchdogFired': False,
            'replySha256': decoded['reply']['sha256'], 'replyBytes': len(decoded['reply']['raw']),
            'frameSha256': life.sha(loaded['frameBytes']), 'descriptorSha256': life.sha(loaded['descriptorBytes']),
            'writersBeforeSha256': authority['lifecycle']['sha256'], 'writersAfterSha256': after_proof['sha256'],
            'originalRoleStopCallsAdded': 0, 'originalInitializerStopCallsAdded': 0}
        receipt_proof = persist(output, 'decoder-lifecycle.private.json', life.encoded(receipt))
        decoder_bundle = {**receipt_proof, 'reply': decoded['reply'], 'writersAfter': after_proof}
        life.remaining(producer, seen)
        stage = 'NORMALIZE'
        result = normalizer.normalize_graph(decoded['reply']['raw'], loaded, authority, decoder_bundle, planner['raw'],
            now=utc(), policy=policy, expected_authority_source_sha256=authority_source_sha256)
        life.remaining(producer, seen)
        persist(output, 'normalization.private.json', life.encoded(result))
        stage = 'COMPLETED'
    except BaseException as error:
        normalization_failure_code = safe_normalization_failure(error, normalizer, stage)
        text = str(error)
        failure = text if re.fullmatch('[A-Z0-9_]{1,128}', text) else 'COMPOSITE_FAILED_OR_UNKNOWN_NO_RETRY'
    finally:
        # Decoder.run owns cleanup. Never stop original roles, recreate, or retry.
        finished = {'scope': 'COMPOSITE_SOURCE_BOUND_PIPELINE_NOT_PUBLIC_COMPLETENESS',
            'sourceCommit': source_commit, 'authoritySourceSha256': authority_source_sha256,
            'mainCallsStarted': main_calls, 'mainReturnedZero': type(main_return) is int and main_return == 0,
            'lastStage': stage, 'inventoryProduced': result is not None and result.get('inventory') is not None,
            'failureCode': failure, 'safeNormalizationFailureCode': normalization_failure_code,
            'pipelineFinishedWithoutException': failure is None,
            'decoderCreatedKnownCid': owned_decoder is not None and owned_decoder.cid is not None,
            'decoderStoppedVerified': owned_decoder is not None and owned_decoder.stopped,
            'decoderAttachCliReaped': owned_decoder is not None and owned_decoder.cli_reaped,
            'originalRoleStopCallsAdded': 0, 'originalInitializerStopCallsAdded': 0,
            'automaticRetry': False, 'snapshotExpirationOrGcPerformed': False,
            'publicCompletenessClaimed': False}
        persist(output, 'composite-result.private.json', life.encoded(finished))
    return {'result': result, 'receipt': finished, 'exitCode': 0 if failure is None else 1}
