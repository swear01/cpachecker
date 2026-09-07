# Issue 203 Java/context integration

## Result

Successor branch: `integration/203-java-context-successor`

Base: personal fork `origin/main@08fc281180b9d6f18453aa7ea684ea026ad59d3d`.

Integrated in requested order:

1. PR #193 (`57d2210b568744d336d377964687080594927105`): native-width and global-SSA handling, raw candidate attribution, and array/native regression tests. Its notes-only change was excluded.
2. PR #185 (`9868c055044da22d06046323d862ac19c535ae15`): predicate-precision ownership/lifecycle filtering and regression tests.
3. PR #190 (`e3ad856237b97f9fecd5d61b2327e628af9d760c`): context retention, source selection, prompt component accounting, dumper accounting, and tests.

All three applied without a merge conflict before rebasing onto the latest fork main. The only rebase conflict was the excluded `docs/notes.md`; it was resolved to current main. The final net diff is 15 Java production/test files and no docs change. PR #194 was not included; its wording variant and `L@N` priority cue remain outside production defaults.

## Verification

- `ant resolve-dependencies` — exit 0.
- `env JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 PATH=/usr/lib/jvm/java-21-openjdk-amd64/bin:$PATH ant all-checks` — ECJ build passed; 4,346 unit-test entries passed with 734 skips; 3,880 configuration-check entries passed with 768 skips; Checkstyle completed; SpotBugs reported the known missing Eclipse filesystem classes; final target stopped on 68 repository-wide forbidden-API findings, matching the accepted baseline class of findings.
- After rebase: `env JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 PATH=/usr/lib/jvm/java-21-openjdk-amd64/bin:$PATH ant -Divy.disable=true build-project` — exit 0.
- After rebase targeted JUnit invocation ran 55 tests. Core affected tests passed; five dumper/accounting tests failed in direct invocation because the standalone classpath did not supply the project’s expected `vguide.frozenDir` file configuration. The canonical Ant suite passed those classes before rebase; this direct invocation is not claimed green.
- `git diff --check` — exit 0.
- Generic pre-push helper failed immediately because it detected pytest, which is unavailable in this Java/Ant repository (`ModuleNotFoundError: No module named 'pytest'`). Native Ant verification above is the authoritative project check.

No solver reproducer, interpolation probe, provider/model change, benchmark, service change, harness/analyzer/lineage change, or #194 production wording change was made.
