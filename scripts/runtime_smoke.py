"""Run real local embedding and grammar-constrained generation probes.

Records evidence in reports/runtime_smoke.json. Outbound network from this
Python process is refused; llama-server must already be running in offline mode.
"""
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
original_connect = socket.socket.connect


def local_only_connect(self, address):
    if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("Non-loopback network forbidden during runtime smoke")
    return original_connect(self, address)


socket.socket.connect = local_only_connect
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

config = json.loads((ROOT / "runtime_config.json").read_text(encoding="utf-8"))
model_path = ROOT / config["embedding"]["path"]
start = time.monotonic()
torch.set_num_threads(4)
tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
model = AutoModel.from_pretrained(model_path, local_files_only=True, trust_remote_code=False).eval()
texts = ["自由空间路径损耗与载波频率和传播距离有关", "计算收发天线之间的自由空间传输衰减", "热噪声功率与温度和带宽有关"]
tokens = tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors="pt")
with torch.inference_mode():
    vectors = torch.nn.functional.normalize(model(**tokens).last_hidden_state[:, 0], p=2, dim=1).cpu().numpy()
assert vectors.shape == (3, 512)
assert np.isfinite(vectors).all()
assert float(vectors[0] @ vectors[1]) > float(vectors[0] @ vectors[2])
embedding = {"model": config["embedding"], "shape": list(vectors.shape), "norms": np.linalg.norm(vectors, axis=1).tolist(), "cosine_related": float(vectors[0] @ vectors[1]), "cosine_unrelated": float(vectors[0] @ vectors[2]), "elapsed_seconds": time.monotonic() - start, "passed": True}
schema = {"type": "object", "properties": {"selected_formula_ids": {"type": "array", "items": {"type": "string", "enum": ["fspl", "thermal_noise"]}}}, "required": ["selected_formula_ids"], "additionalProperties": False}
request_body = {
    "model": config["generation"]["alias"],
    "messages": [
        {"role": "system", "content": "你只负责从给定候选公式中选择公式ID，不计算数值。候选：fspl=自由空间路径损耗；thermal_noise=热噪声功率。仅输出受约束JSON。"},
        {"role": "user", "content": "已知视距、无遮挡，按自由空间基准计算4.5 GHz、0.2 km的路径损耗。/no_think"},
    ],
    "temperature": 0, "seed": 42, "max_tokens": 100,
    "chat_template_kwargs": {"enable_thinking": False},
    "response_format": {"type": "json_schema", "json_schema": {"name": "formula_selection", "strict": True, "schema": schema}},
}
request = urllib.request.Request(config["generation"]["endpoint"], data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
start = time.monotonic()
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=180) as response:
    reply = json.load(response)
parsed = json.loads(reply["choices"][0]["message"]["content"])
assert parsed == {"selected_formula_ids": ["fspl"]}, parsed
report = {
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "network_boundary": "Python socket.connect rejects non-loopback addresses; local_files_only=True; llama-server started --offline. This is not a physical unplug test.",
    "embedding": embedding,
    "generation": {"model": config["generation"], "request": request_body, "response": reply, "parsed": parsed, "elapsed_seconds": time.monotonic() - start, "passed": True},
    "packages": {name: importlib.metadata.version(name) for name in ("torch", "transformers", "numpy", "tokenizers", "safetensors")},
    "passed": True,
}
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports/runtime_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": True, "embedding": embedding, "selection": parsed}, ensure_ascii=False, indent=2))
