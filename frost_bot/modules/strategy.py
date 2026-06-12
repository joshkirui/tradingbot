from modules.logic import detect_h1_path, identify_x_zone, find_m15_target, check_liquidation_sweep
from modules.data_engine import get_session

def score_institutional_setup(df_h1, df_m15, df_m1):
    # Rule: Path Check
    bias = detect_h1_path(df_h1)
    if bias == "neutral": return {"valid": False, "reason": "No HTF Path"}

    # Rule: Liquidation Zone (x) Check
    x_zone = identify_x_zone(df_m1, bias)
    if not x_zone: return {"valid": False, "reason": "Zone X Missing"}

    # Rule: Defined Target POI
    target_poi = find_m15_target(df_m15, bias)
    if not target_poi: return {"valid": False, "reason": "No Target POI"}

    # Rule: Entry Model (Sweep)
    sweep_data = check_liquidation_sweep(df_m1, x_zone, bias)
    if not sweep_data["swept"]: return {"valid": False, "reason": "No Sweep of X"}

    # Risk Parameters
    entry, sl, tp = df_m1["close"].iloc[-1], sweep_data["sl"], target_poi
    risk, reward = abs(entry - sl), abs(tp - entry)
    
    if risk == 0 or (reward / risk) < 1.5: return {"valid": False, "reason": "Poor RR"}

    return {"valid": True, "bias": bias, "entry": entry, "sl": sl, "tp": tp, "rr": reward/risk}