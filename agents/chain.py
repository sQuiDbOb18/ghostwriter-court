import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

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


def should_process_agent(content: str, agent_name: str) -> bool:
    if not is_mentioned(content, AGENT_HANDLES[agent_name]):
        return False

    previous_agent = PREVIOUS_AGENT.get(agent_name)
    if not previous_agent:
        return True

    previous_marker = f"{AGENT_LABELS[previous_agent]} findings summary:"
    return previous_marker.lower() in content.lower()


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
            "mentions": [{"handle": HUMAN_HANDLE}],
        }
    }
    return client.post(
        f"{band_base_url}/api/v1/agent/chats/{chat_id}/messages",
        headers=headers,
        json=payload,
    )
