import io
import wave

import httpx
import teacher_product_tasks as tasks


def _error_fields(response):
    err_type = None
    err_code = None
    err_message = None
    try:
        payload = response.json()
        err = payload.get("error") or {}
        err_type = err.get("type")
        err_code = err.get("code")
        err_message = err.get("message")
    except Exception:
        pass
    return err_type, err_code, err_message


def _silent_wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return buf.getvalue()


def run():
    key = (tasks.OPENAI_API_KEY or "").strip()
    if not key:
        print("OpenAI key diagnostic: missing OPENAI_API_KEY", flush=True)
        return

    headers = {"Authorization": f"Bearer {key}"}

    try:
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers=headers,
            timeout=20.0,
        )
        if response.status_code < 400:
            print(f"OpenAI key diagnostic /models: HTTP {response.status_code} OK", flush=True)
        else:
            err_type, err_code, _ = _error_fields(response)
            print(
                f"OpenAI key diagnostic /models: HTTP {response.status_code} type={err_type or '-'} code={err_code or '-'}",
                flush=True,
            )
    except Exception as exc:
        print(f"OpenAI key diagnostic /models failed: {type(exc).__name__}", flush=True)

    # Verify the exact Audio API endpoint used by Telegram voice transcription.
    # This sends only one second of generated silence; no user audio or secret is logged.
    try:
        files = {"file": ("diag.wav", _silent_wav_bytes(), "audio/wav")}
        data = {"model": "gpt-4o-mini-transcribe", "language": "ru"}
        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=30.0,
        )
        if response.status_code < 400:
            print(f"OpenAI audio diagnostic: HTTP {response.status_code} OK", flush=True)
        else:
            err_type, err_code, err_message = _error_fields(response)
            # Message is safe to log: OpenAI error text does not contain the submitted API key.
            print(
                f"OpenAI audio diagnostic: HTTP {response.status_code} type={err_type or '-'} code={err_code or '-'} message={err_message or '-'}",
                flush=True,
            )
    except Exception as exc:
        print(f"OpenAI audio diagnostic failed: {type(exc).__name__}", flush=True)
