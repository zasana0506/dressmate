# dressmate 发布文案

> 三个平台各一份。标了「␣」的是需要你替换的地方。
> 截图在 `docs/screenshot.png`（竖版主图）和 `docs/social-preview.png`（横版封面）。

---

## 一、Hacker News（Show HN）

### 标题

```
Show HN: dressmate – an outfit recommender that explains itself instead of guessing
```

### 正文

```
I built dressmate after noticing that most outfit apps give you the same
useless output: "This combination looks great! Consider adding some personal
flair." They take your photo, send it to an LLM, and hand back a paragraph.

The paragraph isn't the problem. The missing "why" is.

dressmate computes outfits from 19 explicit rules instead of a language
model. Every recommendation tells you which rule fired and why:

    "Navy long-sleeve shirt: at 9°C apparent temperature the base layer
     needs to be light and breathable; cotton worn against skin won't
     stick."

    "Khaki straight-leg pants: chosen because the low is 1°C and your legs
     can't get cold."

    Pitfall: "The khaki pants are too light and the black Chelsea boots too
     dark — the foot of the outfit will look heavy. If you're not in a hurry,
     switch to the brown pair."

It also argues with itself in a useful way. This rule, among others:

    "sneaker_dress_pants": 0.45    # sneakers with dress pants
    "sneaker_tailored_outer": 0.35 # sneakers with a coat or blazer

The style score enters multiplicatively (score *= 1 - 0.40 * (1 - style)).
With an additive penalty, "sneakers with dress pants" was worth 0.03 points
and got buried by warmth details. Multiplicative, it actually holds.

Tradeoffs, stated plainly:
- The rules only know what someone encoded. Coverage is the ceiling.
- Women's clothing rules are written but under-tested, because most of my
  fixture data is menswear. This is the part I most want help with.
- Zero token cost and offline support are real advantages, but they're
  secondary to explainability. If you'd rather have an LLM's creativity than
  a rule's accountability, this isn't for you.

Details:
- 19 rules (12 style penalties + 7 accessory checks), all in
  engine/styling.py and engine/extras.py, all tweakable
- 323 cities in an offline coordinate table, weather from Open-Meteo,
  climate-table interpolation as fallback (3.4°C average error offline)
- Photos and wardrobe stay on your machine. Nothing is sent unless you
  configure a vision model endpoint yourself.
- Path traversal blocked, CSRF protection on by default, optional
  DRESSMATE_TOKEN for write operations
- 286 tests, CI runs Python 3.10–3.13 plus a real Docker build and smoke test
- AGPL-3.0

Repo: https://github.com/zasana0506/dressmate
```

### 第一条评论（自己回，HN 上很关键）

```
A few things people usually ask:

- "Why not just use the LLM?" Because I want to know why, and because the
  answer should be the same tomorrow. The rules are also the unit of
  improvement — someone can disagree with a rule and change it, which
  isn't really possible with a prompt.
- "Is it good for women's clothing?" Honestly, unknown. The rules exist but
  haven't been exercised against a real wardrobe. That's the main thing I'd
  like feedback on.
- "Does it need an API key?" No. Python 3.9+, no dependencies:
  git clone ... && python server.py
```

---

## 二、Reddit（r/SideProject 或 r/opensource）

### 标题

```
I built an outfit recommender that uses 19 rules instead of an LLM, and tells you why
```

### 正文

```
Problem: every outfit app sends your photos to a model and returns
"This outfit looks great!" — with no way to learn from it.

What I built: dressmate, a self-hosted outfit recommender that scores
outfits with 19 explicit rules and explains each choice.

Example output:

  [Base] Navy long-sleeve shirt
     At 9°C apparent temperature the base layer needs to be light and
     breathable; cotton worn against skin won't stick.
  [Outer] Long charcoal down jacket
     Low is 1°C all day, 0.92 clo — this is the critical piece.

  Pitfall: The khaki pants are too light and the black Chelsea boots too
  dark — the foot of the outfit will look heavy. Switch to the brown pair.

  Also needed: socks — khaki pants are light enough on their own, so take
  navy or charcoal, not a shade that follows the pants. The ankle breaks
  the line otherwise.

Things it does: picks by weather and occasion, splits your day into
segments (morning meeting / afternoon client / evening gym = three outfits),
and plans what to pack for a trip with the weather along the way.

No API key, no token cost, works offline. 323 cities in a local coordinate
table. Your photos never leave your machine unless you point it at a vision
model yourself.

Stack: Python stdlib only on the backend, single-file frontend. 286 tests,
CI on Python 3.10–3.13 plus a Docker build and smoke test.

Honest gaps: it's a rules engine, so coverage is the ceiling. Women's rules
are written but under-tested — that's what I'd most like help with.

AGPL-3.0: https://github.com/zasana0506/dressmate
```

---

## 三、一句话版本（发微博 / 群里 / 签名档）

```
写了个不靠大模型的穿搭推荐器：19 条规则代替一次 API 调用，
每件都告诉你为什么这么搭，还会挑毛病。零 token 成本，断网可用。
```

---

## 四、发之前的检查

- [ ] GitHub **Topics 填了**（18 个标签）——不然搜不到，等于没发
- [ ] GitHub **Description 的「12 条」改成「19 条」**
- [ ] 仓库 **Description 改成英文版**（冲国际的话）
- [ ] HN：**标题不要带中文**，正文别太长，别放 GIF
- [ ] Reddit：选对子版（r/SideProject 比 r/Python 更合适）
- [ ] 截图：README 用竖版 `docs/screenshot.png`，
      分享出去用横版 `docs/social-preview.png`
