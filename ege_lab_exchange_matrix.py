"""Conservative aqueous ion-exchange coverage for the EGE BLIZKO laboratory.

Only explicitly mapped aqueous species participate. The matrix *never* assumes
that two salts react just because their ions can be permuted. Conditions for a
real reaction are precipitation, release of a gas, or neutralisation to water.

Known hydrolysis and redox exceptions are delegated to their reviewed, explicit
reactions. This module does not claim to model every concentration or excess
case; it provides EGE-level outcomes for ordinary aqueous conditions.
"""
from __future__ import annotations

from math import gcd

SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

# (display formula, electric charge, chromatic aqueous cation)
CATIONS = {
    "li": ("Li", 1, "#f8fbff"), "na": ("Na", 1, "#f8fbff"),
    "k": ("K", 1, "#f8fbff"), "nh4": ("NH₄", 1, "#f8fbff"),
    "ag": ("Ag", 1, "#f8fbff"), "ca": ("Ca", 2, "#f8fbff"),
    "ba": ("Ba", 2, "#f8fbff"), "sr": ("Sr", 2, "#f8fbff"),
    "mg": ("Mg", 2, "#f8fbff"), "zn": ("Zn", 2, "#f8fbff"),
    "fe2": ("Fe", 2, "#c8e5c8"), "cu2": ("Cu", 2, "#42baf5"),
    "pb": ("Pb", 2, "#f8fbff"), "al": ("Al", 3, "#f8fbff"),
    "fe3": ("Fe", 3, "#d99d2b"), "cr3": ("Cr", 3, "#759b83"),
}
# (display formula, magnitude of anion charge)
ANIONS = {
    "cl": ("Cl", 1), "br": ("Br", 1), "i": ("I", 1),
    "no3": ("NO₃", 1), "f": ("F", 1),
    "so4": ("SO₄", 2), "co3": ("CO₃", 2),
    "so3": ("SO₃", 2), "s": ("S", 2),
    "sio3": ("SiO₃", 2), "cro4": ("CrO₄", 2),
    "po4": ("PO₄", 3),
}
# Only salts whose catalogue entries explicitly denote a soluble aqueous form.
# The keys are exact IDs from ege_lab_substances.REAGENTS.
AQUEOUS_SALTS = {
    "li": {"br":"libr","no3":"lino3","so4":"li2so4"},
    "na": {"cl":"nacl","br":"nabr","i":"nai","f":"naf","no3":"nano3",
           "so4":"na2so4","co3":"na2co3","so3":"na2so3","s":"na2s",
           "po4":"na3po4","sio3":"na2sio3","cro4":"na2cro4"},
    "k": {"cl":"kcl","br":"kbr","i":"ki","f":"kf","no3":"kno3",
          "so4":"k2so4","co3":"k2co3","so3":"k2so3","s":"k2s",
          "po4":"k3po4","sio3":"k2sio3","cro4":"k2cro4"},
    "nh4": {"cl":"nh4cl","no3":"nh4no3","so4":"nh42so4","co3":"nh42co3"},
    "ca": {"cl":"cacl2","br":"cabr2","i":"cai2","no3":"cano3"},
    "ba": {"cl":"bacl2","br":"babr2","no3":"bano3"},
    "sr": {"cl":"srcl2"},
    "mg": {"cl":"mgcl2","no3":"mgno3","so4":"mgso4"},
    "zn": {"cl":"zncl2","br":"znbr2","no3":"znno3","so4":"znso4"},
    "fe2": {"cl":"fecl2","no3":"feno3_2","so4":"feso4"},
    "cu2": {"cl":"cucl2","br":"cubr2","no3":"cuno3","so4":"cuso4","f":"cuf2"},
    "pb": {"no3":"pbno3"},
    "al": {"cl":"alcl3","br":"albr3","i":"ali3","no3":"alno3","so4":"al2so43"},
    "fe3": {"cl":"fecl3","br":"febr3","no3":"feno3_3","so4":"fe2so43"},
    "cr3": {"cl":"crcl3","no3":"crno3_3","so4":"cr2so43"},
    "ag": {"no3":"agno3","f":"agf"},
}
# pH-dependent reagents, aqueous. No concentration-dependent chemical guess.
AQUEOUS_HYDROXIDES = {
    "naoh":"na","koh":"k","lioh":"li",
    "caoh2":"ca","baoh2":"ba","sroh2":"sr",
}
# Acid contributes the indicated anion, and exactly as many protons as its charge.
# Nitric acid is used only in neutralisation and carbonate decomposition;
# its oxidising interaction with S(−II), SO₃²⁻ or halides is NOT guessed.
AQUEOUS_ACIDS = {
    "hcl":"cl","hbr":"br","hi":"i","hno3":"no3",
    "h2so4":"so4","hf":"f",
}

# Precipitation rules for ambient aqueous mixtures.
# Source: curated, conservative classroom solubility rules. Form-specific
# exceptions such as AgOH, Fe(III) carbonates and basic Cu carbonates bypass
# this generic lookup and require explicit reaction records.
INSOLUBLE = {
    "cl": {"ag","pb"}, "br": {"ag","pb"}, "i": {"ag","pb"},
    "so4": {"ba","sr","pb"},
    "co3": {"ca","ba","sr","mg","zn","fe2","pb","ag"},
    "so3": {"ca","ba","sr","mg","zn","fe2","pb"},
    "s": {"zn","fe2","cu2","pb","ag"},
    "po4": {"ca","ba","sr","mg","zn","fe2","fe3","cu2","pb","ag","al","cr3"},
    "sio3": {"ca","ba","sr","mg","zn","fe2","cu2","pb"},
    "cro4": {"ba","sr","pb","ag"},
    "f": {"ca","ba","sr","mg","pb"},
    "no3": set(),
}
INSOLUBLE_HYDROXIDES = {
    "mg", "zn", "fe2", "fe3", "cu2", "pb", "al", "cr3",
}
# Not chemically honest to approximate these with an ordinary salt-exchange
# equation: oxidation/reduction, basic salt or joint hydrolysis takes priority.
EXCEPTIONAL_CATIONS = {"al","fe3","cr3"}
EXCEPTIONAL_ANIONS = {"co3","so3","s"}
PRECIP_COLORS = {
    ("ag","cl"):"#ffffff", ("ag","br"):"#e9d79a",
    ("ag","i"):"#f0d64a", ("ag","co3"):"#e9d78b",
    ("ag","po4"):"#e5c92d", ("ag","cro4"):"#b84e31",
    ("pb","i"):"#e9d136", ("pb","cro4"):"#f1c934",
    ("ba","cro4"):"#efd636",
    ("fe2","co3"):"#a8b18b", ("fe2","s"):"#232323",
    ("fe3","po4"):"#d5b070", ("cu2","s"):"#151515",
    ("cu2","po4"):"#65a9d2",
    ("zn","s"):"#ffffff", ("pb","s"):"#151515",
    ("ag","s"):"#171717",
    ("fe2","oh"):"#89b98e", ("fe3","oh"):"#9a4a2b",
    ("cu2","oh"):"#42baf5", ("cr3","oh"):"#6e966f",
}

def _numbers(cat, anion):
    cp = CATIONS[cat][1]
    ap = ANIONS[anion][1] if anion != "oh" else 1
    g = gcd(cp,ap)
    return ap//g, cp//g

def _unit(text, count):
    if count == 1:
        return text
    if text == "OH" or len(text) > 2 or any(d in text for d in "₀₁₂₃₄₅₆₇₈₉"):
        return "(" + text + ")" + str(count).translate(SUB)
    return text + str(count).translate(SUB)

def _formula(cat, anion):
    c=CATIONS[cat][0]
    a=ANIONS[anion][0] if anion!="oh" else "OH"
    m,n=_numbers(cat,anion)
    # Conventional plain formulas: Na₂SO₄, Fe(OH)₃, (NH₄)₂CO₃.
    return _unit(c,m)+_unit(a,n)

def _balance_exchange(cat1, an1, cat2, an2):
    """Return coefficients of M1X, M2Y, M1Y, M2X, using ion-unit conservation."""
    m1,n1=_numbers(cat1,an1)
    m2,n2=_numbers(cat2,an2)
    m3,n3=_numbers(cat1,an2)
    m4,n4=_numbers(cat2,an1)
    for a in range(1,73):
        if a*m1 % m3 or a*n1 % n4:continue
        c=a*m1//m3
        d=a*n1//n4
        if c*n3 % n2:continue
        b=c*n3//n2
        if b*m2 == d*m4:
            vals=[a,b,c,d]
            common=gcd(gcd(a,b),gcd(c,d))
            return tuple(x//common for x in vals)
    raise ValueError(f"Exchange stoichiometry failed: {cat1},{an1},{cat2},{an2}")

def _prefix(n,formula):
    return (str(n) if n>1 else "")+formula

def _solution_color(remaining):
    for cat in ("cu2","fe3","cr3","fe2"):
        if cat in remaining:return CATIONS[cat][2]
    return "#f8fbff"

def _special_pair(cat1,an1,cat2,an2):
    # Skip both directions of these redox and hydrolysis combinations.
    for cat,anion in ((cat1,an2),(cat2,an1)):
        if cat in EXCEPTIONAL_CATIONS and anion in EXCEPTIONAL_ANIONS:return True
        if cat == "cu2" and anion in {"i","co3","so3"}:return True
        if cat == "fe3" and anion == "i":return True
    return False

def _make_record(a,b,eq,kind,sign,sol="#f8fbff",ppt="",gas="",condition=""):
    return {
        "a":a,"b":b,"eq":eq,"t":kind,"sign":sign,"sol":sol,
        "ppt":ppt,"gas":gas,"heat":False,"excess":"","condition":condition,
    }

def generate_exchange_reactions(known_reagents, existing_pairs=()):
    """Build conservative, balanced aqueous reaction outcomes.

    Explicit catalogue reactions always have precedence. This matrix only
    adds previously missing pairs; no duplicate competes with curated Fe/Cu,
    manganese/chromium, amphoteric-excess or hydrolysis pathways.
    """
    known=set(known_reagents)
    existing={tuple(sorted(p)) for p in existing_pairs}
    rows=[]
    def add(row):
        pair=tuple(sorted((row["a"],row["b"])))
        if pair in existing or row["a"] not in known or row["b"] not in known:return
        rows.append(row);existing.add(pair)

    salts=[]
    for cat,anions in AQUEOUS_SALTS.items():
        for anion,rid in anions.items():
            if rid in known:
                salts.append((rid,cat,anion))

    # Salt + salt. Only real precipitation; no "reaction" for all-soluble ions.
    for i,(a,ca,xa) in enumerate(salts):
        for b,cb,xb in salts[i+1:]:
            if ca==cb or xa==xb or _special_pair(ca,xa,cb,xb):continue
            precip=[(ca,xb),(cb,xa)]
            precip=[(c,x) for c,x in precip if c in INSOLUBLE.get(x,set())]
            if not precip:continue
            m,n,k,l=_balance_exchange(ca,xa,cb,xb)
            eq=(f"{_prefix(m,_formula(ca,xa))} + {_prefix(n,_formula(cb,xb))} → "
                f"{_prefix(k,_formula(ca,xb))}{'↓' if (ca,xb) in precip else ''}"
                f" + {_prefix(l,_formula(cb,xa))}{'↓' if (cb,xa) in precip else ''}")
            sign="Образуется осадок "+", ".join(_formula(c,x) for c,x in precip)+"."
            ppt=PRECIP_COLORS.get(precip[0],"#ffffff")
            sol=_solution_color([cat for cat in (ca,cb) if all(cat!=c for c,x in precip)])
            add(_make_record(a,b,eq,"p",sign,sol,ppt,condition="Смешивание водных растворов"))

    # Strong aqueous acid + soluble hydroxide => salt + water.
    for acid,anion in AQUEOUS_ACIDS.items():
        for base,cat in AQUEOUS_HYDROXIDES.items():
            if acid not in known or base not in known:continue
            salt=_formula(cat,anion)
            num_cat,num_an=_numbers(cat,anion)
            water=num_cat*CATIONS[cat][1]
            eq=(f"{_prefix(num_an,_prefix(1,_acid_formula(anion)))} + "
                f"{_prefix(num_cat,_formula(cat,'oh'))} → {salt} + {_prefix(water,'H₂O')}")
            # _acid_formula returns H_x A; cat OH formula includes correct count.
            precip=cat in INSOLUBLE.get(anion,set())
            add(_make_record(acid,base,eq,"p" if precip else "n",
                "Образуется осадок "+salt+"." if precip else "Нейтрализация: образуется вода.",
                "#f8fbff",PRECIP_COLORS.get((cat,anion),"#ffffff") if precip else "",
                condition="Водные растворы, полная нейтрализация"))

    # Salt + soluble hydroxide. The driving force may be a metal hydroxide
    # OR a new insoluble salt (e.g. Ba(OH)₂ + Na₂SO₄ -> BaSO₄).
    # Silver forms oxide rather than an imaginary "AgOH" precipitate.
    for salt,cat,anion in salts:
        for base,bc in AQUEOUS_HYDROXIDES.items():
            if base not in known or cat==bc:continue
            if cat=="ag":
                if base not in {"naoh","koh"}:continue
                # 2AgNO₃ + 2NaOH -> Ag₂O + 2NaNO₃ + H₂O.
                if anion not in {"no3","f"}:continue
                source=_formula(cat,anion)
                product=_formula(bc,anion)
                eq=f"2{source} + 2{_formula(bc,'oh')} → Ag₂O↓ + 2{product} + H₂O"
                add(_make_record(salt,base,eq,"p",
                    "Образуется бурый осадок Ag₂O (AgOH неустойчив).",
                    "#f8fbff","#7c5536",condition="Водные растворы"))
                continue
            if cat=="nh4":
                if bc not in {"na","k","li"}:continue
                # One NH₄⁺ consumes one OH⁻ to produce NH₃ and H₂O.
                num_c,num_a=_numbers(cat,anion)
                prod_cat,prod_an=_numbers(bc,anion)
                for m in range(1,19):
                    if m*num_c%prod_cat==0:break
                n_prod=m*num_c//prod_cat
                n_base=n_prod*prod_an
                if n_base!=m*num_c:raise ValueError("NH4 hydroxide balance")
                eq=(f"{_prefix(m,_formula(cat,anion))} + {_prefix(n_base,_formula(bc,'oh'))}"
                    f" → {_prefix(n_prod,_formula(bc,anion))} + {_prefix(n_base,'NH₃')}↑"
                    f" + {_prefix(n_base,'H₂O')}")
                add(_make_record(salt,base,eq,"g",
                    "Выделяется аммиак NH₃ с характерным резким запахом.",
                    "#f8fbff","","NH₃",condition="Нагревание ускоряет выделение NH₃"))
                continue
            ppts=[]
            if cat in INSOLUBLE_HYDROXIDES:ppts.append((cat,"oh"))
            if bc in INSOLUBLE.get(anion,set()):ppts.append((bc,anion))
            if not ppts:continue
            if _special_pair(cat,anion,bc,"oh"):continue
            m,n,k,l=_balance_exchange(cat,anion,bc,"oh")
            c_prod=_formula(cat,"oh")
            s_prod=_formula(bc,anion)
            eq=(f"{_prefix(m,_formula(cat,anion))} + {_prefix(n,_formula(bc,'oh'))} → "
                f"{_prefix(k,c_prod)}{'↓' if (cat,'oh') in ppts else ''}"
                f" + {_prefix(l,s_prod)}{'↓' if (bc,anion) in ppts else ''}")
            add(_make_record(salt,base,eq,"p",
                "Образуется осадок "+", ".join(_formula(c,x) for c,x in ppts)+".",
                "#f8fbff",PRECIP_COLORS.get(ppts[0],"#ffffff"),
                condition="Без избытка щёлочи; амфотерные гидроксиды могут растворяться при избытке"))

    # Acid + soluble carbonate/sulfite/sulfide; weak volatile acid collapses.
    gas_rules={
        "co3": ("CO₂","H₂O","hcl hbr hno3 h2so4"),
        "so3": ("SO₂","H₂O","hcl h2so4"),
        "s": ("H₂S","","hcl h2so4"),
    }
    for salt,cat,anion in salts:
        if anion not in gas_rules:continue
        gas,water,allowed=gas_rules[anion]
        for acid in allowed.split():
            if acid not in known:continue
            ax=AQUEOUS_ACIDS[acid]
            if cat in {"ag","cu2","fe3","al","cr3"}:continue
            # Existing explicit equations override; solve by charge ratios.
            cat_n,anion_n=_numbers(cat,anion)
            salt_cat_n,new_an_n=_numbers(cat,ax)
            x_acid=ANIONS[ax][1]
            for n_salt in range(1,37):
                if n_salt*cat_n % salt_cat_n:continue
                n_product=n_salt*cat_n//salt_cat_n
                n_acid=n_product*new_an_n
                if n_acid*x_acid != n_salt*anion_n*ANIONS[anion][1]:continue
                break
            else:raise ValueError(f"Unable to balance acidic salt: {cat}/{anion}/{ax}")
            common=gcd(gcd(n_salt,n_acid),gcd(n_product,n_salt*anion_n))
            n_salt//=common;n_acid//=common;n_product//=common
            n_gas=(n_salt*anion_n)
            prod=_formula(cat,ax)
            eq=(f"{_prefix(n_salt,_formula(cat,anion))} + {_prefix(n_acid,_acid_formula(ax))}"
                f" → {_prefix(n_product,prod)} + {_prefix(n_gas,gas)}↑")
            if water:eq+=f" + {_prefix(n_gas,water)}"
            add(_make_record(salt,acid,eq,"g","Выделяется газ "+gas+".",
                "#f8fbff","",gas,condition="Водные растворы; слабая летучая кислота разлагается"))
    return rows

def _acid_formula(anion):
    unit,charge=ANIONS[anion]
    h="H"+(str(charge).translate(SUB) if charge>1 else "")
    return h+unit
