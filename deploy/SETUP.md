# Setting up the Grail Discord bot on the Synology

About 20 minutes, once. After that, updates install themselves within 5 minutes of being merged.

## 1. Create the bot in Discord (about 5 minutes)

1. On your PC, go to https://discord.com/developers/applications and sign in.
2. Click **New Application** (top right). Name it `Grail`, tick the box, click **Create**.
3. In the left menu click **Bot**. Click **Reset Token**, then **Yes, do it!**, then **Copy**.
   Paste it into Notepad for a minute. This is the bot's password, so don't share it.
4. In the left menu click **OAuth2**, then scroll to **OAuth2 URL Generator**.
   Tick **bot** and **applications.commands**. Under Bot Permissions tick **Send Messages**,
   **Embed Links** and **Read Message History**.
5. Copy the URL at the bottom, open it in a new tab, pick your server, click **Authorize**.
6. In the Discord app: **Settings → Advanced → Developer Mode** on. Then right-click your server icon →
   **Copy Server ID** (paste in Notepad), and right-click the channel for the daily price post →
   **Copy Channel ID** (paste in Notepad).

## 2. Install on the NAS (about 10 minutes)

1. Open DSM in your browser. **Package Center** → search **Git Server** → **Install** (this adds the `git` command).
   Also install **Text Editor** if you don't have it.
2. **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script.**
   - General tab: Task name `tcg-bot install`, User **root**, untick **Enabled**.
   - Task Settings tab, paste into Run command:
     ```
     git clone https://github.com/siddly-lab/tcg-bot.git /volume1/docker/tcg-bot; bash /volume1/docker/tcg-bot/deploy/install.sh
     ```
   - Click **OK**, select the task, click **Run**, then **OK**.
3. **File Station → docker → tcg-bot.** Right-click `.env` → **Open with Text Editor**.
   Replace `paste-your-bot-token-here` with the token, and fill in `GUILD_ID` and `CHANNEL_ID`. Save.
   (If you don't see `.env`, go to File Station **Settings** and tick **Show hidden files**.)
4. **Container Manager → Project → Create.**
   - Project name `tcg-bot`, Path: **docker/tcg-bot**, Source: **Use existing docker-compose.yml**.
   - Click **Next** through to **Done**. It builds for a minute or two, then starts.
5. In Discord, type `/botstatus`. It should answer with the version and the price date.

## 3. Turn on automatic updates (2 minutes)

**Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script.**
- General tab: Task name `tcg-bot update`, User **root**.
- Schedule tab: **Run on the following days: Daily**, then under Time pick **Continue running within the same day**,
  every **5 minutes**, from 00:00 to 23:55.
- Task Settings tab, Run command:
  ```
  bash /volume1/docker/tcg-bot/deploy/update.sh
  ```
- **OK**.

It checks GitHub every 5 minutes and restarts the bot only when the bot's code changed. The daily
price updates don't restart it. The log is at `docker/tcg-bot/deploy/update.log`.

## What lives only on the NAS

`.env` (the token) and `botdata/` (alerts and collections). Updates never touch them. They're
worth adding to your Hyper Backup task, since the drives have no redundancy.
