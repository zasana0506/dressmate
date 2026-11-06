# 建仓时填什么

GitHub 仓库设置页（Settings → General）里，这几项直接影响别人能不能搜到你。

## Description（最多 350 字符）

```
不靠大模型也能推荐穿搭。12 条可解释的规则代替 AI，零 token 成本、断网可用、每次结果一致。拍照建衣橱，按天气和场合给方案。
```

（67 字符。选这版是因为 GitHub 上同类的衣橱项目——wardrowbe、Libre-Closet、
clothinv、wardrobe-hq——清一色走 AI 视觉识别路线。「不用大模型」是最大的区分点，
放最前面，别人一眼就知道不一样。）

备选：

```
衣柜满得关不上，早上出门还是不知道穿什么。拍照建衣橱，按天气和场合给建议——每条建议都能说出为什么这么搭。
```

（53 字符。痛点开头，转化率通常更高，但技术差异点被压在后面。）

纯英文版（冲国际 star）：

```
Rule-based outfit advisor. 12 explainable style rules instead of an LLM — zero token cost, works offline, same result every time. Snap your wardrobe, get outfits for the weather.
```

## Topics（最多 20 个，加满）

这���是 GitHub 搜索的主要索引维度，加满。

```
wardrobe
outfit-recommendation
outfit-planner
styling
menswear
womenswear
self-hosted
docker
privacy
no-llm
rule-engine
weather
python
clothing
fashion
personal-wardrobe
home-automation
open-source
```

## Website（可选）

你部署后的公网地址，比如 `https://dressmate.你的域名.com`。
没有就先留空，等部署了再回来填。

## Social preview（可选但强烈建议）

在 README 顶部配一张 1280×640 的图，显示在搜索结果和分享卡片里。
仓库首页右侧有个「Add a social preview image」的上传位。

没有现成截图的话，临时截一张网页顶部也行——比没有强很多。

## 关于分支保护

个人项目不需要。Settings → Branches 里的规则可以不动。

## 关于 Discussions

Settings → General → Features → 勾上 **Discussions**。
给提问和「规则讨论」留个地方。仓库已经备好了对应的 issue 模板，
但规则怎么改更适合放讨论区。

## 关于 Sponsors

不急着开。等真的有人想赞助再说，
提前挂着反而像在卖东西。
