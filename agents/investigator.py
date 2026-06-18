import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv

from agents.chain import AGENT_HANDLES, post_agent_handoff, should_process_agent

load_dotenv()

BAND_BASE_URL = os.getenv("BAND_REST_URL", "https://app.band.ai")
AIML_BASE_URL = "https://api.aimlapi.com/v1"
POLL_SECONDS = 3
AGENT_NAME = "investigator"
NEXT_AGENT_NAME = "similarity"
OWN_HANDLE = AGENT_HANDLES[AGENT_NAME]

SYSTEM_PROMPT = "You are the Investigator agent in a copyright dispute workflow. When given URLs, describe what you would find there (title, creator, date, content type) and provide a structured findings summary. Always respond with your analysis."


def say(message: str) -> None:
    print(message, flush=True)


def load_investigator_api_key() -> str:
    if os.getenv("INVESTIGATOR_API_KEY"):
        return os.environ["INVESTIGATOR_API_KEY"]

    config_path = Path("agent_config.yaml")
    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    api_key = config.get("investigator", {}).get("api_key")
    if not api_key:
        raise RuntimeError("Missing investigator api_key in agent_config.yaml")
    return api_key


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def band_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }


def raise_with_body(response: httpx.Response) -> None:
    if getattr(response, "status_code", 0) >= 400:
        say(f"HTTP error {response.status_code} {response.request.method} {response.request.url}")
        say(f"Response body: {response.text}")
        response.raise_for_status()


def extract_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data", [])
        if isinstance(data, list):
            return data
    return []


def extract_object(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            return data
    return None


def get_chat_id(chat: dict[str, Any]) -> str | None:
    value = chat.get("id") or chat.get("chat_room_id")
    return str(value) if value else None


def get_message_id(message: dict[str, Any]) -> str | None:
    value = message.get("id") or message.get("message_id")
    return str(value) if value else None


def get_reply_mention(message: dict[str, Any]) -> dict[str, str]:
    sender_id = message.get("sender_id")
    if not sender_id:
        metadata = message.get("metadata")
        if isinstance(metadata, dict):
            sender = metadata.get("sender")
            if isinstance(sender, dict):
                sender_id = sender.get("id")

    if not sender_id:
        raise RuntimeError(f"Cannot reply: incoming message has no sender_id: {message}")

    mention = {"id": str(sender_id)}

    sender_handle = message.get("sender_handle") or message.get("handle")
    if sender_handle:
        mention["handle"] = str(sender_handle)

    sender_name = message.get("sender_name") or message.get("name")
    if sender_name:
        mention["name"] = str(sender_name)

    return mention


def ask_aiml(message_content: str, aiml_api_key: str) -> str:
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message_content},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {aiml_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{AIML_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        raise_with_body(response)
        data = response.json()

    return data["choices"][0]["message"]["content"].strip()


def process_message(
    *,
    client: httpx.Client,
    api_key: str,
    aiml_api_key: str,
    chat_id: str,
    message: dict[str, Any],
) -> None:
    message_id = get_message_id(message)
    content = str(message.get("content", "")).strip()
    if not message_id:
        say(f"Skipping message with no id: {message}")
        return
    if not content:
        say(f"Skipping empty message: {message_id}")
        return

    say(f"Found message: {message_id} {content[:300]}")

    if not should_process_agent(message, AGENT_NAME):
        say(f"Skipping message that is not ready for {OWN_HANDLE}: {message_id}")
        raise_with_body(
            client.post(
                f"{BAND_BASE_URL}/api/v1/agent/chats/{chat_id}/messages/{message_id}/processing",
                headers=band_headers(api_key),
            )
        )
        raise_with_body(
            client.post(
                f"{BAND_BASE_URL}/api/v1/agent/chats/{chat_id}/messages/{message_id}/processed",
                headers=band_headers(api_key),
            )
        )
        return

    raise_with_body(
        client.post(
            f"{BAND_BASE_URL}/api/v1/agent/chats/{chat_id}/messages/{message_id}/processing",
            headers=band_headers(api_key),
        )
    )

    llm_response = ask_aiml(content, aiml_api_key)
    say(f"Replying: {llm_response[:500]}")

    handoff_response = post_agent_handoff(
        client=client,
        band_base_url=BAND_BASE_URL,
        api_key=api_key,
        headers=band_headers(api_key),
        chat_id=chat_id,
        current_agent=AGENT_NAME,
        next_agent=NEXT_AGENT_NAME,
        incoming_content=content,
        findings=llm_response,
    )
    raise_with_body(handoff_response)

    processed_response = client.post(
        f"{BAND_BASE_URL}/api/v1/agent/chats/{chat_id}/messages/{message_id}/processed",
        headers=band_headers(api_key),
    )
    raise_with_body(processed_response)

    say("Done.")


def poll_forever() -> None:
    api_key = load_investigator_api_key()
    aiml_api_key = require_env("AIML_API_KEY")

    say("Investigator REST poller starting")
    say(f"Band base URL: {BAND_BASE_URL}")

    with httpx.Client(timeout=30) as client:
        while True:
            try:
                say("Polling...")
                chats_response = client.get(
                    f"{BAND_BASE_URL}/api/v1/agent/chats",
                    headers=band_headers(api_key),
                )
                raise_with_body(chats_response)

                for chat in extract_list(chats_response.json()):
                    chat_id = get_chat_id(chat)
                    if not chat_id:
                        continue

                    next_response = client.get(
                        f"{BAND_BASE_URL}/api/v1/agent/chats/{chat_id}/messages/next",
                        headers=band_headers(api_key),
                    )
                    if next_response.status_code == 204:
                        continue
                    raise_with_body(next_response)

                    message = extract_object(next_response.json())
                    if message:
                        process_message(
                            client=client,
                            api_key=api_key,
                            aiml_api_key=aiml_api_key,
                            chat_id=chat_id,
                            message=message,
                        )

            except Exception as exc:
                say(f"Error: {type(exc).__name__}: {exc}")

            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    poll_forever()
