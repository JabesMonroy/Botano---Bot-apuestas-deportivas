# Best Football Leagues Worldwide by FREE Data Availability — Expansion Module for the Betting-Analysis Bot

## TL;DR
- **The data-richest free leagues are the four remaining big-5 European leagues (Spain La Liga, Italy Serie A, Germany Bundesliga, France Ligue 1) — they join the EPL in Tier S**, because they are the ONLY leagues on earth with free shot-level xG from Understat (2014/15→present), plus football-data.co.uk odds+match-stats CSVs back to the 1990s, full Sofascore granularity, and football-data.org free-tier fixtures.
- **The single biggest "hidden gem" for your stack is the Russian Premier League (RFPL): it is the ONLY non-big-5 league Understat covers**, giving it free xG that no other second-tier league has. Runner-up gems: StatsBomb's free event data for **Copa América 2024** (32 matches, directly LatAm-relevant) and **AFCON 2023** (52 matches), the **Indian Super League 2020/21** (115 matches of full free StatsBomb events), and the **A-League** (free SkillCorner broadcast tracking for 10 matches of 2024/25).
- **For betting edge, target leagues that combine decent free data with soft markets**: Argentina Liga Profesional, Liga MX, the Scandinavian leagues (Allsvenskan, Eliteserien), and second divisions. Big-5 markets are efficient; your edge there is model quality, not market softness.

## Key Findings

1. **Free xG is the binding constraint.** With FBref's xG feed gone (StatsPerform termination, Jan 2026), only three free xG sources remain: **Understat** (6 leagues only), **Sofascore** (broad, its own model, must be scraped), and **StatsBomb Open Data** (fixed tournament list). Any league ranking for a betting bot is really a ranking of "how do I get xG and granular stats here."
2. **Understat's coverage is exactly six leagues and will not expand.** Confirmed verbatim by the worldfootballR docs — *"The leagues currently available for Understat are: 'EPL', 'La liga', 'Bundesliga', 'Serie A', 'Ligue 1', 'RFPL'"* — and by understat.com's homepage. Data begins 2014/15.
3. **football-data.org's free tier is exactly 12 competitions** (10 requests/minute): Champions League, Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga, Championship, Brazilian Série A, FIFA World Cup, European Championship. Everything else — and all match-stats/odds add-ons — is paid.
4. **football-data.co.uk is your backtesting backbone for far more leagues than people realize** — 22+ leagues with closing odds, Over/Under 2.5 and Asian-handicap prices, and (for the 11 "main" European leagues) full match stats (shots, shots on target, corners, fouls, cards) back ~25 years to 1993/94.
5. **API-Football (your backbone) lists exactly 1,236 leagues/cups on the free tier** (100 requests/day, reset 00:00 UTC), but data DEPTH is uneven: top leagues have full stats/lineups/events; smaller leagues frequently lack lineups or detailed stats, and historical seasons are gated on the free plan.
6. **Sofascore is the great equalizer**: it computes its own xG for 500+ competitions worldwide. ScraperFC's curated `comps.yaml` supports a growing subset; for anything outside it you query Sofascore's JSON API directly by tournament ID.

## Details

### The six free data sources — verified coverage

| Source | What it gives | Free? / limits | Verified coverage |
|---|---|---|---|
| **API-Football** (api-sports.io) | Fixtures, results, standings, events, lineups, players, team/match statistics, odds | Free tier **100 req/day** (reset 00:00 UTC), all endpoints; historical seasons limited | **1,236 leagues/cups**; depth uneven — big-5 full, smaller leagues often missing lineups/stats |
| **football-data.org** | Fixtures, results, standings, scorers | Free = **12 competitions**, 10 req/min | CL, PL, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga, Championship, Brazil Série A, World Cup, Euro |
| **Understat** (scrape via ScraperFC/worldfootballR/soccerdata) | Shot-level xG, xA, npxG, xGChain, xGBuildup, match win-probabilities | Free scrape | EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL **only**; 2014/15→present |
| **Sofascore** (scrape via ScraperFC/soccerdata) | Its own xG, shots, heatmaps, match momentum, player/team match & season stats | Free scrape (anti-bot; browser mode) | 500+ competitions; ScraperFC curated list expanding |
| **StatsBomb Open Data** (GitHub) | Full event data + 360 freeze-frames for select comps | Free, register + credit | See tournament list below |
| **football-data.co.uk** | Historical results + closing odds (1X2, O/U 2.5, Asian handicap) + match stats | Free CSV | 22+ leagues (see below) |

**Where to get each:**
- API-Football: `https://www.api-football.com/` · docs `https://api-sports.io/documentation/football/v3` · coverage `https://www.api-football.com/coverage`
- football-data.org: `https://www.football-data.org/` · coverage `https://www.football-data.org/coverage`
- Understat: `https://understat.com/` · scrape via `soccerdata` (`github.com/probberechts/soccerdata`) or `ScraperFC` (`github.com/oseymour/ScraperFC`) or R `worldfootballR`
- Sofascore: via `ScraperFC` / `soccerdata`; raw JSON at `https://www.sofascore.com/api/v1/…`
- StatsBomb: `https://github.com/statsbomb/open-data` · Python `statsbombpy` · R `StatsBombR`
- football-data.co.uk: `https://www.football-data.co.uk/data.php` (main European) and `https://www.football-data.co.uk/all_new_data.php` (worldwide/extra); GitHub mirror `github.com/footballcsv/cache.footballdata`; auto-updated packages at `datahub.io/football`

### StatsBomb Open Data — the exact free competition list (with match counts)
Confirmed against StatsBomb's public listing (events; some with 360 tracking). This is your xG-model **training** data (you already use it), not per-round modeling data — coverage is historical/tournament, not current league rounds.

- **Men's international**: FIFA World Cup 2022 (64 matches, events+360) & 2018 (64); UEFA EURO 2024 (51, events+360) & 2020 (51); **CONMEBOL Copa América 2024 (32 matches; competition_id = 223)**; **CAF AFCON 2023 (52 matches)**.
- **Women's international**: FIFA Women's World Cup 2023 (64, events+360) & 2019 (52); UEFA Women's EURO 2025 (31, events+360) & 2022 (31).
- **Club**: UEFA Champions League finals (15 matches); **Lionel Messi's full club career — over 550 matches with events** (all 17 La Liga seasons 2004/05–2020/21, PSG 2021/22–2022/23, and Inter Miami 2023 MLS); StatsBomb Icons Maradona (13) & Cruyff (11); FA Women's Super League seasons; **Indian Super League 2020/21 (115 matches)**; and specific European club seasons: **Spanish La Liga 2015/16 (380), German 1. Bundesliga 2015/16 (306), Italian Serie A 2015/16 (380), EPL 2015/16 (380), Arsenal's "Invincibles" EPL 2003/04 (38), Bayer Leverkusen's Bundesliga 2023/24 (34, events+360)**.
- Access: `github.com/statsbomb/open-data`.

### football-data.co.uk — exact league list & what you get
- **11 "main" European leagues** (season-by-season files, WITH match stats — shots, SOT, corners, fouls, cards — plus 1X2 / O/U 2.5 / Asian-handicap odds and closing lines): England (E0 Premier, E1 Championship, E2 League One, E3 League Two, EC National League), Scotland (SC0–SC3), Germany (D1 Bundesliga, D2 2.Bundesliga), Italy (I1 Serie A, I2 Serie B), Spain (SP1 La Liga, SP2 Segunda), France (F1 Ligue 1, F2 Ligue 2), Netherlands (N1), Belgium (B1), Portugal (P1), Turkey (T1), Greece (G1).
- **16 "extra" worldwide leagues** (all-seasons-in-one file, results + odds, generally NO detailed match stats): Argentina, Austria, Brazil, China, Denmark, Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland, USA (MLS).
- The stat columns available (main leagues): HS/AS (shots), HST/AST (shots on target), HC/AC (corners), HF/AF (fouls), HY/AY (yellows), HR/AR (reds), plus half-time scores and referee. Depth: top leagues back to 1993/94; updated twice weekly.

### Free community datasets (Kaggle / GitHub)
- **openfootball** (`github.com/openfootball`): public-domain results/fixtures JSON+TXT for Europe and **South America incl. Brazil, Argentina, Colombia** — no API key. Results only (no odds/stats), but excellent for schedule scaffolding.
- **Understat mirrors on Kaggle** (`mexwell/understat-database`, `codytipton/understat-data`, 2014/15→2024/25) for bulk xG without scraping.
- **Saudi Pro League** datasets (Kaggle `saudidata2030/spl-stats-last-4-years`; GitHub `alioh/Saudi-Professional-League-Datasets`).
- **"Complete football data — 96k matches, 18 leagues"** Kaggle bundle (`bastekforever/…`) for quick multi-league backtests.

---

## MASTER RANKING / TIER LIST

Ranked by overall FREE data richness for betting modeling (xG availability weighted heavily). ★ = already in your existing report.

| Tier | League | Free xG | Granular stats (free) | Historical odds (fd.co.uk) | fd.org free | Standout free source |
|---|---|---|---|---|---|---|
| **S** | EPL ★ | Understat + Sofascore | Yes (fd.co.uk + Sofascore + API-F) | Yes, since 1993, +Asian | Yes | Understat |
| **S** | Spain La Liga | Understat + Sofascore | Yes | Yes (SP1) | Yes | Understat + StatsBomb (Messi era) |
| **S** | Italy Serie A | Understat + Sofascore | Yes | Yes (I1) | Yes | Understat |
| **S** | Germany Bundesliga | Understat + Sofascore | Yes | Yes (D1) | Yes | Understat |
| **S** | France Ligue 1 | Understat + Sofascore | Yes | Yes (F1) | Yes | Understat |
| **A** | Russia Premier League (RFPL) | **Understat** + Sofascore | Sofascore | Yes (RUS, extra) | No | **Understat (only non-big-5!)** |
| **A** | England Championship | Sofascore (ScraperFC) | Yes (fd.co.uk E1 full stats) | Yes, +Asian | Yes | fd.org free + fd.co.uk |
| **A** | Netherlands Eredivisie | Sofascore (ScraperFC) | fd.co.uk N1 + Sofascore | Yes (N1) | Yes | football-data.org free |
| **A** | Portugal Primeira Liga | Sofascore (ScraperFC) | fd.co.uk P1 + Sofascore | Yes (P1) | Yes | football-data.org free |
| **A** | Brazil Série A ★ | Sofascore | Sofascore + API-F | Yes (extra) | Yes | fd.org free + Copa Libertadores context |
| **B** | Argentina Liga Profesional | Sofascore (own model) | Sofascore | Yes (ARG, extra) | No | fd.co.uk odds + Copa América StatsBomb |
| **B** | Mexico Liga MX | Sofascore (ScraperFC Apertura/Clausura) | Sofascore | Yes (MEX, extra) | No | ScraperFC Sofascore module |
| **B** | Belgium Pro League | Sofascore | fd.co.uk B1 | Yes (B1) | No | fd.co.uk |
| **B** | Turkey Süper Lig | Sofascore | fd.co.uk T1 | Yes (T1) | No | fd.co.uk |
| **B** | Scotland Premiership | Sofascore | fd.co.uk SC0 (full stats) | Yes, +Asian | No | fd.co.uk full stats |
| **B** | Sweden Allsvenskan | Sofascore | Sofascore | Yes (SWE, extra) | No | fd.co.uk odds + soft summer market |
| **B** | Norway Eliteserien | Sofascore | Sofascore | Yes (NOR, extra) | No | fd.co.uk odds + soft summer market |
| **B** | Denmark Superliga | Sofascore | Sofascore | Yes (DNK, extra) | No | fd.co.uk odds |
| **B** | Greece Super League | Sofascore | fd.co.uk G1 | Yes (G1) | No | fd.co.uk |
| **B** | Austria Bundesliga | Sofascore | Sofascore | Yes (AUT, extra) | No | fd.co.uk odds |
| **B** | Switzerland Super League | Sofascore | Sofascore | Yes (SWZ, extra) | No | fd.co.uk odds |
| **B** | Poland Ekstraklasa | Sofascore | Sofascore | Yes (POL, extra) | No | fd.co.uk odds |
| **B** | USA MLS ★ | Sofascore | Sofascore + API-F | Yes (USA, extra) | No | fd.co.uk odds; soft market |
| **C** | Japan J1 League | Sofascore | Sofascore + API-F | Yes (JPN, extra) | No | fd.co.uk odds |
| **C** | China Super League | Sofascore | API-F | Yes (CHN, extra) | No | fd.co.uk odds |
| **C** | Romania Liga 1 | Sofascore | API-F | Yes (ROU, extra) | No | fd.co.uk odds |
| **C** | Ireland Premier Div | Sofascore | API-F | Yes (IRL, extra) | No | fd.co.uk odds |
| **C** | Finland Veikkausliiga | Sofascore | API-F | Yes (FIN, extra) | No | fd.co.uk odds |
| **C** | Saudi Pro League | Sofascore | API-F | No | No | Kaggle datasets + API-F |
| **C** | South Korea K League | Sofascore | API-F | No | No | Sofascore + API-F |
| **C** | Australia A-League | Sofascore | API-F | No | No | **SkillCorner open tracking (10 matches, 2024/25)** |
| **C** | Colombia Liga BetPlay ★ | Sofascore | API-F | No | No | Sofascore API + openfootball |
| **C** | Chile / Uruguay / Ecuador / Peru / Paraguay | Sofascore | API-F (thin) | No | No | Sofascore API + openfootball |

### Tier notes
- **Tier S** — Everything you could want, free: shot-level Understat xG since 2014/15, 25+ years of odds + match stats on football-data.co.uk, Sofascore for corners/cards/possession, football-data.org free fixtures, and StatsBomb historical events (especially La Liga via Messi's 17-season career). Markets are efficient, so your edge is model quality and specific markets (corners/cards) where books are lazier.
- **Tier A** — Very good free data but usually MISSING one dimension. RFPL is the standout because it uniquely has Understat xG; Championship/Eredivisie/Primeira Liga get football-data.org free fixtures + full odds; Brazil Série A gets fd.org free + Sofascore.
- **Tier B** — Solid: Sofascore granular stats + xG, football-data.co.uk odds for backtesting, but NO Understat xG and NOT on the fd.org free tier. This is where free data meets soft markets — your best hunting ground.
- **Tier C** — Usable but sparse: fixtures + basic stats via API-Football + Sofascore, odds only if a football-data.co.uk "extra" file exists. LatAm domestic leagues beyond Argentina/Brazil live here — fine for 1X2/O/U/BTTS via Sofascore, thin for corners/cards.

## HIDDEN GEMS (unusual/far-away leagues, unusually rich free data)
1. **Russia Premier League (RFPL)** — the ONLY non-big-5 league in Understat. Free shot-level xG since 2014/15. If you want xG-driven models outside the obvious leagues, this is unique. (Note: Cyrillic team names are URL-encoded by scrapers automatically.)
2. **Copa América 2024 (32 matches) & AFCON 2023 (52 matches) in StatsBomb Open Data** — full free event data. Copa América is directly LatAm-relevant and lets you build South-America-calibrated xG/event models for free (competition_id 223, season_id 282).
3. **Indian Super League 2020/21** — 115 matches of full free StatsBomb event data (rare for a domestic league); train models on a league most books price lazily.
4. **Australia A-League** — SkillCorner released free broadcast **tracking** data for 10 matches of 2024/25 (per SkillCorner's opendata GitHub) — genuinely rare free positional data.
5. **Scandinavia (Allsvenskan, Eliteserien)** — Sofascore xG + football-data.co.uk odds, and notably soft summer markets (they play Mar–Nov, filling the European off-season when your other leagues are dark).
6. **Argentina Liga Profesional** — football-data.co.uk odds file + Sofascore xG + Copa América StatsBomb for calibration; soft, high-variance market.

## Market EDGE implications
- **Efficient (edge = model quality only)**: EPL, La Liga, Bundesliga, Serie A, Ligue 1, Champions League. Huge liquidity; closing lines are sharp — academic and practitioner consensus is that major leagues are weak-form efficient and rarely beatable by more than a few percent on the closing line.
- **Semi-soft with good free data (best risk/reward)**: Championship, Eredivisie, Primeira Liga, Belgium, Scotland, Brazil, Argentina, Liga MX. Sofascore gives you the stats; markets are less sharp than the big-5.
- **Soft, good-enough data (highest theoretical edge, higher variance)**: Scandinavian leagues, Poland, Austria, Switzerland, MLS, J1, lower divisions. Betting-market analysts consistently note that lower-profile/lower-liquidity leagues stay inefficient longer and carry wider bookmaker margins — meaning slower odds correction and more room for a solo modeler, offset by higher variance and lower betting limits.
- **Best free-data-vs-softness combos for you specifically (Colombian, LatAm focus)**: Argentina, Liga MX, Brazil Série A, plus your existing Colombia — all reachable via Sofascore + API-Football, with StatsBomb Copa América for model calibration.

## Recommendations (staged)
1. **Immediately add the four remaining big-5 leagues (La Liga, Serie A, Bundesliga, Ligue 1) to Tier S.** They are drop-in identical to your EPL pipeline: Understat xG scrape + football-data.co.uk CSV + Sofascore. Zero new infrastructure. Do this first.
2. **Add RFPL as your one "exotic" xG league** — it reuses your Understat scraper unchanged. Benchmark: if your Understat-based EPL model generalizes to RFPL with acceptable calibration, you've validated the pipeline cheaply.
3. **Build the Tier-A/B second-division + mid-tier layer** (Championship, Eredivisie, Primeira Liga, Belgium, Scotland, Brazil, Argentina, Liga MX) on Sofascore xG + football-data.co.uk odds. This is your value-hunting core. Escalation benchmark: if backtested closing-line value (CLV) is consistently positive in these leagues, scale stakes here before touching the big-5.
4. **Use StatsBomb Copa América 2024 + AFCON 2023 to train a South-America/rest-of-world xG model** so you're not applying a Europe-trained xG model to LatAm shot distributions. Benchmark: compare your SB-trained xG vs Sofascore's xG on the same LatAm matches; large divergence means keep the custom model.
5. **Only expand into Tier C (Asia, minor LatAm) once your Sofascore ingestion is rock-solid.** These leagues have the softest markets but the flakiest free data and lowest betting limits — do them last, and cap exposure. STOP benchmark: if Sofascore coverage gaps exceed ~10–15% of fixtures in a league, it's not modelable reliably on free data — drop it.

## Caveats
- **Sofascore anti-bot**: ScraperFC now requires browser-mode (Botasaurus) to hit Sofascore's JSON API; expect occasional breakage and rate-limit carefully. For leagues outside `comps.yaml`, query Sofascore's tournament-ID endpoints directly (e.g. `/api/v1/team/{id}/unique-tournament/{id}/season/{id}/statistics/overall`).
- **ScraperFC's Sofascore league list is narrower than Sofascore.com itself.** Confirmed-supported via the module (from release notes) include the big-5 + their second divisions (Championship, Ligue 2, LaLiga 2, 2.Bundesliga, Serie B, Liga Portugal 2), Eredivisie, Primeira Liga, Liga MX (Apertura & Clausura), plus Bulgarian and Ukrainian top flights and English WSL/WSL 2. **Argentina, Brazil, MLS, J1 and Saudi are covered by Sofascore.com but should be verified in `comps.yaml` (main branch — the repo default is `main`, not `master`) before you rely on the module** — otherwise scrape by tournament ID.
- **"Free xG" outside Understat is model-specific.** Sofascore's xG ≠ Understat's xG ≠ StatsBomb's xG; don't mix them in one training set without a source flag (use an `xg_source` column).
- **API-Football free depth is uneven and historical seasons are gated**; treat it as your fixtures/standings/live backbone, not your granular-stats source for smaller leagues.
- **football-data.org free "12 competitions" is fixtures/results/standings only** — no match stats, no odds on the free tier.
- **Aggregator xG sites (xGscore, OddAlerts, FootyStats, footballxg) show xG for 50+ leagues but are for on-screen viewing / paid CSV** — they are NOT free APIs and shouldn't be scraped as a pipeline dependency. Use Sofascore for programmatic xG instead.
- **StatsBomb open data does not include current league rounds** — it's tournament/historical. Great for training an xG model or event-based features, useless for "what are this weekend's fixtures."
- **The exact StatsBomb competition list changes** as new data is released; always re-check `competitions.json` (or `FreeCompetitions()` in R) rather than trusting a static list.