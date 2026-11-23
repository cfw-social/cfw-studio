#!/usr/bin/env python3
# Takeover text names only the order's brand, unless it quotes the speech word for word.
# usage: python3 scripts/takeover_brand.py PLAN.json WORDS.json [BRAND]          (repair takeovers in place)
#        python3 scripts/takeover_brand.py --check PLAN.json WORDS.json [BRAND]  (exit 1 on a foreign name)
# BRAND is the order's brand name ("" = the order has none). Without it the brand comes from the
# step workdir: inputs/cta/cta.json brandName, else brief.json brand.name (as the end card does).
# A foreign name is a brand-like word the speech says that the order does not own: an acronym with no
# vowel (XQZ, also spelled out "X Q Z") or a CamelCase word whose first part has 3+ letters (AcmeCloud).
# It is never a generic acronym (AI, CAC, MLS, HOA, NYC, PhD, ...), a regulator or firm (SEC, FINRA,
# KPMG, ...), a channel or tool (Instagram, iPhone, ...), a word that starts lower case (iOS, eBay), a
# person's name or initials (McKenzie, DeShawn, JoAnn, JT, ANNA), or capitals used for emphasis (INSANE,
# BOOM): a 2-letter acronym, an all-caps word with a vowel and a CamelCase word with a 2-letter first
# part are all left alone. tk-quote ATTR credits a person or company, so it is never touched.
# A line of 3+ words that is an exact run of
# transcript words (case and punctuation aside) is a quote and keeps its words, unless the foreign
# name is most of it. Otherwise the name becomes the order's brand; with no order brand it is dropped.
# A brand is never invented. When in doubt a word is left alone: rule 5 asks the planner for the rest.
import html, json, os, re, sys

TOKEN = re.compile(r"[A-Za-z0-9]+(?:['’.&-][A-Za-z0-9]+)*")
TAG = re.compile(r"(<[^>]*>)")
POSS = re.compile(r"['’]s$", re.I)
VOWEL = re.compile(r"[AEIOUYaeiouy]")
NAME_PREFIX = re.compile(r"^(?:Mc|Mac|O['’]|D['’]|De|Di|Da|Du|Le|La|Van|Von|St)[A-Z]")
SKIP = {"tk-typing-ui": {"LABEL", "TYPING_SPEED"}, "tk-quote": {"ATTR"}}   # ATTR names who said it
HTML_KEYS = {"TITLE", "QUOTE"}
MIN_QUOTE = 3
# Never a competing brand: generic business, marketing, finance, real-estate, place and tech
# acronyms, and the channels / tools a reel talks about.
GENERIC = set("""
i ok ai api apis ceo ceos cto cfo coo cmo cro vp svp evp md phd mba cpa cfa jd rn pa hr pr it qa
diy faq faqs pdf url sms dm dms fyi asap eta tbh imo lol omg vip am pm est pst cst mst utc
q1 q2 q3 q4 ytd mtd yoy qoq mom b2b b2c d2c dtc smb smbs saas crm cms erp kpi kpis okr okrs roi
roas aov ltv cac cpc cpm cpa cpl ctr cvr ppc sem seo ugc cta ctas mrr arr gmv nps sop sops mvp
llc inc ltd co corp plc nda llp gst vat irs ira etf ipo sba fico heloc dti pmi apr apy arm emi gdp
usd eur gbp cad aud inr jpy cny
mls hoa fha va usda adu adus hvac reo nar cma hud fsbo noi reit reits sqft sf bd ba ac gc hoas
usa us uk eu uae nyc la sf dc nj ny ca tx fl wa nc ga az co il ma pa oh mi uk gta bc on nsw
tv hd uhd 4k 8k pc ios os wifi usb gps app apps vr ar xr iot gpu cpu ram ssd llm llms gpt ml nft nfts
btc eth qr id ip sdk ui ux js css html sql aws gcp
instagram ig tiktok youtube yt linkedin facebook fb threads pinterest reddit x twitter whatsapp
snapchat google gmail chatgpt claude gemini openai anthropic iphone ipad android macbook mac zoom
slack excel outlook zillow
sec finra fdic fda ftc fcc cfpb doj fbi cia nsa epa osha hhs dol sba nasdaq nyse cboe cme
kpmg pwc deloitte ey bcg hsbc ubs ibm sap amd bbc cnn cnbc nbc abc cbs espn hbo
""".split())
# Common words a transcript may put in capitals for emphasis ("NO", "STOP"): never a brand name.
COMMON = set("""
no so go do we me my he be by us or an at on in to up of if is it as yes now new top big best free win
wow stop look this that what when why how who you your our all one two ten get got see the and but not
just more most less real true easy fast huge done love hate need want must never ever only
""".split())


def norm(t):
    return re.sub(r"[^a-z0-9']", "", t.lower().replace("’", "'"))


def base(t):
    return norm(POSS.sub("", t))


def shaped(t):
    """an acronym (2-6 capitals, no lower case) or CamelCase word (AcmeCloud), by its own spelling;
    never a lower-case-first word (iPhone, iOS) or a Mc/Mac/O'/De/Le name (McKenzie)"""
    b = POSS.sub("", t)
    if not b[:1].isupper() or NAME_PREFIX.match(b):
        return False
    letters = re.sub(r"[^A-Za-z]", "", b)
    if 3 <= len(letters) <= 6 and letters.isupper():
        return not VOWEL.search(letters)   # an acronym cannot be read as a word; INSANE, ANNA, BOOM can
    m = re.fullmatch(r"([A-Z][a-z]+)(?:[A-Z][a-z0-9]*)+", b)
    return bool(m) and len(m.group(1)) >= 3   # AcmeCloud; not the names JoAnn, DeShawn


def plain(v):
    return html.unescape(TAG.sub(" ", v))


def stop(msg):
    print("takeover brand check: " + msg, file=sys.stderr)
    sys.exit(1)


def order_brand():
    cta, brief = {}, {}
    try:
        if os.path.isfile("inputs/cta/cta.json"):
            cta = json.load(open("inputs/cta/cta.json"))
        if os.path.isfile("brief.json"):
            brief = json.load(open("brief.json"))
    except ValueError as exc:
        stop("inputs/cta/cta.json or brief.json is not valid JSON (%s)" % exc)
    if not os.path.isfile("brief.json") and not cta:
        stop("no order brand: pass BRAND, or run in the step workdir with brief.json")
    b = brief.get("brand") if isinstance(brief, dict) else None
    b = b if isinstance(b, dict) else {}
    return str((cta.get("brandName") if isinstance(cta, dict) else "") or b.get("name") or "").strip()


def transcript(words):
    """the transcript's plain tokens, the brand-like names it speaks, and its spelled-out letter runs"""
    toks, raw, stops, names, letters = [], [], [], set(), []
    for w in words:
        t = str(w.get("text", w.get("w", w.get("word", "")))) if isinstance(w, dict) else str(w)
        for m in TOKEN.finditer(t):
            toks.append(norm(m.group(0)))
            raw.append(m.group(0))
            stops.append(bool(re.match(r"\s*[.!?,;:…]", t[m.end():])))   # punctuation ends a run
    caps = [bool(re.search(r"[A-Z]", r)) and not re.search(r"[a-z]", r) and len(r) > 1 for r in raw]
    plainly = {b for r, b in zip(raw, toks) if not r.isupper()}
    for k, r in enumerate(raw):
        if not shaped(r):
            continue
        # an all-caps run of 2+ words ("NYC TEAM", "SO GOOD") is emphasis, and a word also said in
        # lower case is an ordinary word: neither is a name
        if caps[k] and ((k and caps[k - 1] and not stops[k - 1]) or (k + 1 < len(raw) and caps[k + 1] and not stops[k])
                        or base(r) in plainly):
            continue
        if base(r) not in COMMON:
            names.add(base(r))
    run = []
    for t in toks + [""]:   # "C F W" spoken letter by letter: every 3+ letter run is a name
        if len(t) == 1 and t.isalpha() and t not in ("a", "i"):
            run.append(t)
            continue
        for i in range(len(run)):
            for j in range(i + 3, len(run) + 1):
                letters.append("".join(run[i:j]))
        run = []
    return toks, names, set(letters)


def all_caps(value):
    letters = re.sub(r"[^A-Za-z]", "", plain(value))
    return bool(letters) and letters.isupper()


def foreign(value, names, spelled, own):
    """the foreign names in this line: a spoken name written as an acronym / CamelCase word (or in an
    all-caps word), or a spelled-out letter run ("C F W") written as an acronym"""
    out = []
    for m in TOKEN.finditer(plain(value)):
        tok, b = m.group(0), base(m.group(0))
        if not b or b in own or b in GENERIC or b in COMMON or not re.search(r"[a-z]", b):
            continue
        bare = POSS.sub("", tok)
        if not bare[:1].isupper() or NAME_PREFIX.match(bare):
            continue
        upper = re.sub(r"[^A-Za-z]", "", bare).isupper()
        if (b in names and (upper or shaped(bare))) or (b in spelled and upper and len(b) >= 3 and not VOWEL.search(b)):
            out.append(tok)
    return out


def quoted(value, said, hits):
    toks = [t for t in (norm(t) for t in TOKEN.findall(plain(value))) if t]
    if len(toks) < MIN_QUOTE or 2 * len(hits) > len(toks):
        return False
    return (" " + " ".join(toks) + " ") in (" " + " ".join(said) + " ")


def fix_text(seg, names_hit, brand, caps):
    hit = {base(t) for t in names_hit}
    toks = list(TOKEN.finditer(seg))
    out, pos, i = [], 0, 0
    while i < len(toks):
        m = toks[i]
        if base(m.group(0)) not in hit:
            i += 1
            continue
        j = i  # a run of adjacent names ("Acme Labs") is one name
        while j + 1 < len(toks) and base(toks[j + 1].group(0)) in hit and seg[toks[j].end():toks[j + 1].start()].strip() == "":
            j += 1
        poss = POSS.search(toks[j].group(0))
        out.append(seg[pos:m.start()])
        pos = toks[j].end()
        if brand:
            out.append((brand.upper() if caps else brand) + (poss.group(0) if poss else ""))
        else:
            # drop the name and the space after it (or before it at the end)
            if seg[pos:pos + 1].isspace():
                pos += 1
            elif out and out[-1][-1:].isspace():
                out[-1] = out[-1][:-1]
        i = j + 1
    out.append(seg[pos:])
    return "".join(out)


def fix_value(value, names_hit, brand, is_html):
    caps = all_caps(value)
    if not is_html:
        return re.sub(r"\s{2,}", " ", fix_text(value, names_hit, brand, caps)).strip()
    hit = {base(t) for t in names_hit}
    parts = []
    for p in TAG.split(value):
        if TAG.fullmatch(p):
            parts.append(p)
            continue
        text = html.unescape(p)   # tokenise the text as shown (XQZ&nbsp;writes is XQZ + writes)
        if not any(base(t) in hit for t in TOKEN.findall(text)):
            parts.append(p)
            continue
        parts.append(html.escape(fix_text(text, names_hit, brand, caps), quote=False).replace("\xa0", "&nbsp;"))
    new = re.sub(r"<span[^>]*>\s*</span>", "", "".join(parts))
    return re.sub(r"[ \t]{2,}", " ", new).strip()


def problems(plan, said, names, spelled, own):
    bad = []
    for i, tk in enumerate(plan.get("takeovers") or []):
        fill = tk.get("fill") if isinstance(tk, dict) else None
        if not isinstance(fill, dict):
            continue
        skip = SKIP.get(tk.get("template"), set())
        for key, v in fill.items():
            if key in skip or not isinstance(v, str):
                continue
            hits = foreign(v, names, spelled, own)
            if hits and not quoted(v, said, hits):
                bad.append((i, key, v, hits))
    return bad


def main(argv):
    check = argv[:1] == ["--check"]
    args = argv[1:] if check else argv
    if len(args) not in (2, 3):
        stop("usage: takeover_brand.py [--check] PLAN.json WORDS.json [BRAND]")
    path, wpath = args[0], args[1]
    brand = args[2].strip() if len(args) == 3 else order_brand()
    for p in (path, wpath):
        if not os.path.isfile(p):
            stop("file not found: %s" % p)
    try:
        plan, words = json.load(open(path)), json.load(open(wpath))
    except ValueError as exc:
        stop("not valid JSON: %s" % exc)
    if isinstance(words, dict):
        words = words.get("words") or []
    if not isinstance(plan, dict) or not isinstance(words, list):
        stop("plan must be a JSON object and words a JSON list")
    if not any(str(w.get("text", w.get("w", w.get("word", "")))).strip() if isinstance(w, dict) else str(w).strip() for w in words):
        stop("%s holds no words to compare the takeovers with" % wpath)
    said, names, spelled = transcript(words)
    own = {base(t) for t in TOKEN.findall(brand)}
    bad = problems(plan, said, names, spelled, own)
    if check:
        for i, key, v, hits in bad:
            print("takeover brand check: takeover %d %s %r names %s, not the order brand %r, and is not a word-for-word "
                  "quote of the speech - quote the speech or use the order brand"
                  % (i + 1, key, v, "/".join(hits), brand or "(none)"), file=sys.stderr)
        sys.exit(1 if bad else 0)
    for i, key, v, hits in bad:
        tk = plan["takeovers"][i]
        new = fix_value(v, hits, brand, key in HTML_KEYS)
        if not re.search(r"[A-Za-z0-9]", plain(new)):
            stop("takeover %d %s %r is only a foreign name; rewrite it from the speech" % (i + 1, key, v))
        tk["fill"][key] = new
        print("[plan] takeover %d %s: %r -> %r (names %s; order brand %r)" % (i + 1, key, v, new, "/".join(hits), brand or "(none)"))
    if bad:
        json.dump(plan, open(path, "w"), indent=2)
    else:
        print("[plan] takeover brand: no foreign brand names, plan unchanged")
    left = problems(plan, said, names, spelled, own)
    for i, key, v, hits in left:
        print("takeover brand check: takeover %d %s %r still names %s" % (i + 1, key, v, "/".join(hits)), file=sys.stderr)
    sys.exit(1 if left else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
