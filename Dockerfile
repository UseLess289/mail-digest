FROM python:3.12-slim

# Définir le répertoire de travail avec un chemin absolu
WORKDIR /app

# Copier les dépendances et les installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier tous les scripts Python
COPY bot.py .
COPY digest.py .

# Le point d'entrée par défaut pour le service principal
CMD ["python", "digest.py"]
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY digest.py .
CMD ["python", "digest.py"]
