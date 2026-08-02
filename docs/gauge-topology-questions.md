# River questions for someone who knows Assam's rivers

Everything needed to answer is on the page, so nothing here should send
you looking something up.

Two parts:

- **Part 1** — 53 places that may be reading the wrong
  river. The bigger job.
- **Part 2** — 7 pairs of gauges, where a rise
  at one may give warning time to the other. Quick.

Built 2026-08-02 by
`scripts/build_gauge_decision_packets.py` from
`data/review/locality-gauge-mappings/current.json`.

## What is being asked

Every circle below shows a river level taken from a gauge. The distance
audit flagged these because the gauge is far away, or because a much
closer one exists. Distance alone proves nothing — a far gauge on the
**same river** can be right, and a close one on a **different river** is
useless. That is the judgement no script can make.

Three answers are allowed:

- **Keep** — the gauge is on the water that reaches this circle.
- **Reassign** — name the gauge that is.
- **No gauge fits** — nothing on this circle's drainage is gauged. This is
  a real answer, not a failure. Better to say so than to quietly show a
  number from the wrong river.

⚠️ Where a table says *river name matches one over the circle*, that is a
string comparison between two name lists. It means the two sources used
the same word. It is a place to look first, not an answer.

River names come from OpenStreetMap (© OpenStreetMap contributors, ODbL).

## Where the answers go

Answers are recorded in `config/gauge-topology-decisions.json`, one entry
per circle, each carrying who decided, their reasoning, and the date.
Then:

```
uv run python scripts/apply_gauge_decisions.py --check   # reads them back
uv run python scripts/apply_gauge_decisions.py --write   # applies them
```

`--check` refuses a circle that does not exist, a gauge that is not in the
CWC reference, and a reassign to a gauge that has stopped reporting.

**Your stated qualification is recorded as you give it** and travels with
every mapping it decided. It is a record-keeping field, not something the
site prints — the bulletin names you and stops there. Knowing Assam's
rivers is enough to answer these questions. Nothing here is written up as
a hydrologist sign-off.

**53 circles.** 22 are in the first
group: those are both far from their gauge *and* have a much closer one.

---

# Part 1 — is this place reading the right river?

## First: far gauge, and a much closer one exists

### Mahur — Dima Hasao

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 118.4 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Jiri River (60.6 km)
- Jenani River (53.0 km)
- Chikhu Nadi (20.1 km)
- Mahur River (9.0 km)
- NInduki Nadi (6.3 km)
- Savom Vādung (4.4 km)
- Jenām Nadi (4.2 km)
- Hāmān Ki (4.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Lakhipur (`009-MBDGHY`) | Barak | 44.0 km |  |
| Fulertal (`01-11-01-008`) | Barak | 44.1 km |  |
| Annapurna Ghat (`01-11-01-007`) | Barak | 50.2 km |  |
| Annapurnaghat (`010-MBDGHY`) | Barak | 50.2 km |  |
| TULARGRAM (`007-MDSIL`) | Sonai | 56.1 km |  |
| Katigorah (`015-MDSIL`) | Katakhal | 61.8 km |  |
| Badarpur Ghat (`01-11-01-006`) | Barak | 63.8 km |  |
| Badarpurghat (`011-MBDGHY`) | Barak | 63.8 km |  |
| Gumrabazar (`01-11-13-001`) | - | 64.3 km |  |
| Amraghat (`017-MBDghy`) | Sonai | 65.3 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Harangajao (`030-MBDGHY`) | Jatinga | 27.1 km |  |
| UDHARBOND (`025 - MDSIL`) | Barak | 37.0 km |  |
| CHIRIPOOL (`024- MDSIL`) | Barak | 42.3 km |  |
| Mojowari (`062-MBDNEW`) | Kopili | 42.8 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 46.1 km |  |
| SIBAPUR (`026- MDSIL`) | Barak | 48.3 km |  |
| NEAIRGRAM (`028- MDSIL`) | Barak | 53.9 km |  |
| KALAIN (`027- MDSIL`) | Barak | 60.8 km |  |
| Khandong Dam (`048-MBDGHY`) | Kopili | 62.7 km |  |
| Rangaphar Siding (`064-MBDNEW`) | Dhansiri (South) | 67.0 km |  |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Haflong — Dima Hasao

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 110.4 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Diyung River (36.9 km)
- Dalalma River (35.1 km)
- Jātinga Nadi (25.0 km)
- Kopili (21.5 km)
- Dlhamlal Nadi (17.1 km)
- Simleng (14.6 km)
- Jiri Gang (13.4 km)
- Robi Nadi (9.9 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Annapurna Ghat (`01-11-01-007`) | Barak | 45.9 km |  |
| Annapurnaghat (`010-MBDGHY`) | Barak | 45.9 km |  |
| Lakhipur (`009-MBDGHY`) | Barak | 46.1 km |  |
| Fulertal (`01-11-01-008`) | Barak | 46.3 km |  |
| Gumrabazar (`01-11-13-001`) | - | 53.6 km |  |
| Katigorah (`015-MDSIL`) | Katakhal | 55.1 km |  |
| Badarpur Ghat (`01-11-01-006`) | Barak | 55.2 km |  |
| Badarpurghat (`011-MBDGHY`) | Barak | 55.2 km |  |
| TULARGRAM (`007-MDSIL`) | Sonai | 55.5 km |  |
| Amraghat (`017-MBDghy`) | Sonai | 66.8 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Harangajao (`030-MBDGHY`) | Jatinga | 16.5 km |  |
| UDHARBOND (`025 - MDSIL`) | Barak | 34.8 km |  |
| Mojowari (`062-MBDNEW`) | Kopili | 37.1 km | river name matches one over the circle |
| Borkhola (`016-MDSIL`) | Jatinga | 39.2 km |  |
| CHIRIPOOL (`024- MDSIL`) | Barak | 44.9 km |  |
| SIBAPUR (`026- MDSIL`) | Barak | 47.6 km |  |
| KALAIN (`027- MDSIL`) | Barak | 50.4 km |  |
| Khandong Dam (`048-MBDGHY`) | Kopili | 50.4 km | river name matches one over the circle |
| NEAIRGRAM (`028- MDSIL`) | Barak | 51.6 km |  |
| Jalalpur (`01-10-24-001`) | - | 57.9 km |  |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Pathorighat (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 106.6 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Bhola River (90.3 km)
- Khulsi River (81.0 km)
- Nanoi (65.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 30.0 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 37.9 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 42.5 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 50.3 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 51.3 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 52.2 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 56.2 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 56.2 km |  |
| Dharamtul (`034-UBDDIB`) | Kopili | 57.8 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 34.6 km |  |
| Kaliajari (`044-MBDNEW`) | - | 38.5 km |  |
| Simultala (`046-MBDNEW`) | - | 39.3 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 42.2 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 45.7 km |  |
| Nona (`043-MBDNEW`) | - | 46.9 km |  |
| Jagibhakatgaon (`051`) | Kopili | 49.6 km |  |
| Changsari (`050-MBDNEW`) | - | 50.0 km |  |
| Ramdia (`041-MBDNEW`) | - | 60.1 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 69.7 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Silonijan — Karbi Anglong

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 101.2 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Kaliyani (56.8 km)
- Dhansiri River (38.7 km)
- Deopani Nadi (31.6 km)
- Daigurung (25.2 km)
- Khenari (13.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Bokajan (`023-UBDDIB`) | Dhansiri (South) | 21.4 km | river name matches one over the circle |
| Gelabil (`025-UBDDIB`) | Doyang | 31.6 km |  |
| Golaghat (`026-UBDDIB`) | Dhansiri (South) | 46.3 km | river name matches one over the circle |
| Numaligarh (`024-UBDDIB`) | Dhansiri (South) | 51.1 km | river name matches one over the circle |

<details><summary>3 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Garampani (`056-MBDNEW`) | Dhansiri (South) | 28.2 km | river name matches one over the circle |
| Bakalighat (`063-MBDNEW`) | - | 50.4 km |  |
| Ririgaon (`040-MBDNEW`) | Dhansiri (South) | 55.3 km | river name matches one over the circle |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Harisinga — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 100.6 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Rivers running through this circle**, longest first:

- Khulsi River (36.3 km)
- Bhola River (29.2 km)
- Puthimari (23.6 km)
- Nanai River (19.5 km)
- Kala River (16.2 km)
- Khaiara (10.6 km)
- Nanoi (3.7 km)
- Jia Ber Nadi (0.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| DRF (`005-MBDGHY`) | Puthimari | 17.3 km | river name matches one over the circle |
| Suklai (`007-MBDGHY`) | Suklai | 19.7 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 33.0 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 49.5 km | river name matches one over the circle |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 53.7 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 64.9 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 68.7 km |  |

<details><summary>9 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 47.2 km |  |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 57.7 km |  |
| Changsari (`050-MBDNEW`) | - | 60.6 km |  |
| Kaliajari (`044-MBDNEW`) | - | 63.3 km |  |
| Simultala (`046-MBDNEW`) | - | 63.7 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 64.7 km |  |
| Ramdia (`041-MBDNEW`) | - | 65.9 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 69.1 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 69.3 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Khoirabari (Pt) — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 99.9 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Puthimari (136.5 km)
- Khulsi River (81.0 km)
- Nanoi (65.4 km)
- Jia Ber Nadi (12.4 km)
- Khaiara (10.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 17.5 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 24.4 km | river name matches one over the circle |
| Matunga (`003-MBDGHY`) | Kalanadi | 38.8 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 39.1 km | river name matches one over the circle |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 48.1 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 52.2 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 56.7 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 59.0 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 39.8 km |  |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 48.0 km |  |
| Changsari (`050-MBDNEW`) | - | 49.1 km |  |
| Simultala (`046-MBDNEW`) | - | 50.4 km |  |
| Kaliajari (`044-MBDNEW`) | - | 50.6 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 51.0 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 55.7 km |  |
| Ramdia (`041-MBDNEW`) | - | 56.4 km |  |
| Jagibhakatgaon (`051`) | Kopili | 61.4 km |  |
| Sholmari (`042-MBDNEW`) | - | 66.1 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Maibong — Dima Hasao

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 98.8 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Langting River (90.3 km)
- Diyung River (43.2 km)
- Mahur River (42.9 km)
- Homo Nadi (29.0 km)
- Delen Nadi (28.3 km)
- Lumding River (28.1 km)
- Dhansiri River (20.6 km)
- Mupa River (19.3 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Kheronighat (`032-UBDDIB`) | Kopili | 58.0 km |  |
| Lakhipur (`009-MBDGHY`) | Barak | 67.9 km |  |
| Fulertal (`01-11-01-008`) | Barak | 68.0 km |  |

<details><summary>7 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Mojowari (`062-MBDNEW`) | Kopili | 24.0 km |  |
| Harangajao (`030-MBDGHY`) | Jatinga | 42.5 km |  |
| Gahampai (`061-MBDNEW`) | Kopili | 51.1 km |  |
| Khandong Dam (`048-MBDGHY`) | Kopili | 54.7 km |  |
| UDHARBOND (`025 - MDSIL`) | Barak | 59.5 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 65.4 km |  |
| CHIRIPOOL (`024- MDSIL`) | Barak | 66.3 km |  |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Gohpur — Biswanath

**Reads now:** Tezpur (`031-UBDDIB`) on the **Brahmaputra**, 92.2 km away.
Recorded reason for that mapping: *Brahmaputra at Tezpur*.

**Rivers running through this circle**, longest first:

- Kokila River (25.2 km)
- Holongi River (16.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Badatighat (`022-UBDDIB`) | Subansiri | 29.3 km |  |
| Numaligarh (`024-UBDDIB`) | Dhansiri (South) | 29.7 km |  |
| Golaghat (`026-UBDDIB`) | Dhansiri (South) | 51.4 km |  |
| Ranganadi NT Road crossing (`36-UBDDIB`) | Ranganadi | 51.6 km |  |
| Yazali (`046`) | Ranganadi | 56.4 km | upstream of Assam |
| Neamatighat (`019-UBDDIB`) | Brahmaputra | 57.5 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Chimpu (`0010NEID3`) | Sinki | 20.5 km | upstream of Assam |
| Jollang (`007NEID3`) | Sinki | 20.8 km | upstream of Assam |
| Ririgaon (`040-MBDNEW`) | Dhansiri (South) | 24.7 km |  |
| Jotte (`008NEID3`) | Sinki | 26.7 km | upstream of Assam |
| Doimukh (`058-UBDDIB`) | Dikrong | 28.3 km | upstream of Assam |
| Bana (`028-UBDDIB`) | Kamang | 34.5 km | upstream of Assam |
| Pare HEP (`078-UBDDIB`) | Dikrong | 40.7 km | upstream of Assam |
| Balighat (`052-UBDDIB`) | Subansiri | 53.6 km |  |
| Biswanath Ghat (`059-MBDNEW`) | Brahmaputra | 56.2 km |  |
| Garampani (`056-MBDNEW`) | Dhansiri (South) | 65.7 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Kalaigaon (Pt) — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 91.9 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Rivers running through this circle**, longest first:

- Bhola River (18.8 km)
- Nanoi (18.2 km)
- Khulsi River (17.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 26.4 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 32.9 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 43.3 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 47.7 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 53.3 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 55.1 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 56.1 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 58.7 km |  |
| Dharamtul (`034-UBDDIB`) | Kopili | 63.3 km |  |

<details><summary>9 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 39.4 km |  |
| Kaliajari (`044-MBDNEW`) | - | 44.1 km |  |
| Simultala (`046-MBDNEW`) | - | 44.9 km |  |
| Nona (`043-MBDNEW`) | - | 46.2 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 47.2 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 51.0 km |  |
| Changsari (`050-MBDNEW`) | - | 51.9 km |  |
| Jagibhakatgaon (`051`) | Kopili | 55.2 km |  |
| Ramdia (`041-MBDNEW`) | - | 61.0 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Pathorighat (Pt) — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 90.5 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Bhola River (90.3 km)
- Khulsi River (81.0 km)
- Nanoi (65.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 30.0 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 37.9 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 42.5 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 50.3 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 51.3 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 52.2 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 56.2 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 56.2 km |  |
| Dharamtul (`034-UBDDIB`) | Kopili | 57.8 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 34.6 km |  |
| Kaliajari (`044-MBDNEW`) | - | 38.5 km |  |
| Simultala (`046-MBDNEW`) | - | 39.3 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 42.2 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 45.7 km |  |
| Nona (`043-MBDNEW`) | - | 46.9 km |  |
| Jagibhakatgaon (`051`) | Kopili | 49.6 km |  |
| Changsari (`050-MBDNEW`) | - | 50.0 km |  |
| Ramdia (`041-MBDNEW`) | - | 60.1 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 69.7 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Mangaldoi (Pt) — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 89.3 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Bhola River (90.3 km)
- Tangla (64.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 34.9 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 42.5 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 43.8 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 45.9 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 47.5 km |  |
| Dharamtul (`034-UBDDIB`) | Kopili | 51.4 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 53.9 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 57.7 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 58.2 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 29.3 km |  |
| Kaliajari (`044-MBDNEW`) | - | 32.0 km |  |
| Simultala (`046-MBDNEW`) | - | 33.1 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 36.5 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 39.6 km |  |
| Jagibhakatgaon (`051`) | Kopili | 43.2 km |  |
| Nona (`043-MBDNEW`) | - | 48.5 km |  |
| Changsari (`050-MBDNEW`) | - | 48.5 km |  |
| Ramdia (`041-MBDNEW`) | - | 59.8 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 63.8 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Diphu — Karbi Anglong

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 88.7 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Dhansiri River (118.7 km)
- Jamuna River (30.7 km)
- Diphu River (29.7 km)
- Bara Langpher River (22.0 km)
- Lumding River (18.4 km)
- Dhansiri (2.5 km)
- Langhit Nadi (0.7 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Bokajan (`023-UBDDIB`) | Dhansiri (South) | 31.9 km | river name matches one over the circle |
| Gelabil (`025-UBDDIB`) | Doyang | 60.8 km |  |
| Kheronighat (`032-UBDDIB`) | Kopili | 61.3 km |  |

<details><summary>4 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Bakalighat (`063-MBDNEW`) | - | 35.7 km |  |
| Gahampai (`061-MBDNEW`) | Kopili | 56.6 km |  |
| Garampani (`056-MBDNEW`) | Dhansiri (South) | 62.1 km | river name matches one over the circle |
| Mojowari (`062-MBDNEW`) | Kopili | 64.9 km |  |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Jonai — Dhemaji

**Reads now:** Chouldhowaghat (`021-UBDDIB`) on the **Subansiri**, 88.6 km away.
Recorded reason for that mapping: *Subansiri at Chouldhowaghat downstream*.

**Rivers running through this circle**, longest first:

- Lali (44.6 km)
- Brahmaputra (41.5 km)
- Sissari (34.5 km)
- 西棱河 (23.4 km)
- STR3 (19.5 km)
- STR4 (3.2 km)
- Dikari River (2.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Dibrugarh (`010-UBDDIB`) | Brahmaputra | 33.3 km | river name matches one over the circle |
| Passighat (`005-UBDDIB`) | Siang | 44.5 km | upstream of Assam |
| Dholabazar (`007-UBDDIB`) | Lohit | 47.4 km |  |
| Chenimari (Khowang) (`013-UBDDIB`) | Buridehing | 52.1 km |  |
| Pangin (`003NEID-3`) | Siang | 55.0 km | upstream of Assam |
| Naharkatia (`012-ubddib`) | Buridehing | 55.7 km |  |
| Kabu basti (Kambang) (`048`) | Siyum | 58.7 km | upstream of Assam |

<details><summary>7 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| MURKONGSELEK (`068-UBDDIB`) | Siang | 20.6 km |  |
| GUTANG (`062-UBDDIB`) | Dibru | 33.8 km |  |
| BALIJAGAON (`060-UBDDIB`) | Buridehing | 44.6 km |  |
| Bogibil (`055-UBDDIB`) | Brahmaputra | 49.5 km | river name matches one over the circle |
| Doomdooma (`045-ubddib`) | Dibru | 49.9 km |  |
| Boleng (`004neid3`) | Siang | 63.8 km | upstream of Assam |
| Dihingmukh (`057-UBDDIB`) | Buridehing | 64.2 km |  |

</details>

**Question:** does the Subansiri reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Udalguri — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 80.0 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Rivers running through this circle**, longest first:

- Dhansiri (24.2 km)
- Bhola River (22.0 km)
- Jampani River (0.1 km)
- 查莫河 (0.1 km)
- Bhairabi River (0.0 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 37.0 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 39.1 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 54.8 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 57.6 km |  |
| Bhalukpong (`029-UBDDIB`) | Kamang | 65.0 km | upstream of Assam |
| Dharamtul (`034-UBDDIB`) | Kopili | 66.8 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 66.9 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 66.9 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 68.4 km |  |

<details><summary>8 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 38.7 km |  |
| Kaliajari (`044-MBDNEW`) | - | 50.0 km |  |
| Simultala (`046-MBDNEW`) | - | 52.6 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 57.4 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 59.9 km |  |
| Nona (`043-MBDNEW`) | - | 60.0 km |  |
| Jagibhakatgaon (`051`) | Kopili | 61.3 km |  |
| Changsari (`050-MBDNEW`) | - | 66.1 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Goreswar (Pt) — Tamulpur

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 78.0 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Rivers running through this circle**, longest first:

- Puthimari (56.7 km)
- Baralia (4.9 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 12.0 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 20.6 km | river name matches one over the circle |
| DRF (`005-MBDGHY`) | Puthimari | 25.3 km | river name matches one over the circle |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 25.9 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 31.5 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 39.5 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 41.4 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 55.1 km |  |

<details><summary>14 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 17.8 km |  |
| Changsari (`050-MBDNEW`) | - | 32.7 km |  |
| Ramdia (`041-MBDNEW`) | - | 36.2 km |  |
| Sholmari (`042-MBDNEW`) | - | 44.0 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 46.0 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 50.2 km |  |
| Simultala (`046-MBDNEW`) | - | 54.4 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 56.7 km |  |
| Kaliajari (`044-MBDNEW`) | - | 57.5 km |  |
| Satpokholi (`051-MBDNEW`) | - | 58.3 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Rangia (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 77.3 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Rivers running through this circle**, longest first:

- Baralia (25.9 km)
- Puthimari (9.5 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 7.5 km | river name matches one over the circle |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 16.7 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 26.5 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 28.5 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 28.6 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 39.0 km | river name matches one over the circle |
| Matunga (`003-MBDGHY`) | Kalanadi | 41.3 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 49.1 km |  |
| KULSI (`BY00045`) | Kulsi | 55.5 km |  |

<details><summary>15 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 6.8 km |  |
| Changsari (`050-MBDNEW`) | - | 19.7 km |  |
| Ramdia (`041-MBDNEW`) | - | 21.3 km |  |
| Sholmari (`042-MBDNEW`) | - | 31.3 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 39.7 km |  |
| Satpokholi (`051-MBDNEW`) | - | 43.5 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 46.8 km |  |
| Pohumara (`071-MBDNEW`) | - | 51.4 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 53.8 km |  |
| Simultala (`046-MBDNEW`) | - | 53.8 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Helem — Biswanath

**Reads now:** Tezpur (`031-UBDDIB`) on the **Brahmaputra**, 76.7 km away.
Recorded reason for that mapping: *Brahmaputra at Tezpur*.

**Rivers running through this circle**, longest first:

- Brahmaputra (19.7 km)
- Burai River (19.0 km)
- Holongi River (5.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Numaligarh (`024-UBDDIB`) | Dhansiri (South) | 30.0 km |  |
| Badatighat (`022-UBDDIB`) | Subansiri | 44.7 km |  |
| Golaghat (`026-UBDDIB`) | Dhansiri (South) | 55.6 km |  |
| NT Road Crossing Jia-Bharali (`030-UBDDIB`) | Jiabharali | 64.7 km |  |
| Yazali (`046`) | Ranganadi | 66.4 km | upstream of Assam |
| Ranganadi NT Road crossing (`36-UBDDIB`) | Ranganadi | 66.6 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Ririgaon (`040-MBDNEW`) | Dhansiri (South) | 24.1 km |  |
| Jotte (`008NEID3`) | Sinki | 24.2 km | upstream of Assam |
| Chimpu (`0010NEID3`) | Sinki | 26.8 km | upstream of Assam |
| Jollang (`007NEID3`) | Sinki | 27.9 km | upstream of Assam |
| Doimukh (`058-UBDDIB`) | Dikrong | 40.3 km | upstream of Assam |
| Biswanath Ghat (`059-MBDNEW`) | Brahmaputra | 40.6 km | river name matches one over the circle |
| Bana (`028-UBDDIB`) | Kamang | 50.1 km | upstream of Assam |
| Pare HEP (`078-UBDDIB`) | Dikrong | 53.0 km | upstream of Assam |
| Silghat (`054-MBDNEW`) | Brahmaputra | 63.3 km | river name matches one over the circle |
| Garampani (`056-MBDNEW`) | Dhansiri (South) | 65.8 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Nagarbera — Kamrup

**Reads now:** Guwahati(D.C.Court) (`001-MBDGHY`) on the **Brahmaputra**, 74.9 km away.
Recorded reason for that mapping: *Brahmaputra at Guwahati downstream*.

**Rivers running through this circle**, longest first:

- Kulsi (12.9 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| DUDHNAI (`bv000f5`) | Dudhnai | 24.2 km |  |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 38.4 km |  |
| KULSI (`BY00045`) | Kulsi | 40.1 km | river name matches one over the circle |
| Beki Road bridge (`002-LBDJPG`) | Beki | 46.1 km |  |
| PANCHARATNA (`BB000D6`) | Brahmaputra | 46.9 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 48.9 km |  |
| AIE NH XING (`033-LBDJPG`) | Aie | 57.3 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 58.4 km |  |
| BAHALPUR (`034-LBDJPG`) | Champamati | 59.1 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 60.9 km |  |

<details><summary>13 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Malibari (`047-MBDNEW`) | Kulsi | 10.3 km | river name matches one over the circle |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 18.4 km |  |
| Dudhnoi (`BV000FS`) | Dudhnai | 24.2 km |  |
| Krishnai (`058-MBDNEW`) | Krishnai | 33.9 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 35.1 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 38.5 km |  |
| Sholmari (`042-MBDNEW`) | - | 42.0 km |  |
| Pohumara (`071-MBDNEW`) | - | 45.3 km |  |
| Satpokholi (`051-MBDNEW`) | - | 45.7 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 52.0 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Umrangso — Dima Hasao

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 69.8 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Diyung River (125.5 km)
- Kopili (51.1 km)
- Kopili River (44.7 km)
- Lānglāi River (29.8 km)
- Dere Nadi (14.2 km)
- Umrong (10.3 km)
- Mahur River (5.4 km)
- Lumding River (4.3 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Kheronighat (`032-UBDDIB`) | Kopili | 34.3 km | river name matches one over the circle |
| Kampur (`033-UBDDIB`) | Kopili | 69.8 km | **reads this now**, river name matches one over the circle |

<details><summary>7 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Mojowari (`062-MBDNEW`) | Kopili | 15.9 km | river name matches one over the circle |
| Khandong Dam (`048-MBDGHY`) | Kopili | 19.5 km | river name matches one over the circle |
| Gahampai (`061-MBDNEW`) | Kopili | 31.0 km | river name matches one over the circle |
| Harangajao (`030-MBDGHY`) | Jatinga | 47.8 km |  |
| Bakalighat (`063-MBDNEW`) | - | 66.8 km |  |
| KALAIN (`027- MDSIL`) | Barak | 69.1 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 69.4 km |  |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Dalgaon (Pt) — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 67.3 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Rivers running through this circle**, longest first:

- Dhansiri (5.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 51.4 km |  |
| Dharamtul (`034-UBDDIB`) | Kopili | 53.2 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 55.8 km |  |
| Tezpur (`031-UBDDIB`) | Brahmaputra | 56.2 km |  |
| Bhalukpong (`029-UBDDIB`) | Kamang | 59.0 km | upstream of Assam |
| SONAPUR (`BKA00D7`) | Digaru | 62.3 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 64.8 km |  |
| NT Road Crossing Jia-Bharali (`030-UBDDIB`) | Jiabharali | 67.3 km | **reads this now** |
| Kampur (`033-UBDDIB`) | Kopili | 67.9 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 68.9 km |  |

<details><summary>9 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 23.5 km |  |
| Kaliajari (`044-MBDNEW`) | - | 39.9 km |  |
| Simultala (`046-MBDNEW`) | - | 44.6 km |  |
| Jagibhakatgaon (`051`) | Kopili | 50.7 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 52.3 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 52.8 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 58.9 km |  |
| Bhomoraguri (`035`) | Brahmaputra | 61.9 km |  |
| Banglabasti (`037-MBDNEW`) | - | 65.2 km |  |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Ghograpar (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 63.4 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Rivers running through this circle**, longest first:

- Pagladia (10.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 7.8 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 20.6 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 26.3 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 32.2 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 35.3 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 39.6 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 41.2 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 59.1 km |  |
| KULSI (`BY00045`) | Kulsi | 59.5 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 62.9 km |  |

<details><summary>12 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 8.1 km |  |
| Ramdia (`041-MBDNEW`) | - | 26.3 km |  |
| Sholmari (`042-MBDNEW`) | - | 27.1 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 27.4 km |  |
| Changsari (`050-MBDNEW`) | - | 31.2 km |  |
| Pohumara (`071-MBDNEW`) | - | 39.7 km |  |
| Satpokholi (`051-MBDNEW`) | - | 48.6 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 50.6 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 60.8 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 62.2 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Tamulpur — Tamulpur

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 61.2 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Rivers running through this circle**, longest first:

- Baralia (32.8 km)
- Pagladia (32.3 km)
- Puthimari (19.8 km)
- Jia Ber Nadi (10.7 km)
- Boga Juli (5.9 km)
- Dimabori Nadi (4.9 km)
- Darranga Nadi (1.2 km)
- Mutanga Nadi (0.0 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Matunga (`003-MBDGHY`) | Kalanadi | 13.5 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 15.4 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 17.4 km | river name matches one over the circle |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 26.6 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 35.2 km | river name matches one over the circle |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 56.1 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 56.2 km |  |
| Mathanguri (`001-LBDJPG`) | Beki | 61.2 km | **reads this now** |
| Beki Road bridge (`002-LBDJPG`) | Beki | 66.9 km |  |

<details><summary>9 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 25.4 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 37.2 km |  |
| Ramdia (`041-MBDNEW`) | - | 45.4 km |  |
| Sholmari (`042-MBDNEW`) | - | 45.5 km |  |
| Changsari (`050-MBDNEW`) | - | 47.4 km |  |
| Pohumara (`071-MBDNEW`) | - | 49.2 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 67.2 km |  |
| Satpokholi (`051-MBDNEW`) | - | 67.9 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 69.5 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

---

## Then: the rest of the flagged circles

Same question, lower urgency.

### Chamaria — Kamrup

**Reads now:** Guwahati(D.C.Court) (`001-MBDGHY`) on the **Brahmaputra**, 59.6 km away.
Recorded reason for that mapping: *Brahmaputra at Guwahati downstream*.

**Rivers running through this circle**, longest first:

- Kulsi (16.3 km)
- Singra (4.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| KULSI (`BY00045`) | Kulsi | 27.5 km | river name matches one over the circle |
| DUDHNAI (`bv000f5`) | Dudhnai | 39.1 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 48.5 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 48.6 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 52.0 km |  |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 52.5 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 56.2 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 57.3 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 59.6 km | **reads this now** |
| PANCHARATNA (`BB000D6`) | Brahmaputra | 60.9 km |  |

<details><summary>13 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Malibari (`047-MBDNEW`) | Kulsi | 6.1 km | river name matches one over the circle |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 12.5 km |  |
| Sholmari (`042-MBDNEW`) | - | 29.2 km |  |
| Satpokholi (`051-MBDNEW`) | - | 30.9 km |  |
| Dudhnoi (`BV000FS`) | Dudhnai | 39.1 km |  |
| Ramdia (`041-MBDNEW`) | - | 40.0 km |  |
| Pohumara (`071-MBDNEW`) | - | 41.4 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 44.5 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 45.6 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 46.1 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Boko — Kamrup

**Reads now:** Guwahati(D.C.Court) (`001-MBDGHY`) on the **Brahmaputra**, 59.5 km away.
Recorded reason for that mapping: *Brahmaputra at Guwahati downstream*.

**Rivers running through this circle**, longest first:

- Singra (27.2 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| KULSI (`BY00045`) | Kulsi | 18.8 km |  |
| DUDHNAI (`bv000f5`) | Dudhnai | 40.7 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 51.9 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 58.5 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 59.5 km | **reads this now** |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 60.7 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 62.5 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 63.7 km |  |
| PANCHARATNA (`BB000D6`) | Brahmaputra | 69.2 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 70.0 km |  |

<details><summary>13 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Malibari (`047-MBDNEW`) | Kulsi | 14.3 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 27.8 km |  |
| Satpokholi (`051-MBDNEW`) | - | 28.0 km |  |
| Sholmari (`042-MBDNEW`) | - | 39.8 km |  |
| Dudhnoi (`BV000FS`) | Dudhnai | 40.7 km |  |
| Ramdia (`041-MBDNEW`) | - | 44.9 km |  |
| Krishnai (`058-MBDNEW`) | Krishnai | 53.0 km |  |
| Changsari (`050-MBDNEW`) | - | 55.4 km |  |
| Pohumara (`071-MBDNEW`) | - | 56.5 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 57.5 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Dhekiajuli (Pt) — Udalguri

**Reads now:** NT Road Crossing Jia-Bharali (`030-UBDDIB`) on the **Jiabharali**, 55.8 km away.
Recorded reason for that mapping: *Jiabharali at NT Road Crossing downstream*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Brahmaputra (118.1 km)
- Dhansiri (38.5 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Tezpur (`031-UBDDIB`) | Brahmaputra | 44.1 km | river name matches one over the circle |
| Bhalukpong (`029-UBDDIB`) | Kamang | 51.2 km | upstream of Assam |
| Dharamtul (`034-UBDDIB`) | Kopili | 51.9 km |  |
| NT Road Crossing Jia-Bharali (`030-UBDDIB`) | Jiabharali | 55.8 km | **reads this now** |
| Kampur (`033-UBDDIB`) | Kopili | 61.3 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 63.5 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 67.5 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 68.3 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 22.6 km | river name matches one over the circle |
| Kaliajari (`044-MBDNEW`) | - | 43.1 km |  |
| Simultala (`046-MBDNEW`) | - | 49.1 km |  |
| Bhomoraguri (`035`) | Brahmaputra | 49.8 km | river name matches one over the circle |
| Jagibhakatgaon (`051`) | Kopili | 52.7 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 53.5 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 57.5 km |  |
| Banglabasti (`037-MBDNEW`) | - | 57.9 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 58.4 km |  |
| Silghat (`054-MBDNEW`) | Brahmaputra | 58.4 km | river name matches one over the circle |

</details>

**Question:** does the Jiabharali reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Dalgaon (Pt) — Darrang

**Reads now:** Puthimari NH Rd Xing (`006-MBDGHY`) on the **Puthimari**, 53.3 km away.
Recorded reason for that mapping: *Puthimari at NH Road Crossing downstream*.

**Rivers running through this circle**, longest first:

- Tangla (42.3 km)
- Dhansiri (22.1 km)
- Brahmaputra (11.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Suklai (`007-MBDGHY`) | Suklai | 43.7 km |  |
| Dharamtul (`034-UBDDIB`) | Kopili | 48.7 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 50.5 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 51.6 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 53.3 km | **reads this now** |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 56.9 km | river name matches one over the circle |
| Pandu (`025-MBDGHY`) | Brahmaputra | 63.7 km | river name matches one over the circle |
| Matunga (`003-MBDGHY`) | Kalanadi | 65.4 km |  |
| Tezpur (`031-UBDDIB`) | Brahmaputra | 65.5 km | river name matches one over the circle |
| Kampur (`033-UBDDIB`) | Kopili | 68.3 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 22.1 km | river name matches one over the circle |
| Kaliajari (`044-MBDNEW`) | - | 32.0 km |  |
| Simultala (`046-MBDNEW`) | - | 35.4 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 41.7 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 43.1 km |  |
| Jagibhakatgaon (`051`) | Kopili | 43.4 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 58.2 km |  |
| Changsari (`050-MBDNEW`) | - | 58.8 km |  |
| Nona (`043-MBDNEW`) | - | 59.3 km |  |
| Banglabasti (`037-MBDNEW`) | - | 66.5 km |  |

</details>

**Question:** does the Puthimari reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Sonari — Charaideo

**Reads now:** Sivasagar (`018-ubddib`) on the **Dikhow**, 50.5 km away.
Recorded reason for that mapping: *Dikhow at Sivasagar*.

**Rivers running through this circle**, longest first:

- Disang River (122.2 km)
- Tiyak Nadi (48.9 km)
- Tāukok River (34.7 km)
- Safrai Nadi (24.7 km)
- Timān River (20.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Desangpani (`015-UBDDIB`) | Desang | 17.0 km |  |
| Dillighat (`014-UBDDIB`) | Desang | 30.2 km |  |
| Nanglamoraghat (`016-UBDDIB`) | Desang | 31.2 km |  |
| Bihubar (`017-UBDDIB`) | Dikhow | 35.3 km |  |
| Chenimari (Khowang) (`013-UBDDIB`) | Buridehing | 35.8 km |  |
| Naharkatia (`012-ubddib`) | Buridehing | 36.9 km |  |
| Sivasagar (`018-ubddib`) | Dikhow | 50.5 km | **reads this now** |
| Dibrugarh (`010-UBDDIB`) | Brahmaputra | 52.2 km |  |
| Margherita (`011-UBDDIB`) | Buridehing | 63.1 km |  |

<details><summary>6 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Machaigaon (`038-MBDNEW`) | - | 30.8 km |  |
| BALIJAGAON (`060-UBDDIB`) | Buridehing | 35.8 km |  |
| Dihingmukh (`057-UBDDIB`) | Buridehing | 41.3 km |  |
| Bogibil (`055-UBDDIB`) | Brahmaputra | 49.1 km |  |
| B G Road (`039-MBDNEW`) | Brahmaputra | 54.7 km |  |
| GUTANG (`062-UBDDIB`) | Dibru | 65.1 km |  |

</details>

**Question:** does the Dikhow reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Baganpara (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 50.2 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Rivers running through this circle**, longest first:

- Pagladia (24.9 km)
- Dirang Nadi (20.3 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Matunga (`003-MBDGHY`) | Kalanadi | 15.4 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 25.2 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 26.6 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 26.6 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 40.2 km |  |
| Mathanguri (`001-LBDJPG`) | Beki | 50.2 km | **reads this now** |
| Beki Road bridge (`002-LBDJPG`) | Beki | 56.5 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 60.0 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 61.1 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 62.3 km |  |

<details><summary>8 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Nona (`043-MBDNEW`) | - | 28.2 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 28.5 km |  |
| Pohumara (`071-MBDNEW`) | - | 39.8 km |  |
| Sholmari (`042-MBDNEW`) | - | 41.8 km |  |
| Ramdia (`041-MBDNEW`) | - | 46.3 km |  |
| Changsari (`050-MBDNEW`) | - | 51.5 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 60.9 km |  |
| Satpokholi (`051-MBDNEW`) | - | 67.8 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Barama (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 49.4 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Pagladia (72.3 km)
- Dirang Nadi (21.2 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 16.0 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 26.6 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 32.1 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 34.8 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 35.9 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 49.2 km |  |
| Mathanguri (`001-LBDJPG`) | Beki | 49.4 km | **reads this now** |
| Pandu (`025-MBDGHY`) | Brahmaputra | 52.7 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 55.1 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 56.9 km |  |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Patacharkuchi (`049-MBDNEW`) | - | 18.6 km |  |
| Nona (`043-MBDNEW`) | - | 22.2 km |  |
| Sholmari (`042-MBDNEW`) | - | 30.7 km |  |
| Pohumara (`071-MBDNEW`) | - | 30.8 km |  |
| Ramdia (`041-MBDNEW`) | - | 37.2 km |  |
| Changsari (`050-MBDNEW`) | - | 44.8 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 49.7 km |  |
| Satpokholi (`051-MBDNEW`) | - | 57.7 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 63.2 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 63.6 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Lanka — Hojai

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 49.1 km away.
Recorded reason for that mapping: *Kopili at Kampur*.

**Rivers running through this circle**, longest first:

- Bara Langpher River (30.7 km)
- Lumding River (17.0 km)
- Jamuna River (11.6 km)
- Kopili (4.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Kheronighat (`032-UBDDIB`) | Kopili | 19.4 km | river name matches one over the circle |
| Kampur (`033-UBDDIB`) | Kopili | 49.1 km | **reads this now**, river name matches one over the circle |

<details><summary>6 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Gahampai (`061-MBDNEW`) | Kopili | 17.4 km | river name matches one over the circle |
| Bakalighat (`063-MBDNEW`) | - | 19.6 km |  |
| Mojowari (`062-MBDNEW`) | Kopili | 42.1 km | river name matches one over the circle |
| Banglabasti (`037-MBDNEW`) | - | 50.6 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 59.9 km | river name matches one over the circle |
| Khandong Dam (`048-MBDGHY`) | Kopili | 60.8 km | river name matches one over the circle |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Biswanath — Biswanath

**Reads now:** Tezpur (`031-UBDDIB`) on the **Brahmaputra**, 48.8 km away.
Recorded reason for that mapping: *Brahmaputra at Tezpur*.

**Rivers running through this circle**, longest first:

- Brahmaputra (43.4 km)
- Bargang (27.2 km)
- Burai River (26.4 km)
- 16 (25.5 km)
- Dighaimukh River (10.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| NT Road Crossing Jia-Bharali (`030-UBDDIB`) | Jiabharali | 35.6 km |  |
| Tezpur (`031-UBDDIB`) | Brahmaputra | 48.8 km | **reads this now**, river name matches one over the circle |
| Numaligarh (`024-UBDDIB`) | Dhansiri (South) | 52.9 km |  |
| Bhalukpong (`029-UBDDIB`) | Kamang | 63.3 km | upstream of Assam |
| Seppa (`027-UBDDIB`) | Kamang | 63.8 km | upstream of Assam |

<details><summary>8 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Biswanath Ghat (`059-MBDNEW`) | Brahmaputra | 18.2 km | river name matches one over the circle |
| Jotte (`008NEID3`) | Sinki | 33.9 km | upstream of Assam |
| Silghat (`054-MBDNEW`) | Brahmaputra | 36.5 km | river name matches one over the circle |
| Bhomoraguri (`035`) | Brahmaputra | 44.2 km | river name matches one over the circle |
| Chimpu (`0010NEID3`) | Sinki | 45.8 km | upstream of Assam |
| Jollang (`007NEID3`) | Sinki | 47.4 km | upstream of Assam |
| Ririgaon (`040-MBDNEW`) | Dhansiri (South) | 47.6 km |  |
| Doimukh (`058-UBDDIB`) | Dikrong | 62.6 km | upstream of Assam |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Kaliabor — Nagaon

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 48.4 km away.
Recorded reason for that mapping: *Kopili at Kampur*.

**Rivers running through this circle**, longest first:

- Kolong (34.9 km)
- Mora Diphlu (21.0 km)
- Diphlu (6.1 km)
- Brahmaputra (4.9 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Tezpur (`031-UBDDIB`) | Brahmaputra | 15.3 km | river name matches one over the circle |
| NT Road Crossing Jia-Bharali (`030-UBDDIB`) | Jiabharali | 32.2 km |  |
| Kampur (`033-UBDDIB`) | Kopili | 48.4 km | **reads this now** |
| Bhalukpong (`029-UBDDIB`) | Kamang | 61.0 km | upstream of Assam |
| Dharamtul (`034-UBDDIB`) | Kopili | 67.6 km |  |

<details><summary>7 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Silghat (`054-MBDNEW`) | Brahmaputra | 11.1 km | river name matches one over the circle |
| Bhomoraguri (`035`) | Brahmaputra | 11.3 km | river name matches one over the circle |
| Biswanath Ghat (`059-MBDNEW`) | Brahmaputra | 30.1 km | river name matches one over the circle |
| Banglabasti (`037-MBDNEW`) | - | 43.0 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 51.8 km |  |
| Bakalighat (`063-MBDNEW`) | - | 58.7 km |  |
| Polaguri (`055-MBDNEW`) | Brahmaputra | 60.3 km | river name matches one over the circle |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Goroimari — Kamrup

**Reads now:** Guwahati(D.C.Court) (`001-MBDGHY`) on the **Brahmaputra**, 48.2 km away.
Recorded reason for that mapping: *Brahmaputra at Guwahati downstream*.

**Rivers running through this circle**, longest first:

- Kulsi (23.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| KULSI (`BY00045`) | Kulsi | 16.8 km | river name matches one over the circle |
| Pandu (`025-MBDGHY`) | Brahmaputra | 40.5 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 44.0 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 48.2 km | **reads this now** |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 48.6 km |  |
| DUDHNAI (`bv000f5`) | Dudhnai | 49.9 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 57.1 km |  |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 64.7 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 66.7 km |  |

<details><summary>13 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Malibari (`047-MBDNEW`) | Kulsi | 16.9 km | river name matches one over the circle |
| Satpokholi (`051-MBDNEW`) | - | 18.7 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 21.3 km |  |
| Sholmari (`042-MBDNEW`) | - | 25.6 km |  |
| Ramdia (`041-MBDNEW`) | - | 30.9 km |  |
| Changsari (`050-MBDNEW`) | - | 42.6 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 46.1 km |  |
| Pohumara (`071-MBDNEW`) | - | 46.3 km |  |
| Nona (`043-MBDNEW`) | - | 48.4 km |  |
| Dudhnoi (`BV000FS`) | Dudhnai | 49.9 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Chhaygaon — Kamrup

**Reads now:** Guwahati(D.C.Court) (`001-MBDGHY`) on the **Brahmaputra**, 46.0 km away.
Recorded reason for that mapping: *Brahmaputra at Guwahati downstream*.

**Rivers running through this circle**, longest first:

- Kulsi (39.3 km)
- Gargara (0.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| KULSI (`BY00045`) | Kulsi | 7.8 km | river name matches one over the circle |
| Pandu (`025-MBDGHY`) | Brahmaputra | 38.4 km |  |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 46.0 km | **reads this now** |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 49.5 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 50.3 km |  |
| DUDHNAI (`bv000f5`) | Dudhnai | 53.5 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 66.2 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 66.3 km |  |

<details><summary>13 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Satpokholi (`051-MBDNEW`) | - | 14.4 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 22.7 km | river name matches one over the circle |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 30.2 km |  |
| Sholmari (`042-MBDNEW`) | - | 32.5 km |  |
| Ramdia (`041-MBDNEW`) | - | 33.1 km |  |
| Changsari (`050-MBDNEW`) | - | 42.3 km |  |
| Nona (`043-MBDNEW`) | - | 52.4 km |  |
| Dudhnoi (`BV000FS`) | Dudhnai | 53.5 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 54.4 km |  |
| Pohumara (`071-MBDNEW`) | - | 55.3 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Tihu (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 45.4 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Kaldiya Nadi (80.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 17.4 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 38.1 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 38.8 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 38.8 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 44.1 km |  |
| Mathanguri (`001-LBDJPG`) | Beki | 45.4 km | **reads this now** |
| PANBARI (`003-LBDJPG`) | Burisuti | 47.6 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 48.7 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 52.6 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 55.0 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Patacharkuchi (`049-MBDNEW`) | - | 6.4 km |  |
| Pohumara (`071-MBDNEW`) | - | 18.9 km |  |
| Sholmari (`042-MBDNEW`) | - | 22.6 km |  |
| Nona (`043-MBDNEW`) | - | 27.0 km |  |
| Ramdia (`041-MBDNEW`) | - | 35.0 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 37.7 km |  |
| Changsari (`050-MBDNEW`) | - | 46.0 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 51.2 km |  |
| Satpokholi (`051-MBDNEW`) | - | 52.1 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 52.2 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Phuloni — Karbi Anglong

**Reads now:** Kampur (`033-UBDDIB`) on the **Kopili**, 44.4 km away.
Recorded reason for that mapping: *Kopili at Kampur downstream*.

**Rivers running through this circle**, longest first:

- Jamuna River (54.3 km)
- Langhit Nadi (30.3 km)
- Dikharu Nadi (25.8 km)
- Bar Dikharu Nadi (19.9 km)
- Horu Dikharu Nadi (14.7 km)
- Kohora Nadi (5.2 km)
- Kaliyani (3.7 km)
- Deopani Nadi (2.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Kheronighat (`032-UBDDIB`) | Kopili | 39.5 km |  |
| Kampur (`033-UBDDIB`) | Kopili | 44.4 km | **reads this now** |
| Tezpur (`031-UBDDIB`) | Brahmaputra | 60.1 km |  |

<details><summary>8 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Bakalighat (`063-MBDNEW`) | - | 13.3 km |  |
| Gahampai (`061-MBDNEW`) | Kopili | 41.4 km |  |
| Banglabasti (`037-MBDNEW`) | - | 42.8 km |  |
| Silghat (`054-MBDNEW`) | Brahmaputra | 54.6 km |  |
| Magurgaon (`048-MBDNEW`) | Kopili | 54.9 km |  |
| Bhomoraguri (`035`) | Brahmaputra | 57.0 km |  |
| Biswanath Ghat (`059-MBDNEW`) | Brahmaputra | 57.3 km |  |
| Mojowari (`062-MBDNEW`) | Kopili | 68.5 km |  |

</details>

**Question:** does the Kopili reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Chapar (Pt) — Dhubri

**Reads now:** Dhubri (`005-LBDJPG`) on the **Brahmaputra**, 42.8 km away.
Recorded reason for that mapping: *Brahmaputra at Dhubri*.

**Rivers running through this circle**, longest first:

- Champamati (23.4 km)
- Brahmaputra (1.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| BAHALPUR (`034-LBDJPG`) | Champamati | 14.1 km | river name matches one over the circle |
| Kokrajhar (`039LBDJPG`) | Gaurang | 19.8 km |  |
| PANCHARATNA (`BB000D6`) | Brahmaputra | 20.1 km | river name matches one over the circle |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 28.6 km | river name matches one over the circle |
| AIE NH XING (`033-LBDJPG`) | Aie | 40.9 km |  |
| Dhubri (`005-LBDJPG`) | Brahmaputra | 42.8 km | **reads this now**, river name matches one over the circle |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 46.3 km |  |
| DUDHNAI (`bv000f5`) | Dudhnai | 52.4 km |  |
| Golokganj (`008-LBDJPG`) | Sankosh | 55.2 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 60.7 km |  |

<details><summary>7 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Kusumbil (`068-MBDNEW`) | - | 30.8 km |  |
| Krishnai (`058-MBDNEW`) | Krishnai | 39.6 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 40.1 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 47.6 km |  |
| South Salmara (`069-MBDNEW`) | Brahmaputra | 52.1 km | river name matches one over the circle |
| Dudhnoi (`BV000FS`) | Dudhnai | 52.4 km |  |
| Baladoba (`046-LBDJPG`) | Sankosh | 58.2 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Golokganj (Pt) — Kokrajhar

**Reads now:** Kokrajhar (`039LBDJPG`) on the **Gaurang**, 41.1 km away.
Recorded reason for that mapping: *Gaurang at Kokrajhar*.

**Rivers running through this circle**, longest first:

- Godadhar (31.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Golokganj (`008-LBDJPG`) | Sankosh | 14.9 km |  |
| Dhubri (`005-LBDJPG`) | Brahmaputra | 30.2 km |  |
| Kokrajhar (`039LBDJPG`) | Gaurang | 41.1 km | **reads this now** |
| BAHALPUR (`034-LBDJPG`) | Champamati | 59.0 km |  |
| PANCHARATNA (`BB000D6`) | Brahmaputra | 66.5 km |  |

<details><summary>3 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Baladoba (`046-LBDJPG`) | Sankosh | 24.0 km |  |
| Kusumbil (`068-MBDNEW`) | - | 30.7 km |  |
| South Salmara (`069-MBDNEW`) | Brahmaputra | 40.0 km |  |

</details>

**Question:** does the Gaurang reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Margherita — Tinsukia

**Reads now:** Dholabazar (`007-UBDDIB`) on the **Lohit**, 40.2 km away.
Recorded reason for that mapping: *Lohit at Dholabazar downstream*.

**Rivers running through this circle**, longest first:

- Burhi Dihing (81.7 km)
- Tirap River (69.6 km)
- Burhi Dehing River (16.5 km)
- Dirāk Nadi (10.6 km)
- Nāmdāng Nadi (10.3 km)
- Tipang Nadi (8.3 km)
- Namchik River (5.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Margherita (`011-UBDDIB`) | Buridehing | 20.9 km |  |
| Namsai (`009-UBDDIB`) | Nao Dehing | 22.4 km | upstream of Assam |
| Dholabazar (`007-UBDDIB`) | Lohit | 40.2 km | **reads this now** |
| Miao (`008-ubddib`) | Nao Dehing | 45.1 km | upstream of Assam |
| Naharkatia (`012-ubddib`) | Buridehing | 46.1 km |  |
| Dillighat (`014-UBDDIB`) | Desang | 51.9 km |  |
| Tezu (`006-UBDDIB`) | Lohit | 65.2 km | upstream of Assam |

<details><summary>10 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| JAGUNGHAT (`061-UBDDIB`) | Buridehing | 13.4 km |  |
| Udaipur (`049`) | Tirap | 14.9 km | river name matches one over the circle |
| Doomdooma (`045-ubddib`) | Dibru | 25.0 km |  |
| JAIRAMPUR (`067-UBDDIB`) | Buridehing | 31.0 km | upstream of Assam |
| Motipur (`050`) | Nao Dehing | 39.6 km | upstream of Assam |
| GUTANG (`062-UBDDIB`) | Dibru | 41.4 km |  |
| Pagoda (`059-UBDDIB`) | Lohit | 41.7 km | upstream of Assam |
| CHOWKHAMGHAT (`063-UBDDIB`) | Lohit | 51.5 km | upstream of Assam |
| BALIJAGAON (`060-UBDDIB`) | Buridehing | 58.0 km |  |
| MURKONGSELEK (`068-UBDDIB`) | Siang | 59.4 km |  |

</details>

**Question:** does the Lohit reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Bajali (Pt) — Baksa

**Reads now:** Mathanguri (`001-LBDJPG`) on the **Beki**, 39.8 km away.
Recorded reason for that mapping: *Beki at Mathanguri*.

**Named rivers nearby.** None has a point inside the drawn outline, which usually means the outline is wrong rather than that the circle has no river:

- Kaldiya Nadi (80.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 22.4 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 34.6 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 37.6 km |  |
| Mathanguri (`001-LBDJPG`) | Beki | 39.8 km | **reads this now** |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 43.6 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 43.7 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 45.2 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 46.2 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 54.6 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 58.9 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Patacharkuchi (`049-MBDNEW`) | - | 9.3 km |  |
| Pohumara (`071-MBDNEW`) | - | 20.0 km |  |
| Sholmari (`042-MBDNEW`) | - | 29.7 km |  |
| Nona (`043-MBDNEW`) | - | 31.2 km |  |
| Ramdia (`041-MBDNEW`) | - | 41.6 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 43.3 km |  |
| Changsari (`050-MBDNEW`) | - | 51.8 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 52.1 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 58.3 km |  |
| Satpokholi (`051-MBDNEW`) | - | 59.2 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Tinsukia — Tinsukia

**Reads now:** Dholabazar (`007-UBDDIB`) on the **Lohit**, 39.6 km away.
Recorded reason for that mapping: *Lohit at Dholabazar downstream*.

**Rivers running through this circle**, longest first:

- Lohit (21.7 km)
- Tingrāl Nadi (19.7 km)
- Sissari (14.4 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Naharkatia (`012-ubddib`) | Buridehing | 19.5 km |  |
| Dillighat (`014-UBDDIB`) | Desang | 36.6 km |  |
| Margherita (`011-UBDDIB`) | Buridehing | 37.8 km |  |
| Dholabazar (`007-UBDDIB`) | Lohit | 39.6 km | **reads this now**, river name matches one over the circle |
| Dibrugarh (`010-UBDDIB`) | Brahmaputra | 42.7 km |  |
| Chenimari (Khowang) (`013-UBDDIB`) | Buridehing | 48.6 km |  |
| Namsai (`009-UBDDIB`) | Nao Dehing | 53.3 km | upstream of Assam |
| Desangpani (`015-UBDDIB`) | Desang | 63.3 km |  |
| Passighat (`005-UBDDIB`) | Siang | 67.7 km | upstream of Assam |

<details><summary>8 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| GUTANG (`062-UBDDIB`) | Dibru | 11.9 km |  |
| BALIJAGAON (`060-UBDDIB`) | Buridehing | 19.9 km |  |
| Doomdooma (`045-ubddib`) | Dibru | 23.3 km |  |
| MURKONGSELEK (`068-UBDDIB`) | Siang | 34.9 km |  |
| Udaipur (`049`) | Tirap | 52.3 km |  |
| JAGUNGHAT (`061-UBDDIB`) | Buridehing | 54.4 km |  |
| Bogibil (`055-UBDDIB`) | Brahmaputra | 56.4 km |  |
| Dihingmukh (`057-UBDDIB`) | Buridehing | 64.0 km |  |

</details>

**Question:** does the Lohit reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Sarupathar — Golaghat

**Reads now:** Golaghat (`026-UBDDIB`) on the **Dhansiri (South)**, 39.3 km away.
Recorded reason for that mapping: *Dhansiri South at Golaghat*.

**Rivers running through this circle**, longest first:

- Dhansiri River (86.4 km)
- Doyang (64.1 km)
- ri4 (12.6 km)
- Diphupani river (9.6 km)
- Dhansiri (1.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Gelabil (`025-UBDDIB`) | Doyang | 10.5 km | river name matches one over the circle |
| Bokajan (`023-UBDDIB`) | Dhansiri (South) | 20.4 km | river name matches one over the circle |
| Golaghat (`026-UBDDIB`) | Dhansiri (South) | 39.3 km | **reads this now**, river name matches one over the circle |
| Numaligarh (`024-UBDDIB`) | Dhansiri (South) | 56.7 km | river name matches one over the circle |

<details><summary>2 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Garampani (`056-MBDNEW`) | Dhansiri (South) | 20.7 km | river name matches one over the circle |
| Ririgaon (`040-MBDNEW`) | Dhansiri (South) | 62.3 km | river name matches one over the circle |

</details>

**Question:** does the Dhansiri (South) reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Mahmora — Charaideo

**Reads now:** Sivasagar (`018-ubddib`) on the **Dikhow**, 39.1 km away.
Recorded reason for that mapping: *Dikhow at Sivasagar*.

**Rivers running through this circle**, longest first:

- Disang River (58.4 km)
- Diroi Nadi (37.9 km)
- Safrai Nadi (0.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Desangpani (`015-UBDDIB`) | Desang | 7.8 km |  |
| Nanglamoraghat (`016-UBDDIB`) | Desang | 21.8 km |  |
| Chenimari (Khowang) (`013-UBDDIB`) | Buridehing | 23.4 km |  |
| Bihubar (`017-UBDDIB`) | Dikhow | 32.0 km |  |
| Sivasagar (`018-ubddib`) | Dikhow | 39.1 km | **reads this now** |
| Dillighat (`014-UBDDIB`) | Desang | 42.0 km |  |
| Dibrugarh (`010-UBDDIB`) | Brahmaputra | 42.3 km |  |
| Naharkatia (`012-ubddib`) | Buridehing | 43.2 km |  |

<details><summary>7 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Machaigaon (`038-MBDNEW`) | - | 17.6 km |  |
| Dihingmukh (`057-UBDDIB`) | Buridehing | 26.2 km |  |
| Bogibil (`055-UBDDIB`) | Brahmaputra | 35.7 km |  |
| BALIJAGAON (`060-UBDDIB`) | Buridehing | 36.1 km |  |
| B G Road (`039-MBDNEW`) | Brahmaputra | 41.4 km |  |
| Teok (`057-MBDNEW`) | - | 61.0 km |  |
| GUTANG (`062-UBDDIB`) | Dibru | 66.2 km |  |

</details>

**Question:** does the Dikhow reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Ramkrishna Nagar — Sribhumi

**Reads now:** Karimganj (`021-MBDGHY`) on the **Kushiyara**, 35.3 km away.
Recorded reason for that mapping: *Kushiyara at Karimganj*.

**Rivers running through this circle**, longest first:

- Singla (39.2 km)
- Singla Nadi (37.6 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| ANIPUR (`008-MDSIL`) | Singla | 2.8 km | river name matches one over the circle |
| Matijuri (`01-11-01-002`) | Katakhal | 20.0 km |  |
| Matijuri (`015-MBDGHY`) | Katakhal | 20.0 km |  |
| Gharmura (`012-MBDGHY`) | Dhaleswari | 32.7 km |  |
| Katigorah (`015-MDSIL`) | Katakhal | 35.2 km |  |
| Karimganj (`021-MBDGHY`) | Kushiyara | 35.3 km | **reads this now** |
| Badarpur Ghat (`01-11-01-006`) | Barak | 37.2 km |  |
| Badarpurghat (`011-MBDGHY`) | Barak | 37.2 km |  |
| Dholai (`01-11-06-003`) | Rukni | 41.9 km |  |
| Dholai (`016-MBDGHY`) | Rukni | 41.9 km |  |

<details><summary>14 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Patharkandi (`019-MDSIL`) | Longai | 12.0 km |  |
| Lala (`018-MDSIL`) | Katakhal | 18.9 km |  |
| Muhammedpur (`017-MDSIL`) | Katakhal | 19.0 km |  |
| Kaliganj (`021-MDSIL`) | Longai | 23.9 km |  |
| Fakirabazar (`01-11-03-001`) | Longai | 35.5 km |  |
| Kulichera (`005neid1`) | Rukni | 38.7 km |  |
| NEAIRGRAM (`028- MDSIL`) | Barak | 46.3 km |  |
| KALAIN (`027- MDSIL`) | Barak | 46.7 km |  |
| Jalalpur (`01-10-24-001`) | - | 48.3 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 51.1 km |  |

</details>

**Question:** does the Kushiyara reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Patharkandi — Sribhumi

**Reads now:** Karimganj (`021-MBDGHY`) on the **Kushiyara**, 34.9 km away.
Recorded reason for that mapping: *Kushiyara at Karimganj*.

**Rivers running through this circle**, longest first:

- Longai River (68.5 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| ANIPUR (`008-MDSIL`) | Singla | 12.7 km |  |
| Matijuri (`01-11-01-002`) | Katakhal | 31.6 km |  |
| Matijuri (`015-MBDGHY`) | Katakhal | 31.6 km |  |
| Karimganj (`021-MBDGHY`) | Kushiyara | 34.9 km | **reads this now** |
| Gharmura (`012-MBDGHY`) | Dhaleswari | 37.7 km |  |
| Badarpur Ghat (`01-11-01-006`) | Barak | 43.7 km |  |
| Badarpurghat (`011-MBDGHY`) | Barak | 43.7 km |  |
| Katigorah (`015-MDSIL`) | Katakhal | 44.1 km |  |
| Gumrabazar (`01-11-13-001`) | - | 50.2 km |  |
| Dholai (`01-11-06-003`) | Rukni | 54.2 km |  |

<details><summary>12 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Patharkandi (`019-MDSIL`) | Longai | 1.3 km | river name matches one over the circle |
| Kaliganj (`021-MDSIL`) | Longai | 26.1 km | river name matches one over the circle |
| Muhammedpur (`017-MDSIL`) | Katakhal | 31.0 km |  |
| Lala (`018-MDSIL`) | Katakhal | 31.0 km |  |
| Fakirabazar (`01-11-03-001`) | Longai | 32.7 km | river name matches one over the circle |
| Jalalpur (`01-10-24-001`) | - | 50.6 km |  |
| Kulichera (`005neid1`) | Rukni | 50.8 km |  |
| KALAIN (`027- MDSIL`) | Barak | 51.5 km |  |
| NEAIRGRAM (`028- MDSIL`) | Barak | 57.5 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 59.8 km |  |

</details>

**Question:** does the Kushiyara reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Katlichara — Hailakandi

**Reads now:** Matijuri (`01-11-01-002`) on the **Katakhal**, 33.7 km away.
Recorded reason for that mapping: *Katakhal at Matijuri*.

**Rivers running through this circle**, longest first:

- Tlawng (66.9 km)
- Dhal Chhara (23.1 km)
- Kukichara (19.6 km)
- Teirei (5.8 km)
- Dalai River (3.1 km)
- Thinglian Lui (2.7 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Gharmura (`012-MBDGHY`) | Dhaleswari | 7.9 km |  |
| ANIPUR (`008-MDSIL`) | Singla | 23.2 km |  |
| Matijuri (`01-11-01-002`) | Katakhal | 33.7 km | **reads this now** |
| Matijuri (`015-MBDGHY`) | Katakhal | 33.7 km |  |
| Dholai (`01-11-06-003`) | Rukni | 41.4 km |  |
| Dholai (`016-MBDGHY`) | Rukni | 41.4 km |  |
| Monierkhal (`009-mdsil`) | Sonai | 50.0 km |  |
| Amraghat (`017-MBDghy`) | Sonai | 51.1 km |  |
| Katigorah (`015-MDSIL`) | Katakhal | 52.7 km |  |
| TULARGRAM (`007-MDSIL`) | Sonai | 53.8 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Muhammedpur (`017-MDSIL`) | Katakhal | 19.6 km |  |
| Lala (`018-MDSIL`) | Katakhal | 29.3 km |  |
| Kulichera (`005neid1`) | Rukni | 31.5 km |  |
| Patharkandi (`019-MDSIL`) | Longai | 33.2 km |  |
| Kashithal (`004neid1`) | Sonai | 47.6 km |  |
| Kaliganj (`021-MDSIL`) | Longai | 49.1 km |  |
| NEAIRGRAM (`028- MDSIL`) | Barak | 54.9 km |  |
| SIBAPUR (`026- MDSIL`) | Barak | 61.1 km |  |
| Fakirabazar (`01-11-03-001`) | Longai | 61.3 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 67.2 km |  |

</details>

**Question:** does the Katakhal reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Chenga — Barpeta

**Reads now:** Beki Road bridge (`002-LBDJPG`) on the **Beki**, 33.2 km away.
Recorded reason for that mapping: *Beki at Beki Road Bridge*.

**Rivers running through this circle**, longest first:

- Brahmaputra (28.7 km)
- Pagladia (5.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Beki Road bridge (`002-LBDJPG`) | Beki | 33.2 km | **reads this now** |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 39.5 km |  |
| KULSI (`BY00045`) | Kulsi | 40.7 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 43.7 km |  |
| DUDHNAI (`bv000f5`) | Dudhnai | 45.6 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 46.9 km |  |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 49.7 km | river name matches one over the circle |
| AIE NH XING (`033-LBDJPG`) | Aie | 53.8 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 53.9 km |  |
| Pandu (`025-MBDGHY`) | Brahmaputra | 55.1 km | river name matches one over the circle |

<details><summary>13 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 4.8 km | river name matches one over the circle |
| Malibari (`047-MBDNEW`) | Kulsi | 20.4 km |  |
| Sholmari (`042-MBDNEW`) | - | 22.2 km |  |
| Pohumara (`071-MBDNEW`) | - | 24.7 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 29.4 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 34.6 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 37.6 km |  |
| Ramdia (`041-MBDNEW`) | - | 39.0 km |  |
| Satpokholi (`051-MBDNEW`) | - | 39.7 km |  |
| Dudhnoi (`BV000FS`) | Dudhnai | 45.6 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Tengakhat — Dibrugarh

**Reads now:** Chenimari (Khowang) (`013-UBDDIB`) on the **Buridehing**, 31.6 km away.
Recorded reason for that mapping: *Buridehing at Chenimari Khowang*.

**Rivers running through this circle**, longest first:

- Burhi Dihing (42.4 km)
- Tingrāl Nadi (21.6 km)
- Tipling Nadi (7.7 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Naharkatia (`012-ubddib`) | Buridehing | 16.5 km |  |
| Dibrugarh (`010-UBDDIB`) | Brahmaputra | 30.6 km |  |
| Chenimari (Khowang) (`013-UBDDIB`) | Buridehing | 31.6 km | **reads this now** |
| Dillighat (`014-UBDDIB`) | Desang | 31.6 km |  |
| Desangpani (`015-UBDDIB`) | Desang | 46.0 km |  |
| Margherita (`011-UBDDIB`) | Buridehing | 47.5 km |  |
| Dholabazar (`007-UBDDIB`) | Lohit | 56.6 km |  |
| Nanglamoraghat (`016-UBDDIB`) | Desang | 59.9 km |  |
| Bihubar (`017-UBDDIB`) | Dikhow | 70.0 km |  |

<details><summary>9 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| BALIJAGAON (`060-UBDDIB`) | Buridehing | 2.6 km |  |
| GUTANG (`062-UBDDIB`) | Dibru | 27.8 km |  |
| Doomdooma (`045-ubddib`) | Dibru | 41.1 km |  |
| Bogibil (`055-UBDDIB`) | Brahmaputra | 41.2 km |  |
| MURKONGSELEK (`068-UBDDIB`) | Siang | 45.8 km |  |
| Dihingmukh (`057-UBDDIB`) | Buridehing | 46.8 km |  |
| Machaigaon (`038-MBDNEW`) | - | 53.5 km |  |
| Udaipur (`049`) | Tirap | 65.1 km |  |
| JAGUNGHAT (`061-UBDDIB`) | Buridehing | 68.5 km |  |

</details>

**Question:** does the Buridehing reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Palasbari — Kamrup

**Reads now:** Guwahati(D.C.Court) (`001-MBDGHY`) on the **Brahmaputra**, 29.5 km away.
Recorded reason for that mapping: *Brahmaputra at Guwahati downstream*.

**Rivers running through this circle**, longest first:

- Kulsi (28.1 km)
- Brahmaputra (10.9 km)
- Gargara (9.2 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| KULSI (`BY00045`) | Kulsi | 13.5 km | river name matches one over the circle |
| Pandu (`025-MBDGHY`) | Brahmaputra | 22.3 km | river name matches one over the circle |
| Guwahati(D.C.Court) (`001-MBDGHY`) | Brahmaputra | 29.5 km | **reads this now**, river name matches one over the circle |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 38.3 km |  |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 44.3 km |  |
| SONAPUR (`BKA00D7`) | Digaru | 49.0 km |  |

<details><summary>12 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Satpokholi (`051-MBDNEW`) | - | 3.7 km |  |
| Ramdia (`041-MBDNEW`) | - | 23.7 km |  |
| Changsari (`050-MBDNEW`) | - | 28.0 km |  |
| Sholmari (`042-MBDNEW`) | - | 32.8 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 38.8 km | river name matches one over the circle |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 42.0 km | river name matches one over the circle |
| Nona (`043-MBDNEW`) | - | 44.0 km |  |
| Kamarpur (`045-MBDNEW`) | Kopili | 55.3 km |  |
| Patacharkuchi (`049-MBDNEW`) | - | 56.4 km |  |
| Diprang Gaon (`036-MBDNEW`) | Kopili | 60.8 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Bajali (Pt) — Bajali

**Reads now:** Beki Road bridge (`002-LBDJPG`) on the **Beki**, 29.4 km away.
Recorded reason for that mapping: *Beki at Beki Road Bridge*.

**Rivers running through this circle**, longest first:

- Kaldiya Nadi (28.8 km)
- Bhelengi River (10.2 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Pagladiya N T Road Crossing (`004-MBDGHY`) | Pagladiya | 25.1 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 29.4 km | **reads this now** |
| PANBARI (`003-LBDJPG`) | Burisuti | 39.5 km |  |
| Mathanguri (`001-LBDJPG`) | Beki | 40.6 km |  |
| Matunga (`003-MBDGHY`) | Kalanadi | 45.6 km |  |
| Puthimari NH Rd Xing (`006-MBDGHY`) | Puthimari | 46.2 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 46.3 km |  |
| Suklai (`007-MBDGHY`) | Suklai | 52.7 km |  |
| AIE NH XING (`033-LBDJPG`) | Aie | 55.7 km |  |
| DRF (`005-MBDGHY`) | Puthimari | 56.7 km |  |

<details><summary>11 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Patacharkuchi (`049-MBDNEW`) | - | 2.4 km |  |
| Pohumara (`071-MBDNEW`) | - | 10.1 km |  |
| Sholmari (`042-MBDNEW`) | - | 24.1 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 32.7 km |  |
| Nona (`043-MBDNEW`) | - | 35.0 km |  |
| Ramdia (`041-MBDNEW`) | - | 39.8 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 42.4 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 48.1 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 50.8 km |  |
| Changsari (`050-MBDNEW`) | - | 52.1 km |  |

</details>

**Question:** does the Beki reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Dudhnai — Goalpara

**Reads now:** Goalpara (`002-MBDGHY`) on the **Brahmaputra**, 28.9 km away.
Recorded reason for that mapping: *Brahmaputra at Goalpara*.

**Rivers running through this circle**, longest first:

- Dudhnoi (13.8 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| DUDHNAI (`bv000f5`) | Dudhnai | 2.3 km |  |
| Goalpara (`002-MBDGHY`) | Brahmaputra | 28.9 km | **reads this now** |
| PANCHARATNA (`BB000D6`) | Brahmaputra | 36.3 km |  |
| BAHALPUR (`034-LBDJPG`) | Champamati | 51.0 km |  |
| Manas N H Crossing (`004-LBDJPG`) | Manas | 54.1 km |  |
| KULSI (`BY00045`) | Kulsi | 57.2 km |  |
| Beki Road bridge (`002-LBDJPG`) | Beki | 58.1 km |  |
| AIE NH XING (`033-LBDJPG`) | Aie | 59.5 km |  |
| PANBARI (`003-LBDJPG`) | Burisuti | 67.6 km |  |

<details><summary>9 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Dudhnoi (`BV000FS`) | Dudhnai | 2.3 km |  |
| Krishnai (`058-MBDNEW`) | Krishnai | 15.3 km |  |
| Malibari (`047-MBDNEW`) | Kulsi | 31.1 km |  |
| Khudrakhowa (`066-MBDNEW`) | Manas | 36.8 km |  |
| Tarabari (`067-MBDNEW`) | Brahmaputra | 40.1 km |  |
| Chaklagaon (`065-MBDNEW`) | Manas | 45.0 km |  |
| Pohumara (`071-MBDNEW`) | - | 63.3 km |  |
| Sholmari (`042-MBDNEW`) | - | 64.3 km |  |
| Satpokholi (`051-MBDNEW`) | - | 65.3 km |  |

</details>

**Question:** does the Brahmaputra reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Sonai — Cachar

**Reads now:** Annapurna Ghat (`01-11-01-007`) on the **Barak**, 28.6 km away.
Recorded reason for that mapping: *Barak at Annapurna Ghat*.

**Rivers running through this circle**, longest first:

- Sonāi River (59.3 km)
- Barak River (56.6 km)
- Serlui (47.8 km)
- Dalai River (22.7 km)
- Sonai River (16.4 km)
- Gowāli Khāl (12.8 km)
- Barāk River (9.2 km)
- Nāla Chhara (8.1 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Dholai (`01-11-06-003`) | Rukni | 2.0 km |  |
| Dholai (`016-MBDGHY`) | Rukni | 2.0 km |  |
| Monierkhal (`009-mdsil`) | Sonai | 9.6 km | river name matches one over the circle |
| Amraghat (`017-MBDghy`) | Sonai | 9.7 km | river name matches one over the circle |
| TULARGRAM (`007-MDSIL`) | Sonai | 15.0 km | river name matches one over the circle |
| Matijuri (`01-11-01-002`) | Katakhal | 26.6 km |  |
| Matijuri (`015-MBDGHY`) | Katakhal | 26.6 km |  |
| Lakhipur (`009-MBDGHY`) | Barak | 27.3 km | river name matches one over the circle |
| Fulertal (`01-11-01-008`) | Barak | 27.4 km | river name matches one over the circle |
| Annapurna Ghat (`01-11-01-007`) | Barak | 28.6 km | **reads this now**, river name matches one over the circle |

<details><summary>15 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Kashithal (`004neid1`) | Sonai | 10.3 km | river name matches one over the circle |
| Kulichera (`005neid1`) | Rukni | 11.8 km |  |
| NEAIRGRAM (`028- MDSIL`) | Barak | 20.1 km | river name matches one over the circle |
| SIBAPUR (`026- MDSIL`) | Barak | 22.9 km | river name matches one over the circle |
| Lala (`018-MDSIL`) | Katakhal | 25.2 km |  |
| Muhammedpur (`017-MDSIL`) | Katakhal | 26.4 km |  |
| CHIRIPOOL (`024- MDSIL`) | Barak | 29.4 km | river name matches one over the circle |
| UDHARBOND (`025 - MDSIL`) | Barak | 35.7 km | river name matches one over the circle |
| Borkhola (`016-MDSIL`) | Jatinga | 39.5 km |  |
| Kaliganj (`021-MDSIL`) | Longai | 50.6 km |  |

</details>

**Question:** does the Barak reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

### Katigora — Cachar

**Reads now:** Annapurna Ghat (`01-11-01-007`) on the **Barak**, 27.1 km away.
Recorded reason for that mapping: *Barak at Annapurna Ghat*.

**Rivers running through this circle**, longest first:

- Larang Nadi (46.0 km)
- Barāk River (36.3 km)
- Arang Chara (35.3 km)
- Gumra Nadi (25.7 km)
- সুরমা নদী (19.0 km)
- Bali Chara Nadi (16.2 km)
- Kayāng Nadi (15.7 km)
- Jātinga Nadi (7.3 km)

**Gauges within 70 km that are reporting:**

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| Gumrabazar (`01-11-13-001`) | - | 4.8 km |  |
| Badarpur Ghat (`01-11-01-006`) | Barak | 9.6 km |  |
| Badarpurghat (`011-MBDGHY`) | Barak | 9.6 km |  |
| Katigorah (`015-MDSIL`) | Katakhal | 18.3 km |  |
| Karimganj (`021-MBDGHY`) | Kushiyara | 22.6 km |  |
| Annapurna Ghat (`01-11-01-007`) | Barak | 27.1 km | **reads this now** |
| Annapurnaghat (`010-MBDGHY`) | Barak | 27.1 km |  |
| Matijuri (`01-11-01-002`) | Katakhal | 34.9 km |  |
| Matijuri (`015-MBDGHY`) | Katakhal | 34.9 km |  |
| TULARGRAM (`007-MDSIL`) | Sonai | 42.4 km |  |

<details><summary>16 more nearby, but not reporting</summary>

| Gauge | River | Distance | Notes |
| --- | --- | --- | --- |
| KALAIN (`027- MDSIL`) | Barak | 1.5 km |  |
| Jalalpur (`01-10-24-001`) | - | 11.6 km |  |
| Borkhola (`016-MDSIL`) | Jatinga | 19.7 km | river name matches one over the circle |
| Kaliganj (`021-MDSIL`) | Longai | 24.9 km |  |
| Fakirabazar (`01-11-03-001`) | Longai | 29.6 km |  |
| Harangajao (`030-MBDGHY`) | Jatinga | 34.3 km | river name matches one over the circle |
| UDHARBOND (`025 - MDSIL`) | Barak | 35.4 km |  |
| NEAIRGRAM (`028- MDSIL`) | Barak | 35.4 km |  |
| Lala (`018-MDSIL`) | Katakhal | 39.5 km |  |
| SIBAPUR (`026- MDSIL`) | Barak | 39.9 km |  |

</details>

**Question:** does the Barak reach this circle's water? Keep it, name a better gauge, or say no gauge fits.

---

# Part 2 — does a rise upstream reach here?

A different question, same kind of knowledge. If a gauge upstream rises
and that water reliably arrives downstream some hours later, the site can
warn people before their own river moves.

We measured the timing against seven monsoons of readings. What the
measurement **cannot** tell us is whether the two gauges are really on the
same stretch of water, or whether something between them — a tributary
joining, a barrage, a big bend — breaks the link. That is the question.

⚠️ Matching timing is not proof. Two gauges can rise together because the
same rain fell on both, with no water travelling between them at all.
That is exactly the mistake this review exists to catch.

**7 pairs to check.**

### Goalpara → Dhubri

**Upstream:** Goalpara on the Brahmaputra, Goalpara, Assam.
**Downstream:** Dhubri on the Brahmaputra, Dhubri, Assam.

**What the readings show:** a rise upstream has usually shown up downstream about **13 hours** later. Across 6 monsoons that gap ran from 7 to 16 hours.
**Who this would help:** Bagribari (Pt), Bilasipara (Pt), Chapar (Pt), Dhubri (Pt), Gossaigaon (Pt), Mankachar, and 1 more — these read the downstream gauge.

**Question:** is the water at Goalpara the same water that reaches Dhubri? Anything major in between?

### Tezpur → Guwahati(D.C.Court)

**Upstream:** Tezpur on the Brahmaputra, Sonitpur, Assam.
**Downstream:** Guwahati(D.C.Court) on the Brahmaputra, Kamrup, Assam.

**What the readings show:** a rise upstream has usually shown up downstream about **24 hours** later. Across 5 monsoons that gap ran from 22 to 28 hours.
**Who this would help:** Azara, Boko, Chamaria, Chandrapur, Chhaygaon, Dispur, and 11 more — these read the downstream gauge.

**Question:** is the water at Tezpur the same water that reaches Guwahati(D.C.Court)? Anything major in between?

### Guwahati(D.C.Court) → Goalpara

**Upstream:** Guwahati(D.C.Court) on the Brahmaputra, Kamrup, Assam.
**Downstream:** Goalpara on the Brahmaputra, Goalpara, Assam.

**What the readings show:** a rise upstream has usually shown up downstream about **24 hours** later. Across 6 monsoons that gap ran from 14 to 30 hours.
**Who this would help:** Balijana, Dudhnai, Lakhipur, Matia, Rangjuli — these read the downstream gauge.

**Question:** is the water at Guwahati(D.C.Court) the same water that reaches Goalpara? Anything major in between?

### Neamatighat → Tezpur

**Upstream:** Neamatighat on the Brahmaputra, Jorhat, Assam.
**Downstream:** Tezpur on the Brahmaputra, Sonitpur, Assam.

**What the readings show:** a rise upstream has usually shown up downstream about **26 hours** later. Across 6 monsoons that gap ran from 22 to 30 hours.
**Who this would help:** Biswanath, Dhekiajuli (Pt), Gohpur, Helem, Na-Duar, Tezpur — these read the downstream gauge.

**Question:** is the water at Neamatighat the same water that reaches Tezpur? Anything major in between?

### Dibrugarh → Neamatighat

**Upstream:** Dibrugarh on the Brahmaputra, Dibrugarh, Assam.
**Downstream:** Neamatighat on the Brahmaputra, Jorhat, Assam.

**What the readings show:** a rise upstream has usually shown up downstream about **21 hours** later. Across 7 monsoons that gap ran from 18 to 23 hours.
**Who this would help:** Jorhat East, Jorhat West, Majuli, Mariani, Teok, Titabor — these read the downstream gauge.

**Question:** is the water at Dibrugarh the same water that reaches Neamatighat? Anything major in between?

### Yingkiong → Passighat

**Upstream:** Yingkiong on the Siang, Upper Siang, Arunachal Pradesh.
**Downstream:** Passighat on the Siang, East Siang, Arunachal Pradesh.

**What the readings show:** a rise upstream has usually shown up downstream about **5 hours** later. Across 7 monsoons that gap ran from 4 to 7 hours.
**Who this would help:** no revenue circle currently reads the downstream gauge, so this pair adds lead time only if a circle is reassigned to it in Part 1.

**Question:** is the water at Yingkiong the same water that reaches Passighat? Anything major in between?

### Passighat → Dibrugarh

**Upstream:** Passighat on the Siang, East Siang, Arunachal Pradesh.
**Downstream:** Dibrugarh on the Brahmaputra, Dibrugarh, Assam.

**What the readings show:** a rise upstream has usually shown up downstream about **14 hours** later. Across 7 monsoons that gap ran from 12 to 15 hours.
**Who this would help:** Chabua, Dibrugarh East, Dibrugarh West — these read the downstream gauge.

**Question:** is the water at Passighat the same water that reaches Dibrugarh? Anything major in between?

## Not asking about these

The timing here was too weak or too unstable to be worth your time.
Listed so nobody wonders later why they are missing.

- **Namsai → Dibrugarh** (Nao Dehing): the gap ranged from 0 to 21 hours between years, which is too loose to build a sentence on.
