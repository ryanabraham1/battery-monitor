"""Query JLCPCB's parts library for live stock / price / basic-vs-extended.
usage: python jlc.py KEYWORD [KEYWORD ...]   (use C-numbers for exact lookups)
"""
import sys, json, time, requests

URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
HDR = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}


def search(kw, n=8):
    for _ in range(3):
        try:
            r = requests.post(URL, headers=HDR, timeout=25,
                              data=json.dumps({"keyword": kw, "currentPage": 1, "pageSize": n}))
            d = r.json()
            return (d.get("data") or {}).get("componentPageInfo", {}).get("list") or []
        except Exception as e:  # noqa
            err = e
            time.sleep(2)
    print("  ERR", err)
    return []


def row(c):
    pr = c.get("componentPrices") or []
    p1 = pr[0]["productPrice"] if pr else None
    return dict(lcsc=c.get("componentCode"), mpn=c.get("componentModelEn"),
                brand=c.get("componentBrandEn"), pkg=c.get("componentSpecificationEn"),
                stock=c.get("stockCount"), lib=c.get("componentLibraryType"),
                pref=c.get("preferredComponentFlag"), price=p1,
                desc=(c.get("describe") or "")[:110])


if __name__ == "__main__":
    for kw in sys.argv[1:]:
        print("===", kw)
        for c in search(kw):
            r = row(c)
            print("  {lcsc:>10} | {mpn} | {brand} | {pkg} | stock {stock} | {lib}{p} | ${price} | {desc}".format(
                p="/pref" if r["pref"] else "", **r))
        time.sleep(0.6)
