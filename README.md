# LeagueTelegramBot

Telegram bot for league management.

## Developer setup

1. Create a virtualenv and install runtime deps:
   - `python -m venv .venv`
   - `source .venv/bin/activate`
   - `make contribute`
2. If you prefer manual setup instead of `make contribute`:
   - `pip install -r requirements.txt`
   - `pip install -r requirements-dev.txt`
   - `pre-commit install`
   - `pre-commit install --hook-type commit-msg`
3. Prepare config files:
   - `cp app/config.ini.example app/config.ini`
   - Create `app/token.txt` with your bot token.
4. Run the bot:
   - `python scripts/run_bot.py`

## Developer tools

- `pre-commit run -a`
- `ruff check src app scripts`
- `ruff format src app scripts`
- `pytest`
