FROM python:3.12-slim AS app

RUN mkdir -p /app/
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    rm -rf /root/.cache/pip

COPY app/* /app/

WORKDIR /app
EXPOSE 8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["/app/telegram_main.py"]
