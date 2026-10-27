# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout 120 --retries 3 --prefer-binary tensorflow-cpu==2.18.0
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 3 --prefer-binary -r requirements.txt
COPY . .
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
