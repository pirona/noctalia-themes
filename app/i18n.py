# SPDX-License-Identifier: GPL-3.0-or-later
"""Translations: English in the code, other languages from po/ (gettext), themes from their [locale.<lang>] table."""
import gettext
import os

import paths

DOMAIN = "noctalia-themes"
_catalog = gettext.translation(DOMAIN, paths.LOCALE, fallback=True)  # no compiled catalog: English
_ = _catalog.gettext
ngettext = _catalog.ngettext


def lang():
    """Two-letter UI language, read from the environment in gettext's order."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "").split(":")[0]
        if value:
            code = value.split("_")[0].split(".")[0].lower()
            return "en" if code in ("c", "posix") else code
    return "en"


def localize(meta):
    """Theme metadata for display: `title` and `description` in the UI language, group labels translated.

    `name` stays as written: backups refer to the theme by it.
    """
    tr = meta.get("locale", {}).get(lang(), {})
    labels = tr.get("widget_groups", {})
    return {**meta, "title": tr.get("name", meta["name"]),
            "description": tr.get("description", meta.get("description", "")),
            "widget_groups": {labels.get(k, k): v for k, v in meta.get("widget_groups", {}).items()}}
