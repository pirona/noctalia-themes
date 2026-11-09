# SPDX-License-Identifier: GPL-3.0-or-later
"""App preferences, and their translation into a Noctalia config fragment layered over the theme's."""
import json
import re
import shutil
from pathlib import Path

import paths

PATH = paths.SETTINGS

TRANSITIONS = ["fade", "wipe", "disc", "stripes", "zoom", "honeycomb", "vortex", "pixel", "diamond", "golden", "melt"]
FILL_MODES = ["crop", "fit", "center", "stretch", "repeat", "span"]
THEME_MODES = ["theme", "dark", "light", "auto"]  # "theme" = keep the theme's own value
CLOCK_COLORS = ["primary", "secondary", "tertiary", "on_surface"]

# Desktop widgets of the plugin shipped with the app (plugins/theme-widgets)
PLAYER, CLOCK = "billisdead/theme-widgets:player", "billisdead/theme-widgets:clock"

# None means "don't override, keep the theme's value".
DEFAULTS = {
    "transitions": None, "transition_duration": None, "fill_mode": None,
    "theme_mode": "theme",
    "hidden_widgets": [],
    "clock_12h": None, "clock_seconds": None, "clock_color": None,
    "player_hide_when_idle": None,
    "max_backups": 10, "output": "", "confirm_apply": True,
    "greeter_sync": True,
}


def _tri(v):
    return v is None or isinstance(v, bool)


# A hand-edited or future settings.json must never stop the app from opening: bad values fall back to defaults.
VALID = {
    "transitions": lambda v: v is None or (isinstance(v, list) and v and set(v) <= set(TRANSITIONS)),
    "transition_duration": lambda v: v is None or (type(v) is int and 200 <= v <= 5000),
    "fill_mode": lambda v: v is None or v in FILL_MODES,
    "theme_mode": lambda v: v in THEME_MODES,
    "hidden_widgets": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "clock_12h": _tri, "clock_seconds": _tri,
    "clock_color": lambda v: v is None or v in CLOCK_COLORS,
    "player_hide_when_idle": _tri,
    "max_backups": lambda v: type(v) is int and 1 <= v <= 50,
    "output": lambda v: isinstance(v, str),
    "confirm_apply": lambda v: isinstance(v, bool),
    "greeter_sync": lambda v: isinstance(v, bool),
}


def load():
    try:
        saved = json.loads(PATH.read_text())
        saved = saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        saved = {}
    return {k: saved[k] if k in saved and VALID[k](saved[k]) else d for k, d in DEFAULTS.items()}


def save(opts):
    paths.ensure_dir(PATH.parent)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(opts, indent=2, ensure_ascii=False))
    tmp.replace(PATH)


def patch_clock(fmt, hour12=None, seconds=None):
    """Adjust the theme's clock format in place, keeping anything else it shows (date, weekday, text)."""
    if seconds is True and "%S" not in fmt:
        fmt = fmt.replace("%M", "%M:%S", 1)
    elif seconds is False:
        fmt = fmt.replace(":%S", "")
    if hour12 is True:
        fmt = fmt.replace("%H", "%I")
        if "%p" not in fmt:
            last = "%S" if "%S" in fmt else "%M"
            fmt = fmt.replace(last, last + " %p", 1)
    elif hour12 is False:
        fmt = fmt.replace("%I", "%H").replace(" %p", "").replace("%p", "")
    return fmt


def greeter_installed():
    return shutil.which("noctalia-greeter") is not None


def overrides(fragment, opts, greeter=False, login=False):
    """Nested dict of the config keys the preferences change, given the theme's parsed fragment.

    `login`: the theme has its own login wallpaper, synced by the app; auto_sync would push the desktop one.
    """
    out = {}
    if greeter and opts["greeter_sync"]:
        out["shell"] = {"greeter_sync": {"auto_sync": not login}}
    wall = {k: v for k, v in (("transition", opts["transitions"]),
                              ("transition_duration", opts["transition_duration"]),
                              ("fill_mode", opts["fill_mode"])) if v is not None}
    if wall:
        out["wallpaper"] = wall
    if opts["theme_mode"] != "theme":
        out["theme"] = {"mode": opts["theme_mode"], "shell_mode": opts["theme_mode"]}

    dw = fragment.get("desktop_widgets", {})
    widgets, settings = dw.get("widget", {}), {}
    for wid, w in widgets.items():
        s = {}
        if w.get("type") in ("clock", CLOCK):
            base = w.get("settings", {}).get("format", "{:%H:%M}")
            fmt = patch_clock(base, opts["clock_12h"], opts["clock_seconds"])
            if fmt != base:
                s["format"] = fmt
            if opts["clock_color"]:
                s["color"] = opts["clock_color"]
        elif w.get("type") in ("media_player", PLAYER) and opts["player_hide_when_idle"] is not None:
            s["hide_when_no_media" if w["type"] == "media_player" else "hide_when_idle"] = opts["player_hide_when_idle"]
        if s:
            settings[wid] = {"settings": s}
    hidden = set(opts["hidden_widgets"])
    for wid in hidden & set(widgets):  # belt and braces: widget_order is authoritative, `enabled` is documented too
        settings.setdefault(wid, {})["enabled"] = False
    if settings or hidden & set(widgets):
        out["desktop_widgets"] = {}
        if hidden & set(widgets):
            out["desktop_widgets"]["widget_order"] = [w for w in dw.get("widget_order", widgets) if w not in hidden]
        if settings:
            out["desktop_widgets"]["widget"] = settings
    return out


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)  # JSON string escaping is valid TOML
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):  # a table inside a list (e.g. [[bar.default.capsule_group]]): inline table
        return "{" + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + "}"
    raise TypeError(f"unsupported TOML value: {v!r}")


def _key(k):
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k)  # quote anything that is not a bare key


def dump(table, prefix=()):
    """Minimal TOML writer for the value types overrides() produces."""
    leaves = [f"{_key(k)} = {_value(v)}\n" for k, v in table.items() if not isinstance(v, dict)]
    out = (f"\n[{'.'.join(_key(k) for k in prefix)}]\n" if prefix and leaves else "") + "".join(leaves)
    for k, v in table.items():
        if isinstance(v, dict):
            out += dump(v, prefix + (k,))
    return out


if __name__ == "__main__":
    import tomllib
    frag = {"desktop_widgets": {"widget_order": ["c", "p", "d"], "widget": {
        "c": {"type": "clock", "settings": {"format": "{:%H:%M}"}},
        "p": {"type": PLAYER}, "d": {"type": "sticker"}, "k": {"type": CLOCK, "settings": {"format": "{:%H:%M}"}}}}}
    o = {**DEFAULTS, "clock_12h": True, "hidden_widgets": ["d"], "transitions": ["melt"], "theme_mode": "dark",
         "player_hide_when_idle": True}
    text = dump(overrides(frag, o))
    back = tomllib.loads(text)
    assert back["desktop_widgets"]["widget_order"] == ["c", "p"]
    assert back["desktop_widgets"]["widget"]["c"]["settings"]["format"] == "{:%I:%M %p}"
    assert back["desktop_widgets"]["widget"]["k"]["settings"]["format"] == "{:%I:%M %p}"  # the plugin clock too
    assert back["desktop_widgets"]["widget"]["p"]["settings"]["hide_when_idle"] is True
    assert back["wallpaper"]["transition"] == ["melt"] and back["theme"]["mode"] == "dark"
    assert overrides(frag, DEFAULTS) == {}  # defaults change nothing
    assert tomllib.loads(dump(overrides(frag, DEFAULTS, greeter=True)))["shell"]["greeter_sync"]["auto_sync"]
    login = tomllib.loads(dump(overrides(frag, DEFAULTS, True, login=True)))
    assert login["shell"]["greeter_sync"]["auto_sync"] is False
    assert "shell" not in overrides(frag, {**DEFAULTS, "greeter_sync": False}, greeter=True)
    assert back["desktop_widgets"]["widget"]["d"]["enabled"] is False
    assert patch_clock("{:%a %d %b  %H:%M}", seconds=True) == "{:%a %d %b  %H:%M:%S}"  # date kept
    assert patch_clock("{:%H:%M:%S}", hour12=True) == "{:%I:%M:%S %p}"
    assert patch_clock("{:%I:%M %p}", hour12=False) == "{:%H:%M}"
    odd = {"desktop_widgets": {"widget": {"my clock.v2": {"type": "clock", "settings": {"format": "{:%H:%M}"}}}}}
    assert "my clock.v2" in tomllib.loads(dump(overrides(odd, {**DEFAULTS, "clock_seconds": True})))[
        "desktop_widgets"]["widget"]
    groups = {"bar": {"default": {"capsule_group": [{"id": "g1", "members": ["a", "b"], "padding": 6.0}]}}}
    assert tomllib.loads(dump(groups)) == groups  # array of tables survives as inline tables
    import tempfile
    PATH = Path(tempfile.mkdtemp()) / "settings.json"
    PATH.write_text('{"theme_mode": "Dark", "max_backups": "10", "clock_12h": true}')
    loaded = load()
    assert loaded["theme_mode"] == "theme" and loaded["max_backups"] == 10 and loaded["clock_12h"] is True
    print("options OK")
