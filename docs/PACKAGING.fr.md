# Empaqueter un thème, de A à Z

*English: [PACKAGING.md](PACKAGING.md)*

Ce guide mène de « j'aime l'allure de mon bureau » à « un ami a installé mon thème d'un simple glisser », et
explique pourquoi chaque étape existe. Les tableaux de référence (chaque fichier, chaque règle) sont dans
[THEMES.md](THEMES.md) (en anglais) ; cette page raconte l'histoire dans l'ordre.

## 1. Ce qu'est un paquet

Un **thème** est un dossier : une palette (les couleurs), un petit fragment de configuration Noctalia (réglages de
la barre, du dock, du fond d'écran et des widgets du bureau) et ses propres images. Un **paquet** est ce dossier
zippé, rien de plus : `night-swim-1.0.0.zip` contient `night-swim/` et tout ce qu'il y a dedans.

Pourquoi un simple `.zip` : tous les systèmes l'ouvrent, on peut regarder dedans avant d'installer, et l'appli n'a
besoin ni d'installeur ni de réseau pour le lire.

Pourquoi l'appli est stricte sur le contenu : la configuration de Noctalia peut lancer des programmes (un bouton de
barre, un crochet de session). Un thème téléchargé chez quelqu'un ne doit changer que **l'apparence** : l'appli
vérifie donc chaque paquet contre une liste de ce qui est permis avant de l'installer, et refuse le paquet entier si
une seule règle échoue. Tes propres thèmes passent les mêmes contrôles : ce que tu exportes s'installera chez les
autres.

## 2. Deux façons de faire un thème

| | Depuis ton bureau | À la main |
|---|---|---|
| Départ | Noctalia réglé comme tu l'aimes, menu → **Créer un thème depuis mon bureau** | `python3 app/package.py new <dossier>` |
| Idéal pour | figer un réglage déjà peaufiné | un thème pensé de zéro, ou fignoler un thème capturé |
| Terminal | inutile | nécessaire pour `new`, `check`, `pack` |

Les deux finissent pareil : un dossier que l'appli vérifie, puis exporte en `.zip`. On peut les combiner :
capturer son bureau, puis retoucher les fichiers à la main (section 4).

## 3. Première façon : depuis ton bureau

1. Règle Noctalia : palette, fond d'écran, taille et police de la barre, dock, widgets du bureau (autocollants,
   horloge, lecteur).
2. Dans l'appli, ouvre le menu et choisis **Créer un thème depuis mon bureau** (Ctrl+N).
3. Remplis le nom (seul champ obligatoire), l'auteur, la description et la licence (`GPL-3.0-or-later` par défaut ;
   tout [identifiant SPDX](https://spdx.org/licenses/) convient). Clique sur **Créer**.
4. Lis la fenêtre de résultat. Elle liste tout ce qui a été **laissé de côté**, et pourquoi :

   | Laissé de côté | Pourquoi |
   |---|---|
   | la disposition des widgets de la barre | ils se règlent hors du thème ; leur allure (taille, police, couleurs) suit |
   | les applis épinglées au dock | ce sont tes applis, pas une apparence |
   | les widgets de plugins tiers | un thème ne peut utiliser que le plugin livré avec l'appli |
   | tout réglage qui lance un programme | voir section 1 |
   | un fichier qui ne peut pas voyager (un texte, un dossier de ton home) | seules des images sortent de ton home ; rien de privé |
   | une palette sans fichier, ou qui échoue aux contrôles de contraste | le thème part des couleurs de Brume (section 5) |

5. Clique sur **Ouvrir le dossier** pour voir ce qui a été fait, ou **Exporter…** pour enregistrer le `.zip` tout de
   suite.

Ce que l'appli a fait en coulisse : elle a copié ta palette, le fond d'écran affiché et chaque autocollant utilisé
par tes widgets dans un nouveau dossier, réécrit leurs chemins en `@THEME_DIR@/…` (pour qu'ils marchent où que le
thème soit installé) et le nom de ton écran en `@OUTPUT@` (pour que les widgets tombent sur l'écran de qui
l'installe), puis l'a empaqueté et importé comme n'importe quel paquet. Le nouveau thème apparaît dans la liste avec
l'étiquette « Importé ».

**Nom du dossier.** Le dossier prend le nom du thème : `Night Swim` → `night-swim`, accents retirés
(`Été brûlant` → `ete-brulant`). Un nom sans lettre latine (`夜の猫`) devient `theme-` suivi de 8 caractères tirés
du nom. Le nom affiché dans l'appli garde ses accents et son écriture dans tous les cas.

## 4. Deuxième façon : à la main

```bash
python3 app/package.py new ~/my-themes/night-swim
```

Cela crée un squelette qui passe déjà les contrôles :

```
night-swim/
├── theme.toml      nom, auteur, version, licence, palette = "night-swim"
├── palette.json    couleurs de Brume, à recolorer (section 5)
├── noctalia.toml   [theme] et [wallpaper], commentés
├── wallpapers/     tes fonds d'écran (section 6)
└── stickers/       images des widgets du bureau (section 7)
```

Le nom du dossier ne contient que des minuscules, chiffres, `-` ou `_`, et `palette` dans `theme.toml` doit lui
être égal : toutes les palettes partagent un même dossier Noctalia, deux thèmes ne doivent pas s'écraser. Remplis
`theme.toml` (champs expliqués dans [THEMES.md](THEMES.md#folder-layout)). Pour fignoler un thème capturé, ouvre son
dossier depuis la fenêtre de résultat (il est dans `~/.local/share/noctalia-themes/library/<dossier>`) et
**copie-le ailleurs** avant de le modifier : la bibliothèque appartient à l'appli, et un import la remplace.

## 5. La palette

`palette.json` contient deux modes, `dark` et `light`. Chacun a 16 rôles de couleur (`mPrimary` et le texte posé
dessus, `mOnPrimary`, et pareil pour Secondary, Tertiary, Error, Surface, SurfaceVariant, Hover), plus `mOutline`,
`mShadow` et un bloc `terminal` (texte, fond, curseur, les 16 couleurs ANSI). Les couleurs sont au format strict
`#RRGGBB`.

L'appli vérifie que chaque couleur et le texte posé dessus atteignent un **contraste de 4,5:1** (le niveau WCAG pour
un texte normal), car Noctalia ne prévient pas quand une barre est illisible : il la dessine, c'est tout. Une paire
qui échoue s'affiche ainsi :

```
dark: mPrimary/mOnPrimary contrast 2.10 < 4.5
```

Corrige en éclaircissant ou en assombrissant l'une des deux jusqu'à dépasser 4,5. Pars d'une palette livrée
(`themes/*/palette.json`) plutôt que d'un fichier vide.

## 6. Fonds d'écran

Mets-les dans `wallpapers/` en WebP, PNG ou JPEG (32 Mo maximum chacun). L'appli les montre dans sa galerie dès que
le thème est actif. Pour en afficher un aussi sur l'écran de connexion (Noctalia Greeter), nomme-le dans
`theme.toml` :

```toml
login_wallpaper = "wall_night-swim.webp"
```

Ne livre que des images que tu as faites ou que tu as le droit de partager, et indique leur origine dans
`wallpapers/SOURCES.md` (prompt et graine pour une image générée : voir
[Generate wallpapers with ComfyUI](../README.md#generate-wallpapers-with-comfyui)).

## 7. Widgets du bureau, autocollants et polices

Les widgets du bureau vont dans `noctalia.toml`, sous `[desktop_widgets]`. Chaque fichier utilisé par un widget
s'écrit comme un chemin dans le thème, et l'écran comme `@OUTPUT@` :

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

Le plus simple pour bien placer les widgets : les positionner avec l'éditeur de Noctalia, puis capturer le bureau
(section 3) et recopier les nombres. Les positions sont pensées pour une taille d'écran (voir Known limits dans le
README).

L'horloge et le lecteur de musique dessinés dans ton propre cadre viennent du plugin livré avec l'appli
(`billisdead/theme-widgets:clock` et `:player`) ; comment dessiner et découper un cadre est expliqué dans
[THEMES.md](THEMES.md#folder-layout). Les polices vont dans `fonts/` en `.ttf` ou `.otf`, avec leur fichier de
licence à côté ; les widgets les nomment par famille (`font_family`).

## 8. Vérifier

```bash
python3 app/package.py check ~/my-themes/night-swim
```

La commande lance **exactement** les contrôles d'un import et affiche `ok`, ou une ligne par problème. Les plus
courants :

| Message (affiché en anglais par `check`) | Correction |
|---|---|
| `theme.toml: missing 'author'` | ajoute le champ |
| `theme.toml: 'palette' must be the folder name 'night-swim'` | mets `palette = "night-swim"` |
| `noctalia.toml: 'bar.default.middle_click_command' can run a program, not allowed in a theme` | retire la clé |
| `noctalia.toml: '…' must point inside the theme (@THEME_DIR@/...)` | copie le fichier dans le thème et écris `@THEME_DIR@/…` |
| `notes.docx: file type not allowed` | retire-le ; permis : `.toml .json .md .txt .webp .png .jpg .jpeg .svg .ttf .otf` |
| `dark: mPrimary/mOnPrimary contrast 2.10 < 4.5` | section 5 |
| `theme.toml: login_wallpaper '…' is not a file of wallpapers/` | corrige le nom, ou range le fichier dans `wallpapers/` |

Dans l'appli, rien à lancer : **l'export** fait d'abord ce même contrôle et liste ce qu'il faut corriger.

## 9. Empaqueter ou exporter

Dans les deux cas tu obtiens `<dossier>-<version>.zip` :

- **Dans l'appli** : l'icône d'enregistrement sur la ligne du thème, puis « Enregistrer sous ». Marche pour tout
  thème de la liste, y compris ceux livrés avec l'appli.
- **Dans un terminal** : `python3 app/package.py pack ~/my-themes/night-swim` écrit `night-swim-1.0.0.zip` dans le
  dossier courant (donne un dossier ou un chemin `.zip` en second argument pour choisir).

Les scripts de fabrication (`*.py`) posés à côté des images restent hors du paquet : ce sont tes outils, pas ceux des
gens qui installent le thème.

## 10. Le tester comme quelqu'un d'autre

Dépose le `.zip` sur la zone en pointillés sous la liste des thèmes (ou clique dessus pour le choisir). L'appli le
décompresse dans un dossier privé de transit, le vérifie là, et seulement ensuite le met en place : un paquet refusé
ne laisse rien derrière lui. Applique-le, regarde chaque écran qui compte pour toi, essaie le mode sombre et le mode
clair.

Quand tu déposes le paquet d'un thème déjà installé, l'appli les compare :

| Cas | Ce qui se passe |
|---|---|
| mêmes fichiers | « déjà installé, à l’identique : rien à faire », rien ne change |
| version plus récente | elle demande avant de remplacer (bouton mis en avant) |
| même version mais fichiers différents, ou version plus ancienne | elle demande, le dit, et le bouton Remplacer est rouge |
| nom ou dossier d'un thème livré avec l'appli | refusé : ces thèmes ne se remplacent pas |

Si tu remplaces le thème actif, clique sur **Mettre à jour** (⟳ sur sa ligne) pour voir la nouvelle version sur le bureau.

## 11. Partager une nouvelle version

1. Modifie le dossier.
2. Monte `version` dans `theme.toml` (`1.0.0` → `1.0.1`) : ceux qui l'installent voient « version plus récente » au
   lieu d'un avertissement rouge.
3. Vérifie, puis empaquette ou exporte à nouveau : le nom du fichier suit la version, l'ancien `.zip` n'est pas
   écrasé.

## 12. Retirer un thème

La corbeille sur la ligne d'un thème importé le retire de la liste (jamais tant qu'il est actif : retire d'abord le
thème du bureau avec le bandeau du haut). Tes sauvegardes restent ; redéposer le `.zip` le fait revenir.

## Dépannage

- **« Ce thème ne peut pas être importé »** suivi d'une liste : chaque ligne est une règle (section 8). Corrige-les
  toutes, puis empaquette à nouveau.
- **« L’archive doit contenir un seul dossier de thème »** : tu as zippé les fichiers au lieu du dossier. Zippe le dossier
  lui-même, ou utilise `pack`, qui le fait correctement.
- **Une valeur avec `/` est refusée alors que ce n'est pas un fichier**, par exemple un format de date `"%d/%m"` :
  le contrôle prend chaque `/` pour un chemin. Utilise un autre séparateur (`"%d.%m"`, `"%d %b"`).
- **Widgets absents ou mal placés après l'installation** : le thème a été fait pour une autre taille d'écran, ou
  l'écran a changé. Applique à nouveau le thème ; les positions sont pensées pour un écran (README, Known limits).
- **L'horloge ou le lecteur restent vides** : le plugin s'active via Noctalia ; applique le thème pendant que
  Noctalia tourne, ou active « Theme Widgets » dans les réglages de plugins de Noctalia.
- **L'écran de connexion utilise une autre police** : il ne voit que les polices installées pour tout le système.
