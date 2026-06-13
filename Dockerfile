FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gettext-base && rm -rf /var/lib/apt/lists/*

RUN pip install flask nanobot-ai -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . /app

EXPOSE 8080

CMD sh -c 'mkdir -p /root/.nanobot && envsubst < /app/config.json > /root/.nanobot/config.json && python message_router.py'