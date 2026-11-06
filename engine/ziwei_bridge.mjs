// 紫微斗数排盘桥接：Python 侧通过 stdin 传入生辰，stdout 返回 JSON。
//
// 为什么不把排盘逻辑用 Python 重写：iztro 的排盘口径（星曜亮度、闰月、
// 真太阳时）已经对齐《紫微斗数全书》，重写必然引入偏差。这里只做一次
// 取数，不做判断——五行、颜色、款式的映射全部留在 Python 侧，方便调整。
//
// 依赖复用 workbuddy 的 ziwei-doushu skill 自带的 node_modules，
// 不往项目里装任何东西。找不到时明确报错，不用假数据兜底。
//
// 取数范围：本命十二宫（含主星亮度、辅星、四组十二神）+ 流运五层
// （大限/小限/流年/流月/流日/流时）的宫名映射与四化。之所以一次全取，
// 是因为「流日疾厄宫」「流日迁移宫」都要靠 flow 的宫名映射回本命宫才能定位。

import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const CANDIDATES = [
  process.env.ZIWEI_NODE_MODULES,
  join(process.env.USERPROFILE || process.env.HOME || '', '.workbuddy/skills/ziwei-doushu/scripts'),
  join(process.env.USERPROFILE || process.env.HOME || '', '.workbuddy/skills/ziwei-doushu'),
].filter(Boolean);

function loadIztro() {
  for (const dir of CANDIDATES) {
    const pkg = join(dir, 'package.json');
    if (!existsSync(join(dir, 'node_modules', 'iztro'))) continue;
    try {
      const req = createRequire(existsSync(pkg) ? pkg : join(dir, 'noop.json'));
      const mod = req('iztro');
      return mod.astro || (mod.default && mod.default.astro) || null;
    } catch (e) {
      // 换下一个候选路径
    }
  }
  return null;
}

const readStdin = () => new Promise((resolve) => {
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => { buf += c; });
  process.stdin.on('end', () => resolve(buf));
});

const main = async () => {
  let args = {};
  try {
    args = JSON.parse((await readStdin()) || '{}');
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: '参数不是合法 JSON' }));
    return;
  }

  const astro = loadIztro();
  if (!astro) {
    process.stdout.write(JSON.stringify({
      ok: false,
      error: '找不到 iztro 排盘引擎（需要 Node.js 与 ziwei-doushu skill 的依赖）',
    }));
    return;
  }

  const solar = String(args.solar_date || '').trim();
  const timeIndex = Number.isFinite(+args.time_index) ? +args.time_index : 6;
  const gender = args.gender === '女' ? '女' : '男';
  const target = String(args.target_date || '').trim();

  if (!/^\d{4}-\d{1,2}-\d{1,2}$/.test(solar)) {
    process.stdout.write(JSON.stringify({ ok: false, error: '出生日期格式应为 YYYY-MM-DD' }));
    return;
  }

  let astrolabe;
  try {
    astrolabe = astro.bySolar(solar, timeIndex, gender, true, 'zh-CN');
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: '排盘失败：' + e.message }));
    return;
  }

  const horo = astrolabe.horoscope(target);
  const palaces = astrolabe.palaces || [];

  // 本命十二宫：星曜名称与亮度是 Python 侧唯一的判断依据，原样给出不加工
  const natal = palaces.map((p, i) => ({
    index: i,
    name: p.name,
    branch: p.earthlyBranch,
    stem: p.heavenlyStem,
    is_body_palace: !!p.isBodyPalace,
    major: (p.majorStars || []).map((s) => ({
      name: s.name, brightness: s.brightness || '', mutagen: s.mutagen || '',
    })),
    minor: (p.minorStars || []).map((s) => ({
      name: s.name, brightness: s.brightness || '', mutagen: s.mutagen || '',
    })),
    // 杂曜里有红鸾、天喜、咸池这类桃花星，是判断"今天要不要见人"的关键
    adj: (p.adjectiveStars || []).map((s) => s.name),
    changsheng12: p.changsheng12 || '',
    boshi12: p.boshi12 || '',
    jiangqian12: p.jiangqian12 || '',
    suiqian12: p.suiqian12 || '',
  }));

  // 流运各层：palaceNames 与 palaces 同序，index_of 把「流日疾厄」这类
  // 宫名换回本命宫下标，再回 natal 取星曜。缺 index_of 就只能取命宫，
  // 疾厄/迁移这些判断全部做不了，所以这里必须给全。
  const flowLayer = (o) => {
    if (!o) return null;
    const names = o.palaceNames || [];
    const indexOf = {};
    names.forEach((nm, i) => { if (!(nm in indexOf)) indexOf[nm] = i; });
    return {
      stem: o.heavenlyStem || '',
      branch: o.earthlyBranch || '',
      palace_names: names,
      index_of: indexOf,
      mutagen: o.mutagen || [],
    };
  };

  const flow = {
    decadal: flowLayer(horo.decadal),
    age: flowLayer(horo.age),
    yearly: flowLayer(horo.yearly),
    monthly: flowLayer(horo.monthly),
    daily: flowLayer(horo.daily),
    hourly: flowLayer(horo.hourly),
  };

  const daily = flow.daily || { palace_names: [], index_of: {}, mutagen: [], stem: '', branch: '' };
  const soulIdx = daily.index_of['命宫'];
  const soulPalace = soulIdx === undefined ? null : palaces[soulIdx];
  const opposite = soulIdx === undefined ? null : palaces[(soulIdx + 6) % 12];

  const pickStars = (p) => (p && p.majorStars ? p.majorStars.map((s) => ({
    name: s.name, brightness: s.brightness || '', mutagen: s.mutagen || '',
  })) : []);

  process.stdout.write(JSON.stringify({
    ok: true,
    gender,
    solar_date: astrolabe.solarDate || solar,
    lunar_date: horo.lunarDate || '',
    birth_lunar: astrolabe.lunarDate || '',
    chinese_date: astrolabe.chineseDate || '',
    soul: astrolabe.soul || '',
    body: astrolabe.body || '',
    five_elements_class: astrolabe.fiveElementsClass || '',
    soul_palace_branch: astrolabe.earthlyBranchOfSoulPalace || '',
    body_palace_branch: astrolabe.earthlyBranchOfBodyPalace || '',
    target_date: target,
    palaces: natal,
    flow,
    // 以下为旧字段，保持向后兼容（/api/luck 的既有输出依赖它）
    daily: {
      stem: daily.stem,
      branch: daily.branch,
      palace_branch: soulPalace ? soulPalace.earthlyBranch : '',
      natal_palace_name: soulPalace ? soulPalace.name : '',
      mutagen: daily.mutagen,
      soul_stars: pickStars(soulPalace),
      opposite_stars: pickStars(opposite),
      soul_star_names: pickStars(soulPalace).map((s) => s.name),
      opposite_star_names: pickStars(opposite).map((s) => s.name),
    },
    yearly: {
      stem: horo.yearly ? horo.yearly.heavenlyStem : '',
      branch: horo.yearly ? horo.yearly.earthlyBranch : '',
    },
  }));
};

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: '排盘异常：' + e.message }));
});
