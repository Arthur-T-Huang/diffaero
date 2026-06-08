"""Render the raw Claude Code session JSONL into a human-readable markdown
transcript.

Reads results/simulation_suite/CHAT_LOG.jsonl and writes CHAT_LOG.md alongside.

User prompts are shown verbatim. Assistant text is shown verbatim. Tool calls
are summarised in a single bullet line each (name + a short argument summary
+ a short result summary), so the transcript stays skimmable.
"""

import json
import re
import textwrap
from pathlib import Path

ROOT = Path("/home/arthur-huang/Desktop/diffaero/results/simulation_suite")
IN_PATH = ROOT / "CHAT_LOG.jsonl"
OUT_PATH = ROOT / "CHAT_LOG.md"

MAX_TOOL_ARG_CHARS = 200
MAX_TOOL_RESULT_CHARS = 300


def shorten(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def render_tool_args(name: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return shorten(str(inp), MAX_TOOL_ARG_CHARS)
    # pick the most informative arg per tool
    primary_key = {
        "Bash": "command",
        "Read": "file_path",
        "Write": "file_path",
        "Edit": "file_path",
        "Glob": "pattern",
        "Grep": "pattern",
        "TodoWrite": None,
        "AskUserQuestion": "questions",
        "WebFetch": "url",
        "Monitor": "description",
        "Agent": "description",
        "ToolSearch": "query",
        "Skill": "skill",
    }.get(name)
    if primary_key and primary_key in inp:
        return shorten(str(inp[primary_key]), MAX_TOOL_ARG_CHARS)
    if "description" in inp:
        return shorten(str(inp["description"]), MAX_TOOL_ARG_CHARS)
    # fallback: first non-empty string value
    for k, v in inp.items():
        if isinstance(v, str) and v.strip():
            return f"{k}={shorten(v, MAX_TOOL_ARG_CHARS - len(k) - 1)}"
    return shorten(json.dumps(inp)[:MAX_TOOL_ARG_CHARS], MAX_TOOL_ARG_CHARS)


def extract_text(content) -> str:
    """Pull plain text out of an assistant content list."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(c.get("text", ""))
    return "\n".join(p for p in parts if p)


def main():
    out_lines = []
    out_lines.append("# Claude Code session transcript")
    out_lines.append("")
    out_lines.append(f"_Source: `{IN_PATH.name}` (raw JSONL is the source of truth)._  ")
    out_lines.append("_Tool calls are collapsed to a single bullet each (name + key arg + result snippet)._")
    out_lines.append("")

    tool_use_id_to_call = {}  # toolu_xxx -> {"name": ..., "args_summary": ...}

    # first pass: collect tool_use mapping
    with IN_PATH.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            msg = d.get("message", {})
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tool_use_id_to_call[c.get("id")] = {
                        "name": c.get("name", "?"),
                        "args_summary": render_tool_args(c.get("name", "?"), c.get("input", {})),
                    }

    # second pass: walk in order, emit user/assistant turns
    with IN_PATH.open() as f:
        prev_role = None
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = d.get("message", {})
            role = msg.get("role")
            content = msg.get("content", [])

            if role == "user":
                # user content might be either plain text or a list of tool_result blocks
                if isinstance(content, str):
                    text = content.strip()
                    if text:
                        out_lines.append("## User")
                        out_lines.append("")
                        out_lines.append(text)
                        out_lines.append("")
                        prev_role = "user"
                elif isinstance(content, list):
                    # split into "tool results" and "plain text"
                    tool_results = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_result"]
                    text_blocks = [c for c in content if isinstance(c, dict) and c.get("type") == "text"]
                    plain_text = "\n".join(c.get("text", "") for c in text_blocks).strip()

                    # emit tool result snippets attached to the previous assistant turn
                    if tool_results:
                        for tr in tool_results:
                            call = tool_use_id_to_call.get(tr.get("tool_use_id"))
                            if not call:
                                continue
                            tc = tr.get("content", "")
                            if isinstance(tc, list):
                                tc = "\n".join(c.get("text", "") for c in tc if isinstance(c, dict))
                            snippet = shorten(tc, MAX_TOOL_RESULT_CHARS)
                            out_lines.append(f"    ↳ result: {snippet}")
                        out_lines.append("")

                    if plain_text:
                        out_lines.append("## User")
                        out_lines.append("")
                        out_lines.append(plain_text)
                        out_lines.append("")
                        prev_role = "user"

            elif role == "assistant":
                text = extract_text(content)
                tool_uses = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"] \
                            if isinstance(content, list) else []

                if text.strip() or tool_uses:
                    out_lines.append("## Assistant")
                    out_lines.append("")
                    if text.strip():
                        out_lines.append(text.strip())
                        out_lines.append("")
                    for tu in tool_uses:
                        name = tu.get("name", "?")
                        args = render_tool_args(name, tu.get("input", {}))
                        out_lines.append(f"- **{name}** — `{args}`")
                    if tool_uses:
                        out_lines.append("")
                    prev_role = "assistant"

    OUT_PATH.write_text("\n".join(out_lines))
    print(f"wrote {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
