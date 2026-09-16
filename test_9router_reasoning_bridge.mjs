import fs from "node:fs";
import vm from "node:vm";

const sourcePath = process.argv[2];
if (!sourcePath) throw new Error("usage: node test_9router_reasoning_bridge.mjs SOURCE");
let source = fs.readFileSync(sourcePath, "utf8")
  .replace(/^import .*?;$/gm, "")
  .replace(/export function /g, "function ")
  .replace(/register\(FORMATS\.OPENAI, FORMATS\.OPENAI_RESPONSES, null, openaiToOpenAIResponsesResponse\);/g, "")
  .replace(/register\(FORMATS\.OPENAI_RESPONSES, FORMATS\.OPENAI, null, openaiResponsesToOpenAIResponse\);/g, "");
const context = {
  buildChunk: (meta, delta, finish) => ({ ...meta, delta, finish }),
  reasoningDelta: (text) => ({ reasoning_content: text }),
  extractReasoningText: () => "",
  register: () => {},
  FORMATS: { OPENAI: "openai", OPENAI_RESPONSES: "responses" },
  RESPONSES_ITEM: { FUNCTION_CALL: "function_call", CUSTOM_TOOL_CALL: "custom_tool_call" },
  OPENAI_FINISH: { STOP: "stop", TOOL_CALLS: "tool_calls" },
  OPENAI_BLOCK: { FUNCTION: "function" },
  ROLE: { ASSISTANT: "assistant" },
  MODEL_FALLBACK: "fallback",
  fallbackToolCallId: () => "call_test",
};
vm.createContext(context);
vm.runInContext(source + "\nthis.bridge = openaiResponsesToOpenAIResponse;", context);

const state = {};
const raw = context.bridge({ type: "response.reasoning_text.delta", delta: "raw thought" }, state);
if (raw?.delta?.reasoning_content !== "raw thought") {
  throw new Error("raw Halogen reasoning delta was not bridged to reasoning_content");
}

const withSummary = {};
context.bridge({ type: "response.reasoning_summary_part.added" }, withSummary);
const rawWithSummary = context.bridge({ type: "response.reasoning_text.delta", delta: "raw" }, withSummary);
const summary = context.bridge({ type: "response.reasoning_summary_text.delta", delta: "summary" }, withSummary);
if (rawWithSummary !== null || summary?.delta?.reasoning_content !== "summary") {
  throw new Error("summary and raw reasoning events were not de-duplicated");
}

console.log("9Router reasoning bridge test OK");
