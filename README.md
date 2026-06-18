# GhostWriter Court

GhostWriter Court is a hackathon prototype for helping creators respond to possible copyright infringement. Give it an original URL and an allegedly infringing URL, and the system opens a Band room where a panel of specialist AI agents investigates the dispute, compares the works, reasons through policy, proposes negotiation options, summarizes the case, and drafts a cease-and-desist brief.

This is not legal advice. It is a workflow demo for triage, evidence organization, and first-draft dispute documents.

## What it does

- Starts a new copyright dispute from a simple HTTP API.
- Creates a Band chat room and adds six specialist agents.
- Routes the submitted URLs to the Investigator agent to begin the workflow.
- Lets each agent poll Band, process its next message, and reply with a structured analysis.
- Automatically chains the agents in order, so one Investigator mention can drive the full workflow.
- Produces practical outputs such as similarity findings, fair-use risk, settlement tiers, a case summary, and a formal demand letter draft.

## Agent lineup

| Agent | Role |
| --- | --- |
| Investigator | Reads the submitted URLs and creates an evidence summary. |
| Similarity | Scores overlap between the original and allegedly infringing work. |
| Policy | Applies DMCA and fair-use reasoning to the evidence. |
| Negotiator | Drafts three settlement paths, from attribution to takedown. |
| Synthesizer | Compresses the full discussion into a plain-English case recommendation. |
| BriefWriter | Drafts a formal cease-and-desist letter. |

## Architecture

```text
Client
  |
  | POST /new-dispute
  v
FastAPI main router
  |
  | create Band room, add agents, post initial message
  v
Band room
  |
  | agents poll for work every few seconds
  v
Investigator -> Similarity -> Policy -> Negotiator -> Synthesizer -> BriefWriter
  |
  v
Structured dispute analysis and legal brief draft
```

The agent chain is:

```text
Investigator -> Similarity -> Policy -> Negotiator -> Synthesizer -> BriefWriter -> Human review
```

Each agent only processes a message when it is their turn. After replying, it posts a new Band message that mentions the next agent by agent ID and includes both the original dispute URLs and its own findings summary. BriefWriter ends the chain by tagging `@officialpeters1` with `Your dispute packet is ready for review.`

Key files:

- `main_router.py` - FastAPI API for creating a new dispute and bootstrapping a Band room.
- `orchestrator.py` - local runner that starts all six agent pollers in parallel.
- `agents/` - individual agent pollers and prompts.
- `agents/chain.py` - shared chain order, handle checks, agent ID loading, and handoff message helpers.
- `outputs/` - placeholder directory for generated artifacts.
- `requirements.txt` / `pyproject.toml` - Python dependencies.
- `render.yaml` - Render deployment configuration.

## Tech stack

- Python
- FastAPI
- Band agent chat API
- AI/ML API chat completions
- HTTPX
- python-dotenv
- fpdf2

## Setup

Clone the repo and install dependencies:

```bash
pip install -r requirements.txt
```

Or, if you are using `uv`:

```bash
uv sync
```

Create a `.env` file with your API keys and agent IDs:

```bash
AIML_API_KEY=your_aiml_api_key
BAND_API_KEY=your_band_api_key
BAND_REST_URL=https://app.band.ai
BAND_API_BASE_URL=https://api.band.ai

INVESTIGATOR_AGENT_ID=your_investigator_agent_id
SIMILARITY_AGENT_ID=your_similarity_agent_id
POLICY_AGENT_ID=your_policy_agent_id
NEGOTIATOR_AGENT_ID=your_negotiator_agent_id
SYNTHESIZER_AGENT_ID=your_synthesizer_agent_id
BRIEFWRITER_AGENT_ID=your_brief_writer_agent_id

INVESTIGATOR_API_KEY=your_investigator_band_agent_key
SIMILARITY_API_KEY=your_similarity_band_agent_key
POLICY_API_KEY=your_policy_band_agent_key
NEGOTIATOR_API_KEY=your_negotiator_band_agent_key
SYNTHESIZER_API_KEY=your_synthesizer_band_agent_key
BRIEFWRITER_API_KEY=your_brief_writer_band_agent_key
```

The agents can also read their Band API keys from `agent_config.yaml` using this shape:

```yaml
investigator:
  agent_id: your_investigator_agent_id
  api_key: your_key
similarity:
  agent_id: your_similarity_agent_id
  api_key: your_key
policy:
  agent_id: your_policy_agent_id
  api_key: your_key
negotiator:
  agent_id: your_negotiator_agent_id
  api_key: your_key
synthesizer:
  agent_id: your_synthesizer_agent_id
  api_key: your_key
brief_writer:
  agent_id: your_brief_writer_agent_id
  api_key: your_key
```

## Run locally

Start the API router:

```bash
uvicorn main_router:app --reload
```

In another terminal, start all six agents:

```bash
python orchestrator.py
```

Submit a new dispute:

```bash
curl -X POST http://127.0.0.1:8000/new-dispute \
  -H "Content-Type: application/json" \
  -d '{
    "original_url": "https://example.com/original-work",
    "infringing_url": "https://example.com/suspected-copy"
  }'
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## API

### `POST /new-dispute`

Creates a new Band room, adds the configured agents, and posts the initial dispute prompt.

Request body:

```json
{
  "original_url": "https://example.com/original-work",
  "infringing_url": "https://example.com/suspected-copy"
}
```

Response:

```json
{
  "ok": true,
  "room_id": "band-room-id",
  "agents_added": ["agent-id-1", "agent-id-2"],
  "first_message": {}
}
```

### `GET /health`

Returns:

```json
{
  "status": "ok"
}
```

## Hackathon demo flow

1. Start the FastAPI router.
2. Start the orchestrator so all six agents are polling.
3. Submit an original URL and suspected copy URL.
4. Open the Band room returned by `/new-dispute`.
5. Send or verify the first message mentions `@officialpeters1/investigator`.
6. Watch Investigator hand off to Similarity, then Policy, Negotiator, Synthesizer, and BriefWriter.
7. Review the final BriefWriter message when it tags `@officialpeters1`.

You can also start the chain manually in an existing Band room by sending one message like:

```text
@officialpeters1/investigator New dispute submitted.
Original URL: https://example.com/original-work
Infringing URL: https://example.com/suspected-copy

Please investigate both URLs and start the workflow.
```

## Why it matters

Independent creators often do not know whether a copied work is worth escalating, how to talk about fair use, or how to write a professional first response. GhostWriter Court turns that stressful blank page into a guided multi-agent workflow: gather facts, assess similarity, evaluate legal risk, choose a strategy, and draft the next message.

## Future work

- Fetch and archive page snapshots as evidence.
- Generate downloadable PDF briefs in `outputs/`.
- Add a creator-facing web form for submitting disputes.
- Add human review checkpoints before sending any legal language.
- Store dispute history and final outcomes.
