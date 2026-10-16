import os,sys,json,time,math,random,signal,argparse
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
import soundfile as sf
import torchaudio
from torchaudio.functional import resample as ta_resample

# ---------------- CONFIG ----------------
DEFAULT_SR=16000
CLIP_SEC=2.0
BATCH=24
EPOCHS=5
LR=1e-4
TARGET_FRACTION_STEP=0.25
SAVE_EVERY_STEPS=400
PRINT_EVERY_STEPS=50
CPU_THREADS=4
PAUSE_FLAG="pause.flag"

# Full augment (CPU-friendly)
def aug_full(wav,sr):
    # wav: torch [T]
    # gain
    g = float(torch.empty(1).uniform_(0.8,1.25))
    wav = wav * g
    # noise
    nl = float(torch.empty(1).uniform_(0.001,0.01))
    wav = wav + nl * torch.randn_like(wav)
    # speed perturb (via linear resample trick)
    sp = float(torch.empty(1).uniform_(0.9,1.1))
    if abs(sp-1.0) > 1e-3:
        new_len = max(8, int(wav.numel()/sp))
        wav = F.interpolate(wav.view(1,1,-1), size=new_len, mode="linear", align_corners=False).view(-1)
        wav = F.interpolate(wav.view(1,1,-1), size=int(DEFAULT_SR*CLIP_SEC), mode="linear", align_corners=False).view(-1)
    # time mask (zero out random segment)
    T = wav.numel()
    if T > 100:
        m = int(torch.randint(low=max(10,int(0.02*T)), high=max(11,int(0.08*T)), size=(1,)).item())
        s = int(torch.randint(low=0, high=max(1,T-m), size=(1,)).item())
        wav[s:s+m] = 0.0
    # mild clip
    wav = torch.clamp(wav, -1.0, 1.0)
    return wav

def load_wav(path, target_sr=DEFAULT_SR):
    wav_np, sr = sf.read(path, always_2d=True)
    wav_np = wav_np[:,0] if wav_np.shape[1] > 0 else wav_np[:,0]
    wav = torch.from_numpy(wav_np).float()
    if sr != target_sr:
        wav = ta_resample(wav, orig_freq=sr, new_freq=target_sr)
    if wav.numel() < 8:
        raise RuntimeError("too_short")
    return wav, target_sr

def rand_crop(wav, sr=DEFAULT_SR, clip_sec=CLIP_SEC):
    clip = int(sr*clip_sec)
    if wav.numel() >= clip:
        start = int(torch.randint(0, wav.numel()-clip+1, (1,)).item())
        return wav[start:start+clip]
    else:
        pad = clip - wav.numel()
        return F.pad(wav, (0,pad))

def read_index(path):
    # supports: jsonl with {"original_path": "..."} OR plain path per line
    items=[]
    with open(path,"r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj=json.loads(line)
                    p=obj.get("original_path") or obj.get("path") or obj.get("wav") or obj.get("audio")
                    if p: items.append(p)
                except: 
                    continue
            else:
                # may be "path|text"
                if "|" in line:
                    items.append(line.split("|",1)[0].strip())
                else:
                    items.append(line)
    return items

class Encoder(nn.Module):
    def __init__(self, proj=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(1,64,5,2,2), nn.BatchNorm1d(64), nn.GELU(),
            nn.Conv1d(64,128,5,2,2), nn.BatchNorm1d(128), nn.GELU(),
            nn.Conv1d(128,256,5,2,2), nn.BatchNorm1d(256), nn.GELU(),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.proj = nn.Sequential(nn.Linear(256,256), nn.GELU(), nn.Linear(256,proj))
    def forward(self,x):
        h=self.net(x)
        h=self.pool(h).squeeze(-1)
        z=self.proj(h)
        return F.normalize(z, dim=-1)

def nt_xent(z1,z2,temp=0.1):
    b=z1.size(0)
    z=torch.cat([z1,z2],0)                          # 2b,d
    sim=torch.matmul(z, z.t())/temp                 # 2b,2b
    mask=torch.eye(2*b, device=z.device).bool()
    sim=sim.masked_fill(mask, -9e15)
    tgt=torch.arange(b,2*b, device=z.device)
    tgt=torch.cat([tgt, torch.arange(0,b,device=z.device)],0)
    return F.cross_entropy(sim, tgt)

def save_ckpt(ckpt_path, model, optim, meta):
    torch.save({"model":model.state_dict(),"optim":optim.state_dict(),"meta":meta}, ckpt_path)

def load_ckpt(ckpt_path, model, optim):
    d=torch.load(ckpt_path, map_location="cpu")
    model.load_state_dict(d["model"])
    if optim is not None and "optim" in d: optim.load_state_dict(d["optim"])
    return d.get("meta",{})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data_index", required=True)
    ap.add_argument("--output_dir", required=True)  # models\audio_encoder
    ap.add_argument("--sample_rate", type=int, default=DEFAULT_SR)
    ap.add_argument("--batch_size", type=int, default=BATCH)
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--cpu_threads", type=int, default=CPU_THREADS)
    ap.add_argument("--target_fraction_step", type=float, default=TARGET_FRACTION_STEP)
    ap.add_argument("--save_every_steps", type=int, default=SAVE_EVERY_STEPS)
    ap.add_argument("--print_every_steps", type=int, default=PRINT_EVERY_STEPS)
    ap.add_argument("--device", default=("cuda" if torch.cuda.is_available() else "cpu"))
    args=ap.parse_args()

    torch.set_num_threads(args.cpu_threads)

    out_dir=os.path.abspath(args.output_dir)
    ckpt_dir=os.path.join(out_dir,"checkpoints")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(ckpt_dir, exist_ok=True)

    project_root=os.path.abspath(os.path.join(out_dir, "..", ".."))
    state_dir=os.path.join(project_root,"state")
    os.makedirs(state_dir, exist_ok=True)
    state_path=os.path.join(state_dir,"audio_encoder_state.json")

    items=read_index(args.data_index)
    items=[p for p in items if p and os.path.isfile(p)]
    if not items:
        print("[ERROR] Ingen gyldige wav paths funnet i index.", flush=True)
        return 2
    random.shuffle(items)

    steps_per_epoch=math.ceil(len(items)/args.batch_size)
    total_steps=steps_per_epoch*args.epochs

    # load state
    if os.path.isfile(state_path):
        try:
            st=json.load(open(state_path,"r",encoding="utf-8"))
        except:
            st={}
    else:
        st={}
    last_frac=float(st.get("last_fraction",0.0) or 0.0)
    next_frac=float(st.get("next_fraction", args.target_fraction_step) or args.target_fraction_step)
    steps_done=int(st.get("steps_completed",0) or 0)

    target_steps=min(total_steps, int(round(next_frac*total_steps)))
    if steps_done >= total_steps:
        print("[DONE] Allerede fullført (steps_done >= total_steps).", flush=True)
        return 0
    if steps_done >= target_steps:
        # bump to next fraction if state is behind
        while steps_done >= target_steps and target_steps < total_steps:
            last_frac=next_frac
            next_frac=round(next_frac + args.target_fraction_step, 2)
            target_steps=min(total_steps, int(round(next_frac*total_steps)))
        st["last_fraction"]=last_frac
        st["next_fraction"]=next_frac

    device=torch.device(args.device)
    model=Encoder().to(device)
    optim=torch.optim.Adam(model.parameters(), lr=args.lr)

    ckpt_last=os.path.join(ckpt_dir,"checkpoint_last.pt")
    if os.path.isfile(ckpt_last):
        meta=load_ckpt(ckpt_last, model, optim)
        steps_done=int(meta.get("global_step", steps_done))
        # reload st if checkpoint has it
        ck_st=meta.get("state")
        if isinstance(ck_st, dict):
            st.update(ck_st)
            steps_done=int(st.get("steps_completed", steps_done))
        print(f"[RESUME] checkpoint_last.pt loaded. steps_done={steps_done}", flush=True)

    # interrupt handler
    stop_flag={"stop":False}
    def _sigint(sig,frame):
        stop_flag["stop"]=True
    signal.signal(signal.SIGINT, _sigint)

    print(f"[INFO] Starter trening. device={device} files={len(items)} steps/epoch={steps_per_epoch} total_steps={total_steps}", flush=True)
    print(f"[INFO] Pulje: last_fraction={last_frac} next_fraction={next_frac} target_steps={target_steps}", flush=True)

    start_time=time.time()
    global_step=steps_done
    epoch_start = max(0, global_step // steps_per_epoch)
    # iterator that yields batches across epochs deterministically-ish
    def batch_iter():
        for e in range(args.epochs):
            # shuffle each epoch
            random.shuffle(items)
            for i in range(0,len(items), args.batch_size):
                yield e, items[i:i+args.batch_size]
    it=batch_iter()

    for epoch, batch_paths in it:
        if stop_flag["stop"]:
            # save and exit gracefully
            st["steps_completed"]=global_step
            st["total_steps_estimate"]=total_steps
            st["epochs_completed"]=epoch
            st["last_checkpoint"]=os.path.basename(ckpt_last)
            meta={"global_step":global_step,"state":st}
            save_ckpt(ckpt_last, model, optim, meta)
            json.dump(st, open(state_path,"w",encoding="utf-8"), indent=2)
            print("\n[INTERRUPT] CTRL+C -> lagret checkpoint_last.pt og avslutter.", flush=True)
            return 0

        # pause flag
        if os.path.exists(PAUSE_FLAG):
            print("[PAUSE] pause.flag funnet. Pauser... (slett filen for å fortsette)", flush=True)
            while os.path.exists(PAUSE_FLAG):
                time.sleep(1.0)

        # build batch tensors
        xs1=[]; xs2=[]
        ok=0
        for p in batch_paths:
            try:
                wav,sr=load_wav(p, args.sample_rate)
                w=rand_crop(wav, args.sample_rate, CLIP_SEC)
                v1=aug_full(w.clone(), args.sample_rate)
                v2=aug_full(w.clone(), args.sample_rate)
                xs1.append(v1); xs2.append(v2); ok+=1
            except:
                continue
        if ok < max(2, min(4, args.batch_size//4)):
            continue

        x1=torch.stack(xs1,0).unsqueeze(1).to(device)   # B,1,T
        x2=torch.stack(xs2,0).unsqueeze(1).to(device)

        z1=model(x1); z2=model(x2)
        loss=nt_xent(z1,z2, temp=0.1)

        optim.zero_grad()
        loss.backward()
        optim.step()

        global_step += 1

        # progress, eta
        elapsed=time.time()-start_time
        done=max(0, global_step)
        rem=max(0, target_steps - global_step)
        spd = elapsed/max(1,(global_step-steps_done))  # sec/step this run
        eta = rem*spd

        pct = 100.0 * (global_step/target_steps) if target_steps>0 else 0.0
        pct = min(100.0, max(0.0, pct))

        if (global_step % args.print_every_steps)==0 or global_step==target_steps:
            print(f"[TRAIN] step {global_step}/{target_steps} loss={loss.item():.4f} ETA={eta/60:.1f}m", flush=True)
            # kompatibel med DEL 4 regex:
            print(f"PROGRESS:{pct:.2f}", flush=True)

        # checkpointing
        if (global_step % args.save_every_steps)==0 or global_step==target_steps:
            st["steps_completed"]=global_step
            st["total_steps_estimate"]=total_steps
            st["epochs_completed"]=epoch
            st["last_fraction"]=last_frac
            st["next_fraction"]=next_frac
            st["last_checkpoint"]=os.path.basename(ckpt_last)
            meta={"global_step":global_step,"state":st}
            save_ckpt(ckpt_last, model, optim, meta)
            json.dump(st, open(state_path,"w",encoding="utf-8"), indent=2)
            if global_step % (args.save_every_steps*5) == 0:
                save_ckpt(os.path.join(ckpt_dir, f"checkpoint_step_{global_step}.pt"), model, optim, meta)

        # epoch end checkpoint
        if (global_step % steps_per_epoch)==0:
            st["steps_completed"]=global_step
            st["epochs_completed"]=epoch+1
            meta={"global_step":global_step,"state":st}
            save_ckpt(os.path.join(ckpt_dir, f"checkpoint_epoch_{epoch+1}.pt"), model, optim, meta)

        # pulje ferdig?
        if global_step >= target_steps:
            frac_tag=int(round(next_frac*100))
            st["steps_completed"]=global_step
            st["total_steps_estimate"]=total_steps
            st["last_fraction"]=next_frac
            st["next_fraction"]=round(min(1.0, next_frac + args.target_fraction_step), 2)
            st["last_checkpoint"]=f"checkpoint_fraction_{frac_tag}.pt"
            meta={"global_step":global_step,"state":st}
            save_ckpt(os.path.join(ckpt_dir, f"checkpoint_fraction_{frac_tag}.pt"), model, optim, meta)
            save_ckpt(ckpt_last, model, optim, meta)
            json.dump(st, open(state_path,"w",encoding="utf-8"), indent=2)
            print(f"[DONE] Pulje fullført ({frac_tag}%). Neste pulje: {int(round(st['next_fraction']*100))}%", flush=True)
            print("PROGRESS:100.00", flush=True)
            return 0

    # if loop ends naturally
    st["steps_completed"]=global_step
    st["total_steps_estimate"]=total_steps
    meta={"global_step":global_step,"state":st}
    save_ckpt(ckpt_last, model, optim, meta)
    json.dump(st, open(state_path,"w",encoding="utf-8"), indent=2)
    print("[DONE] Ferdig (loop slutt).", flush=True)
    print("PROGRESS:100.00", flush=True)
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}", flush=True)
        raise
