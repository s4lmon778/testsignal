# TestSignal

Turn JUnit XML into an inspectable failure-triage report. Import test attempts into SQLite, compare two explicit runs and export HTML, JSON and CSV with source digests and per-attempt diagnostics.

[Inspect the synthetic example report](https://s4lmon778.github.io/testsignal/). This is a published example output; the importer runs locally.

Requires Python 3.11+; no third-party packages.

```powershell
python -m unittest -v
python testsignal.py --db runs.sqlite3 import baseline examples/baseline.xml
python testsignal.py --db runs.sqlite3 import current examples/current.xml
python testsignal.py --db runs.sqlite3 report 2 --baseline 1 --out report
```

Open `report/index.html`. The included example reports are synthetic.

Results distinguish passing, failing, skipped and mixed outcomes. Mixed means a passing and a failing attempt share the same file/class/name identity in a report; it is an observed instability signal, not a root-cause diagnosis. Baseline comparison identifies regressions, recoveries, new cases and cases missing from the current report. Missing and skipped cases are not reported as passes. Re-importing the same label and bytes is idempotent; conflicting labels and invalid XML fail before a partial import.

JUnit producers differ. This importer supports UTF-8 testsuite/testsuites documents with testcase elements and failure/error/skipped children or supported status attributes. It rejects unsupported testcase children, ambiguous statuses, invalid durations, empty reports, DTD/entity declarations and files above 8 MB. Supply explicit baseline run IDs and inspect attempt evidence. Test names and diagnostics are escaped in HTML and formula-like CSV fields are neutralized. Source reports can contain private logs: keep generated databases and reports local.

This tool summarizes recorded test evidence. It does not infer a failure's root cause, call an LLM, operate CI, or approve a release.
