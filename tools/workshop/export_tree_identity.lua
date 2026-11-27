-- Read-only helper for an existing, pristine Tools session BEFORE tree clearing.
-- Returns a function. The caller must supply the exact patch and client build
-- from their console version output; these are DECLARED, not measured here.
-- Never launch a match, regrow/destroy trees or modify the existing exporter.
return function(exact_patch, client_build)
    assert(IsServer() and IsInToolsMode(), "Requires server-side Workshop Tools")
    assert(exact_patch == "7.42", "Exact 7.42 required; letter patches need review")
    assert(type(client_build) == "number" and client_build > 0
        and client_build == math.floor(client_build), "Explicit client build required")
    assert(GetMapName() == "dota", "Original dota map required")
    assert(type(GetTreeIdForEntityIndex) == "function"
        and type(GetEntityIndexForTreeId) == "function", "Native identity API unavailable")
    local trees = Entities:FindAllByClassname("ent_dota_tree")
    assert(#trees > 0, "No static tree entities")
    local rows, ids = {}, {}
    -- Validate everything before emitting the completion-framed record stream.
    for _, tree in ipairs(trees) do
        local entity = tree:entindex()
        local id = GetTreeIdForEntityIndex(entity)
        local back = GetEntityIndexForTreeId(id)
        assert(id >= 0 and id == math.floor(id) and back == entity and not ids[id],
            "Native tree identity is ambiguous")
        ids[id] = true
        local p = tree:GetAbsOrigin()
        rows[#rows + 1] = string.format(
            "DOTA_TREE_IDENTITY_ROW\t%d\t%d\t%d\t%.17g\t%.17g\t%.17g",
            id, entity, back, p.x, p.y, p.z)
    end
    print(string.format("DOTA_TREE_IDENTITY_BEGIN\t1\t%s\t%d\tdota",
        exact_patch, client_build))
    for _, row in ipairs(rows) do print(row) end
    print("DOTA_TREE_IDENTITY_END\t" .. #rows)
end
