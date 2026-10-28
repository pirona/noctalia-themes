# noctalia-themes

Decorative themes for [Noctalia](https://docs.noctalia.dev/noctalia/) v5 (tested on 5.3.0 with niri), with a small
GTK 4 / libadwaita app to apply and remove them safely. Themes: **Vaporwave**, **Batman — Year One**,
**Batman — Black and White**. License: GPL-3.0-or-later.

The app is in English, with a French translation picked from your locale.

## Install

```bash
git clone <this repository> noctalia-themes
cd noctalia-themes
./install.sh
```

`install.sh` checks that Python 3.11+, PyGObject, GTK 4 and libadwaita are importable (it prints the package
command for Fedora, Debian/Ubuntu and Arch otherwise), builds the translations if `msgfmt` is available, and adds a
launcher entry. It never uses `sudo` and can be run again at any time. `./install.sh --uninstall` removes the launcher
entry; themes and backups are kept.

Start “Noctalia Themes” from the launcher, or run `python3 app/main.py`.

## Use

- **Apply**: button on the theme's row, after confirmation. A toast offers “Undo” for 8 s.
- **Remove**: the banner at the top as soon as a theme is active, one click. The configuration from before the theme
  comes back **with the settings you changed meanwhile** (bar, dock, plugins…); only the theme's own settings leave
  with it (keys it sets, its widgets, a wallpaper from its folder). If you changed some of the theme's own settings,
  the app lists them first. Switching straight from one theme to another works the same way.
- **Save my setup** (menu, Ctrl+S): copies all of Noctalia as is (config, `settings.toml`, active theme, widget
  positions, fonts, wallpaper). Restoring it brings everything back; these backups are never pruned automatically.
- **Wallpapers**: gallery of the active theme's wallpapers; click to set one, 🔀 for a random one.
- **Update** (⟳ on the active theme): reinstalls stickers, palette and widgets without touching your settings.
- **Backups**: dated list. “Restore” brings Noctalia back to that date, wallpaper included; the trash deletes a
  backup after confirmation (never the active theme's, its only way back).
- **Widget groups stay together**: a theme groups widgets that form one visual unit (a player and its frame, a clock
  and its ink blot). Noctalia's widget editor moves widgets one by one; when you close it, the app (if it is open)
  moves the rest of the group by the same offset. It also does it when its window gets the focus back.

### Preferences (menu → Preferences, or Ctrl+,)

| Page | Settings |
|---|---|
| Wallpapers | transition effects (11), duration, fill mode |
| Widgets | show/hide each widget group, dark/light/auto mode, clock 12 h / seconds / color, media player (blurred cover, hide when idle) |
| App | confirm before applying, target screen, number of backups to keep + clean-up (confirmed, never the active theme's) |
| Diagnostic | versions, active theme, screen, changed or overridden settings, paths, log tail, copy to clipboard |

A preference left on “like the theme” writes nothing. Invalid values in the preferences file fall back to defaults.

## How it works

Noctalia loads its layers in this order, the last one wins:

1. its defaults;
2. `~/.config/noctalia/*.toml`, **in alphabetical order**: `zz-theme.toml` (the theme), then
   `zzz-theme-options.toml` (the app's preferences, which therefore win over the theme);
3. `~/.local/state/noctalia/settings.toml`, written by Noctalia's own settings UI, which wins over everything.

A theme dropped in `~/.config` would be hidden by the state file. So applying a theme:

1. validates it (palette, `theme.toml`, readable TOML): nothing is touched if it is invalid;
2. removes the active theme first, if any, so the backup always captures the original state;
3. backs up `settings.toml`, every file about to be overwritten and the current wallpaper;
4. copies the theme to its installed place, the palette to `palettes/`, the fragment to `zz-theme.toml`, the
   preferences to `zzz-theme-options.toml`;
5. removes from `settings.toml` the keys the theme sets, and the whole `[desktop_widgets]` table.

If a step fails after the backup, everything is restored. Writes are atomic (temporary file, then rename), so
Noctalia, which watches these files, never reads a half-written one. Noctalia reloads them live.

When no setting needs carrying over, removing a theme restores `settings.toml` byte for byte. Otherwise it is
rewritten with the same content in a different layout (arrays of tables become inline tables).

### Files and folders

| Path | Owner | What |
|---|---|---|
| `~/.config/noctalia/zz-theme.toml`, `zzz-theme-options.toml`, `palettes/<name>.json` | Noctalia, written by the app | the active theme and preferences |
| `~/.local/state/noctalia/settings.toml` | Noctalia | read; theme keys removed on apply, widget positions adjusted by the group glue |
| `~/.local/share/noctalia-themes/` | the app, **0700** | installed theme copies, `backups/`, `current`, `glue.json`, `app.log` |
| `~/.local/share/fonts/noctalia-themes/` | the app | theme fonts (fontconfig must see them) |
| `~/.config/noctalia-themes/settings.json` | the app, **0700** folder | app preferences |

Each base folder follows XDG and can be overridden: `NOCTALIA_CONFIG_HOME`, `NOCTALIA_STATE_HOME`,
`NOCTALIA_THEMES_HOME`, `NOCTALIA_THEMES_FONTS`, `NOCTALIA_THEMES_CONFIG` (all defined in `app/paths.py`).
`NOCTALIA_THEMES_OUTPUT` forces the screen the widgets go to.

### Security

- No `sudo`, no network access from the app, nothing outside the folders above.
- Backups hold copies of `settings.toml`, which may contain tokens (calendar accounts, plugins): the app's data
  folder is owner-only (0700), and so is its preferences folder.
- Folders are created when first written to, never at start-up.
- Every TOML file is parsed before it is written; a theme's palette name is restricted to `[A-Za-z0-9_-]+` and the
  screen name is escaped, so a theme cannot write outside its place.
- Log: `~/.local/share/noctalia-themes/app.log` (rotated at 200 KB): applies, restores, deletions, wallpaper changes.

## Add a theme

Create a folder in `themes/`; the app needs no change:

| File | Role |
|---|---|
| `theme.toml` | `name`, `description`, `author`, `palette` (file name, `[A-Za-z0-9_-]+`), `preview` (optional) |
| `[widget_groups]` in `theme.toml` | optional: show/hide labels; the widgets of a group toggle and move together |
| `[locale.<lang>]` in `theme.toml` | optional: `name`, `description` and `[locale.<lang>.widget_groups]` (English label → translation) |
| `palette.json` | Noctalia palette: `dark` + `light`, 16 roles + a `terminal` block, strict `#RRGGBB` |
| `noctalia.toml` | Noctalia config fragment; `@THEME_DIR@` becomes the installed path, `@OUTPUT@` the target screen: `NOCTALIA_THEMES_OUTPUT` if set, else the screen chosen in the preferences, else niri's focused screen, else the first enabled `wlr-randr` output |
| `stickers/`, `wallpapers/` | **original** artwork; `wallpapers/SOURCES.md` for prompts and seeds |
| `fonts/` | optional `.ttf`/`.otf` (with their free license), installed with the theme and removed on rollback; widgets name them by family (`font_family`) |

Preview: apply the theme, then `tools/preview.sh themes/<name>` (captures the desktop on an empty workspace; niri only).
Without `preview.webp`, the app shows the palette's colors. Start from `themes/vaporwave/`.

Wallpapers: see [Generate wallpapers with ComfyUI](#generate-wallpapers-with-comfyui).

## Generate wallpapers with ComfyUI

Optional: only needed to make new wallpapers. Requires a [ComfyUI](https://www.comfy.org/) server (local or on your
network) with the Flux.2 Dev files: diffusion model `flux2_dev_fp8mixed`, text encoder `mistral_3_small_flux2_fp8`,
VAE `flux2-vae`.

**Configure once**, in one command:

```bash
python3 tools/comfy_generate.py --setup
```

It asks for the server address (Enter keeps `http://127.0.0.1:8188`), checks that the server answers, lists the model
files it offers and proposes the right ones (Enter accepts). Everything goes to **`~/.config/noctalia-themes/comfyui.toml`**:

```toml
url = "http://127.0.0.1:8188"
unet = "flux2_dev_fp8mixed.safetensors"
clip = "mistral_3_small_flux2_fp8.safetensors"
vae = "flux2-vae.safetensors"
```

Edit it by hand or run `--setup` again. `COMFY_URL` overrides the address for one run. Without the file, these
defaults are used, and a model stored in a subfolder on the server (e.g. `FLUX2/flux2_dev_fp8mixed.safetensors`) is
found by its file name. If the server does not answer or a model is missing, the tool says so and points to `--setup`.

**Generate and promote**:

```bash
python3 tools/comfy_generate.py --theme vaporwave --prompt-file tools/prompts/vaporwave/01-atrium.txt \
    --seed 20111209 --name atrium       # one job; waits its turn, never cancels anything; --dry-run prints the graph
python3 tools/promote_wallpaper.py --theme vaporwave <render.png> atrium
```

Renders land in `<Pictures>/noctalia-<theme>-renders/` (`WALLPAPER_BUFFER` to change). Promotion trims a frame drawn
by the model, crops to 1920×1080, converts to WebP, updates `SOURCES.md` and copies the file to
`<Pictures>/wallpapers/<theme>/` (`WALLPAPER_DIR` to change). Prompt rules per theme: `tools/prompts/<theme>/RULES.md`.

## Command line

```bash
python3 app/installer.py apply themes/vaporwave   # prints the backup id
python3 app/installer.py list                     # available backups
python3 app/installer.py rollback <id>            # back to that backup
python3 app/installer.py refresh themes/vaporwave # update the active theme in place, your settings untouched
python3 app/installer.py save                     # save my setup
python3 app/installer.py glue                     # move widget groups back together
```

## Development

```bash
python3 app/palette.py           # color format + contrast >= 4.5:1 (Noctalia silently ignores a bad color)
python3 app/options.py           # preferences: overrides, clock format, TOML keys, validation
python3 tests/test_installer.py  # sandbox: round trip, invalid theme, failure, path tricks, screen, carried
                                 # settings, setup backup, preferences, clean-up, glue, wallpaper, permissions
python3 tests/test_promote_bw.py # black and white thresholding
pipx run ruff==0.12.0 check .    # lint + PEP 8 (config in pyproject.toml)
```

Layout: `app/paths.py` (every path), `app/i18n.py` (translations), `app/installer.py` (logic, no GTK, testable),
`app/options.py` (preferences → TOML fragment), `app/window.py` (main window), `app/preferences.py` (preferences
dialog), `app/main.py` (application, actions, shortcuts), `app/palette.py` (palette validation).

Translations: strings are English in the code, wrapped in `_()`. After changing them:

```bash
xgettext -L Python --from-code=UTF-8 -k_ -kngettext:1,2 --add-comments=Translators --no-wrap \
    --package-name=noctalia-themes -o po/noctalia-themes.pot app/*.py
msgmerge -q --no-wrap -U po/fr.po po/noctalia-themes.pot   # then translate the new or fuzzy entries
./install.sh                                                # rebuilds app/locale/
```

A new language is a new `po/<lang>.po` (`msginit -i po/noctalia-themes.pot -l <lang> -o po/<lang>.po`).

## Known limits

- **One screen**: `@OUTPUT@` is fixed when the theme is applied, and positions are designed for 1536×864 logical
  pixels. On another screen, or if that screen goes away, widgets are misplaced or missing: apply the theme again.
- **Group glue** needs the app to be open when the widget editor closes (or to get the focus afterwards), and detects
  the editor through niri; on another compositor a glue made while the editor is open is overwritten by Noctalia.
- The **theme's own** settings changed while it is active (a widget's position…) leave with it (the app warns);
  use “Save my setup” first to keep them.
- No lock with Noctalia: a write it makes during the sub-second window of an apply would be lost.

## Noctalia pitfalls

- Desktop widget `rotation` is in **radians** (the documentation does not say).
- `theme.shell_mode = "auto"` keeps the bar light even with `mode = "dark"`.
- `theme.pure_black_dark = true` replaces the palette's dark surfaces with black.
- GIF wallpapers: only the first frame is shown (5.3.0).
- Desktop widgets have a background by default: `background = false` for bare text.
- Stickers are cached by path: to replace an image, give it a **new file name**.
- A font installed while Noctalia runs is only seen after **restarting Noctalia** (fontconfig is read at start).
- While the widget editor is open, Noctalia ignores changes to `settings.toml` and rewrites its own positions when
  the editor closes.
- The media player only shows the cover if the player publishes a readable `mpris:artUrl`. A **Flatpak** player
  based on Chromium/Electron writes it into **its own** private `/tmp`, which Noctalia cannot read. Fix:
  `flatpak override --user --filesystem=/tmp <app-id>` then restart the player (undo: `--nofilesystem=/tmp`);
  the trade-off is that the player sees the session's `/tmp`.
- The audio visualizer reads the sound before the output: with AirPlay (~1.6 s of buffer) it runs ahead of what you hear.
