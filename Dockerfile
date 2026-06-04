FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY digest.py .

# Le point d'entrée par défaut pour le service principal
CMD ["python", "digest.py"]
