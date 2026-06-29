---
title: "The Empty 200 Bug That Taught Me AI Coders Need Operating Rules"
subtitle: "A production scraper failed until I stopped treating Claude Code like a prompt box and started giving it tests, Docker gates, retry rules, and adversarial review."
tags:
  - claude code
  - ai engineering
  - software engineering
  - web scraping
  - prompt engineering
publication_target: "AI Advances or Better Programming"
source_repo: "https://github.com/GatoProgramador-01/claude-code-master-prompt"
status: "publish-ready draft"
---

The portal returned HTTP 200.

Every time.

But the AJAX body was empty.

No 429. No error code. No obvious failure. Just a successful request with nothing inside it.

That was the moment my AI-generated scraper stopped being impressive and started being expensive. Claude Code had written plausible code, but it did not understand the operational rule behind the failure: an HTTP 200 with an empty AJAX body can be a soft-block.

That failure became one of the rules inside my Claude Code control plane.

## The HTTP 200 That Lied

I was building a scraper for Peruvian judiciary portals. The stack was intentionally boring: TypeScript, axios, cheerio, HTTP requests, no browser automation.

The hard part was not parsing HTML. The hard part was surviving legacy portal behavior: JSF ViewState, AJAX responses, session state, worker concurrency, checkpointing, and retries.

My first AI-assisted attempt looked productive. It generated files, wired requests, parsed selectors, and started moving through pages.

Then the portal started returning HTTP 200 with empty bodies.

A naive retry loop treats that as success. A slightly better retry loop treats it as a transient parse failure. Neither understands that three consecutive empty AJAX responses can mean the portal is softly blocking the workflow or that worker concurrency has broken session state.

The scraper needed a rule:

```python
EMPTY_PAGE_THRESHOLD = 3
empty_count = 0

for page in pages:
    response = fetch_ajax_page(page)

    if response.status_code == 200 and not response.text.strip():
        empty_count += 1
        if empty_count >= EMPTY_PAGE_THRESHOLD:
            checkpoint_progress()
            retry_with_fewer_workers()
            break
        continue

    empty_count = 0
    process_page(response)
```

That rule did not come from a better prompt. It came from a production failure.

This is the core lesson behind [`claude-code-master-prompt`](https://github.com/GatoProgramador-01/claude-code-master-prompt): AI coding assistants become useful when you stop treating them like autocomplete and start wrapping them in operating rules.

## A Prompt Is Not a Control Plane

Most developers try to fix AI coding failures by writing a longer prompt.

I did that too.

My original `CLAUDE.md` kept growing. Every time Claude Code made a mistake, I added another instruction. Run tests. Prefer Docker. Use TDD. Check branches before editing GitHub Actions. Normalize Unicode in LLM JSON. Do not use deprecated LangChain patterns. Avoid `npm ci` when the project lockfile was generated in a way that breaks Linux CI.

The file eventually became the problem.

A React component fix paid the token cost of Terraform rules. A simple Python test update carried web scraping instructions. The prompt had become a junk drawer of scars.

The better design was modular:

- Keep core behavior in `CLAUDE.md`.
- Move domain knowledge into `.claude/rules/`.
- Load rules only when the task touches matching files.
- Use specialist agents for validation, scraping, adversarial review, and integration.
- Let hooks enforce behavior that prose instructions cannot reliably enforce.

That is why I call it a control plane.

It manages how Claude Code works, not just what Claude Code writes.

## The Rules That Actually Matter

The useful rules are not motivational. They are operational.

Here are the ones I would steal first from the repo:

| Rule | Failure It Prevents | Why It Matters |
|------|---------------------|----------------|
| TDD before implementation | Code that looks plausible but has no failing test proving the bug | Forces the model to define success before it writes |
| Docker-first validation | Native environment passes but the container fails at startup | Catches missing dependencies and deploy-time drift |
| Branch verification | GitHub Actions workflow targets `main` when the repo uses `master` | Prevents silent CI failures |
| Unicode normalization | LLM JSON parses in tests but fails on curly quotes in production | Makes structured output resilient |
| Lazy-loaded rules | Every session pays for every domain rule | Keeps context focused and cheaper |
| Adversarial review | The same agent that wrote the design reviews its own assumptions | Finds blind spots before code lands |
| Build-log compression | Claude reads thousands of irrelevant CI lines | Preserves context for the actual error |
| Soft-block detection | Scrapers retry successful-but-empty responses forever | Converts a silent failure into recoverable control flow |

None of these rules are glamorous.

That is the point.

Senior engineering is often the boring discipline that prevents expensive surprises.

## Why Generic AI Coding Assistants Stay Junior

A junior engineer writes the happy path.

A senior engineer asks what happens when the API returns success with invalid content, when the event loop closes between tests, when the Docker image lacks a dependency, when the lockfile behaves differently in CI, or when a tool call returns JSON with smart quotes.

Claude Code can write useful code quickly. But without project-specific constraints, it does not know which failures your team has already paid for.

That knowledge lives in your repo, your tests, your hooks, your CI, and your postmortems.

`claude-code-master-prompt` exists to move that knowledge into the assistant's operating environment.

The repo's README describes it as a production-grade Claude Code system prompt: modular, lazy-loaded, token-efficient, and built to enforce parallel agents, TDD, Docker-first development, LLMOps standards, and web scraping expertise.

That description matters because it is specific. It is not "make Claude better." It is "make Claude obey the engineering constraints that already keep production systems alive."

## The Multi-Agent Pattern

The repo defines a multi-agent working style:

- Architect: decomposes the problem.
- Adversarial: attacks the design before implementation.
- Analyst: reads logs, tests, and code paths.
- Drafter: writes tests and implementation.
- Integrator: wires the pieces together.
- Validate: runs the final gate.

The key is not the agent names. The key is separation of responsibility.

If the same context designs, implements, reviews, and validates, it becomes too easy for the model to agree with itself.

For production work, I want disagreement. I want one agent to say "this design ignores the retry path." I want another to say "the test mocks the wrong thing." I want validation to run after the implementation, not after the explanation.

That is how human teams catch mistakes.

The control plane makes Claude Code imitate that discipline.

## The Scraper Case Study

The best proof for this approach is not an abstract benchmark. It is a project that was painful enough to teach rules.

In the `pj-peru-scraper` work, the requirements were clear:

- Use HTTP-only scraping where possible.
- Avoid browser automation unless absolutely necessary.
- Handle JSF ViewState and AJAX behavior.
- Download PDFs reliably.
- Keep progress resumable.
- Detect soft-blocks.
- Retry with fewer workers when concurrency causes bad portal behavior.
- Keep output structured enough to audit.

The important part is not that AI helped write code.

The important part is that AI needed guardrails to avoid repeating expensive mistakes.

Once the soft-block rule existed, it became reusable. Once the Docker rule existed, it became reusable. Once the Unicode JSON rule existed, it became reusable.

That is the compounding value of a control plane: every failure becomes future leverage.

## How This Connects to medium-agent-factory

The same idea now drives `medium-agent-factory`.

A content pipeline should not simply ask a model to "write a good Medium post." That produces fluent mush.

It needs operating rules too:

- Research before writing.
- Extract evidence from real repositories.
- Run local commands when possible.
- Separate structural checks from LLM scoring.
- Use fact-checking before publication.
- Track revisions and quality history.
- Use LangSmith traces to inspect behavior.
- Evaluate whether a post can actually earn, not just whether it reads well.

That is why the next version of `medium-agent-factory` needs agents like `RepoAnalyzer`, `RunbookExecutor`, `EvidenceWeaver`, `GuidePlanner`, and `MediumMoneyEvaluator`.

The money is not in generic AI posts.

The money is in first-hand technical stories with proof.

## What You Can Steal Today

Start small.

Do not write a 1,300-line master prompt.

Instead, write down the last five failures your AI coding assistant caused or failed to prevent.

Turn each one into a rule:

1. What condition should the assistant detect?
2. What should it do before writing code?
3. What command must pass before the task is done?
4. What files trigger this rule?
5. Which specialist should review it?

Then move that rule into a place Claude Code will actually load at the right time.

For example:

```markdown
---
paths:
  - "**/scraper/**"
  - "**/crawler/**"
  - "**/download/**"
---

# Web Scraping Rule

HTTP 200 with an empty response body is not automatically success.

If three consecutive AJAX pages are empty:
- checkpoint progress
- reduce worker concurrency
- retry from checkpoint
- log the soft-block event
```

That is a small rule.

It is also the kind of rule that can save an entire project.

## The Real Bet

I do not think the future belongs to the longest prompt.

I think it belongs to the best control plane.

The teams that win with AI coding tools will not be the teams that trust the model most. They will be the teams that encode their engineering judgment into tests, hooks, validators, lazy-loaded rules, and adversarial review.

That is what [`claude-code-master-prompt`](https://github.com/GatoProgramador-01/claude-code-master-prompt) is trying to be.

Not a magic prompt.

An operating system for Claude Code.

And like any useful operating system, its job is simple: make the right thing easy, make the dangerous thing difficult, and make failure visible before production does.
