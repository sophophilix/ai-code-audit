# First outside trial: setup, packaging and a guided report

> Status: Draft
> Created: 2026-11-20T12:07:07Z
> Last reviewed: 2026-11-20T12:07:07Z
> Next review: Not scheduled

## Session

- Date: 2026-11-20
- Who: tester, self-described as less technical
- Setup: Claude Code on Ubuntu under Windows (WSL), kit 0.26.x
- Format: two chats on the same day. The first was during setup. The second
  came after a self-run trial. The tester asked for a demo, because some
  points may come from using the kit in the wrong way.
- Their goal: find out where their own code is insecure, get the flaws in a
  structured form, and hand that to an AI to fix.

## Points raised

### F1. Ship the kit as a plugin

- What they said: package the kit as a plugin, so people can use it in the AI
  tool they already have. "If someone built the code with AI they might want
  to test it with AI." They mentioned a plugin format that works across most
  tools, and said Claude does not support it yet. They raised this twice,
  once during the trial and once after it.
- What the kit does today: install copies files into the workspace. `make ready`
  or `bin/kit install` copies agents, commands and skills into `.claude/`
  (`adapters/claude-code/README.md`). There is no plugin manifest.
  `adapters/generic/` covers other tools by hand.
- Status: `checked`
- Next step: ask which cross-tool format they meant. Compare a Claude Code
  plugin with the current install. A change to packaging needs a decision record.

### F2. Add a `learn` skill

- What they said: add a skill called `learn`. When you call it, the AI tells
  you how to use the kit.
- What the kit does today: no such skill or command. Guidance is in
  `README.md`, `docs/tutorials/` and `docs/how-to-run-an-audit.md`.
- Status: `checked`
- Next step: consider a `/audit-learn` command that walks a new user through
  the tutorial. It fits with F1 and F5.

### F3. One HTML report you can click through

- What they said: give the user a single HTML file, so they see every report
  in one place. Make it clickable, so it guides the user to where each
  problem is and explains what is happening there.
- What the kit does today: outputs are separate Markdown files in `.audit/`.
  The lead reviewer writes the report and briefing (`docs/how-to-run-an-audit.md`,
  section 10). Findings cite `file:line`, but nothing links them or builds HTML.
- Status: `checked`
- Next step: consider a `kit` command that joins the outputs into one offline
  HTML file with no external assets. Each finding links to its file and line,
  and shows the code excerpt. That keeps the kit local-first.

### F4. Diagrams had no images on Ubuntu

- What they said: the diagrams had no images. The run said it could not
  install the image viewer, but could still generate the diagrams. The tester
  thought the images are made later.
- What the kit does today: `kit diagrams` writes `.drawio` files. You export
  SVG or PNG by hand in draw.io (`docs/how-to-run-an-audit.md`, section 9).
  So a run with no draw.io gives no images. This matches what the tester saw.
- Status: `checked`, partly `user error`
- Next step: say in the tutorial that images need a manual export. Check
  whether drawio-skill can export headless on Linux. Find out which "image
  viewer" the run tried to install. Rule 3 forbids installing tools during a
  run, so that attempt may be a separate problem.

### F5. Unclear where to clone and where to run commands

- What they said: "I clone the repo then run your commands from within it?"
  They read `docs/how-to-run-an-audit.md` on `main` to find out.
- What the kit does today: on `main`, that guide starts with
  `cd ~/code/github.com/sophophilix/agent-audit-kit`
  (`docs/how-to-run-an-audit.md:32`). That is the old repository name and a
  maintainer's own path. The branch `docs/readme-and-tutorial` rewrites the
  README and adds a first tutorial, and no longer has that line. It is not
  merged yet.
- Status: `planned`
- Next step: merge the README and tutorial branch. Ask the tester to try the
  tutorial and say whether the kit clone and the target clone are clear.

### F6. Setup on Ubuntu under Windows

- What they said: they test on Ubuntu on Windows.
- What the kit does today: `README.md` says to use WSL2 on Windows. The
  Makefile and `bin/checkpoint` need a POSIX shell
  (`docs/architecture/ARCHITECTURE.md`, decision log). Nobody has recorded a
  full run on WSL2 before this trial.
- Status: `checked`
- Next step: record what worked and what failed on WSL2 after the demo. F4 is
  one result.

### F7. Positive: the evaluation

- What they said: the evaluation "seems cool". They described it as a script
  that plants bugs and counts how many the tool finds. As a data scientist, they
  liked that it checks the tool does what it claims to do.
- What the kit does today: `evals/README.md` describes the method.
- Status: `checked`
- Next step: none. Use their description when explaining the evaluation to
  new users.

### F8. Some security flaws are on purpose

- What they said: about half the security flaws in their code are there on
  purpose, to make their life easier.
- What the kit does today: findings have a severity and a recommendation
  (`core/skills/audit-findings/SKILL.md`). There is no way to mark a finding
  as an accepted risk with a reason, so these come back on every run.
  `kit scan` lists code suppression comments, which is a different thing
  (`src/audit_kit/code_facts.py`).
- Status: `checked`
- Next step: consider an accepted-risk list in `.audit/` that the human tech
  lead owns. Each entry names the finding, the reason and a review date. The
  report still shows these findings, in a separate section.

### F9. Hand the security findings to an AI to fix

- What they said: they want the kit to say the code is not secure, describe
  each flaw in a structured way, and give that to an AI to fix.
- What the kit does today: every finding has a fixed shape with severity,
  `file:line` evidence and a recommendation (`core/skills/audit-findings/SKILL.md`).
  `kit query . "<SQL>" --format json` reads them from the findings store
  (`src/audit_kit/cli.py`). There is no step-by-step guide for feeding that
  output to a coding AI. The kit itself stays read-only on the target
  (`AGENTS.md`, rule 1), so the fix happens outside the audit.
- Status: `checked`, partly `user error`
- Next step: write a how-to that exports the security findings as JSON and
  hands them to a separate AI session to fix. Consider a ready-made export,
  such as SARIF or a "fix brief" per finding.

### F10. Positive: the outputs document the code well

- What they said: they ran the kit on a work project. It "has done a good
  job" of writing technical documentation of the code. They think it helps a
  person, and possibly another AI, with future development. Overall it
  "seems really cool".
- What the kit does today: the discovery and architect outputs describe the
  code, its parts and its diagrams (`core/agents/`). The kit presents itself
  as an audit, not a documentation tool.
- Status: `checked`
- Next step: consider naming "documents an unfamiliar codebase" as a use the
  kit supports. Ask which output files they found most useful.

## Follow-up

- [ ] Give the tester a demo.
- [ ] Ask which cross-tool plugin format they meant (F1).
- [ ] Get the run log or message from the failed image viewer install (F4).
- [ ] Merge the README and tutorial branch, then ask the tester to retry (F5).
- [ ] Decide which of F1, F2, F3, F8 and F9 to build, and open issues for them.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-20T12:07:07Z | Drafted | Recorded from two chats on the same day. Names removed. |
