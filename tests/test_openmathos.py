#!/usr/bin/env python3
"""The Open Math OS reviewer (Mei fork) is the claude CLI against the Open Math OS gateway.

It must carry only the Open Math OS key (never an Anthropic key or a Claude login), be recorded as
its own provider and model, and stay explicit-only.

Exit 0 = all assertions hold; 1 = a mismatch.
"""

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "runner"))
import openmathos  # noqa: E402
import pricing  # noqa: E402
import reviewers  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("FAIL:", msg)


keys = {"anthropic": "sk-ant-must-not-leak", "openai": "", "kiro": "", "openrouter": "",
        "openmathos": "omos-key"}
for subscription in (False, True):
    env, home = reviewers.reviewer_env("openmathos", keys, subscription=subscription)
    try:
        check(env.get("ANTHROPIC_BASE_URL") == openmathos.BASE_URL, "gateway base URL")
        check(env.get("ANTHROPIC_AUTH_TOKEN") == "omos-key", "Open Math OS key as bearer token")
        check("ANTHROPIC_API_KEY" not in env, "no Anthropic key reaches the gateway")
        check(not os.path.exists(os.path.join(home, ".claude", ".credentials.json")),
              "no Claude login is seeded")
        check(env.get("HOME") == home, "throwaway HOME is kept")
        for name in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                     "CLAUDE_CODE_SUBAGENT_MODEL"):
            check(env.get(name) == openmathos.MODEL, f"{name} pinned to the reviewer model")
        check("OPENAI_API_KEY" not in env and "CODEX_HOME" not in env, "no other provider's credential")
    finally:
        reviewers.cleanup_rev_home(home)

# Claude reviewers are unchanged.
env, home = reviewers.reviewer_env("claude", keys)
check("ANTHROPIC_BASE_URL" not in env and env.get("ANTHROPIC_API_KEY") == keys["anthropic"],
      "claude reviewer keeps Anthropic")
reviewers.cleanup_rev_home(home)

# Its own model id, never presented as a Claude model; never auto-drawn by the price guard.
check(openmathos.MODEL.startswith("claude-openmathos-"), "Open Math OS routing id")
check(openmathos.MODEL not in pricing.dispatch_models(), "not part of the default dispatch set")
check(pricing.usage_totals("openmathos", {"input_tokens": 3, "cache_read_input_tokens": 2})["input_tokens"] == 5,
      "claude-style usage accounting")

# Key resolution: explicit env, then file, else empty (the CLI then refuses the reviewer).
saved = {k: os.environ.pop(k, None) for k in ("OPENMATHOS_API_KEY", "OPENMATHOS_API_KEY_FILE")}
try:
    with tempfile.TemporaryDirectory() as tmp:
        keyfile = pathlib.Path(tmp) / "key"
        keyfile.write_text("from-file\n")
        os.environ["OPENMATHOS_API_KEY_FILE"] = str(keyfile)
        check(openmathos.api_key() == "from-file", "key file")
        os.environ["OPENMATHOS_API_KEY"] = "from-env"
        check(openmathos.api_key() == "from-env", "explicit key wins")
        del os.environ["OPENMATHOS_API_KEY"]
        os.environ["OPENMATHOS_API_KEY_FILE"] = str(pathlib.Path(tmp) / "absent")
        check(openmathos.api_key() == "", "missing key is empty")
finally:
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v

print("openmathos reviewer:", "OK" if not fails else f"{fails} failure(s)")
sys.exit(1 if fails else 0)
