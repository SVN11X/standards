#!/usr/bin/env python3
"""Call remote model providers through one transport for OpenAI-compatible APIs.

Commands:
  status            list the providers of settings/providers.yml and whether each has its key. Never prints a key
  models ID         ask one provider for its models and keep the list in STANDARDS_HOME/providers
  check ID          ask one provider about the account and its free quota, where an endpoint reports it

The transport lists models, checks the account before a call, sends chat requests with text, images and tools,
and turns every failure into one error with a kind. Keys come from the environment only: they are never stored,
printed or written to a report. This module decides nothing about cost or privacy. scripts/orchestrate.py asks
its gate first and calls this after.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required. Install it with: pip install pyyaml")

STANDARD_ROOT = Path(__file__).resolve().parents[1]
SETTINGS = STANDARD_ROOT / "settings" / "providers.yml"
NOT_CHAT = re.compile(r"embed|whisper|tts|speech|rerank|moderation|guard|imagen|flux|diffusion|transcri", re.IGNORECASE)
UPGRADE = re.compile(r"upgrade|paid plan|billing|payment|insufficient (credit|balance|quota)|\b5035\b", re.IGNORECASE)
DATA_POLICY = re.compile(r"data policy|data_collection|privacy settings", re.IGNORECASE)
UPSTREAM = re.compile(r"upstream|provider returned error", re.IGNORECASE)
UNSUPPORTED = re.compile(r"not support|unsupported|no endpoints found|does not accept|is not available for|invalid.*(tool|image|response_format)",
                         re.IGNORECASE)
PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
IMAGE_TYPES = (("iVBOR", "image/png"), ("/9j/", "image/jpeg"), ("R0lG", "image/gif"), ("UklG", "image/webp"))


class ProviderError(Exception):
    """One failure of a provider call. kind is no-key, config, auth, payment, rate-limit, privacy, unsupported, rejected,
    not-found, unavailable, network or bad-reply. upstream is True when a limit belongs to the host behind a router,
    which is one model's problem, not the account's."""

    def __init__(self, kind: str, message: str, status: int | None = None, retry_after: str | None = None, upstream: bool = False):
        super().__init__(message)
        self.kind, self.status, self.retry_after, self.upstream = kind, status, retry_after, upstream


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect could carry the key to another host, so it is an error instead."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to another address refused ({code})", headers, fp)


OPENER = urllib.request.build_opener(NoRedirect)


def home() -> Path:
    path = Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")
    path.mkdir(parents=True, exist_ok=True)
    return path


def load(path: Path | None = None) -> dict:
    path = path or SETTINGS
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("providers") or {}


def split(model: str) -> tuple[str, str]:
    """provider/model. The model part keeps its own slashes."""
    provider, _, name = model.partition("/")
    return provider, name


def missing_env(conf: dict) -> list[str]:
    """Names of the environment variables this provider still needs. Only names, never values."""
    names = [conf["key_env"]] if conf.get("key_env") else []
    names += PLACEHOLDER.findall(str(conf.get("base_url", "")))
    return [name for name in dict.fromkeys(names) if not os.environ.get(name)]


def base_url(conf: dict) -> str:
    raw = str(conf.get("base_url") or "")
    if not raw:
        raise ProviderError("config", "this provider has no base_url")
    lacking = [name for name in PLACEHOLDER.findall(raw) if not os.environ.get(name)]
    if lacking:
        raise ProviderError("no-key", f"set {', '.join(lacking)} in the environment")
    url = PLACEHOLDER.sub(lambda match: urllib.parse.quote(os.environ[match.group(1)], safe=""), raw).rstrip("/")
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https" and (parts.hostname or "") not in {"127.0.0.1", "localhost", "::1"}:
        raise ProviderError("config", "a provider address must use https")
    return url


def is_gateway(conf: dict) -> bool:
    """A gateway routes one request among several providers behind one address. Listening on localhost does not make it local."""
    return isinstance(conf.get("gateway"), dict)


def gateway_allow(conf: dict) -> list[str]:
    """The provider/model pairs a gateway may use, from settings. Nothing is sent to a gateway without a non-empty list."""
    allow = (conf.get("gateway") or {}).get("allow")
    if not isinstance(allow, list) or not allow or not all(isinstance(item, str) and "/" in item.strip("/") for item in allow):
        raise ProviderError("config", "a gateway needs an allowed list of provider/model pairs before anything is sent")
    return list(allow)


def gateway_request(conf: dict) -> dict:
    """What a gateway receives besides the chat: the allowed list for its routing and its own fallback, and fusion, caching and billing off.
    The names are this adapter's contract. A real gateway needs them mapped and proven at trial."""
    settings = conf["gateway"]
    if settings.get("fusion") or settings.get("cache"):
        raise ProviderError("config", "fusion and caching of private data stay off for a gateway")
    return {"allow": gateway_allow(conf), "fusion": False, "cache": False, "billing": "refuse"}


def gateway_answer(conf: dict, reply: dict) -> str:
    """The provider/model that answered, checked against the allowed list. A gateway that does not say, or answered
    from outside the list, or fused or served a cached reply, is refused."""
    info = reply.get("gateway") if isinstance(reply, dict) else None
    provider, model = (info or {}).get("provider"), (info or {}).get("model")
    if not isinstance(provider, str) or not isinstance(model, str) or not provider or not model:
        raise ProviderError("bad-reply", "the gateway did not say which provider answered")
    if info.get("fusion") or info.get("cached"):
        raise ProviderError("privacy", "the gateway fused several providers or served a cached reply")
    answered = f"{provider}/{model}"
    if answered not in gateway_allow(conf):
        raise ProviderError("privacy", f"the gateway answered from {answered}, which is not in the allowed list")
    return answered


def redact(text: str, conf: dict) -> str:
    """Remove the key and any bearer value from text that will be shown or stored."""
    for name in [conf.get("key_env"), *PLACEHOLDER.findall(str(conf.get("base_url", "")))]:
        value = os.environ.get(name or "")
        if value:
            text = text.replace(value, "[hidden]")
    return re.sub(r"(?i)(bearer\s+)\S+", r"\1[hidden]", text)


def call(conf: dict, method: str, path: str, payload: dict | None = None, timeout: float = 60,
         retries: int = 1, sleep=time.sleep) -> tuple[dict, dict]:
    """One request. Returns the JSON body and the headers in lower case. One retry on a server or network error, none on a limit."""
    url = base_url(conf) + path
    key = os.environ.get(conf.get("key_env") or "")
    if conf.get("key_env") and not key:
        raise ProviderError("no-key", f"set {conf['key_env']} in the environment")
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "standards-analyzer"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    attempt = 0
    while True:
        attempt += 1
        try:
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            with OPENER.open(request, timeout=timeout) as response:  # noqa: S310 (https or loopback, checked in base_url)
                body = response.read().decode("utf-8", "replace")
                seen = {name.lower(): value for name, value in response.headers.items()}
            try:
                parsed = json.loads(body)
            except ValueError as error:
                raise ProviderError("bad-reply", "the provider did not answer with JSON") from error
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), (dict, str)) and "choices" not in parsed and "data" not in parsed:
                raise failure(200, json.dumps(parsed["error"]), {}, conf)
            return parsed, seen
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", "replace") if error.fp else ""
            problem = failure(error.code, text, dict(error.headers or {}), conf)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            problem = ProviderError("network", redact(str(getattr(error, "reason", error))[:200], conf))
        if problem.kind in {"unavailable", "network"} and attempt <= retries:
            sleep(2 * attempt)
            continue
        raise problem


def failure(status: int, text: str, headers: dict, conf: dict) -> ProviderError:
    """Name an HTTP failure. A request for money and a limit are told apart from a wrong key or a missing feature."""
    detail = redact(" ".join(text.split())[:300], conf)
    lower = {str(name).lower(): value for name, value in headers.items()}
    if status == 402 or (status in {200, 400, 403} and UPGRADE.search(text) and not UNSUPPORTED.search(text)):
        kind = "payment"
    elif status == 429:
        kind = "rate-limit"
    elif DATA_POLICY.search(text) and status in {200, 400, 403, 404}:
        kind = "privacy"
    elif status in {401, 403}:
        kind = "auth"
    elif UNSUPPORTED.search(text) and status in {200, 400, 404, 422, 501}:
        kind = "unsupported"
    elif status == 404:
        kind = "not-found"
    elif status >= 500:
        kind = "unavailable"
    else:
        kind = "rejected"
    return ProviderError(kind, f"HTTP {status}: {detail}" if detail else f"HTTP {status}", status, lower.get("retry-after"),
                         upstream=kind == "rate-limit" and bool(UPSTREAM.search(text)))


# Discovery


def zero_price(pricing) -> bool | None:
    """True when every listed price is 0, False when one is not, None when the listing has no prices."""
    if not isinstance(pricing, dict):
        return None
    values = [value for value in pricing.values() if value not in (None, "")]
    try:
        return all(float(value) == 0 for value in values) if values else None
    except (TypeError, ValueError):
        return None


def normalize_model(provider: str, raw: dict) -> dict | None:
    name = raw.get("id") or raw.get("name")
    if not isinstance(name, str) or not name:
        return None
    architecture = raw.get("architecture") if isinstance(raw.get("architecture"), dict) else {}
    inputs, outputs = architecture.get("input_modalities"), architecture.get("output_modalities")
    parameters = raw.get("supported_parameters")
    if name.startswith(f"{provider}/") and provider == "openrouter":
        kind = "router"
    elif NOT_CHAT.search(name) or (isinstance(outputs, list) and set(outputs) != {"text"}):
        kind = "other"
    else:
        kind = "chat"
    return {"id": name, "kind": kind, "free": zero_price(raw.get("pricing")),
            "vision": ("image" in inputs) if isinstance(inputs, list) else None,
            "tools": ("tools" in parameters) if isinstance(parameters, list) else None,
            "context": raw.get("context_length") or raw.get("context_window"),
            "active": raw.get("active", True) is not False}


def list_models(provider: str, conf: dict, timeout: float = 30) -> list[dict]:
    reply, _ = call(conf, "GET", "/models", timeout=timeout)
    rows = reply.get("data") if isinstance(reply, dict) else reply
    if not isinstance(rows, list):
        raise ProviderError("bad-reply", "the models list has an unexpected shape")
    return [model for model in (normalize_model(provider, row) for row in rows if isinstance(row, dict)) if model]


def cache_file(provider: str) -> Path:
    return home() / "providers" / f"{provider}.json"


def cached(provider: str) -> dict | None:
    path = cache_file(provider)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None


def cache_age_hours(listing: dict | None) -> float | None:
    try:
        fetched = dt.datetime.fromisoformat((listing or {})["fetched"])
    except (KeyError, ValueError, TypeError):
        return None
    return (dt.datetime.now(dt.timezone.utc) - fetched).total_seconds() / 3600


def refresh(provider: str, conf: dict) -> dict:
    """Ask the provider for its models and keep the list. A failure is kept too, so the report can say why."""
    listing = {"provider": provider, "fetched": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "models": []}
    try:
        listing["models"] = list_models(provider, conf)
    except ProviderError as error:
        listing["error"] = {"kind": error.kind, "message": str(error)}
    path = cache_file(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(listing, indent=2) + "\n", encoding="utf-8")
    return listing


def preflight(provider: str, conf: dict) -> dict:
    """What the provider says about the account before a call. ok is False only when it reports no free quota left."""
    if conf.get("preflight") != "openrouter-key":
        return {"ok": True, "remaining": None, "why": "no endpoint reports the account, so the owner's check is the evidence"}
    reply, _ = call(conf, "GET", "/key", timeout=30)
    data = reply.get("data") if isinstance(reply.get("data"), dict) else reply
    quota = data.get("free_model_daily_requests") if isinstance(data.get("free_model_daily_requests"), dict) else {}
    remaining = quota.get("remaining")
    if isinstance(remaining, (int, float)) and remaining <= 0:
        return {"ok": False, "remaining": 0, "why": "the free requests of today are used up"}
    return {"ok": True, "remaining": int(remaining) if isinstance(remaining, (int, float)) else None,
            "why": f"{int(remaining)} free requests left today" if isinstance(remaining, (int, float)) else "the account answered, without a free quota figure"}


# Inference


def image_type(encoded: str) -> str:
    return next((kind for start, kind in IMAGE_TYPES if encoded.startswith(start)), "image/png")


def to_openai(messages: list[dict]) -> list[dict]:
    """The scripts keep messages in Ollama's shape: images as a base64 list, tool arguments as an object. Convert them."""
    out = []
    for message in messages:
        role = message.get("role")
        if role == "user" and message.get("images"):
            parts = [{"type": "text", "text": message.get("content", "")}]
            parts += [{"type": "image_url", "image_url": {"url": f"data:{image_type(image)};base64,{image}"}} for image in message["images"]]
            out.append({"role": "user", "content": parts})
        elif role == "assistant" and message.get("tool_calls"):
            calls = [{"id": call_.get("id") or f"call_{index}", "type": "function",
                      "function": {"name": (call_.get("function") or {}).get("name"),
                                   "arguments": json.dumps((call_.get("function") or {}).get("arguments") or {})}}
                     for index, call_ in enumerate(message["tool_calls"])]
            out.append({"role": "assistant", "content": message.get("content") or None, "tool_calls": calls})
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": message.get("tool_call_id") or "call_0", "content": message.get("content", "")})
        else:
            out.append({"role": role, "content": message.get("content", "")})
    return out


def from_openai(message: dict) -> dict:
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    calls = []
    for call_ in message.get("tool_calls") or []:
        function = call_.get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = None
        calls.append({"id": call_.get("id"), "function": {"name": function.get("name"), "arguments": arguments}})
    return {"role": "assistant", "content": content or "", **({"tool_calls": calls} if calls else {})}


def same_model(asked: str, answered: str | None) -> bool:
    """A reply may add or drop a suffix such as a date or :free. Another model family is a mismatch."""
    return not answered or asked == answered or asked.startswith(answered) or answered.startswith(asked)


def chat(conf: dict, model: str, messages: list[dict], tools: list | None = None, want_json: bool = False,
         max_tokens: int = 400, timeout: float = 60) -> dict:
    """One chat completion. Raises ProviderError with kind unsupported when the adapter may not send what the request needs."""
    features = conf.get("features") or []
    needs = [name for name, wanted in (("vision", any(m.get("images") for m in messages)), ("tools", bool(tools)),
                                       ("json", want_json)) if wanted and name not in features]
    if needs:
        raise ProviderError("unsupported", f"the adapter for {conf.get('name', 'this provider')} does not send {', '.join(needs)}")
    payload = {"model": model, "messages": to_openai(messages), conf.get("max_tokens_field", "max_tokens"): max_tokens,
               **(conf.get("request_extra") or {})}
    if is_gateway(conf):
        payload["gateway"] = gateway_request(conf)
    if tools:
        payload["tools"] = tools
    if want_json:
        payload["response_format"] = {"type": "json_object"}
    reply, headers = call(conf, "POST", "/chat/completions", payload, timeout)
    choices = reply.get("choices") if isinstance(reply, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError("bad-reply", "the reply has no choices")
    usage = reply.get("usage") if isinstance(reply.get("usage"), dict) else {}
    charged = usage.get("cost")
    answered_by = gateway_answer(conf, reply) if is_gateway(conf) else None
    return {"provider": answered_by, "message": from_openai(choices[0].get("message") or {}), "model": reply.get("model"), "usage": usage,
            "charged": charged if isinstance(charged, (int, float)) and charged > 0 else None,
            "limits": {name: value for name, value in headers.items() if name.startswith("x-ratelimit") or name == "retry-after"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    for name in ("models", "check"):
        sub.add_parser(name).add_argument("provider")
    args = parser.parse_args(argv)
    known = load()
    if args.command == "status":
        for name, conf in known.items():
            lacking = missing_env(conf) if conf.get("status") == "adapter" else []
            if conf.get("status") != "adapter":
                state = conf.get("status")
            elif conf.get("cost") not in {"local", "free-quota", "free-promo"}:
                state = "never called: not a free offer"
            else:
                state = "needs " + ", ".join(lacking) if lacking else "key present"
            print(f"{name:<18} {conf.get('cost', '-'):<11} {state}")
        return 0
    conf = known.get(args.provider)
    if not conf or conf.get("status") != "adapter":
        print(f"{args.provider} has no adapter in settings/providers.yml", file=sys.stderr)
        return 2
    try:
        if args.command == "check":
            print(json.dumps(preflight(args.provider, conf), indent=2))
            return 0
        listing = refresh(args.provider, conf)
        if listing.get("error"):
            raise ProviderError(listing["error"]["kind"], listing["error"]["message"])
        for model in listing["models"]:
            price = {True: "price 0", False: "priced", None: "no price listed"}[model["free"]]
            print(f"{model['id']:<60} {model['kind']:<8} {price}")
        print(f"\n{len(listing['models'])} models kept in {cache_file(args.provider)}")
        return 0
    except ProviderError as error:
        print(f"{error.kind}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
