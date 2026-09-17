# Pokémon Battle Counter-Picker

Finds the best Pokémon to counter a given Doubles team, using real ranked battle
data to figure out each opponent's actual stats, moves, and speed — instead of
guessing from base stats alone.

Built against the 2026 World Champion's actual Doubles team of 6 as a test case.

## How it works

1. Pulls real ranked-usage data for the target team (their most common nature,
   EV spread, and moves) and computes their true in-battle stats
2. Scans every other Pokémon in the game and builds each one's best possible
   stat line
3. Scores every candidate on three things: does it outspeed the target team,
   does it hit them super effectively, and does it resist their attacks
4. Ranks and prints the top 5 counters, with the reasoning behind each pick

## Tech stack

Python, REST APIs, JSON

Data pulled live from the [Champions Battle Data API](https://championsbattledata.com/api_guide).

## Setup and Usage
```bash
pip install requests
python app.py
```
