# Release readiness gates — Aite Commander desktop

**Evidence rule:** PASS only when tested on the specified environment; no inferred passes. Record exact command/test/build, platform, date, result. A release is not `READY` with a BLOCKED/FAIL/NOT-RUN critical gate.

| Gate | Required evidence |
| --- | --- |
| G01 Repository baseline | Head, branch/worktree, clean/dirty status, Python/Qt/Windows versions, actual release target |
| G02 Automated tests | Full pytest and relevant contract/regression tests; output, counts, failures |
| G03 Code and translation | Ruff check and formatting check; `python -m i18n check`; generated assets verified |
| G04 Start and finish | Packaged app starts, closes, restarts; Windows COM/single instance/worker and DB shutdown verified |
| G05 Data safety | Create/read/update/delete, nested transactions, rollback, backup integrity, restore using disposable databases |
| G06 Upgrade compatibility | Existing user-data sample from previous public release upgrades with data intact; clean install also works |
| G07 Core UI regression | Navigation history, table/tree selection, right-click target, focus, copy/cut/paste, DnD, Undo/Redo |
| G08 UI and localization | Core workflows in available light/dark themes, font scaling, DPI/resolution and runtime locale switching |
| G09 File handling | Local files/folders/program/script launch, Quick Look, HTML bookmark import, .aitesec/.aitecat and backup packages, corrupt/untrusted input rejection |
| G10 Windows installer | Isolated install, first launch, restart, uninstall, shortcuts/file associations and packaged resource visibility |
| G11 Reliability and security | Unhandled exceptions, paths/permissions, zip traversal, logs free of secrets, dependency/security review |
| G12 Distribution | Version/name/license, checksum if available, working official download link, docs accuracy and no unapproved publication |

**Critical gates:** G02, G03, G04, G05, G06, G07, G09, G10 must be PASS for a distribution-ready declaration. If a required test environment (e.g. Windows 10 VM) is unavailable, mark environment-dependent portions `NOT-RUN` or `BLOCKED`; do not substitute theoretical assurance. G08/G11/G12 must be reviewed, and any confirmed release-blocking issue makes the verdict `BLOCKED`.

Prioritize actual failures and regressions, not theoretical code style and subjective polish. No new features unless necessary to eliminate a confirmed release blocker.
