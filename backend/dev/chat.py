"""Terminal chat client that talks to OpenAI through TAP.

    export TAP_KEY=<your TAP key>
    export OPENAI_KEY=<your OpenAI key>
    python3 backend/dev/chat.py

Standard library only, so it runs anywhere without installing anything.
Requests are streamed, which is what gives TAP a ttft_ms to record.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

TAP_URL = os.environ.get("TAP_URL", "https://tap-analytics-adrian.fly.dev")
TAP_KEY = os.environ.get("TAP_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_KEY", "")
MODEL = os.environ.get("MODEL", "gpt-5.5")


def send(messages: list[dict]) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    request = urllib.request.Request(
        f"{TAP_URL}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-TAP-Key": TAP_KEY,
            "Authorization": f"Bearer {OPENAI_KEY}",
        },
    )

    reply = ""
    with urllib.request.urlopen(request) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue

            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break

            chunk = json.loads(data)
            if not chunk.get("choices"):
                continue

            text = chunk["choices"][0].get("delta", {}).get("content")
            if text:
                print(text, end="", flush=True)
                reply += text

    print()
    return reply


def main() -> None:
    if not TAP_KEY or not OPENAI_KEY:
        sys.exit("set TAP_KEY and OPENAI_KEY first")

    print(f"{MODEL} via {TAP_URL} — ctrl-c to quit")
    messages: list[dict] = []

    while True:
        try:
            prompt = input("\nyou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not prompt:
            continue

        messages.append({"role": "user", "content": prompt})
        print("bot: ", end="", flush=True)

        try:
            reply = send(messages)
        except urllib.error.HTTPError as error:
            print(f"\n{error.code} {error.read().decode()}")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
