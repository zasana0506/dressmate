# 发布到 GitHub 的完整步骤

本文档给「第一次发 GitHub 仓库」的人看。全部照做即可，不需要懂 Git 内部原理。

## 前提

- 一个 GitHub 账号（免费就够）
- 电脑上装了 Git（你这台已经有了，版本 2.55.0）
- 仓库代码在 `dressmate/` 目录，已经有 6 次提交，测试全绿

---

## 第一步：在 GitHub 网页上建一个空仓库（2 分钟）

打开 https://github.com/new

| 字段 | 填什么 |
|---|---|
| Owner | 你的账号 |
| Repository name | `dressmate`（这个名字现在没人用，我确认过） |
| Description | 先留空，等下在 Settings 里填效果更好的版本 |
| Public / Private | **Public**（要 star 必须是公开） |
| **Add a README file** | **不要勾** |
| **Add .gitignore** | **不要勾** |
| **Choose a license** | **不要选** |

后三项千万别勾——仓库里已经有了，勾了会冲突。

点 **Create repository**。

---

## 第二步：填仓库设置（1 分钟）

建好后会跳到仓库首页。点右边的 **Settings** → **General**。

### Description

```
拍照建衣橱，按天气和场合给穿搭建议。规则驱动，不猜、不联网、不花 token 钱。
```

### Topics

在页面往下滚，找到 **Topics**，点铅笔图标，把下面这行整个粘进去：

```
wardrobe outfit-recommendation outfit-planner styling menswear womenswear self-hosted docker privacy no-llm rule-engine weather python clothing fashion personal-wardrobe open-source
```

**这一步别跳过。** Topics 是别人在 GitHub 里搜到你的唯一途径。不加标签，等于把仓库锁在小黑屋里。

### Discussions

同一页往下，**Features** 区域勾上 **Discussions**。

给「规则怎么改才对」这类问题留个讨论区，比塞 issue 合适。

---

## 第三步：推代码（1 分钟）

回到代码目录。最省事的办法是用仓库里准备好的脚本：

```bash
cd D:/workbuddydate/2026-11-05-11-03-54/dressmate
```

打开 `publish.sh`，把第二行改成你的 GitHub 用户名：

```bash
GITHUB_USER="你的用户名"
```

然后执行：

```bash
bash publish.sh
```

脚本会自动：检查工作区 → 配 git 身份 → 关联远程 → 推送 → 打印后续提示。

### 推送时要求登录

第一次推送会弹出一个浏览器窗口，让你授权 Git Credential Manager 访问 GitHub。
点授权即可，之后就不再提示了。

### 如果你更想手动敲

```bash
git config user.name "你的用户名"
git config user.email "你的用户名@users.noreply.github.com"
git remote add origin https://github.com/你的用户名/dressmate.git
git push -u origin main
```

（提交信息里用的邮箱如果想显示在 GitHub 主页上，换成真实邮箱：
`git config user.email 你的邮箱@example.com`，然后需要重设提交作者——
可以用 `git rebase` 或直接不折腾，noreply 邮箱也完全没问题。）

---

## 第四步：等 CI 跑完（2–5 分钟）

仓库首页有个 **Actions** 标签。点进去应该能看到一个正在跑的工作流。

它做四件事：
1. 在 Python 3.10 / 3.11 / 3.12 / 3.13 上各跑一遍 239 个测试
2. 校验样例衣橱的数据没写错
3. 跑发布自检（确认没有私人数据混进仓库）
4. **真的构建 Docker 镜像，然后起容器、实调推荐接口**

第 4 条是最有价值的——它验证的是「别人 clone 下来能不能跑起来」。

**全绿说明这个仓库是能用的。** 如果某条挂了，点进去看日志，通常就是我在这边已经修过的问题的另一个环境版本。

---

## 第五步：加一张截图（重要）

README 现在没有配图。**这是影响 star 转化最大的一个短板。**

GitHub 仓库首页右侧有个图片框，点它上传一张 **1280×640** 的图，会显示在搜索结果和分享卡片里。

怎么截：

```bash
cd D:/workbuddydate/2026-11-05-11-03-54/dressmate
python server.py
```

浏览器打开 http://127.0.0.1:8848 ，截推荐页面最上面那块（标题 + 三套方案卡），
用系统截图工具存成 PNG，再传到 GitHub。

也可以放进仓库里，让 README 顶部能直接显示：

```bash
# 截图存成 docs/screenshot.png 后，在 README 顶部加一行：
# ![screenshot](docs/screenshot.png)
```

---

## 第六步：让别人看到（这步才是拿 star 的关键）

发出去才有 star，躺着不会有人来。

**小红书**（最有效）：拍一段 15 秒的录屏——拖三件衣服进去，它按今天的天气给出三套，
每套都告诉你这身哪里不讲究。标题写「我把 2000 件衣服变成了一个会讲道理的搭配器」。

**知乎 / V2EX**：写一篇「为什么我用规则引擎而不是大模型做穿搭推荐」，
这类观点贴在这个赛道上很容易被顶。

**V2EX / 掘金**：直接发「开源了一个自托管的穿搭推荐工具，零依赖零 token 费」，
带上仓库地址。

**朋友圈 / 群**：先找 3–5 个人用起来，他们提的每个 issue 都是后续 star 的理由。

---

## 常见问题

**Q：推的时候提示 `fatal: could not read Username`**
说明没登录。确认 credential.helper 是 `manager`：
```bash
git config --global credential.helper manager
```
然后重推，会弹浏览器授权。

**Q：GitHub 上显示的默认分支是 master，但我是推 main 的**
建仓时没勾 README，GitHub 就没有初始分支，第一次推送会直接创建 main。
如果还是不对，在 Settings → Branches 里改默认分支为 main。

**Q：想改仓库名 / 描述 / topics**
随时能改，不影响代码。但仓库名改了，旧链接会失效，所以早改早好。

**Q：以后怎么更新代码**
```bash
git add -A
git commit -m "说明这次改了什么"
git push
```

**Q：能不能撤销已经推上去的东西**
能，但麻烦——改历史要 force push，别人 clone 过就会出问题。
所以推送前跑一次 `python tools/check_release.py`，它会告诉你有没有不该进仓库的文件。

**Q：我的真实衣橱会不会被推上去**
不会。已经验证过：2017 张照片、1989 件标注、`data/profile.json`（含出生日期）、
`web/cloud-config.local.js`（含云服务密钥）全部被 `.gitignore` 挡住，
git 里只有 64 个文件、769KB。
但每次提交前跑一次 `python tools/check_release.py` 更保险。
