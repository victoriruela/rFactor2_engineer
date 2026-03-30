"""Telemetry tab: lap-time display and interactive lap chart."""

from __future__ import annotations

import pandas as pd

from frontend.components import telemetry_embed


def compute_fastest_lap(df_local: pd.DataFrame, laps: list) -> tuple[dict, int | None]:
    """Return (lap_times_dict, fastest_lap_number).

    Tries ``Last_Laptime`` first; falls back to elapsed-time delta.
    """
    lap_times: dict[int, float] = {}
    has_last_laptime = "Last_Laptime" in df_local.columns

    for lap in laps:
        lap_df = df_local[df_local["Lap_Number"] == lap]
        if lap_df.empty:
            continue
        if has_last_laptime:
            lt = lap_df["Last_Laptime"].iloc[-1]
            if lt > 0:
                lap_times[lap] = float(lt)
                continue
        if "Session_Elapsed_Time" in df_local.columns:
            lap_times[lap] = float(
                lap_df["Session_Elapsed_Time"].max() - lap_df["Session_Elapsed_Time"].min()
            )

    fastest = min(lap_times, key=lap_times.get) if lap_times else None
    return lap_times, fastest


def render_telemetry_tab(
    df_local: pd.DataFrame,
    laps: list,
    all_lap_figs: list,
    lap_times: dict,
    fastest_lap: int | None,
) -> None:
    """Render the telemetry tab with formatted lap times and interactive charts."""
    lap_options = [
        f"V{lap} ({_fmt_lap(lap_times[lap])})" if lap in lap_times else f"V{lap}"
        for lap in laps
    ]
    telemetry_embed.plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fmt_lap(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    tenths = int(round((s % 1) * 10))
    return f"{m}:{int(s):02}:{tenths}00"
