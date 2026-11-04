# Setting up the Grail Discord bot on the Synology

About 15 minutes, once. After that it updates itself within 5 minutes of any change.

## 1. Create the bot in Discord (about 10 minutes, on your PC)

1. Go to https://discord.com/developers/applications and sign in.
2. Click **New Application** (top right). Name it `Grail`, tick the box, click **Create**.
3. Left menu → **Bot** → **Reset Token** → **Yes, do it!** → **Copy**. Paste it into Notepad.
   This is the bot's password: don't share it or post it anywhere.
4. Left menu → **OAuth2** → scroll to **OAuth2 URL Generator**. Tick **bot** and **applications.commands**.
   Under Bot Permissions tick **Send Messages**, **Embed Links** and **Read Message History**.
5. Copy the URL at the bottom, open it in a new tab, pick your server, click **Authorize**.
6. In the Discord app: **User Settings (gear) → Advanced → Developer Mode** on.
   Right-click your server icon → **Copy Server ID** → paste in Notepad.
   Right-click the channel for the daily price post → **Copy Channel ID** → paste in Notepad.

## 2. Install it on the NAS (about 3 minutes, one paste)

1. Open DSM in your browser → **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**.
2. **General** tab: Task name `grail install`, User **root**, untick **Enabled**.
3. **Task Settings** tab: paste this into **Run command**, then replace the three `paste-...` parts with your
   token, server ID and channel ID from Notepad (keep the single quotes):
   ```
   TOKEN='paste-token' GUILD='paste-server-id' CHANNEL='paste-channel-id' bash -c "$(curl -fsSL https://raw.githubusercontent.com/siddly-lab/tcg-bot/main/deploy/install.sh)"
   ```
4. Click **OK** (accept the warning about root). Select the task → **Run** → **OK**. Wait about 2 minutes.
5. **Delete the task** afterwards (select it → **Delete**): it contains your token, and it isn't needed again.

That's it. It downloads the code, saves your settings, starts the bot and starts a small updater next to it.

## 3. Check it

- In Discord, type `/botstatus`. It answers with the version and the price date.
- Try `/watch add` on a card or box you want, for example the Radiance booster box below $100.
- If `/botstatus` doesn't appear after a few minutes: in **File Station → docker**, open
  `tcg-bot-install.log`. It shows what happened (the token is never written to it). Send me what it says.

## Good to know

- Both containers (`tcg-bot`, `tcg-bot-updater`) show in **Container Manager → Container**.
- Your alerts and collection live in `docker/tcg-bot/botdata`, and your token in `docker/tcg-bot/.env`.
  Updates never touch them. Add the `docker/tcg-bot` folder to your Hyper Backup task.
- To change the token or channel later, run the same install command again with the new values.
