import os
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl


load_dotenv()

app = FastAPI(title="Ghostwriter Court Main Router")

BAND_API_BASE_URL = os.getenv("BAND_API_BASE_URL", "https://api.band.ai").rstrip("/")
BAND_CREATE_ROOM_PATH = os.getenv("BAND_CREATE_ROOM_PATH", "/v1/rooms")
BAND_ADD_ROOM_MEMBER_PATH = os.getenv(
    "BAND_ADD_ROOM_MEMBER_PATH", "/v1/rooms/{room_id}/members"
)
BAND_POST_MESSAGE_PATH = os.getenv("BAND_POST_MESSAGE_PATH", "/v1/messages")

INVESTIGATOR_TAG = os.getenv("INVESTIGATOR_TAG", "@Investigator")
DEFAULT_AGENT_IDS = {
    "investigator": os.getenv("BAND_INVESTIGATOR_AGENT_ID")
    or os.getenv("INVESTIGATOR_AGENT_ID"),
    "similarity": os.getenv("BAND_SIMILARITY_AGENT_ID")
    or os.getenv("SIMILARITY_AGENT_ID"),
    "policy": os.getenv("BAND_POLICY_AGENT_ID") or os.getenv("POLICY_AGENT_ID"),
    "negotiator": os.getenv("BAND_NEGOTIATOR_AGENT_ID")
    or os.getenv("NEGOTIATOR_AGENT_ID"),
    "synthesizer": os.getenv("BAND_SYNTHESIZER_AGENT_ID")
    or os.getenv("SYNTHESIZER_AGENT_ID"),
    "brief_writer": os.getenv("BAND_BRIEF_WRITER_AGENT_ID")
    or os.getenv("BRIEFWRITER_AGENT_ID"),
}


class NewDisputeRequest(BaseModel):
    original_url: HttpUrl
    infringing_url: HttpUrl


def band_token() -> str:
    token = os.getenv("BAND_API_KEY") or os.getenv("BAND_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="Missing BAND_API_KEY in .env")
    return token


def agent_ids() -> list[str]:
    comma_separated = os.getenv("BAND_AGENT_IDS")
    if comma_separated:
        ids = [agent_id.strip() for agent_id in comma_separated.split(",") if agent_id.strip()]
        if len(ids) != 6:
            raise HTTPException(
                status_code=500,
                detail="BAND_AGENT_IDS must contain exactly 6 comma-separated agent ids",
            )
        return ids

    missing = [name for name, agent_id in DEFAULT_AGENT_IDS.items() if not agent_id]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Missing Band agent ids for: {', '.join(missing)}",
        )
    return [agent_id for agent_id in DEFAULT_AGENT_IDS.values() if agent_id]


def extract_room_id(data: dict[str, Any]) -> str | None:
    candidates = [
        data.get("room_id"),
        data.get("roomId"),
        data.get("id"),
        data.get("chat_id"),
        data.get("chatId"),
    ]
    room = data.get("room")
    if isinstance(room, dict):
        candidates.extend([room.get("id"), room.get("room_id"), room.get("roomId")])
    chat = data.get("chat")
    if isinstance(chat, dict):
        candidates.extend([chat.get("id"), chat.get("chat_id"), chat.get("chatId")])
    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    return None


async def create_band_room(client: httpx.AsyncClient) -> str:
    payload = {
        "name": os.getenv("BAND_ROOM_NAME", "Ghostwriter Court Dispute"),
        "description": "Automated copyright dispute workflow",
    }
    response = await client.post(f"{BAND_API_BASE_URL}{BAND_CREATE_ROOM_PATH}", json=payload)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Band room creation failed: {response.text}",
        )

    room_id = extract_room_id(response.json())
    if not room_id:
        raise HTTPException(status_code=502, detail="Band room creation returned no room id")
    return room_id


async def add_agents_to_room(client: httpx.AsyncClient, room_id: str) -> list[str]:
    added: list[str] = []
    for agent_id in agent_ids():
        path = BAND_ADD_ROOM_MEMBER_PATH.format(room_id=room_id)
        payload = {"agent_id": agent_id, "member_id": agent_id}
        response = await client.post(f"{BAND_API_BASE_URL}{path}", json=payload)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to add agent {agent_id} to Band room: {response.text}",
            )
        added.append(agent_id)
    return added


async def send_initial_message(
    client: httpx.AsyncClient,
    room_id: str,
    original_url: str,
    infringing_url: str,
) -> dict[str, Any]:
    content = "\n".join(
        [
            f"{INVESTIGATOR_TAG} New dispute submitted.",
            f"Original URL: {original_url}",
            f"Infringing URL: {infringing_url}",
            "",
            "Please investigate both URLs and start the workflow.",
        ]
    )
    payload = {"room_id": room_id, "content": content}
    response = await client.post(f"{BAND_API_BASE_URL}{BAND_POST_MESSAGE_PATH}", json=payload)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Band initial message failed: {response.text}",
        )
    if response.content:
        return response.json()
    return {"ok": True}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/new-dispute")
async def new_dispute(request: NewDisputeRequest) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {band_token()}",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        room_id = await create_band_room(client)
        added_agents = await add_agents_to_room(client, room_id)
        first_message = await send_initial_message(
            client,
            room_id,
            str(request.original_url),
            str(request.infringing_url),
        )

    return {
        "ok": True,
        "room_id": room_id,
        "agents_added": added_agents,
        "first_message": first_message,
    }
