#!/usr/bin/env python3
"""
One-time script to generate unified track JSON files from multiple data sources.

Sources:
  1. TUMFTM racetrack-database (25 tracks, centerline + width, LGPL-3.0)
  2. OpenF1 location API (XYZ telemetry for ~18 F1 tracks)
  3. TUMRT Bathurst (full 3D with left/right boundaries)

Usage:
  python scripts/generate_track_data.py

Output:
  tracks/<circuit>.json files in unified format
"""

import csv
import io
import json
import os
import sys
import time

import numpy as np
import requests
from scipy.spatial import KDTree
from scipy.spatial import procrustes as scipy_procrustes

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tracks")

TUMFTM_BASE_URL = (
    "https://raw.githubusercontent.com/TUMFTM/racetrack-database/master/tracks"
)

TUMRT_BATHURST_URL = (
    "https://raw.githubusercontent.com/TUMRT/online_3D_racing_line_planning"
    "/main/data/raw_track_data/mount_panorama_bounds_3d.csv"
)

# TUMFTM track filenames (without extension) and their display names
TUMFTM_TRACKS = [
    {"file": "Austin", "name": "Circuit of the Americas"},
    {"file": "BrandsHatch", "name": "Brands Hatch"},
    {"file": "Budapest", "name": "Hungaroring"},
    {"file": "Catalunya", "name": "Circuit de Barcelona-Catalunya"},
    {"file": "Hockenheim", "name": "Hockenheimring"},
    {"file": "IMS", "name": "Indianapolis Motor Speedway"},
    {"file": "Jeddah", "name": "Jeddah Corniche Circuit"},
    {"file": "Melbourne", "name": "Albert Park"},
    {"file": "MexicoCity", "name": "Autodromo Hermanos Rodriguez"},
    {"file": "Miami", "name": "Miami International Autodrome"},
    {"file": "Monza", "name": "Autodromo Nazionale Monza"},
    {"file": "Montreal", "name": "Circuit Gilles Villeneuve"},
    {"file": "Mugello", "name": "Mugello Circuit"},
    {"file": "Nuerburgring", "name": "Nurburgring"},
    {"file": "Oschersleben", "name": "Motorsport Arena Oschersleben"},
    {"file": "Sakhir", "name": "Bahrain International Circuit"},
    {"file": "SaoPaulo", "name": "Interlagos"},
    {"file": "Sepang", "name": "Sepang International Circuit"},
    {"file": "Shanghai", "name": "Shanghai International Circuit"},
    {"file": "Silverstone", "name": "Silverstone Circuit"},
    {"file": "Spa", "name": "Spa-Francorchamps"},
    {"file": "Spielberg", "name": "Red Bull Ring"},
    {"file": "Suzuka", "name": "Suzuka International Racing Course"},
    {"file": "YasMarina", "name": "Yas Marina Circuit"},
    {"file": "Zandvoort", "name": "Circuit Zandvoort"},
]

# Mapping from TUMFTM file name -> OpenF1 circuit info
# session_key: a 2024 race session key; driver_number: typically the pole sitter
# These are approximate session keys from 2024 F1 season
TUMFTM_TO_OPENF1_MAPPING = {
    "Austin": {"circuit_short_name": "Austin", "session_key": 9222, "driver_number": 1},
    "Budapest": {"circuit_short_name": "Budapest", "session_key": 9191, "driver_number": 1},
    "Catalunya": {"circuit_short_name": "Barcelona", "session_key": 9175, "driver_number": 1},
    "Jeddah": {"circuit_short_name": "Jeddah", "session_key": 9102, "driver_number": 1},
    "Melbourne": {"circuit_short_name": "Melbourne", "session_key": 9107, "driver_number": 1},
    "MexicoCity": {"circuit_short_name": "Mexico City", "session_key": 9227, "driver_number": 1},
    "Miami": {"circuit_short_name": "Miami", "session_key": 9144, "driver_number": 1},
    "Monza": {"circuit_short_name": "Monza", "session_key": 9207, "driver_number": 1},
    "Montreal": {"circuit_short_name": "Montréal", "session_key": 9170, "driver_number": 1},
    "Sakhir": {"circuit_short_name": "Sakhir", "session_key": 9097, "driver_number": 1},
    "SaoPaulo": {"circuit_short_name": "São Paulo", "session_key": 9232, "driver_number": 1},
    "Shanghai": {"circuit_short_name": "Shanghai", "session_key": 9117, "driver_number": 1},
    "Silverstone": {"circuit_short_name": "Silverstone", "session_key": 9186, "driver_number": 1},
    "Spa": {"circuit_short_name": "Spa-Francorchamps", "session_key": 9196, "driver_number": 1},
    "Spielberg": {"circuit_short_name": "Spielberg", "session_key": 9181, "driver_number": 1},
    "Suzuka": {"circuit_short_name": "Suzuka", "session_key": 9112, "driver_number": 1},
    "YasMarina": {"circuit_short_name": "Yas Island", "session_key": 9250, "driver_number": 1},
    "Zandvoort": {"circuit_short_name": "Zandvoort", "session_key": 9201, "driver_number": 1},
}

OPENF1_LOCATION_URL = "https://api.openf1.org/v1/location"


# ---------------------------------------------------------------------------
# Parsing functions
# ---------------------------------------------------------------------------

def parse_tumftm_csv(filepath):
    """Parse a TUMFTM centerline CSV file.

    Format: # x_m, y_m, w_tr_right_m, w_tr_left_m  (header comment)
    followed by data rows: x,y,w_right,w_left

    Returns list of dicts with keys: x, y, w_right, w_left
    """
    points = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) >= 4:
                points.append({
                    "x": float(parts[0]),
                    "y": float(parts[1]),
                    "w_right": float(parts[2]),
                    "w_left": float(parts[3]),
                })
    return points


def parse_tumftm_csv_from_text(text):
    """Parse TUMFTM CSV from text content (downloaded from GitHub)."""
    points = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) >= 4:
            points.append({
                "x": float(parts[0]),
                "y": float(parts[1]),
                "w_right": float(parts[2]),
                "w_left": float(parts[3]),
            })
    return points


def parse_tumrt_bathurst_csv(filepath):
    """Parse TUMRT Bathurst CSV with left/right boundary columns.

    Format: right_bound_x,right_bound_y,right_bound_z,left_bound_x,left_bound_y,left_bound_z

    Computes centerline as midpoint of boundaries, width as distance
    from center to each boundary.

    Returns list of dicts with keys: x, y, z, w_right, w_left
    """
    points = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rx = float(row["right_bound_x"].strip())
            ry = float(row["right_bound_y"].strip())
            rz = float(row["right_bound_z"].strip())
            lx = float(row["left_bound_x"].strip())
            ly = float(row["left_bound_y"].strip())
            lz = float(row["left_bound_z"].strip())

            # Centerline = midpoint
            cx = (rx + lx) / 2.0
            cy = (ry + ly) / 2.0
            cz = (rz + lz) / 2.0

            # Width = distance from center to each boundary
            w_right = np.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
            w_left = np.sqrt((lx - cx) ** 2 + (ly - cy) ** 2)

            points.append({
                "x": cx,
                "y": cy,
                "z": cz,
                "w_right": w_right,
                "w_left": w_left,
            })
    return points


def parse_tumrt_bathurst_csv_from_text(text):
    """Parse TUMRT Bathurst CSV from text content."""
    points = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        rx = float(row["right_bound_x"].strip())
        ry = float(row["right_bound_y"].strip())
        rz = float(row["right_bound_z"].strip())
        lx = float(row["left_bound_x"].strip())
        ly = float(row["left_bound_y"].strip())
        lz = float(row["left_bound_z"].strip())

        cx = (rx + lx) / 2.0
        cy = (ry + ly) / 2.0
        cz = (rz + lz) / 2.0

        w_right = np.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
        w_left = np.sqrt((lx - cx) ** 2 + (ly - cy) ** 2)

        points.append({
            "x": cx,
            "y": cy,
            "z": cz,
            "w_right": w_right,
            "w_left": w_left,
        })
    return points


# ---------------------------------------------------------------------------
# Alignment & elevation
# ---------------------------------------------------------------------------

def resample_points(points_2d, target_count):
    """Resample a 2D point array to target_count points via linear interpolation."""
    # Compute cumulative arc length
    diffs = np.diff(points_2d, axis=0)
    segment_lengths = np.sqrt((diffs ** 2).sum(axis=1))
    cumulative = np.zeros(len(points_2d))
    cumulative[1:] = np.cumsum(segment_lengths)
    total_length = cumulative[-1]

    # New evenly-spaced parameter values
    new_params = np.linspace(0, total_length, target_count)

    # Interpolate x and y
    new_x = np.interp(new_params, cumulative, points_2d[:, 0])
    new_y = np.interp(new_params, cumulative, points_2d[:, 1])

    return np.column_stack([new_x, new_y])


def procrustes_align_2d(source, target):
    """Align source 2D points to target 2D points using Procrustes analysis.

    Both source and target must have the same number of points.
    Returns (aligned_source, transform_params) where transform_params is a dict
    with scale, rotation, and translation info.
    """
    # scipy.spatial.procrustes expects same-shape matrices and standardizes them
    # We need to handle the transform ourselves for applying to all points

    # Center both
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)

    source_centered = source - source_mean
    target_centered = target - target_mean

    # Scale
    source_norm = np.sqrt((source_centered ** 2).sum())
    target_norm = np.sqrt((target_centered ** 2).sum())

    source_scaled = source_centered / source_norm
    target_scaled = target_centered / target_norm

    # Optimal rotation via SVD
    M = target_scaled.T @ source_scaled
    U, S, Vt = np.linalg.svd(M)
    R = U @ Vt

    # Handle reflection
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = U @ Vt

    scale = target_norm / source_norm

    # Apply transform: aligned = (source - source_mean) * scale @ R.T + target_mean
    aligned = (source - source_mean) @ (scale * R.T) + target_mean

    transform_params = {
        "source_mean": source_mean,
        "target_mean": target_mean,
        "scale": scale,
        "rotation": R,
    }

    return aligned, transform_params


def apply_transform_2d(points, transform_params):
    """Apply a previously computed Procrustes transform to new 2D points."""
    source_mean = transform_params["source_mean"]
    target_mean = transform_params["target_mean"]
    scale = transform_params["scale"]
    R = transform_params["rotation"]

    return (points - source_mean) @ (scale * R.T) + target_mean


def project_elevation(tumftm_xy_aligned, openf1_xyz):
    """Project OpenF1 Z values onto TUMFTM points via nearest-neighbor.

    Args:
        tumftm_xy_aligned: (N, 2) array of aligned TUMFTM 2D points
        openf1_xyz: (M, 3) array of OpenF1 XYZ points

    Returns:
        (N,) array of Z values for each TUMFTM point
    """
    tree = KDTree(openf1_xyz[:, :2])
    _, indices = tree.query(tumftm_xy_aligned)
    return openf1_xyz[indices, 2]


# ---------------------------------------------------------------------------
# JSON building
# ---------------------------------------------------------------------------

def build_track_json(name, source, points, z_values=None):
    """Build the unified track JSON structure.

    Args:
        name: display name of the track
        source: data source identifier (tumftm, tumftm+openf1, tumrt)
        points: list of dicts with x, y, (optional z), w_right, w_left
        z_values: optional numpy array of elevation values

    Returns:
        dict matching the output JSON schema
    """
    output_points = []
    for i, p in enumerate(points):
        z = 0.0
        if z_values is not None:
            z = float(z_values[i])
        elif "z" in p:
            z = float(p["z"])

        output_points.append({
            "x": float(p["x"]),
            "y": float(p["y"]),
            "z": z,
            "width_left": float(p["w_left"]),
            "width_right": float(p["w_right"]),
        })

    return {
        "name": name,
        "source": source,
        "points": output_points,
    }


# ---------------------------------------------------------------------------
# OpenF1 data fetching
# ---------------------------------------------------------------------------

def fetch_openf1_location(session_key, driver_number):
    """Fetch location data from OpenF1 API for a given session and driver.

    Returns list of dicts with x, y, z or None on failure.
    """
    try:
        resp = requests.get(
            OPENF1_LOCATION_URL,
            params={
                "session_key": session_key,
                "driver_number": driver_number,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return data
    except (requests.RequestException, ValueError) as e:
        print(f"  WARNING: OpenF1 request failed: {e}")
        return None


def extract_single_lap(location_data):
    """Extract approximately one lap of location data.

    Uses the data points to find a lap by detecting when the driver
    returns close to the starting point.
    """
    if not location_data or len(location_data) < 50:
        return None

    # Filter out points with None/null coordinates
    valid = [p for p in location_data if p.get("x") is not None and p.get("y") is not None and p.get("z") is not None]
    if len(valid) < 50:
        return None

    points = np.array([[p["x"], p["y"], p["z"]] for p in valid])

    # Start from point 0; find where we get close to it again after traveling
    # at least half the total distance
    start = points[0, :2]
    dists_from_start = np.sqrt(((points[:, :2] - start) ** 2).sum(axis=1))

    # Find first point that is far enough from start (at least 100m)
    far_idx = np.argmax(dists_from_start > 100)
    if far_idx == 0:
        # Never got far from start; use middle section
        n = len(points)
        return points[n // 4: 3 * n // 4]

    # From far_idx onward, find where we get close to start again
    close_threshold = 50.0  # meters
    for i in range(far_idx + 50, len(points)):
        if dists_from_start[i] < close_threshold:
            return points[:i]

    # If no close return found, just use all points
    return points


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def download_tumftm_csv(track_file):
    """Download a TUMFTM track CSV from GitHub."""
    url = f"{TUMFTM_BASE_URL}/{track_file}.csv"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  WARNING: Failed to download {track_file}: {e}")
        return None


def download_tumrt_bathurst():
    """Download TUMRT Bathurst CSV from GitHub."""
    try:
        resp = requests.get(TUMRT_BATHURST_URL, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  WARNING: Failed to download Bathurst: {e}")
        return None


def process_tumftm_track(track_info, openf1_cache=None):
    """Process a single TUMFTM track, optionally adding OpenF1 elevation.

    Returns (track_json, source) or None on failure.
    """
    file_name = track_info["file"]
    display_name = track_info["name"]

    print(f"  Downloading TUMFTM data for {display_name}...")
    csv_text = download_tumftm_csv(file_name)
    if csv_text is None:
        return None

    points = parse_tumftm_csv_from_text(csv_text)
    if not points:
        print(f"  WARNING: No points parsed for {display_name}")
        return None

    # Check if we have OpenF1 mapping for elevation
    z_values = None
    source = "tumftm"

    if file_name in TUMFTM_TO_OPENF1_MAPPING:
        mapping = TUMFTM_TO_OPENF1_MAPPING[file_name]
        print(f"  Fetching OpenF1 elevation data for {display_name}...")

        openf1_data = fetch_openf1_location(
            mapping["session_key"],
            mapping["driver_number"],
        )

        if openf1_data:
            lap_xyz = extract_single_lap(openf1_data)

            if lap_xyz is not None and len(lap_xyz) >= 20:
                try:
                    # Resample both to same point count for Procrustes
                    tumftm_xy = np.array([[p["x"], p["y"]] for p in points])
                    n_resample = min(len(tumftm_xy), len(lap_xyz))

                    tumftm_resampled = resample_points(tumftm_xy, n_resample)
                    openf1_resampled = resample_points(lap_xyz[:, :2], n_resample)

                    # Procrustes alignment on resampled points
                    _, transform_params = procrustes_align_2d(tumftm_resampled, openf1_resampled)

                    # Apply transform to all original TUMFTM points
                    aligned_xy = apply_transform_2d(tumftm_xy, transform_params)

                    # Project elevation
                    z_values = project_elevation(aligned_xy, lap_xyz)
                    source = "tumftm+openf1"
                    print(f"  SUCCESS: Elevation data applied ({len(lap_xyz)} OpenF1 points)")
                except Exception as e:
                    print(f"  WARNING: Procrustes alignment failed for {display_name}: {e}")
            else:
                print(f"  WARNING: Insufficient OpenF1 data for {display_name}")
        else:
            print(f"  WARNING: No OpenF1 data available for {display_name}")

    track_json = build_track_json(display_name, source, points, z_values)
    return track_json


def generate_all_tracks():
    """Generate all track JSON files."""
    os.makedirs(TRACKS_DIR, exist_ok=True)

    generated = []
    failed = []

    # Process TUMFTM tracks
    print("=" * 60)
    print("TRACK DATA GENERATION")
    print("=" * 60)

    for track_info in TUMFTM_TRACKS:
        print(f"\nProcessing: {track_info['name']}")
        try:
            track_json = process_tumftm_track(track_info)
            if track_json:
                # Write JSON
                safe_name = track_info["file"].lower()
                output_path = os.path.join(TRACKS_DIR, f"{safe_name}.json")
                with open(output_path, "w") as f:
                    json.dump(track_json, f, indent=2)
                generated.append((track_info["name"], track_json["source"], len(track_json["points"])))
                print(f"  SAVED: {output_path} ({len(track_json['points'])} points, source: {track_json['source']})")
            else:
                failed.append(track_info["name"])
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append(track_info["name"])

        # Rate limit for OpenF1
        time.sleep(0.5)

    # Process Bathurst (TUMRT)
    print(f"\nProcessing: Mount Panorama (Bathurst)")
    try:
        csv_text = download_tumrt_bathurst()
        if csv_text:
            points = parse_tumrt_bathurst_csv_from_text(csv_text)
            if points:
                track_json = build_track_json("Mount Panorama (Bathurst)", "tumrt", points)
                output_path = os.path.join(TRACKS_DIR, "bathurst.json")
                with open(output_path, "w") as f:
                    json.dump(track_json, f, indent=2)
                generated.append(("Mount Panorama (Bathurst)", "tumrt", len(track_json["points"])))
                print(f"  SAVED: {output_path} ({len(track_json['points'])} points, source: tumrt)")
            else:
                failed.append("Mount Panorama (Bathurst)")
        else:
            failed.append("Mount Panorama (Bathurst)")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed.append("Mount Panorama (Bathurst)")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Generated: {len(generated)} tracks")
    for name, source, n_points in generated:
        elevation = "3D" if source != "tumftm" else "flat"
        print(f"  {name}: {n_points} points ({elevation})")
    if failed:
        print(f"\nFailed: {len(failed)} tracks")
        for name in failed:
            print(f"  {name}")


if __name__ == "__main__":
    generate_all_tracks()
