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

## 3. Communication Constraints
- **Zero Explanation Rule**: Upon completing a task, your response MUST be extremely brief. "Готово" (Done) is ideal. Do NOT list the files you changed. Do NOT explain your logic.
- **No Permissions**: If a file is missing or untracked during an operation (e.g., git commit), assume it is intentional and proceed. DO NOT stop to ask the user for permission.

## 4. Mandatory Workflow Rule (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ)
- **Strict Order of Action**: Before touching ANY code, you MUST follow this strict sequence:
  1. **Причина**: Describe the exact root cause of the problem.
  2. **Решение**: Describe the proposed technical solution.
  3. **План**: Provide a detailed implementation plan.
  4. **Согласование**: Wait for explicit user approval.
  5. **Смена кода**: ONLY after user approval, make code changes. NO EXCEPTIONS.

