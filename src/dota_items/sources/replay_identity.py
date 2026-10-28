"""Isolated Gem sampling instrumentation; never patches the installed package."""


def entity_evidence(entity):
    """Capture identity and coordinate components from the actual selected entity."""
    return {
        "entity_index": entity.get_index(),
        "entity_serial": entity.get_serial(),
        "class_name": entity.get_class_name(),
        "team": entity.get_int32("m_iTeamNum"),
        "player_id_primary": entity.get_int32("m_nPlayerID"),
        "player_id_secondary": entity.get_int32("m_iPlayerID"),
        "life_state": entity.get_int32("m_lifeState"),
        "cell_x": entity.get_uint32("CBodyComponent.m_cellX"),
        "cell_y": entity.get_uint32("CBodyComponent.m_cellY"),
        "vec_x": entity.get_float32("CBodyComponent.m_vecX"),
        "vec_y": entity.get_float32("CBodyComponent.m_vecY"),
    }


def sample_evidence(extractor, entity, player_id):
    row = entity_evidence(entity)
    canonical = extractor._canonical_hero_entity(player_id)
    row["canonical_for_slot"] = canonical is not None and (
        canonical.get_index(),
        canonical.get_serial(),
    ) == (entity.get_index(), entity.get_serial())
    row["canonical_identity"] = (
        [canonical.get_index(), canonical.get_serial()] if canonical is not None else None
    )
    return row


def instrument_players(source):
    """One exact insertion in a verified private copy; selection math stays unchanged."""
    anchor = "            snap = _build_hero_snapshot(entity, tick, player_id)\n"
    if source.count(anchor) != 1 or "snap.coordinate_evidence" in source:
        raise ValueError("Unsupported Gem sampling source")
    return source.replace(
        anchor,
        anchor
        + "            from dota_items.sources.replay_identity import sample_evidence\n"
        + "            snap.coordinate_evidence = sample_evidence(self, entity, player_id)\n",
        1,
    )


def capture(path):
    """Run only in a fresh process with the instrumented Gem on sys.path."""
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser
    from gem.state.entities import EntityOp

    parser = ReplayParser(path)
    players = PlayerExtractor()
    players.attach(parser)
    landmarks = {}

    def on_entity(entity, op):
        cls = entity.get_class_name()
        if not any(word in cls.lower() for word in ("tower", "barracks", "fort", "fountain")):
            return
        if op.has(EntityOp.DELETED):
            return
        row = entity_evidence(entity)
        names = parser.string_tables.get_by_name("EntityNames")
        name_index = entity.get_int32("m_nameStringableIndex")
        if name_index is None:
            name_index = entity.get_int32("m_nameStringTableIndex")
        item = names.items.get(name_index) if names is not None else None
        row["npc_name"] = item[0] if item else None
        # Preserve incomplete and changed observations rather than filling names/positions.
        key = tuple(
            row[k]
            for k in (
                "entity_index",
                "entity_serial",
                "class_name",
                "team",
                "npc_name",
                "cell_x",
                "cell_y",
                "vec_x",
                "vec_y",
            )
        )
        if key not in landmarks:
            landmarks[key] = {
                **row,
                "first_tick": parser.tick,
                "last_tick": parser.tick,
                "observations": 0,
            }
        landmarks[key]["last_tick"] = parser.tick
        landmarks[key]["observations"] += 1

    parser.on_entity(on_entity)
    parser.parse()
    if parser.parse_error is not None:
        raise ValueError(f"Incomplete parse at tick {parser.truncated_at_tick}")
    rows = []
    for snap in players.snapshots:
        if snap.x is None or snap.y is None:
            continue
        rows.append(
            {
                **snap.coordinate_evidence,
                "player_id": snap.player_id,
                "tick": snap.tick,
                "x": snap.x,
                "y": snap.y,
                "hero_name": snap.npc_name,
            }
        )
    return {
        "match_id": parser.match_id,
        "game_build": parser.game_build,
        "positions": rows,
        "landmarks": list(landmarks.values()),
    }
