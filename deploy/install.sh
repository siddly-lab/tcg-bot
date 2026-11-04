#!/bin/bash
# One-time install on the Synology, run from DSM Task Scheduler as root.
# Usage (one line, with your three values):
#   TOKEN='...' GUILD='...' CHANNEL='...' bash -c "$(curl -fsSL https://raw.githubusercontent.com/siddly-lab/tcg-bot/main/deploy/install.sh)"
# Needs only Container Manager (Docker). Git runs inside a throwaway container.
set -e
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
DIR=/volume1/docker/tcg-bot
LOG=/volume1/docker/tcg-bot-install.log
mkdir -p /volume1/docker
exec > >(tee "$LOG") 2>&1
echo "$(date) installing Grail bot to $DIR"
[ -n "$TOKEN" ] || { echo "Missing TOKEN. Paste your bot token between the quotes."; exit 1; }
mkdir -p /volume1/docker
if [ ! -d "$DIR/.git" ]; then
  docker run --rm -v /volume1/docker:/w alpine/git:latest clone -q https://github.com/siddly-lab/tcg-bot.git /w/tcg-bot
  echo "downloaded the code"
else
  docker run --rm -v "$DIR":/repo -w /repo alpine/git:latest -c safe.directory=/repo pull -q origin main || true
  echo "code already there, updated it"
fi
cd "$DIR"
umask 077
cat > .env <<ENV
DISCORD_TOKEN=$TOKEN
GUILD_ID=$GUILD
CHANNEL_ID=$CHANNEL
DASHBOARD_URL=https://siddly-lab.github.io/tcg-bot/
REFRESH_MINUTES=30
ENV
echo "saved your settings to .env (the token isn't printed here)"
mkdir -p botdata
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
$DC up -d --build
sleep 20
echo "--- bot status ---"
docker ps --filter name=tcg-bot --format '{{.Names}}: {{.Status}}'
echo "--- last bot log lines ---"
docker logs --tail 15 tcg-bot 2>&1 | grep -v -i token || true
echo "$(date) done. In Discord, type /botstatus to check."
