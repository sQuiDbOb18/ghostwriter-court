import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

def run_investigator():
    from agents.investigator import poll_forever
    poll_forever()

def run_similarity():
    from agents.similarity import poll_forever
    poll_forever()

def run_policy():
    from agents.policy import poll_forever
    poll_forever()

def run_negotiator():
    from agents.negotiator import poll_forever
    poll_forever()

def run_synthesizer():
    from agents.synthesizer import poll_forever
    poll_forever()

def run_brief_writer():
    from agents.brief_writer import poll_forever
    poll_forever()

def main():
    logger.info("Starting all 6 GhostWriter Court agents...")
    functions = [
        run_investigator,
        run_similarity,
        run_policy,
        run_negotiator,
        run_synthesizer,
        run_brief_writer,
    ]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fn) for fn in functions]
        for future in futures:
            try:
                future.result()
            except Exception as exc:
                logger.exception(f"Agent failed: {exc}")

if __name__ == "__main__":
    main()