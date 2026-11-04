#!/bin/sh
# Runs inside the updater container. Every 5 minutes: pull the latest code from GitHub and restart
# the bot only when the bot's own files changed (the daily price commits don't restart it).
apk add --no-cache git docker-cli >/dev/null 2>&1
git config --global --add safe.directory /repo
LOG=/repo/deploy/update.log
while true; do
  cd /repo || exit 1
  if git fetch -q origin main 2>>"$LOG"; then
    CHANGED=$(git diff --name-only HEAD origin/main)
    if [ -n "$CHANGED" ]; then
      git reset -q --hard origin/main
      if echo "$CHANGED" | grep -q '^bot/'; then
        docker restart tcg-bot >/dev/null && echo "$(date) bot restarted with the latest code" >> "$LOG"
      fi
      if echo "$CHANGED" | grep -qE '^(deploy/updater-loop.sh|docker-compose.yml)$'; then
        echo "$(date) updater script changed, restarting the updater" >> "$LOG"
        docker restart tcg-bot-updater
      fi
    fi
  else
    echo "$(date) couldn't reach GitHub, will try again" >> "$LOG"
  fi
  tail -n 200 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
  sleep 300
done
