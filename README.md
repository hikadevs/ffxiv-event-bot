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
   - `PORT` (optional for local runs; Railway sets this automatically).

3. Start the bot:

   ```sh
   xivbot
   ```

## Railway deployment

This project is ready for Railway as a Python service. Add the same environment
variables above in the Railway project settings, then set the start command to:

```sh
python -m xivbot
```

The bot exposes a lightweight `/healthz` endpoint on the Railway-assigned `PORT`
so the service stays healthy while the Discord bot runs in the same process.

The database tables are created automatically when the bot starts. Slash
commands are synced to `TEST_GUILD_ID`.

## Commands

- `/ping` checks the bot's latency.
- `/character search name` searches Lodestone characters.
- `/character link name` links the first Lodestone search result to your
  Discord account.
- `/character me` displays your linked character profile and jobs.
- `/character unlink` removes your character link.
- `/event create` walks you through an event's details, start time, and group
  setup, then lets you review and confirm it. Role slots are optional, but the
  event is posted in the channel where you ran the command. The total number
  of slots cannot exceed 24. Minimum job level can be set from 1 to 100.
- The event post shows the event details, roster, and remaining slots.
  **Details**, **Join**, and **Leave** buttons let members review the event,
  sign up, or drop their signup. Joining uses a job from a linked character.
- `/event join` can also sign up for an event using a linked character.
- `/event leave` leaves an event you can no longer attend.
- `/event roster` displays the event's role capacity and signups.

## Event Times

During the `/event create` walkthrough, choose your timezone from the dropdown
and enter the local start time as `YYYY-MM-DD HH:MM`. Common timezones are
listed, with an option to enter any other IANA timezone (for example,
`America/New_York`). The bot stores the event as an absolute UTC time and uses
Discord's timestamp formatting, so each viewer sees the event time in their
own local timezone. Local times that do not exist or occur twice because of a
daylight-saving transition are rejected; choose an unambiguous local time
instead.

## Event Role Signups

Each player can hold one role per event. The roster is posted publicly with
the event, including each signup's character, world, job, and level. The event
post updates as members join and leave, while signup confirmations are private
to the user.

## Tech Stack

- Python
- discord.py
- Lodestone character pages
- PostgreSQL
- Railway for deployment
