"""Committee daemon — runs the members continuously as a background process.

Loops forever: run the next member's gated cycle -> derive app data -> sleep -> repeat.
Persists nothing extra (state lives in the master + SCORECARD + LOG, which each member updates).
Exponential backoff on errors so a transient network blip doesn't kill the loop.

Run in the foreground:      python3 daemon.py
Run detached (simple):      nohup python3 daemon.py > daemon.out 2>&1 &
Run under a manager:        see deploy/ (systemd unit, Dockerfile, Procfile)

Env:
  GOOGLE_MAPS_API_KEY   needed for the geocoder member (skip it if unset)
  CYCLE_SLEEP_SEC       seconds between cycles (default 900 = 15 min)
  CENSUS_EVERY_N        run the census once every N cycles (default 24; it changes slowly)
  GEOCODE_BATCH         branches per geocode cycle (default 50)
"""
import os, time, subprocess, traceback, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(HERE, "..", "pipeline")
SLEEP = int(os.environ.get("CYCLE_SLEEP_SEC", "900"))
CENSUS_EVERY = int(os.environ.get("CENSUS_EVERY_N", "24"))
GEOCODE_BATCH = os.environ.get("GEOCODE_BATCH", "50")

def log(msg):
    print(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)

def sh(cmd, cwd=None):
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)

def run_geocoder():
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        log("geocoder skipped (no GOOGLE_MAPS_API_KEY)"); return
    sh(["python3", "run_cycle.py", "--member", "geocoder", "--batch", GEOCODE_BATCH], cwd=HERE)

def run_scout():
    master = os.path.join(HERE, "..", "source-data", "branches_final.json")
    provs = os.environ.get("SCOUT_PROVINCES", "ระยอง ชลบุรี เชียงใหม่").split()
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        log("scout skipped (no GOOGLE_MAPS_API_KEY)"); return
    sh(["python3", "scout.py", "--in", master, "--provinces", *provs], cwd=HERE)

def run_census():
    master = os.path.join(HERE, "..", "source-data", "branches_final.json")
    sh(["python3", "census.py", "--in", master], cwd=HERE)

def derive():
    sh(["python3", "derive.py"], cwd=PIPE)

def main():
    log(f"committee daemon starting · sleep={SLEEP}s · census every {CENSUS_EVERY} cycles")
    cyc, backoff = 0, 5
    while True:
        try:
            if cyc % CENSUS_EVERY == 0:
                run_census()            # authoritative factories (reachable anywhere)
            run_geocoder()              # accuracy backfill (needs API key)
            if cyc % CENSUS_EVERY == 0: run_scout()   # competitor mapping (needs API key)
            derive()                    # refresh the live app data
            backoff = 5                 # reset on success
            log(f"cycle {cyc} done; sleeping {SLEEP}s")
        except subprocess.CalledProcessError as e:
            log(f"cycle {cyc} member failed ({e}); backing off {backoff}s")
            time.sleep(backoff); backoff = min(backoff * 2, 1800); continue
        except Exception:
            log("unexpected error:\n" + traceback.format_exc())
            time.sleep(backoff); backoff = min(backoff * 2, 1800); continue
        cyc += 1
        time.sleep(SLEEP)

if __name__ == "__main__":
    main()
