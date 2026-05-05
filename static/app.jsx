const {useState,useEffect,useCallback} = React;

// ═══ CONFIG ═══
const API = window.location.origin;
const DEV_USER = new URLSearchParams(window.location.search).get("user") || "1530002";
const EDITORS = [1530002,1530003,1530001,1870001];

// ═══ API ═══
const apiFetch = async (path, opts={}) => {
  const r = await fetch(`${API}${path}${path.includes("?")?"&":"?"}dev_user_id=${DEV_USER}`, {
    headers: {"Content-Type":"application/json","x-dev-user-id":DEV_USER,...opts.headers}, ...opts
  });
  if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.detail||r.statusText); }
  return r.json();
};

// ═══ HELPERS ═══
const dk = d => d.toISOString().slice(0,10);
const mondayOf = d => { const m=new Date(d); m.setDate(m.getDate()-((m.getDay()+6)%7)); return m; };
const weekDays = mon => Array.from({length:7},(_,i)=>{ const d=new Date(mon); d.setDate(d.getDate()+i); return d; });
const isSame = (a,b) => dk(a)===dk(b);
const apiTime = t => { if(!t)return""; const m=t.match(/(\d+):(\d+)\s*(AM|PM)/i); if(!m)return t; return `${+m[1]}:${m[2]}${m[3][0].toLowerCase()}`; };
const to24 = t => { const[tm,p]=t.split(/(?=[ap])/); let[h,m]=tm.split(":").map(Number); if(p==="p"&&h!==12)h+=12; if(p==="a"&&h===12)h=0; return `${String(h).padStart(2,"0")}:${String(m||0).padStart(2,"0")}:00`; };
const pT = t => { const[tm,p]=t.split(/(?=[ap])/); let[h,m]=tm.split(":").map(Number); if(p==="p"&&h!==12)h+=12; if(p==="a"&&h===12)h=0; return h+(m||0)/60; };
const fmtH = h => { const hr=Math.floor(h),mn=Math.round((h-hr)*60); return mn?`${hr}h ${mn}m`:`${hr}h`; };

const DS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
const DF = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
const MS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const RC = { Stylist:{bg:"#dbeafe",tx:"#1e40af",bd:"#93c5fd"}, Receptionist:{bg:"#f3e8ff",tx:"#7c3aed",bd:"#c4b5fd"} };
const TOPTS = (()=>{ const a=[]; for(let h=6;h<=21;h++) for(let m=0;m<60;m+=10){ const hr=h>12?h-12:h===0?12:h; a.push(`${hr}:${String(m).padStart(2,"0")}${h>=12?"p":"a"}`); } return a; })();

// ═══ STYLES ═══
const SI = {width:"100%",padding:"8px 10px",borderRadius:6,border:"1px solid #d1d5db",fontSize:14,color:"#111",background:"#fff",outline:"none"};
const CD = {background:"#fff",borderRadius:10,border:"1px solid #e5e7eb",padding:16,marginBottom:12};
const GH = {padding:"8px 4px",textAlign:"center",borderBottom:"1px solid #e5e7eb",borderRight:"1px solid #f3f4f6",background:"#f9fafb",fontSize:11,fontWeight:600,color:"#6b7280"};
const NB = {width:36,height:36,borderRadius:8,border:"1px solid #e5e7eb",background:"#fff",fontSize:18,color:"#374151",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center"};
const AV = {width:36,height:36,borderRadius:8,background:"#f3f4f6",display:"flex",alignItems:"center",justifyContent:"center",fontSize:12,fontWeight:700,color:"#6b7280",flexShrink:0};
const IB = {width:30,height:30,borderRadius:6,border:"1px solid #e5e7eb",background:"#fff",display:"flex",alignItems:"center",justifyContent:"center",cursor:"pointer",fontSize:14,color:"#6b7280"};
const SH = {fontSize:13,fontWeight:700,color:"#374151",marginBottom:10,textTransform:"uppercase",letterSpacing:.5};
const BTN = {padding:"10px 16px",borderRadius:8,border:"none",fontSize:14,fontWeight:600,cursor:"pointer",background:"#3b82f6",color:"#fff"};

// ═══ SHARED COMPONENTS ═══
const Badge = ({s}) => {
  const m = {DRAFT:["#fef3c7","#92400e"],PUBLISHED:["#d1fae5","#065f46"],PENDING:["#fef3c7","#92400e"],APPROVED:["#d1fae5","#065f46"],DENIED:["#fee2e2","#991b1b"]};
  const[bg,c] = m[s]||m.DRAFT;
  return <span style={{background:bg,color:c,fontSize:10,fontWeight:600,padding:"2px 8px",borderRadius:4,textTransform:"uppercase",letterSpacing:.5}}>{s}</span>;
};

const Toast = ({msg}) => msg ? <div style={{position:"fixed",bottom:80,left:"50%",transform:"translateX(-50%)",background:"#1f2937",color:"#fff",padding:"10px 20px",borderRadius:8,fontSize:13,fontWeight:500,zIndex:999,boxShadow:"0 4px 12px rgba(0,0,0,.25)",animation:"fadeUp .25s ease"}}>{msg}</div> : null;

// ═══ SHIFT MODAL ═══
function ShiftModal({mode,shift,name,day,positions,templates,onSave,onDelete,onClose}) {
  const[start,setStart]=useState(shift?.start||"9:50a");
  const[end,setEnd]=useState(shift?.end||"6:00p");
  const[role,setRole]=useState(shift?.role||positions?.[0]||"Stylist");
  const ok = pT(end)>pT(start);

  return <div onClick={onClose} style={{position:"fixed",inset:0,background:"rgba(0,0,0,.4)",zIndex:500,display:"flex",alignItems:"center",justifyContent:"center",padding:16}}>
    <div onClick={e=>e.stopPropagation()} style={{background:"#fff",borderRadius:12,padding:24,width:"100%",maxWidth:380,boxShadow:"0 20px 60px rgba(0,0,0,.2)"}}>
      <div style={{display:"flex",justifyContent:"space-between",marginBottom:16}}>
        <h3 style={{fontSize:16,fontWeight:600,color:"#111",margin:0}}>{mode==="add"?"Add Shift":"Edit Shift"}</h3>
        <button onClick={onClose} style={{background:"none",border:"none",fontSize:18,color:"#9ca3af",cursor:"pointer"}}>✕</button>
      </div>
      <div style={{background:"#f9fafb",borderRadius:8,padding:12,marginBottom:16,fontSize:13}}>
        <strong>{name}</strong><br/><span style={{color:"#6b7280"}}>{day}</span>
      </div>
      <div style={{fontSize:11,fontWeight:600,color:"#6b7280",marginBottom:4,textTransform:"uppercase"}}>Role</div>
      <div style={{display:"flex",gap:8,marginBottom:16}}>
        {(positions||["Stylist"]).map(p =>
          <button key={p} onClick={()=>setRole(p)} style={{flex:1,padding:8,borderRadius:6,fontSize:13,fontWeight:500,cursor:"pointer",
            border:`1.5px solid ${role===p?"#3b82f6":"#e5e7eb"}`,
            background:role===p?"#eff6ff":"#fff",
            color:role===p?"#1d4ed8":"#6b7280"}}>{p}</button>
        )}
      </div>
      {templates?.length>0 && mode==="add" &&
        <div style={{display:"flex",gap:6,marginBottom:12,flexWrap:"wrap"}}>
          {templates.map(t =>
            <button key={t.template_id} onClick={()=>{setStart(apiTime(t.start_time));setEnd(apiTime(t.end_time))}}
              style={{padding:"5px 10px",borderRadius:6,fontSize:11,border:"1px solid #e5e7eb",background:"#f9fafb",color:"#374151",cursor:"pointer"}}>{t.template_name}</button>
          )}
        </div>
      }
      <div style={{display:"flex",gap:12,marginBottom:16}}>
        <div style={{flex:1}}>
          <div style={{fontSize:11,fontWeight:600,color:"#6b7280",marginBottom:4}}>Start</div>
          <select value={start} onChange={e=>setStart(e.target.value)} style={SI}>{TOPTS.map(t=><option key={t}>{t}</option>)}</select>
        </div>
        <div style={{flex:1}}>
          <div style={{fontSize:11,fontWeight:600,color:"#6b7280",marginBottom:4}}>End</div>
          <select value={end} onChange={e=>setEnd(e.target.value)} style={SI}>{TOPTS.map(t=><option key={t}>{t}</option>)}</select>
        </div>
      </div>
      {ok && <div style={{background:"#f0fdf4",borderRadius:6,padding:8,textAlign:"center",fontSize:13,color:"#166534",fontWeight:500,marginBottom:16}}>{start} – {end} · {fmtH(pT(end)-pT(start))}</div>}
      <div style={{display:"flex",gap:8}}>
        <button disabled={!ok} onClick={()=>onSave({start,end,role})} style={{...BTN,flex:1,opacity:ok?1:.4}}>{mode==="add"?"Add Shift":"Save"}</button>
        {mode==="edit" && <button onClick={onDelete} style={{...BTN,background:"#fee2e2",color:"#991b1b"}}>Delete</button>}
      </div>
    </div>
  </div>;
}

// ═══ CALENDAR GRID ═══
function CalendarGrid({days,canE,vU,gs,isCl,getTOR,wh,setModal,drag,setDrag,moveShift}) {
  return <div style={{overflowX:"auto",marginBottom:16}}>
    <div style={{display:"grid",gridTemplateColumns:"100px repeat(7,1fr)",minWidth:680,borderRadius:8,overflow:"hidden",border:"1px solid #e5e7eb",background:"#fff"}}>
      <div style={GH}>Staff</div>
      {days.map((d,i)=>{
        const td=isSame(d,new Date()), cl=isCl(d);
        return <div key={i} style={{...GH,background:cl?"#fef2f2":td?"#eff6ff":"#f9fafb"}}>
          <div style={{fontSize:10,fontWeight:600,color:td?"#3b82f6":cl?"#dc2626":"#9ca3af",textTransform:"uppercase"}}>{DS[d.getDay()]}</div>
          <div style={{fontSize:16,fontWeight:700,color:td?"#fff":cl?"#dc2626":"#374151",
            ...(td?{background:"#3b82f6",width:26,height:26,borderRadius:"50%",display:"inline-flex",alignItems:"center",justifyContent:"center"}:{})}}>{d.getDate()}</div>
          {cl && <div style={{fontSize:8,fontWeight:700,color:"#dc2626"}}>CLOSED</div>}
        </div>;
      })}

      {vU.map(u => <div key={u.user_id} style={{display:"contents"}}>
        <div style={{padding:"6px 8px",borderBottom:"1px solid #f3f4f6",borderRight:"1px solid #e5e7eb",background:"#fff",display:"flex",flexDirection:"column",justifyContent:"center"}}>
          <div style={{fontSize:12,fontWeight:600,color:"#111",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{u.display_name}</div>
          <div style={{fontSize:10,color:"#9ca3af"}}>{fmtH(wh[u.user_id]||0)}</div>
        </div>
        {days.map((d,di)=>{
          const s=gs(u.user_id,d), cl=isCl(d), tr=getTOR(u.user_id,d);
          const rc=s?RC[s.role]||RC.Stylist:null, dr=s?.status==="DRAFT";
          return <div key={di}
            style={{padding:"4px 3px",borderBottom:"1px solid #f3f4f6",borderRight:"1px solid #f3f4f6",display:"flex",alignItems:"center",justifyContent:"center",minHeight:48,cursor:canE?"pointer":"default",background:cl?"#fef2f2":isSame(d,new Date())?"#f0f7ff":"#fff"}}
            onDragOver={canE?e=>{e.preventDefault();e.dataTransfer.dropEffect="move"}:undefined}
            onDrop={canE?e=>{e.preventDefault();if(drag?.uid===u.user_id&&drag.s?.shift_id)moveShift(drag.s.shift_id,dk(d));setDrag(null)}:undefined}
            onClick={()=>{
              if(cl)return;
              if(canE&&!s&&!tr) setModal({mode:"add",uid:u.user_id,dk:dk(d),day:`${DF[d.getDay()]}, ${MS[d.getMonth()]} ${d.getDate()}`,name:u.display_name,positions:u.positions,locId:u.location_id});
              else if(canE&&s) setModal({mode:"edit",uid:u.user_id,dk:dk(d),day:`${DF[d.getDay()]}, ${MS[d.getMonth()]} ${d.getDate()}`,name:u.display_name,shift:s,positions:u.positions,locId:u.location_id});
            }}>
            {cl ? <span style={{fontSize:10,color:"#fca5a5"}}>✕</span>
            : tr&&!s ? <div style={{width:"100%",padding:"4px 2px",borderRadius:4,fontSize:8,fontWeight:600,textAlign:"center",textTransform:"uppercase",...(tr.status==="PENDING"?{background:"repeating-linear-gradient(45deg,#f3f4f6,#f3f4f6 2px,#e5e7eb 2px,#e5e7eb 4px)",color:"#6b7280"}:{background:"#e5e7eb",color:"#6b7280"})}}>{tr.status==="APPROVED"?"OFF":"REQ"}</div>
            : s ? <div className="sp" draggable={canE}
                onDragStart={()=>setDrag({uid:u.user_id,s})} onDragEnd={()=>setDrag(null)}
                style={{width:"100%",padding:"3px 2px",borderRadius:4,fontSize:9,fontWeight:600,textAlign:"center",lineHeight:1.3,background:rc.bg,color:rc.tx,border:`1px ${dr?"dashed":"solid"} ${rc.bd}`,opacity:dr?.7:1,position:"relative"}}>
                {dr && <div className="hatch" style={{position:"absolute",inset:0,borderRadius:3}}/>}
                <div style={{position:"relative"}}>{s.start}<br/>{s.end}</div>
              </div>
            : canE ? <div style={{width:"100%",height:32,border:"1.5px dashed #d1d5db",borderRadius:4,display:"flex",alignItems:"center",justifyContent:"center",color:"#d1d5db",fontSize:14}}>+</div>
            : <span style={{fontSize:10,color:"#e5e7eb"}}>—</span>}
          </div>;
        })}
      </div>)}

      <div style={{...GH,fontSize:10,fontWeight:600}}>Hours</div>
      {days.map((d,i)=>{
        let h=0; vU.forEach(u=>{const s=gs(u.user_id,d);if(s)h+=pT(s.end)-pT(s.start)});
        return <div key={i} style={{...GH,fontSize:11,fontWeight:700,color:"#3b82f6"}}>{h>0?fmtH(h):""}</div>;
      })}
    </div>
  </div>;
}

// ═══ LIST VIEW ═══
function ListView({days,canE,vU,gs,isCl,getTOR,setModal}) {
  return <div>{days.map(d=>{
    const cl=isCl(d), td=isSame(d,new Date());
    const ds=vU.map(u=>({u,s:gs(u.user_id,d),t:getTOR(u.user_id,d)})).filter(x=>x.s||x.t);
    return <div key={dk(d)} style={{marginBottom:16}}>
      <div style={{background:td?"#3b82f6":"#374151",color:"#fff",padding:"8px 14px",borderRadius:"8px 8px 0 0",fontSize:12,fontWeight:600,textTransform:"uppercase",letterSpacing:.5,display:"flex",justifyContent:"space-between"}}>
        <span>{DF[d.getDay()]}, {MS[d.getMonth()]} {d.getDate()}</span>
        {cl?<span style={{background:"#dc2626",padding:"1px 8px",borderRadius:4}}>CLOSED</span>:<span>{ds.filter(x=>x.s).length} shifts</span>}
      </div>
      {cl ? <div style={{...CD,borderRadius:"0 0 8px 8px",textAlign:"center",color:"#9ca3af",padding:20,marginBottom:0}}>Closed</div>
      : ds.length===0 ? <div style={{...CD,borderRadius:"0 0 8px 8px",textAlign:"center",color:"#9ca3af",padding:20,marginBottom:0}}>No shifts</div>
      : <div style={{background:"#fff",border:"1px solid #e5e7eb",borderTop:"none",borderRadius:"0 0 8px 8px"}}>
          {ds.map(({u,s,t})=>{
            if(t&&!s) return <div key={u.user_id} style={{display:"flex",alignItems:"center",gap:12,padding:"12px 14px",borderBottom:"1px solid #f3f4f6"}}>
              <div style={AV}>{u.avatar_initials}</div>
              <div style={{flex:1}}><div style={{fontWeight:600,fontSize:14,color:"#111"}}>{u.first_name} {u.last_name}</div><div style={{fontSize:13,color:"#9ca3af"}}>Time Off</div></div>
              <Badge s={t.status}/>
            </div>;
            const rc=RC[s?.role]||RC.Stylist, dr=s?.status==="DRAFT";
            return <div key={u.user_id}
              style={{display:"flex",alignItems:"center",gap:12,padding:"12px 14px",borderBottom:"1px solid #f3f4f6",cursor:canE?"pointer":"default",...(dr?{background:"#fefce8"}:{})}}
              onClick={()=>canE&&s&&setModal({mode:"edit",uid:u.user_id,dk:dk(d),day:`${DF[d.getDay()]}, ${MS[d.getMonth()]} ${d.getDate()}`,name:u.display_name,shift:s,positions:u.positions,locId:u.location_id})}>
              <div style={{...AV,borderLeft:`3px solid ${rc.bd}`}}>{u.avatar_initials}</div>
              <div style={{flex:1}}>
                <div style={{fontWeight:600,fontSize:14,color:"#111"}}>{u.first_name} {u.last_name}</div>
                <div style={{fontSize:15,fontWeight:700,color:"#374151"}}>{s.start} – {s.end}</div>
                <div style={{fontSize:12,color:"#9ca3af"}}>{s.role}</div>
              </div>
              {dr && <Badge s="DRAFT"/>}
              <span style={{color:"#d1d5db",fontSize:18}}>›</span>
            </div>;
          })}
        </div>}
    </div>;
  })}</div>;
}

// ═══ TIME OFF VIEW ═══
function TimeOffView({me,isM,tor,vL,fetchAll,tt}) {
  const[show,setShow]=useState(false);
  const[f,setF]=useState({start_date:"",end_date:"",reason:""});
  const[deny,setDeny]=useState(null);
  const[dc,setDc]=useState("");
  const fl=isM?tor.filter(r=>vL==="All"||r.location_name===vL):tor.filter(r=>r.user_id===me.user_id);

  const submit=async()=>{ if(!f.start_date||!f.reason){tt("Fill fields");return} try{await apiFetch("/api/scheduling/time-off",{method:"POST",body:JSON.stringify({...f,end_date:f.end_date||f.start_date})});await fetchAll();setF({start_date:"",end_date:"",reason:""});setShow(false);tt("Submitted")}catch(e){tt(e.message)} };
  const review=async(id,st,cm)=>{ try{await apiFetch(`/api/scheduling/time-off/${id}`,{method:"PUT",body:JSON.stringify({status:st,comment:cm})});await fetchAll();tt(st)}catch(e){tt(e.message)} };
  const del=async id=>{ try{await apiFetch(`/api/scheduling/time-off/${id}`,{method:"DELETE"});await fetchAll();tt("Removed")}catch(e){tt(e.message)} };

  return <div style={{paddingTop:16}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
      <h2 style={{fontSize:18,fontWeight:700,color:"#111"}}>{isM?"Requests":"My Time Off"}</h2>
      {!isM&&<button onClick={()=>setShow(!show)} style={{...BTN,padding:"8px 14px",fontSize:13}}>{show?"Cancel":"+ Request"}</button>}
    </div>
    {show && <div style={{...CD,borderColor:"#3b82f6"}}>
      <div style={{display:"flex",gap:12,marginBottom:10}}>
        <div style={{flex:1}}><div style={{fontSize:11,fontWeight:600,color:"#6b7280",marginBottom:4}}>Start *</div><input type="date" style={SI} value={f.start_date} onChange={e=>setF({...f,start_date:e.target.value})}/></div>
        <div style={{flex:1}}><div style={{fontSize:11,fontWeight:600,color:"#6b7280",marginBottom:4}}>End</div><input type="date" style={SI} value={f.end_date} onChange={e=>setF({...f,end_date:e.target.value})}/></div>
      </div>
      <div style={{marginBottom:10}}><div style={{fontSize:11,fontWeight:600,color:"#6b7280",marginBottom:4}}>Reason *</div><select style={SI} value={f.reason} onChange={e=>setF({...f,reason:e.target.value})}><option value="">Select...</option><option>Vacation</option><option>Personal</option><option>Medical</option><option>Family</option></select></div>
      <button onClick={submit} style={{...BTN,width:"100%",textAlign:"center"}}>Submit</button>
    </div>}
    {fl.sort((a,b)=>a.status==="PENDING"?-1:1).map(r=><div key={r.request_id} style={CD}>
      <div style={{display:"flex",justifyContent:"space-between"}}>
        <div>
          {isM&&<div style={{fontWeight:600,fontSize:14,color:"#111",marginBottom:2}}>{r.display_name} <span style={{fontSize:11,color:"#9ca3af",fontWeight:400}}>{r.location_name}</span></div>}
          <div style={{fontWeight:600,fontSize:14,color:"#374151"}}>{r.start_date}{r.end_date!==r.start_date?` – ${r.end_date}`:""}</div>
          <div style={{fontSize:13,color:"#6b7280",marginTop:2}}>{r.reason}</div>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:6}}>
          <Badge s={r.status}/>
          {isM&&<button onClick={()=>del(r.request_id)} style={{background:"none",border:"none",fontSize:14,color:"#d1d5db",cursor:"pointer"}}>✕</button>}
        </div>
      </div>
      {isM&&r.status==="PENDING"&&<div style={{marginTop:10}}>
        {deny===r.request_id ? <div>
          <input placeholder="Reason for denying..." style={{...SI,marginBottom:6}} value={dc} onChange={e=>setDc(e.target.value)}/>
          <div style={{display:"flex",gap:6}}>
            <button onClick={()=>{review(r.request_id,"DENIED",dc);setDeny(null);setDc("")}} style={{...BTN,fontSize:12,padding:"6px 12px",background:"#fee2e2",color:"#991b1b"}}>Deny</button>
            <button onClick={()=>setDeny(null)} style={{...BTN,fontSize:12,padding:"6px 12px",background:"#f3f4f6",color:"#374151"}}>Cancel</button>
          </div>
        </div> : <div style={{display:"flex",gap:6}}>
          <button onClick={()=>review(r.request_id,"APPROVED")} style={{...BTN,fontSize:12,padding:"6px 12px",background:"#d1fae5",color:"#065f46"}}>Approve</button>
          <button onClick={()=>setDeny(r.request_id)} style={{...BTN,fontSize:12,padding:"6px 12px",background:"#fee2e2",color:"#991b1b"}}>Deny</button>
        </div>}
      </div>}
    </div>)}
    {fl.length===0&&<div style={{textAlign:"center",padding:40,color:"#9ca3af"}}>No requests</div>}
  </div>;
}

// ═══ PEOPLE VIEW ═══
function PeopleView({users,locs,fetchAll,tt}) {
  const[eu,setEu]=useState(null);
  const[f,setF]=useState({firstName:"",lastName:"",positions:["Stylist"],location_id:""});
  const[cd,setCd]=useState(null);

  const save=async()=>{if(!f.firstName||!f.lastName){tt("Enter name");return}try{if(eu==="new")await apiFetch("/api/scheduling/users",{method:"POST",body:JSON.stringify({first_name:f.firstName,last_name:f.lastName,positions:f.positions,location_id:f.location_id})});else await apiFetch(`/api/scheduling/users/${eu.user_id}`,{method:"PUT",body:JSON.stringify({first_name:f.firstName,last_name:f.lastName,positions:f.positions,location_id:f.location_id})});await fetchAll();setEu(null);tt("Saved")}catch(e){tt(e.message)}};
  const del=async uid=>{try{await apiFetch(`/api/scheduling/users/${uid}`,{method:"DELETE"});await fetchAll();setCd(null);tt("Removed")}catch(e){tt(e.message)}};

  return <div style={{paddingTop:16}}>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:16}}>
      <h2 style={{fontSize:18,fontWeight:700,color:"#111"}}>People</h2>
      <button onClick={()=>{setEu("new");setF({firstName:"",lastName:"",positions:["Stylist"],location_id:locs[0]?.id||""})}} style={{...BTN,padding:"8px 14px",fontSize:13}}>+ Add</button>
    </div>
    {eu&&<div style={{...CD,borderColor:"#3b82f6"}}>
      <div style={{display:"flex",gap:10,marginBottom:10}}>
        <input placeholder="First" style={{...SI,flex:1}} value={f.firstName} onChange={e=>setF({...f,firstName:e.target.value})}/>
        <input placeholder="Last" style={{...SI,flex:1}} value={f.lastName} onChange={e=>setF({...f,lastName:e.target.value})}/>
      </div>
      <div style={{display:"flex",gap:6,marginBottom:10}}>
        {["Stylist","Receptionist"].map(p=><button key={p} onClick={()=>{const h=f.positions.includes(p);const n=h?f.positions.filter(x=>x!==p):[...f.positions,p];if(n.length)setF({...f,positions:n})}}
          style={{padding:"6px 14px",borderRadius:6,fontSize:13,fontWeight:500,border:`1.5px solid ${f.positions.includes(p)?"#3b82f6":"#d1d5db"}`,background:f.positions.includes(p)?"#eff6ff":"#fff",color:f.positions.includes(p)?"#1d4ed8":"#6b7280",cursor:"pointer"}}>{f.positions.includes(p)?"✓ ":""}{p}</button>)}
      </div>
      <select style={{...SI,marginBottom:10}} value={f.location_id} onChange={e=>setF({...f,location_id:e.target.value})}>{locs.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select>
      <div style={{display:"flex",gap:8}}>
        <button onClick={save} style={{...BTN,flex:1,textAlign:"center"}}>{eu==="new"?"Add":"Save"}</button>
        <button onClick={()=>setEu(null)} style={{...BTN,background:"#f3f4f6",color:"#374151"}}>Cancel</button>
      </div>
    </div>}
    {users.map(u=><div key={u.user_id} style={CD}>
      {cd===u.user_id ? <div>
        <div style={{fontWeight:600,color:"#dc2626",marginBottom:8}}>Remove {u.display_name}?</div>
        <div style={{display:"flex",gap:6}}>
          <button onClick={()=>del(u.user_id)} style={{...BTN,fontSize:12,padding:"6px 12px",background:"#fee2e2",color:"#991b1b"}}>Yes</button>
          <button onClick={()=>setCd(null)} style={{...BTN,fontSize:12,padding:"6px 12px",background:"#f3f4f6",color:"#374151"}}>Cancel</button>
        </div>
      </div> : <div style={{display:"flex",alignItems:"center",gap:12}}>
        <div style={AV}>{u.avatar_initials}</div>
        <div style={{flex:1}}>
          <div style={{fontWeight:600,fontSize:14,color:"#111"}}>{u.display_name}</div>
          <div style={{display:"flex",gap:4,marginTop:3}}>{u.positions.map(p=><span key={p} style={{fontSize:11,padding:"1px 6px",borderRadius:4,background:RC[p]?.bg||"#f3f4f6",color:RC[p]?.tx||"#374151",fontWeight:500}}>{p}</span>)}</div>
          <div style={{fontSize:11,color:"#9ca3af",marginTop:2}}>{u.location_name}</div>
        </div>
        <div style={{display:"flex",gap:4}}>
          <button onClick={()=>{setEu(u);setF({firstName:u.first_name,lastName:u.last_name,positions:[...u.positions],location_id:u.location_id})}} style={IB}>✎</button>
          <button onClick={()=>setCd(u.user_id)} style={{...IB,color:"#dc2626"}}>✕</button>
        </div>
      </div>}
    </div>)}
  </div>;
}

// ═══ ADMIN VIEW ═══
function AdminView({tpls,rules,bh}) {
  return <div style={{paddingTop:16}}>
    <h2 style={{fontSize:18,fontWeight:700,color:"#111",marginBottom:16}}>Admin</h2>
    <h3 style={SH}>Templates</h3>
    {tpls.map(t=><div key={t.template_id} style={{...CD,display:"flex",justifyContent:"space-between"}}>
      <div><div style={{fontWeight:600,fontSize:14,color:"#111"}}>{t.template_name}</div><div style={{fontSize:13,color:"#6b7280"}}>{apiTime(t.start_time)} – {apiTime(t.end_time)}</div></div>
    </div>)}
    <h3 style={{...SH,marginTop:20}}>Rules</h3>
    {rules.map(r=><div key={r.RULE_ID} style={{...CD,borderLeft:"3px solid #3b82f6"}}>
      <div style={{fontWeight:600,fontSize:14,color:"#111"}}>{r.RULE_NAME}</div>
      {r.RULE_DESCRIPTION&&<div style={{fontSize:13,color:"#6b7280",marginTop:2}}>{r.RULE_DESCRIPTION}</div>}
      <div style={{fontSize:11,color:"#9ca3af",marginTop:4}}>{r.RULE_TYPE}{r.PARAM_1?` · ${r.PARAM_1}`:""}{r.USER_NAME?` · ${r.USER_NAME}`:""}</div>
    </div>)}
    <h3 style={{...SH,marginTop:20}}>Business Hours</h3>
    {[...new Set(bh.map(h=>h.LOCATION_NAME))].map(l=><div key={l} style={CD}>
      <div style={{fontWeight:600,fontSize:14,color:"#111",marginBottom:8}}>{l}</div>
      {bh.filter(h=>h.LOCATION_NAME===l).sort((a,b)=>a.DAY_OF_WEEK-b.DAY_OF_WEEK).map(h=>
        <div key={h.HOURS_ID} style={{display:"flex",justifyContent:"space-between",padding:"4px 0",borderBottom:"1px solid #f3f4f6",fontSize:13}}>
          <span>{h.DAY_NAME}</span><span style={{color:"#6b7280"}}>{h.IS_OPEN?`${h.OPEN_TIME} – ${h.CLOSE_TIME}`:"Closed"}</span>
        </div>
      )}
    </div>)}
    <div style={{textAlign:"center",padding:24,color:"#9ca3af",fontSize:12}}>Cookie Cutters · v2.0</div>
  </div>;
}

// ══════════════════════════════════
//  MAIN APP COMPONENT
// ══════════════════════════════════
function App() {
  const[view,setView]=useState("schedule");
  const[sv,setSv]=useState("calendar");
  const[ws,setWs]=useState(mondayOf(new Date()));
  const[loc,setLoc]=useState("All");
  const[toast,setToast]=useState(null);
  const[modal,setModal]=useState(null);
  const[loading,setLoading]=useState(true);
  const[jd,setJd]=useState("");
  const[drag,setDrag]=useState(null);
  const[me,setMe]=useState(null);
  const[users,setUsers]=useState([]);
  const[shifts,setShifts]=useState({});
  const[hasDrafts,setHasDrafts]=useState(false);
  const[tpls,setTpls]=useState([]);
  const[tor,setTor]=useState([]);
  const[closed,setClosed]=useState([]);
  const[bo,setBo]=useState([]);
  const[ann,setAnn]=useState([]);
  const[locs,setLocs]=useState([]);
  const[rules,setRules]=useState([]);
  const[bh,setBh]=useState([]);

  const tt=m=>{setToast(m);setTimeout(()=>setToast(null),3000)};
  const isM=me?.is_manager;
  const canE=me&&EDITORS.includes(me.user_id);
  const days=weekDays(ws);
  const wl=`${MS[days[0].getMonth()]} ${days[0].getDate()} – ${MS[days[6].getMonth()]} ${days[6].getDate()}, ${days[6].getFullYear()}`;
  const vL=isM?loc:me?.location_name;
  const vU=users.filter(u=>u.positions?.length>0&&(vL==="All"||u.location_name===vL));
  const gs=(uid,d)=>shifts[`${uid}-${dk(d)}`]||null;
  const isCl=d=>closed.some(c=>c.closed_date===dk(d));
  const getTOR=(uid,d)=>tor.find(r=>r.user_id===uid&&dk(d)>=r.start_date&&dk(d)<=r.end_date);

  const fetchAll=useCallback(async()=>{
    try{
      const u=await apiFetch("/api/scheduling/users");setUsers(u);setMe(u.find(x=>x.user_id==DEV_USER));
      setLocs([...new Map(u.map(x=>[x.location_id,{id:x.location_id,name:x.location_name}])).values()]);
      const[a,b,c,d,e,f,g]=await Promise.all([
        apiFetch("/api/scheduling/templates").catch(()=>[]),apiFetch("/api/scheduling/time-off").catch(()=>[]),
        apiFetch("/api/scheduling/admin/closed-dates").catch(()=>[]),apiFetch("/api/scheduling/admin/blackout-periods").catch(()=>[]),
        apiFetch("/api/scheduling/admin/announcements").catch(()=>[]),apiFetch("/api/scheduling/admin/scheduling-rules").catch(()=>[]),
        apiFetch("/api/scheduling/admin/business-hours").catch(()=>[])
      ]);
      setTpls(a);setTor(b);setClosed(c);setBo(d);setAnn(e);setRules(f);setBh(g);
      apiFetch("/api/scheduling/admin/log-login",{method:"POST",body:JSON.stringify({device_type:/Mobi/i.test(navigator.userAgent)?"mobile":"desktop"})}).catch(()=>{});
    }catch(e){console.error(e)}
  },[]);

  const fetchShifts=useCallback(async()=>{
    try{
      const data=await apiFetch(`/api/scheduling/shifts?week_start=${dk(ws)}`);
      const map={};let dr=false;
      data.forEach(s=>{map[`${s.user_id}-${s.shift_date}`]={shift_id:s.shift_id,start:apiTime(s.start_time),end:apiTime(s.end_time),role:s.position_name,hours:s.hours_scheduled,status:s.status||"DRAFT"};if((s.status||"DRAFT")==="DRAFT")dr=true});
      setShifts(map);setHasDrafts(dr);
    }catch(e){console.error(e)}
  },[ws]);

  useEffect(()=>{(async()=>{setLoading(true);await fetchAll();setLoading(false)})()},[]);
  useEffect(()=>{fetchShifts()},[ws]);

  // Actions
  const saveShift=async(uid,dateStr,data,locId)=>{const pm={Stylist:1,Receptionist:2};const ex=shifts[`${uid}-${dateStr}`];try{if(ex?.shift_id)await apiFetch(`/api/scheduling/shifts/${ex.shift_id}`,{method:"PUT",body:JSON.stringify({start_time:to24(data.start),end_time:to24(data.end),position_id:pm[data.role]||1})});else await apiFetch("/api/scheduling/shifts",{method:"POST",body:JSON.stringify({user_id:uid,location_id:locId,shift_date:dateStr,start_time:to24(data.start),end_time:to24(data.end),position_id:pm[data.role]||1})});setModal(null);await fetchShifts();tt("Saved")}catch(e){tt(e.message)}};
  const delShift=async(uid,ds)=>{const ex=shifts[`${uid}-${ds}`];if(!ex?.shift_id)return;try{await apiFetch(`/api/scheduling/shifts/${ex.shift_id}`,{method:"DELETE"});setModal(null);await fetchShifts();tt("Removed")}catch(e){tt(e.message)}};
  const moveShift=async(sid,nd)=>{try{await apiFetch(`/api/scheduling/shifts/${sid}/move`,{method:"PUT",body:JSON.stringify({new_date:nd})});await fetchShifts();tt("Moved")}catch(e){tt(e.message)}};
  const pub=async()=>{const li=locs.find(l=>l.name===loc)?.id;try{await apiFetch("/api/scheduling/shifts/publish",{method:"POST",body:JSON.stringify({week_start:dk(ws),location_id:li||undefined})});await fetchShifts();tt("Published!")}catch(e){tt(e.message)}};
  const unpub=async()=>{const li=locs.find(l=>l.name===loc)?.id;try{await apiFetch("/api/scheduling/shifts/unpublish",{method:"POST",body:JSON.stringify({week_start:dk(ws),location_id:li||undefined})});await fetchShifts();tt("Unpublished")}catch(e){tt(e.message)}};
  const shiftW=n=>{const d=new Date(ws);d.setDate(d.getDate()+n*7);setWs(d)};

  // Weekly hours
  const wh={};let th=0;vU.forEach(u=>{let h=0;days.forEach(d=>{const s=gs(u.user_id,d);if(s)h+=pT(s.end)-pT(s.start)});wh[u.user_id]=h;th+=h});

  if(loading||!me) return <div style={{display:"flex",alignItems:"center",justifyContent:"center",minHeight:"100vh"}}><div style={{textAlign:"center"}}><div style={{fontSize:18,fontWeight:700,color:"#111"}}>Cookie Cutters</div><div style={{color:"#999",fontSize:14,marginTop:4}}>Loading...</div></div></div>;

  const tabs=[{id:"home",l:"Overview",i:"◷"},{id:"schedule",l:"Schedule",i:"▦"},{id:"timeoff",l:"Time Off",i:"☰"},...(canE?[{id:"team",l:"People",i:"◎"},{id:"admin",l:"Admin",i:"⚙"}]:[])];

  return <div style={{background:"#f8f9fb",minHeight:"100vh",maxWidth:960,margin:"0 auto"}}>
    <Toast msg={toast}/>
    {modal&&<ShiftModal {...modal} templates={tpls} onSave={d=>saveShift(modal.uid,modal.dk,d,modal.locId)} onDelete={()=>delShift(modal.uid,modal.dk)} onClose={()=>setModal(null)}/>}

    {/* Header */}
    <div style={{background:"#fff",borderBottom:"1px solid #e5e7eb",padding:"12px 16px",display:"flex",justifyContent:"space-between",alignItems:"center",position:"sticky",top:0,zIndex:100}}>
      <div>
        <div style={{fontSize:10,fontWeight:600,color:"#9ca3af",textTransform:"uppercase",letterSpacing:1}}>Cookie Cutters</div>
        <div style={{fontSize:15,fontWeight:700,color:"#111"}}>{me.display_name} {isM&&<span style={{fontSize:10,background:"#dbeafe",color:"#1e40af",padding:"2px 6px",borderRadius:4,marginLeft:4,fontWeight:600}}>MGR</span>}</div>
      </div>
      {isM&&<select value={loc} onChange={e=>setLoc(e.target.value)} style={{padding:"6px 10px",borderRadius:6,border:"1px solid #d1d5db",fontSize:13,fontWeight:500,color:"#374151",background:"#fff"}}><option value="All">All Locations</option>{locs.map(l=><option key={l.id} value={l.name}>{l.name}</option>)}</select>}
    </div>

    <div style={{padding:"0 16px 100px"}}>
      {/* Overview */}
      {view==="home"&&<div style={{paddingTop:16}}>
        {ann.length>0&&<><h3 style={SH}>Announcements</h3>{ann.map(a=><div key={a.announcement_id} style={{...CD,borderLeft:"3px solid #3b82f6"}}><div style={{fontWeight:600,fontSize:14,color:"#111"}}>{a.title}</div><div style={{fontSize:13,color:"#6b7280",marginTop:4}}>{a.body}</div></div>)}</>}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginTop:16}}>
          <div style={CD}><div style={{fontSize:28,fontWeight:700,color:"#3b82f6"}}>{tor.filter(r=>r.status==="PENDING").length}</div><div style={{fontSize:12,color:"#6b7280"}}>Pending Requests</div></div>
          <div style={CD}><div style={{fontSize:28,fontWeight:700,color:"#3b82f6"}}>{vU.length}</div><div style={{fontSize:12,color:"#6b7280"}}>Team Members</div></div>
        </div>
        <button onClick={()=>setView("schedule")} style={{...BTN,width:"100%",marginTop:16,textAlign:"center"}}>View Schedule →</button>
      </div>}

      {/* Schedule */}
      {view==="schedule"&&<div style={{paddingTop:16}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <button onClick={()=>shiftW(-1)} style={NB}>‹</button>
          <div style={{textAlign:"center"}}>
            <div style={{fontSize:16,fontWeight:700,color:"#111"}}>{wl}</div>
            <div style={{display:"flex",gap:8,justifyContent:"center",marginTop:6}}>
              <button onClick={()=>setWs(mondayOf(new Date()))} style={{fontSize:12,fontWeight:500,color:"#3b82f6",background:"none",border:"1px solid #3b82f6",borderRadius:4,padding:"2px 8px",cursor:"pointer"}}>Today</button>
              <input type="date" value={jd} onChange={e=>setJd(e.target.value)} onBlur={()=>{if(jd){setWs(mondayOf(new Date(jd+"T12:00")));setJd("")}}} style={{fontSize:12,border:"1px solid #d1d5db",borderRadius:4,padding:"2px 6px",color:"#374151"}}/>
            </div>
          </div>
          <button onClick={()=>shiftW(1)} style={NB}>›</button>
        </div>
        <div style={{display:"flex",gap:6,marginBottom:12}}>
          <button onClick={()=>setSv("calendar")} style={{padding:"6px 14px",borderRadius:6,fontSize:12,fontWeight:600,border:`1px solid ${sv==="calendar"?"#3b82f6":"#e5e7eb"}`,background:sv==="calendar"?"#3b82f6":"#fff",color:sv==="calendar"?"#fff":"#6b7280",cursor:"pointer"}}>▦ Calendar</button>
          <button onClick={()=>setSv("list")} style={{padding:"6px 14px",borderRadius:6,fontSize:12,fontWeight:600,border:`1px solid ${sv==="list"?"#3b82f6":"#e5e7eb"}`,background:sv==="list"?"#3b82f6":"#fff",color:sv==="list"?"#fff":"#6b7280",cursor:"pointer"}}>☰ List</button>
        </div>
        {sv==="calendar"&&<CalendarGrid {...{days,canE,vU,gs,isCl,getTOR,wh,setModal,drag,setDrag,moveShift}}/>}
        {sv==="list"&&<ListView {...{days,canE,vU,gs,isCl,getTOR,setModal}}/>}

        {canE&&Object.keys(shifts).length>0&&<div style={{...CD,display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:12,...(hasDrafts?{borderColor:"#fbbf24",background:"#fffbeb"}:{borderColor:"#6ee7b7",background:"#ecfdf5"})}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}><Badge s={hasDrafts?"DRAFT":"PUBLISHED"}/><span style={{fontSize:13,color:"#374151"}}>{hasDrafts?"Unpublished changes":"Published"}</span></div>
          {hasDrafts?<button onClick={pub} style={{...BTN,padding:"8px 16px",fontSize:13}}>Publish</button>:<button onClick={unpub} style={{...BTN,padding:"8px 16px",fontSize:13,background:"#f3f4f6",color:"#374151"}}>Unpublish</button>}
        </div>}

        <div style={{...CD,marginTop:8}}>
          <div style={{fontWeight:600,fontSize:14,color:"#111",marginBottom:10}}>Weekly Summary</div>
          {vU.map(u=><div key={u.user_id} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #f3f4f6",fontSize:13}}><span style={{color:"#374151"}}>{u.display_name}</span><span style={{fontWeight:600,color:"#111"}}>{fmtH(wh[u.user_id]||0)}</span></div>)}
          <div style={{display:"flex",justifyContent:"flex-end",paddingTop:8,borderTop:"2px solid #e5e7eb",marginTop:6}}><span style={{fontWeight:700,color:"#3b82f6",fontSize:14}}>Total: {fmtH(th)}</span></div>
        </div>
      </div>}

      {view==="timeoff"&&<TimeOffView {...{me,isM,tor,vL,fetchAll,tt}}/>}
      {view==="team"&&canE&&<PeopleView {...{users:vU,locs,fetchAll,tt}}/>}
      {view==="admin"&&canE&&<AdminView {...{tpls,rules,bh}}/>}
    </div>

    {/* Bottom Nav */}
    <div style={{position:"fixed",bottom:0,left:"50%",transform:"translateX(-50%)",width:"100%",maxWidth:960,background:"#fff",borderTop:"1px solid #e5e7eb",display:"flex",justifyContent:"space-around",padding:"6px 0 env(safe-area-inset-bottom, 10px)",zIndex:100}}>
      {tabs.map(t=><button key={t.id} onClick={()=>setView(t.id)} style={{background:"none",border:"none",cursor:"pointer",display:"flex",flexDirection:"column",alignItems:"center",gap:2,padding:"4px 10px",fontSize:10,fontWeight:view===t.id?600:400,color:view===t.id?"#3b82f6":"#9ca3af",fontFamily:"inherit"}}><span style={{fontSize:17}}>{t.i}</span>{t.l}</button>)}
    </div>
  </div>;
}
