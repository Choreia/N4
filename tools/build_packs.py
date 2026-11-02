#!/usr/bin/env python3
"""公開データから Choreia Learn の問題パック(packs/*.json)を生成する。

  python3 tools/build_packs.py <データ置き場>
  データ置き場に置くもの(取得元は README「問題パック」参照):
    n1.csv n2.csv n3.csv     … open-anki-jlpt-decks (MIT)  expression,reading,meaning,tags,guid
    kanji.json               … kanji-data (MIT)            {"漢字":{jlpt_new,meanings,readings_on,readings_kun,...}}
    cefrj.csv                … CEFR-J Vocabulary Profile   headword,pos,CEFR,...
    cefr_c.csv               … Octanove Vocabulary Profile C1/C2 (CC BY-SA 4.0)  headword,pos,CEFR,notes
    ejdic.txt                … EJDict-hand (パブリックドメイン)  英単語<TAB>意味

出力: packs/jp_vocab_n3n2n1.json / packs/jp_kanji_n3n2n1.json / packs/en_cefr_b2c1.json と packs/index.json
行の形式は hanasu_jp.json と同じ [cat,q,a,b,c,d,ans,exp,level]。正解は常に a(画面側でシャッフル)。
"""
import csv, json, os, random, re, sys

random.seed(20261102)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'packs')


def words_overlap(a, b):
    ta = set(re.findall(r'[a-z]+', a.lower()))
    tb = set(re.findall(r'[a-z]+', b.lower()))
    return bool((ta & tb) - {'to', 'a', 'an', 'the', 'of', 'be', 'in', 'on', 'or', 'and', 'for'})


def pick_distractors(correct, pool, n=3, overlap=words_overlap):
    out, tries = [], 0
    while len(out) < n and tries < 200:
        tries += 1
        c = random.choice(pool)
        if c == correct or c in out or overlap(c, correct) or any(overlap(c, o) for o in out):
            continue
        out.append(c)
    return out if len(out) == n else None


# ---------------- 日本語 語彙 N3/N2/N1 ----------------
def build_jp_vocab(src):
    rows = []
    for lv in ('n3', 'n2', 'n1'):
        level = lv.upper()
        path = os.path.join(src, lv + '.csv')
        items, seen = [], set()
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                exp, rd, mean, tags = r['expression'].strip(), r['reading'].strip(), r['meaning'].strip(), r.get('tags', '')
                # 上位レベルの重複(JLPT_2 と JLPT_3 両方のタグ)は下のレベル(先に処理)に入れる
                lvs = sorted(int(t.split('_')[1]) for t in tags.split() if t.startswith('JLPT_'))
                if lvs and 'N%d' % max(lvs) != level:
                    continue
                if not exp or not mean or exp in seen:
                    continue
                seen.add(exp)
                mean = re.sub(r'\s*\([^)]*\)', '', mean)  # 括弧注記を落とす
                mean = ', '.join(m.strip() for m in mean.split(',') if m.strip())[:60]
                if not mean:
                    continue
                items.append((exp, rd, mean))
        pool = [m for _, _, m in items]
        for exp, rd, mean in items:
            ds = pick_distractors(mean, pool)
            if not ds:
                continue
            q = '%s (%s)' % (rd, exp) if rd and rd != exp else exp
            rows.append(['vocab', q, mean, ds[0], ds[1], ds[2], 'A', '%s = %s' % (exp, mean), level])
    return rows


# ---------------- 日本語 漢字 N3/N2/N1 ----------------
def build_jp_kanji(src):
    with open(os.path.join(src, 'kanji.json'), encoding='utf-8') as f:
        data = json.load(f)
    by_level = {3: [], 2: [], 1: []}
    for k, v in data.items():
        lv = v.get('jlpt_new')
        if lv in by_level and v.get('meanings') and (v.get('readings_on') or v.get('readings_kun')):
            by_level[lv].append((k, v))
    rows = []
    for lv, items in by_level.items():
        level = 'N%d' % lv
        items.sort(key=lambda kv: kv[1].get('freq') or 9999)
        meanings = [v['meanings'][0] for _, v in items]
        readings = []
        for _, v in items:
            readings += [r.replace('.', '').replace('-', '') for r in (v.get('readings_on') or []) + (v.get('readings_kun') or [])]
        readings = sorted(set(r for r in readings if r))
        for k, v in items:
            m = v['meanings'][0]
            ds = pick_distractors(m, meanings)
            if ds:
                rows.append(['kanji', 'What does the kanji %s mean?' % k, m, ds[0], ds[1], ds[2], 'A',
                             '%s = %s. on: %s / kun: %s' % (k, ', '.join(v['meanings'][:3]), ' '.join(v.get('readings_on') or []) or '-', ' '.join(v.get('readings_kun') or []) or '-'), level])
            on = v.get('readings_on') or []
            if on:
                ans = on[0]
                mine = set(r.replace('.', '').replace('-', '') for r in on + (v.get('readings_kun') or []))
                ds = pick_distractors(ans, readings, overlap=lambda a, b: a in mine or b in mine or a[0] == b[0])
                if ds:
                    rows.append(['kanji', 'What is the on-reading (音読み) of %s?' % k, ans, ds[0], ds[1], ds[2], 'A',
                                 '%s (%s) = %s' % (k, ', '.join(on), ', '.join(v['meanings'][:3])), level])
    return rows


# ---------------- 英語 B2 / C1 ----------------
def clean_gloss(s):
    s = s.split(' / ')[0]
    s = re.sub(r'〈[^〉]*〉|《[^》]*》|\{[^}]*\}', '', s)   # 〈物事〉《+名》などの文型注記は丸ごと落とす
    s = re.sub(r'[『』]', '', s)
    s = re.sub(r'\([^)]*\)|（[^）]*）', '', s)
    s = re.sub(r'[＋+]\s*[『]?[名動形副][』]?.*$', '', s)
    s = s.replace('…', '').replace('〈', '').strip(' ,;:、。')
    parts = [p.strip() for p in re.split(r'[,，;；]', s) if p.strip()]
    s = '・'.join(parts[:3])
    return s


def build_en(src):
    dic = {}
    with open(os.path.join(src, 'ejdic.txt'), encoding='utf-8') as f:
        for line in f:
            if '\t' not in line:
                continue
            w, g = line.rstrip('\n').split('\t', 1)
            for hw in w.split(','):
                hw = hw.strip()
                if hw and hw not in dic:
                    dic[hw] = g
    heads = {'B2': [], 'C1': []}
    with open(os.path.join(src, 'cefrj.csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['CEFR'] == 'B2':
                heads['B2'].append((r['headword'], r['pos']))
    with open(os.path.join(src, 'cefr_c.csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['CEFR'] == 'C1':
                heads['C1'].append((r['headword'], r['pos']))
    rows = []
    for level, hs in heads.items():
        items, seen = [], set()
        for hw, pos in hs:
            hw = hw.split('/')[0].strip()
            if not re.fullmatch(r'[a-z][a-z\-]+', hw) or hw in seen or hw not in dic:
                continue
            g = clean_gloss(dic[hw])
            if not g or len(g) > 18 or re.search(r'[A-Za-z]', g):
                continue
            seen.add(hw)
            items.append((hw, pos.split('/')[0], g))
        by_pos = {}
        for hw, pos, g in items:
            by_pos.setdefault(pos, []).append(g)
        for hw, pos, g in items:
            pool = by_pos[pos] if len(by_pos.get(pos, [])) >= 20 else [x[2] for x in items]
            ds = pick_distractors(g, pool, overlap=lambda a, b: bool(set(re.findall(r'[一-龥ぁ-んァ-ン]+', a)) & set(re.findall(r'[一-龥ぁ-んァ-ン]+', b))))
            if not ds:
                continue
            rows.append(['vocab', '"%s" の意味は？' % hw, g, ds[0], ds[1], ds[2], 'A', '%s (%s) = %s' % (hw, pos, g), level])
    return rows


def write_pack(name, course, source, rows):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'source': source, 'course': course, 'generated': '2026-11-02',
                   'fields': ['cat', 'q', 'a', 'b', 'c', 'd', 'ans', 'exp', 'level'], 'rows': rows}, f, ensure_ascii=False)
    from collections import Counter
    print(name, len(rows), dict(Counter((r[0], r[8]) for r in rows)))
    return name


def main():
    src = sys.argv[1]
    packs = [
        write_pack('jp_vocab_n3n2n1.json', 'jp', 'open-anki-jlpt-decks (Jamie Sinclair, MIT)', build_jp_vocab(src)),
        write_pack('jp_kanji_n3n2n1.json', 'jp', 'kanji-data (David Gouveia, MIT)', build_jp_kanji(src)),
        write_pack('en_cefr_b2c1.json', 'en', 'CEFR-J Vocabulary Profile / Octanove Vocabulary Profile (CC BY-SA 4.0) + EJDict-hand (public domain)', build_en(src)),
    ]
    index = {'packs': ['../hanasu_jp.json'] + packs}
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
