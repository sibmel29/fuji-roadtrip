import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

POI_FILE = Path("poi.json")
FISHING_FILE = Path("fishing-log.json")
SURF_FILE = Path("surf-log.json")
VAN_FILE = Path("van-nights.geojson")

def slugify(v):
    return re.sub(r"[^a-z0-9]+", "-", str(v or "").strip().lower()).strip("-") or "mobile-entry"

def as_bool(v, default=True):
    if v in (None, ""): return default
    return str(v).strip().lower() not in {"0","false","no","draft","private"}

def num(v, field):
    n=float(v)
    if field=="latitude" and not -90<=n<=90: raise ValueError("bad latitude")
    if field=="longitude" and not -180<=n<=180: raise ValueError("bad longitude")
    return round(n,6)

def split_list(v):
    if not v: return []
    if isinstance(v,list): return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[,\n]+",str(v)) if x.strip()]

def body(v):
    if not v:return []
    if isinstance(v,list):return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"\n\s*\n",str(v)) if x.strip()]

def unique(base, ids):
    if base not in ids:return base
    i=2
    while f"{base}-{i}" in ids:i+=1
    return f"{base}-{i}"

def fp(item):
    raw=json.dumps(item,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def load_list(path):
    return json.loads(path.read_text()) if path.exists() else []

def already(entries, mid):
    return any(e.get("source_mobile_id")==mid for e in entries if isinstance(e,dict))

def main():
    item=json.loads(os.environ["MOBILE_ITEM"])
    kind=str(item.get("type","")).lower()
    mid=fp(item)
    title=str(item.get("title") or kind or "Mobile entry").strip()
    lat=num(item.get("latitude"),"latitude"); lon=num(item.get("longitude"),"longitude")
    date=str(item.get("date") or "")
    published=as_bool(item.get("published"),True)

    if kind=="poi":
        p=POI_FILE; entries=load_list(p)
        if already(entries,mid): return
        ids={str(x.get("id")) for x in entries}
        entries.insert(0,{"id":unique(slugify(title),ids),"title":title,"date":date,
          "coordinates":[lon,lat],"marker":str(item.get("marker") or "sun"),
          "summary":str(item.get("summary") or ""),"body":body(item.get("story")),
          "images":[],"tags":split_list(item.get("tags")),"published":published,
          "source_mobile_id":mid})
        p.write_text(json.dumps(entries,indent=2,ensure_ascii=False)+"\n")
    elif kind in ("fishing","surf"):
        p=FISHING_FILE if kind=="fishing" else SURF_FILE
        entries=load_list(p)
        if already(entries,mid): return
        ids={str(x.get("id")) for x in entries}
        details={}
        fields = ({"Caught time":"caught_time","Spot name":"spot_name","Species":"species",
                   "Other species":"other_species","Catch details":"catch_details",
                   "Kept or released":"kept_released","Bait or lure":"bait_lure","Conditions":"conditions"}
                  if kind=="fishing" else
                  {"Surf spot":"title","First surfed":"first_surfed","Wave size":"wave_size",
                   "Wind":"wind","Tide":"tide","Board":"board","Rating":"rating","Crowd":"crowd"})
        for label,key in fields.items():
            val=title if key=="title" else str(item.get(key) or "").strip()
            if val: details[label]=val
        tags=split_list(item.get("tags"))
        if kind not in {t.lower() for t in tags}:tags.insert(0,kind)
        entries.insert(0,{"id":unique(slugify(title),ids),"type":kind,"title":title,"date":date,
          "coordinates":[lon,lat],"marker":"fish" if kind=="fishing" else "surf",
          "summary":str(item.get("summary") or ""),"body":body(item.get("story")),
          "images":[],"tags":tags,"details":details,"published":published,
          "source_mobile_id":mid})
        p.write_text(json.dumps(entries,indent=2,ensure_ascii=False)+"\n")
    elif kind in ("van-night","van_night"):
        data=json.loads(VAN_FILE.read_text()) if VAN_FILE.exists() else {"type":"FeatureCollection","features":[]}
        feats=data.setdefault("features",[])
        if any(f.get("properties",{}).get("source_mobile_id")==mid for f in feats):return
        ids={str(f.get("properties",{}).get("id")) for f in feats}
        eid=unique(slugify(f"{date}-{title}"),ids)
        feats.insert(0,{"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
          "properties":{"id":eid,"type":"van-night","profile":"manual","source_profile":"manual",
          "source_profiles":["manual"],"title":title,"first_night":date,"last_night":date,
          "night_count":1,"nights":[date] if date else [],"note":str(item.get("notes") or ""),
          "vibe":str(item.get("vibe") or ""),"facilities":str(item.get("facilities") or ""),
          "warnings":str(item.get("warnings") or ""),"published":published,
          "created_at":datetime.now(timezone.utc).isoformat(),"source_mobile_id":mid}})
        VAN_FILE.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
    else:
        raise ValueError(f"unsupported type: {kind}")

if __name__=="__main__":
    main()
