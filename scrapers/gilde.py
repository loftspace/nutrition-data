import sys
from common import *
from nortura_cms import *

SOURCE = "gilde"


def discover(cl, log):
    return sitemap_urls(cl, log, ["https://www.gilde.no/sitemap.xml"], r"gilde\.no/produkter/")


def scrape(cl, url):
    html = cl.get(url)
    return parse(html, "Gilde") if html else None


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
