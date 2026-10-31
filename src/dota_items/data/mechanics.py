"""U26 knowledge framework, layer 1: decoding of official raw ability enums.

The hero registry stores Valve's raw_mechanics values opaquely. The decoding table
(knowledge/mechanics/enums-*.json) gives each value a meaning plus example abilities;
this module checks the table against the registry so that wrong examples or new,
unexplained values (e.g. after a patch) fail loudly instead of being guessed.
"""


def _abilities(registry_heroes):
    return {a["name"]: a for h in registry_heroes for a in h["abilities"]}


def load_enums(doc, registry_heroes):
    """Validate the table; return {field: {int value: entry}}."""
    if doc.get("schema") != "mechanics-enums/1":
        raise ValueError("Unsupported mechanics enum schema")
    abilities = _abilities(registry_heroes)
    out = {}
    for field, spec in doc["fields"].items():
        values = {}
        for raw, entry in spec["values"].items():
            value = int(raw)
            if not entry.get("examples"):
                raise ValueError(f"{field}={value}: needs at least one example ability")
            if not isinstance(entry.get("confirmed"), bool):
                raise ValueError(f"{field}={value}: confirmed must be true or false")
            for name in entry["examples"]:
                ability = abilities.get(name)
                if ability is None:
                    raise ValueError(f"{field}={value}: unknown example ability {name}")
                actual = int(ability["raw_mechanics"][field])
                if actual != value:
                    raise ValueError(f"{field}={value}: example {name} has {actual}")
            values[value] = entry
        seen = {int(a["raw_mechanics"][field]) for a in abilities.values()}
        unexplained = sorted(seen - set(values))
        if unexplained:
            raise ValueError(f"{field}: registry values without meaning: {unexplained}")
        out[field] = values
    return out


def decode(enums, field, value):
    """Meaning (zh) of one raw value; raises KeyError for undecoded fields/values."""
    return enums[field][int(value)]["zh"]


def unconfirmed(enums):
    """(field, value) pairs the user has not confirmed yet, for review prompts."""
    return [
        (field, value)
        for field, values in enums.items()
        for value, entry in sorted(values.items())
        if not entry["confirmed"]
    ]
