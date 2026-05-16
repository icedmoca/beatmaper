#!/usr/bin/env python3
"""Train a lightweight Beat Saber pattern model from ranked map zips.

This is intentionally local/offline and dependency-light. It extracts Standard .dat
notes from the downloaded ranked corpus, learns timing-bin pattern transitions,
lane/layer/cut distributions, and difficulty-density buckets, then writes a JSON
model the generator can use.
"""
from __future__ import annotations
import json, os, zipfile, statistics, math, time, random
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
CORPUS = Path(
    os.environ.get('BEATMAPER_RANKED_ZIPS', str(ROOT / 'data' / 'ranked_zips'))
).expanduser()
OUTDIR = ROOT / 'models'
OUTDIR.mkdir(exist_ok=True)
MODEL = OUTDIR / 'ranked_pattern_model.json'
REPORT = OUTDIR / 'training_report.json'
MAX_MAPS = 2600
MAX_NOTES_PER_MAP = 20000

DIFF_RANK = {'Easy':1,'Normal':3,'Hard':5,'Expert':7,'ExpertPlus':9,'Expert+':9}
CUTS = list(range(9))

def load_dat(raw: bytes):
    # Beat Saber dat is JSON, sometimes UTF-8 with BOM.
    return json.loads(raw.decode('utf-8-sig'))

def get_notes(beatmap):
    if '_notes' in beatmap:
        return [n for n in beatmap.get('_notes', []) if n.get('_type') in (0,1)]
    # v3 format fallback
    out=[]
    for n in beatmap.get('colorNotes', []):
        out.append({'_time': n.get('b',0), '_lineIndex': n.get('x',0), '_lineLayer': n.get('y',0), '_type': n.get('c',0), '_cutDirection': n.get('d',0)})
    return out

def info_sets(info):
    return info.get('_difficultyBeatmapSets') or info.get('difficultyBeatmapSets') or []

def set_name(s):
    return s.get('_beatmapCharacteristicName') or s.get('beatmapCharacteristicName') or ''

def maps_in_set(s):
    return s.get('_difficultyBeatmaps') or s.get('difficultyBeatmaps') or []

def map_file(d):
    return d.get('_beatmapFilename') or d.get('beatmapFilename')

def map_diff(d):
    return d.get('_difficulty') or d.get('difficulty') or 'Unknown'

def quant_time(t):
    # 1/8 beat bins. Good compromise for pattern learning.
    return round(float(t)*8)/8

def pattern_token(notes_at_time):
    parts=[]
    for n in sorted(notes_at_time, key=lambda x:(x.get('_type',0), x.get('_lineIndex',0), x.get('_lineLayer',0))):
        parts.append(f"{int(n.get('_type',0))}:{int(n.get('_lineIndex',0))}:{int(n.get('_lineLayer',0))}:{int(n.get('_cutDirection',8))}")
    return '|'.join(parts[:4]) or 'REST'

def parse_zip(path: Path):
    examples=[]
    try:
        with zipfile.ZipFile(path) as z:
            names={n.lower(): n for n in z.namelist()}
            info_name=names.get('info.dat')
            if not info_name: return examples
            info=load_dat(z.read(info_name))
            bpm=float(info.get('_beatsPerMinute') or info.get('beatsPerMinute') or 120)
            song=info.get('_songName') or info.get('songName') or path.stem
            for s in info_sets(info):
                if set_name(s) != 'Standard':
                    continue
                for d in maps_in_set(s):
                    fn=map_file(d)
                    if not fn or fn.lower() not in names: continue
                    diff=map_diff(d)
                    try:
                        bm=load_dat(z.read(names[fn.lower()]))
                    except Exception:
                        continue
                    notes=get_notes(bm)[:MAX_NOTES_PER_MAP]
                    if len(notes) < 50: continue
                    notes.sort(key=lambda n: float(n.get('_time',0)))
                    duration_beats=max(float(n.get('_time',0)) for n in notes) or 1
                    nps=len(notes)/(duration_beats*60/bpm) if bpm else 0
                    grouped=defaultdict(list)
                    for n in notes:
                        grouped[quant_time(n.get('_time',0))].append(n)
                    seq=[]
                    for t in sorted(grouped):
                        seq.append((t, pattern_token(grouped[t]), grouped[t]))
                    examples.append({'song':song,'file':path.name,'difficulty':diff,'rank':DIFF_RANK.get(diff,5),'bpm':bpm,'nps':nps,'notes':len(notes),'seq':seq})
    except Exception:
        return examples
    return examples

def weighted_top(counter, limit=80):
    total=sum(counter.values()) or 1
    return [{'token':k,'count':v,'p':v/total} for k,v in counter.most_common(limit)]

def main():
    zips=sorted(CORPUS.glob('*.zip'))[:MAX_MAPS]
    print(f'Training from {len(zips)} zips in {CORPUS}', flush=True)
    transitions=defaultdict(Counter)
    starters=Counter(); global_patterns=Counter(); gap_bins=Counter(); note_cells=Counter(); cut_dirs=Counter()
    by_diff=defaultdict(lambda: {'patterns':Counter(),'transitions':defaultdict(Counter),'nps':[],'maps':0,'notes':0})
    parsed=0; maps=0; total_notes=0; skipped=0
    started=time.time()
    for i,zp in enumerate(zips,1):
        exs=parse_zip(zp)
        if not exs:
            skipped+=1
        for ex in exs:
            parsed+=1; maps+=1; total_notes+=ex['notes']
            bucket = 'expertplus' if ex['rank']>=9 else 'expert' if ex['rank']>=7 else 'hard' if ex['rank']>=5 else 'lower'
            by_diff[bucket]['maps']+=1; by_diff[bucket]['notes']+=ex['notes']; by_diff[bucket]['nps'].append(ex['nps'])
            prev='START'; prev_t=None
            for t,tok,notes in ex['seq']:
                starters[tok]+= 1 if prev=='START' else 0
                global_patterns[tok]+=1; by_diff[bucket]['patterns'][tok]+=1
                transitions[prev][tok]+=1; by_diff[bucket]['transitions'][prev][tok]+=1
                if prev_t is not None:
                    gap_bins[round((t-prev_t)*8)/8]+=1
                for n in notes:
                    note_cells[f"{int(n.get('_type',0))}:{int(n.get('_lineIndex',0))}:{int(n.get('_lineLayer',0))}"]+=1
                    cut_dirs[str(int(n.get('_cutDirection',8)))] += 1
                prev=tok; prev_t=t
        if i%100==0:
            print(f'KCODE_PROGRESS {json.dumps({"zips":i,"parsed_maps":parsed,"notes":total_notes,"elapsed_sec":round(time.time()-started,1)})}', flush=True)
    model={
        'version':1,
        'createdAt':time.time(),
        'source':str(CORPUS),
        'stats':{'zips_seen':len(zips),'zips_without_standard_maps':skipped,'standard_maps':maps,'notes':total_notes},
        'global':{
            'starters':weighted_top(starters,120),
            'patterns':weighted_top(global_patterns,400),
            'transitions':{k: weighted_top(v,80) for k,v in transitions.items() if sum(v.values())>=4},
            'gapBeats':weighted_top(gap_bins,32),
            'noteCells':weighted_top(note_cells,80),
            'cutDirections':weighted_top(cut_dirs,16),
        },
        'difficultyBuckets':{}
    }
    for bucket,d in by_diff.items():
        model['difficultyBuckets'][bucket]={
            'maps':d['maps'], 'notes':d['notes'],
            'avgNps': statistics.mean(d['nps']) if d['nps'] else 0,
            'medianNps': statistics.median(d['nps']) if d['nps'] else 0,
            'patterns': weighted_top(d['patterns'],300),
            'transitions': {k: weighted_top(v,70) for k,v in d['transitions'].items() if sum(v.values())>=3},
        }
    MODEL.write_text(json.dumps(model, indent=2), encoding='utf-8')
    REPORT.write_text(json.dumps(model['stats'] | {'elapsed_sec':round(time.time()-started,2),'model':str(MODEL)}, indent=2), encoding='utf-8')
    print(f'DONE model={MODEL} report={REPORT}', flush=True)
    print(json.dumps(model['stats'], indent=2), flush=True)

if __name__=='__main__': main()
