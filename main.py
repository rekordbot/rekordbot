from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import re

app = FastAPI()

camelot_keys = ['1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A']
camelot_major_keys = ['1B', '2B', '3B', '4B', '5B', '6B', '7B', '8B', '9B', '10B', '11B', '12B']

def generate_camelot_path(start_key, direction):
    index = camelot_keys.index(start_key)
    if direction == "clockwise":
        return [camelot_keys[(index + i) % 12] for i in range(6)]
    else:
        return [camelot_keys[(index - i) % 12] for i in range(6)]

def convert_major_to_minor(major_key):
    if major_key not in camelot_major_keys:
        return None
    index = camelot_major_keys.index(major_key)
    minor_index = (index - 3) % 12
    return camelot_keys[minor_index]

def determine_best_direction(tracks, start_key):
    clockwise_path = generate_camelot_path(start_key, "clockwise")
    counter_path = generate_camelot_path(start_key, "counter-clockwise")

    def count_matches(path):
        count = 0
        for t in tracks:
            key = t["key"]
            if key in path:
                count += 1
                continue
            if key not in camelot_keys:
                continue
            orig_i = camelot_keys.index(key)
            shiftable = []
            for group_key in path:
                group_i = camelot_keys.index(group_key)
                delta = (group_i - orig_i) % 12
                if delta in (5, 7):
                    shiftable.append(group_key)
            if len(shiftable) == 1:
                count += 1
        return count

    cw_count = count_matches(clockwise_path)
    ccw_count = count_matches(counter_path)
    return "clockwise" if cw_count >= ccw_count else "counter-clockwise"

def group_tracks(tracks, start_key_match, direction):
    path = generate_camelot_path(start_key_match, direction)
    groups = {k: {"originals": [], "pitch_shifted": []} for k in path}
    ungrouped = []

    for t in tracks:
        key = t["key"]
        bpm = float(t["bpm"])
        if key in path:
            groups[key]["originals"].append(t)
        elif key in camelot_keys:
            matches = []
            orig_i = camelot_keys.index(key)
            for group_key in path:
                group_i = camelot_keys.index(group_key)
                delta = (group_i - orig_i) % 12
                if delta == 5:
                    matches.append((group_key, "-1"))
                elif delta == 7:
                    matches.append((group_key, "+1"))
            if len(matches) == 1:
                group_key, shift = matches[0]
                groups[group_key]["pitch_shifted"].append({**t, "shift": shift})
            elif len(matches) == 2:
                ungrouped.append((t, matches))
        elif key in camelot_major_keys:
            minor_key = convert_major_to_minor(key)
            if minor_key in path:
                ungrouped.append((t, [(minor_key, "mode")]))
    
    start_track = next(tr for tr in tracks if tr["match"] == start_key_match)
    start_bpm = float(start_track["bpm"])

    for t, matches in ungrouped:
        if len(matches) == 1:
            group_key, shift = matches[0]
            groups[group_key]["pitch_shifted"].append({**t, "shift": shift})
        else:
            a, b = matches[0][0], matches[1][0]
            len_a = len(groups[a]["originals"]) + len(groups[a]["pitch_shifted"])
            len_b = len(groups[b]["originals"]) + len(groups[b]["pitch_shifted"])
            if len_a < len_b:
                selected = a
            elif len_b < len_a:
                selected = b
            else:
                bpm = float(t["bpm"])
                index_a = path.index(a)
                index_b = path.index(b)
                if bpm <= start_bpm + 2:
                    selected = a if index_a < index_b else b
                else:
                    selected = b if index_b > index_a else a
            selected_shift = [s for g, s in matches if g == selected][0]
            groups[selected]["pitch_shifted"].append({**t, "shift": selected_shift})

    output = []
    for key in path:
        section = {"group": key, "tracks": []}
        all_tracks = groups[key]["originals"] + groups[key]["pitch_shifted"]
        all_tracks.sort(key=lambda x: float(x["bpm"]))
        for t in all_tracks:
            if "shift" in t:
                if t["shift"] == "mode":
                    label = f'{t["artist"]} – {t["title"]} (from {t["key"]}) – {t["bpm"]} BPM (mode shift)'
                else:
                    label = f'{t["artist"]} – {t["title"]} (from {t["key"]}) – {t["bpm"]} BPM ({t["shift"]} semitone shift)'
            else:
                label = f'{t["artist"]} – {t["title"]} ({t["key"]}) – {t["bpm"]} BPM'
            section["tracks"].append(label)
        output.append(section)
    return output

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

@app.post("/build_set")
async def build_set(request: Request):
    try:
        data = await request.json()
        tracklist = data["tracklist"]
        match_input = data["starting_track"]
        normalized_input = normalize(match_input)

        for t in tracklist:
            t["match"] = f'{t["artist"].strip()} – {t["title"].strip()}'
        fuzzy_matches = [t for t in tracklist if normalized_input in normalize(t["match"])]

        if not fuzzy_matches:
            return JSONResponse({"error": "Starting track not found."}, status_code=404)

        selected_track = fuzzy_matches[0]
        start_key = selected_track["key"]
        direction = determine_best_direction(tracklist, start_key)
        grouped = group_tracks(tracklist, selected_track["match"], direction)

        return {
            "starting_key": start_key,
            "direction": direction,
            "groups": grouped
        }
    except Exception as e:
        return JSONResponse({"error": f"Processing failed: {str(e)}"}, status_code=400)