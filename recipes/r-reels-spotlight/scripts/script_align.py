#!/usr/bin/env python3
# Check recognised words against the known script and fix mis-heard ones.
# usage: python3 scripts/script_align.py words.json   (fix words.json in place)
# The script is the first of: inputs/script/* (script.json {"text"} or .txt/.md),
# (nothing else is read). With no script file (an uploaded clip) the
# order brief's intent (brief.json) is checked instead, more strictly: 80 % must match, and only a
# look-alike word is swapped one-for-one (never a number); nothing is inserted or dropped.
# Neither -> the words are left unchanged.
#        python3 scripts/script_align.py --write-hint FILE   (write a short hint of names and unusual words as a b-audio hint file, or nothing)
import difflib, glob, json, os, re, sys

def script_text():
    for p in sorted(glob.glob('inputs/script/*')):
        if not os.path.isfile(p):
            continue
        raw = open(p, encoding='utf-8').read()
        if p.endswith('.json'):
            try:
                raw = str((json.loads(raw) or {}).get('text') or '')
            except (ValueError, AttributeError):
                raw = ''
        raw = raw.strip()
        if raw:
            return raw
    return ''

def brief_script():
    # an uploaded clip's order has no script file; the owner may have pasted the script
    # as the brief. It is only a candidate: align() leaves the words alone unless 60 % match.
    try:
        brief = json.load(open('brief.json', encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    intent = brief.get('intent') if isinstance(brief, dict) else None
    return intent.strip() if isinstance(intent, str) else ''

def norm(t):
    return re.sub(r"[^0-9a-z]", "", t.lower())

def dress(rec, scr):
    # the script's word, wearing the recognised token's leading/trailing punctuation
    core = re.sub(r"^\W+|\W+$", "", scr) or scr
    lead = re.match(r"^\W*", rec).group(0)
    tail = re.search(r"\W*$", rec).group(0)
    return lead + core + tail

NUMBER_WORDS = set(("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                    "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy "
                    "eighty ninety hundred thousand million billion half once twice first second third").split())

def near_miss(heard, want):
    # a look-alike of the script word (flowers -> flour); never a number or number word
    if heard == want or not heard or not want:
        return False
    if any(re.search(r"\d", t) or t in NUMBER_WORDS for t in (heard, want)):
        return False
    return difflib.SequenceMatcher(None, heard, want, autojunk=False).ratio() >= 0.6

def align(words, script, max_block=4, min_ratio=0.6, near_only=False):
    # near_only (, a brief rather than a script file): only swap a heard word for a look-alike
    # script word one-for-one; never insert, drop, merge or split words.
    toks = []  # (entry index, token)
    for i, w in enumerate(words):
        for t in str(w['text']).split():
            if norm(t):
                toks.append([i, t])
    scr = [t for t in script.split() if norm(t)]
    a, b = [norm(t) for _, t in toks], [norm(t) for t in scr]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ratio = sum(m.size for m in sm.get_matching_blocks()) / max(len(a), 1)
    report = {"script_words": len(scr), "recognised_words": len(a), "match": round(ratio, 3),
              "fixed": [], "dropped": [], "left": []}
    spans = []  # (first, last) entry of each fewer-words fix
    if not scr or ratio < min_ratio:
        report["note"] = "the script does not match this voice; words left as recognised"
        return words, report
    for op, i1, i2, j1, j2 in (sm.get_opcodes() if near_only else []):
        if op == 'replace' and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                rec, want = toks[i1 + k][1], scr[j1 + k]
                if near_miss(norm(rec), norm(want)):
                    new = dress(rec, want)
                    report["fixed"].append([rec, new])
                    toks[i1 + k][1] = new
                else:
                    report["left"].append(rec)
        elif op != 'equal' and op != 'insert':
            report["left"].append(" ".join(t for _, t in toks[i1:i2]))
    for op, i1, i2, j1, j2 in ([] if near_only else sm.get_opcodes()):
        if op == 'equal' or op == 'insert':
            continue
        n, m = i2 - i1, j2 - j1
        if max(n, m) > max_block:
            report["left"].append(" ".join(t for _, t in toks[i1:i2]))
            continue
        if op == 'delete':
            for k in range(i1, i2):
                report["dropped"].append(toks[k][1]); toks[k][1] = None
            continue
        if n > m:  # fewer script words than heard ('New York' -> 'NYC'): one caption
            joined = " ".join(scr[j1:j2])  # from the start of the first heard word to the end of the last
            core = re.sub(r"^\W+|\W+$", "", joined) or joined
            new = re.match(r"^\W*", toks[i1][1]).group(0) + core + re.search(r"\W*$", toks[i2 - 1][1]).group(0)
            report["fixed"].append([" ".join(t for _, t in toks[i1:i2]), new])
            toks[i1][1] = new
            for k in range(i1 + 1, i2):
                toks[k][1] = None
            spans.append((toks[i1][0], toks[i2 - 1][0]))
            continue
        for k in range(n):  # replace: spread the script words over the recognised slots
            s0, s1 = round(k * m / n), round((k + 1) * m / n)
            new = " ".join(dress(toks[i1 + k][1], t) for t in scr[j1 + s0:j1 + s1]) or None
            report["fixed"].append([toks[i1 + k][1], new])
            toks[i1 + k][1] = new
    texts = {}
    for i, t in toks:
        texts.setdefault(i, [])
        if t:
            texts[i].append(t)
    head = list(range(len(words)))  # entries a fewer-words fix spans fold into their first
    for first, last in spans:
        for i in range(first + 1, last + 1):
            head[i] = head[first]
    out, kept = [], {}
    for i, w in enumerate(words):
        if head[i] != i and head[i] in kept:
            o = kept[head[i]]
            more = " ".join(texts[i]) if i in texts else str(w.get('text', '')).strip()
            if more:
                o['text'] = (str(o.get('text', '')).strip() + " " + more).strip()
            if 'end' in w:
                o['end'] = w['end']
            continue
        if i in texts and not texts[i]:
            continue  # every token of this entry was not in the script
        new = dict(w)
        if i in texts:
            new['text'] = " ".join(texts[i])
        out.append(new)
        kept[i] = new
    return out, report

def hint_text(limit=300):
    # b-audio --hint-file: a short list of the names and unusual words the speech holds, so they are
    # spelled right. NOT the whole script: a long hint made whisper.cpp repeat its last sentence in a
    # real run. Sources: the brand name in brief.json, and from the script file the words that are
    # ALL CAPS, hold a digit or an inner capital, or start with a capital in the middle of a sentence.
    # Plain text only: letters, digits, spaces, and . , & ' - characters.
    found = []
    try:
        brief = json.load(open('brief.json', encoding='utf-8'))
        name = (brief.get('brand') or {}).get('name') if isinstance(brief, dict) else None
        if isinstance(name, str):
            found.append(name)
    except (OSError, ValueError, AttributeError):
        pass
    text = script_text()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9'&.-]*", sentence)
        for k, t in enumerate(toks):
            core = t.strip(".'-&")
            if len(core) < 2:
                continue
            if core.isupper() or re.search(r"\d", core) or re.search(r"[a-z][A-Z]", core) or (k > 0 and core[0].isupper()):
                found.append(core)
    seen, out = set(), []
    for w in found:
        w = re.sub(r"[^A-Za-z0-9 .,&'-]", " ", w)
        w = re.sub(r"\s+", " ", w).strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    hint = ", ".join(out)
    if len(hint) > limit:
        hint = hint[:limit].rsplit(", ", 1)[0]
    return hint

if __name__ == '__main__':
    if sys.argv[1:2] == ['--write-hint'] and len(sys.argv) == 3:
        hint = hint_text()
        if hint:
            open(sys.argv[2], 'w', encoding='utf-8').write(hint)
            print("[transcribe] hint file written: %d characters" % len(hint))
        else:
            print("[transcribe] no names or unusual words to hint: no hint file")
        sys.exit(0)
    path = sys.argv[1]
    text, source = script_text(), "script"
    if not text:  # no script file -> the brief, when it is the spoken script
        text, source = brief_script(), "brief"
    if not text:
        print("[transcribe] no script text: words left as recognised (an uploaded clip has no script)")
        sys.exit(0)
    words = json.load(open(path))
    if source == "brief":  # a brief is not a script: 80 % must match, look-alike swaps only
        out, rep = align(words, text, min_ratio=0.8, near_only=True)
    else:
        out, rep = align(words, text)
    rep["source"] = source
    if source == "brief" and rep.get("note"):
        rep["note"] = "the brief is not the spoken script; words left as recognised"
    if not out:
        sys.exit("script check removed every word")
    json.dump(out, open(path, 'w'))
    json.dump(rep, open(os.path.join(os.path.dirname(path) or '.', 'script_align.json'), 'w'), indent=1)
    print("[transcribe] script check (%s): match %.2f, fixed %d, dropped %d, left %d%s" % (
        source, rep["match"], len(rep["fixed"]), len(rep["dropped"]), len(rep["left"]),
        (" - " + rep["note"]) if rep.get("note") else ""))
