import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSalespersonInstructions,
  createResponseEvent,
  createSessionUpdateEvent,
  createUserMessageEvent
} from "../src/realtimeSalesAgent.js";

test("buildSalespersonInstructions includes product and sales behavior", () => {
  const instructions = buildSalespersonInstructions("Demo CRM");

  assert.match(instructions, /Demo CRM/);
  assert.match(instructions, /discovery questions/i);
  assert.match(instructions, /call to action/i);
});

test("createSessionUpdateEvent sets text-only realtime session config", () => {
  const event = createSessionUpdateEvent({ productName: "Demo CRM", voice: "echo" });

  assert.equal(event.type, "session.update");
  assert.deepEqual(event.session.modalities, ["text"]);
  assert.equal(event.session.voice, "echo");
  assert.match(event.session.instructions, /Demo CRM/);
});

test("createUserMessageEvent trims user input", () => {
  const event = createUserMessageEvent("   Tell me more   ");

  assert.equal(event.item.content[0].text, "Tell me more");
});

test("createResponseEvent requests text response", () => {
  const event = createResponseEvent();

  assert.equal(event.type, "response.create");
  assert.deepEqual(event.response.modalities, ["text"]);
});
