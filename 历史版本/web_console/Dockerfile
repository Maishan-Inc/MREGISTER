FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY web_console/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY . /app

RUN mkdir -p /app/web_console/runtime/tasks

EXPOSE 8000

CMD ["uvicorn", "web_console.app:app", "--host", "0.0.0.0", "--port", "8000"]
