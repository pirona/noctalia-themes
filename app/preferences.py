# SPDX-License-Identifier: GPL-3.0-or-later
"""Preferences dialog: wallpapers, desktop widgets, app behaviour, diagnostics."""
import logging
import subprocess
import threading
import tomllib

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import installer  # noqa: E402
import options  # noqa: E402
import paths  # noqa: E402
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
from i18n import _, ngettext  # noqa: E402

log = logging.getLogger("noctalia-themes")
DEBOUNCE_MS = 400  # push to Noctalia once edits settle, not on every spin-button step
TRANSITION_LABELS = {"fade": _("Fade"), "wipe": _("Wipe"), "disc": _("Disc"), "stripes": _("Stripes"),
                     "zoom": _("Zoom"), "honeycomb": _("Honeycomb"), "vortex": _("Vortex"), "pixel": _("Pixels"),
                     "diamond": _("Diamonds"), "golden": _("Golden spiral"), "melt": _("Melt")}
FILL_LABELS = {"crop": _("Fill (crop)"), "fit": _("Fit"), "center": _("Center"), "stretch": _("Stretch"),
               "repeat": _("Tile"), "span": _("Span across screens")}
MODE_LABELS = {"theme": _("The theme's"), "dark": _("Dark"), "light": _("Light"), "auto": _("Automatic (Noctalia)")}
COLOR_LABELS = {None: _("The theme's"), "primary": _("Primary"), "secondary": _("Secondary"),
                "tertiary": _("Tertiary"), "on_surface": _("Text (neutral)")}
TRISTATE = [_("Like the theme"), _("Yes"), _("No")]


def _combo(title, labels, selected, subtitle=None):
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_selected(selected)
    return row


def _tristate(value):
    return 0 if value is None else (1 if value else 2)


def _from_tristate(index):
    return None if index == 0 else index == 1


class Preferences(Adw.PreferencesDialog):
    def __init__(self, window, theme):
        super().__init__(title=_("Preferences"), search_enabled=True)
        self.window, self.theme = window, theme
        self.opts = options.load()
        self._pending = None
        self._needs_refresh = False
        self.fragment = self._theme_fragment()
        for page in (self._page_wallpapers(), self._page_widgets(), self._page_app(), self._page_diagnostic()):
            self.add(page)

    # --- persistence ----------------------------------------------------

    def _theme_fragment(self):
        src = paths.FRAGMENT if paths.FRAGMENT.exists() else (self.theme["dir"] / "noctalia.toml"
                                                                  if self.theme else None)
        try:
            return tomllib.loads(src.read_text()) if src else {}
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def _set(self, key, value, refresh=False):
        """Save a preference now; push it to Noctalia once edits settle."""
        self.opts[key] = value
        options.save(self.opts)
        self._needs_refresh |= refresh
        if self._pending:
            GLib.source_remove(self._pending)
        self._pending = GLib.timeout_add(DEBOUNCE_MS, self._push)

    def _push(self):
        self._pending = None
        try:
            if self._needs_refresh and installer.current_theme():
                installer.refresh(self.theme["dir"])  # output is baked into the theme fragment
            else:
                installer.write_options()
            self._needs_refresh = False
        except Exception as e:  # report, never crash the dialog
            log.exception("could not apply preferences")
            self.add_toast(Adw.Toast(title=_("Preference saved but not applied: {error}").format(error=e),
                                     timeout=6))
        self.window.refresh()
        return GLib.SOURCE_REMOVE

    # --- pages ----------------------------------------------------------

    def _page_wallpapers(self):
        page = Adw.PreferencesPage(title=_("Wallpapers"), icon_name="image-x-generic-symbolic")
        wall = self.fragment.get("wallpaper", {})
        self._theme_transitions = wall.get("transition") or list(options.TRANSITIONS)
        current = self.opts["transitions"] or self._theme_transitions
        self._syncing = False

        trans = Adw.PreferencesGroup(title=_("Transition effects"),
                                     description=_("Noctalia picks one at random on each wallpaper change."))
        self._trans_rows = {}
        for name in options.TRANSITIONS:
            row = Adw.SwitchRow(title=TRANSITION_LABELS[name], subtitle=name, active=name in current)
            row.connect("notify::active", self._on_transition)
            self._trans_rows[name] = row
            trans.add(row)
        page.add(trans)

        other = Adw.PreferencesGroup(title=_("Rendering"))
        dur = Adw.SpinRow.new_with_range(200, 5000, 100)
        dur.set_title(_("Transition duration"))
        dur.set_subtitle(_("in milliseconds"))
        dur.set_value(self.opts["transition_duration"] or wall.get("transition_duration", 1500))
        dur.connect("notify::value", lambda r, _p: self._set("transition_duration", int(r.get_value())))
        other.add(dur)

        fills = [None, *options.FILL_MODES]
        fill = _combo(_("Fill mode"), [_("The theme's"), *(FILL_LABELS[f] for f in options.FILL_MODES)],
                      fills.index(self.opts["fill_mode"]) if self.opts["fill_mode"] in fills else 0)
        fill.connect("notify::selected", lambda r, _p: self._set("fill_mode", fills[r.get_selected()]))
        other.add(fill)

        reset = Adw.ButtonRow(title=_("Back to the theme's settings"))
        reset.connect("activated", self._reset_wallpaper)
        other.add(reset)
        page.add(other)
        return page

    def _sync_transitions(self, active):
        self._syncing = True  # programmatic changes must not loop back into _on_transition
        for name, row in self._trans_rows.items():
            row.set_active(name in active)
        self._syncing = False

    def _on_transition(self, *_a):
        if self._syncing:
            return
        chosen = [n for n, r in self._trans_rows.items() if r.get_active()]
        if not chosen:  # keep at least one: show what will really be used (the theme's effects)
            self._sync_transitions(self._theme_transitions)
            self.add_toast(Adw.Toast(title=_("At least one effect is needed: the theme's are back."), timeout=4))
        self._set("transitions", chosen or None)

    def _reset_wallpaper(self, *_a):
        for key in ("transitions", "transition_duration", "fill_mode"):
            self.opts[key] = None
        self._sync_transitions(self._theme_transitions)
        self._set("fill_mode", None)
        self.add_toast(Adw.Toast(title=_("The theme's wallpaper settings are back."), timeout=4))

    def _page_widgets(self):
        page = Adw.PreferencesPage(title=_("Widgets"), icon_name="view-grid-symbolic")
        overridden = installer.overridden_by_state()
        if overridden:
            warn = Adw.PreferencesGroup(
                title=_("Some settings are ignored"),
                description=_("Your Noctalia configuration (settings.toml) already sets them and wins: {keys}. "
                              "Change them in Noctalia, or remove the theme and apply it again.")
                .format(keys=", ".join(overridden)))
            page.add(warn)

        shown = Adw.PreferencesGroup(title=_("Display"), description=_("Hiding a widget removes it from the desktop."))
        groups = (self.theme or {}).get("widget_groups") or {
            wid: [wid] for wid in self.fragment.get("desktop_widgets", {}).get("widget", {})}
        hidden = set(self.opts["hidden_widgets"])
        for label, ids in groups.items():
            row = Adw.SwitchRow(title=label, active=not hidden & set(ids))
            row.connect("notify::active", self._on_visibility, ids)
            shown.add(row)
        page.add(shown)

        look = Adw.PreferencesGroup(title=_("Appearance"))
        modes = options.THEME_MODES
        mode = _combo(_("Mode"), [MODE_LABELS[m] for m in modes], modes.index(self.opts["theme_mode"]),
                      _("Dark, light, or let Noctalia decide"))
        mode.connect("notify::selected", lambda r, _p: self._set("theme_mode", modes[r.get_selected()]))
        look.add(mode)
        page.add(look)

        clock = Adw.PreferencesGroup(title=_("Clock"))
        for key, title in (("clock_12h", _("12-hour format")), ("clock_seconds", _("Show seconds"))):
            row = _combo(title, TRISTATE, _tristate(self.opts[key]))
            row.connect("notify::selected", lambda r, _p, k=key: self._set(k, _from_tristate(r.get_selected())))
            clock.add(row)
        colors = list(COLOR_LABELS)
        color = _combo(_("Color"), list(COLOR_LABELS.values()), colors.index(self.opts["clock_color"])
                       if self.opts["clock_color"] in colors else 0)
        color.connect("notify::selected", lambda r, _p: self._set("clock_color", colors[r.get_selected()]))
        clock.add(color)
        page.add(clock)

        player = Adw.PreferencesGroup(title=_("Media player"),
                                      description=_("Title, artist and cover of what is playing."))
        row = _combo(_("Hide when nothing plays"), TRISTATE, _tristate(self.opts["player_hide_when_idle"]))
        row.connect("notify::selected", lambda r, _p: self._set("player_hide_when_idle",
                                                                _from_tristate(r.get_selected())))
        player.add(row)
        page.add(player)
        return page

    def _on_visibility(self, row, _pspec, ids):
        hidden = set(self.opts["hidden_widgets"])
        hidden = hidden - set(ids) if row.get_active() else hidden | set(ids)
        self._set("hidden_widgets", sorted(hidden))

    def _page_app(self):
        page = Adw.PreferencesPage(title=_("App"), icon_name="preferences-system-symbolic")

        behaviour = Adw.PreferencesGroup(title=_("Behavior"))
        confirm = Adw.SwitchRow(title=_("Ask before applying"),
                                subtitle=_("The “Undo” toast is offered either way"),
                                active=self.opts["confirm_apply"])
        confirm.connect("notify::active", lambda r, _p: self._set("confirm_apply", r.get_active()))
        behaviour.add(confirm)
        page.add(behaviour)

        if options.greeter_installed():  # nothing to sync without Noctalia Greeter
            login = Adw.PreferencesGroup(title=_("Login screen"))
            sync = Adw.SwitchRow(title=_("Follow the theme"),
                                 subtitle=_("Noctalia copies the wallpaper, colors and font to Noctalia Greeter"),
                                 active=self.opts["greeter_sync"])
            sync.connect("notify::active", lambda r, _p: self._set("greeter_sync", r.get_active()))
            login.add(sync)
            page.add(login)

        screen = Adw.PreferencesGroup(title=_("Screen"), description=_("Screen the theme's widgets are shown on."))
        outputs = ["", *installer.list_outputs()]
        if self.opts["output"] and self.opts["output"] not in outputs:
            outputs.append(self.opts["output"])  # keep a saved but disconnected screen selectable
        out = _combo(_("Target screen"), [_("Automatic (focused screen)"), *outputs[1:]],
                     outputs.index(self.opts["output"]))
        out.connect("notify::selected", lambda r, _p: self._set("output", outputs[r.get_selected()], refresh=True))
        screen.add(out)
        page.add(screen)

        backups = Adw.PreferencesGroup(
            title=_("Backups"),
            description=_("Nothing is deleted automatically. The active theme's backup is never deleted."))
        keep = Adw.SpinRow.new_with_range(1, 50, 1)
        keep.set_title(_("Backups to keep"))
        keep.set_value(self.opts["max_backups"])
        backups.add(keep)
        self._prune_row = Adw.ActionRow(title="")
        prune = Gtk.Button(label=_("Clean up"), valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        prune.connect("clicked", self._confirm_prune)
        self._prune_row.add_suffix(prune)
        self._prune_button = prune
        backups.add(self._prune_row)
        keep.connect("notify::value", self._on_keep)
        self._update_prune()
        page.add(backups)
        return page

    def _on_keep(self, row, _pspec):
        self.opts["max_backups"] = int(row.get_value())
        options.save(self.opts)
        self._update_prune()

    def _update_prune(self):
        total, extra = len(installer.list_backups()), len(installer.excess_backups(self.opts["max_backups"]))
        self._prune_row.set_title(ngettext("{total} backup, {extra} over the limit",
                                           "{total} backups, {extra} over the limit", total)
                                  .format(total=total, extra=extra))
        self._prune_button.set_sensitive(extra > 0)

    def _confirm_prune(self, *_a):
        doomed = installer.excess_backups(self.opts["max_backups"])
        n = len(doomed)
        dialog = Adw.AlertDialog(heading=ngettext("Delete the oldest backup?", "Delete the {n} oldest backups?", n)
                                 .format(n=n),
                                 body=_("They can no longer be restored. The active theme's backup is kept."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("ok", _("Delete"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "ok" and self._prune(doomed))
        dialog.present(self)

    def _prune(self, doomed):
        for bid in doomed:
            installer.delete_backup(bid)
        self._update_prune()
        self.window.refresh()
        n = len(doomed)
        self.add_toast(Adw.Toast(title=ngettext("{n} backup deleted", "{n} backups deleted", n).format(n=n)))

    def _page_diagnostic(self):
        page = Adw.PreferencesPage(title=_("Diagnostic"), icon_name="utilities-terminal-symbolic")
        self._diag = []
        state = Adw.PreferencesGroup(title=_("State"), description=_("Computing…"))
        self._diag_group = state
        # IPC calls can hang up to their timeout: compute off the UI thread, fill the rows when done.
        threading.Thread(target=lambda: GLib.idle_add(self._fill_diagnostic, self._diagnostic()), daemon=True).start()
        page.add(state)
        actions = Adw.PreferencesGroup()
        copy = Adw.ButtonRow(title=_("Copy the diagnostic"))
        copy.connect("activated", self._copy_diagnostic)
        actions.add(copy)
        page.add(actions)

        logs = Adw.PreferencesGroup(title=_("Log"), description=str(paths.LOG))
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        view.get_buffer().set_text(self._log_tail())
        logs.add(Gtk.Frame(child=view))
        page.add(logs)
        return page

    def _fill_diagnostic(self, diag):
        self._diag = diag
        self._diag_group.set_description(None)
        for title, value in diag:
            row = Adw.ActionRow(title=title, subtitle=value or "—", use_markup=False, subtitle_selectable=True)
            row.set_subtitle_lines(4)
            self._diag_group.add(row)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _run(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return _("unavailable")

    def _diagnostic(self):
        active = installer.current_theme()
        try:
            output = installer.detect_output()
        except ValueError as e:
            output = str(e)
        return [
            ("Noctalia", self._run("noctalia", "--version")),
            (_("Active palette"), self._run("noctalia", "msg", "color-scheme-get")),
            (_("Mode"), self._run("noctalia", "msg", "theme-mode-get")),
            (_("Active theme"), _("{name} (backup {id})").format(name=active["theme"], id=active["id"])
             if active else _("none")),
            (_("Widgets screen"), output),
            (_("Login screen"), (_("follows the theme") if self.opts["greeter_sync"] else _("not synced"))
             if options.greeter_installed() else _("Noctalia Greeter not installed")),
            (_("Settings changed since apply"), ", ".join(installer.changes_since_apply())),
            (_("Preferences overridden by settings.toml"), ", ".join(installer.overridden_by_state())),
            (_("Noctalia config"), str(paths.CONFIG)),
            (_("Noctalia state"), str(paths.STATE)),
            (_("App preferences"), str(paths.SETTINGS)),
            (_("Installed themes and backups"), str(paths.DATA)),
        ]

    @staticmethod
    def _log_tail(lines=20):
        try:
            return "\n".join(paths.LOG.read_text().splitlines()[-lines:]) or _("(empty)")
        except OSError:
            return _("(no log yet)")

    def _copy_diagnostic(self, *_a):
        text = "\n".join(f"{t}: {v}" for t, v in self._diag) + "\n\n" + self._log_tail()
        Gdk.Display.get_default().get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.add_toast(Adw.Toast(title=_("Diagnostic copied")))
