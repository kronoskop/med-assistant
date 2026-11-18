#!/usr/bin/env python3
"""Claude Code PreToolUse(Bash) verification gate -- OBSERVE-only.

Registered in .claude/settings.json (project) for PreToolUse with matcher
"Bash". Standard library only; no network access; Python 3.9+.

Modes (environment variable CLAUDE_VERIFY_MODE):
  off      do nothing
  observe  (default) before a `git commit`, emit a non-blocking reminder
  enforce  NOT IMPLEMENTED -- behaves exactly like observe and says so

Limitation (deliberate): the hook API gives a PreToolUse hook the pending
command only. The documented Bash tool_response carries no exit status, so
this hook cannot reliably correlate "tests were run and passed" with the
current working tree. It therefore never records or trusts evidence, never
blocks, and never treats test commands mentioned in prose or in the same
command line as proof of anything. A blocking ENFORCE mode would be
misleading, so it is not provided.

Output contract: exit 0 always. When a commit is detected, print one JSON
object with `systemMessage` (shown to the user) and
`hookSpecificOutput.additionalContext` (shown to Claude). No
`permissionDecision` is ever emitted, so the normal permission flow is
unchanged. Any unexpected input or internal error -> silent exit 0.
"""

import json
import os
import re
import shlex
import sys

VERSION = "1.0"
MODES = ("off", "observe", "enforce")

# git global options that consume the following token as their argument
_GIT_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                      "--super-prefix", "--config-env"}
# command prefixes that run the next word as the real command
_WRAPPERS = {"env", "command", "builtin", "time", "nohup", "exec", "sudo",
             "nice", "caffeinate"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_SEPARATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")", "{", "}",
               "!", "then", "do", "else", "elif"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_FALLBACK = re.compile(r"(^|[\s;&|(`$])(\S*/)?git\b[^;&|\n]*?\bcommit\b(?!-)")
_MAX_DEPTH = 3


def get_mode(env=None):
    env = os.environ if env is None else env
    mode = str(env.get("CLAUDE_VERIFY_MODE", "") or "observe").strip().lower()
    return mode if mode in MODES else "observe"


def _tokenize(command):
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True,
                      punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def _segments(tokens):
    seg = []
    for tok in tokens:
        if tok in _SEPARATORS or set(tok) <= set(";&|()"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def _is_git_commit(seg, depth):
    i = 0
    while i < len(seg) and (_ASSIGN.match(seg[i]) or seg[i] in _WRAPPERS
                            or (i > 0 and seg[i - 1] in _WRAPPERS
                                and seg[i].startswith("-"))):
        i += 1
    if i >= len(seg):
        return False
    prog = os.path.basename(seg[i])
    rest = seg[i + 1:]
    if prog in _SHELLS:
        for j, tok in enumerate(rest):
            if tok.startswith("-") and "c" in tok[1:] and not tok.startswith("--"):
                return j + 1 < len(rest) and is_git_commit(rest[j + 1], depth + 1)
        return False
    if prog != "git":
        return False
    j = 0
    while j < len(rest):
        tok = rest[j]
        if tok in _GIT_OPTS_WITH_ARG:
            j += 2
        elif tok.startswith("-"):
            j += 1
        else:
            break
    if j >= len(rest) or rest[j] != "commit":
        return False
    args = rest[j + 1:]
    return not any(a in ("-h", "--help", "--dry-run") for a in args)


def is_git_commit(command, depth=0):
    """True if the shell command would run `git commit` (best effort)."""
    if not isinstance(command, str) or depth > _MAX_DEPTH:
        return False
    try:
        tokens = _tokenize(command)
    except ValueError:  # unbalanced quotes etc. -> conservative regex
        return bool(_FALLBACK.search(command))
    return any(_is_git_commit(seg, depth) for seg in _segments(tokens))


def build_output(mode, cwd):
    note = ""
    if mode == "enforce":
        note = (" CLAUDE_VERIFY_MODE=enforce was requested, but ENFORCE is not"
                " implemented (no reliable evidence tracking); not blocking.")
    user_msg = ("verification-gate [observe]: git commit detected. This gate does"
                " not track test evidence; confirm the relevant checks were"
                " actually run on the final diff." + note)
    claude_ctx = ("verification-gate (OBSERVE, non-blocking): a git commit is about"
                  " to run in %s. No verification evidence is tracked by this"
                  " hook. Before committing, make sure the relevant checks from"
                  " CLAUDE.md were executed on the final diff and"
                  " report their actual results (or NOT VERIFIED). Use /verify if"
                  " needed.%s" % (cwd or "the current directory", note))
    return {
        "systemMessage": user_msg,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": claude_ctx,
        },
    }


def run(stdin_text, env=None):
    """Return the JSON-serialisable output object, or None for no output."""
    mode = get_mode(env)
    if mode == "off":
        return None
    try:
        event = json.loads(stdin_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(event, dict):
        return None
    if event.get("hook_event_name", "PreToolUse") != "PreToolUse":
        return None
    if event.get("tool_name") != "Bash":
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if not is_git_commit(tool_input.get("command")):
        return None
    cwd = event.get("cwd")
    return build_output(mode, cwd if isinstance(cwd, str) else None)


def main():
    try:
        if get_mode() == "off":
            return 0
        out = run(sys.stdin.read())
        if out is not None:
            sys.stdout.write(json.dumps(out))
            sys.stdout.write("\n")
    except Exception:  # fail open: this gate must never break Bash
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
