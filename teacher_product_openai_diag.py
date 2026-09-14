import json
import httpx
import teacher_product_tasks as tasks


def run():
    key = (tasks.OPENAI_API_KEY or "").strip()
    if not key:
        print("OpenAI key diagnostic: missing OPENAI_API_KEY", flush=True)
        return
    try:
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20.0,
        )
        if response.status_code < 400:
            print(f"OpenAI key diagnostic: HTTP {response.status_code} OK", flush=True)
            return
        err_type = None
        err_code = None
        try:
            payload = response.json()
            err = payload.get("error") or {}
            err_type = err.get("type")
            err_code = err.get("code")
        except Exception:
            pass
        print(
            f"OpenAI key diagnostic: HTTP {response.status_code} type={err_type or '-'} code={err_code or '-'}",
            flush=True,
        )
    except Exception as exc:
        print(f"OpenAI key diagnostic failed: {type(exc).__name__}", flush=True)
