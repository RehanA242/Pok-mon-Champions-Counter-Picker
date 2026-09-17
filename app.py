"""
Pokemon "Big 6" Counter-Picker

Finds the top 5 Pokemon (from the Champions Battle Data roster) best
positioned to counter a fixed "Big 6" opposing team, using real ranked
Doubles usage data for the Big 6 and best-case Level 50 stats for every
candidate. See CLAUDE.md for the full project scope and design notes.
"""

import requests

BASE_URL = "https://championsbattledata.com"
FORMAT = "Doubles"
SEASON = "M6"  # bump this each new ranked season
DAYS = 7

# The fixed team we are building counters for. "force_base" overrides the
# normal "always use Mega when available" rule for a specific member.
BIG_SIX = [
    {"showdown_id": "floetteeternal", "display_name": "Floette-Eternal", "force_base": False},
    {"showdown_id": "dragonite", "display_name": "Dragonite", "force_base": False},
    {"showdown_id": "garchomp", "display_name": "Garchomp", "force_base": True},
    {"showdown_id": "basculegion", "display_name": "Basculegion", "force_base": False},
    {"showdown_id": "kingambit", "display_name": "Kingambit", "force_base": False},
    {"showdown_id": "sneasler", "display_name": "Sneasler", "force_base": False},
]
BIG_SIX_IDS = {member["showdown_id"] for member in BIG_SIX}

# Standard 18-type effectiveness chart (attacker -> {defender: multiplier}).
# Only non-neutral entries are listed; anything missing defaults to 1.0.
TYPE_CHART = {
    "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0,
             "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water": {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0,
              "Rock": 2.0, "Dragon": 0.5},
    "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0,
                 "Flying": 2.0, "Dragon": 0.5},
    "Grass": {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5,
              "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0,
              "Dragon": 0.5, "Steel": 0.5},
    "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0,
            "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5,
                 "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0,
                 "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison": {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5,
               "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground": {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0,
               "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying": {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0,
               "Rock": 0.5, "Steel": 0.5},
    "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0,
                "Steel": 0.5},
    "Bug": {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5,
            "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0,
            "Steel": 0.5, "Fairy": 0.5},
    "Rock": {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5,
             "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost": {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark": {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5,
             "Fairy": 0.5},
    "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0,
              "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy": {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0,
              "Dark": 2.0, "Steel": 0.5},
}

STAT_FIELD_TO_POINTS_KEY = {
    "HP": "hp_points",
    "Attack": "attack_points",
    "Defense": "defense_points",
    "Sp. Atk": "sp_atk_points",
    "Sp. Def": "sp_def_points",
    "Speed": "speed_points",
}


# --- Component 1.1: API Data Fetcher -----------------------------------

def fetch_roster():
    """Hit /api/index and return the list of Pokemon roster entries."""
    response = requests.get(f"{BASE_URL}/api/index")
    response.raise_for_status()
    return response.json()["pokemon"]


def fetch_metadata(showdown_id):
    """Hit /api/metadata/:baseName and return its list of form rows."""
    response = requests.get(f"{BASE_URL}/api/metadata/{showdown_id}")
    response.raise_for_status()
    return response.json()["rows"]


def fetch_battle_data(showdown_id):
    """Hit /api/battle/:format/:name and return the most recent day's rows."""
    response = requests.get(
        f"{BASE_URL}/api/battle/{FORMAT}/{showdown_id}",
        params={"days": DAYS, "season": SEASON},
    )
    response.raise_for_status()
    daily = response.json()["daily"]
    return daily[0]["rows"] if daily else []


# --- Form selection (handles the "always use Mega" rule) ---------------

def pick_best_form(rows, display_name, force_base=False):
    """Pick which metadata row represents a Pokemon's build.

    Uses the Mega form when one exists, unless force_base is set. Falls
    back to the row matching the Pokemon's own display name, then to the
    first row, for species with no plain/default form (e.g. Basculegion).
    """
    if not force_base:
        mega_rows = [row for row in rows if row["form"].startswith("Mega")]
        if mega_rows:
            exact_mega = [row for row in mega_rows if row["form"] == "Mega"]
            return exact_mega[0] if exact_mega else mega_rows[0]

    name_matches = [row for row in rows if row["title"] == display_name]
    if name_matches:
        return name_matches[0]

    plain_forms = [row for row in rows if row["form"] == ""]
    if plain_forms:
        return plain_forms[0]

    return rows[0]


# --- Component 2.1: Virtual EV Math Engine ------------------------------

def level_50_stat(base, ev_points, nature_mod=1.0, is_hp=False, iv=31):
    """Real Level 50 stat from a base stat, an EV/4 term, and a nature.

    ev_points is already the EV/4 value the API's stat_points rows use
    (e.g. 32 for a 128 EV investment), so it plugs straight into the
    standard formula's EV term without any extra conversion.
    """
    core = ((2 * base + iv + ev_points) * 50) // 100
    if is_hp:
        return core + 50 + 10
    return int((core + 5) * nature_mod)


# --- Component 1.2: Target Threat Profiler ------------------------------

def build_threat_profile(member):
    """Build one Big 6 member's real-build stat line, types, and top moves."""
    metadata_rows = fetch_metadata(member["showdown_id"])
    form = pick_best_form(metadata_rows, member["display_name"], member["force_base"])
    types = form["types"].split("/")

    battle_rows = fetch_battle_data(member["showdown_id"])
    nature_rows = [row for row in battle_rows if row["category"] == "stat_alignment"]
    spread_rows = [row for row in battle_rows if row["category"] == "stat_points"]
    move_rows = [row for row in battle_rows if row["category"] == "move"]

    top_nature = min(nature_rows, key=lambda row: row["rank"])
    top_spread = min(spread_rows, key=lambda row: row["rank"])
    top_moves = sorted(move_rows, key=lambda row: row["rank"])[:3]

    stat_up = top_nature["stat_up"]
    stat_down = top_nature["stat_down"]

    def nature_mod(stat_name):
        if stat_name == stat_up:
            return 1.1
        if stat_name == stat_down:
            return 0.9
        return 1.0

    stats = {
        "HP": level_50_stat(form["hp"], top_spread["hp_points"], is_hp=True),
        "Attack": level_50_stat(form["atk"], top_spread["attack_points"], nature_mod("Attack")),
        "Defense": level_50_stat(form["def"], top_spread["defense_points"], nature_mod("Defense")),
        "Sp. Atk": level_50_stat(form["spa"], top_spread["sp_atk_points"], nature_mod("Sp. Atk")),
        "Sp. Def": level_50_stat(form["spd"], top_spread["sp_def_points"], nature_mod("Sp. Def")),
        "Speed": level_50_stat(form["spe"], top_spread["speed_points"], nature_mod("Speed")),
    }

    return {
        "name": form["title"],
        "types": types,
        "nature": top_nature["name"],
        "spread": (top_spread["hp_points"], top_spread["attack_points"],
                   top_spread["defense_points"], top_spread["sp_atk_points"],
                   top_spread["sp_def_points"], top_spread["speed_points"]),
        "stats": stats,
        "top_moves": [row["name"] for row in top_moves],
    }


def print_threat_report(profiles):
    print("=" * 60)
    print("BIG 6 THREAT REPORT")
    print("=" * 60)
    for profile in profiles:
        print(f"\n{profile['name']} ({'/'.join(profile['types'])})")
        print(f"  Most-used nature: {profile['nature']}")
        print(f"  Most-used spread (HP/Atk/Def/SpA/SpD/Spe points): "
              f"{'/'.join(str(v) for v in profile['spread'])}")
        stats = profile["stats"]
        print(f"  Real Level 50 stats: HP {stats['HP']} / Atk {stats['Attack']} / "
              f"Def {stats['Defense']} / SpA {stats['Sp. Atk']} / "
              f"SpD {stats['Sp. Def']} / Spe {stats['Speed']}")
        print(f"  Top moves: {', '.join(profile['top_moves'])}")


# --- Type effectiveness helpers -----------------------------------------

def type_multiplier(attacking_type, defending_types):
    """Combined multiplier of one attacking type against 1-2 defending types."""
    multiplier = 1.0
    for defending_type in defending_types:
        multiplier *= TYPE_CHART.get(attacking_type, {}).get(defending_type, 1.0)
    return multiplier


def best_offensive_multiplier(attacking_types, defending_types):
    return max(type_multiplier(t, defending_types) for t in attacking_types)


# --- Component 2.2: Matchup Score Engine --------------------------------

def build_candidate_profile(roster_entry):
    """Best-case Level 50 stats (max Speed nature/EVs) + types for a candidate."""
    metadata_rows = fetch_metadata(roster_entry["showdownId"])
    form = pick_best_form(metadata_rows, roster_entry["name"])
    types = form["types"].split("/")
    # Ideal build for the outspeed check: +Speed nature, max Speed EVs.
    speed = level_50_stat(form["spe"], ev_points=63, nature_mod=1.1)
    return {"name": form["title"], "types": types, "speed": speed}


def score_candidate(candidate, threat_profiles):
    """+1 per Big 6 member outspeed / hit super effectively / resisted."""
    score = 0
    reasons = []
    for profile in threat_profiles:
        if candidate["speed"] > profile["stats"]["Speed"]:
            score += 1
            reasons.append(f"outspeeds {profile['name']}")

        if best_offensive_multiplier(candidate["types"], profile["types"]) > 1.0:
            score += 1
            reasons.append(f"hits {profile['name']} super effectively")

        # Approximation: a Big 6 member's primary type stands in for its
        # "common attack type", since the API exposes move names but not
        # move types and a full moveset->type lookup is outside this
        # project's 2-day scope.
        common_attack_type = profile["types"][0]
        if type_multiplier(common_attack_type, candidate["types"]) < 1.0:
            score += 1
            reasons.append(f"resists {profile['name']}'s {common_attack_type}-type attacks")

    return score, reasons


def find_top_counters(roster, threat_profiles, top_n=5):
    results = []
    print(f"\nScoring {len(roster)} candidates against the Big 6...")
    for i, roster_entry in enumerate(roster):
        if roster_entry["showdownId"] in BIG_SIX_IDS:
            continue
        candidate = build_candidate_profile(roster_entry)
        score, reasons = score_candidate(candidate, threat_profiles)
        results.append({**candidate, "score": score, "reasons": reasons})
        if (i + 1) % 40 == 0:
            print(f"  ...{i + 1}/{len(roster)} checked")

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]


def print_top_counters(top_counters):
    print("\n" + "=" * 60)
    print(f"TOP {len(top_counters)} COUNTERS")
    print("=" * 60)
    for rank, counter in enumerate(top_counters, start=1):
        print(f"\n#{rank}: {counter['name']} ({'/'.join(counter['types'])}) "
              f"- score {counter['score']}")
        print(f"  Best-case Level 50 Speed: {counter['speed']}")
        for reason in counter["reasons"]:
            print(f"  - {reason}")


# --- Component 2.3: Interactive CLI --------------------------------------

def main():
    print("Fetching roster and Big 6 threat data...")
    roster = fetch_roster()
    threat_profiles = [build_threat_profile(member) for member in BIG_SIX]
    print_threat_report(threat_profiles)

    while True:
        top_counters = find_top_counters(roster, threat_profiles)
        print_top_counters(top_counters)

        again = input("\nRun again? (y/n): ").strip().lower()
        if again != "y":
            print("Goodbye!")
            break


if __name__ == "__main__":
    main()
