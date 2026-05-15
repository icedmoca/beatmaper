from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import zipfile, json, math, wave, tempfile, shutil, uuid, subprocess, random
import numpy as np
from backend.intelligence import (load_dataset_brain, retrieve_human_examples, section_plan, multi_agent_review, remember_taste, score_map, STYLE_PRESETS)

ROOT=Path(__file__).resolve().parents[1]
GEN=ROOT/'generated_maps'; GEN.mkdir(exist_ok=True)
PROJECTS=ROOT/'generated_projects'; PROJECTS.mkdir(exist_ok=True)
app=FastAPI(title='Beatmaper API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

@app.exception_handler(Exception)
async def catch_all_errors(request, exc):
    return JSONResponse(status_code=500, content={'detail': str(exc), 'type': type(exc).__name__})

MODEL_PATH = ROOT / 'models' / 'ranked_pattern_model.json'
SPACING_PROFILE_PATH = ROOT / 'models' / 'ranked_spacing_profile.json'
_CACHED_SPACING = None
_CACHED_MODEL = None

def load_pattern_model():
    global _CACHED_MODEL
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    if MODEL_PATH.exists():
        try:
            _CACHED_MODEL = json.loads(MODEL_PATH.read_text())
            return _CACHED_MODEL
        except Exception:
            return None
    return None


def load_spacing_profile():
    global _CACHED_SPACING
    if _CACHED_SPACING is not None: return _CACHED_SPACING
    if SPACING_PROFILE_PATH.exists():
        try:
            _CACHED_SPACING=json.loads(SPACING_PROFILE_PATH.read_text())
            return _CACHED_SPACING
        except Exception:
            return {}
    return {}

def spacing_target_for_options(options):
    profile=load_spacing_profile()
    density=float(options.get('density',0.34))
    key='normal' if density<=0.85 else 'expert' if density<=1.4 else 'expertplus'
    p=profile.get(key,{})
    # Use training data but bias Normal toward the readable side for this app.
    target_gap=float(p.get('gap_p75') or (1.0 if key=='normal' else .5))
    if key=='normal': target_gap=max(0.875,target_gap)
    target_nps=float(p.get('nps_p50') or (3.0 if key=='normal' else 5.8 if key=='expert' else 7.5))
    target_nps*=max(.85,min(2.2,density/(.34 if key=='normal' else 1.0)))
    return {'spacingKey':key,'targetGapBeats':round(target_gap,3),'targetNps':round(target_nps,3)}


def simultaneous_probability(options, kind, strength, intensity):
    """Learned/readable chance of two notes at once.
    DeepSaber represents a timestep as a state. Real ranked maps often use 1-note states,
    with occasional 2-note states for musical anchors. This lets Normal have smart doubles
    without becoming a wall of clusters.
    """
    profile=load_spacing_profile()
    density=float(options.get('density',0.34))
    key='normal' if density<=0.85 else 'expert' if density<=1.4 else 'expertplus'
    dist=profile.get(key,{}).get('simul_distribution',{})
    learned_two=float(dist.get('2',0.08))
    base=learned_two
    if 'bass' in kind: base+=0.18
    if 'vocal' in kind and strength>0.72: base+=0.08
    if 'high' in kind: base-=0.04
    base+=max(0,intensity-.55)*0.18
    if density<=0.5: base*=0.75
    return max(0.0,min(0.42,base))

def make_intelligent_double(bt, kind, strength, rng, phrase_idx):
    """Create a readable two-hand state based on musical role."""
    if 'bass' in kind:
        layer=0; cut=rng.choice([0,1])
    elif 'high' in kind:
        layer=2; cut=rng.choice([2,3,4,5])
    else:
        layer=rng.choice([1,1,2]); cut=rng.choice([1,4,5])
    # Alternate between centered doubles and wide phrase opens.
    if phrase_idx % 4 == 0:
        lanes=(0,3)
    else:
        lanes=(1,2)
    return [
        {'_time':round(bt,3),'_lineIndex':lanes[0],'_lineLayer':layer,'_type':0,'_cutDirection':cut},
        {'_time':round(bt,3),'_lineIndex':lanes[1],'_lineLayer':layer,'_type':1,'_cutDirection':cut},
    ]

def add_phrase_arc(notes, bt, kind, strength, rng, phrase_idx):
    """A tiny musical phrase gesture, not spam: note then delayed response."""
    if strength < .68: return
    lane=[0,1,2,3,2,1][phrase_idx%6]
    color=phrase_idx%2
    layer=2 if 'high' in kind else 0 if 'bass' in kind else 1
    cut=[1,5,3,4,2,1][phrase_idx%6]
    notes.append({'_time':round(bt+0.5,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':cut})

def choose_weighted(items, rng):
    if not items:
        return None
    total=sum(float(x.get('count',0)) for x in items) or 1
    r=rng.random()*total
    acc=0
    for x in items:
        acc+=float(x.get('count',0))
        if acc>=r:
            return x.get('token')
    return items[0].get('token')

def token_to_notes(tok, beat_time):
    notes=[]
    if not tok or tok=='REST': return notes
    for part in tok.split('|')[:4]:
        try:
            c,x,y,d=[int(v) for v in part.split(':')]
            if c in (0,1) and 0<=x<=3 and 0<=y<=2 and 0<=d<=8:
                notes.append({'_time':round(beat_time,3),'_lineIndex':x,'_lineLayer':y,'_type':c,'_cutDirection':d})
        except Exception:
            continue
    return notes

def learned_notes_for_beats(beats, bpm, bucket='expertplus'):
    model=load_pattern_model()
    if not model:
        return None
    rng=random.Random(1337 + int(bpm*10) + len(beats))
    diff=model.get('difficultyBuckets',{}).get(bucket) or model.get('difficultyBuckets',{}).get('expert') or {}
    transitions=diff.get('transitions') or model.get('global',{}).get('transitions',{})
    starters=diff.get('patterns') or model.get('global',{}).get('starters',[])
    prev='START'; notes=[]
    for idx,t in enumerate(beats):
        bt=t*bpm/60
        
        if not is_musically_active(t, analysis, radius=0.34):
            continue
        sec=local_section(sections, t)
        policy=dynamic_note_policy(sec, bpm, options)
        dynamic_policies.append(policy)
        local_gap=policy['gap']; local_max_sim=policy['maxSim']; local_intensity=policy['intensity']
        opts=transitions.get(prev) or transitions.get('START') or starters
        tok=choose_weighted(opts, rng)
        if not tok: tok=choose_weighted(model.get('global',{}).get('patterns',[]), rng)
        ns=token_to_notes(tok, bt)
        if not ns:
            ns=[{'_time':round(bt,3),'_lineIndex':idx%4,'_lineLayer':(idx//4)%3,'_type':idx%2,'_cutDirection':1}]
        # avoid huge impossible stacks by limiting to 2 notes most of the time
        if len(ns)>2 and rng.random()<0.75:
            ns=ns[:2]
        notes.extend(ns)
        prev=tok
    return notes


def read_wav(path: Path):
    with wave.open(str(path),'rb') as w:
        sr=w.getframerate(); ch=w.getnchannels(); sw=w.getsampwidth(); n=w.getnframes(); raw=w.readframes(n)
    if sw == 1:
        arr=(np.frombuffer(raw, dtype=np.uint8).astype(np.float32)-128.0)/128.0
    elif sw == 2:
        arr=np.frombuffer(raw, dtype='<i2').astype(np.float32)/32768.0
    elif sw == 3:
        b=np.frombuffer(raw, dtype=np.uint8).reshape(-1,3)
        vals=(b[:,0].astype(np.int32) | (b[:,1].astype(np.int32)<<8) | (b[:,2].astype(np.int32)<<16))
        vals=np.where(vals & 0x800000, vals | ~0xffffff, vals)
        arr=vals.astype(np.float32)/8388608.0
    elif sw == 4:
        arr=np.frombuffer(raw, dtype='<i4').astype(np.float32)/2147483648.0
    else:
        raise HTTPException(400, f'Unsupported WAV sample width: {sw}')
    if ch>1: arr=arr.reshape(-1,ch).mean(axis=1)
    return arr, sr

def ensure_wav(src: Path, tmp: Path):
    if src.suffix.lower()=='.wav': return src
    out=tmp/'audio.wav'
    try:
        subprocess.check_call(['ffmpeg','-y','-i',str(src),'-ac','1','-ar','44100',str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out
    except Exception:
        raise HTTPException(400,'Upload WAV, or install ffmpeg for mp3/ogg conversion')

def analyze_audio(samples, sr):
    hop=512; frame=2048
    if len(samples)<frame: raise HTTPException(400,'Audio is too short')
    rms=[]; times=[]
    for i in range(0,len(samples)-frame,hop):
        x=samples[i:i+frame]
        rms.append(float(np.sqrt(np.mean(x*x))))
        times.append(i/sr)
    rms=np.array(rms); times=np.array(times)
    smooth=np.convolve(rms, np.ones(7)/7, mode='same')
    flux=np.maximum(0, smooth-np.r_[smooth[0], smooth[:-1]])
    thresh=np.percentile(flux, 78)
    peaks=[]; last=-999
    for i in range(1,len(flux)-1):
        if flux[i]>thresh and flux[i]>=flux[i-1] and flux[i]>=flux[i+1] and times[i]-last>0.18:
            peaks.append(float(times[i])); last=times[i]
    intervals=np.diff(peaks[:160]) if len(peaks)>8 else np.array([])
    bpm=120
    if len(intervals):
        med=float(np.median(intervals))
        if med>0: bpm=max(70,min(220,60/med))
        while bpm<90: bpm*=2
        while bpm>210: bpm/=2
    duration=len(samples)/sr
    
    strengths=[]
    max_flux=float(np.max(flux)) or 1.0
    for t in peaks[:2000]:
        idx=int(np.argmin(np.abs(times-t)))
        strengths.append(float(min(1.0, flux[idx]/max_flux)))

    # Deeper tone mapping: separate bass, vocal/mid, and high-energy changes.
    # This is intentionally dependency-light: short FFT windows, band energy flux, then peak pick.
    band_times=[]; bass=[]; vocal=[]; high=[]
    fft_frame=4096; fft_hop=1024
    freqs=np.fft.rfftfreq(fft_frame, 1/sr)
    bass_mask=(freqs>=35)&(freqs<180)
    vocal_mask=(freqs>=220)&(freqs<3400)
    high_mask=(freqs>=3400)&(freqs<9000)
    for i in range(0, len(samples)-fft_frame, fft_hop):
        win=samples[i:i+fft_frame]*np.hanning(fft_frame)
        mag=np.abs(np.fft.rfft(win))
        band_times.append(i/sr)
        bass.append(float(np.mean(mag[bass_mask])) if np.any(bass_mask) else 0)
        vocal.append(float(np.mean(mag[vocal_mask])) if np.any(vocal_mask) else 0)
        high.append(float(np.mean(mag[high_mask])) if np.any(high_mask) else 0)
    band_times=np.array(band_times); bass=np.array(bass); vocal=np.array(vocal); high=np.array(high)
    def band_peaks(arr, pct=82, gap=0.16):
        if len(arr)<5: return [], []
        sm=np.convolve(arr, np.ones(5)/5, mode='same')
        fl=np.maximum(0, sm-np.r_[sm[0], sm[:-1]])
        th=np.percentile(fl, pct)
        out=[]; st=[]; last=-999
        mx=float(np.max(fl)) or 1.0
        for i in range(1,len(fl)-1):
            if fl[i]>th and fl[i]>=fl[i-1] and fl[i]>=fl[i+1] and band_times[i]-last>gap:
                out.append(float(band_times[i])); st.append(float(min(1, fl[i]/mx))); last=band_times[i]
        return out[:2500], st[:2500]
    bass_peaks,bass_strengths=band_peaks(bass,84,0.22)
    vocal_peaks,vocal_strengths=band_peaks(vocal,78,0.14)
    high_peaks,high_strengths=band_peaks(high,86,0.12)
    return {'duration':duration,'bpm':round(bpm,1),'beats':peaks[:2000], 'beatStrengths':strengths,
            'bassBeats':bass_peaks,'bassStrengths':bass_strengths,
            'vocalBeats':vocal_peaks,'vocalStrengths':vocal_strengths,
            'highBeats':high_peaks,'highStrengths':high_strengths,
            'energy':float(np.mean(rms)), 'peakEnergy':float(np.max(rms))}

def normalize_pattern(tok):
    ns = token_to_notes(tok, 0)
    # Ranked corpus sometimes has huge stacks. Keep realistic human-readable chunks.
    seen=set(); out=[]
    for n in ns:
        cell=(n['_lineIndex'],n['_lineLayer'])
        if cell in seen: continue
        seen.add(cell); out.append(n)
        if len(out)>=2: break
    return out

def mirror_token_notes(ns):
    mirrored=[]
    for n in ns:
        m=dict(n)
        m['_lineIndex']=3-int(m.get('_lineIndex',0))
        cd=int(m.get('_cutDirection',8))
        flip={2:3,3:2,4:5,5:4,6:7,7:6}
        m['_cutDirection']=flip.get(cd,cd)
        mirrored.append(m)
    return mirrored

def add_notes_at(out, template, beat_time):
    used={(round(n['_time'],3), n['_lineIndex'], n['_lineLayer']) for n in out}
    added=0
    for n in template:
        nn=dict(n); nn['_time']=round(beat_time,3)
        key=(nn['_time'], nn['_lineIndex'], nn['_lineLayer'])
        if key in used: continue
        used.add(key); out.append(nn); added+=1
    return added


def make_flow_note(time, idx, strength, rng, color=None):
    lane_pattern=[1,2,0,3,1,2,3,0]
    layer_pattern=[1,1,0,2,2,0,1,1]
    cut_pattern=[1,1,3,2,5,4,0,1]
    return {'_time':round(time,3),'_lineIndex':lane_pattern[idx%len(lane_pattern)],'_lineLayer':layer_pattern[idx%len(layer_pattern)],'_type':rng.randrange(2) if color is None else color,'_cutDirection':cut_pattern[idx%len(cut_pattern)]}

def add_fun_stream(notes, bt, idx, rng, strength, length=4):
    # Short ranked-style stream across lanes with alternating colors.
    step=0.125 if strength>0.65 else 0.25
    for k in range(length):
        n=make_flow_note(bt+k*step, idx+k, strength, rng, color=(idx+k)%2)
        notes.append(n)

def add_big_double(notes, bt, rng, cut=1):
    layer=rng.choice([0,1,1,2])
    notes.append({'_time':round(bt,3),'_lineIndex':1,'_lineLayer':layer,'_type':0,'_cutDirection':cut})
    notes.append({'_time':round(bt,3),'_lineIndex':2,'_lineLayer':layer,'_type':1,'_cutDirection':cut})



def is_musically_active(t, analysis, radius=0.28):
    # True only near detected beat/tone events. Prevents blocks in quiet/no-beat space.
    pools=(analysis.get('beats') or [])+(analysis.get('vocalBeats') or [])+(analysis.get('bassBeats') or [])+(analysis.get('highBeats') or [])
    return any(abs(t-x)<=radius for x in pools)

def learned_phrase_token(transitions, patterns, global_patterns, prev, rng, kind, strength):
    # Use training data, but only choose complex patterns for musically meaningful events.
    opts=transitions.get(prev) or transitions.get('START') or patterns or global_patterns
    tok=choose_weighted(opts, rng)
    if strength < .55 and kind in ('flow','beat'):
        # soft/connector events should be simple single notes, not ranked chaos.
        return None
    return tok

def merge_tone_events(analysis, bpm, max_gap_beats=1.0):
    """Create a readable default timeline from vocal/mid peaks with bass/high accents.
    Vocal/mid = main notes. Bass = anchor/doubles. High = small accents only when spaced.
    """
    raw=list(zip(analysis.get('beats') or [], analysis.get('beatStrengths') or []))
    vocal=list(zip(analysis.get('vocalBeats') or [], analysis.get('vocalStrengths') or []))
    bass=list(zip(analysis.get('bassBeats') or [], analysis.get('bassStrengths') or []))
    high=list(zip(analysis.get('highBeats') or [], analysis.get('highStrengths') or []))
    main=vocal if len(vocal)>=8 else raw
    events=[]
    for t,st in main:
        if st >= 0.18: events.append({'time':float(t),'strength':float(st),'kind':'vocal','priority':3})
    for t,st in bass:
        if st >= 0.32: events.append({'time':float(t),'strength':float(st),'kind':'bass','priority':4})
    for t,st in high:
        # highs are accents only, not primary spam
        if st>0.62:
            events.append({'time':float(t),'strength':float(st),'kind':'high','priority':2})
    if not events:
        return [{'time':t,'strength':st or .5,'kind':'beat','priority':1} for t,st in raw]
    events.sort(key=lambda e:(e['time'],-e['priority']))
    min_gap=60/max(bpm,1)*1.05  # roughly 3/8 beat, keeps normal mode spaced/readable
    merged=[]
    for e in events:
        if not merged or e['time']-merged[-1]['time']>=min_gap:
            merged.append(e)
        else:
            # Preserve duplicate musical roles. If bass/vocal/high land together, keep a combined
            # state AND, for strong secondary roles, add a nearby follow-up instead of dropping it.
            cur=merged[-1]
            cur['kind']=cur['kind']+'+'+e['kind'] if e['kind'] not in cur['kind'] else cur['kind']
            cur['strength']=max(cur['strength'],e['strength'])
            if e['strength']>.62 and e['priority']>=2:
                ee=dict(e)
                ee['time']=cur['time'] + min_gap*.55
                ee['kind']='duplicate-'+e['kind']
                merged.append(ee)
    # fill large gaps with beat-grid connective notes so flow does not die
    beat_gap=60/max(bpm,1)*max_gap_beats
    filled=[]
    raw_times=[t for t,_ in raw]
    for i,e in enumerate(merged):
        filled.append(e)
        if i < len(merged)-1 and merged[i+1]['time']-e['time']>beat_gap*1.35:
            mid=e['time']+beat_gap
            # prefer actual raw beat near the gap if available
            near=min(raw_times, key=lambda x:abs(x-mid)) if raw_times else mid
            if e['time']+min_gap < near < merged[i+1]['time']-min_gap and any(abs(near-r)<=min_gap for r in raw_times):
                filled.append({'time':near,'strength':0.38,'kind':'flow','priority':1})
    return filled[:2600]



def enforce_dynamic_spacing(notes, bpm, sections, options, normal=True):
    notes=sorted(notes, key=lambda n:(n.get('_time',0), n.get('_type',0)))
    cleaned=[]; last=-999; last_color={0:-999,1:-999}; max_opt=int(options.get('maxSimultaneous',1))
    for n in notes:
        if n.get('_type') not in (0,1,3): continue
        sec_time=float(n.get('_time',0))*60/max(bpm,1)
        pol=dynamic_note_policy(local_section(sections, sec_time), bpm, options)
        gap=pol['gap']; max_sim=min(max_opt, pol['maxSim']) if normal else min(max_opt, max(1,pol['maxSim']))
        t=round(round(float(n.get('_time',0))/gap)*gap,3)
        same=[x for x in cleaned if abs(x['_time']-t)<0.001]
        if len(same)>=max_sim: continue
        if normal and n.get('_type') in (0,1) and t-last_color.get(n.get('_type'),-999)<gap*.9: continue
        if any(x.get('_lineIndex')==n.get('_lineIndex') and x.get('_lineLayer')==n.get('_lineLayer') for x in same): continue
        nn=dict(n); nn['_time']=t; cleaned.append(nn)
        if nn.get('_type') in (0,1): last_color[nn.get('_type')]=t
        last=t
    return cleaned


def beatsaber_state_token(note):
    return f"{int(note.get('_type',0))}:{int(note.get('_lineIndex',0))}:{int(note.get('_lineLayer',0))}:{int(note.get('_cutDirection',8))}"

def quantize_to_state_grid(notes, bpm, mode='normal'):
    """DeepSaber-inspired state-space cleanup.
    Beat Saber maps become easier to read when notes live on a consistent beat grid and
    transition between compact states. This snaps timing and repairs awkward cells/cuts.
    """
    grid = 0.5 if mode == 'normal' else 0.25 if mode == 'fun' else 0.125
    allowed_cuts=[0,1,2,3,4,5,6,7,8]
    cleaned=[]; occupied=set(); last_color_cell={0:None,1:None}
    for n in sorted(notes, key=lambda x:(x.get('_time',0), x.get('_type',0), x.get('_lineIndex',0))):
        nn=dict(n)
        tm=round(round(float(nn.get('_time',0))/grid)*grid,3)
        typ=int(nn.get('_type',0))
        lane=max(0,min(3,int(nn.get('_lineIndex',0))))
        layer=max(0,min(2,int(nn.get('_lineLayer',0))))
        cut=int(nn.get('_cutDirection',8))
        if cut not in allowed_cuts: cut=8
        # Avoid repeating same hand same exact cell too often. Move one lane if needed.
        if typ in (0,1) and last_color_cell.get(typ)==(lane,layer):
            lane = (lane + (1 if lane < 2 else -1)) % 4
        key=(tm,lane,layer,typ)
        if key in occupied: continue
        occupied.add(key)
        nn.update({'_time':tm,'_lineIndex':lane,'_lineLayer':layer,'_type':typ,'_cutDirection':cut})
        if typ in (0,1): last_color_cell[typ]=(lane,layer)
        cleaned.append(nn)
    cleaned=repair_same_time_collisions(cleaned)
    return cleaned, {'stateGrid':grid,'stateCount':len(set(beatsaber_state_token(n) for n in cleaned if n.get('_type') in (0,1)))}


def cap_to_target_nps(notes, analysis, options):
    target=float(options.get('targetNps',0) or 0)
    if target<=0: return notes
    duration=max(1,float(analysis.get('duration') or 1))
    max_notes=max(1,int(target*duration))
    color=[n for n in notes if n.get('_type') in (0,1)]
    other=[n for n in notes if n.get('_type') not in (0,1)]
    if len(color)<=max_notes: return notes
    # Prefer stronger musical positions by keeping evenly across time, not just first N.
    groups=[]
    by={}
    for n in sorted(color,key=lambda n:n['_time']): by.setdefault(n['_time'],[]).append(n)
    for t in sorted(by): groups.append(by[t])
    # Cap by musical time states, preserving simultaneous doubles within kept states.
    max_states=max(1, int(max_notes / max(1.2, sum(len(g) for g in groups)/max(1,len(groups)))))
    if len(groups)<=max_states: return notes
    step=len(groups)/max_states
    keep=[]; idx=0.0
    while int(idx)<len(groups) and len(keep)<max_notes:
        keep.extend(groups[int(idx)][:2]); idx+=step
    return sorted(keep+other, key=lambda n:(n.get('_time',0),n.get('_type',0)))

def beat_alignment_metrics(notes, analysis, bpm):
    beat_times=[t*bpm/60 for t in (analysis.get('beats') or [])]
    if not beat_times: return {'alignment':None}
    color=[n for n in notes if n.get('_type') in (0,1)]
    if not color: return {'alignment':0}
    close=0; distances=[]
    for n in color:
        d=min(abs(n['_time']-b) for b in beat_times)
        distances.append(d)
        if d<=0.25: close+=1
    return {'alignment':round(close/len(color),3),'avgBeatDistance':round(float(sum(distances)/len(distances)),3)}

def enforce_readable_spacing(notes, bpm, max_simul=1, normal=True, min_gap_beats=None):
    """Keep blocks readable: no excessive near-time clusters, preserve strongest flow."""
    min_step = float(min_gap_beats) if min_gap_beats is not None else (1.25 if normal else 0.5)  # beats between note groups
    notes=sorted(notes, key=lambda n:(n.get('_time',0), n.get('_type',0), n.get('_lineIndex',0)))
    groups={}
    for n in notes:
        if n.get('_type') not in (0,1,3): continue
        q=round(float(n.get('_time',0))/min_step)*min_step
        groups.setdefault(q, []).append(n)
    cleaned=[]; last_time_by_color={0:-999,1:-999}
    for t in sorted(groups):
        group=groups[t]
        color_notes=[n for n in group if n.get('_type') in (0,1)]
        bombs=[n for n in group if n.get('_type')==3]
        # choose spatially separated notes first
        chosen=[]; used_cells=set(); used_colors=set()
        for n in color_notes:
            c=n.get('_type'); cell=(n.get('_lineIndex'),n.get('_lineLayer'))
            if cell in used_cells: continue
            if normal and t-last_time_by_color.get(c,-999)<min_step*.9: continue
            if normal and c in used_colors and max_simul<=2: continue
            nn=dict(n); nn['_time']=round(t,3)
            chosen.append(nn); used_cells.add(cell); used_colors.add(c); last_time_by_color[c]=t
            if len(chosen)>=max_simul: break
        cleaned.extend(chosen)
        if not normal and bombs and len(chosen)<max_simul:
            b=dict(bombs[0]); b['_time']=round(t,3); cleaned.append(b)
    return cleaned


def generate_direct_instrument_arrangement(analysis, bpm, options=None):
    """Abstract conductor mode.
    Instead of maximizing playable density, this maps musical roles to gestures:
    bass = grounded down/side anchors, vocal/mid = main conducting phrase, highs = lift/flick accents.
    The result is intentionally spacious and readable, like cueing live instrumentalists.
    """
    options=options or {}
    rng=random.Random(int(options.get('seed',4242)) + int(bpm*31))
    events=merge_tone_events(analysis, bpm, max_gap_beats=float(options.get('phraseGapBeats',3.25)))
    notes=[]; bombs=[]; walls=[]; lights=[]
    phrase=0; last_t=-999
    for i,e in enumerate(events):
        t=e['time']; st=e['strength']; kind=e['kind']; bt=t*bpm/60
        if t-last_t < (60/max(bpm,1))*0.9:
            continue
        last_t=t
        # Phrase lanes sweep left-to-right then right-to-left, like conductor hand motion.
        lane=[0,1,2,3,2,1][phrase%6]
        phrase += 1
        layer=1
        color=0 if phrase%2 else 1
        cut=1  # down by default, clear cue
        if 'bass' in kind:
            layer=0; cut=rng.choice([0,1]); lane=rng.choice([0,1,2,3])
            # bass can become a grounded two-hand cue if user allows doubles
            if options.get('doubles', True) and int(options.get('maxSimultaneous',1))>=2 and st>0.65:
                notes.append({'_time':round(bt,3),'_lineIndex':1,'_lineLayer':0,'_type':0,'_cutDirection':cut})
                notes.append({'_time':round(bt,3),'_lineIndex':2,'_lineLayer':0,'_type':1,'_cutDirection':cut})
            else:
                notes.append({'_time':round(bt,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':cut})
            lights.append({'_time':round(bt,3),'_type':0,'_value':5})
        elif 'high' in kind:
            layer=2; cut=rng.choice([4,5,2,3]); lane=rng.choice([0,3,1,2])
            notes.append({'_time':round(bt,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':cut})
            lights.append({'_time':round(bt,3),'_type':1,'_value':7})
        else:
            # vocal/mid phrase, smooth alternating conducting gestures
            cut=[1,5,3,4,2,1][phrase%6]
            notes.append({'_time':round(bt,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':cut})
            # longer vocal emphasis gets a gentle follow-through note, spaced and same hand flow
            if st>0.72 and options.get('subdivisions', True):
                notes.append({'_time':round(bt+0.75,3),'_lineIndex':max(0,min(3,lane+(1 if lane<2 else -1))),'_lineLayer':layer,'_type':1-color,'_cutDirection':cut})
            lights.append({'_time':round(bt,3),'_type':0,'_value':3})
        # sparse walls as measure/section markers, not obstacles spam
        if options.get('walls', True) and i>0 and i%18==0:
            walls.append({'_time':round(bt,3),'_lineIndex':0 if phrase%2 else 3,'_type':1,'_duration':2.0,'_width':1})
    max_simul=max(1,min(2,int(options.get('maxSimultaneous',1))))
    notes=enforce_dynamic_spacing(notes, bpm, section_energy_profile(analysis,4.0), options, normal=True)
    notes,state_meta=quantize_to_state_grid(notes,bpm,'normal')
    notes=cap_to_target_nps(notes, analysis, options)
    align_meta=beat_alignment_metrics(notes, analysis, bpm)
    return notes, bombs, walls, lights, {'engine':'direct-instrument-stategrid-v2','normalMode':True,'gestureCount':len(notes),**state_meta,**align_meta,'modelVersion':1,'options':options}


def section_energy_profile(analysis, window=4.0):
    duration=max(1,float(analysis.get('duration') or 1))
    sections=[]; t=0.0
    vocal=analysis.get('vocalBeats') or []; bass=analysis.get('bassBeats') or []; high=analysis.get('highBeats') or []; beats=analysis.get('beats') or []
    while t<duration:
        end=t+window
        vc=sum(1 for x in vocal if t<=x<end); bc=sum(1 for x in bass if t<=x<end); hc=sum(1 for x in high if t<=x<end); rc=sum(1 for x in beats if t<=x<end)
        activity=(vc*1.0+bc*1.25+hc*.65+rc*.45)/window
        sections.append({'start':t,'end':end,'vocalRate':vc/window,'bassRate':bc/window,'highRate':hc/window,'beatRate':rc/window,'activity':activity})
        t=end
    maxa=max([x['activity'] for x in sections] or [1]) or 1
    for x in sections:
        x['intensity']=min(1.0,x['activity']/maxa)
    return sections

def local_section(sections, t):
    if not sections: return {'intensity':.5,'vocalRate':0,'bassRate':0,'highRate':0,'beatRate':0}
    idx=min(len(sections)-1, max(0, int(t/ max(.001, sections[0]['end']-sections[0]['start']))))
    return sections[idx]

def dynamic_note_policy(sec, bpm, options):
    density=float(options.get('density',0.48)); streams=float(options.get('streams',0.18))
    intensity=sec.get('intensity',.5)
    tempo_factor=min(1.35,max(.75,bpm/140))
    # Abstract policy: high intensity permits closer spacing, low intensity breathes.
    base_gap=float(options.get('targetGapBeats') or (2.35 if density<=.6 else 1.65 if density<=1.2 else .85))
    gap=base_gap-(intensity*.28)-(streams*.10)
    gap=max(0.875 if density<=.6 else .5 if density<=1.2 else .25, gap/tempo_factor)
    max_sim=1
    if density>.32 and intensity>.35: max_sim=2
    if density>1.4 and intensity>.60: max_sim=3
    if density>1.8 and intensity>.78: max_sim=min(5,int(options.get('maxSimultaneous',4)))
    # More speed/read distance in intense/fast sections.
    njs=(float(options.get('autoNjs',12)) + intensity*2.2 + max(0,bpm-150)/35)
    return {'gap':round(gap,3),'maxSim':max_sim,'njs':round(njs,2),'intensity':round(intensity,3)}


def maybe_add_stab_dot(notes, bt, kind, strength, rng, options):
    """Rare dot note: Beat Saber cutDirection 8, visualized as a stab/poke target in preview."""
    if not options.get('stabDots', True):
        return
    density=float(options.get('density',0.34))
    # Rare by default, more likely on high/vocal accents and in overkill settings.
    chance=0.025 + max(0,density-1.0)*0.025
    if 'high' in kind: chance += 0.035
    if 'vocal' in kind and strength>.78: chance += 0.02
    if strength < .68 or rng.random() > min(.12,chance):
        return
    lane=rng.choice([1,2,0,3])
    layer=rng.choice([1,1,2])
    color=rng.randrange(2)
    notes.append({'_time':round(bt,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':8})


# --- Choreography layer: Beat Saber mapping philosophy encoded as rules ---
CUT_VEC = {0:(0,1),1:(0,-1),2:(-1,0),3:(1,0),4:(-1,1),5:(1,1),6:(-1,-1),7:(1,-1),8:(0,0)}

def opposite_cut(c):
    return {0:1,1:0,2:3,3:2,4:7,5:6,6:5,7:4}.get(c,8)

def role_from_kind(kind):
    if 'bass' in kind: return 'bass'
    if 'high' in kind: return 'high'
    if 'vocal' in kind: return 'vocal'
    if 'flow' in kind: return 'flow'
    return 'beat'

def choose_choreo_note(bt, kind, strength, hand, prev_note, phrase_idx, rng):
    """Translate musical role into physical choreography.
    bass => heavy grounded down/up cuts
    high => light side/diagonal flicks
    vocal => smooth arcs and continued hand flow
    flow/beat => readable alternating anchors
    """
    role=role_from_kind(kind)
    typ=hand
    # Continue from previous hand motion if possible.
    if prev_note:
        prev_cut=int(prev_note.get('_cutDirection',1))
        vx,vy=CUT_VEC.get(prev_cut,(0,-1))
        prev_lane=int(prev_note.get('_lineIndex',1)); prev_layer=int(prev_note.get('_lineLayer',1))
        lane=max(0,min(3,prev_lane+vx))
        layer=max(0,min(2,prev_layer+vy))
        # Avoid wrist reversal unless using a dot reset or impact accent.
        forbidden=opposite_cut(prev_cut)
    else:
        lane=[1,2,0,3,1,2][phrase_idx%6]
        layer=1
        forbidden=None
    if role=='bass':
        lane=rng.choice([1,2]) if strength>.55 else lane
        layer=0
        cuts=[1,1,0,4,5]  # heavy down mostly
    elif role=='high':
        layer=2
        lane=rng.choice([0,3,1,2])
        cuts=[2,3,4,5]
    elif role=='vocal':
        # smooth curved phrase motion, alternating diagonal/down directions
        cuts=[1,5,3,4,2,1]
        lane=[0,1,2,3,2,1][phrase_idx%6]
        layer=[1,1,2,2,1,0][phrase_idx%6]
    elif role=='flow':
        cuts=[1,3,1,2,1]
        layer=1
    else:
        cuts=[1,4,5,2,3]
    cut=rng.choice(cuts) if role in ('bass','high','beat','flow') else cuts[phrase_idx%len(cuts)]
    if forbidden is not None and cut==forbidden and strength<.78:
        # use dot reset instead of awkward reversal
        cut=8 if rng.random()<.45 else rng.choice([c for c in cuts if c!=forbidden] or [1])
    return {'_time':round(bt,3),'_lineIndex':lane,'_lineLayer':layer,'_type':typ,'_cutDirection':cut}

def apply_choreography(notes, tone_events, bpm, rng, options):
    """Rewrite/augment generated notes into coherent body-motion phrases.
    This keeps musical anchors but improves hand flow and role meaning.
    """
    density=float(options.get('density',0.34))
    max_sim=int(options.get('maxSimultaneous',2))
    prev={0:None,1:None}
    out=[]
    hand=0
    # Map events to nearest generated time, then choose role-aware notes.
    for idx,e in enumerate(tone_events):
        bt=e['time']*bpm/60
        strength=e.get('strength',.5); kind=e.get('kind','beat')
        # alternating hand unless stereo/role suggests a double
        hand=1-hand
        n=choose_choreo_note(bt, kind, strength, hand, prev.get(hand), idx, rng)
        out.append(n); prev[hand]=n
        role=role_from_kind(kind)
        # Intelligent simultaneous states: bass impacts, strong centered accents, or layered vocal+bass.
        if max_sim>=2 and (('bass' in kind and strength>.58) or ('bass' in kind and 'vocal' in kind) or (strength>.86 and density>.8)):
            other=1-hand
            dn=choose_choreo_note(bt, kind, strength, other, prev.get(other), idx+1, rng)
            # force readable side-by-side if both land same cell
            if dn['_lineIndex']==n['_lineIndex'] and dn['_lineLayer']==n['_lineLayer']:
                n['_lineIndex'], dn['_lineIndex'] = 1,2
                dn['_lineLayer']=n['_lineLayer']
            out.append(dn); prev[other]=dn
        # Sustained vocal/high intensity: one follow-through, not spam.
        if role=='vocal' and strength>.72 and density>.45:
            fn=choose_choreo_note(bt+0.5, kind, strength*.85, 1-hand, prev.get(1-hand), idx+2, rng)
            out.append(fn); prev[1-hand]=fn
        # high accents sometimes use dot reset to free momentum.
        if role=='high' and strength>.72 and options.get('stabDots',True):
            if rng.random()<.18+max(0,density-1)*.05:
                dot=choose_choreo_note(bt, kind, strength, hand, prev.get(hand), idx, rng)
                dot['_cutDirection']=8
                out.append(dot); prev[hand]=dot
    return repair_same_time_collisions(out)

def generate_overkill_arrangement(analysis, bpm, options=None):
    options = options or {}
    model=load_pattern_model()
    raw_beats=analysis.get('beats') or []
    vocal_beats=analysis.get('vocalBeats') or []
    bass_beats=analysis.get('bassBeats') or []
    high_beats=analysis.get('highBeats') or []
    tone_events=merge_tone_events(analysis, bpm, max_gap_beats=float(options.get('phraseGapBeats', options.get('normalFlowGapBeats',2.25))))
    beats=[e['time'] for e in tone_events]
    strengths=[e['strength'] for e in tone_events]
    kinds=[e['kind'] for e in tone_events]
    bass_set=set(round(t,2) for t in bass_beats)
    high_set=set(round(t,2) for t in high_beats)
    sections=section_energy_profile(analysis, window=4.0)
    dynamic_policies=[]
    rng=random.Random(int(options.get('seed',9001)) + int(bpm*100) + len(beats))
    if not model:
        return None
    buckets=model.get('difficultyBuckets',{})
    # Expert+ base, fallback to expert/global.
    bucket=buckets.get('expertplus') or buckets.get('expert') or {}
    transitions=bucket.get('transitions') or model.get('global',{}).get('transitions',{})
    patterns=bucket.get('patterns') or model.get('global',{}).get('patterns',[])
    global_patterns=model.get('global',{}).get('patterns',[])
    notes=[]; bombs=[]; walls=[]; events=[]; prev='START'
    density=(0.72 + min(0.42, float(analysis.get('peakEnergy',0))*0.7)) * float(options.get('density',0.48))
    stream_mul=float(options.get('streams',1.0)); doubles_on=bool(options.get('doubles',True)); bombs_on=bool(options.get('bombs',True)); walls_on=bool(options.get('walls',True)); lights_on=bool(options.get('lights',True)); subdivisions=bool(options.get('subdivisions',True)); max_simul=int(options.get('maxSimultaneous',4)); min_density=bool(options.get('minDensity',True))
    last_side=None
    for i,t in enumerate(beats):
        strength=strengths[i] if i<len(strengths) else 0.5
        kind=kinds[i] if i<len(kinds) else 'vocal'
        bt=t*bpm/60
        
        if not is_musically_active(t, analysis, radius=0.34):
            continue
        sec=local_section(sections, t)
        policy=dynamic_note_policy(sec, bpm, options)
        dynamic_policies.append(policy)
        local_gap=policy['gap']; local_max_sim=policy['maxSim']; local_intensity=policy['intensity']
        opts=transitions.get(prev) or transitions.get('START') or patterns or global_patterns
        tok=learned_phrase_token(transitions, patterns, global_patterns, prev, rng, kind, strength) or None
        tmpl=normalize_pattern(tok) if tok else []
        if not tmpl:
            # Realistic simple note based on phrase/tone role.
            lane=[1,2,0,3,1,2][i%6]; layer=0 if 'bass' in kind else 2 if 'high' in kind else 1
            cut=0 if 'bass' in kind else rng.choice([2,3,4,5]) if 'high' in kind else [1,5,3,4,2,1][i%6]
            tmpl=[{'_time':0,'_lineIndex':lane,'_lineLayer':layer,'_type':i%2,'_cutDirection':cut}]
        # Alternate/mirror sometimes to create flow instead of same-pattern spam.
        if i%2 and rng.random()<0.55:
            tmpl=mirror_token_notes(tmpl)
        add_notes_at(notes, tmpl, bt)
        # Learned state-space layer: occasional two-hand states where ranked maps and the audio both justify it.
        if doubles_on and max(max_simul, local_max_sim) >= 2 and rng.random() < simultaneous_probability(options, kind, strength, local_intensity):
            for dn in make_intelligent_double(bt, kind, strength, rng, i):
                notes.append(dn)
        elif doubles_on and max(max_simul, local_max_sim) >= 2 and (('bass' in kind and strength > 0.7) or (strength > 0.90 and i % 12 == 0)):
            add_big_double(notes, bt, rng, cut=rng.choice([0,1,4,5]))
        add_phrase_arc(notes, bt, kind, strength, rng, i)
        maybe_add_stab_dot(notes, bt, kind, strength, rng, options)
        # Fun layer: strong readable doubles and short streams, inspired by ranked corpus density.
        if max_simul>=2 and subdivisions and strength > max(0.80,0.95-local_intensity*.16) and rng.random() < (0.018+local_intensity*.05) * density * stream_mul:
            add_fun_stream(notes, bt+0.125, i, rng, strength, length=rng.choice([3,4,5]))
        elif max_simul>=2 and subdivisions and strength > max(0.76,0.92-local_intensity*.18) and rng.random() < (0.010+local_intensity*.03) * density * stream_mul:
            add_fun_stream(notes, bt+0.25, i, rng, strength, length=2)
        # Strong beats get learned echo/subdivision patterns. This is where it becomes overkill.
        if subdivisions and strength>max(0.76,0.9-local_intensity*.2) and rng.random()<(0.025+local_intensity*.06)*density:
            tok2=choose_weighted(transitions.get(tok) or patterns or global_patterns, rng)
            tmpl2=normalize_pattern(tok2)
            if tmpl2:
                add_notes_at(notes, mirror_token_notes(tmpl2) if rng.random()<0.45 else tmpl2, bt+0.25)
        if subdivisions and strength>max(0.82,0.94-local_intensity*.16) and rng.random()<(0.012+local_intensity*.035)*density:
            tok3=choose_weighted(patterns or global_patterns, rng)
            tmpl3=normalize_pattern(tok3)
            if tmpl3:
                add_notes_at(notes, tmpl3[:1], bt+0.5)
        if subdivisions and ('high' in kind) and strength>0.74 and rng.random()<0.05*density:
            # Controlled burst, never more than one extra at 1/8 grid.
            lane=rng.randrange(4); layer=rng.randrange(3); color=rng.randrange(2)
            notes.append({'_time':round(bt+0.125,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':rng.choice([0,1,2,3,4,5])})
        # Bombs and walls are sparse, used as accent/obstacle information.
        if bombs_on and i>8 and i%24==0 and strength>0.4:
            occupied={(n['_lineIndex'],n['_lineLayer']) for n in notes if abs(n['_time']-round(bt,3))<0.01}
            candidates=[x for x in range(4) if (x,1) not in occupied]
            if candidates:
                bombs.append({'_time':round(bt+0.5,3),'_lineIndex':rng.choice(candidates),'_lineLayer':1,'_type':3,'_cutDirection':0})
        if walls_on and i>16 and i%48==0:
            walls.append({'_time':round(bt,3),'_lineIndex':rng.choice([0,3]),'_type':1,'_duration':round(rng.choice([1.0,1.5,2.0]),2),'_width':1})
        if lights_on and i%4==0:
            events.append({'_time':round(bt,3),'_type':0,'_value':rng.choice([1,5,7])})
        if lights_on and i%8==0:
            events.append({'_time':round(bt,3),'_type':1,'_value':rng.choice([1,5,6])})
        prev=tok
    # Minimum fun-density pass: if the song has sparse detected beats, add safe connective notes between beats.
    if min_density and len(beats) > 1:
        for i in range(len(beats)-1):
            a=beats[i]*bpm/60; b=beats[i+1]*bpm/60
            if b-a > 2.0 and rng.random() < 0.10 * density:
                notes.append(make_flow_note(a+0.5, i, 0.4, rng, color=i%2))
    # Cleanup: sort, cap simultaneous notes, avoid same-color doubles in identical lane/layer.
    notes.sort(key=lambda n:(n['_time'],n['_type'],n['_lineIndex'],n['_lineLayer']))
    cleaned=[]; by_time={}
    for n in notes:
        tm=round(n['_time']*8)/8
        bucket=by_time.setdefault(tm, [])
        if len(bucket)>=max_simul: continue
        if any(x['_lineIndex']==n['_lineIndex'] and x['_lineLayer']==n['_lineLayer'] for x in bucket): continue
        n['_time']=round(tm,3)
        bucket.append(n); cleaned.append(n)
    # Choreography pass: convert musical roles into readable body-motion trajectories.
    choreo = apply_choreography(cleaned, tone_events, bpm, rng, options)
    # Blend: for normal, choreography dominates; for fun/overkill, keep extra learned complexity too.
    if float(options.get('density',0.34)) <= 0.85:
        cleaned = choreo
    else:
        cleaned = repair_same_time_collisions(choreo + cleaned)
    # Final readability pass. Normal/default is intentionally spacious; Fun/Overkill can raise maxSimultaneous/density.
    normal_mode = float(options.get('density',0.34)) <= 0.85 and int(options.get('maxSimultaneous',2)) <= 2
    cleaned = enforce_dynamic_spacing(cleaned, bpm, sections, options, normal=normal_mode)
    grid_mode='normal' if normal_mode else 'overkill' if float(options.get('density',0))>1.4 else 'fun'
    cleaned, state_meta = quantize_to_state_grid(cleaned, bpm, grid_mode)
    cleaned = cap_to_target_nps(cleaned, analysis, options)
    align_meta = beat_alignment_metrics(cleaned, analysis, bpm)
    return cleaned, bombs, walls, events, {'engine':'choreography-roleflow-v10','density':round(density,3),'normalMode':normal_mode,'dynamicSections':len(sections),'avgIntensity':round(sum(x.get('intensity',0) for x in sections)/max(1,len(sections)),3),'sourcePatterns':len(patterns),'modelVersion':model.get('version'),**state_meta,**align_meta,'options':options}


def auto_playability_settings(analysis, options):
    """Pick realistic Beat Saber defaults from the audio.
    Goal: notes are farther apart in time, with enough jump distance/speed to feel real.
    """
    bpm=float(analysis.get('bpm') or 120)
    vocal_count=len(analysis.get('vocalBeats') or [])
    beat_count=len(analysis.get('beats') or [])
    duration=max(1,float(analysis.get('duration') or 1))
    event_rate=max(vocal_count, beat_count)/duration
    density=float(options.get('density',0.48))
    # Normal/direct modes should be spacious. Fun/Overkill can be faster but still readable.
    requested_njs=float(options.get('njs',0) or 0)
    if requested_njs and requested_njs != 11:
        njs=requested_njs
    else:
        if density <= .6:
            njs=11.5 if bpm < 150 else 12.5
        elif density <= 1.2:
            njs=13.5 if bpm < 160 else 14.5
        else:
            njs=15.5 if bpm < 170 else 17.0
    # Offset controls spawn distance/read time. Positive = farther/earlier in many editors.
    offset=float(options.get('offset',0) or 0)
    if offset == 0:
        offset = 0.5 if density <= .6 else 0.3 if density <= 1.2 else 0.1
    # Minimum gap in beats between note groups. More spacious than prior versions.
    if density <= .6:
        min_group_gap_beats=1.25
        phrase_gap_beats=3.25
    elif density <= 1.2:
        min_group_gap_beats=1.45
        phrase_gap_beats=3.0
    else:
        min_group_gap_beats=0.5
        phrase_gap_beats=1.5
    st=spacing_target_for_options(options)
    return {'bpm':bpm,'eventRate':round(event_rate,3),'autoNjs':round(njs,2),'autoOffset':round(offset,2),'minGroupGapBeats':max(min_group_gap_beats, st['targetGapBeats']),'phraseGapBeats':phrase_gap_beats,'dynamicTiming':True, **st}



def repair_same_time_collisions(notes):
    """Never allow red/blue blocks to occupy the exact same grid cell at the same time.
    If two colors collide, place them horizontally next to each other on the same layer.
    """
    groups={}
    for n in notes:
        groups.setdefault(round(float(n.get('_time',0)),3), []).append(dict(n))
    repaired=[]
    for t,grp in sorted(groups.items()):
        colors=[n for n in grp if n.get('_type') in (0,1)]
        others=[n for n in grp if n.get('_type') not in (0,1)]
        bycell={}
        for n in colors:
            bycell.setdefault((n.get('_lineIndex'),n.get('_lineLayer')), []).append(n)
        used=set()
        out=[]
        # First handle actual same-cell collisions.
        for cell,ns in bycell.items():
            if len(ns)>=2 and len(set(n.get('_type') for n in ns))>=2:
                layer=int(cell[1] if cell[1] is not None else 1)
                # side-by-side standard double, never same exact cell
                red=next((n for n in ns if n.get('_type')==0), ns[0])
                blue=next((n for n in ns if n.get('_type')==1), ns[-1])
                red.update({'_lineIndex':1,'_lineLayer':layer,'_time':t})
                blue.update({'_lineIndex':2,'_lineLayer':layer,'_time':t})
                out.extend([red,blue]); used.add((1,layer)); used.add((2,layer))
            else:
                n=ns[0]; n['_time']=t
                c=(n.get('_lineIndex'),n.get('_lineLayer'))
                if c in used:
                    # shift horizontally to nearest free lane
                    layer=int(n.get('_lineLayer',1)); lanes=[0,1,2,3]
                    for lane in lanes:
                        if (lane,layer) not in used:
                            n['_lineIndex']=lane; break
                used.add((n.get('_lineIndex'),n.get('_lineLayer'))); out.append(n)
        # Repair any remaining accidental duplicates after side-by-side placement.
        final=[]; used=set()
        for n in sorted(out, key=lambda x:(x.get('_type',0),x.get('_lineIndex',0))):
            layer=int(n.get('_lineLayer',1)); lane=int(n.get('_lineIndex',0))
            if (lane,layer) in used:
                preferred=[1,2,0,3] if n.get('_type')==0 else [2,1,3,0]
                for ln in preferred:
                    if (ln,layer) not in used:
                        lane=ln; break
                n['_lineIndex']=lane
            used.add((lane,layer)); final.append(n)
        repaired.extend(final+others)
    return sorted(repaired, key=lambda n:(n.get('_time',0), n.get('_type',0), n.get('_lineIndex',0)))

def validate_v2_map(info, beatmaps):
    issues=[]
    if not info.get('_songName'): issues.append('Info.dat missing _songName')
    if not info.get('_songFilename'): issues.append('Info.dat missing _songFilename')
    if not info.get('_difficultyBeatmapSets'): issues.append('Info.dat missing difficulty sets')
    for filename,bm in beatmaps.items():
        notes=bm.get('_notes',[]); obs=bm.get('_obstacles',[]); events=bm.get('_events',[])
        last=-1
        seen=set()
        for i,n in enumerate(notes):
            t=n.get('_time')
            if t is None or t<0: issues.append(f'{filename}: note {i} invalid time')
            if t is not None and t<last: issues.append(f'{filename}: notes not sorted')
            last=t if t is not None else last
            typ=n.get('_type')
            if typ in (0,1):
                if not (0<=n.get('_lineIndex',-1)<=3): issues.append(f'{filename}: note lane out of range')
                if not (0<=n.get('_lineLayer',-1)<=2): issues.append(f'{filename}: note layer out of range')
                cellkey=(n.get('_time'),n.get('_lineIndex'),n.get('_lineLayer'))
                if cellkey in seen: issues.append(f'{filename}: duplicate/same-cell note overlap')
                seen.add(cellkey)
        for i,o in enumerate(obs):
            if o.get('_duration',0)<0: issues.append(f'{filename}: wall {i} negative duration')
    return {'valid':len(issues)==0,'issues':issues[:50]}

def scale_notes_for_difficulty(notes, difficulty):
    color=[n for n in notes if n.get('_type') in (0,1)]
    bombs=[n for n in notes if n.get('_type')==3]
    if difficulty=='Easy': keep_every=4; max_sim=1
    elif difficulty=='Normal': keep_every=3; max_sim=1
    elif difficulty=='Hard': keep_every=2; max_sim=1
    elif difficulty=='Expert': keep_every=1; max_sim=2
    else: keep_every=1; max_sim=4
    out=[]; by_time={}
    for idx,n in enumerate(sorted(color,key=lambda x:(x['_time'],x['_type']))):
        if keep_every>1 and idx%keep_every: continue
        bucket=by_time.setdefault(n['_time'],[])
        if len(bucket)>=max_sim: continue
        nn=dict(n)
        if difficulty in ('Easy','Normal'):
            nn['_cutDirection']=8 if difficulty=='Easy' else nn.get('_cutDirection',1)
            nn['_lineLayer']=min(1,nn.get('_lineLayer',1))
        bucket.append(nn); out.append(nn)
    if difficulty in ('ExpertPlus','Expert'):
        out.extend(bombs[:max(0,len(out)//32)])
    return repair_same_time_collisions(sorted(out,key=lambda n:(n['_time'],n.get('_type',0),n.get('_lineIndex',0))))

def make_beatmap(notes, obstacles, events):
    return {'_version':'2.1.0','_notes':notes,'_obstacles':obstacles,'_events':events}


def build_internal_project(analysis, options, generator_meta, stats, preview_notes):
    """Internal rich project model. Export stays vanilla Beat Saber v2.
    This is a DAW-like layer: sections, musical roles, intents, grammar, validation.
    """
    bpm=float(analysis.get('bpm') or 120)
    duration=float(analysis.get('duration') or 0)
    sections=section_energy_profile(analysis, window=8.0)
    labeled=[]
    for i,sec in enumerate(sections):
        inten=sec.get('intensity',0)
        if inten>.78: label='drop/peak'
        elif inten>.52: label='groove/build'
        elif sec.get('vocalRate',0)>sec.get('bassRate',0): label='vocal phrase'
        elif sec.get('bassRate',0)>0: label='bass pocket'
        else: label='breath/intro'
        labeled.append({**sec,'index':i,'label':label})
    events=[]
    for t,st in zip(analysis.get('vocalBeats',[]), analysis.get('vocalStrengths',[])):
        events.append({'time':t,'beat':round(t*bpm/60,3),'role':'vocal','strength':st,'intent':'phrase/lead gesture'})
    for t,st in zip(analysis.get('bassBeats',[]), analysis.get('bassStrengths',[])):
        events.append({'time':t,'beat':round(t*bpm/60,3),'role':'bass','strength':st,'intent':'grounded impact'})
    for t,st in zip(analysis.get('highBeats',[]), analysis.get('highStrengths',[])):
        events.append({'time':t,'beat':round(t*bpm/60,3),'role':'high','strength':st,'intent':'flick/accent'})
    events=sorted(events,key=lambda e:(e['time'], -e['strength']))[:2500]
    # derive pattern grammar from final notes
    color=[n for n in preview_notes if n.get('_type') in (0,1)]
    by_time={}
    for n in color: by_time.setdefault(n['_time'],[]).append(n)
    grammar=[]
    last=None
    for t in sorted(by_time)[:1200]:
        ns=by_time[t]
        token='double' if len(ns)>=2 else 'dot' if ns[0].get('_cutDirection')==8 else 'single'
        lanes=[n.get('_lineIndex') for n in ns]
        cuts=[n.get('_cutDirection') for n in ns]
        grammar.append({'beat':t,'token':token,'lanes':lanes,'cuts':cuts,'transitionFrom':last})
        last=token
    validation={
        'sameCellOverlaps':0,
        'maxSimultaneous':max([len(v) for v in by_time.values()] or [0]),
        'dotNotes':sum(1 for n in color if n.get('_cutDirection')==8),
        'doubles':sum(1 for v in by_time.values() if len(v)>=2),
        'uniqueBeatTimes':len(by_time),
    }
    seen=set()
    for n in color:
        key=(n['_time'],n.get('_lineIndex'),n.get('_lineLayer'))
        if key in seen: validation['sameCellOverlaps']+=1
        seen.add(key)
    return {
        'version':'beatmaper-project-v1',
        'createdBy':'Beatmaper',
        'bpm':bpm,'duration':duration,
        'options':options,
        'analysisSummary':{k:len(analysis.get(k,[])) for k in ['beats','vocalBeats','bassBeats','highBeats']},
        'sections':labeled,
        'musicalEvents':events,
        'patternGrammar':grammar,
        'playabilityValidation':validation,
        'generator':generator_meta,
        'retrievedHumanExamples': retrieve_human_examples(analysis, options),
        'sectionPlan': section_plan(analysis, options),
        'multiAgentReview': multi_agent_review(preview_notes, analysis, options),
        'stats':stats,
        'exportNote':'Export remains standard Beat Saber v2: Info.dat, difficulty .dat files, song.egg.'
    }

def write_internal_project(folder, project):
    pid=Path(folder).name
    path=PROJECTS/f'{pid}.project.json'
    path.write_text(json.dumps(project, indent=2), encoding='utf-8')
    return path

def make_map(analysis, name, options=None):
    options = options or {}
    auto_settings=auto_playability_settings(analysis, options)
    options={**options, **auto_settings}
    bpm=analysis['bpm']; beats=analysis['beats']; song_id=str(uuid.uuid4())[:8]
    folder=GEN/f'{song_id}_{name[:40].replace("/","_")}'
    folder.mkdir(exist_ok=True)
    info={'_version':'2.1.0','_songName':name,'_songSubName':'Generated by Beatmaper','_songAuthorName':'Unknown','_levelAuthorName':'Beatmaper AI-ish Generator','_beatsPerMinute':bpm,'_songTimeOffset':0,'_shuffle':0,'_shufflePeriod':0.5,'_previewStartTime':0,'_previewDuration':10,'_songFilename':'song.egg','_coverImageFilename':'cover.png','_environmentName':'DefaultEnvironment','_difficultyBeatmapSets':[]}
    arrangement = generate_direct_instrument_arrangement(analysis, bpm, options) if options.get('directInstrument') else generate_overkill_arrangement(analysis, bpm, options)
    generator_meta={'engine':'fallback'}
    if arrangement:
        notes, bombs, obstacles, events, generator_meta = arrangement
        # In v2 format bombs live in _notes with _type 3.
        notes = notes + bombs
    else:
        learned = learned_notes_for_beats(beats, bpm, 'expertplus')
        notes=[] if learned is None else learned
        obstacles=[]; events=[]
        if learned is None:
            lanes=[0,1,2,3]; layers=[0,1,2]
            for idx,t in enumerate(beats):
                bt=t*bpm/60
                lane=lanes[idx%4]; layer=layers[(idx//4)%3]; color=idx%2; cut=[1,0,1,0,2,3,4,5][idx%8]
                notes.append({'_time':round(bt,3),'_lineIndex':lane,'_lineLayer':layer,'_type':color,'_cutDirection':cut})
                if idx%4==1:
                    notes.append({'_time':round(bt+0.125,3),'_lineIndex':3-lane,'_lineLayer':layer,'_type':1-color,'_cutDirection':cut})
        for idx,t in enumerate(beats):
            bt=t*bpm/60
            if idx%32==0 and idx>0:
                obstacles.append({'_time':round(bt,3),'_lineIndex':0,'_type':1,'_duration':1.5,'_width':1})
            if idx%8==0:
                events.append({'_time':round(bt,3),'_type':0,'_value':5})
    ranks={'Easy':1,'Normal':3,'Hard':5,'Expert':7,'ExpertPlus':9}
    diffs=['Easy','Normal','Hard','Expert','ExpertPlus'] if options.get('multiDifficulty', True) else [options.get('difficulty','Expert')]
    beatmaps={}
    diff_entries=[]
    for diff in diffs:
        diff_notes=scale_notes_for_difficulty(notes, diff)
        diff_obstacles=obstacles if diff in ('Expert','ExpertPlus') else obstacles[::3] if diff=='Hard' else []
        diff_events=events
        filename=f'{diff}Standard.dat'
        beatmaps[filename]=make_beatmap(diff_notes, diff_obstacles, diff_events)
        diff_entries.append({'_difficulty':diff,'_difficultyRank':ranks.get(diff,7),'_beatmapFilename':filename,'_noteJumpMovementSpeed':float(options.get('autoNjs', options.get('njs',14))) + (1.5 if diff=='ExpertPlus' else 0),'_noteJumpStartBeatOffset':float(options.get('autoOffset', options.get('offset',0)))})
    info['_difficultyBeatmapSets']=[{'_beatmapCharacteristicName':'Standard','_difficultyBeatmaps':diff_entries}]
    validation=validate_v2_map(info, beatmaps)
    (folder/'Info.dat').write_text(json.dumps(info,indent=2))
    for filename,bm in beatmaps.items():
        (folder/filename).write_text(json.dumps(bm,indent=2))
    (folder/'cover.png').write_bytes(b'')
    zip_path=GEN/f'{folder.name}.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.iterdir(): z.write(f,f.name)
    primary=beatmaps.get(f"{options.get('difficulty','Expert')}Standard.dat") or beatmaps.get('ExpertStandard.dat') or next(iter(beatmaps.values()))
    primary_notes=primary['_notes']
    return folder, zip_path, {'notes':len([n for n in primary_notes if n.get('_type') in (0,1)]),'bombs':len([n for n in primary_notes if n.get('_type')==3]),'walls':len(primary['_obstacles']),'lights':len(primary['_events']),'difficulties':diffs,'validation':validation,'generator':generator_meta,'nps':round(len([n for n in primary_notes if n.get('_type') in (0,1)]) / max(1, analysis.get('duration',1)), 2)}

@app.get('/health')
def health(): return {'ok':True,'modelLoaded': load_pattern_model() is not None, 'spacingProfileLoaded': bool(load_spacing_profile()), 'modelPath': str(MODEL_PATH)}

@app.post('/analyze')
async def analyze(
    file: UploadFile=File(...),
    density: float = Form(0.34), streams: float = Form(0.08), njs: float = Form(10.5), offset: float = Form(0),
    difficulty: str = Form('Expert'), seed: int = Form(9001), maxSimultaneous: int = Form(2),
    doubles: bool = Form(True), bombs: bool = Form(True), walls: bool = Form(True), lights: bool = Form(True),
    subdivisions: bool = Form(True), minDensity: bool = Form(True), directInstrument: bool = Form(False), multiDifficulty: bool = Form(True), stabDots: bool = Form(True), style: str = Form('flowy dance')
):
    difficulty_rank = {'Easy':1,'Normal':3,'Hard':5,'Expert':7,'ExpertPlus':9,'Expert+':9}.get(difficulty,7)
    options={'density':density,'streams':streams,'njs':njs,'offset':offset,'difficulty':difficulty,'difficultyRank':difficulty_rank,'seed':seed,'maxSimultaneous':max(1,min(6,maxSimultaneous)),'doubles':doubles,'bombs':bombs,'walls':walls,'lights':lights,'subdivisions':subdivisions,'minDensity':minDensity,'directInstrument':directInstrument,'multiDifficulty':multiDifficulty,'stabDots':stabDots,'style':style}
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); src=tmp/file.filename; src.write_bytes(await file.read())
        wav=ensure_wav(src,tmp); samples,sr=read_wav(wav); analysis=analyze_audio(samples,sr)
        folder,zip_path,stats=make_map(analysis, Path(file.filename).stem, options)
        egg = folder / 'song.egg'
        audioWarning = None
        try:
            tmp_ogg = folder / 'song.ogg'
            subprocess.check_call(['ffmpeg','-y','-i',str(wav),'-vn','-f','ogg','-acodec','libvorbis','-q:a','5',str(tmp_ogg)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tmp_ogg.replace(egg)
        except Exception as ex:
            # Fallback keeps export non-empty, but proper Beat Saber compatibility needs ffmpeg/libvorbis.
            shutil.copyfile(wav, egg)
            audioWarning = f'ffmpeg/libvorbis conversion failed, song.egg contains WAV data fallback: {ex}'
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for f in folder.iterdir():
                if f.is_file() and f.stat().st_size > 0:
                    z.write(f, f.name)
        preview_notes = []
        try:
            preview_file = folder / f"{options.get('difficulty','Expert')}Standard.dat"
            if not preview_file.exists(): preview_file = folder/'ExpertStandard.dat'
            preview_notes = json.loads(preview_file.read_text()).get('_notes', [])[:3000]
        except Exception:
            preview_notes = []
        project=build_internal_project(analysis, options, stats.get('generator',{}), stats, preview_notes)
        project_path=write_internal_project(folder, project)
        return {'analysis':analysis,'stats':stats,'njs':stats.get('generator',{}).get('options',{}).get('autoNjs', stats.get('generator',{}).get('options',{}).get('njs', 12)),'jumpOffset':stats.get('generator',{}).get('options',{}).get('autoOffset', stats.get('generator',{}).get('options',{}).get('offset', 0)),'project':f'/project/{folder.name}','projectGrid':f'/project/{folder.name}/grid','review':project.get('multiAgentReview'),'modelLoaded': load_pattern_model() is not None,'audioFile':'song.egg','audioWarning':audioWarning,'previewNotes':preview_notes,'audioPreview':f'/audio/{folder.name}','download':f'/download/{zip_path.name}','folder':str(folder)}


@app.get('/training-status')
def training_status():
    log = ROOT / 'models' / 'training.log'
    report = ROOT / 'models' / 'training_report.json'
    pidp = ROOT / 'models' / 'training.pid'
    running = False
    pid = None
    if pidp.exists():
        try:
            pid = int(pidp.read_text().strip())
            import os
            os.kill(pid, 0)
            running = True
        except Exception:
            running = False
    tail = ''
    if log.exists():
        tail = '\n'.join(log.read_text(errors='ignore').splitlines()[-20:])
    rep = None
    if report.exists():
        try: rep = json.loads(report.read_text())
        except Exception: pass
    return {'running': running, 'pid': pid, 'modelLoaded': load_pattern_model() is not None, 'report': rep, 'logTail': tail}


@app.get('/audio/{folder_name}')
def audio_preview(folder_name: str):
    # folder_name is generated folder basename, not an arbitrary path
    safe = Path(folder_name).name
    p = GEN / safe / 'song.egg'
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type='audio/ogg', filename='song.ogg')



@app.get('/styles')
def styles():
    brain=load_dataset_brain()
    return {'styles': STYLE_PRESETS, 'brainVersion': brain.get('version'), 'retrievalExamples': brain.get('retrievalIndex', [])}

@app.post('/taste')
async def taste(payload: dict):
    return remember_taste('feedback', payload)

@app.get('/project/{project_name}')
def project_info(project_name: str):
    safe=Path(project_name).name
    p=PROJECTS/f'{safe}.project.json'
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text())

@app.get('/project/{project_name}/grid')
def project_grid(project_name: str):
    safe=Path(project_name).name
    p=PROJECTS/f'{safe}.project.json'
    if not p.exists():
        raise HTTPException(404)
    proj=json.loads(p.read_text())
    return {'bpm':proj.get('bpm'), 'sections':proj.get('sections',[]), 'grammar':proj.get('patternGrammar',[]), 'validation':proj.get('playabilityValidation',{})}

@app.get('/download/{name}')
def download(name:str):
    p=GEN/name
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p, filename=name)
