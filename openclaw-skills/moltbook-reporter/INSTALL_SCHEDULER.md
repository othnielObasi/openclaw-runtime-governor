Scheduler installation
----------------------

This folder provides two options to schedule the Moltbook poster:

- a) systemd user timer (recommended when available)
- b) fallback: run the `moltbook_lablab_poster.py` periodically via `crontab`

Systemd user timer (recommended)

To install the user timer (if your system supports user systemd):

1. Copy the unit files into your user systemd directory:

   mkdir -p ~/.config/systemd/user
   cp openclaw-skills/moltbook-reporter/systemd/moltbook-poster.* ~/.config/systemd/user/

2. Reload systemd user units and enable the timer:

   systemctl --user daemon-reload
   systemctl --user enable --now moltbook-poster.timer

3. Check status:

   systemctl --user status moltbook-poster.timer

Crontab fallback

If `crontab` is available and you prefer cron, run the bundled installer:

   bash openclaw-skills/moltbook-reporter/install_cron.sh

If neither systemd nor crontab are available in your environment (common in lightweight containers), run the poster with a background loop:

   while true; do
     /usr/bin/env python3 openclaw-skills/moltbook-reporter/moltbook_lablab_poster.py
     sleep 1800
   done &

Notes
- Ensure your `~/.config/moltbook/credentials.json` exists with the API key or set `MOLTBOOK_API_KEY` in the environment used by the scheduler.
- The poster enforces its own minimum interval; the timer/crontab schedule is a trigger only.
