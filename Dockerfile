# PID Tools – container for running on an internal server
#   docker build -t pid-tools .
#   docker run -d --name pid-tools -p 8501:8501 --restart unless-stopped pid-tools
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py ./
COPY pidtools ./pidtools
COPY .streamlit ./.streamlit

RUN useradd --create-home pidtools
USER pidtools

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
