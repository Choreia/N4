#!/usr/bin/env python3
"""Hanasu(Kartik Dhar, https://github.com/KartikDhar09/hanasu)の語彙・漢字・文法データを
Choreia Learn の「問題」行(4択)に変換する。JSは実行せず、データファイルをテキストとして読む。

  python3 tools/import_hanasu.py <hanasuリポジトリのパス>
  → hanasu_jp.json(管理タブの取込ボタンが読む) と hanasu_jp_rows.csv を書き出す

対象: js/vocab-data.js(+vocab-n5/n4/life.js) / js/kanji-data.js(+kanji-n4.js) / js/jlpt-data.js(+grammar-n5/n4.js)
Book(教科書 *Nihongo Fun & Easy*)関連は著作物なので一切読まない。
"""
import json, random, re, sys, csv, os

random.seed(20261102)

# ---------- tiny JS literal parser (strings/numbers/arrays/objects/calls) ----------
class P:
    def __init__(s, t): s.t = t; s.i = 0
    def ws(s):
        while True:
            m = re.compile(r'\s+|//[^\n]*|/\*.*?\*/', re.S).match(s.t, s.i)
            if not m: return
            s.i = m.end()
    def peek(s): s.ws(); return s.t[s.i] if s.i < len(s.t) else ''
    def val(s):
        c = s.peek()
        if c in '\'"`': return s.str()
        if c == '[': return s.arr()
        if c == '{': return s.obj()
        m = re.compile(r'-?\d+(\.\d+)?').match(s.t, s.i)
        if m: s.i = m.end(); return float(m.group()) if '.' in m.group() else int(m.group())
        m = re.compile(r'[A-Za-z_$][\w$]*').match(s.t, s.i)
        if m:
            s.i = m.end(); name = m.group()
            if name in ('true', 'false', 'null', 'undefined'): return {'true': True, 'false': False}.get(name)
            if s.peek() == '(':  # call like G(...) → list of args
                s.i += 1; args = []
                while s.peek() != ')':
                    args.append(s.val())
                    if s.peek() == ',': s.i += 1
                s.i += 1; return {'__call': name, 'args': args}
            return {'__ident': name}
        raise ValueError('unexpected at %d: %r' % (s.i, s.t[s.i:s.i+40]))
    def str(s):
        q = s.t[s.i]; s.i += 1; out = []
        while s.t[s.i] != q:
            ch = s.t[s.i]
            if ch == '\\':
                nx = s.t[s.i+1]; out.append({'n': '\n', 't': '\t'}.get(nx, nx)); s.i += 2
            else: out.append(ch); s.i += 1
        s.i += 1; return ''.join(out)
    def arr(s):
        s.i += 1; out = []
        while s.peek() != ']':
            if s.t.startswith('...', s.i):  # spread: skip the identifier
                s.i += 3; s.val()
            else: out.append(s.val())
            if s.peek() == ',': s.i += 1
        s.i += 1; return out
    def obj(s):
        s.i += 1; out = {}
        while s.peek() != '}':
            if s.t.startswith('...', s.i): s.i += 3; s.val()
            else:
                c = s.peek()
                if c in '\'"': k = s.str()
                else:
                    m = re.compile(r'[^\s:]+').match(s.t, s.i); k = m.group(); s.i = m.end()
                s.ws(); assert s.t[s.i] == ':', (k, s.t[s.i:s.i+30]); s.i += 1
                out[k] = s.val()
            if s.peek() == ',': s.i += 1
        s.i += 1; return out

def export_const(src, name):
    m = re.search(r'export const %s\s*=\s*' % re.escape(name), src)
    if not m: raise KeyError(name)
    p = P(src); p.i = m.end(); return p.val()

def read(base, f):
    with open(os.path.join(base, 'js', f), encoding='utf-8') as fh: return fh.read()

def parse_list(block):
    rows = []
    for line in block.strip().split('\n'):
        if not line.strip(): continue
        rows.append([x.strip() for x in line.split('|')])
    return rows

# ---------- vocabulary ----------
def load_vocab(base):
    topics = []  # {id, level, title, words:[(jp,kana,en)]}
    V = export_const(read(base, 'vocab-data.js'), 'VOCAB')
    seen = set()
    for t in V:
        words = []
        for w in t['words']:
            k = w[0] + '|' + w[1]
            if k in seen: continue
            seen.add(k); words.append((w[0], w[1], w[3]))
        topics.append({'id': t['id'], 'level': t['level'], 'title': t['title'], 'words': words})
    for level, f, const in (('n5', 'vocab-n5.js', 'N5_TOPICS'), ('n4', 'vocab-n4.js', 'N4_TOPICS'), ('life', 'vocab-life.js', 'LIFE_TOPICS')):
        for t in export_const(read(base, f), const):
            words = []
            for r in parse_list(t['list']):
                if len(r) < 4: continue
                k = r[0] + '|' + r[1]
                if k in seen: continue
                seen.add(k); words.append((r[0], r[1], r[2]))
            if words: topics.append({'id': t['id'], 'level': level, 'title': t['title'], 'words': words})
    return topics

def vocab_questions(topics):
    out = []
    all_en = [w[2] for t in topics for w in t['words']]
    for t in topics:
        level = {'n5': 'N5', 'n4': 'N4', 'life': 'N4'}[t['level']]
        pool = [w[2] for w in t['words']]
        for jp, kana, en in t['words']:
            cands = [x for x in pool if x != en and x.split(' ')[0] != en.split(' ')[0]]
            random.shuffle(cands)
            d = cands[:3]
            while len(d) < 3:
                x = random.choice(all_en)
                if x != en and x not in d: d.append(x)
            q = kana if kana == jp else '%s (%s)' % (kana, jp)
            exp = '%s = %s. [%s]' % (jp, en, t['title'])
            out.append(['vocab', q, en, d[0], d[1], d[2], 'A', exp, level])
    return out

# ---------- kanji ----------
def load_kanji(base):
    src = read(base, 'kanji-data.js')
    g5 = export_const(src, 'KANJI_GROUPS'); g4 = export_const(src, 'KANJI_GROUPS_N4')
    items = []  # (ch, en, examples[(word,kana,en)], level, group)
    for level, groups in (('N5', g5), ('N4', g4)):
        for g in groups:
            for k in g['kanji']:
                items.append((k[0], k[3], [(e[0], e[1], e[3]) for e in k[5]], level, g['title']))
    for g in export_const(read(base, 'kanji-n4.js'), 'N4_KANJI_MORE'):
        level = 'N5' if g.get('level') == 'n5' else 'N4'
        for r in parse_list(g['list']):
            if len(r) < 8: continue
            exs = []
            for e in r[7].split(';'):
                p = [x.strip() for x in e.split(',')]
                if len(p) >= 3: exs.append((p[0], p[1], p[2]))
            items.append((r[0], r[3], exs, level, g['title']))
    return items

def kanji_questions(items):
    out = []
    kanas = [e[1] for it in items for e in it[2]]
    for ch, en, exs, level, group in items:
        if not exs: continue
        word, kana, wen = exs[0]
        same = [k for k in kanas if k != kana and abs(len(k) - len(kana)) <= 1]
        random.shuffle(same); d = []
        for k in same:
            if k not in d: d.append(k)
            if len(d) == 3: break
        while len(d) < 3:
            k = random.choice(kanas)
            if k != kana and k not in d: d.append(k)
        exp = '%s = %s.' % (word, wen) + ('' if word == ch else ' %s = %s.' % (ch, en)) + ' [%s]' % group
        out.append(['kanji', 'How do you read %s?' % word, kana, d[0], d[1], d[2], 'A', exp, level])
    return out

# ---------- grammar ----------
def load_grammar(base):
    G = export_const(read(base, 'jlpt-data.js'), 'GRAMMAR')
    out = [dict(id=g['id'], level=g['level'], pattern=g['pattern'], en=g['en'], how=g.get('how', ''), ex=g.get('ex', [])) for g in G if isinstance(g, dict)]
    for g in export_const(read(base, 'grammar-n5.js'), 'GRAMMAR_N5_MORE'):
        out.append(dict(id=g['id'], level='n5', pattern=g['pattern'], en=g['en'], how=g.get('how', ''), ex=g.get('ex', [])))
    for g in export_const(read(base, 'grammar-n4.js'), 'GRAMMAR_N4_MORE'):
        a = g['args'] if isinstance(g, dict) and '__call' in g else None
        if a: out.append(dict(id=a[0], level='n4', pattern=a[1], en=a[2], how=a[5], ex=a[7]))
    return out

def grammar_questions(gs):
    out = []
    answers = {}
    for g in gs:
        for e in g['ex']:
            m = re.search(r'\[([^\]]+)\]', e[0])
            if m: answers.setdefault(g['level'], []).append(m.group(1))
    for g in gs:
        for e in g['ex'][:1]:
            m = re.search(r'\[([^\]]+)\]', e[0])
            if not m: continue
            ans = m.group(1)
            cands = [x for x in answers[g['level']] if x != ans and abs(len(x) - len(ans)) <= 3]
            random.shuffle(cands); d = []
            for x in cands:
                if x not in d: d.append(x)
                if len(d) == 3: break
            while len(d) < 3:
                x = random.choice(answers[g['level']])
                if x != ans and x not in d: d.append(x)
            q = e[0].replace('[' + ans + ']', '＿') + ' (%s)' % e[3]
            out.append(['grammar', q, ans, d[0], d[1], d[2], 'A', '%s = %s. %s' % (g['pattern'], g['en'], g['how']), g['level'].upper()])
    return out

def main():
    base = sys.argv[1]
    rows = vocab_questions(load_vocab(base)) + kanji_questions(load_kanji(base)) + grammar_questions(load_grammar(base))
    seen, uniq = set(), []
    for r in rows:  # 同じ問題文は最初の1つだけ
        if r[1] in seen: continue
        seen.add(r[1]); uniq.append(r)
    rows = uniq
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = {'source': 'Hanasu by Kartik Dhar (https://github.com/KartikDhar09/hanasu)', 'course': 'jp', 'generated': __import__('datetime').date.today().isoformat(),
            'fields': ['cat', 'q', 'a', 'b', 'c', 'd', 'ans', 'exp', 'level'], 'rows': rows}
    with open(os.path.join(here, 'hanasu_jp.json'), 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    with open(os.path.join(here, 'hanasu_jp_rows.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['分野', '問題', '選択肢A', '選択肢B', '選択肢C', '選択肢D', '正解', '解説', 'レベル']); w.writerows(rows)
    from collections import Counter
    print(len(rows), Counter((r[0], r[8]) for r in rows))

if __name__ == '__main__': main()
