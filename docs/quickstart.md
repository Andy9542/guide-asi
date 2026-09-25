# Quickstart

[Overview](../README.md) · [Русский](quickstart.ru.md)

Start with a small local check, then choose a control for your architecture.
Commands assume a POSIX shell on Linux, macOS, or WSL and Python 3.10+.

## 1. Check the evaluation contract

```sh
git clone https://github.com/Andy9542/guide-asi.git
cd guide-asi
python3 configs/redteam/classify_test.py
```

Already cloned? Run only the last command from the repository root.
Expected final line: `classify_test: 58 случаев, расхождений 0`, exit 0.
The Russian summary means “58 cases, zero mismatches.”

This uses the Python standard library and local fixtures. After cloning, it needs
no network, model, API key, Docker, or Node.js. It checks classification of promptfoo
results, including missing results, cached responses, and evaluator errors.
It does not test a live agent.

## 2. Check which configs may run

From the repository root, create an isolated Python environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r configs/redteam/requirements.txt
python3 configs/redteam/preflight_test.py
```

Dependency installation needs package-registry access; the checks run locally.
Expected summary: `preflight_test: 85 случаев, расхождений 0`, exit 0.
On Debian/Ubuntu, install the distribution's `python3-venv` package if creating the
environment reports that `ensurepip` is unavailable.

The preflight limits the config shape before invoking promptfoo. For example, it rejects
a dynamic `package:` assertion value. Provider `config` remains trusted: the validator
is not a sandbox for hostile configurations.

## 3. Run a local echo evaluation

Keep the virtual environment active. You need Node.js with npm/npx; CI uses Node 22.
The first invocation downloads pinned **promptfoo 0.123.0 and its dependencies**;
the repository records an npm footprint of roughly **2.6 GB**. Allow time and disk
space for that download. Echo itself uses no model or API key.

```sh
(
  work=$(mktemp -d) || exit 3
  trap 'rm -rf "$work"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1
  export PROMPTFOO_CONFIG_DIR="$work/promptfoo"
  export REDTEAM_CONFIG="$PWD/configs/redteam/testdata/echo-pass.yaml"
  export REDTEAM_JSON="$work/results.json"
  sh configs/redteam/run.sh
)
```

Expected: `REDTEAM_VERDICT=pass`, exit 0. Change `echo-pass.yaml` to `echo-fail.yaml`
to exercise a failed evaluation: `REDTEAM_VERDICT=fail`, exit 1. The temporary export
is removed when the subshell ends; the npm cache is retained.

The red-team wrapper uses **0 = pass, 1 = fail, 3 = infrastructure/no verdict**.
Echo checks the harness wiring. To evaluate a model, read the
[red-team walkthrough](../configs/redteam/README.md), review the supported config
profile, and connect your gateway. Live model calls can incur provider charges.

## 4. Pick a control

| Your immediate question | Start with | What to verify |
|---|---|---|
| Can the agent rewrite its MCP config? | [OPA](../configs/opa/) | Deny protected paths; allow a legitimate path; distinguish a broken policy |
| What gets installed with an agent's dependencies? | [Semgrep + OSV](../configs/semgrep/) | Findings, clean scans, and incomplete scans have different outcomes |
| Who sent this message, and was it already accepted? | [Message signing](../configs/bus-signing/) | Sender, recipient, tampering, freshness, and replay handling |
| Can I see the control's decision? | [OpenTelemetry](../configs/otel/) | Decision-span fields and the deployed collection path |
| Where should model credentials live? | [LiteLLM](../configs/litellm/) | Gateway boundary, keys, access rules, and live integration |

The detailed walkthroughs are currently in Russian. Each states its measured behavior
and deployment limits. For architecture review, use the [seven control points](../README.md#control-points).

## Full selftest

You need Docker with a working daemon, Node.js/npm/npx, OpenSSL, and Python with PyYAML
and cryptography. Install PyYAML as above; read the cryptography pin from the signing
selftest, as CI does. Run these from the repository root:

```sh
pin=$(sed -n "s/^CRYPTOGRAPHY_VERSION='\(.*\)'$/\1/p" configs/bus-signing/selftest.sh)
test -n "$pin" && python3 -m pip install "cryptography==$pin"
sh build/selftest.sh
```

The full selftest downloads pinned packages/images as needed and exercises local
services. The [workflow](../.github/workflows/selftest.yml) is the reference environment:
Ubuntu 24.04, Python 3.12, Node 22. Live gateway/collector deployment checks are documented
separately in their config directories.

## Make one useful contribution

Reproduce one example with its legitimate control case. Record the commit, versions,
command, expected result, and actual result. A dated tool correction or one English
translation is also welcome. See [CONTRIBUTING.md](../CONTRIBUTING.md).
