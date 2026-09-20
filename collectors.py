import re, hashlib
from datetime import date, datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

HEADERS = {"User-Agent": "Mozilla/5.0 OrthoCourseFinder/3.0 (+course index; links to official source)"}
SOURCES = {
    "BOFAS": "https://www.bofas.org.uk/clinician/education/course-registration",
    "BOA": "https://www.boa.ac.uk/?post_type=events",
    "EFORT": "https://www.efort.org/events-calendar/orthopaedic-event-calendar/",
    "AO": "https://www.aofoundation.org/courses-and-events",
    "BASK": "https://bask.ac.uk/",
    "BHS": "https://britishhipsociety.com/meetings",
    "BESS": "https://bess.ac.uk/courses-and-events/",
    "BSCOS": "https://www.bscos.org.uk/public/events-education/bscos-meetings-and-courses",
    "BSSH": "https://www.bssh.ac.uk/about/events",
    "EFAS": "https://www.efas.net/events",
    "AOFAS": "https://www.aofas.org/education/meetings-courses",
}

def ident(title, start, organiser):
    return hashlib.sha1(f"{title}|{start}|{organiser}".encode()).hexdigest()[:16]

def specialty_for(text):
    t = text.lower()
    rules = [
        (("foot","ankle"), "Foot & Ankle"), (("knee","acl","menisc"), "Knee"), (("hip",), "Hip"),
        (("hand","wrist","carpal"), "Hand & Wrist"), (("spine",), "Spine"),
        (("shoulder","elbow"), "Shoulder & Elbow"), (("paediatric","pediatric","children","kids"), "Paediatrics"),
        (("trauma","fracture"), "Trauma"), (("arthroplasty","joint replacement"), "Arthroplasty"),
        (("exam","ukite","frcs","diploma preparation","resident review"), "FRCS / Exam"),
    ]
    for keys, value in rules:
        if any(k in t for k in keys): return value
    return "General Orthopaedics"

def course_type_for(text):
    t=text.lower()
    if any(k in t for k in ["cadaver", "dissection", "bioskills", "skills course"]): return "Cadaveric / Skills"
    if any(k in t for k in ["webinar", "virtual", "online"]): return "Webinar / Online"
    if any(k in t for k in ["exam", "ukite", "frcs", "diploma preparation", "resident review"]): return "Exam / Revision"
    if any(k in t for k in ["instructional course", "course", "masterclass", "workshop"]): return "Course / Workshop"
    if any(k in t for k in ["annual meeting", "annual congress", "congress", "scientific meeting", "conference"]): return "Conference / Meeting"
    return "Education Event"

def audience_for(text):
    t=text.lower(); tags=[]
    if any(k in t for k in ["consultant", "advanced", "masters", "masterclass"]): tags.append("Consultant")
    if any(k in t for k in ["trainee", "resident", "registrar", "fellow", "ukite", "frcs", "diploma preparation"]): tags.append("Trainee / Fellow")
    if any(k in t for k in ["medical student", "student"]): tags.append("Medical Student")
    if any(k in t for k in ["allied health", "ahp", "therapy", "physio"]): tags.append("AHP")
    return tags or ["All career stages"]

def get(url):
    r=requests.get(url,headers=HEADERS,timeout=20); r.raise_for_status(); return BeautifulSoup(r.text,"html.parser")

def parse_date_range(text):
    patterns=[
        r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",
        r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",
        r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",
    ]
    for i,p in enumerate(patterns):
        m=re.search(p,text,re.I)
        if not m: continue
        try:
            if i==0:
                s=dateparser.parse(f"{m.group(1)} {m.group(3)} {m.group(4)}",dayfirst=True).date(); e=dateparser.parse(f"{m.group(2)} {m.group(3)} {m.group(4)}",dayfirst=True).date()
            elif i==1:
                s=dateparser.parse(f"{m.group(1)} {m.group(2)} {m.group(3)}",dayfirst=True).date(); e=dateparser.parse(f"{m.group(4)} {m.group(5)} {m.group(6)}",dayfirst=True).date()
            else:
                s=dateparser.parse(m.group(0),dayfirst=True).date(); e=s
            return s,e
        except Exception: pass
    return None

def item(title,s,e,specialty,city,country,price,fmt,organiser,url,source,course_type=None,audience=None):
    text=f"{title} {specialty} {fmt}"
    return {"id":ident(title,s.isoformat(),organiser),"title":title,"specialty":specialty,"city":city,"country":country,
            "start_date":s.isoformat(),"end_date":e.isoformat(),"price":price,"format":fmt,"organiser":organiser,"url":url,"source":source,
            "course_type":course_type or course_type_for(text),"audience":audience or audience_for(text)}

def collect_bofas():
    soup=get(SOURCES["BOFAS"]); text=soup.get_text(" ",strip=True); out=[]
    rx=re.compile(r"(.+?) Event Start Date:\s*(\d{2}/\d{2}/\d{4})\s*Event End Date:\s*(\d{2}/\d{2}/\d{4})\s*Cost:\s*£([0-9,.]+)",re.I)
    for m in rx.finditer(text):
        title=m.group(1).strip()[-180:]; s=datetime.strptime(m.group(2),"%d/%m/%Y").date(); e=datetime.strptime(m.group(3),"%d/%m/%Y").date()
        city=next((c for c in ["Glasgow","Bristol","Bromsgrove","Milton Keynes"] if c.lower() in title.lower()),"UK")
        out.append(item(title,s,e,"Foot & Ankle",city,"UK",f"£{m.group(4)}","In person","BOFAS",SOURCES["BOFAS"],"BOFAS"))
    return out

def collect_boa():
    soup=get(SOURCES["BOA"]); out=[]
    for h in soup.select("h2,h3,h4"):
        title=h.get_text(" ",strip=True); block=h.parent.get_text(" ",strip=True) if h.parent else title
        dr=parse_date_range(block)
        if len(title)<5 or not dr: continue
        a=h.find("a") or (h.parent.find("a") if h.parent else None); url=urljoin(SOURCES["BOA"],a.get("href")) if a and a.get("href") else SOURCES["BOA"]
        out.append(item(title,*dr,specialty_for(title),"UK","UK","See organiser","Online" if "online" in block.lower() else "In person","British Orthopaedic Association",url,"BOA"))
    return out

def collect_bess():
    soup=get(SOURCES["BESS"]); out=[]
    for node in soup.select("article,.event,.event-item,li"):
        text=node.get_text(" ",strip=True); dr=parse_date_range(text)
        if not dr or len(text)<15: continue
        a=node.find("a"); title=(a.get_text(" ",strip=True) if a else text[:160]).strip()
        if not any(k in text.lower() for k in ["shoulder","elbow","bess","journal club","elevate","annual scientific"]): continue
        url=urljoin(SOURCES["BESS"],a.get("href")) if a and a.get("href") else SOURCES["BESS"]
        out.append(item(title,*dr,"Shoulder & Elbow","","UK","See organiser","Online" if "online" in text.lower() else "In person","BESS",url,"BESS"))
    return out

def collect_bscos():
    soup=get(SOURCES["BSCOS"]); out=[]
    for node in soup.select("article,.eds_news_Advantage,.event,.card,li"):
        text=node.get_text(" ",strip=True); dr=parse_date_range(text)
        if not dr: continue
        a=node.find("a"); title=(node.find(["h2","h3","h4"]).get_text(" ",strip=True) if node.find(["h2","h3","h4"]) else (a.get_text(" ",strip=True) if a else text[:150]))
        if not any(k in text.lower() for k in ["bscos","children","child","paediatric","pediatric"]): continue
        url=urljoin(SOURCES["BSCOS"],a.get("href")) if a and a.get("href") else SOURCES["BSCOS"]
        out.append(item(title,*dr,"Paediatrics","","UK","See organiser","In person","BSCOS",url,"BSCOS"))
    return out

def collect_bssh():
    soup=get(SOURCES["BSSH"]); out=[]
    for node in soup.select("article,.event,.event-list-item,li"):
        text=node.get_text(" ",strip=True); dr=parse_date_range(text)
        if not dr or not any(k in text.lower() for k in ["hand","wrist","bssh","tetrahand"]): continue
        h=node.find(["h2","h3","h4"]); a=node.find("a"); title=(h.get_text(" ",strip=True) if h else (a.get_text(" ",strip=True) if a else text[:170]))
        url=urljoin(SOURCES["BSSH"],a.get("href")) if a and a.get("href") else SOURCES["BSSH"]
        out.append(item(title,*dr,"Hand & Wrist","","UK","See organiser","Online" if "webinar" in text.lower() else "In person","BSSH",url,"BSSH"))
    return out

def collect_efas():
    soup=get(SOURCES["EFAS"]); out=[]
    for node in soup.select("article,.event,.card,li"):
        text=node.get_text(" ",strip=True); dr=parse_date_range(text)
        if not dr or not any(k in text.lower() for k in ["efas","foot","ankle","hindfoot"]): continue
        h=node.find(["h2","h3","h4","h5"]); a=node.find("a"); title=(h.get_text(" ",strip=True) if h else (a.get_text(" ",strip=True) if a else text[:170]))
        url=urljoin(SOURCES["EFAS"],a.get("href")) if a and a.get("href") else SOURCES["EFAS"]
        out.append(item(title,*dr,"Foot & Ankle","","Europe","See organiser","In person","EFAS",url,"EFAS"))
    return out

def collect_aofas():
    soup=get(SOURCES["AOFAS"]); out=[]
    for node in soup.select("li,article,.event,.card"):
        text=node.get_text(" ",strip=True); dr=parse_date_range(text)
        if not dr or not any(k in text.lower() for k in ["aofas","foot","ankle","resident skills","winter meeting"]): continue
        a=node.find("a"); title=(a.get_text(" ",strip=True) if a else text[:170])
        if len(title)<5: continue
        url=urljoin(SOURCES["AOFAS"],a.get("href")) if a and a.get("href") else SOURCES["AOFAS"]
        city="Online" if "virtual" in text.lower() else "USA"; fmt="Online" if city=="Online" else "In person"
        out.append(item(title,*dr,"Foot & Ankle",city,"USA" if city!="Online" else "Worldwide","See organiser",fmt,"AOFAS",url,"AOFAS"))
    return out

def collect_bhs():
    soup=get(SOURCES["BHS"]); text=soup.get_text(" ",strip=True); out=[]
    # Future BHS date currently public in society updates; generic parser covers page when listed.
    for node in soup.select("article,.card,li,div"):
        tx=node.get_text(" ",strip=True); dr=parse_date_range(tx)
        if not dr or "BHS" not in tx.upper() and "hip" not in tx.lower(): continue
        h=node.find(["h2","h3","h4","h5"]); a=node.find("a"); title=(h.get_text(" ",strip=True) if h else (a.get_text(" ",strip=True) if a else tx[:160]))
        url=urljoin(SOURCES["BHS"],a.get("href")) if a and a.get("href") else SOURCES["BHS"]
        out.append(item(title,*dr,"Hip","","UK","See organiser","In person","British Hip Society",url,"BHS"))
    return out

def collect_bask():
    soup=get(SOURCES["BASK"]); out=[]
    for node in soup.select("article,.event,.card,li"):
        tx=node.get_text(" ",strip=True); dr=parse_date_range(tx)
        if not dr or not any(k in tx.lower() for k in ["bask","knee","coks"]): continue
        h=node.find(["h2","h3","h4","h5"]); a=node.find("a"); title=(h.get_text(" ",strip=True) if h else (a.get_text(" ",strip=True) if a else tx[:160]))
        url=urljoin(SOURCES["BASK"],a.get("href")) if a and a.get("href") else SOURCES["BASK"]
        out.append(item(title,*dr,"Knee","","UK","See organiser","In person","BASK",url,"BASK"))
    return out

def collect_efort():
    soup=get(SOURCES["EFORT"]); out=[]
    for node in soup.select("tr,article,.event,.tribe-events-calendar-list__event-row"):
        text=node.get_text(" ",strip=True); dr=parse_date_range(text)
        if not dr: continue
        a=node.find("a"); title=(a.get_text(" ",strip=True) if a else text[:220]); url=urljoin(SOURCES["EFORT"],a.get("href")) if a and a.get("href") else SOURCES["EFORT"]
        out.append(item(title,*dr,specialty_for(text),"","Europe","See organiser","In person","EFORT / listed society",url,"EFORT"))
    return out

def collect_ao():
    soup=get(SOURCES["AO"]); text=soup.get_text(" ",strip=True); out=[]
    m=re.search(r"Davos.*?November\s+(\d{1,2})\s+to\s+December\s+(\d{1,2}),\s*(20\d{2})",text,re.I)
    if m:
        s=date(int(m.group(3)),11,int(m.group(1))); e=date(int(m.group(3)),12,int(m.group(2)))
        out.append(item("AO Davos Courses",s,e,"Trauma","Davos","Switzerland","See organiser","In person","AO Foundation",SOURCES["AO"],"AO","Course / Workshop",["Trainee / Fellow","Consultant"]))
    return out


def seed_official_courses():
    """
    Curated fallback records from official society event pages.
    These ensure the admin queue is never empty if a society page blocks
    automated collection or changes its HTML. All records still enter as
    PENDING and must be verified by the administrator before publication.
    """
    rows = [
        ("BOA Annual Congress 2026", date(2026,9,22), date(2026,9,24), "General Orthopaedics", "London", "UK", "See organiser", "In person", "British Orthopaedic Association", "https://www.boa.ac.uk/boa-annual-congress-2026.html", "BOA", "Conference / Meeting", ["Consultant","Trainee / Fellow"]),
        ("BSSH Scientific Meeting 2026", date(2026,11,4), date(2026,11,6), "Hand & Wrist", "Edinburgh", "UK", "See organiser", "In person", "BSSH", "https://www.bssh.ac.uk/about/events/4760/bssh_scientific_meeting_2026", "BSSH", "Conference / Meeting", ["Consultant","Trainee / Fellow"]),
        ("Leicester Hand Fracture Management Course", date(2026,11,16), date(2026,11,17), "Hand & Wrist", "Leicester", "UK", "See organiser", "In person", "BSSH-listed event", "https://www.bssh.ac.uk/about/events/date/2026/11/", "BSSH", "Course / Workshop", ["Consultant","Trainee / Fellow"]),
        ("EFAS 2026 Congress", date(2026,10,1), date(2026,10,3), "Foot & Ankle", "Augsburg", "Germany", "See organiser", "In person", "EFAS", "https://www.efas.net/events", "EFAS", "Conference / Meeting", ["Consultant","Trainee / Fellow"]),
        ("EFAS Hindfoot", date(2026,12,10), date(2026,12,11), "Foot & Ankle", "Augsburg", "Germany", "See organiser", "In person", "EFAS", "https://www.efas.net/events", "EFAS", "Course / Workshop", ["Consultant","Trainee / Fellow"]),
        ("AOFAS Foot & Ankle Focus: Resident Review Part 1", date(2026,10,14), date(2026,10,14), "Foot & Ankle", "Online", "Worldwide", "See organiser", "Online", "AOFAS", "https://www.aofas.org/education/meetings-courses", "AOFAS", "Exam / Revision", ["Trainee / Fellow"]),
        ("AOFAS Foot & Ankle Focus: Resident Review Part 2", date(2026,10,21), date(2026,10,21), "Foot & Ankle", "Online", "Worldwide", "See organiser", "Online", "AOFAS", "https://www.aofas.org/education/meetings-courses", "AOFAS", "Exam / Revision", ["Trainee / Fellow"]),
        ("AOFAS Resident Skills Course", date(2026,10,23), date(2026,10,24), "Foot & Ankle", "Lewisville, Texas", "USA", "See organiser", "In person", "AOFAS", "https://www.aofas.org/education/meetings-courses", "AOFAS", "Cadaveric / Skills", ["Trainee / Fellow"]),
        ("AOFAS Medical Student BioSkills Workshop", date(2026,11,7), date(2026,11,7), "Foot & Ankle", "Chicago, Illinois", "USA", "See organiser", "In person", "AOFAS", "https://www.aofas.org/education/meetings-courses", "AOFAS", "Cadaveric / Skills", ["Medical Student"]),
        ("AOFAS Advanced Foot and Ankle Virtual Course", date(2026,11,12), date(2026,11,14), "Foot & Ankle", "Online", "Worldwide", "See organiser", "Online", "AOFAS", "https://www.aofas.org/education/meetings-courses", "AOFAS", "Webinar / Online", ["Consultant","Trainee / Fellow"]),
        ("AOFAS Winter Meeting", date(2027,2,11), date(2027,2,13), "Foot & Ankle", "Orlando, Florida", "USA", "See organiser", "In person", "AOFAS", "https://www.aofas.org/education/meetings-courses", "AOFAS", "Conference / Meeting", ["Consultant","Trainee / Fellow"]),
    ]
    return [item(*r) for r in rows]

def collect_all():
    items=[]
    collectors=[collect_bofas,collect_boa,collect_bask,collect_bhs,collect_bess,collect_bscos,collect_bssh,collect_efas,collect_aofas,collect_efort,collect_ao,seed_official_courses]
    for fn in collectors:
        try: items.extend(fn())
        except Exception: pass
    today=date.today().isoformat(); dedup={}
    for x in items:
        if x["end_date"] >= today: dedup[(x["title"].lower(), x["start_date"])] = x
    return sorted(dedup.values(),key=lambda x:x["start_date"])
