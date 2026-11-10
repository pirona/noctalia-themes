# Packaging a theme, from A to Z

*Français : [PACKAGING.fr.md](PACKAGING.fr.md)*

This guide takes you from "I like how my desktop looks" to "a friend installed my theme with one drag", and
explains why each step exists. The reference tables (every file, every rule) are in [THEMES.md](THEMES.md); this
page tells the story in order.

## 1. What a package is

A **theme** is one folder: a palette (colors), a small Noctalia config fragment (bar, dock, wallpaper and desktop
widget settings), and its own pictures. A **package** is that folder zipped, nothing more: `night-swim-1.0.0.zip`
holds `night-swim/` and everything in it.

Why a plain `.zip`: every system opens one, you can look inside before installing, and the app needs no
installer or network to read it.

Why the app is strict about what goes inside: Noctalia's configuration can start programs (a bar button, a
session hook). A theme you download from someone should only change **looks**, so the app checks every package
against an allowlist before installing it, and refuses the whole package if a single rule fails. Your own themes
go through the same checks, so what you export will install on someone else's machine.

## 2. Two ways to make a theme

| | From your desktop | By hand |
|---|---|---|
| Start | Noctalia as you like it, menu → **Create a theme from my desktop** | `python3 app/package.py new <folder>` |
| Good for | capturing a setup you already tuned | a theme designed from scratch, or polishing a captured one |
| Terminal | not needed | needed for `new`, `check`, `pack` |

Both end the same way: a folder the app checks, then exports as a `.zip`. You can mix them: capture your desktop,
then edit the files by hand (section 4).

## 3. Way one: from your desktop

1. Set Noctalia up: palette, wallpaper, bar size and font, dock, desktop widgets (stickers, clock, player).
2. In the app, open the menu and choose **Create a theme from my desktop** (Ctrl+N).
3. Fill in the name (the only required field), author, description and license (`GPL-3.0-or-later` by default;
   any [SPDX id](https://spdx.org/licenses/) works). Click **Create**.
4. Read the result dialog. It lists everything that was **left out**, and why:

   | Left out | Why |
   |---|---|
   | the bar's widget layout | bar widgets are set up outside the theme; their looks (size, font, colors) come along |
   | pinned dock apps | your apps, not part of a look |
   | widgets from third-party plugins | a theme may only use the plugin shipped with the app |
   | any setting that runs a program | see section 1 |
   | a file that cannot travel (a text file, a folder from your home) | only pictures leave your home; nothing private |
   | a palette with no file, or one that fails the contrast checks | the theme starts with Brume's colors instead (section 5) |

5. Click **Open the folder** to look at what was made, or **Export…** to save the `.zip` right away.

What the app did behind the scenes: it copied your palette, the wallpaper on screen and every sticker your widgets
use into a new folder, rewrote their paths as `@THEME_DIR@/…` (so they work wherever the theme is installed) and
your screen name as `@OUTPUT@` (so the widgets land on the screen of whoever installs it), then packed it and
imported it like any package. The new theme appears in the list with an "Imported" label.

**Folder name.** The folder is named after the theme: `Night Swim` → `night-swim`, accents dropped
(`Été brûlant` → `ete-brulant`). A name with no Latin letters (`夜の猫`) gets `theme-` and 8 characters taken
from the name. The name shown in the app keeps its accents and script either way.

## 4. Way two: by hand

```bash
python3 app/package.py new ~/my-themes/night-swim
```

This creates a skeleton that already passes the checks:

```
night-swim/
├── theme.toml      name, author, version, license, palette = "night-swim"
├── palette.json    Brume's colors, to recolor (section 5)
├── noctalia.toml   [theme] and [wallpaper], commented
├── wallpapers/     your wallpapers (section 6)
└── stickers/       pictures used by desktop widgets (section 7)
```

The folder name must be lowercase letters, digits, `-` or `_`, and `palette` in `theme.toml` must equal it: all
palettes share one Noctalia folder, so two themes must not overwrite each other's. Fill in `theme.toml` (fields
explained in [THEMES.md](THEMES.md#folder-layout)). To polish a captured theme instead, open its folder from the
result dialog (it lives in `~/.local/share/noctalia-themes/library/<folder>`) and copy it somewhere of your own
before editing: the library is the app's, and an import replaces it.

## 5. The palette

`palette.json` holds two modes, `dark` and `light`. Each has 16 color roles (`mPrimary` and the text drawn on it,
`mOnPrimary`, and so on for Secondary, Tertiary, Error, Surface, SurfaceVariant, Hover), plus `mOutline`, `mShadow`
and a `terminal` block (foreground, background, cursor, the 16 ANSI colors). Colors are strict `#RRGGBB`.

The app checks that each color and the text drawn on it reach a **contrast of 4.5:1** (the WCAG level for normal
text), because Noctalia does not warn about unreadable bars: it just draws them. A failing pair reads like this:

```
dark: mPrimary/mOnPrimary contrast 2.10 < 4.5
```

Fix it by making one of the two lighter or darker until the number passes 4.5. Start from any shipped palette
(`themes/*/palette.json`) rather than from a blank file.

## 6. Wallpapers

Put them in `wallpapers/` as WebP, PNG or JPEG (32 MB at most each). The app shows them in its gallery once the
theme is active. To also show one on the login screen (Noctalia Greeter), name it in `theme.toml`:

```toml
login_wallpaper = "wall_night-swim.webp"
```

Only ship pictures you made or may share, and say where they come from in `wallpapers/SOURCES.md` (prompt and seed
for generated ones: see [Generate wallpapers with ComfyUI](../README.md#generate-wallpapers-with-comfyui)).

## 7. Desktop widgets, stickers and fonts

Desktop widgets go in `noctalia.toml` under `[desktop_widgets]`. Every file a widget uses is written as a path inside
the theme, and the screen as `@OUTPUT@`:

```toml
[desktop_widgets]
enabled = true
widget_order = ["moon"]

[desktop_widgets.widget.moon]
type = "sticker"
output = "@OUTPUT@"
cx = 1200.0
cy = 180.0

[desktop_widgets.widget.moon.settings]
image_path = "@THEME_DIR@/stickers/moon.png"
```

The easiest way to get positions right: place the widgets with Noctalia's own editor, then capture the desktop
(section 3) and copy the numbers. Positions are designed for one screen size (see Known limits in the README).

The clock and music player drawn inside your own frame come from the plugin shipped with the app
(`billisdead/theme-widgets:clock` and `:player`); how to draw and slice a frame is in
[THEMES.md](THEMES.md#folder-layout). Fonts go in `fonts/` as `.ttf` or `.otf`, with their license file next to
them; widgets name them by family (`font_family`).

## 8. Check

```bash
python3 app/package.py check ~/my-themes/night-swim
```

It runs **exactly** the checks an import runs and prints `ok`, or one line per problem. The common ones:

| Message | Fix |
|---|---|
| `theme.toml: missing 'author'` | add the field |
| `theme.toml: 'palette' must be the folder name 'night-swim'` | set `palette = "night-swim"` |
| `noctalia.toml: 'bar.default.middle_click_command' can run a program, not allowed in a theme` | remove the key |
| `noctalia.toml: '…' must point inside the theme (@THEME_DIR@/...)` | copy the file into the theme and use `@THEME_DIR@/…` |
| `notes.docx: file type not allowed` | remove it; allowed: `.toml .json .md .txt .webp .png .jpg .jpeg .svg .ttf .otf` |
| `dark: mPrimary/mOnPrimary contrast 2.10 < 4.5` | section 5 |
| `theme.toml: login_wallpaper '…' is not a file of wallpapers/` | fix the name, or move the file into `wallpapers/` |

In the app, there is nothing to run: **Export** does the same check first and lists what to fix.

## 9. Pack or export

Either way you get `<folder>-<version>.zip`:

- **In the app**: the save icon on the theme's row, then "Save as". Works for any theme in the list, built-in ones
  included.
- **In a terminal**: `python3 app/package.py pack ~/my-themes/night-swim` writes `night-swim-1.0.0.zip` in the
  current folder (give a folder or a `.zip` path as a second argument to choose).

Authoring scripts (`*.py`) next to your artwork are left out of the package: they are tools for you, not for the
people who install the theme.

## 10. Test it like someone else would

Drop the `.zip` on the dashed field under the theme list (or click the field to pick it). The app unpacks it into a
private staging folder, checks it there, and only then moves it in place: a refused package leaves nothing behind.
Apply it, look at every screen you care about, try both dark and light mode.

When you drop a package of a theme that is already installed, the app compares them:

| Case | What happens |
|---|---|
| same files | "already installed, identical: nothing to do", nothing changes |
| newer version | it asks before replacing (button highlighted) |
| same version, different files, or older version | it asks, says so, and the Replace button is red |
| a built-in theme's name or folder | refused: built-in themes cannot be replaced |

If you replace the theme that is active, click **Update** (⟳ on its row) to see the new version on the desktop.

## 11. Share a new version

1. Edit the folder.
2. Raise `version` in `theme.toml` (`1.0.0` → `1.0.1`): people who install it see "newer version" instead of a red
   warning.
3. Check, then pack or export again: the file name follows the version, so the old `.zip` is not overwritten.

## 12. Remove a theme

The trash icon on an imported theme's row removes it from the list (never while it is active: remove the theme from
the desktop first, with the banner at the top). Your backups stay; dropping the `.zip` again brings it back.

## Troubleshooting

- **"This theme cannot be imported"** followed by a list: each line is one rule (section 8). Fix them all, then pack
  again.
- **"The archive must hold one theme folder"**: you zipped the files instead of the folder. Zip the folder itself,
  or use `pack`, which does it right.
- **A value with `/` is refused although it is not a file**, for example a date format `"%d/%m"`: the check treats
  every `/` as a path. Use another separator (`"%d.%m"`, `"%d %b"`).
- **Widgets missing or misplaced after install**: the theme was made for another screen size, or the screen
  changed. Apply the theme again; positions are designed for one screen (README, Known limits).
- **The clock or player stays empty**: the plugin is enabled through Noctalia; apply the theme while Noctalia runs,
  or enable "Theme Widgets" in Noctalia's plugin settings.
- **The login screen uses another font**: the login screen only sees fonts installed for the whole system.
