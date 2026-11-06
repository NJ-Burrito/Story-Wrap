"""Camera data for the smoke shot: one beat, one shot. Partner alone, MS eye level, a slow push (2D flat camera: x, y, z, F)."""
BEATS = [{"id": "b1", "start": 0.0, "end": 2.0, "treatment": "A", "emotion": "joy"}]
SHOTS = [
    {"shot": "s1", "beat": "b1", "t0": 0.0, "t1": 2.0, "size": "MS", "angle": "eye", "lens_mm": 35, "move": "push",
     "cam0": {"x": -0.02, "y": -0.03, "z": 0.40, "F": 1700}, "cam1": {"x": 0.08, "y": 0.01, "z": 0.72, "F": 1700},
     "start_frame_desc": "Partner waist up behind the counter, left palm low, right heel on the wall at screen left",
     "end_frame_desc": "a little closer: the left palm lifted with a loaf of bread, a small grin, the right hand on the ledge",
     "why": "a slow push says 'watch what he offers' and keeps the face and the open palm in one frame", "serves_emotion": "joy",
     "safe_boxes": [{"id": "face", "x": 380, "y": 560, "w": 320, "h": 380}], "catalogue_camera": "ms-eye-flat"},
]
CUTS = {}
EXTRA = {"lens_rule": "2D flat camera: x, y, z and focal only (F9).", "line_180": "one shot, no cut", "screen_direction": "his left (offering) hand is screen right, the wall hand screen left"}
