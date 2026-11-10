#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Noctalia Themes: apply decorative themes to Noctalia v5, with snapshot rollback."""
import logging
import logging.handlers
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import paths  # noqa: E402
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402
from i18n import _  # noqa: E402
from window import Window  # noqa: E402

APP_ID = "com.billisdead.NoctaliaThemes"
VERSION = "0.1.0"
DONATE_URL = "https://ko-fi.com/billisdead"


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        for name, cb, accels in (("quit", lambda *_a: self.quit(), ["<primary>q"]),
                                 ("about", self._about, []),
                                 ("donate", self._donate, []),
                                 ("preferences", lambda *_a: self._window().open_preferences(), ["<primary>comma"]),
                                 ("save-setup", lambda *_a: self._window().save_setup(), ["<primary>s"]),
                                 ("open-backups", self._open_backups, [])):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            self.set_accels_for_action(f"app.{name}", accels)

    def do_startup(self):
        Adw.Application.do_startup(self)
        # Under bare "hicolor" (no GNOME session) many symbolic icons are missing: use Adwaita for this app only.
        settings = Gtk.Settings.get_default()
        if settings.get_property("gtk-icon-theme-name") == "hicolor":
            settings.set_property("gtk-icon-theme-name", "Adwaita")
        display = Gdk.Display.get_default()
        Gtk.IconTheme.get_for_display(display).add_search_path(str(paths.ROOT / "data" / "icons"))  # run from git
        Gtk.Window.set_default_icon_name(APP_ID)
        css = Gtk.CssProvider()
        css.load_from_string(".drop-zone { border: 2px dashed alpha(currentColor, 0.35); border-radius: 12px;"
                             " padding: 24px 12px; }"
                             " .drop-zone.drop-hover { border-color: @accent_color;"
                             " background: alpha(@accent_color, 0.1); }")
        Gtk.StyleContext.add_provider_for_display(display, css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _window(self):
        return self.get_active_window() or Window(self)

    def do_activate(self):
        self._window().present()

    def _about(self, *_a):
        about = Adw.AboutDialog(application_name=_("Noctalia Themes"), application_icon=APP_ID,
                                version=VERSION, developer_name="billisdead", license_type=Gtk.License.GPL_3_0,
                                comments=_("Decorative themes for Noctalia v5, with guaranteed rollback."))
        about.add_link("billisdead.com", "https://billisdead.com")
        about.add_link(_("Support on Ko-fi"), DONATE_URL)
        about.present(self.get_active_window())

    def _donate(self, *_a):
        # The browser opens the page: the app itself still never touches the network.
        Gtk.UriLauncher.new(DONATE_URL).launch(self.get_active_window(), None, None, None)

    def _open_backups(self, *_a):
        paths.ensure_dir(paths.BACKUPS)
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(str(paths.BACKUPS)))
        launcher.launch(self.get_active_window(), None, None, None)


if __name__ == "__main__":
    paths.ensure_dir(paths.DATA)
    # Audit trail of applies/rollbacks, shown in Preferences > Diagnostic.
    file_log = logging.handlers.RotatingFileHandler(paths.LOG, maxBytes=200_000, backupCount=1)
    file_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger().addHandler(file_log)
    sys.exit(App().run(sys.argv))
