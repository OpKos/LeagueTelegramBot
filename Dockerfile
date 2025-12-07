FROM python:3.12-slim AS app

RUN apt-get update && apt-get install -y fontconfig

RUN mkdir -p /app/
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    rm -rf /root/.cache/pip

COPY app/* /app/

RUN mkdir -p /usr/share/fonts/custom
COPY Jost-VariableFont_wght.ttf /usr/share/fonts/custom/
RUN fc-cache -f -v

WORKDIR /app
EXPOSE 8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["/app/telegram_main.py"]
