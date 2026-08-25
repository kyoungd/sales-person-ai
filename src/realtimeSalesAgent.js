export const DEFAULT_PRODUCT_NAME = "Sales Person AI";

export function buildSalespersonInstructions(productName = DEFAULT_PRODUCT_NAME) {
  return [
    `You are a top performing sales representative for ${productName}.`,
    "Open with a concise greeting and learn the prospect's goals.",
    "Ask discovery questions before pitching features.",
    "Tie benefits to the prospect's stated needs.",
    "Handle objections with empathy and clear next steps.",
    "Close by proposing a specific call to action."
  ].join(" ");
}

export function createSessionUpdateEvent({
  productName = DEFAULT_PRODUCT_NAME,
  voice = "alloy",
  temperature = 0.7
} = {}) {
  return {
    type: "session.update",
    session: {
      instructions: buildSalespersonInstructions(productName),
      voice,
      temperature,
      modalities: ["text"]
    }
  };
}

export function createUserMessageEvent(text) {
  return {
    type: "conversation.item.create",
    item: {
      type: "message",
      role: "user",
      content: [{ type: "input_text", text: text.trim() }]
    }
  };
}

export function createResponseEvent() {
  return {
    type: "response.create",
    response: {
      modalities: ["text"]
    }
  };
}
