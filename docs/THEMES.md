# Making a theme

A theme is one folder: a palette, a Noctalia config fragment, and its own artwork. Shipped themes live in
`themes/`; anyone else's arrive as a **package**, a `.zip` holding that one folder, dropped on the app.

## In four commands

```bash
python3 app/package.py new ~/my-themes/night-swim   # commented skeleton that already passes the checks
# edit theme.toml, palette.json, noctalia.toml; add wallpapers/ and stickers/
python3 app/package.py check ~/my-themes/night-swim # the exact checks an import runs; prints "ok" or each problem
python3 app/package.py pack ~/my-themes/night-swim  # writes night-swim-1.0.0.zip
```

Then drag the `.zip` onto the dashed field under the theme list (or click the field to pick it). The theme appears
with an “Imported” label; apply it like any other. To try changes, raise `version`, pack again and drop the new
`.zip`: the app asks before replacing the installed copy. The trash on an imported theme's row removes it from the
list (never while it is active; your backups stay).

## Folder layout



| File | Role |
|---|---|
| `theme.toml` | `format` (`1`), `name`, `description`, `author`, `version`, `license` (SPDX id), `palette` (file name, `[A-Za-z0-9_-]+`; **the folder name** in a package), `preview` (optional), `ink` (optional: `"black-and-white"` thresholds wallpapers to pure ink and paper, `"grain"` turns them grey with a fixed film grain, `"pixel"` into fine grey pixel art, all at promotion; `--ink` overrides it for one wallpaper) |
| `[widget_groups]` in `theme.toml` | optional: show/hide labels; the widgets of a group toggle and move together |
| `[locale.<lang>]` in `theme.toml` | optional: `name`, `description` and `[locale.<lang>.widget_groups]` (English label → translation) |
| `palette.json` | Noctalia palette: `dark` + `light`, 16 roles + a `terminal` block, strict `#RRGGBB` |
| `noctalia.toml` | Noctalia config fragment; `@THEME_DIR@` becomes the installed path, `@OUTPUT@` the target screen: `NOCTALIA_THEMES_OUTPUT` if set, else the screen chosen in the preferences, else niri's focused screen, else the first enabled `wlr-randr` output |
| `stickers/`, `wallpapers/` | **original** artwork; `wallpapers/SOURCES.md` for prompts and seeds |
| player, clock | optional: `billisdead/theme-widgets:player` (cover, title, artist, ⏮ ⏯ ⏭ for any MPRIS player) and `billisdead/theme-widgets:clock` (`format`, `date_format`, `size`, `date_size`) draw inside your frame as **one** widget each (plugin in `plugins/theme-widgets/`, installed and enabled with the theme). Draw the frame at 2× with a flat or transparent interior, run `tools/slice_frame.py <frame.png>` (`--tol 24` for a paper grain, flattened under the text), point the widget's `frame` setting at the folder it writes; `fill`, `color`, `font_family` style the content, and on a frame with a fixed interior colour an unreadable colour role becomes black or white. Set `background = false` |
| `fonts/` | optional `.ttf`/`.otf` (with their free license), installed with the theme and removed on rollback; widgets name them by family (`font_family`) |

Preview: apply the theme, then `tools/preview.sh themes/<name>` (captures the desktop on an empty workspace; niri only).
Without `preview.webp`, the app shows the palette's colors. Start from `themes/vaporwave/`.

Wallpapers: see [Generate wallpapers with ComfyUI](../README.md#generate-wallpapers-with-comfyui).


Authoring scripts (`*.py`, `__pycache__`) may sit next to the artwork: they are left out of the package and never
run.

## What an imported theme may do

A package can come from anyone, and Noctalia's configuration can start programs (bar buttons, hooks, session
commands). So an imported theme is held to **looks only**; the app refuses the whole package otherwise and lists
every reason.

| Rule | Why |
|---|---|
| `noctalia.toml` only sets `[theme]`, `[wallpaper]`, `[bar]`, `[desktop_widgets]`, `[dock]` | session, idle, launcher, network or hooks settings are not a theme's business |
| no key named `*command*`, `exec`, `*script*`, `*hook*`, `cmd`, `*url*`, at any depth | these start programs or reach the network |
| every value with a `/` is `@THEME_DIR@/…` (no `..`) or a plugin shipped with the app (`billisdead/theme-widgets:player`, `:clock`) | no reading files elsewhere, no third-party plugin code |
| `palette` equals the folder name | palettes share one folder (`~/.config/noctalia/palettes/`): two themes must not overwrite each other's |
| a built-in theme's folder or name cannot be reused; two imported themes cannot share a name | the app finds the active theme by name |
| only `.toml .json .md .txt .webp .png .jpg .jpeg .svg .ttf .otf` files | nothing executable |
| one top-level folder, no absolute path, no `..`, no symbolic link | nothing lands outside the theme's place |
| at most 500 files, 32 MB per file, 128 MB unpacked | a malformed or hostile archive cannot fill the disk |

The archive is unpacked into a private staging folder, checked there, then moved in place: a refused package leaves
nothing behind. Imported themes live in `~/.local/share/noctalia-themes/library/` (owner-only, like the rest of the
app's data). Fonts and images are still parsed by fontconfig and Noctalia: import packages from people you trust.

Built-in themes are trusted (they ship with the code) but follow the same rules, so any of them can be packed.

## Licenses

`license` covers the theme as a whole. Fonts keep their own license file next to them (`fonts/OFL-*.txt`). Only ship
artwork you made or may redistribute; say where it comes from in `wallpapers/SOURCES.md`.
