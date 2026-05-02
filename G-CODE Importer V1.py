import c4d
import colorsys
import math
import os
import random
import re
from c4d import gui, Vector
from c4d.modules import mograph

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

TYPES_AVAILABLE = [
    "External perimeter",
    "Perimeter",
    "Overhang perimeter",
    "Top solid infill",
    "Solid infill",
    "Internal infill",
    "Bridge infill",
]

# Dialog IDs
ID_CHECK_START   = 10100
ID_SIDES_EDIT    = 10201
ID_MIN_LEN_EDIT  = 10202
ID_CORNER_ANGLE  = 10203
ID_CLOSE_LOOPS   = 10204
ID_ARC_SEGS      = 10205
ID_MODE_COMBO    = 10206
ID_OK            = 10300
ID_CANCEL        = 10301

# Reveal mode values (used both in dialog combobox AND main routing)
MODE_FIELD = 0
MODE_HIDE  = 1

FEATURE_TYPE_ALIASES = {
    "external perimeter": "External perimeter",
    "perimeter": "Perimeter",
    "overhang perimeter": "Overhang perimeter",
    "top solid infill": "Top solid infill",
    "solid infill": "Solid infill",
    "internal infill": "Internal infill",
    "bridge infill": "Bridge infill",
}

# Slider extended bounds. Stored value uses 1.0 == 100% (DESC_UNIT_PERCENT).
# Manual entry is allowed in this whole range; the visual slider is capped to [0, 1].
SLIDER_HARD_MIN = -10.0   # = -1000%
SLIDER_HARD_MAX =  10.0   # = +1000%

# Safety cap against pathological arcs creating millions of mesh points.
MAX_ARC_SEGMENTS = 1024

COMMAND_RE = re.compile(r"\s*([A-Za-z])\s*0*(\d+(?:\.\d+)?)")
WORD_RE = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)")


# ---------------------------------------------------------------------------
# DIALOG
# ---------------------------------------------------------------------------

class GCodeImportDialog(c4d.gui.GeDialog):
    def __init__(self):
        self.selected_types       = []
        self.sides                = 8
        self.min_path_len         = 1.0
        self.corner_angle_deg     = 0.0
        self.close_wall_loops     = True
        self.arc_segments_per_mm  = 2
        self.reveal_mode          = MODE_FIELD
        self.ok_clicked           = False

    def CreateLayout(self):
        self.SetTitle("G-Code Import Options")

        # ── Feature types ──────────────────────────────────────────────────
        self.GroupBegin(1000, c4d.BFH_SCALEFIT, 1, 0, "Feature types to import")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(8, 8, 8, 8)
        for i, t in enumerate(TYPES_AVAILABLE):
            self.AddCheckbox(ID_CHECK_START + i, c4d.BFH_LEFT, 240, 14, t)
        self.GroupEnd()

        # ── Geometry settings ──────────────────────────────────────────────
        self.GroupBegin(1001, c4d.BFH_SCALEFIT, 2, 0, "Geometry settings")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(8, 8, 8, 8)
        self.AddStaticText(0, c4d.BFH_LEFT, 160, 14, "Tube sides (4-24):")
        self.AddEditNumberArrows(ID_SIDES_EDIT, c4d.BFH_LEFT, 60, 14)
        self.AddStaticText(0, c4d.BFH_LEFT, 160, 14, "Min path length (mm):")
        self.AddEditSlider(ID_MIN_LEN_EDIT, c4d.BFH_SCALEFIT, 160, 14)
        self.AddStaticText(0, c4d.BFH_LEFT, 160, 14, "Corner subdiv angle (deg):")
        self.AddEditNumberArrows(ID_CORNER_ANGLE, c4d.BFH_LEFT, 60, 14)
        self.AddStaticText(0, c4d.BFH_LEFT, 160, 14, "Arc pts/mm (1-5):")
        self.AddEditNumberArrows(ID_ARC_SEGS, c4d.BFH_LEFT, 60, 14)
        self.AddCheckbox(ID_CLOSE_LOOPS, c4d.BFH_LEFT, 220, 14, "Close wall loops")
        self.GroupEnd()

        # ── Reveal mode ────────────────────────────────────────────────────
        self.GroupBegin(1003, c4d.BFH_SCALEFIT, 2, 0, "Reveal mode")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(8, 8, 8, 8)
        self.AddStaticText(0, c4d.BFH_LEFT, 160, 14, "Reveal mode:")
        self.AddComboBox(ID_MODE_COMBO, c4d.BFH_LEFT, 220, 14)
        self.AddChild(ID_MODE_COMBO, MODE_FIELD, "MoGraph Field (continuous scale)")
        self.AddChild(ID_MODE_COMBO, MODE_HIDE,  "Visibility (layer-by-layer hide)")
        self.GroupEnd()

        # ── Buttons ────────────────────────────────────────────────────────
        self.GroupBegin(1002, c4d.BFH_CENTER, 2, 0, "")
        self.GroupBorderSpace(8, 6, 8, 8)
        self.AddButton(ID_OK,     c4d.BFH_LEFT, 80, 18, "Import")
        self.AddButton(ID_CANCEL, c4d.BFH_LEFT, 80, 18, "Cancel")
        self.GroupEnd()
        return True

    def InitValues(self):
        # All feature types ON by default
        for i in range(len(TYPES_AVAILABLE)):
            self.SetBool(ID_CHECK_START + i, True)
        self.SetLong(ID_SIDES_EDIT, 8)
        self.SetReal(ID_MIN_LEN_EDIT, 1.0)
        self.SetReal(ID_CORNER_ANGLE, 0.0)
        self.SetLong(ID_ARC_SEGS, 2)
        self.SetBool(ID_CLOSE_LOOPS, True)
        self.SetInt32(ID_MODE_COMBO, MODE_FIELD)
        return True

    def Command(self, id, msg):
        if id == ID_OK:
            self.selected_types = [
                t for i, t in enumerate(TYPES_AVAILABLE)
                if self.GetBool(ID_CHECK_START + i)
            ]
            self.sides                = max(4, min(24, self.GetLong(ID_SIDES_EDIT)))
            self.min_path_len         = max(0.0, self.GetReal(ID_MIN_LEN_EDIT))
            self.corner_angle_deg     = max(0.0, min(180.0, self.GetReal(ID_CORNER_ANGLE)))
            self.arc_segments_per_mm  = max(1, min(5, self.GetLong(ID_ARC_SEGS)))
            self.close_wall_loops     = self.GetBool(ID_CLOSE_LOOPS)
            self.reveal_mode          = self.GetInt32(ID_MODE_COMBO)
            self.ok_clicked = True
            self.Close()
        elif id == ID_CANCEL:
            self.ok_clicked = False
            self.Close()
        return True


# ---------------------------------------------------------------------------
# ARC INTERPOLATION (G2/G3)
# ---------------------------------------------------------------------------

def _arc_center_from_radius(x_start, y_start, x_end, y_end, r_value, clockwise):
    radius = abs(r_value)
    dx = x_end - x_start
    dy = y_end - y_start
    chord = math.sqrt(dx * dx + dy * dy)

    if radius < 1e-6 or chord < 1e-8:
        return None

    half_chord = chord * 0.5
    if radius < half_chord:
        # Invalid radius for the chord. Clamp instead of failing the import.
        radius = half_chord

    mx = (x_start + x_end) * 0.5
    my = (y_start + y_end) * 0.5
    h = math.sqrt(max(0.0, radius * radius - half_chord * half_chord))
    px = -dy / chord
    py = dx / chord

    candidates = [
        (mx + px * h, my + py * h),
        (mx - px * h, my - py * h),
    ]
    want_large_arc = r_value < 0.0
    best = candidates[0]
    best_score = 1e18

    for cx, cy in candidates:
        angle_start = math.atan2(y_start - cy, x_start - cx)
        angle_end   = math.atan2(y_end   - cy, x_end   - cx)
        if clockwise:
            if angle_end >= angle_start:
                angle_end -= 2.0 * math.pi
        else:
            if angle_end <= angle_start:
                angle_end += 2.0 * math.pi
        sweep = abs(angle_end - angle_start)
        is_large_arc = sweep > math.pi + 1e-8
        score = 0.0 if is_large_arc == want_large_arc else 1.0
        score += abs(sweep - math.pi) * 1e-6
        if score < best_score:
            best_score = score
            best = (cx, cy)

    return best


def interpolate_arc(x_start, y_start, z_start, x_end, y_end, z_end,
                    i_off=None, j_off=None, r_value=None,
                    clockwise=False, width=0.4, height=0.2,
                    segs_per_mm=2.0, arc_truncated_counter=None):
    """
    Returns the points to insert between (x_start..z_start) and (x_end..z_end).
    arc_truncated_counter is an optional [int] (single-element list, used as
    a mutable counter) incremented when MAX_ARC_SEGMENTS clamps the resolution.
    """
    if i_off is not None or j_off is not None:
        i_off = 0.0 if i_off is None else i_off
        j_off = 0.0 if j_off is None else j_off
        cx = x_start + i_off
        cy = y_start + j_off
    elif r_value is not None:
        center = _arc_center_from_radius(x_start, y_start, x_end, y_end, r_value, clockwise)
        if center is None:
            return [{"point": (x_end, y_end, z_end), "width": width, "height": height}]
        cx, cy = center
    else:
        return [{"point": (x_end, y_end, z_end), "width": width, "height": height}]

    radius = math.sqrt((x_start - cx) * (x_start - cx) + (y_start - cy) * (y_start - cy))
    if radius < 1e-6:
        return [{"point": (x_end, y_end, z_end), "width": width, "height": height}]

    angle_start = math.atan2(y_start - cy, x_start - cx)
    angle_end   = math.atan2(y_end   - cy, x_end   - cx)
    same_endpoint = math.sqrt((x_end - x_start) * (x_end - x_start) + (y_end - y_start) * (y_end - y_start)) < 1e-8

    if same_endpoint:
        angle_end = angle_start - 2.0 * math.pi if clockwise else angle_start + 2.0 * math.pi
    elif clockwise:
        if angle_end >= angle_start:
            angle_end -= 2.0 * math.pi
    else:
        if angle_end <= angle_start:
            angle_end += 2.0 * math.pi

    sweep = angle_end - angle_start
    arc_len = abs(sweep) * radius
    if arc_len < 1e-4:
        return [{"point": (x_end, y_end, z_end), "width": width, "height": height}]

    requested = max(2, int(math.ceil(arc_len * segs_per_mm)))
    n_segs = min(MAX_ARC_SEGMENTS, requested)
    if requested > MAX_ARC_SEGMENTS and arc_truncated_counter is not None:
        arc_truncated_counter[0] += 1

    points = []
    for k in range(1, n_segs + 1):
        t  = float(k) / float(n_segs)
        a  = angle_start + t * sweep
        px = cx + radius * math.cos(a)
        py = cy + radius * math.sin(a)
        pz = z_start + (z_end - z_start) * t
        points.append({"point": (px, py, pz), "width": width, "height": height})
    return points


# ---------------------------------------------------------------------------
# G-CODE PARSING HELPERS
# ---------------------------------------------------------------------------

def normalize_feature_type(raw_type):
    if not raw_type:
        return "Unknown"
    cleaned = " ".join(raw_type.strip().split())
    return FEATURE_TYPE_ALIASES.get(cleaned.lower(), cleaned)


def split_code_and_comment(line):
    code, _, comment = line.partition(";")
    return code.strip(), comment.strip()


def parse_axis_words(code):
    values = {}
    for axis, raw_value in WORD_RE.findall(code):
        axis = axis.upper()
        if axis in ("G", "M", "T", "N"):
            continue
        try:
            values[axis] = float(raw_value)
        except:
            continue
    return values


def parse_command_and_words(code):
    m = COMMAND_RE.match(code)
    if not m:
        return None, {}

    prefix = m.group(1).upper()
    if prefix == "N":
        m = COMMAND_RE.match(code, m.end())
        if not m:
            return None, {}
        prefix = m.group(1).upper()

    raw_number = m.group(2)
    if "." in raw_number:
        number = raw_number.rstrip("0").rstrip(".")
    else:
        try:
            number = str(int(raw_number))
        except:
            return None, {}

    return "{}{}".format(prefix, number), parse_axis_words(code[m.end():])


def derive_import_name(filepath):
    stem = os.path.splitext(os.path.basename(filepath))[0]

    metadata_markers = [
        re.compile(r"_(\d+(?:\.\d+)?)n(?:_|$)", re.IGNORECASE),
        re.compile(r"_(\d+(?:\.\d+)?)mm(?:_|$)", re.IGNORECASE),
        re.compile(r"_\d+H\d+M(?:_|$)", re.IGNORECASE),
        re.compile(r"_\d+M(?:_|$)", re.IGNORECASE),
    ]

    cut_index = len(stem)
    for pattern in metadata_markers:
        match = pattern.search(stem)
        if match:
            cut_index = min(cut_index, match.start())

    cleaned = stem[:cut_index].rstrip("_- ")
    return cleaned if cleaned else stem


def parse_prusa_list(raw_value):
    values = []
    current = []
    in_quotes = False
    escape = False

    for ch in raw_value:
        if escape:
            current.append(ch)
            escape = False
            continue
        if ch == "\\" and in_quotes:
            escape = True
            continue
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if ch == ";" and not in_quotes:
            values.append("".join(current).strip())
            current = []
            continue
        current.append(ch)

    values.append("".join(current).strip())
    return values


def parse_hex_color(raw):
    if not raw:
        return None
    raw = raw.strip()
    if not re.match(r"^#[0-9A-Fa-f]{6}$", raw):
        return None
    return raw.upper()


def hex_to_vector(hex_color):
    return Vector(
        int(hex_color[1:3], 16) / 255.0,
        int(hex_color[3:5], 16) / 255.0,
        int(hex_color[5:7], 16) / 255.0
    )


def choose_tool_colors(tool_ids, metadata):
    resolved = {}
    extruder_values = metadata.get("extruder_colour", [])
    filament_values = metadata.get("filament_colour", [])

    for tid in tool_ids:
        color = None
        if tid < len(extruder_values):
            color = parse_hex_color(extruder_values[tid])
        if color is None and tid < len(filament_values):
            color = parse_hex_color(filament_values[tid])
        if color:
            resolved[tid] = hex_to_vector(color)

    return resolved


def generate_distinct_tool_colors(tool_ids, seed_text):
    rng = random.Random(seed_text)
    colors = {}
    used_hues = []

    for tid in sorted(tool_ids):
        best_hue = None
        best_distance = -1.0
        for _ in range(24):
            hue = rng.random()
            if not used_hues:
                best_hue = hue
                break
            distance = min(min(abs(hue - prev), 1.0 - abs(hue - prev)) for prev in used_hues)
            if distance > best_distance:
                best_distance = distance
                best_hue = hue

        used_hues.append(best_hue)
        sat = 0.60 + rng.random() * 0.25
        val = 0.75 + rng.random() * 0.20
        r, g, b = colorsys.hsv_to_rgb(best_hue, sat, val)
        colors[tid] = Vector(r, g, b)

    return colors


# ---------------------------------------------------------------------------
# PARSE GCODE
# ---------------------------------------------------------------------------

def parse_gcode_by_filaments(filepath, allowed_types=None,
                             min_path_len=1.0, arc_segs_per_mm=2.0):
    """
    Returns (filaments, metadata, stats) where stats is a dict:
        {
            "paths_kept":      int,
            "paths_too_short": int,   # filtered by min_path_len
            "arcs_truncated":  int,   # arcs clamped at MAX_ARC_SEGMENTS
            "tool_changes":    int,
            "inch_mode_used":  bool,  # G20 was encountered and converted to mm
        }
    """
    width_res = [
        re.compile(r"\s*; LINE_WIDTH: ([0-9]+(?:\.[0-9]+)?)\s*$"),
        re.compile(r"\s*;WIDTH:([0-9]+(?:\.[0-9]+)?)\s*$"),
    ]
    height_res = [
        re.compile(r"\s*; LAYER_HEIGHT: ([0-9]+(?:\.[0-9]+)?)\s*$"),
        re.compile(r"\s*;HEIGHT:([0-9]+(?:\.[0-9]+)?)\s*$"),
    ]
    type_res = [
        re.compile(r"\s*; FEATURE:(.*)$"),
        re.compile(r"\s*;TYPE:(.*)$"),
    ]

    def match_first(patterns, line):
        for p in patterns:
            m = p.match(line)
            if m: return m
        return None

    if allowed_types is not None:
        allowed_types = set(allowed_types)

    filaments    = {}
    current_path = []
    x = y = z    = 0.0
    prev_e       = 0.0
    e_relative   = False
    xyz_relative = False
    unit_scale   = 1.0
    width        = 0.4
    height       = 0.2
    current_type = "Unknown"
    current_tool = 0
    extruding    = False
    metadata     = {}
    tool_ids     = set([0])

    arc_truncated_counter = [0]
    stats = {
        "paths_kept":      0,
        "paths_too_short": 0,
        "arcs_truncated":  0,
        "tool_changes":    0,
        "inch_mode_used":  False,
    }

    def path_length(path):
        total = 0.0
        for i in range(1, len(path)):
            p0, p1 = path[i-1]["point"], path[i]["point"]
            dx, dy, dz = p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2]
            total += math.sqrt(dx*dx + dy*dy + dz*dz)
        return total

    def close_path():
        nonlocal current_path, extruding
        if extruding and len(current_path) >= 2:
            if path_length(current_path) >= min_path_len:
                zkey = round(current_path[0]["point"][2], 3)
                tool_layers = filaments.setdefault(current_tool, {})
                tool_layers.setdefault(zkey, []).append(current_path)
                stats["paths_kept"] += 1
            else:
                stats["paths_too_short"] += 1
        current_path = []
        extruding    = False

    def scaled_value(words, axis, default=None):
        if axis not in words:
            return default
        value = words[axis]
        if axis in ("X", "Y", "Z", "I", "J", "R"):
            return value * unit_scale
        return value

    def resolve_axis(words, axis, current):
        value = scaled_value(words, axis)
        if value is None:
            return current
        return current + value if xyz_relative else value

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()

            if line.startswith(";"):
                if "=" in line:
                    key, value = line[1:].split("=", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key in ("extruder_colour", "filament_colour", "filament_settings_id", "filament_type"):
                        metadata[key] = parse_prusa_list(value)
                m_w = match_first(width_res, line)
                if m_w:
                    try: width = float(m_w.group(1))
                    except: pass
                m_h = match_first(height_res, line)
                if m_h:
                    try: height = float(m_h.group(1))
                    except: pass
                m_t = match_first(type_res, line)
                if m_t:
                    current_type = normalize_feature_type(m_t.group(1))
                continue

            code, _ = split_code_and_comment(line)
            command, words = parse_command_and_words(code)
            if command is None:
                continue

            if command.startswith("T"):
                close_path()
                current_tool = int(command[1:])
                tool_ids.add(current_tool)
                stats["tool_changes"] += 1
                continue

            if command == "M82": e_relative = False; continue
            if command == "M83": e_relative = True;  continue
            if command == "G90": xyz_relative = False; continue
            if command == "G91": xyz_relative = True;  continue
            if command == "G20":
                unit_scale = 25.4
                stats["inch_mode_used"] = True
                continue
            if command == "G21":
                unit_scale = 1.0
                continue
            if command == "G92":
                if "X" in words: x = scaled_value(words, "X", x)
                if "Y" in words: y = scaled_value(words, "Y", y)
                if "Z" in words: z = scaled_value(words, "Z", z)
                if "E" in words: prev_e = words["E"]
                continue

            # G2 / G3
            if command == "G2" or command == "G3":
                cw  = command == "G2"
                new_x = resolve_axis(words, "X", x)
                new_y = resolve_axis(words, "Y", y)
                new_z = resolve_axis(words, "Z", z)
                i_off = scaled_value(words, "I")
                j_off = scaled_value(words, "J")
                r_value = scaled_value(words, "R")
                has_arc_center = i_off is not None or j_off is not None or r_value is not None

                if "E" in words:
                    ev    = words["E"]
                    moved = (new_x != x) or (new_y != y) or (new_z != z) or has_arc_center
                    if e_relative: is_arc = ev > 0 and moved
                    else:          is_arc = (ev > prev_e) and moved
                    prev_e   = ev
                    type_ok  = (allowed_types is None) or (current_type in allowed_types)
                    if is_arc and type_ok:
                        if not extruding:
                            current_path = [{"point": (x, y, z), "width": width, "height": height, "feature_type": current_type}]
                        arc_pts = interpolate_arc(x, y, z, new_x, new_y, new_z,
                                                  i_off, j_off, r_value,
                                                  cw, width, height, arc_segs_per_mm,
                                                  arc_truncated_counter)
                        for pt in arc_pts:
                            pt["feature_type"] = current_type
                        current_path.extend(arc_pts)
                        extruding = True
                    else:
                        close_path()
                else:
                    close_path()
                x, y, z = new_x, new_y, new_z
                continue

            # G0 / G1
            if command != "G0" and command != "G1":
                continue
            new_x = resolve_axis(words, "X", x)
            new_y = resolve_axis(words, "Y", y)
            new_z = resolve_axis(words, "Z", z)
            e_val = words.get("E")
            has_e = e_val is not None

            moved = (new_x != x) or (new_y != y) or (new_z != z)
            if has_e and e_val is not None:
                if e_relative: is_extruding = e_val > 0 and moved
                else:          is_extruding = (e_val > prev_e) and moved
                prev_e = e_val
            else:
                is_extruding = False

            if not moved:
                if has_e:
                    close_path()
                x, y, z = new_x, new_y, new_z
                continue

            type_ok = (allowed_types is None) or (current_type in allowed_types)
            if is_extruding and type_ok:
                if not extruding:
                    current_path = [{"point": (x, y, z), "width": width, "height": height, "feature_type": current_type}]
                current_path.append({"point": (new_x, new_y, new_z), "width": width, "height": height, "feature_type": current_type})
                extruding = True
            else:
                close_path()
            x, y, z = new_x, new_y, new_z

    close_path()
    metadata["tool_ids"] = sorted(tool_ids)
    stats["arcs_truncated"] = arc_truncated_counter[0]
    return filaments, metadata, stats


# ---------------------------------------------------------------------------
# TUBE GENERATION (advanced: vertical-aligned frames + corner subdiv + caps)
# ---------------------------------------------------------------------------

def _build_frames(centers, closed=False):
    """
    Build (tangent, normal, binormal) frames along the centers polyline.
    Aligns the binormal with world-up whenever possible so the "height" radius
    of the tube stays vertical for nearly horizontal paths (avoids the 90°
    rotated tubes that occur with naive parallel transport).
    """
    n = len(centers)
    if n < 2:
        return [(Vector(0, 0, 1), Vector(1, 0, 0), Vector(0, 1, 0))] * n

    world_up = Vector(0, 1, 0)
    tangents = []
    for i in range(n):
        if closed and n > 2:
            t = centers[(i + 1) % n] - centers[i - 1]
        elif i == 0:
            t = centers[1] - centers[0]
        elif i == n - 1:
            t = centers[-1] - centers[-2]
        else:
            t = centers[i+1] - centers[i-1]
        if t.GetLength() < 1e-8: t = Vector(0, 1, 0)
        t.Normalize()
        tangents.append(t)

    vertical_refs = []
    for t in tangents:
        up_proj = world_up - t * world_up.Dot(t)
        if up_proj.GetLength() < 1e-6:
            vertical_refs.append(None)
        else:
            up_proj.Normalize()
            vertical_refs.append(up_proj)

    if all(ref is not None for ref in vertical_refs):
        frames = []
        for t, b in zip(tangents, vertical_refs):
            n_vec = b.Cross(t)
            if n_vec.GetLength() < 1e-8:
                n_vec = t.Cross(world_up)
            n_vec.Normalize()
            frames.append((t, n_vec, b))
        return frames

    # Fallback: parallel-transport when path becomes near-vertical
    t0 = tangents[0]
    if   abs(t0.x) <= abs(t0.y) and abs(t0.x) <= abs(t0.z): arb = Vector(1, 0, 0)
    elif abs(t0.y) <= abs(t0.z):                             arb = Vector(0, 1, 0)
    else:                                                     arb = Vector(0, 0, 1)
    n0 = t0.Cross(arb); n0.Normalize()
    b0 = t0.Cross(n0);  b0.Normalize()
    frames = [(tangents[0], n0, b0)]

    for i in range(1, n):
        t_prev, n_prev, _ = frames[i-1]
        t_curr = tangents[i]
        axis   = t_prev.Cross(t_curr)
        alen   = axis.GetLength()
        if alen < 1e-8:
            b_new = t_curr.Cross(n_prev); b_new.Normalize()
            frames.append((t_curr, n_prev, b_new))
            continue
        axis.Normalize()
        cos_a = max(-1.0, min(1.0, t_prev.Dot(t_curr)))
        sin_a = alen
        n_new = n_prev * cos_a + axis.Cross(n_prev) * sin_a + axis * (axis.Dot(n_prev) * (1.0 - cos_a))
        n_new.Normalize()
        b_new = t_curr.Cross(n_new); b_new.Normalize()
        frames.append((t_curr, n_new, b_new))

    return frames


def _wall_loop_info(path):
    feature_type = path[0].get("feature_type", "")
    start_point = path[0]["point"]
    end_point   = path[-1]["point"]
    dx = end_point[0] - start_point[0]
    dy = end_point[1] - start_point[1]
    dz = end_point[2] - start_point[2]
    end_gap = math.sqrt(dx * dx + dy * dy + dz * dz)
    avg_width = 0.5 * (path[0]["width"] + path[-1]["width"])
    close_loop = (
        feature_type in ("Perimeter", "External perimeter", "Overhang perimeter")
        and end_gap <= max(1.5, avg_width * 6.0)
    )
    duplicate_endpoint = close_loop and end_gap <= max(1e-4, avg_width * 0.05)
    return close_loop, duplicate_endpoint


def _point_distance(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    dz = b[2] - a[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _accumulate_bbox(bbox, vec):
    """In-place bbox update. bbox is a list [min_x, min_y, min_z, max_x, max_y, max_z]."""
    if vec.x < bbox[0]: bbox[0] = vec.x
    if vec.y < bbox[1]: bbox[1] = vec.y
    if vec.z < bbox[2]: bbox[2] = vec.z
    if vec.x > bbox[3]: bbox[3] = vec.x
    if vec.y > bbox[4]: bbox[4] = vec.y
    if vec.z > bbox[5]: bbox[5] = vec.z


def add_tube_for_path(path, all_points, all_polys, sides=8, bbox=None):
    """
    bbox (optional): mutable [min_x, min_y, min_z, max_x, max_y, max_z]
    updated in place to track the running bbox WITHOUT a second pass.
    """
    if len(path) < 2: return

    close_loop, duplicate_endpoint = _wall_loop_info(path)
    if duplicate_endpoint and len(path) > 2:
        path = path[:-1]
    if len(path) < 2:
        return

    centers = []
    for p in path:
        gx, gy, gz = p["point"]
        centers.append(Vector(gx, gz, gy))   # GCode(X,Y,Z) -> C4D(X, Zgcode, Ygcode)

    frames = _build_frames(centers, closed=close_loop)
    rings  = []
    for i, c in enumerate(centers):
        _, n, b = frames[i]
        r_w = path[i]["width"]  * 0.5
        r_h = path[i]["height"] * 0.5
        ring_idx = []
        for k in range(sides):
            angle  = 2.0 * math.pi * k / sides
            offset = math.cos(angle) * n * r_w + math.sin(angle) * b * r_h
            idx    = len(all_points)
            world_p = c + offset
            all_points.append(world_p)
            if bbox is not None:
                _accumulate_bbox(bbox, world_p)
            ring_idx.append(idx)
        rings.append(ring_idx)

    # Side faces between consecutive rings
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(sides):
            a0 = r0[k]; a1 = r0[(k+1) % sides]
            b0 = r1[k]; b1 = r1[(k+1) % sides]
            all_polys.append(c4d.CPolygon(a0, a1, b1, b0))

    # Wall-loop closure: ties last ring to first when the path is a closed perimeter
    if close_loop:
        r0, r1 = rings[-1], rings[0]
        for k in range(sides):
            a0 = r0[k]; a1 = r0[(k+1) % sides]
            b0 = r1[k]; b1 = r1[(k+1) % sides]
            all_polys.append(c4d.CPolygon(a0, a1, b1, b0))
        return

    # Otherwise cap both ends with a fan
    sc = len(all_points); all_points.append(centers[0])
    if bbox is not None: _accumulate_bbox(bbox, centers[0])
    for k in range(sides):
        p1 = rings[0][k]; p2 = rings[0][(k+1) % sides]
        all_polys.append(c4d.CPolygon(sc, p2, p1, p1))

    ec = len(all_points); all_points.append(centers[-1])
    if bbox is not None: _accumulate_bbox(bbox, centers[-1])
    for k in range(sides):
        p1 = rings[-1][k]; p2 = rings[-1][(k+1) % sides]
        all_polys.append(c4d.CPolygon(ec, p1, p2, p2))


def _turn_angle_deg(p_prev, p_curr, p_next):
    in_vec = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1], p_curr[2] - p_prev[2])
    out_vec = (p_next[0] - p_curr[0], p_next[1] - p_curr[1], p_next[2] - p_curr[2])
    in_len = math.sqrt(in_vec[0] ** 2 + in_vec[1] ** 2 + in_vec[2] ** 2)
    out_len = math.sqrt(out_vec[0] ** 2 + out_vec[1] ** 2 + out_vec[2] ** 2)
    if in_len <= 1e-6 or out_len <= 1e-6:
        return None, in_len, out_len
    in_dir = (in_vec[0] / in_len, in_vec[1] / in_len, in_vec[2] / in_len)
    out_dir = (out_vec[0] / out_len, out_vec[1] / out_len, out_vec[2] / out_len)
    dot = max(-1.0, min(1.0, in_dir[0]*out_dir[0] + in_dir[1]*out_dir[1] + in_dir[2]*out_dir[2]))
    return math.degrees(math.acos(dot)), in_len, out_len


def _lerp_path_point(a, b, t):
    pa = a["point"]
    pb = b["point"]
    return {
        "point": (
            pa[0] + (pb[0] - pa[0]) * t,
            pa[1] + (pb[1] - pa[1]) * t,
            pa[2] + (pb[2] - pa[2]) * t
        ),
        "width": a["width"] + (b["width"] - a["width"]) * t,
        "height": a["height"] + (b["height"] - a["height"]) * t,
        "feature_type": a.get("feature_type", b.get("feature_type"))
    }


def _subdivision_params(turn_angle_deg, corner_angle_deg):
    """Return (insert_count, trim_ratio) for a corner above the threshold."""
    sharpness = (turn_angle_deg - corner_angle_deg) / max(1e-6, 180.0 - corner_angle_deg)
    insert_count = 1 + int(math.ceil(sharpness * 2.0))
    trim_ratio = 0.2 + sharpness * 0.2
    return insert_count, trim_ratio


def subdivide_sharp_corners(path, corner_angle_deg, closed=False):
    """
    Adds extra points around sharp corners to soften the tube twist.
    No-op when corner_angle_deg <= 0 or the path is too short.

    When closed=True, the joint between path[-1] and path[0] is also processed
    so closed perimeter loops with sharp seams remain smooth.
    """
    if corner_angle_deg <= 1e-6 or len(path) < 3:
        return path

    resampled = []

    # ── Prefix: subdivide BEFORE path[0] when the joint is sharp (closed only) ──
    if closed:
        prev_for_first = path[-1]
        # Avoid using a duplicate endpoint as "prev"
        if _point_distance(prev_for_first["point"], path[0]["point"]) < 1e-6 and len(path) >= 4:
            prev_for_first = path[-2]
        turn, in_len, out_len = _turn_angle_deg(prev_for_first["point"], path[0]["point"], path[1]["point"])
        if turn is not None and turn >= corner_angle_deg:
            insert_count, trim_ratio = _subdivision_params(turn, corner_angle_deg)
            for step in range(insert_count, 0, -1):
                t = 1.0 - trim_ratio * (float(step) / float(insert_count + 1))
                if 1e-4 < t < 1.0 - 1e-4:
                    resampled.append(_lerp_path_point(prev_for_first, path[0], t))

    resampled.append(dict(path[0]))

    # ── Interior corners (path[i], 1 <= i <= n-2) ──
    for i in range(1, len(path) - 1):
        prev = path[i - 1]
        curr = path[i]
        nxt  = path[i + 1]

        turn, in_len, out_len = _turn_angle_deg(prev["point"], curr["point"], nxt["point"])
        if turn is None or turn < corner_angle_deg:
            resampled.append(dict(curr))
            continue

        insert_count, trim_ratio = _subdivision_params(turn, corner_angle_deg)

        for step in range(insert_count, 0, -1):
            t = 1.0 - trim_ratio * (float(step) / float(insert_count + 1))
            if 1e-4 < t < 1.0 - 1e-4:
                resampled.append(_lerp_path_point(prev, curr, t))

        resampled.append(dict(curr))

        for step in range(1, insert_count + 1):
            t = trim_ratio * (float(step) / float(insert_count + 1))
            if 1e-4 < t < 1.0 - 1e-4:
                resampled.append(_lerp_path_point(curr, nxt, t))

    resampled.append(dict(path[-1]))

    # ── Suffix: subdivide AFTER path[-1] when the joint is sharp (closed only) ──
    if closed and len(path) >= 3:
        next_for_last = path[0]
        if _point_distance(path[-1]["point"], next_for_last["point"]) < 1e-6 and len(path) >= 4:
            next_for_last = path[1]
        turn, in_len, out_len = _turn_angle_deg(path[-2]["point"], path[-1]["point"], next_for_last["point"])
        if turn is not None and turn >= corner_angle_deg:
            insert_count, trim_ratio = _subdivision_params(turn, corner_angle_deg)
            for step in range(1, insert_count + 1):
                t = trim_ratio * (float(step) / float(insert_count + 1))
                if 1e-4 < t < 1.0 - 1e-4:
                    resampled.append(_lerp_path_point(path[-1], next_for_last, t))

    return resampled


def create_layer_mesh(paths, z_height, sides=8, corner_angle_deg=0.0,
                      close_wall_loops=True, global_bbox=None):
    """
    Returns the PolygonObject (or None if no paths produced points).

    global_bbox: optional mutable [min_x, min_y, min_z, max_x, max_y, max_z]
                 updated in place across all layers, eliminating the need for
                 a second pass over points later.
    """
    all_points, all_polys = [], []
    for path in paths:
        close_loop, duplicate_endpoint = _wall_loop_info(path)
        if close_wall_loops and duplicate_endpoint and len(path) > 2:
            # Remove the slicer's repeated endpoint before seam subdivision.
            # add_tube_for_path still stitches the final ring back to the first.
            path = path[:-1]
        path = subdivide_sharp_corners(path, corner_angle_deg, closed=close_loop)
        if not close_wall_loops:
            # Strip feature_type so add_tube_for_path falls back to capped ends
            path = [dict(point) for point in path]
            for point in path:
                point["feature_type"] = ""
        add_tube_for_path(path, all_points, all_polys, sides=sides, bbox=global_bbox)
    if not all_points: return None

    obj = c4d.PolygonObject(len(all_points), len(all_polys))
    obj.SetName("Layer_{:.3f}".format(z_height))
    for i, p in enumerate(all_points): obj.SetPoint(i, p)
    for i, poly in enumerate(all_polys): obj.SetPolygon(i, poly)

    phong = c4d.BaseTag(c4d.Tphong)
    phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
    phong[c4d.PHONGTAG_PHONG_ANGLE]      = math.radians(30)
    obj.InsertTag(phong)
    obj.Message(c4d.MSG_UPDATE)
    return obj


# ---------------------------------------------------------------------------
# CENTERING
# ---------------------------------------------------------------------------

def center_layers(layer_objs, global_bbox):
    """
    Shift all layer meshes so XZ center = origin and Y min = 0.
    Uses the precomputed global_bbox (in-place running bbox from mesh build)
    to skip the second pass entirely.
    """
    if not layer_objs or global_bbox is None or global_bbox[0] >= global_bbox[3]:
        return Vector(0, 0, 0), 0.0, 0.0, 0.0

    min_x, min_y, min_z, max_x, max_y, max_z = global_bbox

    cx = (min_x + max_x) * 0.5
    cz = (min_z + max_z) * 0.5
    offset = Vector(-cx, -min_y, -cz)

    for obj in layer_objs:
        cnt = obj.GetPointCount()
        for i in range(cnt):
            p = obj.GetPoint(i)
            obj.SetPoint(i, p + offset)
        obj.Message(c4d.MSG_UPDATE)

    width_x  = max_x - min_x
    height_y = max_y - min_y
    depth_z  = max_z - min_z
    return offset, width_x, height_y, depth_z


# ---------------------------------------------------------------------------
# MATERIALS
# ---------------------------------------------------------------------------

def create_material_for_filament(tool_id, color, doc):
    mat = c4d.BaseMaterial(c4d.Mmaterial)
    mat.SetName("Mat_Filament_T{}".format(tool_id))
    mat[c4d.MATERIAL_USE_COLOR] = True
    mat[c4d.MATERIAL_COLOR_COLOR] = color
    try:
        mat[c4d.MATERIAL_USE_REFLECTION] = False
    except:
        pass
    doc.InsertMaterial(mat)
    doc.AddUndo(c4d.UNDOTYPE_NEW, mat)
    mat.Message(c4d.MSG_UPDATE)
    return mat


def assign_material_to_object(obj, mat, doc):
    tag = c4d.TextureTag()
    tag[c4d.TEXTURETAG_MATERIAL] = mat
    obj.InsertTag(tag)
    doc.AddUndo(c4d.UNDOTYPE_NEW, tag)
    tag.Message(c4d.MSG_UPDATE)
    return tag


# ---------------------------------------------------------------------------
# USERDATA HELPERS
# ---------------------------------------------------------------------------

def add_int_userdata(node, name, value):
    bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_LONG)
    bc[c4d.DESC_NAME] = name
    bc[c4d.DESC_SHORT_NAME] = name
    desc_id = node.AddUserData(bc)
    node[desc_id] = int(value)
    return desc_id


def set_layer_visibility(obj, is_visible):
    mode = c4d.MODE_UNDEF if is_visible else c4d.MODE_OFF
    if obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] != mode:
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = mode
    if obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] != mode:
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = mode
    obj.Message(c4d.MSG_UPDATE)


def add_reveal_slider(parent_null):
    """
    Adds the 'Reveal' percent slider on parent_null.

    - DESC_MIN / DESC_MAX = wide bounds so the user can TYPE values outside [0%, 100%]
    - DESC_MINSLIDER / DESC_MAXSLIDER = [0, 1] so the visual slider stays clamped
      to a 0..100% range.
    """
    slider_bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_REAL)
    slider_bc[c4d.DESC_NAME]       = "Reveal"
    slider_bc[c4d.DESC_SHORT_NAME] = "Reveal"
    slider_bc[c4d.DESC_UNIT]       = c4d.DESC_UNIT_PERCENT
    slider_bc[c4d.DESC_MIN]        = SLIDER_HARD_MIN
    slider_bc[c4d.DESC_MAX]        = SLIDER_HARD_MAX
    slider_bc[c4d.DESC_MINSLIDER]  = 0.0
    slider_bc[c4d.DESC_MAXSLIDER]  = 1.0
    slider_bc[c4d.DESC_STEP]       = 0.01
    slider_bc[c4d.DESC_CUSTOMGUI]  = c4d.CUSTOMGUI_REALSLIDER
    slider_id = parent_null.AddUserData(slider_bc)
    parent_null[slider_id] = 1.0
    return slider_id


# ---------------------------------------------------------------------------
# MODE 1: FIELD REVEAL  (MoGraph Plain + Linear Field driven by slider)
# ---------------------------------------------------------------------------

def setup_field_reveal(parent_null, fracture_objs, doc, obj_height):
    """
    Builds a shared Plain Effector + Linear Field, wires them to the Fractures,
    and adds a Python tag on parent_null that maps the Reveal slider to the
    field's Y position.

    No clipping in the driver: typing 150% pushes the field beyond the object
    (everything visible); typing -50% drops it below (everything hidden).
    """
    if not fracture_objs:
        return None, None

    def touch(op):
        if op is None:
            return
        op.SetDirty(c4d.DIRTYFLAGS_DATA)
        op.Message(c4d.MSG_UPDATE)

    # ── Plain Effector ─────────────────────────────────────────────────────
    plain = c4d.BaseObject(c4d.Omgplain)
    plain.SetName("Plain_FilamentReveal")
    doc.InsertObject(plain, parent_null)
    doc.AddUndo(c4d.UNDOTYPE_NEW, plain)
    plain.Message(c4d.MSG_MENUPREPARE, doc)
    plain[c4d.ID_MG_BASEEFFECTOR_POSITION_ACTIVE] = False
    plain[c4d.ID_MG_BASEEFFECTOR_ROTATE_ACTIVE]   = False
    plain[c4d.ID_MG_BASEEFFECTOR_SCALE_ACTIVE]    = True
    plain[c4d.ID_MG_BASEEFFECTOR_UNIFORMSCALE]    = True
    plain[c4d.ID_MG_BASEEFFECTOR_USCALE]          = -1.0
    plain[c4d.ID_MG_BASEEFFECTOR_STRENGTH]        = 1.0

    # ── Linear Field ───────────────────────────────────────────────────────
    linear_field = c4d.BaseObject(c4d.Flinear)
    linear_field.SetName("LinearField_FilamentReveal")
    doc.InsertObject(linear_field, parent_null)
    doc.AddUndo(c4d.UNDOTYPE_NEW, linear_field)

    linear_field.SetAbsPos(Vector(0, obj_height, 0))
    linear_field[c4d.LINEAR_DIRECTION] = c4d.LINEAR_DIRECTION_YP
    linear_field[c4d.LINEAR_SIZE]      = 0.0
    linear_field.SetEditorMode(c4d.MODE_OFF)

    # Linear Field -> Plain.Fields list (FieldLayer approach for R20+)
    field_list = plain[c4d.FIELDS]
    if field_list is None:
        field_list = c4d.FieldList()
    layer = mograph.FieldLayer(c4d.FLfield)
    layer.SetLinkedObject(linear_field)
    field_list.InsertLayer(layer)
    plain[c4d.FIELDS] = field_list
    touch(linear_field)
    touch(plain)

    # Plain -> each Fracture's effector list
    for fracture in fracture_objs:
        eff_list = fracture[c4d.ID_MG_MOTIONGENERATOR_EFFECTORLIST]
        if eff_list is None:
            eff_list = c4d.InExcludeData()
        eff_list.InsertObject(plain, 1)
        fracture[c4d.ID_MG_MOTIONGENERATOR_EFFECTORLIST] = eff_list
        touch(fracture)

    # ── Python tag driving the field from the Reveal slider ────────────────
    tag = c4d.BaseTag(c4d.Tpython)
    tag.SetName("Reveal_Driver_Field")
    doc.AddUndo(c4d.UNDOTYPE_NEW, tag)

    field_bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_BASELISTLINK)
    field_bc[c4d.DESC_NAME] = "Linear Field Link"
    field_id = tag.AddUserData(field_bc)
    tag[field_id] = linear_field

    height_bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_REAL)
    height_bc[c4d.DESC_NAME] = "Max Height"
    max_height_id = tag.AddUserData(height_bc)
    tag[max_height_id] = float(obj_height)

    tag[c4d.TPYTHON_CODE] = (
        "import c4d\n"
        "\n"
        "_CACHE = {}\n"
        "\n"
        "def _find_userdata_id(node, name):\n"
        "    for desc_id, bc in node.GetUserDataContainer():\n"
        "        if bc[c4d.DESC_NAME] == name:\n"
        "            return desc_id\n"
        "    return None\n"
        "\n"
        "def _cached_id(node, name, key):\n"
        "    cached = _CACHE.get(key)\n"
        "    if cached is not None:\n"
        "        return cached\n"
        "    found = _find_userdata_id(node, name)\n"
        "    if found is not None:\n"
        "        _CACHE[key] = found\n"
        "    return found\n"
        "\n"
        "def main():\n"
        "    controller = op.GetObject()\n"
        "    if controller is None:\n"
        "        return\n"
        "    slider_id = _cached_id(controller, 'Reveal', 'slider')\n"
        "    field_id = _cached_id(op, 'Linear Field Link', 'field')\n"
        "    height_id = _cached_id(op, 'Max Height', 'height')\n"
        "    if slider_id is None or field_id is None or height_id is None:\n"
        "        return\n"
        "    field = op[field_id]\n"
        "    if field is None:\n"
        "        return\n"
        "    max_height = float(op[height_id])\n"
        "    # No clipping: typed values can extend the slider beyond [0%, 100%].\n"
        "    reveal = float(controller[slider_id])\n"
        "    pos = field.GetAbsPos()\n"
        "    new_y = max_height * reveal\n"
        "    if abs(pos.y - new_y) > 1e-6:\n"
        "        pos.y = new_y\n"
        "        field.SetAbsPos(pos)\n"
        "        field.Message(c4d.MSG_UPDATE)\n"
    )

    parent_null.InsertTag(tag)
    parent_null.Message(c4d.MSG_UPDATE)
    tag.Message(c4d.MSG_UPDATE)
    touch(parent_null)

    return plain, linear_field


# ---------------------------------------------------------------------------
# MODE 2: HIDE REVEAL  (visibility on/off, layer-by-layer)
# ---------------------------------------------------------------------------

def setup_hide_reveal(parent_null, layer_entries, doc):
    """
    layer_entries: list of (z_height, tool_id, layer_index, layer_obj)
    Each layer gets a 'Reveal Order' int userdata (1..N).
    A Python tag on parent_null reads the Reveal slider and toggles
    each layer's visibility based on order_index <= visible_count.

    No clipping: reveal=200% -> all layers visible; reveal=-50% -> none visible.
    """
    if not layer_entries:
        return

    sorted_entries = sorted(layer_entries, key=lambda item: (item[0], item[1], item[2]))
    for order_index, (_, _, _, layer_obj) in enumerate(sorted_entries, 1):
        add_int_userdata(layer_obj, "Reveal Order", order_index)
        set_layer_visibility(layer_obj, True)
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, layer_obj)

    tag = c4d.BaseTag(c4d.Tpython)
    tag.SetName("Reveal_Driver_Hide")
    doc.AddUndo(c4d.UNDOTYPE_NEW, tag)

    total_layers_id = add_int_userdata(tag, "Total Layers", len(sorted_entries))

    # The driver caches order_id (same desc id on every layer) and the slider
    # id, so the per-frame cost stays close to "iterate the children".
    tag[c4d.TPYTHON_CODE] = (
        "import c4d\n"
        "import math\n"
        "\n"
        "_CACHE = {}\n"
        "\n"
        "def _find_userdata_id(node, name):\n"
        "    for desc_id, bc in node.GetUserDataContainer():\n"
        "        if bc[c4d.DESC_NAME] == name:\n"
        "            return desc_id\n"
        "    return None\n"
        "\n"
        "def _cached_id(node, name, key):\n"
        "    cached = _CACHE.get(key)\n"
        "    if cached is not None:\n"
        "        return cached\n"
        "    found = _find_userdata_id(node, name)\n"
        "    if found is not None:\n"
        "        _CACHE[key] = found\n"
        "    return found\n"
        "\n"
        "def _iter_children(node):\n"
        "    child = node.GetDown()\n"
        "    while child:\n"
        "        yield child\n"
        "        for sub in _iter_children(child):\n"
        "            yield sub\n"
        "        child = child.GetNext()\n"
        "\n"
        "def _set_visibility(node, is_visible):\n"
        "    mode = c4d.MODE_UNDEF if is_visible else c4d.MODE_OFF\n"
        "    if node[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] != mode:\n"
        "        node[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = mode\n"
        "    if node[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] != mode:\n"
        "        node[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = mode\n"
        "\n"
        "def main():\n"
        "    controller = op.GetObject()\n"
        "    if controller is None:\n"
        "        return\n"
        "    slider_id = _cached_id(controller, 'Reveal', 'slider')\n"
        "    total_id = _cached_id(op, 'Total Layers', 'total')\n"
        "    if slider_id is None or total_id is None:\n"
        "        return\n"
        "    total_layers = max(0, int(op[total_id]))\n"
        "    # No clipping: typed values beyond [0%, 100%] simply saturate naturally.\n"
        "    reveal = float(controller[slider_id])\n"
        "    visible_count = int(math.floor((reveal * total_layers) + 1e-6))\n"
        "    order_id = _CACHE.get('order')\n"
        "    for node in _iter_children(controller):\n"
        "        local_id = order_id\n"
        "        if local_id is None:\n"
        "            local_id = _find_userdata_id(node, 'Reveal Order')\n"
        "            if local_id is None:\n"
        "                continue\n"
        "            _CACHE['order'] = local_id\n"
        "            order_id = local_id\n"
        "        try:\n"
        "            order_index = int(node[local_id])\n"
        "        except Exception:\n"
        "            continue\n"
        "        if order_index <= 0:\n"
        "            continue\n"
        "        _set_visibility(node, order_index <= visible_count)\n"
    )

    parent_null.InsertTag(tag)
    parent_null.Message(c4d.MSG_UPDATE)
    tag.Message(c4d.MSG_UPDATE)
    tag[total_layers_id] = len(sorted_entries)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    filepath = c4d.storage.LoadDialog(
        title="Choose a G-code file",
        type=c4d.FILESELECTTYPE_ANYTHING,
        flags=c4d.FILESELECT_LOAD
    )
    if not filepath:
        return

    dlg = GCodeImportDialog()
    dlg.Open(c4d.DLG_TYPE_MODAL, defaultw=360, defaulth=0)
    if not dlg.ok_clicked:
        return

    if not dlg.selected_types:
        gui.MessageDialog("Select at least one feature type.")
        return

    allowed_types     = dlg.selected_types
    sides             = dlg.sides
    min_path_len      = dlg.min_path_len
    corner_angle_deg  = dlg.corner_angle_deg
    close_wall_loops  = dlg.close_wall_loops
    arc_segs_per_mm   = dlg.arc_segments_per_mm
    reveal_mode       = dlg.reveal_mode
    import_name       = derive_import_name(filepath)

    doc = c4d.documents.GetActiveDocument()
    undo_started = False
    try:
        gui.StatusSetText("Parsing G-code...")
        filament_layers, metadata, parse_stats = parse_gcode_by_filaments(
            filepath,
            allowed_types   = allowed_types,
            min_path_len    = min_path_len,
            arc_segs_per_mm = arc_segs_per_mm,
        )

        if not filament_layers:
            gui.MessageDialog("No extrusion detected for selected types.")
            return

        doc.StartUndo()
        undo_started = True

        parent_null = c4d.BaseObject(c4d.Onull)
        parent_null.SetName(import_name)
        doc.InsertObject(parent_null)
        doc.AddUndo(c4d.UNDOTYPE_NEW, parent_null)

        sorted_filaments = sorted(
            (tool_id, layers) for tool_id, layers in filament_layers.items() if layers
        )
        if not sorted_filaments:
            gui.MessageDialog("No extrusion detected for selected types.")
            return

        tool_ids = [tool_id for tool_id, _ in sorted_filaments]
        tool_colors = choose_tool_colors(tool_ids, metadata)
        if len(tool_colors) != len(tool_ids):
            fallback_colors = generate_distinct_tool_colors(tool_ids, import_name)
            for tool_id in tool_ids:
                if tool_id not in tool_colors:
                    tool_colors[tool_id] = fallback_colors[tool_id]

        gui.StatusSetBar(0)
        gui.StatusSetText("Building tubes...")

        layer_objs       = []     # all layer meshes (for centering)
        fracture_objs    = []     # mode FIELD only
        layer_entries    = []     # mode HIDE only -> (z, tool, idx, obj)
        empty_containers = []     # containers that ended up with zero meshes
        total_layers     = sum(len(layers) for _, layers in sorted_filaments)
        processed_layers = 0

        # Running global bbox: [min_x, min_y, min_z, max_x, max_y, max_z]
        # Updated in-place during add_tube_for_path -> no second pass needed.
        global_bbox = [1e18, 1e18, 1e18, -1e18, -1e18, -1e18]

        for tool_id, layers in sorted_filaments:
            # Container per filament — kind depends on reveal mode.
            if reveal_mode == MODE_FIELD:
                container = c4d.BaseObject(c4d.Omgfracture)
                container.SetName("Fracture_Filament_T{}".format(tool_id))
                container[c4d.MGFRACTUREOBJECT_MODE] = c4d.MGFRACTUREOBJECT_MODE_NONE
            else:
                container = c4d.BaseObject(c4d.Onull)
                container.SetName("Group_Filament_T{}".format(tool_id))

            doc.InsertObject(container, parent_null)
            doc.AddUndo(c4d.UNDOTYPE_NEW, container)

            # Assign once on the filament container to keep the object manager
            # light and avoid one texture tag per layer mesh.
            mat = create_material_for_filament(tool_id, tool_colors[tool_id], doc)
            assign_material_to_object(container, mat, doc)

            container_layers = 0
            for layer_index, (z_height, paths) in enumerate(sorted(layers.items())):
                gui.StatusSetBar(int(100 * processed_layers / max(1, total_layers)))
                layer_obj = create_layer_mesh(
                    paths,
                    z_height,
                    sides=sides,
                    corner_angle_deg=corner_angle_deg,
                    close_wall_loops=close_wall_loops,
                    global_bbox=global_bbox,
                )
                processed_layers += 1
                if layer_obj:
                    layer_obj.InsertUnder(container)
                    doc.AddUndo(c4d.UNDOTYPE_NEW, layer_obj)
                    layer_objs.append(layer_obj)
                    container_layers += 1
                    if reveal_mode == MODE_HIDE:
                        layer_entries.append((z_height, tool_id, layer_index, layer_obj))

            if container_layers == 0:
                empty_containers.append(container)
            elif reveal_mode == MODE_FIELD:
                fracture_objs.append(container)

        # Drop empty containers (filtered out by feature/min_path_len rules)
        for c in empty_containers:
            c.Remove()

        if not layer_objs:
            gui.MessageDialog("All paths were filtered out — no mesh produced.")
            return

        gui.StatusSetText("Centering object...")
        _, w, obj_height, d = center_layers(layer_objs, global_bbox)

        # Slider lives on the parent null in BOTH modes
        add_reveal_slider(parent_null)

        if reveal_mode == MODE_FIELD:
            setup_field_reveal(parent_null, fracture_objs, doc, obj_height)
            mode_label = "MoGraph Field (continuous scale)"
        else:
            setup_hide_reveal(parent_null, layer_entries, doc)
            mode_label = "Visibility (layer-by-layer hide)"

        doc.SetActiveObject(parent_null, c4d.SELECTION_NEW)

        # Build a stats line that surfaces silent filtering or arc clamping
        warnings = []
        if parse_stats["paths_too_short"] > 0:
            warnings.append(
                "{} paths shorter than {:.2f} mm dropped".format(
                    parse_stats["paths_too_short"], min_path_len
                )
            )
        if parse_stats["arcs_truncated"] > 0:
            warnings.append(
                "{} arcs truncated at {} segments".format(
                    parse_stats["arcs_truncated"], MAX_ARC_SEGMENTS
                )
            )
        if parse_stats.get("inch_mode_used"):
            warnings.append("G20 inch units converted to millimeters")
        warning_text = ("\n" + " | ".join(warnings)) if warnings else ""

        gui.MessageDialog(
            "Import complete!\n"
            "{} filaments  |  {} layers  |  {} meshes\n"
            "Object: {:.1f} x {:.1f} x {:.1f} mm\n"
            "Centered at origin, resting on Y=0\n"
            "Reveal mode: {}\n"
            "Reveal slider on '{}'  (drag = 0..100%, type = beyond){}".format(
                len(sorted_filaments), total_layers, len(layer_objs),
                w, obj_height, d, mode_label, import_name, warning_text
            )
        )
    except Exception as exc:
        gui.MessageDialog("G-code import failed:\n{}".format(exc))
        raise
    finally:
        if undo_started:
            doc.EndUndo()
        gui.StatusClear()
        c4d.EventAdd()


if __name__ == "__main__":
    main()
