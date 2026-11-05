#!/usr/bin/env python3
"""英単語クイズで「読み」(発音記号)を出すための辞書 packs/en_ipa.json を作る。

  python3 tools/build_ipa.py <en_US.txt> [cefrj.csv cefr_c.csv ...]
  en_US.txt … ipa-dict (MIT) https://raw.githubusercontent.com/open-dict-data/ipa-dict/master/data/en_US.txt
  cefr*.csv … 見出し語(headword列)。生成問題(/generate)で出る語もだいたい拾えるように入れる

収録する語 = 英語コースの単語問題に出る語(index.html SEED・packs/en_*.json・words/all.tsv)+ 渡した CEFR 見出し語。
発音記号は辞書の米音(異形は一番長いもの)。ɹ→r・ɫ→l(日本の辞書でよく見る書き方に寄せる)。
出力: {"word": "/ˈwɝd/", ...}  熟語は語ごとの記号をスペースでつなぐ(全部の語が辞書にあるときだけ)。
"""
import csv, glob, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
Q_RE = re.compile(r'^"([^"]+)" の意味は')


# 同じつづりで読みが2つある語は、単語クイズで出る形(現在形・形容詞など)を優先
OVERRIDE = {'read': '/ˈrid/', 'lead': '/ˈlid/', 'live': '/ˈlɪv/', 'wind': '/ˈwɪnd/', 'tear': '/ˈtɛr/',
            'close': '/ˈkloʊz/', 'use': '/ˈjuz/', 'present': '/ˈprɛzənt/', 'record': '/ˈrɛkɚd/',
            'object': '/ˈɑbdʒɛkt/', 'minute': '/ˈmɪnət/', 'content': '/ˈkɑntɛnt/'}
VOW = set('aeiouæɑɒɔəɛɪʊʌɝɚɐ')


def fix_er(s):
    # ipa-dict は強勢のない er も ɝ で書く(arrange=ɝˈeɪndʒ, water=ˈwɔtɝ)。
    # 強勢記号の後で母音より前にある ɝ だけ強勢あり=ɝ。それ以外は ɚ、直後が母音なら ə+r(arrange→əˈreɪndʒ)
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch == 'ɝ':
            stressed = False
            for c in reversed(out):
                if c in 'ˈˌ':
                    stressed = True
                    break
                if c in VOW:
                    break
            if stressed:
                if i + 1 < len(s) and s[i + 1] in VOW:  # hurry=ˈhɝi → ˈhɝri
                    out.append('ɝr')
                    i += 1
                    continue
            else:
                j = i + 1
                mark = ''
                if j < len(s) and s[j] in 'ˈˌ':
                    mark = s[j]
                    j += 1
                if j < len(s) and s[j] in VOW:
                    out.append('ə' + mark + 'r')
                    i = j
                    continue
                ch = 'ɚ'
        out.append(ch)
        i += 1
    return ''.join(out)


def norm(ipa):
    # 異形が複数あるときは一番長いもの(短い方は around=ɝˈaʊn のような弱形が多い)。同じ長さなら先頭
    vs = [v.strip().strip('/') for v in ipa.split(',')]
    first = max(vs, key=len)
    return fix_er(first.replace('ɹ', 'r').replace('ɫ', 'l'))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    d = {}
    with open(sys.argv[1], encoding='utf-8') as f:
        for line in f:
            if '\t' not in line:
                continue
            w, ipa = line.rstrip('\n').split('\t', 1)
            d.setdefault(w.lower(), norm(ipa))

    words = set()
    html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    words.update(m.group(1) for m in re.finditer(r'\["vocab","\\"([^"\\]+)\\" の意味は', html))
    for p in glob.glob(os.path.join(ROOT, 'packs', 'en_*.json')):
        if p.endswith('en_ipa.json'):
            continue
        for r in json.load(open(p, encoding='utf-8'))['rows']:
            m = Q_RE.match(r[1])
            if m:
                words.add(m.group(1))
    tsv = os.path.join(ROOT, 'words', 'all.tsv')
    if os.path.exists(tsv):
        for line in open(tsv, encoding='utf-8'):
            if line.strip():
                words.add(line.split('\t')[0])
    for c in sys.argv[2:]:
        for r in csv.DictReader(open(c, encoding='utf-8')):
            for h in r['headword'].split('/'):
                words.add(h)

    for w, v in OVERRIDE.items():
        d[w] = v.strip('/')
    out, miss = {}, []
    for w in sorted({w.strip().lower() for w in words if w.strip()}):
        toks = re.findall(r"[a-z][a-z'\-]*", w)
        if not toks:
            continue
        parts = [d.get(t) for t in toks]
        if all(parts):
            out[w] = '/' + ' '.join(parts) + '/'
        else:
            miss.append(w)
    path = os.path.join(ROOT, 'packs', 'en_ipa.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print(f'{len(out)} words -> {os.path.relpath(path, ROOT)} (not found {len(miss)}: {", ".join(miss[:15])} …)')


if __name__ == '__main__':
    main()
