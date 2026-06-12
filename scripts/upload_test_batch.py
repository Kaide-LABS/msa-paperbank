# -*- coding: utf-8 -*-
"""Upload the ~40-file TEST batch from the local corpus zip to GCS, preserving folder structure
(so the job can derive school/dept/level/semester/year + course code from the object key).
Run LOCALLY. Reads the file list from trial_sample.json. Bounded: only those 40 files."""
import os, sys, zipfile, json
from google.cloud import storage

ZIP = r"c:\Users\hp\paumsa-wsp-pqb-agent\PAU Muslim Committee Initiative-20260601T131802Z-3-001.zip"
SAMPLE = r"c:\tmp\pau-probe\trial_sample.json"
BUCKET = sys.argv[1] if len(sys.argv) > 1 else os.environ["GCS_BUCKET"]
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "cloud_test_batch/"
ROOT = "PAU Muslim Committee Initiative/"   # stripped so the key starts at <School>/...

zf = zipfile.ZipFile(ZIP)
sample = json.load(open(SAMPLE))
sc = storage.Client()
bucket = sc.bucket(BUCKET)

print(f"Uploading {len(sample)} files -> gs://{BUCKET}/{PREFIX}")
n = 0
for s in sample:
    name = s["name"]
    rel = name[len(ROOT):] if name.startswith(ROOT) else name
    key = PREFIX + rel
    data = zf.read(name)
    bucket.blob(key).upload_from_string(data)
    n += 1
    if n % 10 == 0 or n == len(sample):
        print(f"  {n}/{len(sample)} ... {rel[:60]}")
print(f"DONE: {n} objects under gs://{BUCKET}/{PREFIX}")
