"""
Analyze data collection consistency from the exported GrowSense CSV.

What it does:
- Loads the CSV export (growsense_export_2025-12-02_to_2025-12-04.csv) from project root.
- Computes per-device and overall gap statistics assuming 1 reading per minute cadence.
- Identifies device-specific gaps (one device down while others working) vs system-wide gaps (all devices down).
- Measures missing sensor values per device and overall.
- Breaks down missingness by hour-of-day (aggregated) and by specific day+hour.
- Produces charts and a summary JSON in analysis_outputs/.

Usage:
    python scripts/analyze_data_consistency.py

Outputs (written to analysis_outputs/):
    - summary.json: key metrics per device and overall
    - gaps_per_device.png: missing minutes per device
    - device_specific_vs_system_gaps.png: device-specific vs system-wide gap comparison
    - gap_periods_detailed.csv: detailed gap periods with start/end times
    - missing_rates_per_device.png: missing-value rate by sensor per device
    - missing_by_hour_heatmap.png: percent missing by hour-of-day per sensor (aggregated)
    - missing_by_day_and_hour_heatmap.png: percent missing by specific day and hour
    - missing_by_day_and_hour_summary.csv: day-hour specific missing data summary
    - readings_per_minute.png: readings per minute over time (overall + per device)
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CSV_PATH = PROJECT_ROOT / "growsense_export_2025-12-02_to_2025-12-04.csv"
OUT_DIR = PROJECT_ROOT / "analysis_outputs"

# Sensor columns to evaluate for missingness
SENSOR_COLS = ["temperature", "humidity", "light", "soil_moisture", "uv_light"]


def load_data(csv_path: Path) -> pd.DataFrame:
    """Load CSV export and parse timestamps."""
    if not csv_path.exists():
        print(f"❌ CSV file not found at {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)

    # Standardize column names (lowercase just in case)
    df.columns = [c.strip() for c in df.columns]

    # Parse timestamps
    for col in ["server_timestamp", "timestamp"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Use server_timestamp as primary; fallback to timestamp
    df["ts"] = df["server_timestamp"].fillna(df["timestamp"])

    # Ensure device_id present
    if "device_id" not in df.columns:
        print("❌ device_id column missing in CSV.")
        sys.exit(1)

    # Drop rows without timestamp
    df = df.dropna(subset=["ts"])

    # Filter device 4: exclude data before 6:30pm on 2025-12-02
    # Device 4 was not running before then
    device_4_cutoff = pd.Timestamp("2025-12-02 18:30:00", tz="UTC")
    
    # Identify device 4 by checking device_id ending with "_4" or containing "device_4"
    # Also check device_name in case device_id doesn't match the pattern
    device_4_candidates = df[
        (df["device_id"].str.endswith("_4", na=False)) |
        (df["device_id"].str.contains("device_4", na=False, regex=False)) |
        (df["device_name"].str.contains("4", na=False, regex=False))
    ]["device_id"].unique()
    
    if len(device_4_candidates) > 0:
        # Use the first matching device (assuming it's device 4)
        device_4_id = device_4_candidates[0]
        device_4_mask = (df["device_id"] == device_4_id) & (df["ts"] < device_4_cutoff)
        if device_4_mask.any():
            excluded_count = device_4_mask.sum()
            device_4_name = df[df["device_id"] == device_4_id]["device_name"].iloc[0] if len(df[df["device_id"] == device_4_id]) > 0 else device_4_id
            print(f"ℹ️  Excluding {excluded_count} readings from {device_4_name} ({device_4_id}) before 2025-12-02 18:30:00")
            df = df[~device_4_mask]

    # Normalize device name/description
    if "device_name" not in df.columns:
        df["device_name"] = df["device_id"]
    if "device_description" not in df.columns:
        df["device_description"] = ""

    return df


def compute_gap_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute gap statistics assuming 1 reading per minute cadence.
    Returns dict with per-device and overall gap metrics.
    """
    results = {"devices": {}, "overall": {}}

    all_gaps_minutes = []
    total_expected = 0
    total_observed = 0

    for device_id, d in df.groupby("device_id"):
        d_sorted = d.sort_values("ts")

        # Minute-level expected count between first and last reading
        if len(d_sorted) == 0:
            continue

        first_ts = d_sorted["ts"].iloc[0]
        last_ts = d_sorted["ts"].iloc[-1]
        expected_minutes = int((last_ts - first_ts).total_seconds() // 60) + 1
        total_expected += expected_minutes
        total_observed += len(d_sorted)

        # Compute gaps
        diffs = d_sorted["ts"].diff().dropna()
        gaps = (diffs.dt.total_seconds() // 60 - 1).clip(lower=0)  # minutes missed between readings
        gaps = gaps[gaps > 0]

        gap_count = int(gaps.count())
        missing_minutes = int(gaps.sum())
        max_gap = int(gaps.max()) if gap_count > 0 else 0

        results["devices"][device_id] = {
            "device_name": d_sorted["device_name"].iloc[0],
            "readings": int(len(d_sorted)),
            "expected_minutes": expected_minutes,
            "missing_minutes": missing_minutes,
            "gap_count": gap_count,
            "max_gap_minutes": max_gap,
            "gap_minutes_distribution": gaps.tolist(),
        }

        all_gaps_minutes.extend(gaps.tolist())

    overall_missing = int(max(total_expected - total_observed, 0))
    results["overall"] = {
        "devices": len(results["devices"]),
        "total_readings": int(total_observed),
        "expected_minutes": int(total_expected),
        "missing_minutes": overall_missing,
        "gap_minutes_distribution": all_gaps_minutes,
    }

    return results


def compute_device_specific_gaps(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Identify device-specific gaps (one device down while others working)
    vs system-wide gaps (all devices down simultaneously).
    
    Returns dict with device-specific and system-wide gap statistics.
    """
    # Normalize timestamps to UTC and floor to minutes
    df_work = df.copy()
    df_work["ts_floor"] = df_work["ts"].dt.tz_convert("UTC").dt.floor("min")
    
    # Define operational start times for devices
    # Device 4 started at 6:30pm on 2025-12-02
    device_4_cutoff = pd.Timestamp("2025-12-02 18:30:00", tz="UTC")
    
    # Identify device 4
    device_4_id = None
    device_4_candidates = df_work[
        (df_work["device_id"].str.endswith("_4", na=False)) |
        (df_work["device_id"].str.contains("device_4", na=False, regex=False)) |
        (df_work["device_name"].str.contains("4", na=False, regex=False))
    ]["device_id"].unique()
    
    if len(device_4_candidates) > 0:
        device_4_id = device_4_candidates[0]
    
    # Track operational start time for each device
    device_operational_start = {}
    for device_id, d in df_work.groupby("device_id"):
        if device_id == device_4_id:
            # Device 4 operational start is 6:30pm on 12/2
            device_operational_start[device_id] = device_4_cutoff
        else:
            # Other devices start from their first reading
            device_operational_start[device_id] = d["ts_floor"].min()
    
    # Create minute-level index for all devices (in UTC)
    start_min = df_work["ts_floor"].min()
    end_min = df_work["ts_floor"].max()
    all_minutes = pd.date_range(start=start_min, end=end_min, freq="min", tz="UTC")
    
    # For each device, create a presence indicator per minute
    device_presence = {}
    for device_id, d in df_work.groupby("device_id"):
        d_minutes = d["ts_floor"]
        device_presence[device_id] = set(d_minutes)
    
    # Analyze each minute
    device_specific_gaps = {device_id: [] for device_id in device_presence.keys()}
    system_wide_gaps = []
    
    for minute in all_minutes:
        # Only consider devices that should be operational at this minute
        operational_devices = [
            dev_id for dev_id, start_time in device_operational_start.items()
            if minute >= start_time
        ]
        
        if not operational_devices:
            # No devices should be operational yet
            continue
        
        # Check which operational devices are present/missing
        devices_present = [
            dev_id for dev_id in operational_devices 
            if dev_id in device_presence and minute in device_presence[dev_id]
        ]
        devices_missing = [
            dev_id for dev_id in operational_devices 
            if dev_id not in devices_present
        ]
        
        if len(devices_missing) == 0:
            # All operational devices present
            continue
        elif len(devices_present) == 0:
            # System-wide gap: all operational devices missing
            system_wide_gaps.append(minute)
        else:
            # Device-specific gap: some devices missing while others present
            for dev_id in devices_missing:
                device_specific_gaps[dev_id].append(minute)
    
    # Convert to statistics
    results = {
        "device_specific": {},
        "system_wide": {
            "gap_minutes": len(system_wide_gaps),
            "gap_periods": _count_consecutive_gaps(system_wide_gaps),
        }
    }
    
    for device_id, gap_minutes in device_specific_gaps.items():
        device_name = df[df["device_id"] == device_id]["device_name"].iloc[0] if len(df[df["device_id"] == device_id]) > 0 else device_id
        results["device_specific"][device_id] = {
            "device_name": device_name,
            "gap_minutes": len(gap_minutes),
            "gap_periods": _count_consecutive_gaps(gap_minutes),
        }
    
    return results


def _count_consecutive_gaps(gap_minutes: List) -> List[Dict[str, Any]]:
    """Count consecutive gap periods from a list of gap minutes."""
    if not gap_minutes:
        return []
    
    gap_minutes = sorted(gap_minutes)
    periods = []
    current_start = gap_minutes[0]
    current_end = gap_minutes[0]
    
    for i in range(1, len(gap_minutes)):
        if (gap_minutes[i] - current_end).total_seconds() <= 60:  # Within 1 minute
            current_end = gap_minutes[i]
        else:
            # End of current period
            periods.append({
                "start": current_start.isoformat(),
                "end": current_end.isoformat(),
                "duration_minutes": int((current_end - current_start).total_seconds() // 60) + 1,
            })
            current_start = gap_minutes[i]
            current_end = gap_minutes[i]
    
    # Add last period
    periods.append({
        "start": current_start.isoformat(),
        "end": current_end.isoformat(),
        "duration_minutes": int((current_end - current_start).total_seconds() // 60) + 1,
    })
    
    return periods


def compute_missing_values(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute missing-value rates per sensor, per device, and overall."""
    summary = {"devices": {}, "overall": {}}

    for device_id, d in df.groupby("device_id"):
        device_summary = {}
        total = len(d)
        for col in SENSOR_COLS:
            missing = d[col].isna().sum() if col in d.columns else total
            device_summary[col] = {
                "missing": int(missing),
                "rate": float(missing / total) if total else 0.0,
            }
        summary["devices"][device_id] = {
            "device_name": d["device_name"].iloc[0],
            "total": int(total),
            "sensors": device_summary,
        }

    # Overall
    total_all = len(df)
    overall_sensors = {}
    for col in SENSOR_COLS:
        missing = df[col].isna().sum() if col in df.columns else total_all
        overall_sensors[col] = {
            "missing": int(missing),
            "rate": float(missing / total_all) if total_all else 0.0,
        }

    summary["overall"] = {"total": int(total_all), "sensors": overall_sensors}
    return summary


def missing_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Compute percent missing by hour-of-day per sensor (overall)."""
    df_hour = df.copy()
    df_hour["hour"] = df_hour["ts"].dt.tz_convert("UTC").dt.hour

    records = []
    for col in SENSOR_COLS:
        if col not in df_hour.columns:
            continue
        agg = (
            df_hour.assign(is_missing=df_hour[col].isna())
            .groupby("hour")["is_missing"]
            .mean()
            .reset_index()
        )
        agg["sensor"] = col
        agg["percent_missing"] = agg["is_missing"] * 100
        records.append(agg[["hour", "sensor", "percent_missing"]])

    if not records:
        return pd.DataFrame(columns=["hour", "sensor", "percent_missing"])

    return pd.concat(records, ignore_index=True)


def missing_by_day_and_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Compute percent missing by specific day and hour per sensor."""
    df_day_hour = df.copy()
    df_day_hour["date"] = df_day_hour["ts"].dt.tz_convert("UTC").dt.date
    df_day_hour["hour"] = df_day_hour["ts"].dt.tz_convert("UTC").dt.hour
    df_day_hour["day_hour"] = df_day_hour["date"].astype(str) + " " + df_day_hour["hour"].astype(str).str.zfill(2) + ":00"

    records = []
    for col in SENSOR_COLS:
        if col not in df_day_hour.columns:
            continue
        agg = (
            df_day_hour.assign(is_missing=df_day_hour[col].isna())
            .groupby(["date", "hour", "day_hour"])["is_missing"]
            .mean()
            .reset_index()
        )
        agg["sensor"] = col
        agg["percent_missing"] = agg["is_missing"] * 100
        records.append(agg[["date", "hour", "day_hour", "sensor", "percent_missing"]])

    if not records:
        return pd.DataFrame(columns=["date", "hour", "day_hour", "sensor", "percent_missing"])

    result = pd.concat(records, ignore_index=True)
    result = result.sort_values(["date", "hour", "sensor"])
    return result


def readings_per_minute(df: pd.DataFrame) -> pd.DataFrame:
    """Compute readings per minute overall and per device."""
    d = df.copy()
    d["minute"] = d["ts"].dt.floor("min")
    counts = d.groupby(["minute", "device_id"]).size().reset_index(name="count")
    overall = d.groupby("minute").size().reset_index(name="count")
    overall["device_id"] = "ALL"
    overall = overall[["minute", "device_id", "count"]]
    return pd.concat([overall, counts], ignore_index=True)


def ensure_out_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def plot_gaps_per_device(gap_stats: Dict[str, Any], out_dir: Path) -> None:
    data = []
    for device_id, stats in gap_stats["devices"].items():
        data.append(
            {
                "device_id": device_id,
                "device_name": stats["device_name"],
                "missing_minutes": stats["missing_minutes"],
                "gap_count": stats["gap_count"],
                "max_gap_minutes": stats["max_gap_minutes"],
            }
        )
    if not data:
        return
    df_plot = pd.DataFrame(data).sort_values("missing_minutes", ascending=False)

    plt.figure(figsize=(10, 6))
    sns.barplot(data=df_plot, x="missing_minutes", y="device_name", color="#4C72B0")
    plt.xlabel("Missing minutes (total)")
    plt.ylabel("Device")
    plt.title("Missing Minutes per Device (1/min expected)")
    plt.tight_layout()
    plt.savefig(out_dir / "gaps_per_device.png", dpi=200)
    plt.close()


def plot_missing_rates_per_device(missing_stats: Dict[str, Any], out_dir: Path) -> None:
    records = []
    for device_id, stats in missing_stats["devices"].items():
        for sensor, vals in stats["sensors"].items():
            records.append(
                {
                    "device_id": device_id,
                    "device_name": stats["device_name"],
                    "sensor": sensor,
                    "missing_rate_pct": vals["rate"] * 100,
                }
            )
    if not records:
        return
    df_plot = pd.DataFrame(records)

    plt.figure(figsize=(10, 6))
    ax = sns.barplot(
        data=df_plot,
        x="missing_rate_pct",
        y="sensor",
        hue="device_name",
        orient="h",
    )
    
    # Add percentage labels on each bar
    for container in ax.containers:
        ax.bar_label(container, fmt='%.2f%%', padding=3)
    
    plt.xlabel("Missing rate (%)")
    plt.ylabel("Sensor")
    plt.title("Missing Value Rate by Sensor and Device")
    plt.legend(title="Device", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(out_dir / "missing_rates_per_device.png", dpi=200)
    plt.close()


def plot_missing_by_hour(df_hour: pd.DataFrame, out_dir: Path) -> None:
    """Plot aggregated missing by hour (across all days)."""
    if df_hour.empty:
        return
    pivot = df_hour.pivot(index="sensor", columns="hour", values="percent_missing")
    plt.figure(figsize=(12, 4))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="Reds", cbar_kws={"label": "% missing"})
    plt.title("Percent Missing by Hour of Day (UTC) - Aggregated")
    plt.xlabel("Hour of Day")
    plt.ylabel("Sensor")
    plt.tight_layout()
    plt.savefig(out_dir / "missing_by_hour_heatmap.png", dpi=200)
    plt.close()


def plot_missing_by_day_and_hour(df_day_hour: pd.DataFrame, out_dir: Path) -> None:
    """Plot missing by specific day and hour."""
    if df_day_hour.empty:
        return
    
    # Create a pivot table with day_hour as columns
    pivot = df_day_hour.pivot(index="sensor", columns="day_hour", values="percent_missing")
    
    # Sort columns by date and hour
    df_day_hour_sorted = df_day_hour.sort_values(["date", "hour"])
    col_order = df_day_hour_sorted["day_hour"].unique()
    pivot = pivot.reindex(columns=col_order)
    
    plt.figure(figsize=(max(16, len(col_order) * 0.3), 6))
    sns.heatmap(
        pivot, 
        annot=False,  # Too many cells for annotations
        fmt=".1f", 
        cmap="Reds", 
        cbar_kws={"label": "% missing"},
        xticklabels=True,
        yticklabels=True
    )
    plt.title("Percent Missing by Day and Hour (UTC) - Per Sensor")
    plt.xlabel("Day and Hour")
    plt.ylabel("Sensor")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "missing_by_day_and_hour_heatmap.png", dpi=200)
    plt.close()
    
    # Also create a summary table showing which day-hours had issues
    summary_records = []
    for _, row in df_day_hour.iterrows():
        if row["percent_missing"] > 0:
            summary_records.append({
                "date": str(row["date"]),
                "hour": int(row["hour"]),
                "day_hour": row["day_hour"],
                "sensor": row["sensor"],
                "percent_missing": row["percent_missing"]
            })
    
    if summary_records:
        df_summary = pd.DataFrame(summary_records)
        df_summary = df_summary.sort_values(["date", "hour", "sensor"])
        df_summary.to_csv(out_dir / "missing_by_day_and_hour_summary.csv", index=False)


def plot_readings_per_minute(df_rpm: pd.DataFrame, out_dir: Path) -> None:
    if df_rpm.empty:
        return
    plt.figure(figsize=(12, 6))
    for device_id, d in df_rpm.groupby("device_id"):
        label = "Overall" if device_id == "ALL" else device_id
        plt.plot(d["minute"], d["count"], label=label, alpha=0.8)
    plt.xlabel("Time")
    plt.ylabel("Readings per minute")
    plt.title("Readings per Minute (Overall and per Device)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "readings_per_minute.png", dpi=200)
    plt.close()


def plot_device_specific_gaps(gap_analysis: Dict[str, Any], out_dir: Path) -> None:
    """Plot device-specific gaps vs system-wide gaps."""
    device_data = []
    for device_id, stats in gap_analysis["device_specific"].items():
        device_data.append({
            "device_id": device_id,
            "device_name": stats["device_name"],
            "gap_minutes": stats["gap_minutes"],
            "gap_periods": len(stats["gap_periods"]),
        })
    
    if not device_data:
        return
    
    df_plot = pd.DataFrame(device_data).sort_values("gap_minutes", ascending=False)
    
    # Create comparison plot
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # Device-specific gaps
    sns.barplot(data=df_plot, x="gap_minutes", y="device_name", ax=ax1, color="#E74C3C")
    ax1.set_xlabel("Gap Minutes (Device-Specific)")
    ax1.set_ylabel("Device")
    ax1.set_title("Device-Specific Gaps\n(Device down while others working)")
    
    # System-wide gaps
    sys_gaps = gap_analysis["system_wide"]["gap_minutes"]
    ax2.barh(["System-Wide"], [sys_gaps], color="#3498DB")
    ax2.set_xlabel("Gap Minutes")
    ax2.set_title(f"System-Wide Gaps\n(All devices down simultaneously)\nTotal: {sys_gaps} minutes")
    
    plt.tight_layout()
    plt.savefig(out_dir / "device_specific_vs_system_gaps.png", dpi=200)
    plt.close()
    
    # Save detailed gap periods to CSV
    gap_periods_records = []
    
    # Device-specific periods
    for device_id, stats in gap_analysis["device_specific"].items():
        for period in stats["gap_periods"]:
            gap_periods_records.append({
                "type": "device_specific",
                "device_id": device_id,
                "device_name": stats["device_name"],
                "start": period["start"],
                "end": period["end"],
                "duration_minutes": period["duration_minutes"],
            })
    
    # System-wide periods
    for period in gap_analysis["system_wide"]["gap_periods"]:
        gap_periods_records.append({
            "type": "system_wide",
            "device_id": "ALL",
            "device_name": "All Devices",
            "start": period["start"],
            "end": period["end"],
            "duration_minutes": period["duration_minutes"],
        })
    
    if gap_periods_records:
        df_periods = pd.DataFrame(gap_periods_records)
        df_periods = df_periods.sort_values(["start", "type"])
        df_periods.to_csv(out_dir / "gap_periods_detailed.csv", index=False)


def main():
    print("=" * 80)
    print("GROWSENSE DATA CONSISTENCY ANALYSIS")
    print("=" * 80)
    print(f"Input CSV: {CSV_PATH}")
    print(f"Output dir: {OUT_DIR}")
    print()

    ensure_out_dir(OUT_DIR)

    # Load data
    df = load_data(CSV_PATH)
    if df.empty:
        print("⚠️  CSV has no rows after filtering timestamps.")
        sys.exit(0)

    # Gap stats
    gap_stats = compute_gap_stats(df)

    # Device-specific vs system-wide gaps
    gap_analysis = compute_device_specific_gaps(df)

    # Missing value stats
    missing_stats = compute_missing_values(df)

    # Missing by hour (aggregated)
    df_hour = missing_by_hour(df)

    # Missing by day and hour (specific)
    df_day_hour = missing_by_day_and_hour(df)

    # Readings per minute
    df_rpm = readings_per_minute(df)

    # Save summary JSON
    summary = {
        "gap_stats": gap_stats,
        "gap_analysis": gap_analysis,
        "missing_stats": missing_stats,
    }
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"✓ summary.json written")

    # Plots
    plot_gaps_per_device(gap_stats, OUT_DIR)
    plot_device_specific_gaps(gap_analysis, OUT_DIR)
    plot_missing_rates_per_device(missing_stats, OUT_DIR)
    plot_missing_by_hour(df_hour, OUT_DIR)
    plot_missing_by_day_and_hour(df_day_hour, OUT_DIR)
    plot_readings_per_minute(df_rpm, OUT_DIR)
    print("✓ charts written")

    # Console summary (compact)
    print("\n--- GAP SUMMARY ---")
    for device_id, stats in gap_stats["devices"].items():
        print(
            f"{stats['device_name']} ({device_id}): "
            f"readings={stats['readings']}, "
            f"missing_minutes={stats['missing_minutes']}, "
            f"gaps={stats['gap_count']}, "
            f"max_gap={stats['max_gap_minutes']} min"
        )
    overall = gap_stats["overall"]
    print(
        f"OVERALL: readings={overall['total_readings']}, "
        f"expected_minutes={overall['expected_minutes']}, "
        f"missing_minutes={overall['missing_minutes']}"
    )

    print("\n--- DEVICE-SPECIFIC vs SYSTEM-WIDE GAPS ---")
    print("Device-Specific Gaps (device down while others working):")
    for device_id, stats in gap_analysis["device_specific"].items():
        print(
            f"  {stats['device_name']} ({device_id}): "
            f"{stats['gap_minutes']} minutes in {len(stats['gap_periods'])} periods"
        )
    sys_wide = gap_analysis["system_wide"]
    print(
        f"System-Wide Gaps (all devices down): "
        f"{sys_wide['gap_minutes']} minutes in {len(sys_wide['gap_periods'])} periods"
    )

    print("\n--- MISSING VALUES (overall rates) ---")
    for sensor, vals in missing_stats["overall"]["sensors"].items():
        print(f"{sensor}: {vals['missing']} missing ({vals['rate']*100:.2f}%)")

    print("\nDone. Results in analysis_outputs/")
    print("  - gap_periods_detailed.csv: Detailed gap periods")
    print("  - missing_by_day_and_hour_summary.csv: Day-hour specific missing data")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)

