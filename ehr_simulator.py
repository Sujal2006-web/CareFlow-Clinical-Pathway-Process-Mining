"""
CareFlow - Mock EHR event log simulator
Usage: python ehr_simulator.py [--cases 20000] [--loopback 0.40] [--out raw_ehr_events.csv]

Change --loopback to 0.05 to create the "AFTER fixing the intake form" dataset.
"""
import argparse, random
from datetime import datetime, timedelta
import pandas as pd

p = argparse.ArgumentParser()
p.add_argument("--cases", type=int, default=20000)
p.add_argument("--loopback", type=float, default=0.40)   # X-Ray -> Triage loop-back probability
p.add_argument("--skip_triage", type=float, default=0.03) # conformance violation
p.add_argument("--skip_doctor", type=float, default=0.02) # conformance violation
p.add_argument("--messy", type=float, default=0.03)       # share of dirty rows (for dbt cleaning)
p.add_argument("--seed", type=int, default=42)
p.add_argument("--out", default="raw_ehr_events.csv")
a = p.parse_args()

random.seed(a.seed)
DOCTORS = {f"D{str(i).zfill(2)}": s for i, s in enumerate(
    ["slow", "normal", "fast", "normal", "slow", "normal", "fast", "normal"], 1)}
DEPTS = ["Emergency", "Orthopedics", "General Medicine", "Pediatrics"]
AGE_GROUPS = ["0-17", "18-35", "36-60", "60+"]
AGE_W = [0.2, 0.3, 0.3, 0.2]
SPEED = {"slow": 1.5, "normal": 1.0, "fast": 0.7}

def mins(lo, hi, f=1.0):
    return timedelta(minutes=random.randint(lo, hi) * f)

rows = []
start_day = datetime(2025, 1, 1)

for i in range(1, a.cases + 1):
    pid = f"P{str(i).zfill(6)}"
    doc = random.choice(list(DOCTORS))
    f = SPEED[DOCTORS[doc]]
    age = random.choices(AGE_GROUPS, AGE_W)[0]
    gender = random.choice(["Male", "Female"])
    dept = random.choice(DEPTS)

    # arrival: busy mornings (8-11) and evenings (17-20)
    day = start_day + timedelta(days=random.randint(0, 89))
    hour = random.choices(range(24), [1]*6 + [3, 5, 8, 9, 8, 6, 5, 4, 4, 5, 6, 7, 8, 6, 4, 3, 2, 1][:18])[0]
    t = day.replace(hour=hour, minute=random.randint(0, 59))
    busy = 1.4 if hour in (8, 9, 10, 17, 18, 19) else 1.0  # rush-hour waits are longer

    acts = [("Registration", t)]
    t += mins(3, 10)
    if random.random() >= a.skip_triage:
        acts.append(("Triage", t)); t += mins(5, 15, busy)
    if random.random() >= a.skip_doctor:
        t += mins(5, 25, f * busy)           # waiting for doctor
        acts.append(("Doctor Consultation", t)); t += mins(8, 20, f)
    if random.random() < 0.65:               # X-Ray needed
        acts.append(("X-Ray", t)); t += mins(10, 30, busy)
        if random.random() < a.loopback:     # THE HIDDEN BOTTLENECK: missing form
            acts.append(("Triage", t)); t += mins(15, 35, busy)
            acts.append(("X-Ray", t)); t += mins(15, 35, busy)
        acts.append(("Doctor Consultation", t)); t += mins(8, 20, f)
    if random.random() < 0.35:
        acts.append(("Lab Test", t)); t += mins(15, 45, busy)
        acts.append(("Doctor Consultation", t)); t += mins(5, 15, f)
    acts.append(("Treatment", t)); t += mins(10, 30)
    acts.append(("Discharge", t))

    for act, ts in acts:
        rows.append([pid, act, ts, doc, age, gender, dept])

df = pd.DataFrame(rows, columns=["patient_id", "activity", "timestamp", "doctor_id",
                                 "age_group", "gender", "department"])

# ---- inject realistic mess so dbt has real cleaning work ----
n = len(df)
idx = random.sample(range(n), int(n * a.messy))
for k, ix in enumerate(idx):
    m = k % 4
    if m == 0:   df.at[ix, "activity"] = df.at[ix, "activity"].upper()
    elif m == 1: df.at[ix, "activity"] = "  " + df.at[ix, "activity"].lower() + " "
    elif m == 2: df.at[ix, "doctor_id"] = None
    else:        df.at[ix, "gender"] = df.at[ix, "gender"][0]  # M / F
dups = df.sample(frac=a.messy / 3, random_state=a.seed)       # duplicate rows
df = pd.concat([df, dups]).sort_values(["patient_id", "timestamp"]).reset_index(drop=True)
df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

df.to_csv(a.out, index=False)
print(f"{a.out}: {len(df):,} rows, {df.patient_id.nunique():,} cases")
