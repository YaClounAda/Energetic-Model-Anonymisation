import base64
import hashlib
import io
import json
import os
import re
import time
import uuid
import xml.sax
import xml.sax.saxutils
import xml.sax.xmlreader
import zipfile
from collections import Counter

INPUT_XML = r"c:\Users\seban\Downloads\temp\input.xml"
OUTPUT_XML = r"c:\Users\seban\Downloads\temp\output.xml"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

SEARCHABLE_ENERGY_CLASSES = {
    "substation", "substationsld", "transmissionsld", "line", "aclinesegment",
    "plant", "cogenerationplant", "hydropowerplant", "reservoir",
    "subgeographicalregion", "geographicalregion", "hypergeoregion",
    "controlarea", "hostcontrolarea", "controlareaoperator",
    "areaofresponsibility", "operationalauthority",
}

LOCAL_ENERGY_CLASSES = SEARCHABLE_ENERGY_CLASSES | {
    "powertransformer", "powertransformerend", "ratiotapchanger",
    "aclineseriessection", "pole", "breaker", "disconnector",
    "grounddisconnector", "loadbreakswitch", "fuse", "recloser",
    "automaticrecloser", "jumper", "bay", "busbarsection", "voltagelevel",
    "surgearrester", "currenttransformer", "potentialtransformer",
    "wavetrap", "petersencoil", "seriescompensator", "linearshuntcompensator",
    "synchronousmachine", "thermalgeneratingunit", "hydrogeneratingunit",
    "nucleargeneratingunit", "nonconformload", "nonconformloadgroup",
    "servicelocation", "usagepoint", "meter", "asset", "protectionequipment",
    "foldernode", "weatherstation"
}

PERSON_CLASSES = {
    "person", "erpperson", "customer", "employee", "staff",
    "worker", "crewmember", "subscriber_fl", "abonent_fl",
}
ORG_CLASSES = {
    "organisation", "organization", "organisationrole", "company",
    "legalentity", "contractor", "subscriber_ul", "abonent_ul",
}

SYSTEM_CLASSES = {
    "basevoltage", "psrtype", "nametype", "measurementtype", "measurementvaluetype",
    "operationallimittype", "unitlabel", "documenttype", "valuetoalias", "valuealiasset",
    "rtdeventtype", "rtdeventtypeconfiguration", "djcategory", "djcategorytype",
    "shiftrole", "daytype", "season", "calendarmonth", "calendaryear", "calendarday",
}

SCRUB_NAME_CLASSES = {
    "terminal", "connectivitynode", "analog", "discrete", "remoteanalogvalue",
    "remotediscretevalue", "processedanalogvalue", "processeddiscretevalue",
    "operatordiscretevalue", "operatoranalogvalue", "calculatedanalogvalue",
    "calculateddiscretevalue", "copiedanalogvalue", "copieddiscretevalue",
    "remoteanalogsource", "remotediscretesource", "command", "remotecontrol",
}
EMAIL_TAGS = {"email", "e_mail", "mail", "userid"}
META_NAME_TAGS = {"psrtype.classname", "model.name", "nametype.name", "nametype.aliasname"}
PERSON_TAGS = {"fio", "fullname", "lastname", "firstname", "middlename"}
ORG_TAGS = {"orgname", "companyname", "legalname"}
NAME_TAGS = {"name", "identifiedobject.name", "naming.name", "name.name", "nameplate", "foldername"}
DIGIT_TAGS = {
    "inn", "kpp", "ogrn", "okpo", "snils", "passport", "passportnumber", "passportseries",
    "governmentid", "phone", "phonenumber", "telephone", "mobile", "mobilephone",
    "landlinephone", "localnumber", "tabnumber", "personnelnumber", "employeenumber",
    "account", "accountid", "accountnumber", "personalaccount", "contract", "contractnumber",
    "serialnumber", "inventorynumber", "invnum", "meteringpointcode", "ccscode", "address",
    "postalcode", "cadastralnumber",
}
UUID_TAGS = {"mrid", "mridstr", "fiasid", "fiasstreetid"}
ADDRESS_TAGS = {
    "addressgeneral", "streetdetail.name", "streetdetail.number",
    "buildingname", "towndetail.name", "stateorprovince", "country",
}
FREE_TEXT_TAGS = {"comment", "description", "identifiedobject.description", "text", "djrecordtext", "markertext"}

BINARY_TAGS = {
    "moniteldiagram.image", "aclinesegment.sections", "djcategory.allowedobjectsfilter",
    "blobstorage.image", "eventsound.sound", "markertype.diagramview",
    "markertype.additionalview", "djattributeset.xsd",
}
RAW_CURVE_TAGS = {"points"}
COORD_X_TAGS = {"positionpoint.xposition", "lon", "longitude"}
COORD_Y_TAGS = {"positionpoint.yposition", "lat", "latitude"}

# Атрибуты внутри вложенных XML (diagram.xml, sections), где реально могут быть названия/текст
INNER_TEXT_ATTRS = {"name", "text", "caption", "label", "title", "description", "tooltip", "comment"}
INNER_SKIP_NAME_ATTRS = {"nameplate", "typename", "fontname", "classname", "propertyname", "stylename", "layername"}

STOP_WORDS = {
    "object", "value", "diagram", "point", "layer", "style", "group", "table",
    "model", "image", "color", "width", "height", "level", "power", "limit",
    "state", "phase", "curve", "alarm", "event", "panel", "switch", "breaker",
    "station", "feeder", "busbar", "neutral", "default", "global", "common",
    "system", "center", "north", "south", "equivalents", "unknown", "other",
}

RE_ORG_FORM = re.compile(r'^(ООО|ПАО|ОАО|ЗАО|АО|ИП|ГУП|МУП|ФГУП|НКО|ТСЖ|СНТ)\b', re.I)
RE_QUOTED_ORG = re.compile(r'\b(ООО|ПАО|ОАО|ЗАО|АО|ГУП|МУП|ФГУП)\s+([«"]{1,2})([^»"]{2,80})([»"]{1,2})')
RE_FIO_FULL = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,}(?:вич|вна|ич|на))\b')
RE_FIO_SHORT = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ]\.\s?[А-ЯЁ]\.)')
RE_SNILS = re.compile(r'\b\d{3}-\d{3}-\d{3}[\s-]\d{2}\b')
RE_PASSPORT = re.compile(r'(?i)(\bпаспорт[^\d]{0,20}|\bсерия[^\d]{0,10})(\d{4}\s?\d{6})\b')
RE_VOLT_ONLY = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:кВ|kV)$", re.I)
RE_VOLT = re.compile(r"\b\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?\s*(?:кВ|kV)\b", re.I)
RE_PREFIX = re.compile(r"^(ПС|ТП|КТП|БКТП|ЗТП|РП|ВЛ|КЛ|ЛЭП|Фидер|Substation|Sub|Line)\b", re.I)
RE_NUM = re.compile(r"(?<!\d)\d+(?!\d)")
RE_TOK = re.compile(r"((?:kV|KV|кВ|КВ)(?=[A-ZА-ЯЁ])|[A-Za-zА-Яа-яЁё]+|\d+)")
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
RE_PHONE = re.compile(r"(?<![0-9A-Za-zА-Яа-яЁё\-])(?:\+7|8)[\s\-()]{0,2}\d{3}[\s\-()]{0,2}\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?![0-9A-Za-zА-Яа-яЁё\-])")
RE_INN_TXT = re.compile(r"(?i)(\bинн\s*[:№]?\s*)(\d{10}|\d{12})\b")
RE_URL = re.compile(r"https?://[^\s<>\"']+")
RE_UUID_ANY = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
RE_ENERGY_INLINE = re.compile(
    r"\b(?:ПС|ТП|КТП|БКТП|ЗТП|РП|ВЛ|КВЛ|КЛ|ЛЭП|Фидер)"
    r"(?:"
    r"(?:\s*[-]?\s*\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?\s*(?:кВ|kV))?"
    r"(?:\s*[«\"][^»\"]+[»\"]|\s+(?:[А-ЯЁ]\.\s*)?[А-ЯЁ][а-яёА-ЯЁ0-9\-]{2,})"
    r"|"
    r"\s*[-№#]\s*\d+(?:[/-]\d+)*(?!\s*(?:кВ|kV))"
    r")"
)
RE_POLE = re.compile(r"(?i)(\bоп\.?\s*|\bопора\s+)(\d+)([а-яёa-z]?)\b")
RE_XML_TEXT = re.compile(r"(?<=>)([^<]+)(?=<)")
RE_XML_NAMED_ATTR = re.compile(r'([\w:.-]+)="([^"]*)"')
RE_FEEDER = re.compile(r"(?i)(\bф\.?\s*|\bфидер\s*|\bfeeder\s+)(\d+)\b")

def norm_rdf_id(val: str) -> str:
    return val.strip().lstrip("#").lstrip("_").lower()


class AnonymizerEngine:
    def __init__(self, cfg: dict):
        lang_code = cfg["target_language"]
        self.lang = cfg["languages"][lang_code]
        self.secret = cfg["secret_key"].encode("utf-8")
        self.safe_domains = tuple(cfg.get("safe_url_domains", [])) + (
            "schemas.microsoft.com", "schemas.openxmlformats.org",
        )

        self.male = self.lang["male_names"]
        self.female = self.lang["female_names"]
        self.plants = self.lang["plants"]
        self.all_streets = [x[3] for x in self.male + self.female]

        self.known_entities: dict[str, str] = dict(self.lang.get("seed_orgs", {}))
        self.energy_map: dict[str, str] = {}
        self.used_energy: set[str] = set()
        self.trie: dict = {}
        self.binary_stats = Counter()
        self.binary_scrubbed = Counter()
        self.person_map: dict[str, str] = {}
        self.used_persons: set[str] = set()
        self.street_map: dict[str, str] = {}
        self.used_streets: set[str] = set()
        self.stem_map: dict[str, list[tuple[str, str]]] = {}

    def _hash_bytes(self, salt: str, value: str) -> bytes:
        return hashlib.blake2b(f"{salt}:{value}".encode("utf-8"), digest_size=16, key=self.secret).digest()

    def _hash_int(self, salt: str, value: str) -> int:
        return int.from_bytes(self._hash_bytes(salt, value)[:8], "big")

    def fake_uuid_or_id(self, raw_id: str) -> str:
        s = raw_id.strip()
        if s.startswith("#_"):
            prefix = "#_"
        elif s.startswith("#"):
            prefix = "#"
        elif s.startswith("urn:uuid:"):
            prefix = "urn:uuid:"
        elif s.startswith("_"):
            prefix = "_"
        else:
            prefix = ""
        clean = s[len(prefix):]
        # Хешируем в нижнем регистре, чтобы UUID из diagram.xml и основного XML всегда совпадали
        b = bytearray(self._hash_bytes("id", clean.lower()))
        b[6] = (b[6] & 0x0F) | 0x40
        b[8] = (b[8] & 0x3F) | 0x80
        uid = str(uuid.UUID(bytes=bytes(b)))
        if clean.isupper():
            uid = uid.upper()
        return f"{prefix}{uid}"

    def fake_digits(self, value: str, category: str) -> str:
        digits = [c for c in value if c.isdigit()]
        if not digits:
            return value
        h = str(self._hash_int(category, value.strip()))
        while len(h) < len(digits):
            h += str(self._hash_int(category + "_x", h))
        it = iter(h)
        out = []
        first = True
        for c in value:
            if c.isdigit():
                d = next(it)
                if first and len(digits) > 1 and d == "0":
                    d = "7"
                first = False
                out.append(d)
            else:
                out.append(c)
        return "".join(out)

    def fake_email(self, raw: str) -> str:
        h = self._hash_int("mail", raw.strip().lower())
        pool = self.male + self.female
        p1, p2 = pool[h % len(pool)][4], pool[(h // 11) % len(pool)][4]
        return f"{p1}.{p2}.{h % 10000:04d}@example.org"

    def fake_url(self, url: str) -> str:
        if any(d in url for d in self.safe_domains):
            return url
        h = self._hash_bytes("url", url).hex()[:12]
        return f"https://synthetic.local/ref/{h}"

    def fake_person(self, raw: str, remember: bool = False, part: str = "full") -> str:
        clean = " ".join(raw.split())
        if clean not in self.person_map:
            is_f = clean.lower().endswith(("а", "я")) and not clean.lower().startswith(("илья", "никита"))
            pool = self.female if is_f else self.male
            full = ""
            for attempt in range(8):
                h = self._hash_int(f"person:{attempt}", clean)
                s = pool[(h // 7) % len(pool)][1]
                f = pool[h % len(pool)][0]
                p = pool[(h // 13) % len(pool)][2]
                cand = f"{s} {f} {p}" if attempt < 5 else f"{s}-{h % 100000:05d} {f} {p}"
                if cand not in self.used_persons or attempt == 7:
                    full = cand
                    break
            self.used_persons.add(full)
            self.person_map[clean] = full

        res = self.person_map[clean]
        if remember and len(clean) >= 5:
            self.known_entities[clean] = res
        parts = res.split()
        if part == "lastname":
            return parts[0]
        if part == "firstname":
            return parts[1]
        if part == "middlename":
            return parts[2]
        return res

    def _make_adj(self, key: str, kind: str, attempt: int) -> str:
        end = self.lang["adj_endings"].get(kind, "")
        n = len(self.plants)
        if attempt < n:
            idx = (self._hash_int(f"pl:{kind}", key) + attempt) % n
            return self.plants[idx] + end
        i1 = self._hash_int(f"pl1:{kind}", f"{key}:{attempt}") % n
        i2 = self._hash_int(f"pl2:{kind}", f"{key}:{attempt}") % n
        if i1 == i2:
            i2 = (i2 + 1) % n
        sep = "о-" if end else "-"
        return f"{self.plants[i1]}{sep}{self.plants[i2]}{end}"

    def fake_plant_name(self, raw: str, is_org: bool = False, remember: bool = False, stateful: bool = True) -> str:
        clean = " ".join(raw.split())
        if not clean:
            return raw
        norm_key = re.sub(r"\s*[-–—№#]\s*", "-", clean).lower()

        # Stateless-ветка для миллионов мелких железок (Pole, Breaker, Bay): 0 байт в RAM, O(1) скорость
        if not stateful and not is_org:
            h = self._hash_int("eq_fast", norm_key)
            pm = RE_PREFIX.match(clean)
            vm = RE_VOLT.search(clean)
            pref = self.lang["prefixes"].get(pm.group(1).lower() if pm else "", self.lang["prefixes"]["default"])
            volt = f" {vm.group(0)}" if vm else ""
            adj = self._make_adj(norm_key, "energy", 0)
            return f'{pref}{volt} "{adj}-{h % 1000000:06d}"'

        cache_key = f"{'O' if is_org else 'E'}:{norm_key}"
        if cache_key in self.energy_map:
            return self.energy_map[cache_key]

        if is_org:
            res = ""
            for attempt in range(8):
                adj = self._make_adj(norm_key, "org", attempt)
                tag = "" if attempt < 5 else f"-{self._hash_int(f'orgtag:{attempt}', norm_key) % 100000:05d}"
                cand = f'{self.lang["org_prefix"]} "{adj}{tag}"'
                if cand not in self.used_energy or attempt == 7:
                    res = cand
                    break
            self.used_energy.add(res)
            self.energy_map[cache_key] = res
            if remember and len(clean) >= 5:
                self.known_entities[clean] = res
            return res

        pm = RE_PREFIX.match(clean)
        vm = RE_VOLT.search(clean)
        pref = self.lang["prefixes"].get(pm.group(1).lower() if pm else "", self.lang["prefixes"]["default"])
        volt = f" {vm.group(0)}" if vm else ""
        wo_pref_volt = RE_VOLT.sub("", clean[pm.end():] if pm else clean).strip()
        num_m = RE_NUM.search(wo_pref_volt)
        orig_num = num_m.group(0) if num_m else ""
        proper = RE_NUM.sub("", wo_pref_volt).strip(" -№#\"'«».,()")

        res, label = "", ""
        for attempt in range(8):
            adj = self._make_adj(norm_key, "energy", attempt)
            if orig_num:
                fake_num = self.fake_digits(orig_num, f"objnum:{attempt}:{norm_key}")
                tag = "" if attempt < 5 else f"-{self._hash_int(f'etag:{attempt}', norm_key) % 10000:04d}"
                label = f"{adj}-{fake_num}{tag}"
                cand = f'{pref}-{fake_num}{volt} "{adj}{tag}"'
            else:
                tag = "" if attempt == 0 else (f"-{attempt}" if attempt < 5 else f"-{self._hash_int(f'etag:{attempt}', norm_key) % 100000:05d}")
                label = f"{adj}{tag}"
                cand = f'{pref}{volt} "{label}"'
            if cand not in self.used_energy or attempt == 7:
                res = cand
                break

        self.used_energy.add(res)
        self.energy_map[cache_key] = res
        if remember and len(clean) >= 5 and not RE_VOLT_ONLY.match(clean):
            self.known_entities[clean] = res
            if len(proper) >= 5 and proper.lower() not in STOP_WORDS and not proper.isdigit():
                self.known_entities.setdefault(proper, label)
        return res

    def fake_coord(self, raw: str, axis: str) -> str:
        try:
            val = float(raw.strip().replace(",", "."))
        except ValueError:
            return raw
        # Глобальный детерминированный сдвиг всей сетки — длины ЛЭП и геометрия сохраняются
        shift = ((self._hash_int("coord_shift", axis) % 10000) / 10000.0 - 0.5) * 8.0
        return f"{val + shift:.6f}"

    def fake_address(self, raw: str, tag: str, remember: bool = False) -> str:
        clean = " ".join(raw.split())
        if not clean:
            return raw
        h = self._hash_int("addr", clean)
        house = (h % 150) + 1
        sp = f'{self.lang["street_prefix"]} ' if self.lang["street_prefix"] else ""
        hp = self.lang["house_prefix"]

        if "country" in tag:
            return self.lang["country"]
        if "towndetail" in tag or "stateorprovince" in tag:
            if remember:
                # Запоминаем реальные города/районы (типа Koulikoro), чтобы вычищать их в сигналах и схемах
                for w in RE_TOK.findall(clean):
                    if len(w) >= 6 and w.lower() not in STOP_WORDS and w.lower() != "district":
                        self.known_entities.setdefault(w, self._make_adj(w.lower(), "energy", 0))
            return self.lang["city"]
        if "number" in tag or "building" in tag:
            return f"{hp} {house}"

        if clean in self.street_map:
            street = self.street_map[clean]
        elif len(self.street_map) >= 100_000:
            # Предохранитель по RAM для огромных файлов: генерим stateless
            street = f"{sp}{self.all_streets[h % len(self.all_streets)]}-{h % 100000:05d}"
        else:
            street = ""
            for attempt in range(8):
                ha = self._hash_int(f"street:{attempt}", clean)
                suffix = f"{(ha // 17) % 100}" if attempt < 5 else f"{ha % 100000:05d}"
                cand = f"{sp}{self.all_streets[ha % len(self.all_streets)]}-{suffix}"
                if cand not in self.used_streets or attempt == 7:
                    street = cand
                    break
            self.used_streets.add(street)
            self.street_map[clean] = street

        return street if "streetdetail.name" in tag else f'{self.lang["city"]}, {street}, {hp} {house}'

    def compile_scrubber(self):
        self.trie = {}
        self.stem_map = {}
        for k, v in self.known_entities.items():
            clean_k = k.strip(" \"'«»")
            if len(clean_k) < 4 or clean_k.lower() in STOP_WORDS:
                continue
            toks = [t.lower() for t in RE_TOK.split(clean_k) if t]
            if not toks:
                continue
            node = self.trie
            for t in toks:
                node = node.setdefault(t, {})
            node[None] = v
            # Индекс по первым 6 буквам для отлова склонений/суффиксов (Koulikorosaya -> Koulikoro)
            if len(toks) == 1 and len(toks[0]) >= 6 and toks[0].isalpha():
                self.stem_map.setdefault(toks[0][:6], []).append((toks[0], v))
        for lst in self.stem_map.values():
            lst.sort(key=lambda x: -len(x[0]))

    def _scrub_unmatched(self, chunk: str) -> str:
        if not chunk or not chunk.strip():
            return chunk
        chunk = RE_ENERGY_INLINE.sub(lambda m: self.fake_plant_name(m.group(0), is_org=False, remember=False), chunk)
        chunk = RE_POLE.sub(lambda m: f"{m.group(1)}{self.fake_digits(m.group(2), 'pole')}{m.group(3)}", chunk)
        chunk = RE_FEEDER.sub(lambda m: f"{m.group(1)}{self.fake_digits(m.group(2), 'feeder')}", chunk)
        chunk = RE_QUOTED_ORG.sub(
            lambda m: f"{m.group(1)} {m.group(2)}{self._make_adj(m.group(3).lower(), 'org', 0)}{m.group(4)}",
            chunk,
        )
        chunk = RE_FIO_FULL.sub(lambda m: self.fake_person(m.group(0), remember=False), chunk)
        chunk = RE_FIO_SHORT.sub(
            lambda m: (lambda p: f"{p[0]} {p[1][0]}.{p[2][0]}.")(self.fake_person(m.group(0)).split()),
            chunk,
        )
        chunk = RE_SNILS.sub(lambda m: self.fake_digits(m.group(0), "snils"), chunk)
        chunk = RE_PASSPORT.sub(lambda m: m.group(1) + self.fake_digits(m.group(2), "passport"), chunk)
        if "@" in chunk:
            chunk = RE_EMAIL.sub(lambda m: self.fake_email(m.group(0)), chunk)
        if "http" in chunk:
            chunk = RE_URL.sub(lambda m: self.fake_url(m.group(0)), chunk)
        chunk = RE_PHONE.sub(lambda m: self.fake_digits(m.group(0), "phone"), chunk)
        chunk = RE_INN_TXT.sub(lambda m: m.group(1) + self.fake_digits(m.group(2), "inn"), chunk)
        return chunk

    def scrub_free_text(self, text: str) -> str:
        if not text or not text.strip():
            return text
        if not self.trie:
            return self._scrub_unmatched(text)
        parts = [p for p in RE_TOK.split(text) if p]
        out, raw_buf = [], []
        i, n = 0, len(parts)
        while i < n:
            low = parts[i].lower()
            node = self.trie.get(low)
            best_val, best_end = None, i + 1
            if node is not None:
                best_val = node.get(None)
                j = i + 1
                while j < n:
                    node = node.get(parts[j].lower())
                    if node is None:
                        break
                    j += 1
                    if None in node:
                        best_val = node[None]
                        best_end = j
            elif len(low) >= 7 and low.isalpha():
                # Ловим склонения вроде Koulikorosaya по совпадению основы >= 6 букв
                for stem, rep in self.stem_map.get(low[:6], ()):
                    if low.startswith(stem):
                        best_val = rep
                        break
            if best_val is not None:
                if raw_buf:
                    out.append(self._scrub_unmatched("".join(raw_buf)))
                    raw_buf.clear()
                out.append(best_val)
                i = best_end
            else:
                raw_buf.append(parts[i])
                i += 1
        if raw_buf:
            out.append(self._scrub_unmatched("".join(raw_buf)))
        return "".join(out)

    def _scrub_inner_xml(self, xml_str: str) -> tuple[str, bool]:
        changed = False

        def _rep_text(m):
            nonlocal changed
            orig = m.group(1)
            new = RE_UUID_ANY.sub(lambda u: self.fake_uuid_or_id(u.group(0)), orig)
            new = self.scrub_free_text(new)
            if new != orig:
                changed = True
            return new

        def _rep_attr(m):
            nonlocal changed
            aname, aval = m.group(1), m.group(2)
            if not aval or aname == "xmlns" or aname.startswith("xmlns:"):
                return m.group(0)
            new = aval
            if "-" in new:
                new = RE_UUID_ANY.sub(lambda u: self.fake_uuid_or_id(u.group(0)), new)
            alow = aname.lower()
            if alow in INNER_TEXT_ATTRS or ("name" in alow and alow not in INNER_SKIP_NAME_ATTRS):
                new = self.scrub_free_text(new)
            elif "http" in new:
                new = RE_URL.sub(lambda u: self.fake_url(u.group(0)), new)
            if new != aval:
                changed = True
                return f'{aname}="{new.replace(chr(34), "&quot;")}"'
            return m.group(0)

        res = RE_XML_TEXT.sub(_rep_text, xml_str)
        res = RE_XML_NAMED_ATTR.sub(_rep_attr, res)
        return res, changed

    def process_binary_b64(self, tag: str, raw_b64: str) -> str:
        clean = raw_b64.strip()
        if len(clean) < 16:
            return raw_b64
        try:
            head = base64.b64decode(clean[:32] + "===")
        except Exception:
            return raw_b64

        if head.startswith(b"\x89PNG"):
            self.binary_stats[f"{tag} [PNG]"] += 1
            return raw_b64
        if head.startswith(b"\xff\xd8\xff"):
            self.binary_stats[f"{tag} [JPEG]"] += 1
            return raw_b64
        if head.startswith(b"RIFF") and b"WAVE" in head[:12]:
            self.binary_stats[f"{tag} [WAV]"] += 1
            return raw_b64

        if head.startswith((b"<?xml", b"\xef\xbb\xbf<?xml")):
            self.binary_stats[f"{tag} [XML]"] += 1
            if tag.endswith(".xsd"):
                return raw_b64
            try:
                raw_bytes = base64.b64decode(clean)
                has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
                xml_str = raw_bytes.decode("utf-8-sig", errors="replace")
                new_str, changed = self._scrub_inner_xml(xml_str)
                if not changed:
                    return raw_b64
                self.binary_scrubbed[tag] += 1
                out_bytes = (b"\xef\xbb\xbf" if has_bom else b"") + new_str.encode("utf-8")
                return base64.b64encode(out_bytes).decode("ascii")
            except Exception:
                return raw_b64

        if head.startswith(b"PK\x03\x04"):
            self.binary_stats[f"{tag} [ZIP]"] += 1
            try:
                raw_bytes = base64.b64decode(clean)
                any_changed = False
                out_buf = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zin:
                    with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                        for info in zin.infolist():
                            data = zin.read(info.filename)
                            if info.filename.lower().endswith((".xml", ".txt", ".json", ".svg")):
                                txt = data.decode("utf-8-sig", errors="replace")
                                new_txt, ch = self._scrub_inner_xml(txt)
                                if ch:
                                    any_changed = True
                                    data = new_txt.encode("utf-8")
                            zout.writestr(info, data)
                if not any_changed:
                    return raw_b64
                self.binary_scrubbed[tag] += 1
                return base64.b64encode(out_buf.getvalue()).decode("ascii")
            except Exception:
                return raw_b64

        self.binary_stats[f"{tag} [BINARY]"] += 1
        return raw_b64


class CIMStreamHandler(xml.sax.handler.ContentHandler):
    def __init__(self, engine: AnonymizerEngine, system_name_ids: set[str], out_writer=None, collect_only: bool = False):
        super().__init__()
        self.engine = engine
        self.system_name_ids = system_name_ids
        self.out = out_writer
        self.collect_only = collect_only
        self.tag_stack: list[str] = []
        self.text_buf: list[str] = []
        self.cur_obj_id = ""
        self.in_raw_curve = False
        self.tag_count = 0
        self.t_start = time.time()

    def _flush_text(self):
        if not self.text_buf:
            return
        raw = "".join(self.text_buf)
        self.text_buf.clear()
        if not raw.strip() or not self.tag_stack:
            if not self.collect_only:
                self.out.characters(raw)
            return

        full_tag = self.tag_stack[-1]
        short_tag = full_tag.split(".")[-1]
        parent = self.tag_stack[-2] if len(self.tag_stack) > 1 else ""
        res = raw

        if not self.collect_only and full_tag in BINARY_TAGS:
            res = self.engine.process_binary_b64(full_tag, raw)
        elif full_tag in META_NAME_TAGS or parent in SYSTEM_CLASSES:
            pass
        elif parent == "name" and short_tag == "name":
            if not self.collect_only and self.cur_obj_id not in self.system_name_ids:
                clean_n = " ".join(raw.split())
                if clean_n in self.engine.person_map:
                    res = self.engine.person_map[clean_n]
                else:
                    scrubbed = self.engine.scrub_free_text(raw)
                    res = (
                        scrubbed
                        if scrubbed != raw
                        else self.engine.fake_plant_name(raw, is_org=False, remember=False, stateful=False)
                    )
        elif short_tag in PERSON_TAGS or (short_tag in NAME_TAGS and parent in PERSON_CLASSES):
            # Автоопределение юрлица внутри cim:Customer (например, ООО "Завод")
            if short_tag in NAME_TAGS and RE_ORG_FORM.match(raw.strip()):
                res = self.engine.fake_plant_name(raw, is_org=True, remember=self.collect_only, stateful=True)
            else:
                res = self.engine.fake_person(raw, remember=self.collect_only, part=short_tag)
        elif short_tag in ORG_TAGS or (short_tag in NAME_TAGS and parent in ORG_CLASSES):
            res = self.engine.fake_plant_name(raw, is_org=True, remember=self.collect_only, stateful=True)
        elif short_tag in NAME_TAGS and parent in LOCAL_ENERGY_CLASSES:
            # Крупные объекты держим в кэше/Trie (stateful=True), миллионы опор и выключателей — stateless (0 байт RAM)
            is_searchable = (parent in SEARCHABLE_ENERGY_CLASSES) and (short_tag != "nameplate")
            if not self.collect_only or is_searchable:
                res = self.engine.fake_plant_name(
                    raw, is_org=False, remember=(self.collect_only and is_searchable), stateful=is_searchable
                )
        elif full_tag in ADDRESS_TAGS or short_tag in ADDRESS_TAGS:
            # На 1-м проходе заходим сюда только за городами/районами, на 2-м — переписываем все адреса
            if not self.collect_only or "towndetail" in full_tag or "stateorprovince" in full_tag:
                res = self.engine.fake_address(raw, full_tag, remember=self.collect_only)
        elif not self.collect_only:
            if short_tag in NAME_TAGS and parent in SCRUB_NAME_CLASSES:
                res = self.engine.scrub_free_text(raw)
            elif short_tag in UUID_TAGS:
                res = self.engine.fake_uuid_or_id(raw)
            elif full_tag in DIGIT_TAGS or short_tag in DIGIT_TAGS:
                res = self.engine.fake_digits(raw, short_tag)
            elif short_tag in EMAIL_TAGS:
                res = self.engine.fake_email(raw)
            elif full_tag in COORD_X_TAGS:
                res = self.engine.fake_coord(raw, "x")
            elif full_tag in COORD_Y_TAGS:
                res = self.engine.fake_coord(raw, "y")
            elif short_tag in FREE_TEXT_TAGS or "name" in short_tag:
                res = self.engine.scrub_free_text(raw)

        if not self.collect_only:
            self.out.characters(res)

    def startElement(self, name, attrs):
        self._flush_text()
        ltag = name.split(":")[-1].lower()
        short_tag = ltag.split(".")[-1]
        parent = self.tag_stack[-1] if self.tag_stack else ""
        self.tag_stack.append(ltag)
        self.in_raw_curve = short_tag in RAW_CURVE_TAGS

        if "rdf:about" in attrs or "rdf:ID" in attrs:
            raw_id = attrs.get("rdf:about") or attrs.get("rdf:ID")
            self.cur_obj_id = norm_rdf_id(raw_id)

        if self.collect_only:
            if parent in SYSTEM_CLASSES and ltag == "identifiedobject.names" and "rdf:resource" in attrs:
                self.system_name_ids.add(norm_rdf_id(attrs["rdf:resource"]))
            return

        if self.in_raw_curve:
            self.engine.binary_stats[f"{ltag} [CURVE_BIN]"] += 1

        self.tag_count += 1
        if self.tag_count % 500_000 == 0:
            print(f"  [Pass 2] обработано {self.tag_count:,} тегов ({time.time() - self.t_start:.1f}с)...")

        new_attrs = {}
        for k in attrs.getNames():
            v = attrs.getValue(k)
            if k.startswith("xmlns"):
                new_attrs[k] = v
            elif k in ("rdf:ID", "rdf:about"):
                new_attrs[k] = self.engine.fake_url(v) if v.startswith("http") else self.engine.fake_uuid_or_id(v)
            elif k == "rdf:resource":
                if v.startswith("#"):
                    new_attrs[k] = self.engine.fake_uuid_or_id(v)
                elif v.startswith("http"):
                    new_attrs[k] = self.engine.fake_url(v)
                else:
                    new_attrs[k] = v
            else:
                new_attrs[k] = v
        self.out.startElement(name, xml.sax.xmlreader.AttributesImpl(new_attrs))

    def characters(self, content):
        if self.in_raw_curve or (self.collect_only and self.tag_stack and self.tag_stack[-1] in BINARY_TAGS):
            if not self.collect_only:
                self.out.characters(content)
            return
        self.text_buf.append(content)

    def endElement(self, name):
        self._flush_text()
        self.in_raw_curve = False
        self.tag_stack.pop()
        if not self.collect_only:
            self.out.endElement(name)


def process_cim(input_path: str, output_path: str, config_path: str):
    t0 = time.time()
    with open(config_path, "r", encoding="utf-8") as cf:
        cfg = json.load(cf)

    engine = AnonymizerEngine(cfg)
    system_name_ids: set[str] = set()
    parser = xml.sax.make_parser()

    parser.setContentHandler(CIMStreamHandler(engine, system_name_ids, collect_only=True))
    with open(input_path, "rb") as f:
        parser.parse(f)
    print(f"Проход 1 готов за {time.time() - t0:.1f}с. Сущностей в Trie: {len(engine.known_entities)} (язык: {cfg['target_language']})")

    engine.compile_scrubber()

    with open(output_path, "w", encoding="utf-8", buffering=8 * 1024 * 1024) as out_f:
        writer = xml.sax.saxutils.XMLGenerator(out_f, encoding="utf-8", short_empty_elements=True)
        writer.startDocument()
        parser.setContentHandler(CIMStreamHandler(engine, system_name_ids, out_writer=writer, collect_only=False))
        with open(input_path, "rb") as f:
            parser.parse(f)
        writer.endDocument()

    print(f"Готово за {time.time() - t0:.1f}с!")
    print("=== ОТЧЁТ ПО БИНАРНЫМ ВЛОЖЕНИЯМ ===")
    for k, cnt in engine.binary_stats.most_common():
        print(f"  {cnt:>6} | {k}")
    print("=== ОЧИЩЕНО БИНАРНИКОВ С ТЕКСТОМ ===")
    for k, cnt in engine.binary_scrubbed.most_common():
        print(f"  {cnt:>6} | {k}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Потоковый анонимайзер CIM XML")
    ap.add_argument("input", nargs="?", default=INPUT_XML, help="Входной XML")
    ap.add_argument("output", nargs="?", default=OUTPUT_XML, help="Выходной XML")
    ap.add_argument("-c", "--config", default=CONFIG_PATH, help="Путь к config.json")
    args = ap.parse_args()
    process_cim(args.input, args.output, args.config)