from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from typing import List
import pandas as pd
import uvicorn

app = FastAPI()

camelot_keys = ['1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A']

def generate_camelot_path(start_key, direction):
    index = camelot_keys.index(start_key)
    if direction == "clockwise":
        return [camelot_keys[(index + i) % 12] for i in range(6)]
    else:
        return [camelot_keys[(index - i) % 12] for i in range(6)]

def clean_dataframe(contents: bytes) -> pd.DataFrame:
    try:
        # Try UTF-8 first
        text = contents.decode("utf-8")
        sep = "\t" if "\t" in text else ","
        return pd.read_csv(pd.io.common.StringIO(text), sep=sep)
    except UnicodeDecodeError:
        try:
            # Then try UTF-16
            text = contents.decode("utf-16")
            sep = "\t" if "\t" in text else ","
            return pd.read_csv(pd.io.common.StringIO(text), sep=sep)
        except Exception:
            raise ValueError("Could not decode file with UTF-8 or UTF-16")


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

@app.post("/build_set")
async def build_set(
    file: UploadFile = File(...),
    starting_track: str = Form(...),
    direction: str = Form(...)):
    contents = await file.read()
    try:
        df = clean_dataframe(contents)
    except:
        return JSONResponse({"error": "Could not parse the file."}, status_code=400)

    df.columns = [c.strip().lower() for c in df.columns]
    col_map = {
        "track title": "title", "title": "title", "track": "title",
        "artist": "artist",
        "key": "key", "musical key": "key",
        "bpm": "bpm", "tempo": "bpm"
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    df = df[["artist", "title", "key", "bpm"]]
    df["match"] = df["artist"].str.lower() + " – " + df["title"].str.lower()
    match = starting_track.strip().lower()
    match_row = df[df["match"].str.contains(match, case=False, na=False)]
    if match_row.empty:
        return JSONResponse({"error": "Starting track not found."}, status_code=404)

    start_key = match_row.iloc[0]["key"]
    records = df.to_dict(orient="records")
    grouped = group_tracks(records, start_key, direction)
    return {"starting_key": start_key, "direction": direction, "groups": grouped}
