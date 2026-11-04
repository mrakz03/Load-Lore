# "Sort: most popular": where the order comes from

No ammunition maker or store publishes sales counts per load. The Load Dictionary's
"Sort: most popular" uses one large US retailer's own sales ranking instead:
**Impact Guns' "Best Selling" order** on each cartridge / gauge page
(`https://www.impactguns.com/<slug>?sort=bestselling&page=N`, 40 products a page), read
**Nov 4 2026**.

## What was read

- Pages 1 and 2 (page 3 for 9mm) of: 9mm, 308-win (also 7.62x51mm NATO), 223-556 (.223 Remington
  and 5.56x45mm NATO), 45-acp, 40-sw, 38-special, 22-lr, 357-magnum, 30-06, 12-ga-ammo.
- Page 1 of 50 more cartridge / gauge pages (every slug in `popularity_listings.tsv`).
- Cartridges whose Impact Guns page could not be found or opened (.44 Special, .454 Casull,
  .30 Carbine, .338 Win Mag, .280 Rem, 16 gauge and others) have no places: their loads sort by
  brand (product line).
- The store lists products that have no sales alphabetically after the ones that do; a trailing
  run of 5 or more alphabetical listings was treated as unranked and left out.

Every listing read is in `popularity_listings.tsv` (slug, page, place, listing name).

## Matching listings to loads

A listing was matched to a load of the same cartridge by brand (with aliases such as
"Speer Gold Dot" / "Gold Dot", "CCI Blazer" / "Blazer"), bullet weight (within 1.5 gr), the
product line / bullet words (synonyms such as "Extrema" = "Hyperformance", "BTHP" = "OTM"), bullet
type (FMJ / hollow point / soft point must agree) and +P. A listing with only generic words
("FMJ", "JHP") could only match a load with no product line. Shotshells matched by brand, line,
shell length, shot size, payload or pellet count and steel / lead. Where two listings matched the
same load, the better (lower) place was kept.

Result: `data/popularity.csv` gives 933 loads in 61 cartridges / gauges a place (`rank` = the
listing's position on Impact Guns' list, `impact_listing` = the listing's name). A PCC "(est.)"
copy and a .22's "(handgun muzzle velocity)" copy share their load's place.

## In the app

The app counts the places again over the loads listed (so the best seller reads 1), shows them
in a "Popular" column on PC tables, and sorts ranked loads first, then the rest by brand (product
line). Handloads have no place. To refresh: read the pages again, re-match, replace
`data/popularity.csv` and update the date in `POPULARITY_SOURCE` (load_lore.py).
