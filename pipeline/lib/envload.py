#!/usr/bin/env python3
"""
envload.py — load local secrets from a git-ignored .env, once
=============================================================
Lets the pipeline scripts read API keys (DATA_GO_TH_TOKEN, NSO_TOKEN, BOT_*,
GISTDA_SPHERE_KEY, …) from a `.env` file in the repo root instead of re-exporting
them every run. The `.env` is git-ignored — keys stay on your machine and are
never committed. Real shell env vars take precedence (setdefault).

Create the file once (copy .env.example to .env, fill in your keys).
"""
import os

def load_env(path=None):
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(os.path.dirname(here), ".env")   # repo root /.env
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
