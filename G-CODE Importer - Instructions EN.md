# G-CODE Importer - Quick Guide

[French](G-CODE%20Importer%20-%20Instructions%20FR.md) | English

`G-CODE Importer V1.py` is a Python script for Cinema 4D. It imports a G-code file exported from a 3D slicer and turns it into meshes organized by filament and by layer.

The plugin keeps the different materials and colors assigned in PrusaSlicer when that information is present in the G-code. Materials are assigned to the filament parent objects (`T0`, `T1`, `T2`, etc.) to keep the scene lightweight.

## 1. Export From PrusaSlicer

Switch PrusaSlicer to `Expert` mode using the `Simple / Advanced / Expert` button in the top-right corner.

Recommended settings:

- `Printer Settings > General > Firmware > G-code flavor`: `Marlin (legacy)`.
- `Printer Settings > General > Advanced > Use relative E distances`: enabled.
- `Printer Settings > General > Advanced > Use volumetric E`: disabled.
- `Printer Settings > General > Advanced > Use firmware retraction`: preferably disabled.
- `Printer Settings > General > Support binary G-code`: disabled if the option exists.
- `Configuration > Preferences > Other > Use binary G-code when the printer supports it`: disabled.

Then:

1. Click `Slice now`.
2. Quickly check the result in `Preview`.
3. Click `Export G-code`.
4. Do not export as `.bgcode` or any binary format.

These settings are recommended for a file meant for Cinema 4D. If the file also needs to be printed on a real printer, keep the settings required by your printer.

## 2. Install Or Run In Cinema 4D

Quick run:

1. In Cinema 4D, go to `Extensions > User Scripts > Run Script`.
2. Select `G-CODE Importer V1.py`.
3. Select your `.gcode` file.
4. Choose the import options.
5. Click `Import`.

Install option:

1. In Cinema 4D, go to `Extensions > User Scripts > Script Folder`.
2. Place `G-CODE Importer V1.py` in that folder.
3. Restart Cinema 4D if the script does not appear immediately.
4. Run it from `Extensions > User Scripts`.

If you cannot find the scripts folder:

1. Go to `Edit > Preferences`.
2. At the bottom, click `Open Preferences Folder`.
3. Place the script in `library/scripts` or the equivalent user scripts folder.

## 3. Import Options

| Option | What it does | Quick advice |
| --- | --- | --- |
| `Feature types to import` | Chooses which line types to import. | For a lightweight import, keep only `External perimeter` and `Perimeter`. For a full import, keep everything checked. |
| `Tube sides` | Controls how round the extrusions are. | `4-6` is fast, `8` is a good compromise, `12+` is cleaner but heavier. |
| `Min path length` | Removes tiny paths. | `1.0 mm` is a good starting point. Use `0` if small details disappear. |
| `Corner subdiv angle` | Smooths some corners. | Keep `0` for speed. Try `45` if corners show artifacts. |
| `Arc pts/mm` | Controls curve quality. | `1` is fast, `2` is recommended, `3+` is heavier. |
| `Close wall loops` | Closes perimeter loops when start and end points are close. | Keep it enabled in most cases. |
| `Reveal mode` | Chooses the reveal method. | See the next section. |

## 4. Choose The Reveal Mode

`Visibility`

- Pros: lighter, more efficient, more stable, no motion blur bug.
- Cons: not really suitable for smooth animation, because layers simply appear or disappear.
- Use it if you want a clean, fast, reliable import.

`MoGraph Field`

- Pros: allows a real reveal animation, and can be customized afterward with Cinema 4D MoGraph and Field tools.
- Cons: a bit more resource-heavy. Possible motion blur bug if the `Linear Field` size is zero or nearly zero depending on the renderer.
- Use it if you want to animate the print or customize the reveal after import.

## 5. After Import

The script creates:

- One main parent Null.
- One group or Fracture object per filament.
- Layer meshes.
- Materials per filament, recovered from PrusaSlicer colors when available.
- A `Reveal` slider on the main parent Null.

To use the slider:

1. Select the main parent Null.
2. Go to the user parameters.
3. Animate `Reveal` from `0%` to `100%`.

You can also type values below `0%` or above `100%` if you want to push the effect outside the object.

## 6. Common Issues

Nothing imports:

- Make sure you exported a `.gcode`, not a `.bgcode`.
- Set `Min path length` to `0`.
- Keep all `Feature types` checked for testing.

Cinema 4D slows down:

- Lower `Tube sides`.
- Set `Arc pts/mm` to `1`.
- Import only perimeters.
- Use `Visibility` mode.

Wrong colors:

- Check the filament colors in PrusaSlicer.
- Materials are assigned to filament parent objects. If your renderer does not inherit them correctly, manually apply the material to the child meshes.

## 7. Note

This script is open source and vibe-coded. It is meant to help quickly in Cinema 4D, but errors or edge cases may still exist. Always check the imported result before using it in production.
