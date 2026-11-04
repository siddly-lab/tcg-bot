FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/code
# The code is mounted from the repo folder, so an update is just a restart.
# Requirements are re-checked on each start, so a new library version arrives with a restart too.
CMD ["sh", "-c", "pip install --no-cache-dir -q -r /app/code/requirements.txt && exec python -m tcgbot.main"]
