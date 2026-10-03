# EA-4E.92CF Kilo 7.8.3 Baseline Regression Comparison

## Source and isolation

The pre-roll baseline is the committed parent
`b4e2d364a8f7fdb113205c9ead4acd78cce2ad32`, exported with `git archive`
to an isolated temporary directory. The candidate is the committed source roll
`be511925e03a5a46dbb7abd77bb3d3c9752235e3`. Both were run on the same
Windows host with `py -3.14`, the same `tests/hermes_core` selector, and the
committed `tools.ea4e67_fake_only_guard` plugin. The temporary baseline
checkout is not the production checkout and was not used for any live task.

Command in each checkout:

```powershell
py -3.14 -m pytest tests\hermes_core -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard --tb=line --junitxml=<checkout-specific XML path>
```

JUnit artifacts retained in the host temporary directory:

| Tree | XML artifact | XML SHA-256 |
| --- | --- | --- |
| baseline | `ea4e92ce-baseline-b4e2d36-20261003.xml` | `36a2291cb08a02790a723ffcd2b712ab86fce267f71d3d232a436c0f84cbda73` |
| candidate | `ea4e92ce-candidate-be51192-20261003.xml` | `94c34673ef7084ef6ae7b84b2a513c1bd4d33af3fc8f11daf1cd3dd05760f903` |

## Result

| Tree | Passed | Failed | Subtests passed |
| --- | ---: | ---: | ---: |
| baseline | 4,646 | 89 | 104 |
| candidate | 4,679 | 56 | 104 |

Failure identities were compared as JUnit `classname::name`, without using
failure counts alone as a proxy:

- All 56 candidate failures also failed in the baseline.
- Candidate-only failure identities: **0**.
- Baseline-only failure identities: **33**.
- SHA-256 of the 56 shared failure IDs, sorted ordinally and joined by LF:
  `b161933a7e5d6e8438a820dd8e943b79ed80ef4a28f90f813895db35bbd66348`.

The baseline-only failures include old Kilo binary identity/path tests and
checkout-location-dependent fixtures. Their disappearance is not asserted
to be a product fix: the old installed executable was absent, and the
baseline ran from a temporary export while the candidate ran from the
working checkout. The common failures include process-oriented tests denied
by the fake-only guard, stale host pins, and missing historical artifacts.
This comparison supports **no new failing test identity** for the 7.8.3
source roll under this bounded fake-only gate. It does not make the complete
suite green, qualify real process execution, or establish production readiness.

## Boundary

`FULL_HERMES_CORE_GREEN=NO`  
`CANDIDATE_ONLY_FAILURE_IDENTITIES=0`  
`PRODUCTION_ACTIVATED=NO`  
`REAL_RECEIVER_OR_MODEL_ACTIVITY=0`

The 92CD and 92CE commits remain local. The earlier 92CD push was denied;
this evidence does not renew push authorization. Any real receiver probe
remains a separately governed live boundary. The exact mapped-byte proof
requirement for the separate 92S/native-creation path remains HOLD.
