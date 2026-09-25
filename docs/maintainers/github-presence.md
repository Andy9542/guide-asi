# Repository presentation

[Overview](../../README.md) · [Visual assets](../../assets/brand/README.md)

These are the intended GitHub presentation settings. Committing this file does not apply
repository settings. The owner can apply them through the repository's About and Settings UI.

## About description

```text
Practical AI agent security: OWASP risks mapped to open-source controls, runnable configs, evidence, and coverage gaps. EN/RU.
```

## Topics

```text
ai-security
agent-security
ai-agents
agentic-ai
llm-security
owasp
prompt-injection
model-context-protocol
mcp
security-hardening
red-teaming
supply-chain-security
open-policy-agent
```

These describe the repository's content. Keep them aligned with the actual scope when
the guide changes. Leave the website field empty until there is a maintained project site.

## Social preview

Upload [social-preview.png](../../assets/brand/social-preview.png) in repository Settings →
General → Social preview. It is a 1280 × 640 PNG with an opaque background, sized for
[GitHub's documented requirements](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).
The SVG source is adjacent to it. The README uses a separate, shallower banner.

## A focused introduction to share

Share after the relevant README changes are on the default branch. Prefer a concrete
example and a relevant engineering community; adapt the wording to what you actually ran.

### English

We published Agent Defense Guide: 7 places to put controls around an AI agent, mapped
to OWASP's 10 agentic risks. It includes 6 config directories, a 25-tool shortlist,
and explicit evidence labels and coverage gaps. You can start by checking the evaluation
harness with one Python command, without calling a model. The overview and quickstart
are in English and Russian; detailed walkthroughs are currently in Russian.

https://github.com/Andy9542/guide-asi

### Русский

Выложили гайд по защите ИИ-агентов: 7 точек внедрения контролей, связанных с 10 рисками
OWASP. Внутри — 6 каталогов конфигов, 25 инструментов, метки доказательности и явные
пробелы покрытия. Начать можно с проверки обвязки одной командой Python, без вызова
модели. Обзор и быстрый старт доступны на русском и английском, подробные инструкции — на русском.

https://github.com/Andy9542/guide-asi

## Keep the entry point accurate

When the underlying data or examples change, update both overview languages, the
quickstart's expected output, and any affected visual counts. Use the existing selftest
status badge; avoid fixed “passing” badges or unverified adoption claims.
