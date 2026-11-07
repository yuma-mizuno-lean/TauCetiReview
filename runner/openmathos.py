"""Open Math OS reviewer: the claude CLI driven against the Open Math OS gateway (Mei fork).

`--reviewer openmathos` runs the same `run_claude` runner as `claude`, with ANTHROPIC_BASE_URL set
to the Open Math OS Claude-compatible endpoint and the operator's Open Math OS key as the bearer
token. Like the OpenRouter reviewers it is pay-per-token and explicit-only (never auto-drawn), and
its credential is always a key, in both auth modes. It is recorded as its own provider with its
own model id, so a scoreboard never presents it as a Claude review.

Everything provider-specific lives here so that merging upstream touches few lines.

Run as a script (runner/ on sys.path), so imports are flat siblings, not package-relative.
"""

import json
import os
import pathlib
import re

PROVIDER = "openmathos"
# Kimi K3.1 Pro. The gateway's ids are opaque; list them with GET {BASE_URL}/v1/models.
MODEL = (os.environ.get("TAUCETI_OPENMATHOS_MODEL")
         or "claude-openmathos-136586835026765720304391437666977767985")
BASE_URL = (os.environ.get("OPENMATHOS_BASE_URL") or "https://os.openmathmodel.org/claude").rstrip("/")
DEFAULT_KEY_FILE = "~/.config/tauceti/openmathos.key"

# Claude Code picks these for its own side requests. Pin them all to the reviewer model so no
# request names a model the gateway does not serve.
_MODEL_VARIABLES = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)


def api_key():
    """OPENMATHOS_API_KEY wins; otherwise the key file (OPENMATHOS_API_KEY_FILE or the default)."""
    key = (os.environ.get("OPENMATHOS_API_KEY") or "").strip()
    if key:
        return key
    path = pathlib.Path(os.environ.get("OPENMATHOS_API_KEY_FILE") or DEFAULT_KEY_FILE).expanduser()
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def reviewer_env(env, key, model=MODEL):
    """Add the gateway binding to a clean reviewer environment. No Anthropic key or OAuth login is
    seeded: the throwaway HOME carries only this key, as for the OpenRouter reviewers."""
    env["ANTHROPIC_BASE_URL"] = BASE_URL
    env["ANTHROPIC_AUTH_TOKEN"] = key
    for name in _MODEL_VARIABLES:
        env[name] = model
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


# A model name the gateway reports is provider-supplied text that lands inside a backtick span on
# the PR, so accept only a plain model-id shape.
_SERVED_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")


def is_gateway(env):
    return (env or {}).get("ANTHROPIC_BASE_URL") == BASE_URL


def served_model(stream_lines):
    """The model the gateway says answered, from the stream-json assistant events.

    The routing id the gateway requires (MODEL) is opaque; the response names the real model (for
    example moonshotai/kimi-k3.1-pro). Returns it when every assistant event agrees, else None."""
    seen = set()
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "assistant":
            model = (event.get("message") or {}).get("model")
            if isinstance(model, str):
                seen.add(model)
    if len(seen) == 1:
        (model,) = seen
        if _SERVED_MODEL.fullmatch(model):
            return model
    return None


def judge_label(cf):
    """`provider/model` for display: the served model when the gateway reported one."""
    return f"{cf.get('provider')}/{cf.get('served_model') or cf.get('model')}"
