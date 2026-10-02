# EA-4E.34B Kilo 7.5.15 Transport Contract Roll

## Result

```text
EA-4E.34B RESULT=HOLD
HOLD_REASON=STRICT_PROCESS_GUARD_RECORDED_FORBIDDEN_TEST_PROCESS_ATTEMPTS
COMMIT=NO
PUSH=NO
LIVE_AUTHORIZATION=NO
LIVE_EXECUTION=NO
```

The source roll and focused non-live qualification were not completed. The
strict process guard blocked five process-oriented tests in the selected Kilo
adapter suite. One was a direct `kilo.exe --version` probe. No blocked command
started, but EA-4E.34B requires zero blocked attempts and mandates an immediate
stop when a receiver-binary launch is attempted.

## Governing State

```text
GOVERNING_LOCAL_HEAD=263258a1d421f5f8d6ca518bfa2fe1afd9079bb5
GOVERNING_REMOTE_HEAD=263258a1d421f5f8d6ca518bfa2fe1afd9079bb5
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

EA-4E.34 and EA-4E.34A remain HOLD. Their historical outcomes were not
rewritten.

## Verified Successor Identity

```text
KILO_SUCCESSOR_PATH=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.15-win32-x64\bin\kilo.exe
KILO_SUCCESSOR_FILE_EXISTS=YES
KILO_SUCCESSOR_VERSION=7.5.15
KILO_SUCCESSOR_SIZE=170690048
KILO_SUCCESSOR_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
```

The installed `package.json` and `.vsixmanifest` identify version `7.5.15`,
publisher `kilocode`, target `win32-x64`, and repository
`https://github.com/Kilo-Org/kilocode.git`. Neither installed metadata file
contains a source commit. The work in progress therefore uses the explicit
sentinel `UNAVAILABLE_IN_INSTALLED_VSIX_METADATA` instead of retaining the
incorrect 7.5.6 source provenance.

## Preliminary Deterministic IDs

These IDs were calculated without executing any receiver. They remain
unqualified until a fresh authorized non-live phase completes the required
test ladder.

```text
OLD_KILO_TRANSPORT_CONTRACT_ID=c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500
NEW_KILO_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
NEW_KILO_EXECUTABLE_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
NEW_KILO_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
KILO_MODEL_BINDING_CHANGED=NO

EA-4E.6=292f7deeb479cd45c6f33f3466305e7f225c05d9f48f9eeb8dc13f944d7162a1
EA-4E.7=6de9f8b959db33bd2c2885396507baed47a3eadf07423c0e545afe4cc3274661
EA-4E.8=9785647334992c514ef56013c2e410be48c42a3c1813b377e601823387be67a2
EA-4E.11=af7d731ff21614f3ab0e92beb8927d3063e06707af7a9a89bc3d3b7c91e7927a
EA-4E.14=b057272ee70a4f5fceb9500ccf699097ed2de2edfc21e8f47fe3f9247e52f20b
EA-4E.17=5082b1a227a53cfe711bcf3c5d2193cd47031d75d7ec7650d8ab4c2389194e93
EA-4E.18=56471e6509ccc2e99a7b609354748c51a0ada18bda8b92648c21bec584c1ceb3
EA-4E.21=a25a6ba03b6a44f35511bec4b89c332043cd252ea3d1e185bd1b0a5c966fee33
EA-4E.22=0e9d206a0b5d78592bafad624421439774e6c7ffe34a7c9d4c41a66aeb0504bd
EA-4E.23=7bc3d2e036beacaef5aaabd054730dfbd49c57a0c36bbaab6f56894798be4687
EA-4E.26=2e7a4b360c54541ff408e8430d3ac9a28cdee76e0feef5e1da03b87a889657ba
EA-4E.28=90c96695f6294bed90eed1b630b1b44f7faca859b6b818ea2a744c1b753eb5b1
EA-4E.29=00c6808dada4c9cf74a0310a31c9a51b10c1a8ee770f8f6c8a45d4d1f4962dd2
```

The preliminary graph is acyclic. The affected chain is EA-4E.6, 7, 8, 11,
14, 17, 18, 21, 22, 23, 26, 28, and 29. EA-4E.30 through 33B are
qualification/evidence phases and no durable-store schema change was found.

## Strict Guard Incident

Command:

```text
python -m pytest
  tests/hermes_core/test_ea4e34b_kilo_successor_contract_roll.py
  tests/hermes_core/test_kilo_adapter.py
  tests/hermes_core/test_receiver_router.py
  -q
```

Result:

```text
PASSED=142
FAILED=5
BLOCKED_PROCESS_ATTEMPTS=5
BLOCKED_KILO_BINARY_ATTEMPTS=1
RECEIVER_PROCESSES_STARTED=0
MODEL_INVOCATIONS=0
```

Blocked commands:

1. `echo hello`
2. `cmd /c exit 1`
3. `echo hello`
4. `kilo.exe --version`
5. `echo hello`

The first, second, third, and fifth cases are process-controller tests. The
fourth is an explicitly live version-probe test. Selecting the entire adapter
suite under the strict guard was an incorrect test-scope choice for this
phase. The guard prevented all process creation; the result is nevertheless a
contractual HOLD, not a pass.

## Uncommitted Work In Progress

EA-4E.34B changed or created only:

- `tools/hermes_core/kilo_adapter.py`
- `tools/hermes_core/kilo_successor_binding.py`
- `tools/hermes_core/receiver_router.py`
- `tools/hermes_core/production_executor_binding.py`
- `tools/hermes_core/production_invocation_authorization.py`
- `tests/hermes_core/test_kilo_adapter.py`
- `tests/hermes_core/test_receiver_router.py`
- `tests/hermes_core/test_ea4e34b_kilo_successor_contract_roll.py`
- this evidence file

No file was staged, committed, or pushed. Existing unrelated tracked and
untracked work remains untouched.

## Required Continuation

A new explicit authorization must define a safe test selection that excludes
all process-oriented adapter tests while retaining the strict process guard.
The next phase must restart qualification from the governing checkpoint,
review this uncommitted WIP, run the focused successor tests and affected
contract suites, then run the broad safe non-live regression. It must not
reinterpret these blocked attempts as zero or convert this HOLD into a PASS.
