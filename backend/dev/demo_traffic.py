"""Send realistic traffic through a TAP deployment to populate its dashboard.

    export TAP_KEY=<your TAP key>
    export OPENAI_KEY=<your OpenAI key>
    python3 backend/dev/demo_traffic.py

These are real provider calls that cost real money. A default run is a few
dozen requests on cheap models, well under a cent.

Paced below the default 60/minute rate limit, because a rate-limited request
is rejected before TAP logs it and would just be missing from the charts.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

TAP_URL = os.environ.get("TAP_URL", "https://tap-analytics-adrian.fly.dev")
TAP_KEY = os.environ.get("TAP_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_KEY", "")

REQUESTS = int(os.environ.get("REQUESTS", "45"))
PAUSE_SECONDS = float(os.environ.get("PAUSE_SECONDS", "5"))

MODELS = ["gpt-4o-mini", "gpt-4o-mini", "gpt-4o-mini", "gpt-5.5"]

PROMPTS = [
    "Summarise this support ticket: the customer cannot reset their password.",
    "Write a one-sentence release note for a caching feature.",
    "What is the difference between a proxy and a reverse proxy?",
    "Explain p95 latency to someone who has never seen a percentile.",
    "Draft a polite reply declining a meeting request.",
    "Name three reasons an API gateway might return 429.",
    "Turn this into a commit message: fixed the header forwarding bug.",
    "What does TTFT mean for a streaming language model response?",
    "Give me a two-line changelog entry for a rate limiter.",
    "Rewrite this more concisely: we were unable to process your request.",
]

# Sent verbatim more than once so TAP answers the repeats from its own cache.
REPEATED_PROMPT = "Explain what a cache hit is, in one sentence."

# A model that does not exist, so a few calls fail the way a typo would.
BAD_MODEL = "gpt-4o-mini-typo"


def call(model: str, prompt: str, stream: bool) -> int:
    payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if stream:
        payload["stream"] = True

    request = urllib.request.Request(
        f"{TAP_URL}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-TAP-Key": TAP_KEY,
            "Authorization": f"Bearer {OPENAI_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(request) as response:
            # Read to the end: TAP writes the row when the stream finishes, so
            # hanging up early loses it.
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        error.read()
        return error.code


def plan() -> list[tuple[str, str, bool]]:
    calls = []
    for index in range(REQUESTS):
        if index % 12 == 5:
            calls.append((BAD_MODEL, random.choice(PROMPTS), False))
        elif index % 5 == 0:
            calls.append((MODELS[0], REPEATED_PROMPT, False))
        else:
            calls.append(
                (random.choice(MODELS), random.choice(PROMPTS), index % 3 == 0)
            )
    return calls


def main() -> None:
    if not TAP_KEY or not OPENAI_KEY:
        sys.exit("set TAP_KEY and OPENAI_KEY first")

    calls = plan()
    minutes = len(calls) * PAUSE_SECONDS / 60
    print(f"{len(calls)} requests to {TAP_URL}, about {minutes:.0f} min")

    counts: dict[int, int] = {}
    for number, (model, prompt, stream) in enumerate(calls, start=1):
        status = call(model, prompt, stream)
        counts[status] = counts.get(status, 0) + 1
        label = "stream" if stream else "buffered"
        print(f"  {number}/{len(calls)}  {status}  {model} ({label})")
        if number < len(calls):
            time.sleep(PAUSE_SECONDS)

    print("\ndone:", ", ".join(f"{n}x {code}" for code, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
