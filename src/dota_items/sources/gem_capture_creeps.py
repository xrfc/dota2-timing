"""Per-second positions of every lane creep (side file to parser v3, U153).

Parser v3 keeps only the front of each wave (`world.lane_fronts`). The vision
approximation needs every creep, because each one gives its team sight. To leave the
state-v3 files and their producer untouched, this is a separate light pass over the demo
that writes nothing but the creeps: per second `[team, x, y]` of every living lane or
siege creep, in the same cell-space coordinates as state v3. Omniscient like state v3.
"""

from importlib.metadata import version

from dota_items.sources.gem_capture_v3 import LANE_CREEPS

CAPTURE_VERSION = "gem-creep-capture/1"


def creep_rows(em, position):
    """[[team, x, y], ...] of the living lane creeps, sorted."""
    result = []
    for entity in em.all_active():
        if entity.get_class_name() in LANE_CREEPS and entity.get("m_lifeState") == 0:
            pos = position(entity)
            if pos:
                result.append([entity.get("m_iTeamNum"), round(pos[0]), round(pos[1])])
    return sorted(result)


def capture_creeps(path, start_time=-90.0):
    """Parse one unpacked .dem; return (header, rows) with one row per game second."""
    if version("gem-dota") != "0.10.0":
        raise ValueError("Creep capture requires the verified gem-dota==0.10.0")
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
        rows.append({"t": second, "creeps": creep_rows(em, _pos)})

    parser.on_tick_start(sample)
    parser.parse()
    require_complete_parse(parser)
    header = {
        "schema": CAPTURE_VERSION,
        "gem_version": version("gem-dota"),
        "seconds": len(rows),
        "omniscient": True,
        "coordinates": "cell space (cell*128+vec), map centre 16384",
        "fields": ["team", "x", "y"],
    }
    return header, rows
