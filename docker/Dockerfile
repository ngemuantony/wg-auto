FROM python:3.11-slim

RUN apt update && apt install -y wireguard iproute2

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

ENTRYPOINT ["bash", "docker/entrypoint.sh"]
