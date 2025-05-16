from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import re

app = FastAPI()

camelot_keys = ['1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A']
camelot_major_keys = ['1B', '2B', '3B', '4B', '5B', '6B', '7B', '8B', '9B', '10B', '11B', '12B']

def convert_major_to_minor(major_key):
    if major_key in camelot_major_keys:
        index = camelot_major_keys.index(major_key)
        minor_index = (index - 3) % 12
        return camelot_keys[minor_index]
    return major_key

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def generate_camelot_path(start_key, direction):
    index = camelot_keys.index(start_key)
    if direction == "clockwise":
        return [camelot_keys[(index + i) % 12] for i in range(6)]
    else:
        return [camelot_keys[(index - i) % 12] for i in range(6)]

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
            for group_key in path:
                group_i = camelot_keys.index(group_key)
                delta = (group_i - orig_i) % 12
                if delta in (5, 7):
                    count += 1
                    break
        return count

    cw = count_matches(clockwise_path)
    ccw = count_matches(counter_path)
    return "clockwise" if cw >= ccw else "counter-clockwise"

def group_tracks(tracks, start_key, direction, start_bpm):
    path = generate_camelot_path(start_key, direction)
    groups = {k: {"originals": [], "pitch_shifted": []} for k in path}
    ungrouped = []

    for tr in tracks:
        key = tr["key"]
        bpm = float(tr["bpm"])
        if key in path:
            groups[key]["originals"].append(tr)
        elif key in camelot_keys:
            orig_i = camelot_keys.index(key)
            matches = []
            for group_key in path:
                group_i = camelot_keys.index(group_key)
                delta = (group_i - orig_i) % 12
                if delta == 5:
                    matches.append((group_key, "-1"))
                elif delta == 7:
                    matches.append((group_key, "+1"))
            if len(matches) == 1:
                g, s = matches[0]
                groups[g]["pitch_shifted"].append({**tr, "shift": s})
            elif len(matches) == 2:
                ungrouped.append((tr, matches))
        elif key in camelot_major_keys:
            minor = convert_major_to_minor(key)
            if minor in path:
                ungrouped.append((tr, [(minor, "mode")]))

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
    for k in path:
        section = {"group": k, "tracks": []}
        all_tracks = groups[k]["originals"] + groups[k]["pitch_shifted"]
        all_tracks.sort(key=lambda x: float(x["bpm"]))
        for tr in all_tracks:
            if "shift" in tr:
                if tr["shift"] == "mode":
                    label = f'{tr["artist"]} – {tr["title"]} (from {tr["key"]}) – {tr["bpm"]} BPM (mode shift)'
                else:
                    label = f'{tr["artist"]} – {tr["title"]} (from {tr["key"]}) – {tr["bpm"]} BPM ({tr["shift"]} semitone shift)'
            else:
                label = f'{tr["artist"]} – {tr["title"]} ({tr["key"]}) – {tr["bpm"]} BPM'
            section["tracks"].append(label)
        output.append(section)
    return output

@app.post("/build_set")
async def build_set(request: Request):
    try:
        data = await request.json()
        tracklist = data["tracklist"]
        match_input = data["starting_track"]

        # Build match + normalized fields
        for tr in tracklist:
            tr["match"] = f'{tr["artist"].strip()} – {tr["title"].strip()}'
            tr["normalized"] = normalize(tr["match"])

        norm_input = normalize(match_input)
        fuzzy_matches = [tr for tr in tracklist if norm_input in tr["normalized"]]

        if not fuzzy_matches:
            return JSONResponse({"error": "Starting track not found."}, status_code=404)

        selected_track = fuzzy_matches[0]
        start_key = selected_track["key"]
        start_bpm = float(selected_track["bpm"])

        # Convert major to minor if needed
        if start_key in camelot_major_keys:
            start_key = convert_major_to_minor(start_key)

        direction = determine_best_direction(tracklist, start_key)
        grouped = group_tracks(tracklist, start_key, direction, start_bpm)

        return {
            "starting_key": start_key,
            "direction": direction,
            "groups": grouped
        }

    except Exception as e:
        return JSONResponse({"error": f"Processing failed: {str(e)}"}, status_code=400)