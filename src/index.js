import WebSocket from "ws";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import {
  createResponseEvent,
  createSessionUpdateEvent,
  createUserMessageEvent
} from "./realtimeSalesAgent.js";

const apiKey = process.env.OPENAI_API_KEY;
const model = process.env.OPENAI_REALTIME_MODEL || "gpt-4o-realtime-preview";
const productName = process.env.SALES_PRODUCT_NAME || "Sales Person AI";

if (!apiKey) {
  console.error("Missing OPENAI_API_KEY environment variable.");
  process.exit(1);
}

const ws = new WebSocket(
  `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(model)}`,
  {
    headers: {
      Authorization: "Bearer " + apiKey,
      "OpenAI-Beta": "realtime=v1"
    }
  }
);

const rl = readline.createInterface({ input, output });

ws.on("open", async () => {
  console.log(`Connected to OpenAI Realtime API with model ${model}`);
  ws.send(JSON.stringify(createSessionUpdateEvent({ productName })));

  while (true) {
    const prompt = await rl.question("you> ");
    if (!prompt || prompt.trim().toLowerCase() === "exit") {
      break;
    }

    ws.send(JSON.stringify(createUserMessageEvent(prompt)));
    ws.send(JSON.stringify(createResponseEvent()));
  }

  rl.close();
  ws.close();
});

ws.on("message", (data) => {
  let event;

  try {
    event = JSON.parse(data.toString());
  } catch {
    return;
  }

  if (event.type === "response.text.delta") {
    process.stdout.write(event.delta);
  }

  if (event.type === "response.text.done") {
    process.stdout.write("\n");
  }

  if (event.type === "error") {
    console.error("Realtime API error:", event.error?.message || event);
  }
});

ws.on("close", () => {
  console.log("Disconnected from OpenAI Realtime API");
});

ws.on("error", (error) => {
  console.error("WebSocket error:", error.message);
});
