# Servicio de IA de AsistControl (FastAPI + scikit-learn)
FROM python:3.12-slim
WORKDIR /servicio

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app

# Render asigna el puerto en la variable PORT
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
