"""Opt-in build-first parser composition; never patches Gem or historical artifacts."""

import re

VERSION = "decision-build-first/1"
SUPPORTED_BUILD = 6965


def server_build(message):
    """Use the pinned Gem convention, rejecting unknown/ambiguous build strings."""
    matches = re.findall(r"/dota_v(\d+)/", getattr(message, "game_dir", ""))
    if len(matches) != 1 or int(matches[0]) <= 0:
        raise ValueError("Missing or ambiguous ServerInfo game build")
    return int(matches[0])


def build_first_parser(base):
    """Return a local subclass. Caller must hash-pin and isolate the base import.

    This deliberately supports only the two audited build-6965 recordings. It
    does not guess a build for schema-first streams, change any global function,
    or multiply values decoded by an earlier producer.
    """

    class BuildFirstParser(base):
        def _on_server_info(self, message):
            build = server_build(message)
            if build != SUPPORTED_BUILD:
                raise ValueError("Unaudited ServerInfo game build")
            previous = getattr(self, "schema_game_build", None)
            if previous is not None and previous != build:
                raise ValueError("ServerInfo changed after schema construction")
            # The base caches ServerInfo before creating its entity manager.
            # Set the build first so parse_send_tables selects modern decoders.
            self.game_build = build
            super()._on_server_info(message)
            if self.game_build != build:
                raise ValueError("Parser and ServerInfo build mismatch")

        def _on_send_tables(self, data):
            pending = getattr(self, "_pending_server_info", None)
            if pending is None or self.entity_manager is not None:
                raise ValueError("Expected initial schema after pending ServerInfo")
            build = server_build(pending)
            if build != SUPPORTED_BUILD or self.game_build != build:
                raise ValueError("Schema requires verified build before decoder construction")
            self.schema_game_build = build
            super()._on_send_tables(data)
            if self.game_build != build:
                raise ValueError("Build drift during schema construction")

    return BuildFirstParser
