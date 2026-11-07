"""Open Math OS reviewer (Mei fork): the claude CLI driven against the Open Math OS gateway.

`--reviewer openmathos --openmathos-model ID` runs the same `run_claude` runner as `claude`, with
ANTHROPIC_BASE_URL set to the gateway's Claude-compatible endpoint and OPENMATHOS_API_KEY as the
bearer token. The model has no default: the caller passes the exact gateway id from its own
configuration, as the worker passes Kiro's model. The key follows the OpenRouter reviewers: it is
always a key, in both auth modes, read from the environment. Like them, the reviewer is
pay-per-token and joins only when named.

The gateway's routing ids are opaque, so run_claude also records the model the gateway reports in
its responses (`served_model`), and labels show that name. The routing id stays in the records.

Everything provider-specific lives here so that merging upstream touches few lines.
"""

import json
import re

PROVIDER = "openmathos"
BASE_URL = "https://os.openmathmodel.org/claude"
KEY_ENV = "OPENMATHOS_API_KEY"

# A reported model name is provider-supplied text that is rendered on the PR inside a code span,
# so accept only a plain model-id shape.
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")


def reviewer_env(env, key):
    """Bind a clean reviewer environment to the gateway. Its throwaway HOME carries only this key:
    no Anthropic key and no Claude login."""
    env["ANTHROPIC_BASE_URL"] = BASE_URL
    env["ANTHROPIC_AUTH_TOKEN"] = key
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


def is_gateway(env):
    return (env or {}).get("ANTHROPIC_BASE_URL") == BASE_URL


def served_model(stream_lines):
    """The model the gateway says answered, from the stream-json assistant events; None unless
    every event names the same plain model id."""
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
        if _MODEL_NAME.fullmatch(model):
            return model
    return None
