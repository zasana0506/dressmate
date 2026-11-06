#!/usr/bin/env bash
# 一键发布到 GitHub。
#
# 用法：
#   1) 先在 GitHub 网页上建一个空仓库（不要勾 README/.gitignore/LICENSE）
#   2) 改掉下面的 GITHUB_USER
#   3) bash publish.sh
#
# 这个脚本会做的事：配 git 身份 → 关联远程 → 推送 → 打印后续要点的设置。

set -e

# ===== 只需要改这一行 =====
GITHUB_USER="your-username"
# ==========================

REPO_NAME="dressmate"
BRANCH="main"

cd "$(dirname "$0")"

echo "=== 1/5 检查仓库状态 ==="
if [ -z "$(git status --porcelain)" ]; then
    echo "  工作区干净，$(git rev-list --count HEAD) 个提交待推送"
else
    echo "  有未提交的改动："
    git status --short
    echo "  → 先跑 git add -A && git commit -m \"说明\""
    exit 1
fi

echo
echo "=== 2/5 配置 git 身份 ==="
if [ -z "$(git config user.name)" ]; then
    git config user.name "${GITHUB_USER}"
    echo "  已设置 user.name = ${GITHUB_USER}"
else
    echo "  user.name 已是 $(git config user.name)"
fi
if [ -z "$(git config user.email)" ]; then
    git config user.email "${GITHUB_USER}@users.noreply.github.com"
    echo "  已设置 user.email = ${GITHUB_USER}@users.noreply.github.com"
    echo "  （想用真实邮箱就改：git config user.email 你的邮箱）"
else
    echo "  user.email 已是 $(git config user.email)"
fi

echo
echo "=== 3/5 关联远程 ==="
REMOTE="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
if git remote get-url origin > /dev/null 2>&1; then
    echo "  origin 已存在，指向 $(git remote get-url origin)"
    echo "  → 如需改：git remote set-url origin ${REMOTE}"
else
    git remote add origin "$REMOTE"
    echo "  已关联 origin = ${REMOTE}"
fi

echo
echo "=== 4/5 推送 ==="
echo "  执行：git push -u origin ${BRANCH}"
echo "  （首次推送会要求登录，用浏览器授权即可）"
git push -u origin "$BRANCH"

echo
echo "=== 5/5 完成 ==="
cat <<EOF

仓库地址：https://github.com/${GITHUB_USER}/${REPO_NAME}

接下来做这几件事（都在网页上）：

  1. Settings → General → Description 填一句话简介
     docs/REPO-SETUP.md 里有现成的文案

  2. Settings → General → Topics 加满标签（20 个）
     docs/REPO-SETUP.md 里有清单，话题是搜索的主要入口

  3. 在 README 顶部加一张截图（1280×640）
     会显示在搜索结果和分享卡片里，对 star 转化影响最大

  4. 等 Actions 跑完（CI 会建镜像并冒烟测试）
     绿了说明别人 clone 下来能跑

  5. 发一条分享，让第一个人看到它

EOF
