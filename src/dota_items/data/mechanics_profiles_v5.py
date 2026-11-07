"""Profile pages with the official wording "无视减益免疫" (U126).

`mechanics_profiles.render_markdown` writes the old label "穿透减益免疫"; it stays unchanged
so earlier derived layers replay byte for byte. New layers render through this module.
"""

from dota_items.data import mechanics_profiles as v1

OLD, NEW = "穿透减益免疫", "无视减益免疫"


def render_markdown(profile):
    return v1.render_markdown(profile).replace(OLD, NEW)
