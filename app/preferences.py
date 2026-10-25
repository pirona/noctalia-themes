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
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

log = logging.getLogger("noctalia-themes")
DEBOUNCE_MS = 400
TRANSITION_LABELS = {"fade": "Fondu", "wipe": "Balayage", "disc": "Disque", "stripes": "Bandes", "zoom": "Zoom",
                     "honeycomb": "Nid d'abeille", "vortex": "Vortex", "pixel": "Pixels", "diamond": "Losanges",
                     "golden": "Spirale dorée", "melt": "Fonte"}
FILL_LABELS = {"crop": "Remplir (rogner)", "fit": "Ajuster", "center": "Centrer", "stretch": "Étirer",
               "repeat": "Mosaïque", "span": "Étendre sur les écrans"}
MODE_LABELS = {"theme": "Celui du thème", "dark": "Sombre", "light": "Clair", "auto": "Automatique (Noctalia)"}
COLOR_LABELS = {None: "Celle du thème", "primary": "Rose (primaire)", "secondary": "Cyan (secondaire)",
                "tertiary": "Violet (tertiaire)", "on_surface": "Texte (neutre)"}
TRISTATE = ["Comme le thème", "Oui", "Non"]


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
        super().__init__(title="Préférences", search_enabled=True)
        self.window, self.theme = window, theme
        self.opts = options.load()
        self._pending = None
        self._needs_refresh = False
        self.fragment = self._theme_fragment()
        for page in (self._page_wallpapers(), self._page_widgets(), self._page_app(), self._page_diagnostic()):
            self.add(page)

    # --- persistence ----------------------------------------------------

    def _theme_fragment(self):
        src = installer.FRAGMENT if installer.FRAGMENT.exists() else (self.theme["dir"] / "noctalia.toml"
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
            self.add_toast(Adw.Toast(title=f"Préférence enregistrée mais pas appliquée : {e}", timeout=6))
        self.window.refresh()
        return GLib.SOURCE_REMOVE

    # --- pages ----------------------------------------------------------

    def _page_wallpapers(self):
        page = Adw.PreferencesPage(title="Fonds", icon_name="image-x-generic-symbolic")
        wall = self.fragment.get("wallpaper", {})
        self._theme_transitions = wall.get("transition") or list(options.TRANSITIONS)
        current = self.opts["transitions"] or self._theme_transitions
        self._syncing = False

        trans = Adw.PreferencesGroup(title="Effets de transition",
                                     description="Noctalia en tire un au hasard à chaque changement de fond.")
        self._trans_rows = {}
        for name in options.TRANSITIONS:
            row = Adw.SwitchRow(title=TRANSITION_LABELS[name], subtitle=name, active=name in current)
            row.connect("notify::active", self._on_transition)
            self._trans_rows[name] = row
            trans.add(row)
        page.add(trans)

        other = Adw.PreferencesGroup(title="Rendu")
        dur = Adw.SpinRow.new_with_range(200, 5000, 100)
        dur.set_title("Durée de la transition")
        dur.set_subtitle("en millisecondes")
        dur.set_value(self.opts["transition_duration"] or wall.get("transition_duration", 1500))
        dur.connect("notify::value", lambda r, _p: self._set("transition_duration", int(r.get_value())))
        other.add(dur)

        fills = [None, *options.FILL_MODES]
        fill = _combo("Remplissage", ["Celui du thème", *(FILL_LABELS[f] for f in options.FILL_MODES)],
                      fills.index(self.opts["fill_mode"]) if self.opts["fill_mode"] in fills else 0)
        fill.connect("notify::selected", lambda r, _p: self._set("fill_mode", fills[r.get_selected()]))
        other.add(fill)

        reset = Adw.ButtonRow(title="Revenir aux réglages du thème")
        reset.connect("activated", self._reset_wallpaper)
        other.add(reset)
        page.add(other)
        return page

    def _sync_transitions(self, active):
        self._syncing = True  # programmatic changes must not loop back into _on_transition
        for name, row in self._trans_rows.items():
            row.set_active(name in active)
        self._syncing = False

    def _on_transition(self, *_):
        if self._syncing:
            return
        chosen = [n for n, r in self._trans_rows.items() if r.get_active()]
        if not chosen:  # keep at least one: show what will really be used (the theme's effects)
            self._sync_transitions(self._theme_transitions)
            self.add_toast(Adw.Toast(title="Il faut au moins un effet : ceux du thème sont rétablis.", timeout=4))
        self._set("transitions", chosen or None)

    def _reset_wallpaper(self, *_):
        for key in ("transitions", "transition_duration", "fill_mode"):
            self.opts[key] = None
        self._sync_transitions(self._theme_transitions)
        self._set("fill_mode", None)
        self.add_toast(Adw.Toast(title="Réglages des fonds du thème rétablis.", timeout=4))

    def _page_widgets(self):
        page = Adw.PreferencesPage(title="Widgets", icon_name="view-grid-symbolic")
        overridden = installer.overridden_by_state()
        if overridden:
            warn = Adw.PreferencesGroup(
                title="Certains réglages sont ignorés",
                description="Ta configuration Noctalia (settings.toml) les définit déjà et l'emporte : "
                            + ", ".join(overridden)
                            + ". Change-les dans Noctalia ou retire le thème puis ré-applique-le.")
            page.add(warn)

        shown = Adw.PreferencesGroup(title="Affichage", description="Masquer un widget le retire du bureau.")
        groups = (self.theme or {}).get("widget_groups") or {
            wid: [wid] for wid in self.fragment.get("desktop_widgets", {}).get("widget", {})}
        hidden = set(self.opts["hidden_widgets"])
        for label, ids in groups.items():
            row = Adw.SwitchRow(title=label, active=not hidden & set(ids))
            row.connect("notify::active", self._on_visibility, ids)
            shown.add(row)
        page.add(shown)

        look = Adw.PreferencesGroup(title="Apparence")
        modes = options.THEME_MODES
        mode = _combo("Mode", [MODE_LABELS[m] for m in modes], modes.index(self.opts["theme_mode"]),
                      "Sombre, clair, ou laisser Noctalia décider")
        mode.connect("notify::selected", lambda r, _p: self._set("theme_mode", modes[r.get_selected()]))
        look.add(mode)
        page.add(look)

        clock = Adw.PreferencesGroup(title="Horloge")
        for key, title in (("clock_12h", "Format 12 heures"), ("clock_seconds", "Afficher les secondes")):
            row = _combo(title, TRISTATE, _tristate(self.opts[key]))
            row.connect("notify::selected", lambda r, _p, k=key: self._set(k, _from_tristate(r.get_selected())))
            clock.add(row)
        colors = list(COLOR_LABELS)
        color = _combo("Couleur", list(COLOR_LABELS.values()), colors.index(self.opts["clock_color"])
                       if self.opts["clock_color"] in colors else 0)
        color.connect("notify::selected", lambda r, _p: self._set("clock_color", colors[r.get_selected()]))
        clock.add(color)
        page.add(clock)

        player = Adw.PreferencesGroup(title="Lecteur CD",
                                      description="Titre, artiste et pochette de la musique en cours.")
        for key, title in (("player_art_background", "Pochette floutée en fond"),
                           ("player_hide_when_idle", "Masquer quand rien ne joue")):
            row = _combo(title, TRISTATE, _tristate(self.opts[key]))
            row.connect("notify::selected", lambda r, _p, k=key: self._set(k, _from_tristate(r.get_selected())))
            player.add(row)
        page.add(player)
        return page

    def _on_visibility(self, row, _pspec, ids):
        hidden = set(self.opts["hidden_widgets"])
        hidden = hidden - set(ids) if row.get_active() else hidden | set(ids)
        self._set("hidden_widgets", sorted(hidden))

    def _page_app(self):
        page = Adw.PreferencesPage(title="Appli", icon_name="preferences-system-symbolic")

        behaviour = Adw.PreferencesGroup(title="Comportement")
        confirm = Adw.SwitchRow(title="Demander confirmation avant d'appliquer",
                                subtitle="Le toast « Annuler » reste proposé dans tous les cas",
                                active=self.opts["confirm_apply"])
        confirm.connect("notify::active", lambda r, _p: self._set("confirm_apply", r.get_active()))
        behaviour.add(confirm)
        page.add(behaviour)

        screen = Adw.PreferencesGroup(title="Écran", description="Écran sur lequel les widgets du thème s'affichent.")
        outputs = ["", *installer.list_outputs()]
        if self.opts["output"] and self.opts["output"] not in outputs:
            outputs.append(self.opts["output"])  # keep a saved but disconnected screen selectable
        out = _combo("Écran cible", ["Automatique (écran actif)", *outputs[1:]], outputs.index(self.opts["output"]))
        out.connect("notify::selected", lambda r, _p: self._set("output", outputs[r.get_selected()], refresh=True))
        screen.add(out)
        page.add(screen)

        backups = Adw.PreferencesGroup(
            title="Sauvegardes",
            description="Rien n'est supprimé automatiquement. La sauvegarde du thème actif n'est jamais supprimée.")
        keep = Adw.SpinRow.new_with_range(1, 50, 1)
        keep.set_title("Nombre de sauvegardes à conserver")
        keep.set_value(self.opts["max_backups"])
        backups.add(keep)
        self._prune_row = Adw.ActionRow(title="")
        prune = Gtk.Button(label="Faire le ménage", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
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
        self._prune_row.set_title(f"{total} sauvegarde(s), {extra} au-delà de la limite")
        self._prune_button.set_sensitive(extra > 0)

    def _confirm_prune(self, *_):
        doomed = installer.excess_backups(self.opts["max_backups"])
        dialog = Adw.AlertDialog(heading=f"Supprimer les {len(doomed)} sauvegarde(s) les plus anciennes ?",
                                 body="Elles ne pourront plus être restaurées. "
                                      "La sauvegarde du thème actif est conservée.")
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("ok", "Supprimer")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "ok" and self._prune(doomed))
        dialog.present(self)

    def _prune(self, doomed):
        for bid in doomed:
            installer.delete_backup(bid)
        self._update_prune()
        self.window.refresh()
        self.add_toast(Adw.Toast(title=f"{len(doomed)} sauvegarde(s) supprimée(s)"))

    def _page_diagnostic(self):
        page = Adw.PreferencesPage(title="Diagnostic", icon_name="utilities-terminal-symbolic")
        self._diag = []
        state = Adw.PreferencesGroup(title="État", description="Calcul en cours…")
        self._diag_group = state
        # IPC calls can hang up to their timeout: compute off the UI thread, fill the rows when done.
        threading.Thread(target=lambda: GLib.idle_add(self._fill_diagnostic, self._diagnostic()), daemon=True).start()
        page.add(state)
        actions = Adw.PreferencesGroup()
        copy = Adw.ButtonRow(title="Copier le diagnostic")
        copy.connect("activated", self._copy_diagnostic)
        actions.add(copy)
        page.add(actions)

        logs = Adw.PreferencesGroup(title="Journal", description=str(installer.DATA / "app.log"))
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
            return "indisponible"

    def _diagnostic(self):
        active = installer.current_theme()
        try:
            output = installer.detect_output()
        except ValueError as e:
            output = str(e)
        return [
            ("Noctalia", self._run("noctalia", "--version")),
            ("Palette active", self._run("noctalia", "msg", "color-scheme-get")),
            ("Mode", self._run("noctalia", "msg", "theme-mode-get")),
            ("Thème actif", f"{active['theme']} (sauvegarde {active['id']})" if active else "aucun"),
            ("Écran des widgets", output),
            ("Réglages modifiés depuis l'application", ", ".join(installer.changes_since_apply())),
            ("Préférences écrasées par settings.toml", ", ".join(installer.overridden_by_state())),
            ("Config Noctalia", str(installer.CONFIG)),
            ("État Noctalia", str(installer.STATE)),
            ("Préférences de l'appli", str(options.PATH)),
            ("Thèmes installés et sauvegardes", str(installer.DATA)),
        ]

    @staticmethod
    def _log_tail(lines=20):
        try:
            return "\n".join((installer.DATA / "app.log").read_text().splitlines()[-lines:]) or "(vide)"
        except OSError:
            return "(pas encore de journal)"

    def _copy_diagnostic(self, *_):
        text = "\n".join(f"{t} : {v}" for t, v in self._diag) + "\n\n" + self._log_tail()
        Gdk.Display.get_default().get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.add_toast(Adw.Toast(title="Diagnostic copié"))
