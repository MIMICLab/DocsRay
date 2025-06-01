# Multi-stage build로 이미지 크기 줄이기
FROM python:3.11-slim as builder
# 빌드 의존성 설치
RUN apt-get update && apt-get install -y build-essential cmake git
# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
# 런타임 의존성만 설치
RUN apt-get update && apt-get install -y \
    tesseract-ocr tesseract-ocr-kor \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
    
# 빌더에서 패키지 복사
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages