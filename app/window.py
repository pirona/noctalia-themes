# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: themes to apply, one-click removal, wallpaper gallery, backup history."""
import json
import logging
import random
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import installer  # noqa: E402
import options  # noqa: E402
import package  # noqa: E402
import paths  # noqa: E402
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402
from i18n import _, ngettext  # noqa: E402
from preferences import Preferences  # noqa: E402

GLUE_DEBOUNCE_MS = 300  # Noctalia may write settings.toml several times per drag
SWATCH_ROLES = ("mSurface", "mPrimary", "mSecondary", "mTertiary", "mOnSurface")
log = logging.getLogger("noctalia-themes")


def _when(stamp):
    # Translators: strftime format of a backup date
    return datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S").strftime(_("%Y-%m-%d at %H:%M"))


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
        super().__init__(application=app, title=_("Noctalia Themes"), default_width=600, default_height=680)

        menu = Gio.Menu()
        menu.append(_("Save my setup"), "app.save-setup")
        menu.append(_("Preferences"), "app.preferences")
        menu.append(_("Open the backups folder"), "app.open-backups")
        menu.append(_("Support on Ko-fi ☕"), "app.donate")
        menu.append(_("About"), "app.about")
        menu.append(_("Quit"), "app.quit")
        header = Adw.HeaderBar()
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True,
                                       tooltip_text=_("Main menu")))

        self.banner = Adw.Banner(button_label=_("Remove the theme"))
        self.banner.connect("button-clicked", lambda *_a: self._remove())

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                               margin_top=24, margin_bottom=24, margin_start=12, margin_end=12)
        clamp = Adw.Clamp(child=self.content, maximum_size=640)
        self.toasts = Adw.ToastOverlay(child=Gtk.ScrolledWindow(child=clamp, vexpand=True))

        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        view.add_top_bar(self.banner)
        self.set_content(view)

        # Backups may also be created from the CLI: refresh when the window regains focus.
        self.connect("notify::is-active", lambda *_a: self.is_active() and (self._glue(), self.refresh()))
        # Noctalia saves its state when the widget editor closes: re-glue widget groups then.
        self._glue_pending = None
        self._state_monitor = Gio.File.new_for_path(str(paths.STATE)).monitor_file(Gio.FileMonitorFlags.NONE)
        self._state_monitor.connect("changed", lambda *_a: self._schedule_glue())
        self.refresh()

    def _schedule_glue(self):
        if self._glue_pending:
            GLib.source_remove(self._glue_pending)
        self._glue_pending = GLib.timeout_add(GLUE_DEBOUNCE_MS, self._glue)

    def _glue(self):
        self._glue_pending = None
        try:
            installer.heal()  # a stale rewrite by Noctalia first, or the glue would move the wrong widgets
            installer.glue_groups()
        except Exception:  # never let a bad state file break the window
            log.exception("could not heal or glue widgets")
        return GLib.SOURCE_REMOVE

    # --- building -------------------------------------------------------

    def refresh(self):
        while child := self.content.get_first_child():
            self.content.remove(child)
        active = installer.current_theme()
        themes = installer.list_themes()
        theme = next((t for t in themes if active and t["name"] == active["theme"]), None)
        name = theme["title"] if theme else active["theme"] if active else ""
        self.banner.set_title(_("“{name}” is applied").format(name=name) if active else "")
        self.banner.set_revealed(active is not None)
        self.content.append(self._themes_group(active, themes))
        walls = installer.wallpapers(theme["dir"]) if theme else []
        if walls:
            self.content.append(self._gallery_group(walls))
        self.content.append(self._backups_group(active))

    def open_preferences(self):
        themes, active = installer.list_themes(), installer.current_theme()
        theme = next((t for t in themes if active and t["name"] == active["theme"]), themes[0] if themes else None)
        Preferences(self, theme).present(self)

    def _gallery_group(self, walls):
        group = Adw.PreferencesGroup(title=_("Wallpapers"),
                                     description=_("Click a thumbnail to set it as wallpaper right away."))
        shuffle = Gtk.Button(icon_name="media-playlist-shuffle-symbolic", tooltip_text=_("A random wallpaper"),
                             valign=Gtk.Align.CENTER, css_classes=["flat"])
        shuffle.connect("clicked", lambda *_a: self._set_wallpaper(random.choice(walls)))
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
        self._run(lambda: installer.set_wallpaper(path),
                  _("Wallpaper: {name}").format(name=path.stem.removeprefix("wall_")))

    def _themes_group(self, active, themes):
        group = Adw.PreferencesGroup(title=_("Themes"))
        if not themes:
            group.add(_row(_("No theme found"), str(paths.THEMES)))
        for theme in themes:
            row = _row(theme["title"], theme["description"])
            row.add_prefix(_preview(theme))
            if active and active["theme"] == theme["name"]:
                update = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                                    tooltip_text=_("Update (stickers, palette, widgets) without touching "
                                                   "your settings"))
                update.connect("clicked", lambda _b, t=theme: self._run(
                    lambda: installer.refresh(t["dir"]), _("“{name}” updated").format(name=t["title"])))
                row.add_suffix(update)
                row.add_suffix(Gtk.Label(label=_("Active"), valign=Gtk.Align.CENTER,
                                         css_classes=["success", "caption-heading"]))
            else:
                if theme["imported"]:
                    trash = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                                       tooltip_text=_("Remove this imported theme"))
                    trash.connect("clicked", lambda _b, t=theme: self._confirm_forget(t))
                    row.add_suffix(trash)
                btn = Gtk.Button(label=_("Apply"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
                btn.connect("clicked", lambda _b, t=theme: self._confirm_apply(t))
                row.add_suffix(btn)
            if theme["imported"]:
                row.add_prefix(Gtk.Label(label=_("Imported"), valign=Gtk.Align.CENTER, css_classes=["dim-label",
                                                                                                    "caption"]))
            group.add(row)
        group.add(self._drop_zone())
        return group

    def _drop_zone(self):
        """Dashed field: drop a theme .zip on it, or click it to pick one."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
        box.append(Gtk.Image(icon_name="document-open-symbolic", pixel_size=32, css_classes=["dim-label"]))
        box.append(Gtk.Label(label=_("Drop a theme .zip here, or click to choose one"), wrap=True,
                             justify=Gtk.Justification.CENTER))
        zone = Gtk.Button(child=box, css_classes=["drop-zone", "flat"], margin_top=12,
                          tooltip_text=_("Add a theme package (.zip)"))
        zone.connect("clicked", lambda *_a: self._choose_zip())
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("enter", lambda *_a: zone.add_css_class("drop-hover") or Gdk.DragAction.COPY)
        target.connect("leave", lambda *_a: zone.remove_css_class("drop-hover"))
        target.connect("drop", self._on_drop)
        zone.add_controller(target)
        return zone

    def _on_drop(self, _target, files, _x, _y):
        paths_ = [f.get_path() for f in files.get_files() if f.get_path()]
        if len(paths_) != 1:
            self.toasts.add_toast(Adw.Toast(title=_("Drop one theme .zip at a time.")))
            return False
        GLib.idle_add(self._import, paths_[0])  # after the drop returns: the dialog must not block the drag
        return True

    def _choose_zip(self):
        zips = Gtk.FileFilter(name=_("Theme packages (.zip)"))
        zips.add_suffix("zip")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(zips)
        dialog = Gtk.FileDialog(title=_("Add a theme"), filters=filters, default_filter=zips)

        def done(d, result):
            try:
                self._import(d.open_finish(result).get_path())
            except GLib.Error:
                pass  # cancelled

        dialog.open(self, None, done)

    def _import(self, path):
        try:
            folder, meta = package.read_zip(path)
        except ValueError as e:
            self._fail(_("This file is not a valid theme"), str(e))
            return GLib.SOURCE_REMOVE
        name = meta.get("name", folder)

        def do():
            self._run(lambda: package.import_zip(path), _("“{name}” added: apply it from the list").format(name=name))

        old = package.existing(folder)
        if old:
            self._ask(_("Replace “{name}”?").format(name=name),
                      _("Installed version: {old}. Version in the file: {new}.").format(
                          old=old.get("version", "?"), new=meta.get("version", "?")),
                      _("Replace"), Adw.ResponseAppearance.SUGGESTED, do)
        else:
            do()
        return GLib.SOURCE_REMOVE

    def _confirm_forget(self, theme):
        self._ask(_("Remove “{name}”?").format(name=theme["title"]),
                  _("The imported theme leaves the list. Your backups are kept; import its .zip again to get it back."),
                  _("Remove"), Adw.ResponseAppearance.DESTRUCTIVE,
                  lambda: self._run(lambda: package.remove(theme["dir"].name),
                                    _("“{name}” removed").format(name=theme["title"])))

    def _backups_group(self, active):
        group = Adw.PreferencesGroup(
            title=_("Backups"),
            description=_("Every apply first saves your Noctalia configuration; removing the theme restores it "
                          "and keeps the settings you changed meanwhile. “Save my setup” (menu) copies "
                          "everything as is, active theme and wallpaper included."))
        backups = list(reversed(installer.list_backups()))
        if not backups:
            group.add(_row(_("No backup yet"), ""))
        for b in backups:
            row = _row(_when(b["date"]), b["label"])
            btn = Gtk.Button(label=_("Restore"), valign=Gtk.Align.CENTER, css_classes=["flat"])
            btn.connect("clicked", lambda _b, b=b: self._confirm_restore(b))
            row.add_suffix(btn)
            trash = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                               tooltip_text=_("Delete this backup"))
            if active and b["id"] == active["id"]:
                trash.set_sensitive(False)
                trash.set_tooltip_text(_("Only way back from the active theme: remove the theme first"))
            trash.connect("clicked", lambda _b, b=b: self._confirm_delete(b))
            row.add_suffix(trash)
            group.add(row)
        return group

    # --- actions --------------------------------------------------------

    def _ask(self, heading, body, label, appearance, on_yes):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", _("Cancel"))
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
            self._fail(_("The operation failed"), _("Your configuration was left as it was.") + f"\n\n{e}")
            self.refresh()
            return
        toast = Adw.Toast(title=success, timeout=8)
        if undo:
            toast.set_button_label(_("Undo"))
            toast.connect("button-clicked", lambda *_a: undo(result))
        self.toasts.add_toast(toast)
        self.refresh()

    def _fail(self, heading, body):
        err = Adw.AlertDialog(heading=heading, body=body)
        err.add_response("close", _("Close"))
        err.present(self)

    @staticmethod
    def _lost_warning():
        """Say what leaving the active theme keeps (your settings) and drops (the theme's own, changed meanwhile)."""
        def bullets(keys):
            n = len(keys) - 8
            more = "\n" + ngettext("… and {n} more", "… and {n} more", n).format(n=n) if n > 0 else ""
            return "\n".join(f"• {k}" for k in keys[:8]) + more
        lost, kept = installer.changes_since_apply(), installer.kept_since_apply()
        text = "\n\n" + _("Your settings changed meanwhile are kept:") + f"\n{bullets(kept)}" if kept else ""
        if lost:
            text += "\n\n" + _("Theme settings changed meanwhile, which leave with it:") + f"\n{bullets(lost)}"
        return text

    def save_setup(self):
        self._run(installer.save_setup, _("Setup saved: you can restore it from the backups"))

    def _confirm_apply(self, theme):
        if not options.load()["confirm_apply"] and not installer.changes_since_apply():
            return self._do_apply(theme)  # still undoable from the toast
        self._ask(_("Apply “{name}”?").format(name=theme["title"]),
                  _("Your current configuration is saved first.\nSettings you change in Noctalia while the "
                    "theme is active are kept when you remove it; only the theme's own leave with it.")
                  + self._lost_warning(),
                  _("Apply"), Adw.ResponseAppearance.SUGGESTED, lambda: self._do_apply(theme))

    def _do_apply(self, theme):
        self._run(lambda: installer.apply(theme["dir"]), _("“{name}” applied").format(name=theme["title"]),
                  undo=lambda stamp: self._run(lambda: installer.rollback(stamp),
                                               _("Original configuration restored")))

    def _remove(self):
        def remove():
            self._run(lambda: installer.rollback(installer.current()),
                      _("Theme removed, original configuration restored"))

        if not installer.changes_since_apply():
            return remove()  # nothing of the theme's own to lose: one click, no dialog
        self._ask(_("Remove the theme?"), _("Your original configuration will be restored.") + self._lost_warning(),
                  _("Remove anyway"), Adw.ResponseAppearance.DESTRUCTIVE, remove)

    def _confirm_restore(self, backup):
        when = _when(backup["date"])
        if backup.get("kind") == "setup":
            return self._ask(_("Restore your setup from {date}?").format(date=when),
                             _("All of Noctalia goes back exactly to this setup: active theme, widgets, bar, dock, "
                               "wallpaper. Your current configuration is replaced entirely: save it first if you "
                               "want to come back to it.\n\nIf the restored theme has its own fonts, restart "
                               "Noctalia so it sees them."),
                             _("Restore"), Adw.ResponseAppearance.DESTRUCTIVE,
                             lambda: self._run(lambda: installer.rollback(backup["id"]), _("Setup restored")))
        self._ask(_("Restore the backup from {date}?").format(date=when),
                  _("Noctalia's current configuration will be replaced by the one from that date.")
                  + self._lost_warning(),
                  _("Restore"), Adw.ResponseAppearance.DESTRUCTIVE,
                  lambda: self._run(lambda: installer.rollback(backup["id"]), _("Backup restored")))

    def _confirm_delete(self, backup):
        self._ask(_("Delete the backup from {date}?").format(date=_when(backup["date"])),
                  _("It can no longer be restored. Other backups are not touched."),
                  _("Delete"), Adw.ResponseAppearance.DESTRUCTIVE,
                  lambda: self._run(lambda: installer.delete_backup(backup["id"]), _("Backup deleted")))
