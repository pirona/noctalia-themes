#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Noctalia Themes: apply decorative themes to Noctalia v5, with snapshot rollback."""
import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import installer  # noqa: E402
from gi.repository import Adw, Gio, Gtk  # noqa: E402
from window import Window  # noqa: E402

APP_ID = "fr.gyozamancave.NoctaliaThemes"
VERSION = "0.1.0"


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        for name, cb, accels in (("quit", lambda *_: self.quit(), ["<primary>q"]),
                                 ("about", self._about, []),
                                 ("open-backups", self._open_backups, [])):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            self.set_accels_for_action(f"app.{name}", accels)

    def do_activate(self):
        (self.get_active_window() or Window(self)).present()

    def _about(self, *_):
        Adw.AboutDialog(application_name="Thèmes Noctalia", application_icon="preferences-desktop-theme",
                        version=VERSION, developer_name="Antoine Piron", license_type=Gtk.License.GPL_3_0,
                        comments="Thèmes décoratifs pour Noctalia v5, avec retour arrière garanti."
                        ).present(self.get_active_window())

    def _open_backups(self, *_):
        installer.BACKUPS.mkdir(parents=True, exist_ok=True)
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(str(installer.BACKUPS)))
        launcher.launch(self.get_active_window(), None, None, None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    sys.exit(App().run(sys.argv))
