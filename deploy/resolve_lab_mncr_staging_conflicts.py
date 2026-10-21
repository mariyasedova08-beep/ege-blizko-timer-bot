#!/usr/bin/env python3
"""Safely reconcile the four *known* Mn/Cr staging conflicts.

This tool NEVER accesses /opt/bots, Telegram, SQLite or production services.
It writes ONLY to an isolated merge-check-* directory, preserving a verbatim
copy of the unmerged source and requiring all four conflict patterns.
The theme and guided laboratory are PRIVATE server changes and are not
uploaded to GitHub by running this tool.
"""
import argparse
import ast
import pathlib
import re
import shutil
import subprocess

BLOCK = re.compile(r"(?ms)^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n?")
FORBIDDEN_TAGS = ("</style", "<script", "</script", "</head", "</body")
EXPECTED_KEYS = (
    'id="labThemeButton"',
    'href="/lab-solubility"',
    'data-page="guided"',
    'data-page="lesson"',
    'id="lessonMediumField"',
    'id="tubeMediumField"',
)

def reconcile(source: str):
    blocks = list(BLOCK.finditer(source))
    if len(blocks) != 4 or source.count("<<<<<<< ") != 4:
        raise ValueError("Expected EXACTLY four known conflicts; aborting")
    resolved = []
    summaries = []
    for idx, match in enumerate(blocks, 1):
        ours, theirs = match.group(1), match.group(2)
        if idx == 1:
            if "body[data-lab-theme]" not in theirs or "lesson" not in ours.lower():
                raise ValueError("Conflict 1 is not lesson CSS versus existing themes")
            if any(tag in piece.lower() for tag in FORBIDDEN_TAGS for piece in (ours, theirs)):
                raise ValueError("Conflict 1 crosses a CSS/HTML boundary")
            result = ours.rstrip("\n") + "\n" + theirs.rstrip("\n") + "\n"
            summary = "lesson CSS + all existing theme CSS"
        elif idx == 2:
            if 'href="/lab-solubility"' not in ours or 'id="labThemeButton"' not in theirs:
                raise ValueError("Conflict 2 is not solubility link versus theme button")
            result = ours.rstrip("\n") + "\n" + theirs.rstrip("\n") + "\n"
            summary = "solubility link + existing theme picker"
        elif idx == 3:
            if (ours.count('lessonRenderPage()') != 1 or
                    theirs.count('renderGuided()') != 1 or
                    'if(b.dataset.page==="guided")' in ours or
                    ours.count('if(b.dataset.page==="exam"') != 1):
                raise ValueError("Conflict 3 navigation pattern unexpectedly changed")
            result = ours.replace('if(b.dataset.page==="exam"',
                                  'if(b.dataset.page==="guided")renderGuided();if(b.dataset.page==="exam"')
            summary = "retain PDF page handler + guided page handler"
        elif idx == 4:
            if (ours.count('lessonSetup();') != 1 or
                    theirs.count('renderGuided();') != 1 or
                    'renderGuided();' in ours):
                raise ValueError("Conflict 4 initialization pattern unexpectedly changed")
            result = ours.replace('lessonSetup();', 'lessonSetup();renderGuided();')
            summary = "initialize PDF lesson + guided mode"
        resolved.append((match.start(), match.end(), result))
        summaries.append(summary)
    for start, end, text in reversed(resolved):
        source = source[:start] + text + source[end:]
    if "<<<<<<<" in source or ">>>>>>>" in source or re.search(r"(?m)^=======$", source):
        raise ValueError("Unresolved conflict marker remains")
    return source, summaries

def validate_merged(source: str):
    tree = ast.parse(source)
    nodes = [
        n.value for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name) and t.id == "HTML"
    ]
    if len(nodes) != 1:
        raise ValueError("Expected one HTML assignment")
    html = ast.literal_eval(nodes[0])
    for key in EXPECTED_KEYS:
        if key not in html:
            raise ValueError("Feature lost from merged HTML: " + key)
    if html.count('id="labThemeButton"') != 1:
        raise ValueError("Theme button duplicated")
    if 'function renderGuided(' not in html or 'function lessonSetup(' not in html:
        raise ValueError("Expected live guided and PDF functions are absent")
    if 'if(b.dataset.page==="guided")renderGuided()' not in html:
        raise ValueError("Guided page navigation not integrated")
    if html.count('lessonSetup();renderGuided();') != 1:
        raise ValueError("PDF/guided setup not integrated")
    scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", html, re.I)
    if len(scripts) != 2:
        raise ValueError("Unexpected number of HTML scripts")
    if shutil.which("node"):
        check = subprocess.run(["node", "--check"], input=scripts[-1],
                               text=True, capture_output=True, timeout=15)
        if check.returncode:
            raise ValueError("Merged JavaScript syntax invalid: " + check.stderr[-1500:])
        print("MERGED_JAVASCRIPT_SYNTAX_OK")
    else:
        print("MERGED_JAVASCRIPT_SYNTAX_NOT_RUN: node unavailable")
    print("MERGED_PYTHON_SYNTAX_OK")
    print("GUIDED_THEME_PDF_ELEMENTS_OK")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Staging repo/ege_lab_webapp.py with four conflicts")
    parser.add_argument("--apply-staging", action="store_true",
                        help="Modify ONLY staging file after validating and backing up conflict text")
    args = parser.parse_args()
    path = pathlib.Path(args.path).resolve(strict=True)
    if (path.name != "ege_lab_webapp.py" or "repo" not in path.parts or
            not any(v.startswith("merge-check-") for v in path.parts) or
            not str(path).startswith("/root/ege-blizko-staging/")):
        parser.error("Refusing non-staging path")
    raw = path.read_text(encoding="utf-8")
    merged, summaries = reconcile(raw)
    validate_merged(merged)
    for idx, item in enumerate(summaries, 1):
        print("RESOLVED_%d: %s" % (idx, item))
    output = path.parent.parent / "merged-candidate"
    output.mkdir(mode=0o700, exist_ok=True)
    candidate = output / "ege_lab_webapp.py"
    if candidate.exists() and candidate.read_text(encoding="utf-8") != merged:
        raise ValueError("A DIFFERENT merged candidate exists; refusing overwrite")
    candidate.write_text(merged, encoding="utf-8")
    candidate.chmod(0o600)
    print("MERGED_CANDIDATE_CREATED")
    if args.apply_staging:
        original = output / "ege_lab_webapp.with_conflicts.py"
        if original.exists():
            raise ValueError("Original conflicts already backed up; refusing repeat")
        original.write_text(raw, encoding="utf-8")
        original.chmod(0o600)
        path.write_text(merged, encoding="utf-8")
        print("STAGING_FILE_UPDATED")
    else:
        print("STAGING_FILE_UNCHANGED")
    print("PRODUCTION_UNTOUCHED")
    print("STAGING_MERGE_RESOLVED_OK")

if __name__ == "__main__":
    main()
