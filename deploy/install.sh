#!/bin/bash
# One-time install on the Synology. Run from DSM Task Scheduler as root (see deploy/SETUP.md).
set -e
DIR=/volume1/docker/tcg-bot
mkdir -p /volume1/docker
if [ ! -d "$DIR/.git" ]; then
  git clone https://github.com/siddly-lab/tcg-bot.git "$DIR"
fi
cd "$DIR"
[ -f .env ] || cp .env.example .env
mkdir -p botdata
echo "Installed to $DIR on $(date). Next: put your bot token in $DIR/.env" > deploy/install.log
