#!/usr/bin/env python3
"""Dump Internet Archive CDX index (status 200 html, collapsed per URL, newest capture) for a host.
Usage: cdx_dump.py <host> <outfile>. 1 request/second, honest UA. Paged with resumeKey."""
import sys, time, requests, urllib.parse, datetime
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
host, out = sys.argv[1], sys.argv[2]
extra = sys.argv[3:]
base = "https://web.archive.org/cdx/search/cdx"
params = {"url": host + "/*", "output": "txt", "fl": "timestamp,original,statuscode,mimetype",
          "filter": ["statuscode:200", "mimetype:text/html"], "collapse": "urlkey", "limit": 50000, "showResumeKey": "true"}
n = 0; key = None
with open(out, "w", encoding="utf8") as f:
    while True:
        p = dict(params)
        if key: p["resumeKey"] = key
        for attempt in range(6):
            time.sleep(1.1)
            try:
                r = requests.get(base, params=p, headers={"User-Agent": UA}, timeout=300)
                if r.status_code == 200: break
                print("HTTP", r.status_code, flush=True); time.sleep(10 * (attempt + 1))
            except Exception as e:
                print("ERR", e, flush=True); time.sleep(10 * (attempt + 1))
        else:
            sys.exit("cdx failed")
        lines = r.text.split("\n")
        key = None
        # resume key is after a blank line
        if "" in lines:
            i = lines.index("")
            if i + 1 < len(lines) and lines[i + 1].strip():
                key = lines[i + 1].strip()
            lines = lines[:i]
        for ln in lines:
            if ln.strip():
                f.write(ln + "\n"); n += 1
        print(datetime.datetime.now().isoformat(timespec="seconds"), host, "rows", n, "more" if key else "done", flush=True)
        if not key: break
