#!/usr/bin/env python3
"""The Open Math OS reviewer (Mei fork) is the claude CLI against the Open Math OS gateway.

It carries only the Open Math OS key (never an Anthropic key or a Claude login), takes its exact
model from the caller, is labelled by the model the gateway reports, and leaves every other
reviewer unchanged.

Exit 0 = all assertions hold; 1 = a mismatch.
"""

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))
import casefile  # noqa: E402
import openmathos  # noqa: E402
import pricing  # noqa: E402
import render  # noqa: E402
import reviewers  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("FAIL:", msg)


# A clean environment bound to the gateway, in both auth modes.
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
        check("OPENAI_API_KEY" not in env and "CODEX_HOME" not in env, "no other provider's credential")
        check(openmathos.is_gateway(env), "gateway detection")
    finally:
        reviewers.cleanup_rev_home(home)

env, home = reviewers.reviewer_env("claude", keys)
check("ANTHROPIC_BASE_URL" not in env and env.get("ANTHROPIC_API_KEY") == keys["anthropic"],
      "claude reviewer keeps Anthropic")
check(not openmathos.is_gateway(env), "claude is not a gateway run")
reviewers.cleanup_rev_home(home)

# The served model comes from the gateway's own responses; unsafe or ambiguous text is ignored.
event = lambda model: json.dumps({"type": "assistant", "message": {"model": model}})  # noqa: E731
check(openmathos.served_model([event("moonshotai/kimi-k3.1-pro"), "not json",
                               json.dumps({"type": "result"})]) == "moonshotai/kimi-k3.1-pro",
      "served model from the stream")
check(openmathos.served_model([event("a`b")]) is None, "unsafe model text is ignored")
check(openmathos.served_model([event("a"), event("b")]) is None, "disagreeing events are ignored")

# The case file keeps it, and a later run without one clears it.
sm = {}
casefile.update_case_file(sm, "naming", {"provider": "openmathos", "model": "claude-openmathos-1",
                                         "served_model": "moonshotai/kimi-k3.1-pro"}, "abc")
check(sm["naming"].get("served_model") == "moonshotai/kimi-k3.1-pro", "case file keeps the served model")
check(sm["naming"].get("model") == "claude-openmathos-1", "the routing id stays the recorded model")
labelled = render.render_scoreboard(["naming"], sm, "abc", "changes requested", "")
check("`openmathos/moonshotai/kimi-k3.1-pro`" in labelled, "scoreboard shows the served model")
casefile.update_case_file(sm, "naming", {"provider": "claude", "model": "claude-opus-5-5"}, "abd")
check("served_model" not in sm["naming"], "a later run without one clears it")
check("`claude/claude-opus-5-5`" in render.render_scoreboard(["naming"], sm, "abd", "pending", ""),
      "other labels unchanged")

# Claude-style token accounting; never part of the default dispatch set.
check(pricing.usage_totals("openmathos", {"input_tokens": 3, "cache_read_input_tokens": 2})["input_tokens"] == 5,
      "claude-style usage accounting")
check(not any(m.startswith("claude-openmathos") for m in pricing.dispatch_models()),
      "no Open Math OS model in the default dispatch set")

# The engine refuses the reviewer without an explicit model, before any work.
r = subprocess.run([sys.executable, str(ROOT / "runner" / "review.py"), "--repo", "o/r", "--pr", "1",
                    "--providers", "openmathos", "--store", str(ROOT / ".no-store"),
                    "--rubrics-dir", str(ROOT / "rubrics"), "--tool-cwd", str(ROOT), "--diff-file", os.devnull],
                   capture_output=True, text=True, env={**os.environ, "OPENMATHOS_API_KEY": "k"})
check(r.returncode != 0 and "--openmathos-model is required" in (r.stderr + r.stdout),
      "a missing --openmathos-model is refused")

print("openmathos reviewer:", "OK" if not fails else f"{fails} failure(s)")
sys.exit(1 if fails else 0)
