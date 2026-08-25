import json
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    UserTurnMessageAddedMessage,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.realtime.events import (
    AudioConfiguration,
    AudioInput,
    AudioOutput,
    InputAudioTranscription,
    SemanticTurnDetection,
    SessionProperties,
)
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

COMPANY_NAME = "Ironwood Custom Classics"
VOICE = "marin"

DATA_DIR = Path(__file__).parent / "data"
LEADS_PATH = Path(__file__).parent / "leads.json"


def build_system_instruction(car_listing: str, company: str) -> str:
    return f"""You are Ava, the AI phone saleswoman for {COMPANY_NAME},
answering calls about the customized 1969 Corvette Stingray the shop has for
sale. Your personality is cheerful, positive, and professional: warm and
genuinely enthusiastic about the car, never pushy — {COMPANY_NAME} does not
pressure buyers. Introduce yourself as Ava from {COMPANY_NAME} only once, in
your first greeting of the call. Never repeat the introduction in later
turns — just answer the caller directly.

You are in a voice conversation over a telephone line: keep responses short —
one or two sentences — and never use special characters, since your output is
spoken audio.

Speak the caller's language: respond in whatever language the caller speaks
to you, and if they switch languages, follow them.

Answer style: give the headline answer in one or two sentences, then offer
more detail if they want it — never recite a full spec list unasked. After
answering, occasionally ask one short discovery question — what draws them
to the car, or whether they plan to drive it or collect it — but never more
than one question per turn.

Price questions: never negotiate or discuss offers yourself. Say the asking
price confidently and offer to have the sales specialist discuss any offer
on the callback.

You only discuss the car, the company, and arranging the callback. Politely
steer any other topic back to the car.

About the company:

{company}

The car for sale:

{car_listing}

Callback: your goal is to arrange for a sales specialist to call the caller
back at the number they are calling from. Ask after you have answered a few
questions, or sooner if the caller asks about price, offers, inspection,
shipping, or financing — and always offer once before the call ends. If they
decline, accept gracefully and do not ask again. Once they agree and give a
time, repeat the time back to confirm it, then call the request_callback
tool. Tell the caller the callback is arranged only if the tool reports
success; if it fails, say so honestly, apologize, and invite them to call
back with caller ID enabled or visit the showroom during business hours.

Only state facts about the company and the car that are written above. If
you don't know something, say so honestly and offer to have the specialist
answer it on the callback. Never make up facts, prices, or history."""


SYSTEM_INSTRUCTION = build_system_instruction(
    (DATA_DIR / "car-listing.md").read_text(),
    (DATA_DIR / "company.md").read_text(),
)

transport_params = {
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def get_call_info(call_sid: str | None) -> dict | None:
    """Fetch the caller's and our phone numbers from the Twilio REST API."""
    if not call_sid:
        return None

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        logger.warning("Missing Twilio credentials, cannot fetch call info")
        return None

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"
    try:
        auth = aiohttp.BasicAuth(account_sid, auth_token)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth) as response:
                if response.status != 200:
                    logger.error(f"Twilio API error ({response.status}): {await response.text()}")
                    return None
                data = await response.json()
                return {"from_number": data.get("from"), "to_number": data.get("to")}
    except Exception as e:
        logger.error(f"Error fetching call info from Twilio: {e}")
        return None


def make_request_callback(caller_number: str | None, leads_path: Path):
    async def request_callback(
        params: FunctionCallParams,
        callback_time: str,
        interest_note: str,
        language: str,
    ):
        """Record the caller's permission for a sales specialist to call them back at the number they are calling from. Only call this after the caller has agreed to the callback and said when is a good time to call.

        Args:
            callback_time: When the caller said is a good time to call back, in the caller's own words.
            interest_note: One short sentence on what the caller was interested in.
            language: The language the conversation was held in.
        """
        if not caller_number:
            logger.error("request_callback: caller number is not available")
            await params.result_callback(
                {"status": "failed", "reason": "The caller's phone number is not available."}
            )
            return

        lead = {
            "caller_number": caller_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "callback_time": callback_time,
            "interest_note": interest_note,
            "language": language,
        }
        leads = json.loads(leads_path.read_text()) if leads_path.exists() else []
        leads.append(lead)
        leads_path.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
        logger.info(f"Lead recorded: {lead}")
        await params.result_callback({"status": "recorded"})

    return request_callback


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments, call_info: dict | None):
    logger.info(f"Starting bot, call info: {call_info}")

    caller_number = call_info.get("from_number") if call_info else None
    request_callback = make_request_callback(caller_number, LEADS_PATH)

    llm = OpenAIRealtimeLLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAIRealtimeLLMService.Settings(
            system_instruction=SYSTEM_INSTRUCTION,
            session_properties=SessionProperties(
                audio=AudioConfiguration(
                    input=AudioInput(
                        transcription=InputAudioTranscription(),
                        turn_detection=SemanticTurnDetection(),
                    ),
                    output=AudioOutput(voice=VOICE),
                ),
            ),
        ),
    )

    context = LLMContext(
        [
            {
                "role": "developer",
                "content": "Greet the caller: introduce yourself as Ava from "
                f"{COMPANY_NAME}, mention the 1969 Corvette Stingray is "
                "available, and ask how you can help.",
            }
        ],
        [request_callback],
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            # OpenAI Realtime requires 24 kHz PCM input (the service sends frames
            # to the API unresampled); the transport upsamples Twilio's 8 kHz.
            audio_in_sample_rate=24000,
            audio_out_sample_rate=8000,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Caller connected")
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Caller disconnected")
        await runner.cancel()

    @user_aggregator.event_handler("on_user_turn_message_added")
    async def on_user_turn_message_added(aggregator, message: UserTurnMessageAddedMessage):
        logger.info(f"Transcript user: {message.content}")

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        logger.info(f"Transcript assistant: {message.content}")

    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    call_data = getattr(runner_args, "call_data", None)
    call_info = await get_call_info(call_data.call_id) if call_data else None
    await run_bot(transport, runner_args, call_info)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
