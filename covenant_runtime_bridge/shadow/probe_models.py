import asyncio
import time
import httpx

MODELS = [
    ("qwen2.5-coder:3b-instruct-q4_K_M", 4096, None),
    ("qwen2.5-coder:3b-instruct-q4_K_M", 8192, None),
    ("qwen3:4b", 4096, False),
    ("qwen3:4b", 4096, True),
    ("qwen3:4b", 8192, False),
    ("qwen2.5:7b", 4096, None),
    ("qwen2.5:7b", 8192, None),
    ("qwen2.5-coder:7b", 4096, None),
    ("qwen2.5-coder:7b", 8192, None),
]

async def probe(model, num_ctx, think):
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Return a 5-word summary of project status."}
        ],
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0.0},
    }
    if think is not None:
        payload["think"] = think
    
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(url, json=payload)
            dt = time.perf_counter() - t0
            if resp.status_code == 200:
                data = resp.json()
                eval_count = data.get("eval_count", 0)
                eval_duration = data.get("eval_duration", 1) / 1e9
                tps = eval_count / eval_duration if eval_duration > 0 else 0
                load_duration = data.get("load_duration", 0) / 1e6
                print(f"[OK] {model:<30} ctx={num_ctx:<5} think={str(think):<5} | total={dt:6.2f}s load={load_duration:6.0f}ms eval={eval_count:3d} toks ({tps:5.1f} tps)")
            else:
                print(f"[ERR {resp.status_code}] {model} ctx={num_ctx} think={think}: {resp.text[:100]}")
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"[TIMEOUT/FAIL] {model} ctx={num_ctx} think={think} after {dt:6.2f}s: {e}")

async def main():
    print("=== MODEL CALIBRATION & HARDWARE PROBE ===")
    for m, c, th in MODELS:
        await probe(m, c, th)
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())
