# Contributing to Agent Defense Guide

[Русский](CONTRIBUTING.ru.md) · [Overview](README.md)

Issues and pull requests are welcome in **English or Russian**. A small, well-supported
correction is a useful contribution.

## Good first contributions

- Reproduce one config example, including a legitimate control case. Record the commit,
  tool versions, command, and observed result.
- Correct one dated entry in [tools.csv](data/tools.csv) using a primary source and a new check date.
- Translate one risk or control page into English. Keep the evidence labels, citations,
  and limitations; open an issue first if you want to coordinate a longer translation.
- Bring evidence for one of the [coverage gaps](gaps.md).

## Suggest a tool

Use the [tool suggestion form](https://github.com/Andy9542/guide-asi/issues/new?template=tool-suggestion.yml).
Include:

1. The repository and primary documentation.
2. Its SPDX license, OSI status where known, and relevant obligations or commercial limitations.
3. The [control point](README.md#control-points) where it belongs.
4. The related ASI risks, measured coverage, and limitations.
5. Whether your evidence is `[стенд]` (a recorded experiment) or `[дока]` (documentation).

The selection criteria are an identifiable license, recent activity, and evidence of
adoption. See [how tools were selected](README.md#how-tools-were-selected). Record dates
in the data; an excluded candidate belongs in [rejected.csv](data/rejected.csv) with its reason.

## Report an error or a broken example

Use the [correction form](https://github.com/Andy9542/guide-asi/issues/new?template=correction.yml).
Link the affected file and commit. Include the expected and actual behavior, a primary
source or minimal reproduction, and the impact on the guide's claim. Remove credentials
and personal data from logs.

For incidents, cite a vendor report, advisory, CVE record, or original technical research.
Distinguish a demonstrated incident from a hypothesis or an attack class.

## Evidence and wording

- Keep `[стенд]`, `[дока]`, and `[пробел]` distinct. A documentation claim does not become
  a measured result because a tool was added to the table.
- State what an experiment covers and which assumptions it needs.
- Measure legitimate behavior as well as the attack where possible.
- Explain limitations alongside capabilities. Avoid unsupported absolute claims.
- Keep English and Russian landing pages consistent when changing shared facts.

## Before opening a PR

Run the local link check:

```sh
python3 build/check_links.py
```

For changes to an executable example, run its relevant tests and record the result.
The full suite is `sh build/selftest.sh`; its prerequisites are in the
[quickstart](docs/quickstart.md). Explicitly note any check you could not run.

Keep changes focused. In the PR, explain the problem, resulting behavior, evidence,
and limitations. Respect the existing [license split and attribution](NOTICE.md).
