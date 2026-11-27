// Hosted web search is executed by the Responses API, not by Pi.
type Obj = Record<string, any>;
export default function responses(pi: { on: (name: string, handler: (event: any, ctx: any) => any) => void }) {
  pi.on("before_provider_request", (event, ctx) => {
    if (ctx.model?.api !== "openai-responses") throw new Error("Responses protocol required");
    const payload = event.payload as Obj;
    if (!payload || !Array.isArray(payload.input)) throw new Error("Unexpected Responses request");
    const tools = Array.isArray(payload.tools) ? [...payload.tools] : [];
    if (!tools.some(t => t.type === "web_search")) tools.push({type: "web_search"});
    return {...payload, tools, store: false};
  });
}
