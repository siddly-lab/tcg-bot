FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/code
# The code itself is mounted from the repo folder, so an update is just a restart.
CMD ["python", "-m", "tcgbot.main"]
