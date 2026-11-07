"""Record Claude's reading of Codex-only rows, after seeing Codex's quote (U81). Not blind."""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
AGREE = """0 2 3 5 6 7 8 9 10 11 12 14 15 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34
145 146 147 148 153 155 156 157 158 164_x 166 167 170 177 181 183 184 185 186 187 188 194 195 196
204 205 207 211 212 213 214 219 220 221 222 223 224 226 230 232 233 238 239 241 242 245 248 250
253 254 256 265 267 269 270 271 273 276 277 278 279 280 281 282 283 284 285 286 287 288 290 291
295 296 297 298 299 300 301 302 303 304 305 306 307 308 309 311 312 314 318 319 320 321 322 326
327 329 331 332 333 334 335 336 337 338 339 340 341 342 343 353 354 355 356 357 359 360 362 363
364 366 367 368 369 370 371 372 373 374"""
HOLD = {
    "attack_modifier": range(37, 100),
    "aura": range(100, 145),
    "attribute_regen": [234, 235, 236, 237, 240, 243, 246, 247, 251, 252, 255]
    + list(range(257, 265)),
}


def main():
    data = json.loads((OUT / "comparison.json").read_text(encoding="utf-8"))
    rows = sorted(data["buckets"]["new_codex_only"], key=lambda x: x["mechanism"])
    agree = {int(token) for token in AGREE.split() if not token.endswith("_x")}
    held = {index: name for name, group in HOLD.items() for index in group}
    result = {"agree": [], "hold": {name: [] for name in HOLD}, "disagree": []}
    for index, row in enumerate(rows):
        if index in agree:
            result["agree"].append(row)
        elif index in held:
            result["hold"][held[index]].append(row)
        else:
            result["disagree"].append(row)
    (OUT / "triage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        len(rows),
        len(result["agree"]),
        {k: len(v) for k, v in result["hold"].items()},
        len(result["disagree"]),
    )


if __name__ == "__main__":
    main()
