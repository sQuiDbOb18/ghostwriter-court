import os
import re
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    import httpx


AGENT_HANDLES = {
    "investigator": "@officialpeters1/investigator",
    "similarity": "@officialpeters1/similarity",
    "policy": "@officialpeters1/policy",
    "negotiator": "@officialpeters1/negotiator",
    "synthesizer": "@officialpeters1/synthesizer",
    "brief_writer": "@officialpeters1/briefwriter",
}

AGENT_MENTION_ALIASES = {
    "investigator": ("@officialpeters1/investigator", "@investigator"),
    "similarity": ("@officialpeters1/similarity", "@similarity"),
    "policy": ("@officialpeters1/policy", "@policy"),
    "negotiator": ("@officialpeters1/negotiator", "@negotiator"),
    "synthesizer": ("@officialpeters1/synthesizer", "@synthesizer"),
    "brief_writer": (
        "@officialpeters1/briefwriter",
        "@officialpeters1/brief_writer",
        "@briefwriter",
        "@brief_writer",
    ),
}

AGENT_LABELS = {
    "investigator": "Investigator",
    "similarity": "Similarity",
    "policy": "Policy",
    "negotiator": "Negotiator",
    "synthesizer": "Synthesizer",
    "brief_writer": "BriefWriter",
}

PREVIOUS_AGENT = {
    "similarity": "investigator",
    "policy": "similarity",
    "negotiator": "policy",
    "synthesizer": "negotiator",
    "brief_writer": "synthesizer",
}

AGENT_ID_ENV = {
    "investigator": "INVESTIGATOR_AGENT_ID",
    "similarity": "SIMILARITY_AGENT_ID",
    "policy": "POLICY_AGENT_ID",
    "negotiator": "NEGOTIATOR_AGENT_ID",
    "synthesizer": "SYNTHESIZER_AGENT_ID",
    "brief_writer": "BRIEFWRITER_AGENT_ID",
}

HUMAN_HANDLE = "@officialpeters1"
HUMAN_USER_ID = os.getenv("HUMAN_USER_ID", "92b42bb5-4256-40ab-ba83-5df566192d7d")
CHAIN_MARKER = "GhostWriter Chain v2"


def load_agent_id(name: str) -> str:
    env_name = AGENT_ID_ENV[name]
    if os.getenv(env_name):
        return os.environ[env_name]

    config_path = Path("agent_config.yaml")
    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    agent_config = config.get(name, {}) or {}
    agent_id = agent_config.get("agent_id") or agent_config.get("id")
    if not agent_id:
        raise RuntimeError(f"Missing {name} agent_id in agent_config.yaml")
    return str(agent_id)


def is_mentioned(content: str, handle: str) -> bool:
    return handle.lower() in content.lower()


def is_agent_mentioned(content: str, agent_name: str) -> bool:
    normalized = content.lower()
    return any(alias in normalized for alias in AGENT_MENTION_ALIASES[agent_name])


def message_search_text(message_or_content: dict[str, Any] | str) -> str:
    if isinstance(message_or_content, dict):
        content = str(message_or_content.get("content", ""))
        try:
            raw_message = json.dumps(message_or_content, default=str)
        except TypeError:
            raw_message = str(message_or_content)
        return f"{content}\n{raw_message}"
    return message_or_content


def is_agent_mentioned_in_message(message_or_content: dict[str, Any] | str, agent_name: str) -> bool:
    search_text = message_search_text(message_or_content).lower()
    agent_id = load_agent_id(agent_name).lower()
    return agent_id in search_text or any(
        alias in search_text for alias in AGENT_MENTION_ALIASES[agent_name]
    )


def should_process_agent(message_or_content: dict[str, Any] | str, agent_name: str) -> bool:
    search_text = message_search_text(message_or_content)
    if not is_agent_mentioned_in_message(message_or_content, agent_name):
        return False

    previous_agent = PREVIOUS_AGENT.get(agent_name)
    if not previous_agent:
        return True

    previous_marker = f"{AGENT_LABELS[previous_agent]} findings summary:"
    normalized = search_text.lower()
    return CHAIN_MARKER.lower() in normalized and previous_marker.lower() in normalized


def original_context(content: str) -> str:
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if "original url:" in stripped.lower() or "infringing url:" in stripped.lower():
            lines.append(stripped)

    if lines:
        return "\n".join(lines)

    urls = re.findall(r"https?://[^\s)>\]}\"']+", content)
    if not urls:
        return "Original dispute context: not provided."
    if len(urls) == 1:
        return f"Original URL: {urls[0]}"
    return f"Original URL: {urls[0]}\nInfringing URL: {urls[1]}"


def next_agent_content(
    *,
    current_agent: str,
    next_agent: str,
    incoming_content: str,
    findings: str,
) -> str:
    current_label = AGENT_LABELS[current_agent]
    next_handle = AGENT_HANDLES[next_agent]
    return "\n\n".join(
        [
            CHAIN_MARKER,
            f"{next_handle} Please continue this copyright dispute workflow.",
            "Original dispute context:",
            original_context(incoming_content),
            f"{current_label} findings summary:",
            findings,
        ]
    )


def human_ready_content(findings: str) -> str:
    return "\n\n".join(
        [
            f"{HUMAN_HANDLE} Your dispute packet is ready for review.",
            "BriefWriter final draft:",
            findings,
        ]
    )


def post_agent_handoff(
    *,
    client: "httpx.Client",
    band_base_url: str,
    api_key: str,
    headers: dict[str, str],
    chat_id: str,
    current_agent: str,
    next_agent: str,
    incoming_content: str,
    findings: str,
) -> "httpx.Response":
    next_agent_id = load_agent_id(next_agent)
    payload = {
        "message": {
            "content": next_agent_content(
                current_agent=current_agent,
                next_agent=next_agent,
                incoming_content=incoming_content,
                findings=findings,
            ),
            "mentions": [{"id": next_agent_id}],
        }
    }
    return client.post(
        f"{band_base_url}/api/v1/agent/chats/{chat_id}/messages",
        headers=headers,
        json=payload,
    )


def post_human_ready(
    *,
    client: "httpx.Client",
    band_base_url: str,
    headers: dict[str, str],
    chat_id: str,
    findings: str,
) -> "httpx.Response":
    payload = {
        "message": {
            "content": human_ready_content(findings),
            "mentions": [{"id": os.getenv("HUMAN_USER_ID", HUMAN_USER_ID)}],
        }
    }
    return client.post(
        f"{band_base_url}/api/v1/agent/chats/{chat_id}/messages",
        headers=headers,
        json=payload,
    )
