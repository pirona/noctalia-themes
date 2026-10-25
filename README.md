# noctalia-themes

Thèmes décoratifs pour [Noctalia](https://docs.noctalia.dev/noctalia/) v5 (testé sur 5.3.0, Fedora 44, Niri),
avec une petite appli GTK4 / libadwaita pour les appliquer et les retirer. Premier thème : **vaporwave**.
Licence GPL v3.

## Installation

```bash
git clone <ce dépôt> ~/gitea-trucs/noctalia-themes
cd ~/gitea-trucs/noctalia-themes
./install.sh            # vérifie python3-gobject, gtk4, libadwaita ; crée l'entrée du lanceur
```

`install.sh` n'utilise jamais `sudo` : s'il manque un paquet, il affiche la commande `dnf` à lancer.
Il est rejouable sans effet de bord. `./install.sh --uninstall` retire l'entrée du lanceur (sauvegardes conservées).

Lancer : « Thèmes Noctalia » dans le lanceur, ou `python3 app/main.py`.

## Utilisation

- **Appliquer** : bouton sur la carte du thème, après confirmation. Un toast propose « Annuler » pendant 8 s.
- **Retirer** : bandeau en haut de la fenêtre dès qu'un thème est actif, un clic. Si des réglages Noctalia ont été
  modifiés depuis l'application du thème, l'appli les liste et demande confirmation avant de les perdre.
- **Sauvegardes** : liste datée ; « Restaurer » remet la config Noctalia exactement dans l'état de cette date ;
  la corbeille supprime une sauvegarde après confirmation (impossible pour celle du thème actif, seul retour possible).
  Menu → « Ouvrir le dossier des sauvegardes » pour les voir dans le gestionnaire de fichiers.

À savoir : les réglages faits dans l'interface Noctalia **pendant** qu'un thème est actif sont perdus au retrait.
C'est le prix d'une restauration exacte.

## Comment ça marche

Noctalia charge trois couches, la dernière gagne : défauts → `~/.config/noctalia/*.toml` →
`~/.local/state/noctalia/settings.toml` (écrit par l'interface). Un thème déposé dans `~/.config` serait donc
masqué par l'état. Appliquer un thème :

1. valide le thème (palette, `theme.toml`, TOML lisible) : rien n'est touché si c'est invalide ;
2. si un thème est déjà actif, le retire d'abord : la sauvegarde capture toujours l'état d'origine ;
3. sauvegarde `settings.toml` et tout fichier qui sera écrasé dans `~/.local/share/noctalia-themes/backups/<date>/` ;
4. copie le thème dans `~/.local/share/noctalia-themes/themes/`, la palette dans `~/.config/noctalia/palettes/`,
   le fragment dans `~/.config/noctalia/zz-theme.toml` ;
5. retire de `settings.toml` les clés que le thème définit, et toute la table `[desktop_widgets]`.

Si une étape échoue après la sauvegarde, tout est restauré automatiquement. Les écritures sont atomiques
(fichier temporaire puis renommage) pour que Noctalia, qui surveille ces fichiers, ne lise jamais un fichier à moitié écrit.
Le retour arrière restaure les copies **à l'octet près** et retire les fichiers créés. Noctalia recharge à chaud.

## Ajouter un thème

Créer un dossier dans `themes/`, aucune modification de l'appli n'est nécessaire :

| Fichier | Rôle |
|---|---|
| `theme.toml` | `name`, `description`, `author`, `palette` (nom de fichier, `[A-Za-z0-9_-]+`), `preview` (optionnel) |
| `palette.json` | palette Noctalia : `dark` + `light`, 16 rôles + bloc `terminal`, `#RRGGBB` strict |
| `noctalia.toml` | fragment de config Noctalia ; `@THEME_DIR@` devient le chemin installé, `@OUTPUT@` l'écran détecté (écran actif sous niri, sinon le premier de `wlr-randr` ; forçable avec `NOCTALIA_THEMES_OUTPUT=HDMI-A-1`) |
| `stickers/`, `wallpapers/` | assets **originaux** ; `wallpapers/SOURCES.md` pour les prompts et seeds |

Aperçu : appliquer le thème puis `tools/preview.sh themes/<nom>` (capture le bureau sur un espace de travail vide,
niri uniquement). Sans `preview.webp`, l'appli affiche des bandes aux couleurs de la palette. Partir de `themes/vaporwave/`.

## Ligne de commande

```bash
python3 app/installer.py apply themes/vaporwave   # affiche l'id de la sauvegarde
python3 app/installer.py list                     # sauvegardes disponibles
python3 app/installer.py rollback <id>            # retour à l'état de cette sauvegarde
```

## Développement

```bash
python3 app/palette.py               # format des couleurs + contraste >= 4.5:1 (Noctalia ignore une couleur invalide sans prévenir)
python3 tests/test_installer.py      # bac à sable : aller-retour, thème invalide, panne, chemin piégé, écran, réglages perdus
pipx run ruff==0.12.0 check .        # lint + PEP 8 (config dans pyproject.toml), sans installation durable
```

Structure : `app/installer.py` (logique, sans GTK, testable), `app/window.py` (interface), `app/main.py` (application,
actions, raccourcis), `app/palette.py` (validation). Logs sur la sortie d'erreur (journal systemd quand lancé depuis le lanceur).

## Limites connues

- **Un seul écran** : `@OUTPUT@` est figé à l'application du thème, et les positions sont pensées pour 1536×864
  logiques. Sur un autre écran, ou si cet écran disparaît (dock débranché), les widgets sont mal placés ou absents :
  ré-appliquer le thème. Noctalia ne propose pas de cible « tous les écrans » documentée.
- Les réglages modifiés dans Noctalia pendant qu'un thème est actif sont perdus au retrait (l'appli prévient).
- Pas de verrou avec Noctalia : une écriture qu'il ferait pile pendant l'application (fraction de seconde) serait perdue.

## Pièges Noctalia relevés

- `rotation` des widgets de bureau est en **radians** (la doc ne le dit pas).
- `theme.shell_mode = "auto"` garde la barre claire même avec `mode = "dark"`.
- `theme.pure_black_dark = true` remplace les surfaces sombres de la palette par du noir.
- Fond d'écran GIF : seule la première image s'affiche, pas d'animation (testé sur 5.3.0).
- Les widgets de bureau ont un fond par défaut : `background = false` pour du texte seul.
