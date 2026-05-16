#!/usr/bin/env python3
import json, os, zipfile, statistics, math
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent
CORPUS = Path(
    os.environ.get('BEATMAPER_RANKED_ZIPS', str(ROOT / 'data' / 'ranked_zips'))
).expanduser()
OUT = ROOT / 'models' / 'ranked_spacing_profile.json'
MAX=1800

def load(raw): return json.loads(raw.decode('utf-8-sig'))
def notes_of(bm):
    if '_notes' in bm: return [n for n in bm.get('_notes',[]) if n.get('_type') in (0,1)]
    return [{'_time':n.get('b',0),'_lineIndex':n.get('x',0),'_lineLayer':n.get('y',0),'_type':n.get('c',0),'_cutDirection':n.get('d',8)} for n in bm.get('colorNotes',[])]
def pct(a,p):
    if not a: return None
    a=sorted(a); k=(len(a)-1)*p/100; f=math.floor(k); c=math.ceil(k)
    return a[f] if f==c else a[f]*(c-k)+a[c]*(k-f)

profiles=defaultdict(lambda:{'gaps':[],'simul':Counter(),'nps':[],'maps':0})
allg=[]
for zi,zp in enumerate(sorted(CORPUS.glob('*.zip'))[:MAX],1):
    try:
        with zipfile.ZipFile(zp) as z:
            names={n.lower():n for n in z.namelist()}
            if 'info.dat' not in names: continue
            info=load(z.read(names['info.dat']))
            bpm=float(info.get('_beatsPerMinute') or 120)
            for st in info.get('_difficultyBeatmapSets',[]):
                if st.get('_beatmapCharacteristicName')!='Standard': continue
                for d in st.get('_difficultyBeatmaps',[]):
                    diff=d.get('_difficulty','Unknown')
                    fn=(d.get('_beatmapFilename') or '').lower()
                    if fn not in names: continue
                    ns=notes_of(load(z.read(names[fn])))
                    if len(ns)<40: continue
                    times=sorted(round(float(n['_time'])*8)/8 for n in ns)
                    uniq=sorted(set(times))
                    gaps=[b-a for a,b in zip(uniq,uniq[1:]) if 0<b-a<8]
                    if not gaps: continue
                    dur=max(times)*60/bpm if bpm else 1
                    nps=len(ns)/max(1,dur)
                    key='normal' if diff in ('Easy','Normal','Hard') else 'expert' if diff=='Expert' else 'expertplus'
                    profiles[key]['gaps'].extend(gaps); profiles[key]['nps'].append(nps); profiles[key]['maps']+=1
                    c=Counter(times)
                    profiles[key]['simul'].update(min(v,6) for v in c.values())
                    allg.extend(gaps)
    except Exception:
        pass
out={}
for k,v in profiles.items():
    gaps=v['gaps']; nps=v['nps']; simul=v['simul']; total=sum(simul.values()) or 1
    out[k]={
        'maps':v['maps'],
        'gap_p25':pct(gaps,25),'gap_p50':pct(gaps,50),'gap_p75':pct(gaps,75),'gap_p90':pct(gaps,90),
        'nps_p25':pct(nps,25),'nps_p50':pct(nps,50),'nps_p75':pct(nps,75),
        'simul_distribution':{str(k2):round(v2/total,4) for k2,v2 in sorted(simul.items())}
    }
out['createdFromMaps']=sum(v['maps'] for v in profiles.values())
OUT.write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2)[:3000])
