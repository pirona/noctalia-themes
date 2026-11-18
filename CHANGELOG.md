# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR breaks a theme package or the app's files, MINOR adds themes or features, PATCH fixes.

## [0.1.5] - 2026-11-18

- A theme that sets its own mode keeps it: the app's Mode preference no longer turns Kunstruk light system-wide
  (bar, GTK apps, login screen). The preference now only applies to themes that leave the mode open.
- `tools/release.sh`: waits for Gitea to register the tag before creating the release.
- README: link to the launch blog post.

## [0.1.4] - 2026-11-15

- Kunstruk: new preview with the bar at the bottom.
- `tools/preview.sh`: waits 3 s for the empty workspace; 1.5 s could capture the previous one.

## [0.1.3] - 2026-11-15

- Kunstruk: the bar moves to the bottom edge and the square dock to the top; on the right edge the bar collided
  with the desktop widgets.

## [0.1.2] - 2026-11-13

- `theme-widgets`: the clock and player now draw in the theme font right after login (Kunstruk); before, they kept
  the fallback font until the theme was re-applied.

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
