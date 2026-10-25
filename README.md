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
- **Fonds d'écran** : galerie des fonds du thème actif ; clic = fond posé (via `noctalia msg wallpaper-set`), 🔀 = au hasard.
- **Mettre à jour** (⟳ sur le thème actif) : réinstalle stickers, palette et widgets sans toucher à tes réglages.
- **Sauvegardes** : liste datée ; « Restaurer » remet la config Noctalia exactement dans l'état de cette date ;
  la corbeille supprime une sauvegarde après confirmation (impossible pour celle du thème actif, seul retour possible).
  Menu → « Ouvrir le dossier des sauvegardes » pour les voir dans le gestionnaire de fichiers.

### Préférences (menu → Préférences, ou Ctrl+,)

| Onglet | Réglages |
|---|---|
| Fonds | effets de transition (11), durée, remplissage |
| Widgets | afficher/masquer chaque widget (groupes définis par le thème), mode sombre/clair/auto, horloge 12 h / secondes / couleur, lecteur CD (pochette floutée, masquer à l'arrêt) |
| Appli | confirmation avant d'appliquer, écran cible, nombre de sauvegardes à garder + ménage (confirmé, jamais celle du thème actif) |
| Diagnostic | versions, thème actif, écran, réglages modifiés ou écrasés, chemins, fin du journal, copie dans le presse-papiers |

Les préférences sont rangées dans `~/.config/noctalia-themes/settings.json` (une valeur invalide retombe sur
la valeur par défaut). Une préférence laissée sur « comme le thème » n'écrit rien. Chaque changement est appliqué au
thème actif au bout de 400 ms.

À savoir : les réglages faits dans l'interface Noctalia **pendant** qu'un thème est actif sont perdus au retrait.
C'est le prix d'une restauration exacte.

## Comment ça marche

Noctalia charge ses couches dans cet ordre, la dernière gagne :

1. ses valeurs par défaut ;
2. les `~/.config/noctalia/*.toml`, **par ordre alphabétique** : `zz-theme.toml` (le thème) puis
   `zzz-theme-options.toml` (les préférences de l'appli, qui l'emportent donc sur le thème) ;
3. `~/.local/state/noctalia/settings.toml`, écrit par l'interface de Noctalia, qui l'emporte sur tout.

Un thème déposé dans `~/.config` serait donc masqué par l'état. Appliquer un thème :

1. valide le thème (palette, `theme.toml`, TOML lisible) : rien n'est touché si c'est invalide ;
2. si un thème est déjà actif, le retire d'abord : la sauvegarde capture toujours l'état d'origine ;
3. sauvegarde `settings.toml` et tout fichier qui sera écrasé dans `~/.local/share/noctalia-themes/backups/<date>/` ;
4. copie le thème dans `~/.local/share/noctalia-themes/themes/`, la palette dans `~/.config/noctalia/palettes/`,
   le fragment dans `~/.config/noctalia/zz-theme.toml`, les préférences dans `zzz-theme-options.toml` ;
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
| `noctalia.toml` | fragment de config Noctalia ; `@THEME_DIR@` devient le chemin installé, `@OUTPUT@` l'écran cible : `NOCTALIA_THEMES_OUTPUT` s'il est défini, sinon l'écran choisi dans les préférences, sinon l'écran actif sous niri, sinon le premier écran allumé de `wlr-randr` |
| `[widget_groups]` dans `theme.toml` | optionnel : libellés des interrupteurs « afficher/masquer », un groupe peut regrouper plusieurs widgets |
| `stickers/`, `wallpapers/` | assets **originaux** ; `wallpapers/SOURCES.md` pour les prompts et seeds |

Aperçu : appliquer le thème puis `tools/preview.sh themes/<nom>` (capture le bureau sur un espace de travail vide,
niri uniquement). Sans `preview.webp`, l'appli affiche des bandes aux couleurs de la palette. Partir de `themes/vaporwave/`.

## Ligne de commande

```bash
python3 app/installer.py apply themes/vaporwave   # affiche l'id de la sauvegarde
python3 app/installer.py list                     # sauvegardes disponibles
python3 app/installer.py rollback <id>            # retour à l'état de cette sauvegarde
python3 app/installer.py refresh themes/vaporwave # met à jour le thème actif sur place (stickers, palette, widgets)
                                                  # sans toucher à settings.toml : tes réglages modifiés depuis sont gardés
```

## Développement

```bash
python3 app/palette.py               # format des couleurs + contraste >= 4.5:1 (Noctalia ignore une couleur invalide sans prévenir)
python3 app/options.py               # préférences : surcharges, format d'horloge, clés TOML, validation
python3 tests/test_installer.py      # bac à sable : aller-retour, thème invalide, panne, chemin piégé, écran,
                                     # réglages perdus, préférences, ménage des sauvegardes
pipx run ruff==0.12.0 check .        # lint + PEP 8 (config dans pyproject.toml), sans installation durable
```

Structure : `app/installer.py` (logique, sans GTK, testable), `app/options.py` (préférences → fragment TOML),
`app/window.py` (fenêtre principale), `app/preferences.py` (préférences), `app/main.py` (application, actions,
raccourcis), `app/palette.py` (validation). Journal : `~/.local/share/noctalia-themes/app.log` (rotation à 200 Ko,
trace des applications, restaurations, suppressions et changements de fond), aussi sur la sortie d'erreur.

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
- Les stickers sont mis en cache par chemin : pour remplacer une image, lui donner un **nouveau nom de fichier**.
- Le lecteur média (`media_player`) n'affiche la pochette que si le lecteur publie en MPRIS un `mpris:artUrl` lisible.
  Un lecteur **Flatpak** basé sur Chromium/Electron (ex. Aonsoku) l'écrit dans **son** `/tmp` privé : Noctalia ne peut
  pas l'ouvrir. Correctif : `flatpak override --user --filesystem=/tmp <app-id>` puis relancer l'appli
  (retour arrière : `--nofilesystem=/tmp`). Contrepartie : l'appli voit le `/tmp` de la session.
- Le visualiseur audio lit le son avant la sortie : en AirPlay (~1,6 s de tampon), il est en avance sur ce qu'on entend.
