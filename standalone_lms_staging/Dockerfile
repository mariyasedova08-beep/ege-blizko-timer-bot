FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY app_bundle.b64 /tmp/app_bundle.b64
RUN python -c "import base64,io,zipfile,pathlib; data=base64.b64decode(pathlib.Path('/tmp/app_bundle.b64').read_text()); zipfile.ZipFile(io.BytesIO(data)).extractall('/app')" && rm /tmp/app_bundle.b64
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn ege_lms.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
