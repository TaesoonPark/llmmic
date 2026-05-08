FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential espeak-ng libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN git clone https://github.com/myshell-ai/MeloTTS.git
WORKDIR /opt/MeloTTS

RUN python -m pip install --upgrade pip \
    && python -m pip install -e . fastapi uvicorn \
    && python -m unidic download

COPY service.py /service.py

EXPOSE 8899

CMD ["python", "/service.py"]
