# Valorant Visual/Rendering Reference (for the detection model)

Reference for anything that changes how a character renders on screen —
relevant to why the enemy-detection model succeeds or fails on a given
frame. Compiled August 2026 via web research; cite-checked where noted.
Not a strategy guide — visual rendering only.

## 1. Map Pool

**Active competitive rotation (7, current as of Act 4 2026):** Ascent,
Split, Breeze, Lotus, Sunset, Haven, Summit.
[Turbosmurfs](https://turbosmurfs.gg/article/the-7-maps-in-valorant-rotation)

Riot rotates the 7-map competitive pool at the start of each Act; 13 maps
exist total, the other 6 sit out temporarily. Most recent swap: **Summit**
added (Patch 13.00, June 23 2026 — Radiant training academy in Hunan,
China; unique mechanic: droppable walls mid-round), **Fracture and Pearl**
removed from rotation.
[esportstalk](https://www.esportstalk.com/blog/three-available-valorant-maps/)

**Palette notes** (relevant since outline-vs-background contrast appears
to matter a lot for detection):
- **Ascent** — warm/earthy tones, terracotta roofs (similar warm-tan
  family to the Shooting Range walls we tested against).
- **Breeze** — tropical, green and blue scenery, seaside/ruins, open
  spaces — cooler palette, likely higher contrast against red/purple
  outlines than Ascent.
- **Haven** — gardens/architecture, described as "peaceful" — mixed
  palette.
- **Lotus** — bright colors, golden-lit ruins, earthy tones — warm,
  similar contrast profile concern as Ascent/the Shooting Range.
- **Sunset** — disaster-struck kingdom facility, food-truck/city setting,
  traditional 3-lane.
- **Summit** — mountain training-academy setting (visual palette not
  well documented yet, newest map).
- Split, out-of-rotation maps (Bind, Icebox, Fracture, Pearl, Abyss, etc.)
  — not covered in depth here; palette varies map to map.
[Turbosmurfs](https://turbosmurfs.gg/article/the-7-maps-in-valorant-rotation),
[esportstalk](https://www.esportstalk.com/blog/three-available-valorant-maps/)

**Implication:** the outline-color contrast finding (purple >> red >>
yellow against the Shooting Range's warm tan walls) may not generalize
across maps — a cool-palette map like Breeze could flip which highlight
color has the best contrast. This is untested.

## 2. Agent Roster — Visual-Rendering-Relevant Abilities

29 agents total across 4 roles as of 2026; newest is **Miks** (Controller,
added March 18 2026 — only Controller who can heal allies). Agents are
added roughly every two Acts, so any training dataset older than early
2026 likely doesn't include Miks (or possibly other very recent agents).
[strafe.com](https://www.strafe.com/articles/read/all-valorant-agents-released-to-date/)

Full roster found: **Duelists** — Jett, Reyna, Phoenix, Raze, Yoru, Neon,
Iso, Waylay. **Controllers** — Brimstone, Omen, Astra, Viper, Harbor,
Clove, Miks. **Sentinels** — Sage, Cypher, Killjoy, Chamber, Deadlock,
Vyse, Veto. **Initiators** — Sova, Breach, Skye, KAY/O, Fade, Gekko, Tejo,
(+ others not fully enumerated in sources — role count didn't fully
reconcile to 29 across sources, treat this roster as approximate).

**Abilities/effects that change how a character renders, beyond the base
Friend-or-Foe fresnel (already covered in PLAN.md):**
- **Reyna's ultimate (Empress)** — screen-wide gold/yellow color grading
  that also tints enemy rendering (already confirmed directly in this
  project — see PLAN.md).
- **Sova's Recon Bolt** and **Fade's Haunt** — reveal enemy silhouettes
  through walls (temporary outline, distinct from the always-on
  Friend-or-Foe fresnel).
- **Deadlock's Sonic Sensor** — shows enemy silhouettes through walls.
- **Cypher's Neural Theft (ultimate)** — reveals the position of all
  living enemies after interacting with a corpse.
- **Vulnerable status** (doubles incoming damage) — applied by
  **Killjoy's Alarmbot**, **Viper's Snake Bite**, **Astra's Gravity
  Well**. Exact visual treatment (outline/pulse color) unconfirmed by
  research — worth a targeted look if this status shows up in test
  footage.
[zleague](https://www.zleague.gg/theportal/valorant-shooting-through-walls-a-beginners-guide/),
[gamerant](https://gamerant.com/valorant-status-effects-explained/)

Not confirmed in this research pass: Skye's reveal-through-walls exact
visual treatment, Yoru/Omen cloak-adjacent effects, Tejo/Vyse/Waylay/Miks
ability visuals specifically (all newer agents, thinner web coverage).
Flag as unresolved rather than guessed.

## 3. Graphics/Video Settings (Video tab)

| Setting | What it visually changes |
|---|---|
| Material Quality | Reflections (e.g. floor), ability VFX density/brightness (smoke thickness, recon-dart brightness) — environment/VFX, not confirmed to touch character models directly |
| Texture Quality | Overall texture detail — most relevant of the three to character skin/clothing appearance |
| Detail Quality | Map-level clutter (grass, small props) |
| UI Quality | HUD/UI element fidelity |
| VSync | Frame pacing/tearing — not a rendering-content change |
| Anti-Aliasing (None/MSAA levels) | Edge smoothing — could affect crispness of character silhouette edges, relevant to a detector reading edges/outlines |
| Anisotropic Filtering | Clarity of textures at a distance/angle |
| Improve Clarity | Overall sharpness |
| Experimental Sharpening | Reduces blurriness |
| Bloom | Glow around light sources — could bleed into/soften outline edges |
| Distortion | Heat-shimmer around fire/heat sources |
| Cast Shadows | Shadows on player model and weapon |
[metabomb](https://www.metabomb.net/valorant/gameplay-guides/valorant-best-video-settings-for-fps),
[ibuypower](https://www.ibuypower.com/blog/games/best-valorant-pc-settings)

Confirmed elsewhere in this project: Riot explicitly states these
settings **"scale environments, characters, and weapons differently"**
— so character rendering fidelity does vary with Texture/Detail/Material
Quality specifically, not just environment. (Source: earlier research in
this session, search results on Valorant graphics settings guides.)

## 4. Accessibility Settings (General tab)

- **Enemy Highlight Color** — Red (default) / Purple (Tritanopia) /
  Yellow (Deuteranopia) / Yellow (Protanopia). Already extensively tested
  in this project — see PLAN.md.
- **Ally fresnel** is a fixed neutral blue, not user-customizable (no
  "Ally Highlight Color" option found).
- Enemy outlines can also be toggled off entirely ("hide agent outlines")
  — a player running with them off would produce footage with **no**
  fresnel effect on enemies at all, a third state beyond "which color."
[dotesports](https://dotesports.com/valorant/news/how-to-hide-agent-outlines-in-valorant)

## 5. Skins/Cosmetics — Bounded, Good News

**Agent/character skins do not exist in Valorant** (as of this research,
August 2026) — Riot has deliberately not added them, citing competitive-
integrity concerns (a skin altering a character's silhouette/hitbox
would be a gameplay-affecting pay-to-win vector, as seen in other
games). Only **weapons** have skins.
[gamerant](https://gamerant.com/valorant-agent-skins/),
[bo3.gg](https://bo3.gg/valorant/articles/agent-skins-in-valorant-what-they-are-and-whether-theyll-appear-in-game)

**Implication — this bounds the problem nicely:** character-body
appearance is NOT a cosmetic variable across different players' footage
(unlike outline color, quality settings, or map). The only
player-specific cosmetic variance is **weapon skins/viewmodels** — which
matters for the "own weapon misidentified as enemy" false-positive
pattern seen earlier in this project (pretrained model boxing the
player's viewmodel), but does not add variance to how *enemy* character
bodies look.

## 6. Other Rendering-Relevant Quirks

- **Replay System** (added Patch v11.06, 2025) — this is what the
  "killcam"-looking frame found earlier in this project actually was
  (scrubber, timeline, round counter) — correcting that earlier
  assumption, it's the Replay System, not a traditional killcam. Notable
  because Replay mode lets a viewer: watch from **any of the 10 players'
  first-person perspectives** (not just their own), **toggle
  friendly/enemy outlines on or off**, switch to a **third-person free
  observer camera**, and show/hide minimap/HUD. A frame captured from
  Replay mode could therefore show a completely different outline state
  or even a different player's POV than the recording player's own live
  settings — a meaningfully different visual context from live gameplay,
  and worth checking whether any training-dataset or test images came
  from Replay mode rather than live play.
  [thespike.gg](https://www.thespike.gg/valorant/news/valorant-replay-system-explained-features-limitations-and-release-date/6645)
- **Fog of War caveat:** even with outlines toggled off in Replay,
  enemies can still appear on the minimap — inconsistency between
  first-person visibility and minimap visibility.
- Spectator mode, HDR/brightness, and colorblind-mode rendering
  differences beyond the highlight-color options were not found in this
  research pass — unresolved.

## Variables We Have NOT Yet Tested for Effect on the Detection Model

- **Map** — all real-footage tests so far used one map's frames (or the
  Shooting Range, not a real map at all); outline-vs-background contrast
  likely varies significantly by map palette (see Section 1).
- **Texture / Detail / Material Quality settings** — flagged, not tested
  (needs its own comparison clip, ideally on a real player not bots).
- **Enemy outlines toggled fully off** — a state distinct from "which
  color," not yet tested.
- **Replay-mode footage vs. live gameplay** — untested whether frames
  sourced from Replay mode (different outline/POV state) behave
  differently from live-gameplay frames.
- **Ability-driven reveal effects** (Sova Recon, Fade Haunt, Deadlock
  Sonic Sensor, Cypher Neural Theft) and the **Vulnerable status pulse**
  — flagged as a category in PLAN.md, not individually tested per
  ability.
- **Newer agents** (Miks, and possibly Tejo/Vyse/Waylay depending on
  training-dataset vintage) — may be underrepresented or absent from the
  training data entirely if the dataset predates their release.
- **Anti-Aliasing / Bloom / Cast Shadows** settings specifically, as
  distinct from Material/Texture/Detail Quality — not tested, plausible
  minor effect on edge/outline crispness.
