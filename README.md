<a name="гайд-по-защите-ии-агентов"></a>

# Agent Defense Guide

![Agent Defense Guide — map risks, place controls, verify outcomes](assets/brand/readme-banner.svg)

**Practical AI agent security: map OWASP agentic risks to open-source controls, runnable examples, and their limits.**

[![Selftest on main](https://github.com/Andy9542/guide-asi/actions/workflows/selftest.yml/badge.svg?branch=main)](https://github.com/Andy9542/guide-asi/actions/workflows/selftest.yml)
[![Text: CC BY-SA 4.0](https://img.shields.io/badge/text-CC_BY--SA_4.0-526579)](LICENSE)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache_2.0-526579)](configs/LICENSE)

**[Start here](docs/quickstart.md) · [7 control points](#control-points) · [10 risks](risks/) · [Configs](configs/) · [Coverage gaps](gaps.md) · [Русский](README.ru.md)**

Building an agent that can call tools, run code, or share memory? Use this guide to decide
**where a control belongs, what to deploy there, and how to check the result**.

Inside: **7 control points, 10 OWASP risk pages, 25 tool entries, 6 config directories,
and a coverage matrix spanning 20 attack scenarios and 46 defense methods**.
Counts describe this repository; each tool's maturity data has its own check date.

> **Languages:** the overview, quickstart, and contribution guide are available in English
> and Russian. Detailed control/risk pages and config walkthroughs are currently in Russian.
> English translations are welcome.

## Get your first result

Run the result-classifier checks with **Python 3.10+ and its standard library**:

```sh
git clone https://github.com/Andy9542/guide-asi.git
cd guide-asi
python3 configs/redteam/classify_test.py
```

Expected final line:

```text
classify_test: 58 случаев, расхождений 0
```

That means **58 cases, zero mismatches**: the harness distinguishes a passed evaluation,
a failed evaluation, and a run that could not produce a verdict. These are local checks
against fixtures in the promptfoo export format; they do not call a model or measure its security.
After cloning, this step needs no network, API key, Docker, or Node.js.

**[Continue the quickstart →](docs/quickstart.md)** for config validation, a local echo
evaluation, and the full selftest prerequisites.

<a name="как-пользоваться"></a>

## Choose your starting point

- **An agent can call tools or MCP servers:** start with the [tool gateway](points/02-tool-gateway.md)
  and the [OPA policy example](configs/opa/).
- **An agent installs packages or skills:** inspect the [supply chain](points/03-supply-chain.md)
  and the [Semgrep + OSV checks](configs/semgrep/).
- **Multiple agents exchange messages:** review [identity and the bus](points/05-identity.md)
  and the [Ed25519 signing example](configs/bus-signing/).
- **You are reviewing an architecture:** work through the [control points](#control-points),
  the [risk pages](risks/), and the [coverage gaps](gaps.md).
- **You are choosing tools:** use the [25-tool shortlist](data/tools.csv),
  [rejection reasons](data/rejected.csv), and [data definitions](data/README.md).

<a name="точки-внедрения"></a>

## Control points

Risks use [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
(ASI01–ASI10). A risk listed below is a relationship to investigate; the linked page explains
the extent and limits of coverage.

| Where to put the control | Examples and starting material | Related risks |
|---|---|---|
| [01 · Model gateway](points/01-llm-gateway.md) | [LiteLLM config](configs/litellm/) · credentials and model access | ASI03, ASI08 |
| [02 · Tool and MCP gateway](points/02-tool-gateway.md) | [OPA policies](configs/opa/) · agentgateway · Pipelock · content guardrails | ASI01, ASI02, ASI03, ASI09 |
| [03 · Agent supply chain](points/03-supply-chain.md) | [Semgrep + OSV-Scanner](configs/semgrep/) · agent-scan | ASI04, ASI05 |
| [04 · Execution sandbox](points/04-sandbox.md) | E2B · agent-sandbox · gVisor | ASI02, ASI03, ASI05 |
| [05 · Identity and agent bus](points/05-identity.md) | [Message signing](configs/bus-signing/) · Agent Governance Toolkit · SpiceDB | ASI03, ASI07, ASI10 |
| [06 · Memory and RAG](points/06-memory.md) | Memory provenance · OWASP Agent Memory Guard candidate · [open gap](gaps.md) | ASI06 |
| [07 · Telemetry and red teaming](points/07-observability.md) | [Decision spans](configs/otel/) · [promptfoo harness](configs/redteam/) · evaluation tools | ASI08, ASI10 |

Telemetry and red teaming provide **measurement and detection**. They help establish
whether a control worked; they do not themselves stop an attack.

<a name="метки-доказательности"></a>

## Know what the evidence supports

The detailed pages distinguish three evidence labels:

- **`[стенд]` / bench:** observed in the authors' test environment, with the configuration
  and measured behavior documented. The scope of that experiment matters.
- **`[дока]` / docs:** supported by the tool's documentation; not verified in this repository.
- **`[пробел]` / gap:** a suitable mature solution has not been established by this guide.

The config directories document expected results and limitations. Four have executable
selftests: **OPA, Semgrep/OSV, message signing, and red teaming**. The full suite runs
in [GitHub Actions](https://github.com/Andy9542/guide-asi/actions/workflows/selftest.yml).
The LiteLLM and OpenTelemetry integration checks also require a live environment;
a green CI badge does not establish production readiness or complete risk coverage.

<a name="что-ещё-внутри"></a>

## Reuse the research

- **[tools.csv](data/tools.csv):** 25 tools with repository, control point, evidence label,
  license, maturity signals, and check date.
- **[matrix.csv](data/matrix.csv):** 181 recorded scenario–method relationships across
  20 attack scenarios and 46 defense methods, with coverage ratings.
- **[rejected.csv](data/rejected.csv):** 8 candidates and the recorded reasons they were excluded.
- **[tools_raw.csv](data/tools_raw.csv):** the original 118-candidate catalog for further investigation.

Read the [field definitions](data/README.md) before comparing entries. Counts and ratings
describe the recorded assessment; they are not universal protection scores.

<a name="как-отбирались-инструменты"></a>

### How tools were selected

The shortlist was checked on **2026-09-09** against three criteria: an identifiable license
and its obligations, recent project activity, and evidence of adoption. OSV-Scanner,
gVisor, and OWASP Agent Memory Guard were considered alongside the original catalog to
describe the relevant control points; the pages retain each tool's evidence and maturity limits.
Per-entry dates live in the data. Corrections with primary sources are welcome.

<a name="границы-гайда"></a>

## Scope

This guide focuses on the **agent layer**: the boundary where model-generated text becomes
a tool call, code execution, a memory write, or a message to another agent. Apply it alongside
network, host, identity, and application hardening.

The configs are educational reference examples. Review their prerequisites, placeholders,
trust assumptions, and deployment limits before adapting them. A compromised agent can
still sign a harmful message with its own key; a policy needs an enforcement point; a
successful evaluation covers only the tested scenarios.

<a name="дополнить"></a>

## Help improve the guide

Useful first contributions: reproduce one example, correct a dated tool entry, translate
one page, or bring evidence for a [coverage gap](gaps.md).

**[Suggest a tool or correction](https://github.com/Andy9542/guide-asi/issues/new/choose)** ·
**[Contribution guide](CONTRIBUTING.md)**

If this guide helps you design or review an agent system, **give it a star** so you can
find it again, and share the specific control or example your team used.

<a name="лицензии"></a>

## Authors and licenses

Created by **Andrei Yakovlev and Anastasia Istomina** (Андрей Яковлев и Анастасия Истомина).

Text and data: **[CC BY-SA 4.0](LICENSE)**. Code in `configs/` and `build/`:
**[Apache-2.0](configs/LICENSE)**. Original visual assets: **CC BY-SA 4.0**.
OWASP risk descriptions are adapted with attribution; this is an independent guide.
See [NOTICE.md](NOTICE.md) for attribution and reuse terms.
