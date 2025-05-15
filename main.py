from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

camelot_keys = ['1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A']

def generate_camelot_path(start_key, direction):
    index = camelot_keys.index(start_key)
    if direction == "clockwise":
        return [camelot_keys[(index + i) % 12] for i in range(6)]
    else:
        return [camelot_keys[(index - i) % 12] for i in range(6)]

def group_tracks(tracks, start_key, direction):
    path = generate_camelot_path(start_key, direction)
    groups = {k: {"originals": [], "pitch_shifted": []} for k in path}

    for t in tracks:
        key = t["key"]
        bpm = float(t["bpm"])
        if key in path:
            groups[key]["originals"].append(t)
            continue
        if key not in camelot_keys:
            continue
        orig_i = camelot_keys.index(key)
        for group_key in path:
            group_i = camelot_keys.index(group_key)
            delta = (group_i - orig_i) % 12
            if delta == 5:
                groups[group_key]["pitch_shifted"].append({**t, "shift": "-1"})
                break
            elif delta == 7:
                groups[group_key]["pitch_shifted"].append({**t, "shift": "+1"})
                break

    output = []
    for key in path:
        section = {"group": key, "tracks": []}
        all_tracks = groups[key]["originals"] + groups[key]["pitch_shifted"]
        all_tracks.sort(key=lambda x: float(x["bpm"]))
        for t in all_tracks:
            if "shift" in t:
                label = f'{t["artist"]} – {t["title"]} (from {t["key"]}) – {t["bpm"]} BPM ({t["shift"]} semitone shift)'
            else:
                label = f'{t["artist"]} – {t["title"]} ({t["key"]}) – {t["bpm"]} BPM'
            section["tracks"].append(label)
        output.append(section)
    return output

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

    cw_count = count_matches(clockwise_path)
    ccw_count = count_matches(counter_path)
    return "clockwise" if cw_count >= ccw_count else "counter-clockwise"

@app.post("/build_set")
async def build_set(request: Request):
    try:
        data = await request.json()
        tracklist = data["tracklist"]
        match = data["starting_track"].strip().lower()

        for t in tracklist:
            t["match"] = f'{t["artist"].strip().lower()} – {t["title"].strip().lower()}'

        fuzzy_matches = [t for t in tracklist if match in t["match"]]
        if not fuzzy_matches:
            return JSONResponse({"error": "Starting track not found."}, status_code=404)

        selected_track = fuzzy_matches[0]
        start_key = selected_track["key"]
        direction = determine_best_direction(tracklist, start_key)
        grouped = group_tracks(tracklist, start_key, direction)

        return {
            "starting_key": start_key,
            "direction": direction,
            "groups": grouped
        }
    except Exception as e:
        return JSONResponse({"error": f"Processing failed: {str(e)}"}, status_code=400)
