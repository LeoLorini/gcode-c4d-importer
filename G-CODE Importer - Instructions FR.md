# G-CODE Importer - Guide rapide

Français | [English](G-CODE%20Importer%20-%20Instructions%20EN.md)

`G-CODE Importer V1.py` est un script Python pour Cinema 4D. Il importe un fichier G-code exporté depuis un slicer 3D et le transforme en meshes organisés par filament et par layer.

Le plugin conserve les différents matériaux et couleurs appliqués depuis PrusaSlicer quand les informations sont présentes dans le G-code. Les matériaux sont assignés aux parents de filaments (`T0`, `T1`, `T2`, etc.) pour garder une scène légère.

## 1. Exporter depuis PrusaSlicer

Passe PrusaSlicer en mode `Expert` avec le bouton `Simple / Advanced / Expert` en haut à droite.

Réglages conseillés :

- `Printer Settings > General > Firmware > G-code flavor` : `Marlin (legacy)`.
- `Printer Settings > General > Advanced > Use relative E distances` : activé.
- `Printer Settings > General > Advanced > Use volumetric E` : désactivé.
- `Printer Settings > General > Advanced > Use firmware retraction` : désactivé de préférence.
- `Printer Settings > General > Support binary G-code` : désactivé si l'option existe.
- `Configuration > Preferences > Other > Use binary G-code when the printer supports it` : désactivé.

Ensuite :

1. Clique sur `Slice now`.
2. Vérifie rapidement le résultat dans `Preview`.
3. Clique sur `Export G-code`.
4. N'exporte pas en `.bgcode` ou en format binaire.

Ces réglages sont recommandés pour un fichier destiné à Cinema 4D. Si le fichier doit aussi être imprimé réellement, garde les réglages nécessaires à ton imprimante.

## 2. Installer ou lancer dans Cinema 4D

Option rapide :

1. Dans Cinema 4D, va dans `Extensions > User Scripts > Run Script`.
2. Sélectionne `G-CODE Importer V1.py`.
3. Choisis ton fichier `.gcode`.
4. Règle les options d'import.
5. Clique sur `Import`.

Option installation :

1. Dans Cinema 4D, va dans `Extensions > User Scripts > Script Folder`.
2. Place `G-CODE Importer V1.py` dans ce dossier.
3. Redémarre Cinema 4D si le script n'apparaît pas tout de suite.
4. Lance-le depuis `Extensions > User Scripts`.

Si tu ne trouves pas le dossier des scripts :

1. Va dans `Edit > Preferences`.
2. Tout en bas, clique sur `Open Preferences Folder`.
3. Place le script dans le dossier `library/scripts` ou le dossier de scripts utilisateur équivalent.

## 3. Options d'import

| Option | À quoi ça sert | Conseil rapide |
| --- | --- | --- |
| `Feature types to import` | Choisit les types de lignes à importer. | Pour un import léger, garde seulement `External perimeter` et `Perimeter`. Pour un import complet, laisse tout coché. |
| `Tube sides` | Définit la rondeur des extrusions. | `4-6` est rapide, `8` est un bon compromis, `12+` est plus propre mais plus lourd. |
| `Min path length` | Supprime les micro-chemins. | `1.0 mm` est une bonne base. Mets `0` si des détails disparaissent. |
| `Corner subdiv angle` | Adoucit certains coins. | Laisse `0` pour aller vite. Essaie `45` si les angles ont des artefacts. |
| `Arc pts/mm` | Définit la qualité des courbes. | `1` est rapide, `2` est recommandé, `3+` est plus lourd. |
| `Close wall loops` | Ferme les périmètres quand le début et la fin sont proches. | À laisser activé dans la plupart des cas. |
| `Reveal mode` | Choisit la méthode de révélation. | Voir la section suivante. |

## 4. Choisir le mode Reveal

`Visibility`

- Avantages : plus léger, plus efficace, plus stable, pas de bug de motion blur.
- Défauts : pas vraiment animable de façon fluide, car les layers apparaissent/disparaissent par visibilité.
- À utiliser si tu veux un import propre, rapide et fiable.

`MoGraph Field`

- Avantages : permet une vraie animation de révélation, modifiable ensuite avec les outils MoGraph et Field de Cinema 4D.
- Défauts : un peu plus gourmand en ressources. Possible bug de motion blur si le `Linear Field` a une taille à zéro ou quasi zéro selon le renderer.
- À utiliser si tu veux animer l'impression ou customiser l'effet après import.

## 5. Après l'import

Le script crée :

- Un Null parent principal.
- Un groupe ou Fracture par filament.
- Des meshes par layer.
- Des matériaux par filament, récupérés depuis les couleurs PrusaSlicer quand elles existent.
- Un slider `Reveal` sur le Null principal.

Pour utiliser le slider :

1. Sélectionne le Null principal.
2. Va dans les paramètres utilisateur.
3. Anime `Reveal` de `0%` à `100%`.

Tu peux aussi taper une valeur sous `0%` ou au-dessus de `100%` pour pousser l'effet hors de l'objet.

## 6. Problèmes fréquents

Rien ne s'importe :

- Vérifie que tu as bien exporté un `.gcode`, pas un `.bgcode`.
- Mets `Min path length` à `0`.
- Laisse tous les `Feature types` cochés pour tester.

Cinema 4D ralentit :

- Réduis `Tube sides`.
- Mets `Arc pts/mm` à `1`.
- Importe seulement les périmètres.
- Utilise le mode `Visibility`.

Couleurs incorrectes :

- Vérifie les couleurs de filament dans PrusaSlicer.
- Les matériaux sont assignés aux parents de filaments. Si ton renderer ne les hérite pas correctement, applique manuellement le matériau aux meshes enfants.

## 7. Note

Ce script est open source et vibe codé. Il est prévu pour aider rapidement dans Cinema 4D, mais des erreurs ou cas limites peuvent être présents. Vérifie toujours le résultat importé avant de l'utiliser en production.
