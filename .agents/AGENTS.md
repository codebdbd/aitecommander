---
name: Agent Efficiency & Direct Execution Rules
description: Strict, algorithmically actionable guidelines to ensure the agent executes commands quickly without over-analysis.
---

# Agent Execution Rules: High-Efficiency Mode

## 1. Algorithmic Restrictions on Terminal Commands
- **Git Commit Workflow**: When requested to commit, you MUST execute exactly `git add -A` followed by `git commit -m "<message>"` and `git push`. Do NOT run `git status` or `git diff` first.
- **Banned Commands**: You MUST NEVER execute `pytest`, `ruff`, `flake8`, `mypy`, or any other linter/testing tool unless the user explicitly writes the word "проверь", "тест" or "lint".
- **Time Limits**: For any terminal command, set `WaitMsBeforeAsync` to no more than 5000 (5 seconds). If it takes longer, it must go to the background. DO NOT loop or poll endlessly.

## 2. Strict Positive Directives for Code Edits
- **Scope Containment**: Modify ONLY the exact lines of code required to fulfill the user's explicit request. 
- **Blindness to Context**: If you see an unrelated bug, an unused import, or poorly formatted code in the same file, you MUST LEAVE IT AS IS. 
- **No Refactoring**: You MUST NOT change variable names, extract functions, or reformat code unless specifically asked to refactor.
- **No Infrastructure Deletion**: NEVER delete, bypass, or replace existing calls to `app_config`, settings readers, signals, or configuration-driven logic with hardcoded values.

## 3. Communication Constraints
- **Zero Explanation Rule**: Upon completing a task, your response MUST be extremely brief. "Готово" (Done) is ideal. Do NOT list the files you changed. Do NOT explain your logic.
- **No Permissions**: If a file is missing or untracked during an operation (e.g., git commit), assume it is intentional and proceed. DO NOT stop to ask the user for permission.

## 4. Mandatory Workflow Rule (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ)
- **Strict Order of Action**: Before touching ANY code, you MUST follow this strict sequence:
  1. **Причина**: Describe the exact root cause of the problem.
  2. **Решение**: Describe the proposed technical solution.
  3. **План**: Provide a detailed implementation plan containing the EXACT unified diff (code blocks showing exact lines to be removed `-` and added `+`). Never propose vague text summaries without the exact diff.
  4. **Согласование**: Wait for explicit user approval.
  5. **Смена кода**: ONLY after user approval, make code changes. NO EXCEPTIONS.

## 5. Frozen Subsystems: Shutdown Protection (ЗАПРЕТ НА ИЗМЕНЕНИЯ ШАТДАУНА)
- **Status: FROZEN / READ-ONLY**: Механизм закрытия приложения (`app_shutdown_controller.py`, метод `closeEvent` в `main_window.py`, логика shutdown в `runtime.py`) полностью заморожен.
- **Strict Prohibition**: Запрещено вносить любые правки, менять порядок вызовов, рефакторить, переписывать таймауты или оптимизировать процесс завершения.
- **No Theoretical Audits**: При любых вопросах о закрытии запрещено выдумывать теоретические проблемы и предлагать рефакторинг.

## 6. Frozen Subsystems: Spheres Bar & Dock Architecture (ЗАПРЕТ НА ИЗМЕНЕНИЕ ПАНЕЛИ СФЕР)
- **Status: FROZEN / READ-ONLY**: Дизайн, геометрия и физика панели сфер (`spheres_bar`), кнопок сфер (`SphereToolButton`) и контроллера (`SpheresBarController`) полностью зафиксированы.
- **Strict Parameters**:
  1. **Ширина левой панели**: строго **320 px** (`splitter_sizes: [320, 704]`).
  2. **Отступы и сетка**: `spheres_bar_spacing: 8`, `spheres_bar_margin_left: 8`, `spheres_bar_margin_right: 8`.
  3. **Высота панели**: `spheres_bar_height: 96`, `spheres_layout_margins: [8, 2, 8, 4]`.
  4. **Размер кнопок**: строго **70×88 px** (`icon_w + 6, icon_h + 24`).
  5. **Масштабирование macOS Dock**: формула `size = 56.0 + 14.0 * s` (56 px в покое, 70 px на пике), базовая линия `bottom_y = rect.height() - 14`.
  6. **Индикатор активной сферы**: круглая точка диаметром **5.0 px** на `y = rect.height() - dot_d - 3.0` строго при `isChecked()`. Без фонов и рамок.
  7. **Сглаживание**: рендеринг через `QRectF` и `painter.drawPixmap(icon_rect_f, pix, ...)`, шаг LERP `0.18`.
- **Strict Prohibition**: Запрещено самовольно изменять размеры, отступы, базовую линию, формулу зума или возвращать фоновые подложки.


