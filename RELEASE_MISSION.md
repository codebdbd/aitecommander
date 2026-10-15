# Aite Commander — release stabilization mission

**Scope:** existing Windows desktop application in this repository, not the public marketing website. Product features are frozen; prepare for reliable external distribution.

## Mission owner approval already granted

Within a dedicated isolated Antigravity Git worktree, the agent may independently:

- inspect all project source and configuration, Git history and existing tests;
- create and modify non-destructive code, tests, CI configurations and documentation;
- run targeted and full tests, lint/type/i18n checks and read-only diagnostics;
- create test fixtures, disposable SQLite DBs, profiles and isolated virtual environments;
- install **declared project development dependencies** in the isolated environment when required;
- build PyInstaller/Inno Setup installers where tools are installed, writing artifacts only to isolated build locations;
- attempt safe fixes repeatedly and keep progress reports up to date;
- create local, clearly named commits on a dedicated branch for verified changes (no push).

These permissions exist only **within the isolated worktree/test environment**. They do not allow access to personal browser profiles, user databases or production operating-system settings. Outside-workspace access stays disabled.

## Seek explicit owner approval only for

- modifying real user data or production Windows settings; installation/uninstallation on owner's everyday computer;
- irreversibly destructive or breaking database migrations;
- introducing a substantial new dependency, paid service, account access or broad external network access;
- substantive product feature or UX decisions changing established user behavior;
- pushing, tagging, uploading, deploying, publishing or replacing a release; code signing; access to secrets.

If a blocker requires approval, explain it once with exact consequences and meanwhile proceed with other independent work.

## Quality target

No confirmed P0/P1 bugs, no failing applicable test/lint/i18n checks, no regression in critical UI/database flows, demonstrably working packaged app and installer, compatibility with previous user data and an evidence-backed list of any remaining unknowns.

The mission is NOT completed merely because unit tests are green or the application starts from source. See `RELEASE_GATES.md`.

## Execution protocol

Activate `.agents/skills/release-hardening/SKILL.md`. Execute the loop autonomously until the acceptance target is achieved or a real blocker occurs. Never stop after the first analysis report to await permission for ordinary fixes. Keep an actionable backlog in `release-readiness/ISSUES.md` and durable progress in `release-readiness/STATUS.md`. Report owner-facing status in Russian.

Keep `main` untouched; no remote mutations without permission. For multi-module changes write a brief plan into `release-readiness/STATUS.md` **and proceed** if the operation is reversible and within this approval envelope.
