# Agent Defense Guide

*[Русская версия](README.md) — the guide itself is in Russian.*

One question, answered concretely: **which agentic-system risk is closed by which
production-ready open-source tool — and with which config.**

Not a market overview, not a link list. For every point in your infrastructure the guide
says what goes there, what that control catches, what it does **not** catch, and ships a
working config you can copy.

Risks are numbered after the [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
(ASI01–ASI10, published 2025-12-09).

## Scope

**Agent layer only.** Network segmentation, WAF, mail antivirus, fail2ban, ordinary image
CVE scanning are out — that is classic hardening, it is covered well elsewhere, and we are
not going to retell it worse. The line runs along one property: the control belongs here
if it exists because the step between text and action is now taken by an agent.

## Evidence labels

Every claim carries exactly one.

| Label | Meaning |
|---|---|
| `[стенд]` — *bench* | We ran it ourselves; the config is in this repo and we say what was measured |
| `[дока]` — *docs* | From the tool's documentation. We did not verify it |
| `[пробел]` — *gap* | We have not found a production-ready solution — see [gaps.md](gaps.md) |

## Points of control

| Point | Risks | Tools |
|---|---|---|
| [01 · Model call gateway](points/01-llm-gateway.md) | ASI03, ASI08 | LiteLLM `[стенд]` |
| [02 · Tool and MCP gateway](points/02-tool-gateway.md) | ASI01, ASI02, ASI03, ASI09 | OPA `[стенд]` · agentgateway, Pipelock, LlamaFirewall, NeMo Guardrails, Guardrails AI, Presidio `[дока]` |
| [03 · Agent supply chain](points/03-supply-chain.md) | ASI04, ASI05 | Semgrep, OSV-Scanner `[стенд]` · snyk/agent-scan `[дока]` |
| [04 · Execution sandbox](points/04-sandbox.md) | ASI02, ASI03, ASI05 | E2B, kubernetes-sigs/agent-sandbox, gVisor `[дока]` |
| [05 · Agent identity and bus](points/05-identity.md) | ASI03, ASI07, ASI10 | Ed25519 message signing `[стенд]` · Agent Governance Toolkit, SpiceDB `[дока]` |
| [06 · Memory and RAG](points/06-memory.md) | ASI06 | `[пробел]` · OWASP Agent Memory Guard as a candidate `[дока]` |
| [07 · Control telemetry and red-team](points/07-observability.md) | ASI08, ASI10 — detection only | Decision-span contract, promptfoo `[стенд]` · garak, PyRIT, AgentDojo, Inspect, OpenLLMetry `[дока]` |

Point 07 is a **measurement, not a defense**. It does not stop an attack; it answers whether
the controls in points 01–06 fired at all. Without it, "no incident" and "the defense worked"
look identical.

## How tools were selected

Out of a catalogue of 118 repositories, a tool had to clear three bars — checked 2026-09-09:

1. **A license we could establish** — SPDX id, OSI status, and a note when the license
   demands more than attribution.
2. **Activity within the last six months**, repository not archived.
3. **Evidence of adoption** — someone uses it, not just wrote it.

All of it is machine-readable in [`data/tools.csv`](data/tools.csv), with the check date.
Without the date, maturity numbers become a lie within a month.

**Who did not make it and why is in [`data/rejected.csv`](data/rejected.csv)** — arguably the
more useful half. It includes a tool that catalogues still list as production-ready while its
repository is already archived.

## Contributing

Gaps are the most valuable place to contribute — see [gaps.md](gaps.md) and
[CONTRIBUTING.md](CONTRIBUTING.md). Where we wrote "not found", we genuinely looked and did
not find it; we did not conclude it does not exist.

## Licensing

Text under CC BY-SA 4.0 (OWASP risk descriptions are adapted, and their material is
share-alike), configs under Apache-2.0. Details and attribution in [NOTICE.md](NOTICE.md).
