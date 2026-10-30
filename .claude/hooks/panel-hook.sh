#!/usr/bin/env bash
# Hook del panel (docs/harness/panel.md): reenvía el evento de Claude Code al registro de
# `factory hook` del repo principal, también desde un worktree. Llama al módulo directamente
# (mismo código que `factory hook`) para no depender de todo el CLI. Nunca bloquea: si no
# encuentra el entorno de factory del repo principal, termina en 0 sin hacer nada.
common="$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || exit 0
python="$(dirname "$common")/.venv/bin/python"
[ -x "$python" ] || exit 0
"$python" -m factory.panel.hooks >/dev/null || true
exit 0
