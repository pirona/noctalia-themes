# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: themes to apply, one-click removal, backup history."""
import json
import logging
import random
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import installer  # noqa: E402
import options  # noqa: E402
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402
from preferences import Preferences  # noqa: E402

THEMES_ROOT = Path(__file__).resolve().parent.parent / "themes"
SWATCH_ROLES = ("mSurface", "mPrimary", "mSecondary", "mTertiary", "mOnSurface")
log = logging.getLogger("noctalia-themes")


def _when(stamp):
    return datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S").strftime("%d/%m/%Y à %H:%M")


def _swatches(palette_file):
    """Fallback preview: vertical stripes of the palette's key colors."""
    colors = json.loads(palette_file.read_text())["dark"]
    rgb = [tuple(int(colors[r][i:i + 2], 16) / 255 for i in (1, 3, 5)) for r in SWATCH_ROLES]

    def draw(_area, cr, w, h):
        for i, c in enumerate(rgb):
            cr.set_source_rgb(*c)
            cr.rectangle(i * w / len(rgb), 0, w / len(rgb) + 1, h)
            cr.fill()

    area = Gtk.DrawingArea(content_width=96, content_height=54)
    area.set_draw_func(draw)
    return area


def _preview(theme):
    path = theme["dir"] / theme.get("preview", "preview.webp")
    widget = None
    if path.exists():
        try:
            # Synchronous load (async left it blank); Clamp caps the picture's natural width.
            pic = Gtk.Picture(paintable=Gdk.Texture.new_from_filename(str(path)),
                              content_fit=Gtk.ContentFit.COVER, can_shrink=True)
            widget = Adw.Clamp(child=pic, maximum_size=96, tightening_threshold=96)
        except GLib.Error:
            log.warning("preview unreadable, using palette swatches: %s", path)
    widget = widget or _swatches(theme["dir"] / "palette.json")
    frame = Gtk.Frame(child=widget, valign=Gtk.Align.CENTER)
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    return frame


_THUMBS = {}


def _thumbnail(path, width=192, height=108):
    """Small texture for the gallery, cached per path and rebuilt only when the file changes."""
    mtime = path.stat().st_mtime
    cached = _THUMBS.get(path)
    if not cached or cached[0] != mtime:
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), width, height, True)
        _ok, data = pix.save_to_bufferv("png", [], [])  # small PNG round-trip: avoids deprecated pixbuf textures
        cached = _THUMBS[path] = (mtime, Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
    return cached[1]


def _row(title, subtitle):
    row = Adw.ActionRow(title=title, subtitle=subtitle, use_markup=False)
    row.set_subtitle_lines(2)
    return row


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Thèmes Noctalia", default_width=600, default_height=680)

        menu = Gio.Menu()
        menu.append("Sauvegarder mon setup", "app.save-setup")
        menu.append("Préférences", "app.preferences")
        menu.append("Ouvrir le dossier des sauvegardes", "app.open-backups")
        menu.append("À propos", "app.about")
        menu.append("Quitter", "app.quit")
        header = Adw.HeaderBar()
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True,
                                       tooltip_text="Menu principal"))

        self.banner = Adw.Banner(button_label="Retirer le thème")
        self.banner.connect("button-clicked", lambda *_: self._remove())

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                               margin_top=24, margin_bottom=24, margin_start=12, margin_end=12)
        clamp = Adw.Clamp(child=self.content, maximum_size=640)
        self.toasts = Adw.ToastOverlay(child=Gtk.ScrolledWindow(child=clamp, vexpand=True))

        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        view.add_top_bar(self.banner)
        self.set_content(view)

        # Backups may also be created from the CLI: refresh when the window regains focus.
        self.connect("notify::is-active", lambda *_: self.is_active() and self.refresh())
        self.refresh()

    # --- building -------------------------------------------------------

    def refresh(self):
        while child := self.content.get_first_child():
            self.content.remove(child)
        active = installer.current_theme()
        self.banner.set_title(f"« {active['theme']} » est appliqué" if active else "")
        self.banner.set_revealed(active is not None)
        themes = installer.list_themes(THEMES_ROOT)
        self.content.append(self._themes_group(active, themes))
        theme = next((t for t in themes if active and t["name"] == active["theme"]), None)
        walls = installer.wallpapers(theme["dir"]) if theme else []
        if walls:
            self.content.append(self._gallery_group(walls))
        self.content.append(self._backups_group(active))

    def open_preferences(self):
        themes, active = installer.list_themes(THEMES_ROOT), installer.current_theme()
        theme = next((t for t in themes if active and t["name"] == active["theme"]), themes[0] if themes else None)
        Preferences(self, theme).present(self)

    def _gallery_group(self, walls):
        group = Adw.PreferencesGroup(title="Fonds d'écran",
                                     description="Clic sur une vignette : fond posé tout de suite.")
        shuffle = Gtk.Button(icon_name="media-playlist-shuffle-symbolic", tooltip_text="Un fond au hasard",
                             valign=Gtk.Align.CENTER, css_classes=["flat"])
        shuffle.connect("clicked", lambda *_: self._set_wallpaper(random.choice(walls)))
        group.set_header_suffix(shuffle)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, min_children_per_line=2,
                           column_spacing=8, row_spacing=8, homogeneous=True)
        for path in walls:
            try:
                pic = Gtk.Picture(paintable=_thumbnail(path), content_fit=Gtk.ContentFit.COVER, can_shrink=True)
            except GLib.Error:
                continue  # unreadable file: skip it rather than break the window
            pic.set_size_request(160, 90)
            name = path.stem.removeprefix("wall_").replace("-", " ")
            btn = Gtk.Button(child=pic, tooltip_text=name, css_classes=["flat", "card"])
            btn.set_overflow(Gtk.Overflow.HIDDEN)
            btn.connect("clicked", lambda _b, p=path: self._set_wallpaper(p))
            flow.append(btn)
        group.add(flow)
        return group

    def _set_wallpaper(self, path):
        self._run(lambda: installer.set_wallpaper(path), f"Fond : {path.stem.removeprefix('wall_')}")

    def _themes_group(self, active, themes):
        group = Adw.PreferencesGroup(title="Thèmes")
        if not themes:
            group.add(_row("Aucun thème trouvé", str(THEMES_ROOT)))
        for theme in themes:
            row = _row(theme["name"], theme.get("description", ""))
            row.add_prefix(_preview(theme))
            if active and active["theme"] == theme["name"]:
                update = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                                    tooltip_text="Mettre à jour (stickers, palette, widgets) "
                                                 "sans toucher à tes réglages")
                update.connect("clicked", lambda _b, t=theme: self._run(lambda: installer.refresh(t["dir"]),
                                                                       f"« {t['name']} » mis à jour"))
                row.add_suffix(update)
                badge = Gtk.Label(label="Actif", valign=Gtk.Align.CENTER, css_classes=["success", "caption-heading"])
                row.add_suffix(badge)
            else:
                btn = Gtk.Button(label="Appliquer", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
                btn.connect("clicked", lambda _b, t=theme: self._confirm_apply(t))
                row.add_suffix(btn)
            group.add(row)
        return group

    def _backups_group(self, active):
        group = Adw.PreferencesGroup(
            title="Sauvegardes",
            description="Chaque application enregistre d'abord ta configuration Noctalia ; retirer le thème "
                        "la restaure en gardant tes réglages modifiés entre-temps. « Mon setup » (menu) copie "
                        "tout tel quel, thème actif compris.")
        backups = list(reversed(installer.list_backups()))
        if not backups:
            group.add(_row("Aucune sauvegarde pour l'instant", ""))
        for b in backups:
            row = _row(_when(b["date"]), b["label"])
            btn = Gtk.Button(label="Restaurer", valign=Gtk.Align.CENTER, css_classes=["flat"])
            btn.connect("clicked", lambda _b, b=b: self._confirm_restore(b))
            row.add_suffix(btn)
            trash = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                               tooltip_text="Supprimer cette sauvegarde")
            if active and b["id"] == active["id"]:
                trash.set_sensitive(False)
                trash.set_tooltip_text("Seul retour possible pour le thème actif : retire le thème d'abord")
            trash.connect("clicked", lambda _b, b=b: self._confirm_delete(b))
            row.add_suffix(trash)
            group.add(row)
        return group

    # --- actions --------------------------------------------------------

    def _ask(self, heading, body, label, appearance, on_yes):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("ok", label)
        dialog.set_response_appearance("ok", appearance)
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "ok" and on_yes())
        dialog.present(self)

    def _run(self, action, success, undo=None):
        """Run an installer call; on failure the installer has already restored the previous state."""
        try:
            result = action()
        except Exception as e:  # show any failure instead of crashing the UI
            log.exception("operation failed")
            err = Adw.AlertDialog(heading="L'opération a échoué",
                                  body=f"Ta configuration a été laissée telle qu'avant.\n\n{e}")
            err.add_response("close", "Fermer")
            err.present(self)
            self.refresh()
            return
        toast = Adw.Toast(title=success, timeout=8)
        if undo:
            toast.set_button_label("Annuler")
            toast.connect("button-clicked", lambda *_: undo(result))
        self.toasts.add_toast(toast)
        self.refresh()

    @staticmethod
    def _lost_warning():
        """Say what leaving the active theme keeps (your settings) and drops (the theme's own, changed meanwhile)."""
        def bullets(keys):
            more = f"\n… et {len(keys) - 8} autres" if len(keys) > 8 else ""
            return "\n".join(f"• {k}" for k in keys[:8]) + more
        lost, kept = installer.changes_since_apply(), installer.kept_since_apply()
        text = f"\n\nTes réglages modifiés entre-temps sont conservés :\n{bullets(kept)}" if kept else ""
        if lost:
            text += f"\n\nRéglages du thème modifiés entre-temps, qui partent avec lui :\n{bullets(lost)}"
        return text

    def save_setup(self):
        self._run(installer.save_setup, "Setup sauvegardé : tu peux le restaurer depuis les sauvegardes")

    def _confirm_apply(self, theme):
        if not options.load()["confirm_apply"] and not installer.changes_since_apply():
            return self._do_apply(theme)  # still undoable from the toast
        self._ask(f"Appliquer « {theme['name']} » ?",
                  "Ta configuration actuelle est sauvegardée d'abord.\n"
                  "Tes réglages modifiés dans Noctalia pendant que le thème est actif "
                  "sont conservés quand tu le retires ; seuls ceux du thème partent avec lui."
                  + self._lost_warning(),
                  "Appliquer", Adw.ResponseAppearance.SUGGESTED, lambda: self._do_apply(theme))

    def _do_apply(self, theme):
        self._run(lambda: installer.apply(theme["dir"]), f"« {theme['name']} » appliqué",
                  undo=lambda stamp: self._run(lambda: installer.rollback(stamp), "Configuration d'origine restaurée"))

    def _remove(self):
        def remove():
            self._run(lambda: installer.rollback(installer.current()),
                      "Thème retiré, configuration d'origine restaurée")

        if not installer.changes_since_apply():
            return remove()  # nothing of the theme's own to lose: one click, no dialog
        warning = self._lost_warning()
        self._ask("Retirer le thème ?", "Ta configuration d'origine va être restaurée." + warning,
                  "Retirer quand même", Adw.ResponseAppearance.DESTRUCTIVE, remove)

    def _confirm_restore(self, backup):
        if backup.get("kind") == "setup":
            return self._ask(f"Restaurer ton setup du {_when(backup['date'])} ?",
                             "Tout Noctalia revient exactement à ce setup : thème actif, widgets, barre, dock. "
                             "Ta configuration actuelle est remplacée en entier : sauvegarde-la d'abord si tu "
                             "veux pouvoir y revenir.\n\nSi le thème restauré a ses propres polices, redémarre "
                             "Noctalia pour qu'il les voie.",
                             "Restaurer", Adw.ResponseAppearance.DESTRUCTIVE,
                             lambda: self._run(lambda: installer.rollback(backup["id"]), "Setup restauré"))
        self._ask(f"Restaurer la sauvegarde du {_when(backup['date'])} ?",
                  "La configuration actuelle de Noctalia sera remplacée par celle de cette date."
                  + self._lost_warning(),
                  "Restaurer", Adw.ResponseAppearance.DESTRUCTIVE,
                  lambda: self._run(lambda: installer.rollback(backup["id"]), "Sauvegarde restaurée"))

    def _confirm_delete(self, backup):
        self._ask(f"Supprimer la sauvegarde du {_when(backup['date'])} ?",
                  "Elle ne pourra plus être restaurée. Les autres sauvegardes ne sont pas touchées.",
                  "Supprimer", Adw.ResponseAppearance.DESTRUCTIVE,
                  lambda: self._run(lambda: installer.delete_backup(backup["id"]), "Sauvegarde supprimée"))

