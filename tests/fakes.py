"""Fake executors for the tests: an Ollama server that answers the bench tasks and a coding agent that fixes the fixtures."""
import http.server
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
            self.reply(200, {"models": [{"name": n, "size": 2_500_000_000} for n in ("good:1b", "bad:1b", "embed:1b", "swap:1b")]})
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
            self.reply(200, {"capabilities": can})
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
    Ollama.seen, Ollama.loaded = [], []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def write_agent(folder: Path) -> Path:
    path = folder / "fake_agent.py"
    path.write_text(FAKE_AGENT, encoding="utf-8")
    return path
