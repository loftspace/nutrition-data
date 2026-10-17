import sys
from common import *
from nortura_cms import *

SOURCE = "prior"


def discover(cl, log):
    return sitemap_urls(cl, log, ["https://www.prior.no/sitemaps-1-section-sapProducts-2-sitemap.xml"], r"prior\.no/produkter/")


def scrape(cl, url):
    html = cl.get(url)
    return parse(html, "Prior") if html else None


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
