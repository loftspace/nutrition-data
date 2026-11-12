"""Search a NorgesGruppen store (Meny, Spar, Joker, Kiwi) through the API the shops' own sites use.
Usage: python -I ng.py "<search words>" [meny|spar|joker|kiwi] [max_hits]
Prints one compact JSON line per product: ean, title, subtitle (size), vendor, category, per-100 nutrition.
Rules: one request per second (enforced here with a lock file), honest user agent."""
import json, os, sys, time, urllib.request, urllib.parse

UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
CHAINS = {"meny": 1300, "spar": 1210, "joker": 1220, "kiwi": 1100}
LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ng.last")


def pace():
    """One request per second across every agent: hold an exclusive lock on the pacing file."""
    import msvcrt
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT)
    while True:
        try:
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            time.sleep(0.2)
    try:
        os.lseek(fd, 1, 0)
        raw = os.read(fd, 64).decode() or "0"
        try:
            last = float(raw)
        except ValueError:
            last = 0.0
        wait = 1.1 - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        os.lseek(fd, 1, 0)
        os.write(fd, f"{time.time():<40}".encode())
    finally:
        os.lseek(fd, 0, 0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)


def search(q, chain="meny", n=12):
    pace()
    url = f"https://platform-rest-prod.ngdata.no/api/products/{CHAINS[chain]}/0?" + urllib.parse.urlencode(
        {"search": q, "page_size": n, "fieldset": "maximal", "full_response": "true"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    out = []
    if not isinstance(d, dict):
        return out  # Kiwi (1100) answers [] since 2026-11: its range is mostly Meny's, use meny or spar
    for h in d.get("hits", {}).get("hits", []):
        s = h["_source"]
        nut = {}
        for x in s.get("nutritionalContent") or []:
            nut[x.get("displayName") or x.get("name")] = f"{x.get('amount')} {x.get('unit') or ''}".strip()
        out.append({
            "ean": s.get("ean"), "title": s.get("title"), "subtitle": s.get("subtitle"),
            "vendor": s.get("vendor"), "category": s.get("categoryName"),
            "url": f"https://{chain}.no/varer/{s.get('slugifiedUrl')}" if s.get("slugifiedUrl") else None,
            "per100": nut, "for_sale": s.get("isForSale"),
        })
    return out


if __name__ == "__main__":
    q = sys.argv[1]
    chain = sys.argv[2] if len(sys.argv) > 2 else "meny"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    for p in search(q, chain, n):
        print(json.dumps(p, ensure_ascii=True))
