# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR breaks a theme package or the app's files, MINOR adds themes or features, PATCH fixes.

## [0.1.1] - 2026-11-12

- README: screenshots, feature tour, Ko-fi link.
- `tools/release.sh`: one command tags and publishes the Gitea release; the GitHub workflow skips an existing release.

## [0.1.0] - 2026-11-12

First public release.

- Themes: Vaporwave, Brume, Kunstruk, Kunstruk Papier.
- GTK 4 / libadwaita app: apply and remove a theme with a timestamped backup and guaranteed rollback, undo toast,
  saved setups, preferences.
- Theme packages: import a `.zip` by drag and drop, export any theme, create a theme from your desktop.
- `theme-widgets` plugin: music player with cover art (Flatpak players included) and clock.
- Login screen wallpaper follows the theme (Noctalia Greeter).
- English interface with a French translation.
- `install.sh`: per-user install, no `sudo`, `--uninstall`.
