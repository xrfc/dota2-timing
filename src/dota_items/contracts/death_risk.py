"""Contract of the death-risk tables (track B, U160): names, schema and generation checks.

Standard library only. The producer (scripts/build_death_risk_table.py with
data.death_risk) writes one table folder: a `manifest.json` holding the generation
conditions and one `<match>.pkl` per match carrying the digest of those conditions.
Consumers (experiments.awareness.death_risk_tables) refuse folders whose files disagree.

Semantics that consumers must not reinterpret:

* `hit_recent` is 1 when an enemy hero (not an illusion) damaged the real hero in the
  last `hit_window` seconds (3). A sample with `hit_recent == 0` is "not hit in the last
  3 seconds", NOT "not yet hit in this fight": he may have been hit 4 seconds earlier.
* An alert counted by `modeling.awareness.death_risk_eval.alert_leads` is an alert on such
  a sample within the horizon before the death. Reports dated 2026-11-17 call it
  `alerted_before_being_hit`; that name overstated it and is replaced by
  `alerted_not_hit_last_3s` (see docs/b2-death-risk-contract.md). It is kept only for
  comparison: the main measure is fight-level, "before the fight began" (U171,
  `death_risk_eval.fight_alerts`), computed from the `hits` and `contact` parts.
* `contact` holds facts for fight boundaries, including the real distance of unseen
  enemies: evaluation only, never a feature.
"""

from dota_items.storage import digest

TABLE_SCHEMA = "death-risk-table/4"  # 4: manifest and per-match generation digest
MANIFEST_SCHEMA = "death-risk-manifest/1"
MANIFEST = "manifest.json"
LEGACY_SCHEMAS = ("death-risk-table/1", "death-risk-table/2", "death-risk-table/3")
CONDITION_KEYS = ("positions", "params", "win_step", "producer", "knowledge")
# hits: damage taken by second and source; contact: per second, whether the enemy team
# saw him and how far the nearest visible / real enemy hero was (for fight boundaries)
TABLE_PARTS = ("risk", "win", "deaths", "hits", "contact")
CONTACT_COLUMNS = ("t", "seen_by_enemy", "visible_enemy_distance", "enemy_distance")

FEATURES_V1 = (
    "minute",
    "hp",
    "hp_frac",
    "hp_frac_change",
    "mana_frac",
    "level",
    "level_vs_enemies",
    "depth",
    "own_tower_distance",
    "enemy_tower_distance",
    "allies_alive",
    "allies_near",
    "nearest_ally_distance",
    "enemies_alive",
    "enemies_visible",
    "enemies_visible_near",
    "enemies_visible_mid",
    "nearest_visible_enemy_distance",
    "enemies_missing",
    "missing_shortest_age",
    "missing_longest_age",
    "nearest_missing_last_seen_distance",
    "hit_recent",
)
FEATURES_V2_EXTRA = (
    "saves_owned",
    "saves_ready",
    "own_creeps_distance",
    "ahead_of_own_creeps",
    "own_observers_covering",
    "missing_initiators",
    "visible_initiators_mid",
)
FEATURES_V2 = FEATURES_V1 + FEATURES_V2_EXTRA
FEATURES_V3_REACH = ("reach_now", "reach_10", "reach_min", "reach_second")
TREND_OF = (
    "enemies_visible",
    "enemies_missing",
    "depth",
    "nearest_visible_enemy_distance",
    "hp_frac",
    "allies_near",
    "reach_min",
)
# Trend lags in seconds, whatever the sampling step (since 2026-11-18; before, the lags
# were 1, 2 and 3 samples, the same seconds at the step of 5). `_d1` is the 5 s change.
TREND_SECONDS = (5, 10, 15)
VANISHED_SECONDS = 10  # `vanished_10`: enemies that left sight over this many seconds
FEATURES_V3_TREND = tuple(
    f"{name}_d{index}" for name in TREND_OF for index in range(1, len(TREND_SECONDS) + 1)
) + ("vanished_10",)
FEATURES = FEATURES_V2 + FEATURES_V3_REACH + FEATURES_V3_TREND
ID_COLUMNS = ("match_id", "hero", "t", "position", "team")


class TableError(ValueError):
    """A table folder or file that must not be used as it is."""


def check_manifest(manifest):
    """Raise TableError unless `manifest` is a complete manifest of this schema."""
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise TableError(f"not a {MANIFEST_SCHEMA} manifest")
    if manifest.get("table_schema") != TABLE_SCHEMA:
        raise TableError(f"manifest is for {manifest.get('table_schema')}, expected {TABLE_SCHEMA}")
    missing = [key for key in CONDITION_KEYS if key not in manifest.get("conditions", {})]
    if missing:
        raise TableError(f"manifest conditions miss {missing}")
    if manifest.get("conditions_digest") != digest(manifest["conditions"]):
        raise TableError("manifest conditions_digest mismatch")


def check_table(value, match_id, conditions_digest):
    """Raise TableError unless one match file belongs to the folder it sits in."""
    schema = value.get("schema") if isinstance(value, dict) else None
    if schema in LEGACY_SCHEMAS:
        raise TableError(f"{match_id}: legacy {schema} file without generation conditions")
    if schema != TABLE_SCHEMA:
        raise TableError(f"{match_id}: schema {schema}, expected {TABLE_SCHEMA}")
    if value.get("conditions_digest") != conditions_digest:
        raise TableError(f"{match_id}: built under other conditions than the folder manifest")
    if value.get("match_id") != match_id:
        raise TableError(f"{match_id}: file holds match {value.get('match_id')}")
    for part in ("hits", "contact"):
        if not isinstance(value.get(part), list):
            raise TableError(f"{match_id}: no `{part}` list (every {TABLE_SCHEMA} file has one)")
    for key in TABLE_PARTS:
        for row in value.get(key, ()):
            if row.get("match_id") != match_id:
                raise TableError(f"{match_id}: a {key} row belongs to {row.get('match_id')}")
