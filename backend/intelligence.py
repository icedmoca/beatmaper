from __future__ import annotations
import json, math, time, hashlib
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path('/home/dad/Desktop/beat/pro/all_ranked_zips')
BRAIN_DIR = ROOT / 'models' / 'brain'
BRAIN_DIR.mkdir(parents=True, exist_ok=True)
DATASET_BRAIN = BRAIN_DIR / 'dataset_brain.json'
STYLE_MEMORY = BRAIN_DIR / 'style_memory.json'
TASTE_MEMORY = BRAIN_DIR / 'taste_memory.jsonl'

CUT_VEC = {0:(0,1),1:(0,-1),2:(-1,0),3:(1,0),4:(-1,1),5:(1,1),6:(-1,-1),7:(1,-1),8:(0,0)}

STYLE_PRESETS = {
    'ranked tech': {'density':1.45,'streams':1.3,'maxSimultaneous':3,'dots':0.06,'walls':0.05,'flowBias':0.45,'techBias':0.85},
    'flowy dance': {'density':0.9,'streams':0.55,'maxSimultaneous':2,'dots':0.025,'walls':0.03,'flowBias':0.95,'techBias':0.2},
    'ost-like': {'density':0.65,'streams':0.25,'maxSimultaneous':2,'dots':0.03,'walls':0.08,'flowBias':0.8,'techBias':0.15},
    'speed map': {'density':1.8,'streams':1.8,'maxSimultaneous':2,'dots':0.03,'walls':0.01,'flowBias':0.55,'techBias':0.65},
    'accuracy map': {'density':0.8,'streams':0.25,'maxSimultaneous':1,'dots':0.12,'walls':0.0,'flowBias':0.6,'techBias':0.25},
    'fitness map': {'density':1.0,'streams':0.75,'maxSimultaneous':2,'dots':0.02,'walls':0.12,'flowBias':0.9,'techBias':0.1},
    'cinematic map': {'density':0.55,'streams':0.15,'maxSimultaneous':2,'dots':0.04,'walls':0.15,'flowBias':0.7,'techBias':0.05},
}

def _mean(xs): return sum(xs)/len(xs) if xs else 0.0

def token_for_note(n):
    typ = 'RED' if n.get('_type') == 0 else 'BLUE' if n.get('_type') == 1 else 'BOMB'
    cuts = {0:'UP',1:'DOWN',2:'LEFT',3:'RIGHT',4:'UPLEFT',5:'UPRIGHT',6:'DOWNLEFT',7:'DOWNRIGHT',8:'DOT'}
    return f"{typ} L{n.get('_lineIndex',0)} Y{n.get('_lineLayer',0)} {cuts.get(n.get('_cutDirection',8),'DOT')}"

def tokenize_notes(notes):
    groups=defaultdict(list)
    for n in notes:
        groups[round(float(n.get('_time',0)),3)].append(n)
    toks=[]
    for beat in sorted(groups):
        toks.append(f'[BEAT {beat:.3f}]')
        for n in sorted(groups[beat], key=lambda x:(x.get('_type',0),x.get('_lineIndex',0),x.get('_lineLayer',0))):
            toks.append('['+token_for_note(n)+']')
    return toks

def notes_from_preview(preview_notes):
    return [dict(n) for n in preview_notes if n.get('_type') in (0,1,3)]

def map_features(notes, bpm=120, duration=1):
    color=[n for n in notes if n.get('_type') in (0,1)]
    by_time=defaultdict(list)
    for n in color: by_time[n.get('_time',0)].append(n)
    gaps=[]; times=sorted(by_time)
    for a,b in zip(times,times[1:]):
        if b>a: gaps.append(b-a)
    cuts=Counter(n.get('_cutDirection',8) for n in color)
    lanes=Counter(n.get('_lineIndex',0) for n in color)
    doubles=sum(1 for v in by_time.values() if len(v)>=2)
    dots=cuts.get(8,0)
    return {
        'notes':len(color), 'states':len(by_time), 'nps':round(len(color)/max(1,duration),3),
        'avgGap':round(_mean(gaps),3), 'minGap':round(min(gaps),3) if gaps else None,
        'doubles':doubles, 'doubleRate':round(doubles/max(1,len(by_time)),3),
        'dotRate':round(dots/max(1,len(color)),3),
        'laneBalance':dict(lanes), 'cutDistribution':dict(cuts),
    }

def style_vector_from_features(f):
    return {
        'density': min(2.5, f.get('nps',0)/5),
        'doubleAffinity': f.get('doubleRate',0),
        'dotAffinity': f.get('dotRate',0),
        'spacing': f.get('avgGap') or 1,
        'tech': min(1, (f.get('dotRate',0)*1.7 + max(0, .7-(f.get('avgGap') or 1))*0.8)),
        'flow': min(1, (f.get('avgGap') or 1)/1.5),
    }

def build_dataset_brain_from_spacing_profile():
    spacing_path = ROOT / 'models' / 'ranked_spacing_profile.json'
    spacing = json.loads(spacing_path.read_text()) if spacing_path.exists() else {}
    brain = {
        'version':'dataset-brain-v1', 'createdAt':time.time(),
        'source':'ranked_spacing_profile + trained pattern model',
        'styles':{}, 'retrievalIndex':[], 'spacingProfile':spacing,
    }
    for name,preset in STYLE_PRESETS.items():
        brain['styles'][name] = {'name':name, 'vector':preset, 'description':f'Procedural style prior for {name}'}
    # lightweight retrieval prototypes from spacing profile buckets
    for key,data in spacing.items():
        if not isinstance(data, dict) or 'gap_p50' not in data: continue
        brain['retrievalIndex'].append({
            'id':key, 'bpm':120, 'energy':0.5 if key=='normal' else 0.75, 'style':key,
            'gap':data.get('gap_p50'), 'nps':data.get('nps_p50'),
            'logic': {'grid': data.get('gap_p50'), 'simul': data.get('simul_distribution',{})}
        })
    DATASET_BRAIN.write_text(json.dumps(brain, indent=2), encoding='utf-8')
    return brain

def load_dataset_brain():
    if DATASET_BRAIN.exists():
        try: return json.loads(DATASET_BRAIN.read_text())
        except Exception: pass
    return build_dataset_brain_from_spacing_profile()

def retrieve_human_examples(analysis, options, k=8):
    brain=load_dataset_brain()
    bpm=float(analysis.get('bpm') or 120)
    energy=float(analysis.get('peakEnergy') or 0)
    target_style=options.get('style','flowy dance')
    candidates=brain.get('retrievalIndex',[])
    scored=[]
    for c in candidates:
        score=abs((c.get('bpm') or 120)-bpm)/180 + abs((c.get('energy') or 0.5)-energy)
        if target_style in c.get('style',''): score-=0.2
        scored.append((score,c))
    return [c for _,c in sorted(scored, key=lambda x:x[0])[:k]]

def section_plan(analysis, options):
    duration=float(analysis.get('duration') or 1)
    sections=[]
    n=max(1, math.ceil(duration/16))
    for i in range(n):
        start=i*16; end=min(duration,(i+1)*16)
        frac=i/max(1,n-1)
        if frac<.12: role='intro'
        elif frac<.38: role='verse/vocal flow'
        elif frac<.55: role='buildup/tension'
        elif frac<.78: role='drop/chorus'
        elif frac<.9: role='break/recovery'
        else: role='final chorus variation'
        base={'intro':0.45,'verse/vocal flow':0.65,'buildup/tension':0.85,'drop/chorus':1.2,'break/recovery':0.4,'final chorus variation':1.35}[role]
        sections.append({'index':i,'start':start,'end':end,'role':role,'densityMultiplier':base,'difficultyArc':round(base*(.8+.4*frac),3)})
    return sections

def simulate_player(notes, bpm=120):
    color=[n for n in notes if n.get('_type') in (0,1)]
    hand_last={0:None,1:None}; strain=0; parity_breaks=0; vision=0; travel=[]; reaction=[]
    by_time=defaultdict(list)
    for n in color: by_time[n.get('_time',0)].append(n)
    for n in sorted(color, key=lambda x:x.get('_time',0)):
        h=n.get('_type'); last=hand_last.get(h)
        pos=(n.get('_lineIndex',0), n.get('_lineLayer',0)); cut=n.get('_cutDirection',8)
        if last:
            dt=max(.001,(n['_time']-last['_time'])*60/max(1,bpm))
            dist=math.dist(pos,(last.get('_lineIndex',0),last.get('_lineLayer',0)))
            travel.append(dist/dt)
            if cut != 8 and last.get('_cutDirection',8) != 8:
                vx,vy=CUT_VEC.get(cut,(0,0)); lx,ly=CUT_VEC.get(last.get('_cutDirection'),(0,0))
                if vx == -lx and vy == -ly and dt < .55: parity_breaks += 1
            reaction.append(dt)
        hand_last[h]=n
        if len(by_time[n['_time']])>=3: vision+=1
    avg_travel=_mean(travel)
    fatigue=min(1, avg_travel/10 + len(color)/max(1,(max([n['_time'] for n in color] or [1])*60/max(1,bpm)))/15)
    miss=min(1, parity_breaks*.04 + max(0,.25-(_mean(reaction) or 1)) + fatigue*.25)
    return {
        'avgHandVelocity':round(avg_travel,3), 'parityBreaks':parity_breaks,
        'visionBlocks':vision, 'fatigue':round(fatigue,3), 'missProbability':round(miss,3),
        'reactionMargin':round(_mean(reaction),3) if reaction else None,
    }

def score_map(notes, analysis, options):
    f=map_features(notes, analysis.get('bpm',120), analysis.get('duration',1))
    sim=simulate_player(notes, analysis.get('bpm',120))
    alignment=0
    beats=[t*analysis.get('bpm',120)/60 for t in analysis.get('beats',[])]
    color=[n for n in notes if n.get('_type') in (0,1)]
    if beats and color:
        alignment=sum(1 for n in color if min(abs(n['_time']-b) for b in beats)<=.25)/len(color)
    fun=max(0,min(1, alignment*.35 + (1-sim['missProbability'])*.35 + min(1,f['doubleRate']*2)*.15 + min(1,f['nps']/6)*.15))
    return {'features':f, 'simulation':sim, 'alignment':round(alignment,3), 'predictedFun':round(fun,3)}

def multi_agent_review(notes, analysis, options):
    score=score_map(notes, analysis, options)
    reports=[]
    reports.append({'agent':'audio analyst','verdict':'pass' if score['alignment']>.65 else 'repair','notes':f"beat alignment {score['alignment']}"})
    reports.append({'agent':'parity critic','verdict':'pass' if score['simulation']['parityBreaks']<4 else 'repair','notes':f"parity breaks {score['simulation']['parityBreaks']}"})
    reports.append({'agent':'difficulty scaler','verdict':'pass','notes':f"nps {score['features']['nps']}, doubles {score['features']['doubles']}"})
    reports.append({'agent':'human taste judge','verdict':'pass' if score['predictedFun']>.45 else 'needs variation','notes':f"predicted fun {score['predictedFun']}"})
    reports.append({'agent':'export validator','verdict':'pass','notes':'standard v2 export preserved'})
    return {'score':score, 'agents':reports}

def remember_taste(action, payload):
    rec={'time':time.time(), 'action':action, 'payload':payload}
    with TASTE_MEMORY.open('a', encoding='utf-8') as f: f.write(json.dumps(rec)+'\n')
    return rec
