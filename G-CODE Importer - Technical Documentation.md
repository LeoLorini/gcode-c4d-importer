# G-CODE Importer - Technical Documentation

This document explains how `G-CODE Importer V1.py` works internally. It is intended for developers, technical users, and anyone who wants to modify or extend the plugin.

For normal usage, see:

- [French instructions](G-CODE%20Importer%20-%20Instructions%20FR.md)
- [English instructions](G-CODE%20Importer%20-%20Instructions%20EN.md)

## 1. Purpose

G-CODE Importer converts slicer-generated G-code into Cinema 4D polygon meshes.

The script does not simulate a real fused print volume. Instead, it reconstructs each extrusion path as a tube following the toolpath. This makes it useful for:

- visualizing a 3D print inside Cinema 4D;
- rendering stylized print paths;
- animating a print reveal;
- inspecting multi-material G-code visually;
- generating layer-based motion graphics.

## 2. High-Level Pipeline

The import pipeline is:

1. Ask the user to select a `.gcode` file.
2. Show an import options dialog.
3. Parse the G-code into extrusion paths grouped by tool and Z height.
4. Resolve filament colors from slicer metadata.
5. Generate one polygon mesh per imported layer.
6. Group layers by filament.
7. Center the final object at the Cinema 4D origin.
8. Add materials.
9. Add a `Reveal` slider.
10. Set up either a visibility-based reveal or a MoGraph Field reveal.

## 3. Supported G-code Assumptions

The parser is optimized for G-code from PrusaSlicer, SuperSlicer, OrcaSlicer, and similar slicers that emit useful comments.

Best results require comments such as:

- `;TYPE:Perimeter`
- `;TYPE:External perimeter`
- `;WIDTH:0.45`
- `;HEIGHT:0.2`
- `; filament_colour = ...`
- `; extruder_colour = ...`

The script supports:

- `G0` / `G1` linear moves;
- `G2` / `G3` arc moves in the XY plane;
- `G00`, `G01`, `G02`, `G03` normalized command forms;
- lowercase G-code commands;
- line-numbered commands such as `N42 G1 X...`;
- relative and absolute XYZ coordinates through `G90` / `G91`;
- relative and absolute extrusion through `M83` / `M82`;
- extrusion resets through `G92`;
- tool changes through `T0`, `T1`, `T2`, etc.;
- inch mode `G20`, converted to millimeters;
- millimeter mode `G21`.

Unsupported or limited:

- `G18` / `G19` arc planes are not implemented;
- firmware retraction commands `G10` / `G11` are not visualized;
- travel moves are ignored;
- speed, acceleration, temperature, pressure advance, and fan changes are ignored;
- non-listed feature types may be skipped unless added to the feature type list.

## 4. Dialog Options

The dialog is implemented by `GCodeImportDialog`.

### Feature Types

The feature list is defined in `TYPES_AVAILABLE`.

Only paths whose current slicer feature type matches the selected list are imported. If a slicer emits a type not present in `TYPES_AVAILABLE`, it will not appear as a checkbox and may be skipped depending on the selection.

To add support for additional types, edit:

- `TYPES_AVAILABLE`
- `FEATURE_TYPE_ALIASES`

Examples of possible additions:

- `Skirt`
- `Brim`
- `Support material`
- `Wipe tower`
- `Custom`

### Tube Sides

Controls the number of radial segments used for each extrusion tube.

Higher values produce smoother paths but increase:

- point count;
- polygon count;
- memory usage;
- viewport cost;
- render cost.

### Min Path Length

Small extrusion paths are filtered during parsing.

This is done before mesh generation, so increasing `Min path length` can significantly reduce scene weight.

### Corner Subdivision Angle

Sharp corners can cause visible twisting or pinching in tube frames. The corner subdivision pass inserts extra points around corners whose turn angle is above the selected threshold.

This makes some corners visually smoother but increases geometry density.

### Arc Points Per Millimeter

Controls the tessellation density of `G2` / `G3` arcs.

The script also applies `MAX_ARC_SEGMENTS` to avoid pathological cases where a huge arc would generate millions of points.

### Close Wall Loops

When enabled, perimeter-like paths are stitched into closed loops when the end point is close enough to the start point.

This is handled by `_wall_loop_info()` and `add_tube_for_path()`.

## 5. Parsing Architecture

Main function:

```python
parse_gcode_by_filaments(filepath, allowed_types=None, min_path_len=1.0, arc_segs_per_mm=2.0)
```

It returns:

```python
filaments, metadata, stats
```

### `filaments`

Nested dictionary:

```python
{
    tool_id: {
        z_height: [
            path,
            path,
            ...
        ]
    }
}
```

Each `path` is a list of points:

```python
{
    "point": (x, y, z),
    "width": width,
    "height": height,
    "feature_type": current_type
}
```

Coordinates are stored in G-code space during parsing.

### `metadata`

Contains slicer metadata, mostly parsed from semicolon comments.

Common keys:

- `extruder_colour`
- `filament_colour`
- `filament_settings_id`
- `filament_type`
- `tool_ids`

### `stats`

Used for import feedback and warnings:

- `paths_kept`
- `paths_too_short`
- `arcs_truncated`
- `tool_changes`
- `inch_mode_used`

## 6. Command Parsing

The parser separates comments from code with:

```python
split_code_and_comment(line)
```

Command and word parsing is handled by:

```python
parse_command_and_words(code)
parse_axis_words(code)
```

The word parser accepts compact forms such as:

```text
G1 X10.0Y20.0E0.5
```

It extracts axis/value pairs with a regex and stores them in a dictionary:

```python
{"X": 10.0, "Y": 20.0, "E": 0.5}
```

Commands are normalized so `G01` becomes `G1`.

Decimal commands like `G90.1` are preserved as `G90.1`, so they are not accidentally treated as `G90`.

## 7. Extrusion Detection

The parser tracks the current XYZ and E state.

Relevant state variables:

- `x`, `y`, `z`
- `prev_e`
- `e_relative`
- `xyz_relative`
- `unit_scale`
- `current_tool`
- `current_type`
- `width`
- `height`

For linear moves:

- a move must change XYZ;
- it must include E;
- E must indicate positive extrusion.

For relative E mode (`M83`):

```python
is_extruding = e_val > 0 and moved
```

For absolute E mode (`M82`):

```python
is_extruding = e_val > prev_e and moved
```

`G92 E...` resets `prev_e`.

Non-moving E-only commands close the current path. This avoids incorrectly connecting extrusion paths across retractions or E resets.

## 8. Arc Interpolation

Arc moves are handled by:

```python
interpolate_arc(...)
```

Supported arc definitions:

- center offset using `I` / `J`;
- radius using `R`.

The script supports full circles where start and end points are the same.

Arc points are generated between the start point and end point, including Z interpolation for helical-like moves.

The arc is converted into regular path points before mesh generation. After that, arcs and lines are treated the same.

## 9. Coordinate Conversion

G-code coordinates are converted to Cinema 4D coordinates in `add_tube_for_path()`:

```python
Vector(gx, gz, gy)
```

Mapping:

| G-code | Cinema 4D |
| --- | --- |
| X | X |
| Y | Z |
| Z | Y |

This makes the print height align with Cinema 4D's Y axis.

## 10. Mesh Generation

Main mesh functions:

- `_build_frames()`
- `subdivide_sharp_corners()`
- `add_tube_for_path()`
- `create_layer_mesh()`

### Tube Rings

Each path point becomes a ring of vertices.

The ring radius is based on slicer width and height:

```python
r_w = width * 0.5
r_h = height * 0.5
```

The script creates an elliptical tube cross-section rather than a perfect circular tube. This better approximates flattened filament extrusion.

### Frames

`_build_frames()` computes tangent, normal, and binormal vectors along the path.

For mostly horizontal paths, the binormal is aligned with world up so the extrusion height remains vertical.

When a path becomes near-vertical, the function falls back to a parallel transport-like frame.

### Side Faces

Consecutive rings are connected with quads:

```python
c4d.CPolygon(a0, a1, b1, b0)
```

### Caps

Open paths receive end caps.

Closed perimeter loops are stitched from the final ring back to the first ring instead of being capped.

## 11. Closed Loop Handling

Closed loop detection is handled by:

```python
_wall_loop_info(path)
```

A path is considered a closeable wall loop when:

- its feature type is perimeter-like;
- its end point is close to its start point.

Closeable feature types:

- `Perimeter`
- `External perimeter`
- `Overhang perimeter`

If the slicer already duplicated the start point at the end of the path, the duplicate endpoint is removed before seam subdivision and stitching.

This prevents:

- zero-length segments;
- bad tangent calculations;
- twisted rings at the seam;
- duplicate geometry at the closure point.

## 12. Bounding Box And Centering

Mesh generation updates a running global bounding box.

This avoids a second full pass over all generated points.

After all layers are generated, `center_layers()` shifts the mesh points so:

- XZ center is at the Cinema 4D origin;
- minimum Y rests on `Y = 0`.

The object dimensions are reported in the completion dialog.

## 13. Materials

Materials are created per filament tool:

```python
create_material_for_filament(tool_id, color, doc)
```

Color resolution is handled by:

```python
choose_tool_colors(tool_ids, metadata)
```

Priority:

1. `extruder_colour`
2. `filament_colour`
3. generated fallback colors

Materials are assigned to the filament parent object only. This keeps the object manager lighter than assigning one texture tag per layer.

If a renderer does not inherit parent texture tags correctly, the user can manually assign materials to child meshes.

## 14. Object Hierarchy

The imported result is organized under one main parent Null.

In `Visibility` mode:

```text
ImportName
  Group_Filament_T0
    Layer_0.200
    Layer_0.350
  Group_Filament_T1
    Layer_...
```

In `MoGraph Field` mode:

```text
ImportName
  Fracture_Filament_T0
    Layer_0.200
    Layer_0.350
  Fracture_Filament_T1
    Layer_...
  Plain_FilamentReveal
  LinearField_FilamentReveal
```

## 15. Reveal Slider

The main parent receives a user data slider named:

```text
Reveal
```

The stored value uses Cinema 4D percent units:

- `0.0` means `0%`;
- `1.0` means `100%`.

The visual slider is clamped to `0%` to `100%`, but manual typed values can go below or above that range.

## 16. Reveal Mode: Visibility

Function:

```python
setup_hide_reveal(parent_null, layer_entries, doc)
```

Each layer receives a `Reveal Order` integer user data field.

A Python tag on the parent:

1. reads the parent `Reveal` value;
2. computes how many layers should be visible;
3. traverses child objects;
4. toggles editor/render visibility.

Advantages:

- lighter;
- stable;
- no motion blur bug;
- good for heavy scenes.

Drawbacks:

- not a smooth reveal;
- layers pop on/off;
- less flexible for motion design.

## 17. Reveal Mode: MoGraph Field

Function:

```python
setup_field_reveal(parent_null, fracture_objs, doc, obj_height)
```

This mode creates:

- one `Plain_FilamentReveal` effector;
- one `LinearField_FilamentReveal`;
- one Python tag driver;
- one Fracture object per filament.

The Plain Effector applies negative uniform scale. The Linear Field controls where the scale effect applies. The Python tag moves the field along Y based on the `Reveal` slider.

Advantages:

- smooth reveal;
- animatable;
- editable with Cinema 4D MoGraph and Fields;
- better for motion design.

Drawbacks:

- heavier than visibility mode;
- can be renderer-dependent;
- a zero or near-zero Linear Field size may cause motion blur artifacts in some workflows.

## 18. Undo And Scene Updates

The main import process wraps object creation in Cinema 4D undo calls:

- `doc.StartUndo()`
- `doc.AddUndo(...)`
- `doc.EndUndo()`

At the end, the script calls:

```python
c4d.EventAdd()
```

This refreshes the Cinema 4D scene.

## 19. Performance Notes

The heaviest costs are:

- number of G-code paths;
- number of path points;
- `Tube sides`;
- arc tessellation density;
- imported feature types;
- number of layers;
- selected reveal mode.

For lighter scenes:

- import fewer feature types;
- use `Tube sides` 4 or 6;
- use `Arc pts/mm` 1;
- increase `Min path length`;
- use `Visibility` mode.

For cleaner visuals:

- use `Tube sides` 8 or 12;
- use `Arc pts/mm` 2 or 3;
- enable `Close wall loops`;
- try `Corner subdiv angle` around 45 degrees.

## 20. Extending The Plugin

Common extension points:

### Add Feature Types

Edit:

```python
TYPES_AVAILABLE
FEATURE_TYPE_ALIASES
```

### Change Default Import Settings

Edit the defaults in:

```python
GCodeImportDialog.__init__()
GCodeImportDialog.InitValues()
```

### Change Material Behavior

Edit:

```python
create_material_for_filament()
assign_material_to_object()
choose_tool_colors()
```

### Change Mesh Style

Edit:

```python
add_tube_for_path()
_build_frames()
create_layer_mesh()
```

### Change Reveal Behavior

Edit:

```python
setup_hide_reveal()
setup_field_reveal()
add_reveal_slider()
```

## 21. Known Edge Cases

- G-code from slicers that remove comments may import with default width/height or miss feature filtering.
- Some slicers use feature names not listed in the dialog.
- Very dense infill can produce very large Cinema 4D scenes.
- Non-XY arc planes are not supported.
- Volumetric E is not intended for this importer.
- Renderer-specific material inheritance can vary.
- MoGraph reveal may need renderer-specific motion blur adjustments.

## 22. License

The project is released under the MIT License. See `LICENSE`.

## 23. Disclaimer

This script is vibe-coded and provided as-is. It may contain bugs or unsupported edge cases. Always check the imported result before using it in production.
