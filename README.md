# noctalia-themes

Thèmes décoratifs pour [Noctalia](https://docs.noctalia.dev/noctalia/) v5 (testé sur 5.3.0, Fedora 44, Niri).
Premier thème : **vaporwave**. Licence GPL v3.

## Principe

Un thème = un dossier autonome dans `themes/` :

| Fichier | Rôle |
|---|---|
| `theme.toml` | nom, description, auteur, nom de la palette |
| `palette.json` | palette Noctalia (`dark` + `light`, `#RRGGBB` strict) |
| `noctalia.toml` | fragment de config Noctalia (thème, transitions, widgets de bureau). `@THEME_DIR@` est remplacé à l'installation |
| `stickers/`, `wallpapers/` | assets originaux |

Appliquer un thème :

1. sauvegarde `~/.local/state/noctalia/settings.toml` et tout fichier qui sera écrasé dans `~/.local/share/noctalia-themes/backups/<date>/` ;
2. copie le thème dans `~/.local/share/noctalia-themes/themes/`, la palette dans `~/.config/noctalia/palettes/`, le fragment dans `~/.config/noctalia/zz-theme.toml` ;
3. retire du `settings.toml` d'état les clés que le thème définit (sinon elles l'emportent : l'état est la dernière couche chargée par Noctalia) et toute la table `[desktop_widgets]`.

Le retour arrière restaure les copies **à l'octet près** et retire les fichiers créés. Noctalia recharge à chaud.
Ré-appliquer un thème fait d'abord le retour arrière du thème actif, la sauvegarde capture donc toujours l'état d'origine.
Les réglages faits dans l'interface Noctalia pendant qu'un thème est actif sont perdus au retour arrière.

## Ligne de commande (en attendant l'appli)

```bash
python3 app/installer.py apply themes/vaporwave   # affiche l'id de la sauvegarde
python3 app/installer.py list                     # sauvegardes disponibles
python3 app/installer.py rollback <id>            # retour à l'état d'avant
```

## Vérifications

```bash
python3 tools/check_palette.py     # format des couleurs + contraste >= 4.5:1
python3 tests/test_installer.py    # aller-retour appliquer/revenir dans un bac à sable
```

## Pièges Noctalia relevés

- `rotation` des widgets de bureau est en **radians** (la doc ne le dit pas).
- `theme.shell_mode = "auto"` garde la barre claire même avec `mode = "dark"`.
- `theme.pure_black_dark = true` remplace les surfaces sombres de la palette par du noir.
- Fond d'écran GIF : seule la première image s'affiche, pas d'animation (testé sur 5.3.0).
