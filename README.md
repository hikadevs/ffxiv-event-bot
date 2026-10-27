# FFXIV Event Bot

A Discord bot for Final Fantasy XIV communities, with character profiles and
role-based event signups.

## Features

- Search for characters on the Lodestone and link one to a Discord account.
- View a linked character's profile and job levels with `/character me`.
- Create server events with a local start time, IANA timezone, role slots, and
  an optional minimum job level.
- Sign up for Tank, Healer, or DPS slots using a job from a linked character.
  The bot checks the Lodestone job category and level.
- View an event's public roster with `/event roster`.

## Getting Started

The bot requires Python 3.11 or newer, a PostgreSQL database, and a Discord
application with a bot user. Create a test server and enable the application
commands integration for that server.

1. Install the project and its development dependencies:

   ```sh
   python -m venv .venv
   . .venv/bin/activate
   python -m pip install -e ".[dev]"
   ```

2. Copy `.env.example` to `.env` and set:
   - `DISCORD_TOKEN` to the bot token from the Discord Developer Portal.
   - `TEST_GUILD_ID` to the ID of the server where commands should be synced.
   - `DATABASE_URL` to the PostgreSQL connection URL.

3. Start the bot:

   ```sh
   xivbot
   ```

The database tables are created automatically when the bot starts. Slash
commands are synced to `TEST_GUILD_ID`.

## Commands

- `/ping` checks the bot's latency.
- `/character search name` searches Lodestone characters.
- `/character link name` links the first Lodestone search result to your
  Discord account.
- `/character me` displays your linked character profile and jobs.
- `/character unlink` removes your character link.
- `/event create` creates an event. Role slots are optional, but the total
  number of slots cannot exceed 24. Minimum job level can be set from 1 to 100.
- `/event join` signs up for an available role slot using your linked
  character.
- `/event roster` displays the event's role capacity and signups.

## Event Times

For `/event create`, enter the start time as `YYYY-MM-DD HH:MM` in the creator's
local time and provide its IANA timezone (for example, `America/New_York`). The
bot stores the event as an absolute UTC time and uses Discord's timestamp
formatting, so each viewer sees the event time in their own local timezone.
Local times that do not exist or occur twice because of a daylight-saving
transition are rejected; choose an unambiguous local time instead.

## Event Role Signups

Each player can hold one role per event. The roster is posted publicly in the
server, while event creation and signup responses are private to the user.

## Tech Stack

- Python
- discord.py
- Lodestone character pages
- PostgreSQL
- Railway for deployment
