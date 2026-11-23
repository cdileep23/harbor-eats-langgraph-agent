import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .db import init_db
from .graph import build_graph
from .tracing import configure_tracing

HOST = os.environ.get("AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGENT_PORT", os.environ.get("PORT", "8080")))

TRACER = configure_tracing()
init_db()
GRAPH = build_graph()


def _history(payload: dict) -> list:
    messages = []
    for message in payload.get("messages") or []:
        content = str(message.get("content") or "")
        if message.get("role") == "user":
            messages.append(HumanMessage(content=content))
        elif message.get("role") == "assistant":
            messages.append(AIMessage(content=content))
    new_message = str(payload.get("new_message") or "").strip()
    last_user = messages[-1].content if messages and isinstance(messages[-1], HumanMessage) else None
    if new_message and new_message != last_user:
        messages.append(HumanMessage(content=new_message))
    return messages


def respond(payload: dict) -> dict:
    history = _history(payload)
    with TRACER.start_as_current_span("agent.turn") as span:
        span.set_attribute("agent.turn_index", int(payload.get("turn_index") or 0))
        result = GRAPH.invoke({"messages": history})
    produced = result["messages"][len(history):]
    tool_calls = [
        {"id": call["id"], "name": call["name"], "arguments": call["args"]}
        for message in produced
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    tool_responses = [
        {"id": message.tool_call_id, "name": message.name, "content": message.content}
        for message in produced
        if isinstance(message, ToolMessage)
    ]
    reply = next(
        (m.content for m in reversed(produced) if isinstance(m, AIMessage) and m.content),
        "",
    )
    return {"content": reply, "tool_calls": tool_calls, "tool_responses": tool_responses}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._send(200, {"status": "ok"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/chat":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "request body must be JSON"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "request body must be a JSON object"})
            return
        self._send(200, respond(payload))

    def log_message(self, fmt, *args):
        return


def main():
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
