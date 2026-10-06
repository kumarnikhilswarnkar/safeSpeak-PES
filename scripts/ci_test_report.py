"""Publish pytest results from JUnit XML files in GitHub Actions.

Writes a summary table to $GITHUB_STEP_SUMMARY (shown on the run page) and an
error annotation for each failing test (up to 10 per file), so results are
readable without opening the raw logs. Outside GitHub Actions it just prints.

    python scripts/ci_test_report.py "Backend (SQLite)" pytest-sqlite.xml ...
"""
import os
import sys
import xml.etree.ElementTree as ET


def main() -> int:
    if len(sys.argv) < 3 or len(sys.argv) % 2 == 0:
        print("usage: ci_test_report.py LABEL FILE [LABEL FILE ...]", file=sys.stderr)
        return 2
    rows, annotations = [], []
    for label, path in zip(sys.argv[1::2], sys.argv[2::2]):
        if not os.path.exists(path):
            rows.append(f"| {label} | not run | | | |")
            continue
        root = ET.parse(path).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        tests, failures, errors, skipped = (int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
        passed = tests - failures - errors - skipped
        rows.append(f"| {label} | {passed} | {failures + errors} | {skipped} | {float(suite.get('time', 0)):.0f} s |")
        count = 0
        for case in suite.iter("testcase"):
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            if problem is None or count >= 10:
                continue
            count += 1
            name = f"{case.get('classname')}::{case.get('name')}"
            detail = (problem.get("message") or problem.text or "").strip().replace("\n", " ")[:900]
            annotations.append(f"::error title={label}: {name}::{detail}")
    summary = "\n".join(
        ["### Test results", "", "| Suite | Passed | Failed | Skipped | Time |", "|---|---|---|---|---|", *rows, ""]
    )
    print(summary)
    for line in annotations:
        print(line)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(summary + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
