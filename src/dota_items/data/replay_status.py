"""Display-only position availability; never a gameplay anomaly classifier."""


def position_status(row):
    """Mutually exclusive reason for a withheld current position, not an error count."""
    if row.get("display_issue"):
        return row["display_issue"]
    if row["visibility"] == "hidden":
        return "hidden"
    if row["visibility"] == "unknown":
        return "visibility_unknown"
    if row["life_state"] == 1:
        return "dying"
    if row["life_state"] == 2:
        return "dead"
    if row["life_state"] is None:
        return "state_missing"
    return "available" if row["current_position"] is not None else "position_withheld"
