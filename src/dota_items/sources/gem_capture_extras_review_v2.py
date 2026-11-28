"""Per-second map state that parser v3 does not keep (side file, U154).

One light pass over the demo, separate from state v3 so its files and producer stay as
they are. Per game second:

* creeps     every living lane or siege creep as [team, x, y]
* watchers   every Watcher (lantern) as [x, y, team that holds it or 0]; the holder is the
             entity's `m_nFoWTeam` (its `m_iTeamNum` never changes), found 2026-11-13 by
             watching which fields change over a match
* outposts   every outpost as [x, y, team]
* scan       per side the Scan cooldown end and charges, so a use shows as a change

All positions are cell space like state v3. Omniscient like state v3.
"""

from importlib.metadata import version

from dota_items.sources.gem_capture_creeps import creep_rows

CAPTURE_VERSION = "gem-extras-capture/1"
WATCHER, OUTPOST = "CDOTA_NPC_Lantern", "CDOTA_BaseNPC_Watch_Tower"
SCAN = {
    "radiant_cooldown": "m_pGameRules.m_fGoodRadarCooldown",
    "dire_cooldown": "m_pGameRules.m_fBadRadarCooldown",
    "radiant_charges": "m_pGameRules.m_iGoodRadarCharges",
    "dire_charges": "m_pGameRules.m_iBadRadarCharges",
}


def extras_row(em, position):
    """The watchers, outposts and scan state of one second."""
    watchers, outposts = [], []
    for entity in em.all_active():
        cls = entity.get_class_name()
        if cls not in (WATCHER, OUTPOST):
            continue
        pos = position(entity)
        if not pos:
            continue
        spot = [round(pos[0]), round(pos[1])]
        if cls == WATCHER:
            watchers.append([*spot, entity.get("m_nFoWTeam") or 0])
        else:
            outposts.append([*spot, entity.get("m_iTeamNum")])
    rules = em.find_by_class_name("CDOTAGamerulesProxy")
    scan = {}
    for name, field in SCAN.items():
        value = rules.get(field) if rules is not None else None
        scan[name] = round(value, 1) if isinstance(value, float) else value
    return {"watchers": sorted(watchers), "outposts": sorted(outposts), "scan": scan}


def capture_extras(path, start_time=-90.0):
    """Parse one unpacked .dem; return (header, rows) with one row per game second."""
    if version("gem-dota") != "0.10.0":
        raise ValueError("Extras capture requires the verified gem-dota==0.10.0")
    from gem.extractors._snapshots import _pos
    from gem.parser import ReplayParser

    from dota_items.sources.gem_capture import require_complete_parse

    parser = ReplayParser(str(path))
    rows, last = [], {"second": None}

    def sample(_tick):
        em = parser.entity_manager
        game_time = getattr(parser, "game_time_s", None)
        if em is None or game_time is None or game_time < start_time:
            return
        second = int(game_time // 1)
        if second == last["second"]:
            return
        last["second"] = second
        rows.append({"t": second, "creeps": creep_rows(em, _pos), **extras_row(em, _pos)})

    parser.on_tick_start(sample)
    parser.parse()
    require_complete_parse(parser)
    header = {
        "schema": CAPTURE_VERSION,
        "match_id": parser.match_id,
        "gem_version": version("gem-dota"),
        "seconds": len(rows),
        "omniscient": True,
        "coordinates": "cell space (cell*128+vec), map centre 16384",
        "fields": {
            "creeps": ["team", "x", "y"],
            "watchers": ["x", "y", "holder_team_or_0"],
            "outposts": ["x", "y", "team"],
        },
    }
    return header, rows
