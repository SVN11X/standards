"""Fake executors for the tests: an Ollama server that answers the bench tasks and a coding agent that fixes the fixtures."""
import http.server
import itertools
import json
import threading
from pathlib import Path

import bench_tasks

FAKE_AGENT = r'''
import sys
from pathlib import Path
model = sys.argv[1]
if "limit" in model:
    print("Error: 429 Too Many Requests, rate limit reached")
    sys.exit(1)
if "lazy" in model:
    print("All tests pass.")
    sys.exit(0)
task = Path(".delegate-task.md").read_text(encoding="utf-8")
if Path("shop").is_dir():
    pricing = Path("shop/pricing.py")
    pricing.write_text(pricing.read_text().replace("// 10\n", "// 100\n"))
    cart = Path("shop/cart.py")
    cart.write_text(cart.read_text().replace("line_total(price, quantity)", "line_total(price, quantity, discount)"))
    receipt = Path("shop/receipt.py")
    receipt.write_text(receipt.read_text().replace("{total % 100}", "{total % 100:02d}"))
elif "README.md" in task and "Usage" in task:
    readme = Path("README.md")
    readme.write_text(readme.read_text() + "\n## Usage\n\n`sum_even([1, 2])` returns 2. `count_words('a b')` returns 2.\n")
else:
    calc = Path("calc.py")
    calc.write_text(calc.read_text().replace("% 2 != 0", "% 2 == 0"))
print("done")
'''


class Ollama(http.server.BaseHTTPRequestHandler):
    """Models: good:1b answers everything right, bad:1b answers wrong, embed:1b is an embedding model, swap:1b reports another name."""
    seen: list = []
    loaded: list = []
    extra: list = []      # more /api/tags entries, to play a model nobody listed
    silent: set = set()   # models whose /api/show reports no capabilities

    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Ollama.seen.append(self.path)
        if self.path == "/api/tags":
            self.reply(200, {"models": [{"name": n, "size": 2_500_000_000} for n in ("good:1b", "bad:1b", "embed:1b", "swap:1b")]
                             + list(Ollama.extra)})
        elif self.path == "/api/ps":
            self.reply(200, {"models": [{"name": n, "size": 100, "size_vram": 100} for n in Ollama.loaded]})
        else:
            self.reply(200, {"version": "0.0-fake"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Ollama.seen.append(self.path)
        model = body.get("model")
        if self.path == "/api/show":
            can = ["embedding"] if model == "embed:1b" else ["completion", "tools", "vision"]
            self.reply(200, {"details": {"parameter_size": "1B", "family": "fake"}, "model_info": {"fake.context_length": 8192},
                             **({} if model in Ollama.silent else {"capabilities": can})})
        elif self.path == "/api/generate":
            if body.get("keep_alive") == 0 and model in Ollama.loaded:
                Ollama.loaded.remove(model)
            self.reply(200, {"done": True})
        elif self.path == "/api/chat":
            if model not in Ollama.loaded:
                Ollama.loaded.append(model)
            message = answer(body) if model != "bad:1b" else {"content": '{"label": "nope"}'}
            self.reply(200, {"model": "other:9b" if model == "swap:1b" else model, "message": message,
                             "load_duration": 1_500_000_000, "eval_count": 10, "eval_duration": 200_000_000})
        else:
            self.reply(404, {"error": "not found"})


def answer(body: dict) -> dict:
    messages = body["messages"]
    first = messages[0]
    prompt, images = first["content"], first.get("images") or []
    if body.get("tools"):
        done = [m.get("tool_name") for m in messages if m["role"] == "tool"]
        if "read_file" not in done:
            path = "config.yml" if "config.yml" in prompt else "calc.py"
            return {"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": path}}}]}
        if "run_tests" in prompt and "run_tests" not in done:
            return {"content": "", "tool_calls": [{"function": {"name": "run_tests", "arguments": {"target": "tests/test_calc.py"}}}]}
        return {"content": "The file was not found." if "config.yml" in prompt else "sum_even keeps the odd numbers."}
    if prompt.startswith("Classify this issue"):
        return {"content": json.dumps({"label": dict(bench_tasks.CLASSIFY)[prompt.split("Issue: ", 1)[1]]})}
    if prompt.startswith("Extract a JSON"):
        return {"content": json.dumps(bench_tasks.extract_baseline(prompt.split("Line: ", 1)[1]))}
    if prompt.startswith("Summarize"):
        item = next(i for i in bench_tasks.SUMMARIZE if i["text"] in prompt)
        return {"content": json.dumps({"summary": " and ".join(group[0] for group in item["facts"]), "commands": []})}
    if prompt.startswith("Choose the web sub-profile"):
        return {"content": json.dumps({"subprofile": dict(bench_tasks.subprofile_items())[prompt.split("Request: ", 1)[1]]})}
    if prompt.startswith("This image is a screenshot"):
        expected = next(i["expected"] for i in bench_tasks.vision_items() if i["image"] == images[0])
        return {"content": json.dumps(expected)}
    if prompt.startswith("Two versions"):
        pair = next(p for p in bench_tasks.sample_pairs() if {p["a"], p["b"]} == set(images))
        return {"content": json.dumps({"choice": "a" if images[0] == pair[pair["choice"]] else "b", "reason": "clearer"})}
    return {"content": "{}"}


def start_ollama():
    Ollama.seen, Ollama.loaded, Ollama.extra, Ollama.silent = [], [], [], set()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def write_agent(folder: Path) -> Path:
    path = folder / "fake_agent.py"
    path.write_text(FAKE_AGENT, encoding="utf-8")
    return path


PROVIDER_MODELS = [
    {"id": "acme/good:free", "pricing": {"prompt": "0", "completion": "0", "request": "0"}, "context_length": 32000,
     "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}, "supported_parameters": ["tools", "response_format"]},
    {"id": "acme/textonly:free", "pricing": {"prompt": "0", "completion": "0"},
     "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}, "supported_parameters": ["response_format"]},
    {"id": "acme/unsure:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/limit:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/charge:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/swap:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/bill:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/paid", "pricing": {"prompt": "0.000002", "completion": "0.000008"}},
    {"id": "acme/noprice"},
    {"id": "acme/embed-text:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/retired:free", "pricing": {"prompt": "0", "completion": "0"}, "active": False},
]


class Provider(http.server.BaseHTTPRequestHandler):
    """An OpenAI-compatible provider. The key is test-key. Model names decide how it behaves."""
    seen: list = []          # (method, path, model)
    bodies: list = []        # chat payloads as received
    remaining = 40           # free requests the account reports
    outage = 0               # how many chat requests answer 503 before it recovers
    key = "test-key"

    def log_message(self, *args):
        pass

    def reply(self, code, body, headers=None):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def allowed(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {Provider.key}":
            return True
        self.reply(401, {"error": {"message": f"Invalid key {self.headers.get('Authorization')}"}})
        return False

    def do_GET(self):
        Provider.seen.append(("GET", self.path, None))
        if self.path == "/elsewhere/v1/models":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/stolen")
            self.end_headers()
        elif not self.allowed():
            return
        elif self.path == "/v1/models":
            self.reply(200, {"data": PROVIDER_MODELS})
        elif self.path == "/v1/key":
            self.reply(200, {"data": {"usage": 0, "free_model_daily_requests": {"used": 50 - Provider.remaining, "limit": 50,
                                                                                "remaining": Provider.remaining}}})
        else:
            self.reply(404, {"error": {"message": "Not found"}})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        model = body.get("model", "")
        Provider.seen.append(("POST", self.path, model))
        if not self.allowed():
            return
        Provider.bodies.append(body)
        if Provider.outage:
            Provider.outage -= 1
            self.reply(503, {"error": {"message": "overloaded"}})
        elif "limit" in model:
            self.reply(429, {"error": {"message": "Rate limit exceeded: free-models-per-day"}}, {"Retry-After": "3600"})
        elif "bill" in model:
            self.reply(402, {"error": {"message": "Insufficient credits. Add a payment method."}})
        elif body.get("tools") and "unsure" in model:
            self.reply(400, {"error": {"message": "This model does not support tools"}})
        elif any(isinstance(m.get("content"), list) for m in body["messages"]) and "textonly" in model:
            self.reply(404, {"error": {"message": "No endpoints found that support image input"}})
        else:
            message = to_openai_reply(answer(from_openai_request(body)))
            usage = {"prompt_tokens": 10, "completion_tokens": 5, **({"cost": 0.0123} if "charge" in model else {})}
            self.reply(200, {"model": "zzz/another-model" if "swap" in model else model, "usage": usage,
                             "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]},
                       {"x-ratelimit-remaining-requests": "39"})


def from_openai_request(body: dict) -> dict:
    """Turn an OpenAI chat payload into the shape answer() reads."""
    messages = []
    for message in body["messages"]:
        content, images = message.get("content"), []
        if isinstance(content, list):
            images = [part["image_url"]["url"].split("base64,", 1)[1] for part in content if part.get("type") == "image_url"]
            content = "".join(part.get("text", "") for part in content if part.get("type") == "text")
        item = {"role": message["role"], "content": content or "", **({"images": images} if images else {})}
        if message["role"] == "tool":
            calls = [c for m in body["messages"] for c in m.get("tool_calls") or [] if c.get("id") == message.get("tool_call_id")]
            item["tool_name"] = calls[0]["function"]["name"] if calls else None
        messages.append(item)
    return {"messages": messages, "tools": body.get("tools")}


CALL_IDS = itertools.count(1)


def to_openai_reply(message: dict) -> dict:
    calls = [{"id": f"call_{next(CALL_IDS)}", "type": "function",
              "function": {"name": call["function"]["name"], "arguments": json.dumps(call["function"]["arguments"])}}
             for call in message.get("tool_calls") or []]
    return {"role": "assistant", "content": message.get("content") or None, **({"tool_calls": calls} if calls else {})}


def start_provider():
    Provider.seen, Provider.bodies, Provider.remaining, Provider.outage = [], [], 40, 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def provider_settings(url: str) -> dict:
    """A settings/providers.yml for tests: one provider per situation, all pointing at the fake server."""
    shared = {"status": "adapter", "protocol": "openai", "base_url": f"{url}/v1", "cost": "free-quota",
              "features": ["chat", "json", "tools", "vision"], "data": {"stores": "no", "trains": "no"},
              "limits": {"requests_per_day": 100, "requests_per_minute": None}, "sources": ["https://example.com/terms"]}
    return {
        "fake": {**shared, "name": "Fake Router", "key_env": "FAKE_API_KEY", "free_rule": "zero-price", "preflight": "openrouter-key"},
        "plan": {**shared, "name": "Plan Cloud", "key_env": "PLAN_API_KEY", "free_rule": "plan", "preflight": "owner",
                 "features": ["chat", "json"], "data": {"stores": "yes", "trains": "yes"}},
        "keyless": {**shared, "name": "Keyless", "key_env": "KEYLESS_API_KEY_NOT_SET", "free_rule": "plan", "preflight": "owner"},
        "trial": {**shared, "name": "Trial Cloud", "key_env": "FAKE_API_KEY", "cost": "trial", "free_rule": "plan", "preflight": "owner"},
        "gone": {"name": "Gone Models", "status": "retired", "cost": "unknown", "confirmed": "Retired last summer."},
        "cli": {"name": "Some CLI", "status": "no-adapter", "cost": "unknown", "notes": "A command line tool, not an API."},
    }
