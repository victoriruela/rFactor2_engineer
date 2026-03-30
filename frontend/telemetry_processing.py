"""Telemetry processing helpers for frontend preview and visualization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.io


def load_mat_dataframe(file_path: str) -> pd.DataFrame:
    """Load a MATLAB telemetry file into a time-ordered DataFrame."""
    mat = scipy.io.loadmat(file_path, struct_as_record=False, squeeze_me=True)
    channels = {}
    for key in mat.keys():
        if not key.startswith("__") and hasattr(mat[key], "Value"):
            val = mat[key].Value
            if isinstance(val, np.ndarray) and val.ndim > 0:
                channels[key] = val
            else:
                channels[key] = val

    df = pd.DataFrame(channels)

    if not df.empty:
        max_len = len(df)
        for col in df.columns:
            if not isinstance(channels[col], np.ndarray) or channels[col].ndim == 0:
                df[col] = np.full(max_len, channels[col])

    sort_col = "Session_Elapsed_Time" if "Session_Elapsed_Time" in df.columns else df.columns[0]
    return df.sort_values(by=sort_col).reset_index(drop=True)


def filter_incomplete_laps(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out incomplete laps (out-laps/in-laps) from telemetry DataFrame."""
    lap_col = None
    for col in df.columns:
        if "lap" in col.lower() and "number" in col.lower():
            lap_col = col
            break
    if lap_col is None and "Lap_Number" in df.columns:
        lap_col = "Lap_Number"
    if lap_col is None:
        return df

    dist_col = None
    for col in df.columns:
        if "distance" in col.lower() and "lap" in col.lower():
            dist_col = col
            break
    if dist_col is None:
        for col in df.columns:
            if "distance" in col.lower():
                dist_col = col
                break

    laps = sorted([lap for lap in df[lap_col].unique() if lap > 0])
    if len(laps) <= 1:
        return df[df[lap_col] > 0] if 0 in df[lap_col].values else df

    if dist_col is not None:
        lap_distances = {}
        for lap in laps:
            dist = df.loc[df[lap_col] == lap, dist_col].dropna()
            lap_distances[lap] = (dist.max() - dist.min()) if not dist.empty else 0

        if lap_distances:
            target_dist = np.percentile(list(lap_distances.values()), 95)
            complete_laps = [lap for lap, dist in lap_distances.items() if dist >= target_dist * 0.98]
        else:
            complete_laps = []
    else:
        lap_samples = {lap: len(df[df[lap_col] == lap]) for lap in laps}
        if lap_samples:
            target_samples = np.percentile(list(lap_samples.values()), 95)
            complete_laps = [lap for lap, sample_count in lap_samples.items() if sample_count >= target_samples * 0.95]
        else:
            complete_laps = []

    if not complete_laps:
        complete_laps = laps

    time_col = "Session_Elapsed_Time" if "Session_Elapsed_Time" in df.columns else None
    if time_col and len(complete_laps) > 1:
        lap_durations = {}
        for lap in complete_laps:
            times = df.loc[df[lap_col] == lap, time_col].dropna()
            lap_durations[lap] = (times.max() - times.min()) if not times.empty else 0

        if len(complete_laps) > 2:
            middle_laps = complete_laps[1:-1]
            median_dur = np.median([lap_durations[lap] for lap in middle_laps if lap_durations[lap] > 0])
            if median_dur > 0:
                complete_laps = [lap for lap in complete_laps if lap_durations[lap] <= median_dur * 1.50]

    if not complete_laps:
        complete_laps = laps

    return df[df[lap_col].isin(complete_laps)].reset_index(drop=True)


def lap_xy(lap_df: pd.DataFrame, x_col: str, y_col: str):
    """Return x/y arrays with gap markers where abrupt discontinuities happen."""
    if x_col not in lap_df.columns or y_col not in lap_df.columns:
        return [], []

    x_arr = lap_df[x_col].values
    y_arr = lap_df[y_col].values

    if len(x_arr) < 2:
        return x_arr.tolist(), y_arr.tolist()

    xs, ys = [], []
    for idx in range(len(x_arr)):
        if idx > 0:
            diff = x_arr[idx] - x_arr[idx - 1]
            if x_col == "Lap_Distance":
                if diff < -10.0 or diff > 200.0:
                    xs.append(None)
                    ys.append(None)
            else:
                x_range = np.ptp(x_arr) if len(x_arr) > 0 else 0
                threshold = max(x_range * 0.05, 0.001)
                if abs(diff) > threshold:
                    xs.append(None)
                    ys.append(None)

        xv = float(x_arr[idx])
        yv = float(y_arr[idx])
        xs.append(xv if not np.isnan(xv) else None)
        ys.append(yv if not np.isnan(yv) else None)

    return xs, ys


def build_lap_data(lap_df: pd.DataFrame):
    """Extract telemetry channels required by the interactive frontend visualizations."""
    x_col = "Lap_Distance"
    if x_col not in lap_df.columns:
        return None

    data = {
        "max_dist": float(lap_df[x_col].max()),
        "channels": {},
    }

    chart_configs = {
        "speed": [("Ground_Speed", "Velocidad (km/h)")],
        "controls": [("Throttle_Pos", "Acelerador (%)"), ("Brake_Pos", "Freno (%)")],
        "steer": [("Steering_Wheel_Position", "Dirección")],
        "rpm": [("Engine_RPM", "RPM")],
        "gear": [("Gear", "Marcha")],
        "susp_pos": [(f"Susp_Pos_{w}", f"Susp {w}") for w in ["FL", "FR", "RL", "RR"]],
        "ride_height": [(f"Ride_Height_{w}", f"RH {w}") for w in ["FL", "FR", "RL", "RR"]],
        "brake_temp": [(f"Brake_Temp_{w}", f"Brake Temp {w}") for w in ["FL", "FR", "RL", "RR"]],
        "tyre_pres": [(f"Tyre_Pressure_{w}", f"Tyre Pres {w}") for w in ["FL", "FR", "RL", "RR"]],
        "aero": [("Front_Downforce", "Front DF"), ("Rear_Downforce", "Rear DF")],
    }

    for chart_id, configs in chart_configs.items():
        data["channels"][chart_id] = []
        for col, label in configs:
            if col in lap_df.columns:
                xs, ys = lap_xy(lap_df, x_col, col)
                if "Pos" in col:
                    ys = [val * 100 if val is not None else None for val in ys]
                if "Height" in col:
                    ys = [val * 1000 if val is not None else None for val in ys]

                data["channels"][chart_id].append(
                    {
                        "name": label,
                        "x": xs,
                        "y": ys,
                    }
                )

    if "GPS_Longitude" in lap_df.columns and "GPS_Latitude" in lap_df.columns:
        map_xs, map_ys = lap_xy(lap_df, "GPS_Longitude", "GPS_Latitude")
        dist_arr = lap_df[x_col].values.tolist()

        raw_lon = [float(v) if not np.isnan(float(v)) else None for v in lap_df["GPS_Longitude"].values]
        raw_lat = [float(v) if not np.isnan(float(v)) else None for v in lap_df["GPS_Latitude"].values]

        def to_pct(col_name: str):
            if col_name not in lap_df.columns:
                return [0.0] * len(dist_arr)
            out = []
            for val in lap_df[col_name].values:
                try:
                    fv = float(val)
                    out.append(0.0 if np.isnan(fv) else min(100.0, max(0.0, fv * 100.0)))
                except (TypeError, ValueError):
                    out.append(0.0)
            return out

        brake = to_pct("Brake_Pos")
        throttle = to_pct("Throttle_Pos")

        map_max_points = 1500
        raw_n = len(dist_arr)
        if raw_n > map_max_points:
            stride = raw_n // map_max_points
            raw_lon = raw_lon[::stride]
            raw_lat = raw_lat[::stride]
            brake = brake[::stride]
            throttle = throttle[::stride]
            dist_arr = dist_arr[::stride]

        data["map"] = {
            "lon": map_xs,
            "lat": map_ys,
            "dist": dist_arr,
            "raw_lon": raw_lon,
            "raw_lat": raw_lat,
            "brake": brake,
            "throttle": throttle,
        }

    return data


def precompute_all_laps(df: pd.DataFrame, laps):
    """Pre-compute interactive telemetry payload for all laps."""
    all_data = {}
    for lap in laps:
        lap_df = df[df["Lap_Number"] == lap].copy()
        all_data[lap] = build_lap_data(lap_df)
    return all_data
