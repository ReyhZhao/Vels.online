FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# --timeout MUST exceed the assistant's total time budget (ASSISTANT_LOOP_DEADLINE_S
# research + pass-1 + pass-2, each bounded by OLLAMA_TIMEOUT_S — see config/settings.py).
# Worst case ≈ 60 + 60 + 60 = 180s, so 240s leaves ~60s margin. Keep these consistent:
# if you raise the assistant budget, raise this too, or the worker gets SIGABRT-killed.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "240"]
