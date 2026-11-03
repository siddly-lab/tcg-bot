#!/bin/bash
# Runs every 5 minutes from DSM Task Scheduler. Pulls the latest code from GitHub and
# restarts the bot only when bot code changed (the daily price commits don't restart it).
cd "$(dirname "$0")/.." || exit 1
LOG=deploy/update.log
git fetch -q origin main || { echo "$(date) fetch failed" >> $LOG; exit 1; }
CHANGED=$(git diff --name-only HEAD origin/main)
[ -z "$CHANGED" ] && exit 0
git reset -q --hard origin/main
if command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; else DC="docker compose"; fi
if echo "$CHANGED" | grep -qE '^(bot/requirements.txt|bot/Dockerfile|docker-compose.yml)$'; then
  $DC up -d --build >> $LOG 2>&1 && echo "$(date) rebuilt" >> $LOG
elif echo "$CHANGED" | grep -q '^bot/'; then
  $DC up -d >> $LOG 2>&1; docker restart tcg-bot >> $LOG 2>&1 && echo "$(date) restarted" >> $LOG
fi
tail -n 200 $LOG > $LOG.tmp 2>/dev/null && mv $LOG.tmp $LOG
