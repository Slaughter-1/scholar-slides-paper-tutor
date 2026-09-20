var __measureCache = new Map(), __layoutCache = new Map();
const svg=document.querySelector('#map'),drawer=document.querySelector('#drawer'),detail=document.querySelector('#detail');let selected=null,scale=1,pan={x:0,y:0},collapsed=new Set(),showRelations=false;const types=[...new Set(MAP.nodes.map(n=>n.node_type))];types.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;document.querySelector('#type').append(o)});document.querySelector('#title').textContent=MAP.paper_identity.title;document.querySelector('#subtitle').textContent=`${MAP.paper_type} · ${MAP.source.verification_level}`;
function model(){const groups=MAP.paper_type==='benchmark'?['Why this benchmark','Benchmark Design','Evaluation Protocol','Results & Findings','Limits & Questions']:['Why','Method','Evidence','Key Concepts','Limits & Questions'];const nodes=MAP.nodes.map(n=>({...n,presentation_only:false}));const root=nodes.find(n=>!n.parent_id);if(root){const top=nodes.filter(n=>n.parent_id===root.id);const groupFor=n=>{const text=(n.title+' '+n.node_type).toLowerCase();if(/term|concept|definition/.test(text))return 3;if(/limit|question|takeaway|future/.test(text))return 4;if(/method|approach|algorithm|architecture|protocol|design/.test(text))return MAP.paper_type==='benchmark'?1:1;if(/evidence|result|finding|experiment|benchmark|metric|dataset/.test(text))return MAP.paper_type==='benchmark'?3:2;if(/problem|gap|boundary|goal|motivation|why/.test(text))return 0;return 2};groups.forEach((name,i)=>{const g={id:`visual.group.${i}`,title:name,summary:'',node_type:'group',claim_type:'explanation',availability:'supported',evidence_refs:[],parent_id:root.id,presentation_only:true};nodes.push(g)});top.forEach((n,j)=>{const i=Math.min(groups.length-1,groupFor(n));n.parent_id=`visual.group.${i}`})}return nodes}let tutorLayer='key';function tutorItemsFor(id){return (((TUTOR||{}).nodes||{})[id]||{}).map_items||[]}function tutorKindLabel(kind){return ({tutor_explanation:'Tutor',mathematical_meaning:'Meaning',intuition:'Intuition',necessity:'Why needed',prerequisite:'Prerequisite',example:'Example',analogy:'Analogy',misconception:'Misconception',user_question:'Question',comprehension_check:'Check',reader_analysis:'Analysis',verification_question:'Verify'})[kind]||'Tutor'}function withTutorOverlay(base){const nodes=[...base];if(!TUTOR||!TUTOR.nodes)return nodes;base.filter(n=>!n.presentation_only).forEach(anchor=>{const items=tutorItemsFor(anchor.id);if(!items.length)return;const groupId=`visual.tutor.group.${anchor.id}`;nodes.push({id:groupId,title:`Tutor Notes (${items.length})`,summary:'可折叠的 Tutor Explanation / Analysis',node_type:'tutor_group',claim_type:'explanation',availability:'supported',evidence_refs:[],parent_id:anchor.id,presentation_only:true,tutor_group:true,tutor_anchor:anchor.id});items.forEach(item=>nodes.push({id:`visual.tutor.item.${item.id}`,title:`[${tutorKindLabel(item.kind)}] ${item.title}`,summary:item.summary||item.body||'',node_type:'tutor_item',claim_type:'explanation',availability:'supported',evidence_refs:[],parent_id:groupId,presentation_only:true,tutor_overlay:true,tutor_anchor:anchor.id,tutor_item:item}))});return nodes}const V=withTutorOverlay(model()),vById=Object.fromEntries(V.map(n=>[n.id,n])),children={};V.forEach(n=>{if(n.parent_id)(children[n.parent_id]??=[]).push(n.id)});function depthOf(n){let d=0,p=n.parent_id;while(p&&vById[p]){d++;p=vById[p].parent_id}return d}function resetCollapsed(){collapsed.clear();V.forEach(n=>{if(n.tutor_group||n.tutor_overlay||depthOf(n)>=2)collapsed.add(n.id)})}resetCollapsed();
function textLines(text,max,ctx){const raw=String(text||''),tokens=/\s/.test(raw)?raw.split(/(\s+)/).filter(Boolean):Array.from(raw),out=[];let line='';for(const w of tokens){if(ctx.measureText(line+w).width>max&&line){out.push(line.trim());line=w.trim()}else line+=w}if(line)out.push(line.trim());while(out.length>2)out.pop();if(out.length===2&&tokens.length>out.length)out[1]=out[1].replace(/…?$/,'')+'…';return out}function measure(n){const c=document.createElement('canvas').getContext('2d');c.font='700 13px system-ui';const title=textLines(n.title,190,c);c.font='10px system-ui';const summary=textLines(n.summary,190,c);return {w:n.presentation_only?210:220,h:Math.max(58,30+title.length*16+summary.length*14),title,summary}}
function filtered(){const q=document.querySelector('#search').value.toLowerCase(),ty=document.querySelector('#type').value,st=document.querySelector('#status').value,av=document.querySelector('#availability').value;const matches=new Set(V.filter(n=>!q||[n.title,n.summary,...(n.evidence_refs||[])].join(' ').toLowerCase().includes(q)).map(n=>n.id));if(q){[...matches].forEach(id=>{let p=vById[id]?.parent_id;while(p){matches.add(p);p=vById[p]?.parent_id}})}return V.filter(n=>matches.has(n.id)&&(!ty||n.node_type===ty||n.presentation_only)&&(!st||(STUDY.nodes[n.id]||{}).status===st)&&(!av||n.availability===av))}
function layout(){const vs=filtered(),allow=new Set(vs.map(n=>n.id)),depth=new Map();function d(n){if(depth.has(n.id))return depth.get(n.id);const x=n.parent_id&&vById[n.parent_id]?d(vById[n.parent_id])+1:0;depth.set(n.id,x);return x}V.forEach(d);const visible=vs.filter(n=>d(n)<=2||n.presentation_only||!n.parent_id||!collapsed.has(n.parent_id));const pos={},sizes={};let y=35;function place(n){sizes[n.id]=measure(n);const kids=(children[n.id]||[]).map(id=>vById[id]).filter(k=>allow.has(k.id)&&visible.includes(k)&&!collapsed.has(n.id));if(!kids.length){pos[n.id]={x:40+depth.get(n.id)*270,y};y+=sizes[n.id].h+28;return}kids.forEach(place);const ys=kids.map(k=>pos[k.id].y);pos[n.id]={x:40+depth.get(n.id)*270,y:(Math.min(...ys)+Math.max(...ys))/2};}const roots=visible.filter(n=>!n.parent_id||!vById[n.parent_id]);roots.forEach(place);visible.filter(n=>!pos[n.id]).forEach(place);const all=Object.values(pos);return{vs:visible,pos,sizes,bbox:{x:Math.min(...all.map(p=>p.x),0),y:Math.min(...all.map(p=>p.y),0),w:Math.max(...all.map((p,i)=>p.x+sizes[visible[i].id].w),1),h:Math.max(...all.map((p,i)=>p.y+sizes[visible[i].id].h),1)}}}
function render(){const L=layout();svg.innerHTML='';const edges=document.createElementNS(svg.namespaceURI,'g'),nodes=document.createElementNS(svg.namespaceURI,'g');svg.append(edges,nodes);([...V.filter(n=>n.parent_id).map(n=>({source:n.parent_id,target:n.id,relation:'parent_of'})),...MAP.edges.filter(e=>e.relation!=='parent_of')]).forEach(e=>{const a=L.pos[e.source],b=L.pos[e.target];if(!a||!b)return;const p=document.createElementNS(svg.namespaceURI,'path'),sa=L.sizes[e.source],sb=L.sizes[e.target];p.setAttribute('d',`M${a.x+sa.w} ${a.y+sa.h/2} C${(a.x+b.x)/2} ${a.y+sa.h/2},${(a.x+b.x)/2} ${b.y+sb.h/2},${b.x} ${b.y+sb.h/2}`);p.setAttribute('class','edge '+(e.relation==='parent_of'?'':'cross'));if(showRelations&&e.relation!=='parent_of')p.classList.add('active');edges.append(p)});L.vs.forEach(n=>{const p=L.pos[n.id],s=L.sizes[n.id],g=document.createElementNS(svg.namespaceURI,'g');g.dataset.id=n.id;g.setAttribute('tabindex','0');g.setAttribute('role','button');g.setAttribute('aria-label',n.title);const r=document.createElementNS(svg.namespaceURI,'rect');r.setAttribute('x',p.x);r.setAttribute('y',p.y);r.setAttribute('width',s.w);r.setAttribute('height',s.h);const cc={paper_fact:'fact',analysis:'analysis',explanation:'explanation'}[n.claim_type]||'explanation';r.setAttribute('class',`node ${cc} ${n.node_type==='term'?'term':''} ${n.presentation_only?'group':''} ${selected===n.id?'selected':''}`);g.append(r);s.title.forEach((line,i)=>{const t=document.createElementNS(svg.namespaceURI,'text');t.setAttribute('x',p.x+12);t.setAttribute('y',p.y+19+i*15);t.setAttribute('class','node-title');t.textContent=line;g.append(t)});s.summary.forEach((line,i)=>{const t=document.createElementNS(svg.namespaceURI,'text');t.setAttribute('x',p.x+12);t.setAttribute('y',p.y+48+i*13);t.setAttribute('class','node-summary');t.textContent=line;g.append(t)});if((children[n.id]||[]).some(id=>!L.pos[id])){const b=document.createElementNS(svg.namespaceURI,'text');b.setAttribute('x',p.x+s.w-25);b.setAttribute('y',p.y+18);b.setAttribute('class','node-badge');b.textContent='+'+(children[n.id]||[]).length;g.append(b)}g.onclick=()=>select(n.id);g.ondblclick=()=>{collapsed.has(n.id)?collapsed.delete(n.id):collapsed.add(n.id);render()};g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(n.id)}};nodes.append(g)});document.querySelector('#count').textContent=`${L.vs.length}/${V.length} 节点`;transform()}
function transform(){svg.querySelectorAll(':scope>g').forEach(g=>g.setAttribute('transform',`translate(${pan.x},${pan.y}) scale(${scale})`))}function fit(){const L=layout(),r=svg.getBoundingClientRect(),pad=50;scale=Math.min((r.width-pad*2)/Math.max(1,L.bbox.w),(r.height-pad*2)/Math.max(1,L.bbox.h),1.2);pan={x:(r.width-L.bbox.w*scale)/2,y:(r.height-L.bbox.h*scale)/2};render()}
function saveState(){localStorage.setItem('paper-learning-map-study-state',JSON.stringify(STUDY))}function setState(v){if(!selected)return;const s=STUDY.nodes[selected]??={status:'unseen',mastery:0};s.status=v;s.mastery={learning:1,understood:2,mastered:3}[v]||0;s.last_reviewed_at=new Date().toISOString();saveState();select(selected)}function select(id){selected=id;const n=vById[id],s=STUDY.nodes[id]||{},t=TUTOR.nodes[id]||{};detail.innerHTML=`<h2>${esc(n.title)}</h2><div class="muted">${esc(n.node_type)} · ${esc(n.claim_type)} · ${esc(n.availability)}</div><h3>摘要</h3><p>${esc(n.summary||'暂无')}</p><h3>Paper Fact</h3><p>${n.paper_fact?esc(n.paper_fact.statement):'<span class="muted">该节点没有独立 Paper Fact。</span>'}</p><h3>Evidence</h3><p>${(n.evidence_refs||[]).map(x=>`<span class="pill">${esc(x)}</span>`).join('')||'暂无精确定位。'}</p><h3>Tutor Explanation</h3>${['mathematical_meaning','intuition','necessity','example','analogy'].map(k=>t[k]?`<p><b>${k}</b>：${esc(t[k])}</p>`:'').join('')||'<p class="muted">尚未补充。</p>'}<h3>我的问题</h3>${(t.questions||[]).map(q=>`<div class="question">${esc(q)}</div>`).join('')||'<p class="muted">暂无问题。</p>'}<h3>学习状态</h3><p>${esc(s.status||'unseen')} · 掌握度 ${s.mastery||0}/3</p><div class="progress"><i style="width:${(s.mastery||0)*33.33}%"></i></div><p><button onclick="setState('learning')">学习中</button> <button onclick="setState('understood')">已理解</button> <button onclick="setState('mastered')">已掌握</button></p>`;drawer.classList.add('open');render()}function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function focusNode(id){select(id);const L=layout(),r=svg.getBoundingClientRect(),p=L.pos[id];if(p){pan={x:r.width/2-(p.x+L.sizes[id].w/2)*scale,y:r.height/2-(p.y+L.sizes[id].h/2)*scale};render()}}document.querySelector('#close').onclick=()=>drawer.classList.remove('open');window.onkeydown=e=>{if(e.key==='Escape')drawer.classList.remove('open')};document.querySelector('#relations').onclick=()=>{showRelations=!showRelations;render()};document.querySelector('#fit').onclick=fit;document.querySelector('#reset').onclick=()=>{scale=1;pan={x:0,y:0};resetCollapsed();fit()};document.querySelector('#theme').onclick=()=>{document.body.classList.toggle('dark');render()};['search','type','status','availability'].forEach(id=>document.querySelector('#'+id).oninput=()=>{if(id==='search'){const q=document.querySelector('#search').value.toLowerCase(),hit=V.find(n=>[n.title,n.summary,...(n.evidence_refs||[])].join(' ').toLowerCase().includes(q));if(hit){let p=hit.parent_id;while(p){collapsed.delete(p);p=vById[p]?.parent_id}focusNode(hit.id);return}}render()});document.querySelector('#wrap').onwheel=e=>{e.preventDefault();scale=Math.max(.35,Math.min(2,scale*(e.deltaY<0?1.1:.9)));render()};let down=false,last;document.querySelector('#wrap').onmousedown=e=>{down=true;last=e};window.onmouseup=()=>down=false;window.onmousemove=e=>{if(down){pan.x+=e.clientX-last.clientX;pan.y+=e.clientY-last.clientY;last=e;transform()}};fit();

function tutorSearchText(n) {
  const item = n.tutor_item || {};
  const formulaText = (FORMULAS?.formulas || [])
    .filter(formula => formula.anchor_node_id === (n.tutor_anchor || n.id))
    .flatMap(formula => [formula.title, formula.equation_label, formula.paper_formula?.latex,
      formula.mathematical_meaning, formula.intuition, formula.necessity,
      ...(formula.symbols || []).flatMap(symbol => [symbol.symbol, symbol.meaning])])
    .join(' ');
  return [n.title, n.summary, ...(n.evidence_refs || []), item.title, item.summary, item.body, formulaText].join(' ').toLowerCase();
}
function tutorAllowed(n) {
  if (!n.tutor_overlay && !n.tutor_group) return true;
  if (tutorLayer === 'off') return false;
  if (n.tutor_group) return true;
  return tutorLayer === 'all' || Boolean(n.tutor_item && n.tutor_item.map_visible);
}
function parentChainOpen(n) {
  let p = vById[n.parent_id]?.parent_id;
  while (p) {
    if (collapsed.has(p)) return false;
    p = vById[p]?.parent_id;
  }
  return true;
}
__measureCache = new Map();
__layoutCache = new Map();
function measureCached(n) {
  const key = `${n.id}|${n.title}|${n.summary}|${n.presentation_only ? 1 : 0}`;
  if (!__measureCache.has(key)) __measureCache.set(key, measure(n));
  return __measureCache.get(key);
}
function filtered() {
  const q = document.querySelector('#search').value.toLowerCase();
  const ty = document.querySelector('#type').value;
  const st = document.querySelector('#status').value;
  const av = document.querySelector('#availability').value;
  const matches = new Set(V.filter(n => tutorAllowed(n) && (!q || tutorSearchText(n).includes(q))).map(n => n.id));
  if (q) [...matches].forEach(id => { let p = vById[id]?.parent_id; while (p) { matches.add(p); p = vById[p]?.parent_id; } });
  return V.filter(n => matches.has(n.id) && (!ty || n.node_type === ty || n.presentation_only) && (!st || (STUDY.nodes[n.id] || {}).status === st) && (!av || n.availability === av));
}
function layout() {
  const vs = filtered(), allow = new Set(vs.map(n => n.id)), depth = new Map();
  const cacheKey = `${document.querySelector('#search').value}|${document.querySelector('#type').value}|${document.querySelector('#status').value}|${document.querySelector('#availability').value}|${tutorLayer}|${[...collapsed].sort().join(',')}`;
  if (__layoutCache.has(cacheKey)) return __layoutCache.get(cacheKey);
  function d(n) { if (depth.has(n.id)) return depth.get(n.id); const value = n.parent_id && vById[n.parent_id] ? d(vById[n.parent_id]) + 1 : 0; depth.set(n.id, value); return value; }
  V.forEach(d);
  const visible = vs.filter(n => d(n) <= 2 || !n.parent_id || (!n.tutor_overlay && n.presentation_only && !n.tutor_group) || (n.tutor_group && parentChainOpen(n)) || !collapsed.has(n.parent_id));
  const pos = {}, sizes = {}; let y = 35;
  function place(n) {
    sizes[n.id] = measureCached(n);
    const expanded = !collapsed.has(n.id);
    const kids = (children[n.id] || []).map(id => vById[id]).filter(k => allow.has(k.id) && visible.includes(k) && (expanded || k.tutor_group));
    if (!kids.length) { pos[n.id] = { x: 40 + depth.get(n.id) * 270, y }; y += sizes[n.id].h + 28; return; }
    kids.forEach(place);
    const ys = kids.map(k => pos[k.id].y);
    pos[n.id] = { x: 40 + depth.get(n.id) * 270, y: (Math.min(...ys) + Math.max(...ys)) / 2 };
  }
  visible.filter(n => !n.parent_id || !vById[n.parent_id]).forEach(place);
  visible.filter(n => !pos[n.id]).forEach(place);
  const entries = Object.entries(pos), all = entries.map(([, p]) => p);
  const result = { vs: visible, pos, sizes, bbox: { x: Math.min(...all.map(p => p.x), 0), y: Math.min(...all.map(p => p.y), 0), w: Math.max(...entries.map(([id, p]) => p.x + sizes[id].w), 1), h: Math.max(...entries.map(([id, p]) => p.y + sizes[id].h, 1)) } };
  __layoutCache.set(cacheKey, result); return result;
}
let __renderQueued = false;
function scheduleRender() {
  if (__renderQueued) return;
  __renderQueued = true;
  requestAnimationFrame(() => {
    __renderQueued = false;
    render();
  });
}
function render() {
  const L = layout(); svg.innerHTML = '';
  const edges = document.createElementNS(svg.namespaceURI, 'g'), nodes = document.createElementNS(svg.namespaceURI, 'g'); svg.append(edges, nodes);
  ([...V.filter(n => n.parent_id).map(n => ({ source: n.parent_id, target: n.id, relation: 'parent_of' })), ...MAP.edges.filter(e => e.relation !== 'parent_of')]).forEach(e => {
    const a = L.pos[e.source], b = L.pos[e.target]; if (!a || !b) return;
    const p = document.createElementNS(svg.namespaceURI, 'path'), sa = L.sizes[e.source], sb = L.sizes[e.target];
    p.setAttribute('d', `M${a.x + sa.w} ${a.y + sa.h / 2} C${(a.x + b.x) / 2} ${a.y + sa.h / 2},${(a.x + b.x) / 2} ${b.y + sb.h / 2},${b.x} ${b.y + sb.h / 2}`);
    p.setAttribute('class', 'edge ' + (e.relation === 'parent_of' ? '' : 'cross')); if (showRelations && e.relation !== 'parent_of') p.classList.add('active'); edges.append(p);
  });
  L.vs.forEach(n => {
    const p = L.pos[n.id], s = L.sizes[n.id], g = document.createElementNS(svg.namespaceURI, 'g'); g.dataset.id = n.id; g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button'); g.setAttribute('aria-label', n.title);
    const r = document.createElementNS(svg.namespaceURI, 'rect'); r.setAttribute('x', p.x); r.setAttribute('y', p.y); r.setAttribute('width', s.w); r.setAttribute('height', s.h);
    const cc = { paper_fact: 'fact', analysis: 'analysis', explanation: 'explanation' }[n.claim_type] || 'explanation';
    const tc = n.tutor_overlay ? 'tutor-item' : n.tutor_group ? 'tutor-group' : '';
    r.setAttribute('class', `node ${cc} ${n.node_type === 'term' ? 'term' : ''} ${n.presentation_only ? 'group' : ''} ${tc} ${selected === n.id ? 'selected' : ''}`); g.append(r);
    s.title.forEach((line, i) => { const t = document.createElementNS(svg.namespaceURI, 'text'); t.setAttribute('x', p.x + 12); t.setAttribute('y', p.y + 19 + i * 15); t.setAttribute('class', 'node-title'); t.textContent = line; g.append(t); });
    s.summary.forEach((line, i) => { const t = document.createElementNS(svg.namespaceURI, 'text'); t.setAttribute('x', p.x + 12); t.setAttribute('y', p.y + 48 + i * 13); t.setAttribute('class', 'node-summary'); t.textContent = line; g.append(t); });
    const hidden = (children[n.id] || []).filter(id => !L.pos[id] && tutorAllowed(vById[id])).length; if (hidden) { const b = document.createElementNS(svg.namespaceURI, 'text'); b.setAttribute('x', p.x + s.w - 25); b.setAttribute('y', p.y + 18); b.setAttribute('class', 'node-badge'); b.textContent = '+' + hidden; g.append(b); }
    g.onclick = () => select(n.id); g.ondblclick = () => { collapsed.has(n.id) ? collapsed.delete(n.id) : collapsed.add(n.id); scheduleRender(); }; g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(n.id); } }; nodes.append(g);
  });
  document.querySelector('#count').textContent = `${L.vs.length}/${V.length} 节点 · Tutor Layer: ${tutorLayer}`; transform();
}
function setState(v) { if (!selected) return; const anchor = vById[selected]?.tutor_anchor || selected, s = STUDY.nodes[anchor] ??= { status: 'unseen', mastery: 0 }; s.status = v; s.mastery = { learning: 1, understood: 2, mastered: 3 }[v] || 0; s.last_reviewed_at = new Date().toISOString(); saveState(); select(selected); }
function deepHref(nodeId, formulaId) { return `paper-tutor-deep-v2.html#${formulaId ? `formula=${encodeURIComponent(formulaId)}` : `node-${String(nodeId).replace(/_/g, '-').replace(/[^a-zA-Z0-9-]+/g, '-').replace(/^-|-$/g, '').toLowerCase()}`}`; }
function mapHash(nodeId, formulaId) { return `#${formulaId ? `formula=${encodeURIComponent(formulaId)}` : `node=${encodeURIComponent(nodeId)}`}`; }
function syncStatusHtml() {
  const receipts = Array.isArray(window.SYNC_RECEIPTS) ? window.SYNC_RECEIPTS : [];
  const latest = receipts.length ? receipts[receipts.length - 1] : null;
  const status = latest?.status === 'success' ? (latest.unresolved_added > 0 ? 'unresolved' : 'synced') : latest?.status === 'failed' ? 'sync failed' : 'not synced';
  return `<p class="sync-status" data-sync-status="${esc(status)}">Learning Map: ${esc(status)}</p>`;
}
function select(id) {
  selected = id; const n = vById[id]; if (!n) return; const anchor = vById[n.tutor_anchor || id] || n, s = STUDY.nodes[anchor.id] || {}, t = TUTOR.nodes[anchor.id] || {}, items = t.map_items || [];
  if (n.tutor_overlay) { const item = n.tutor_item || {}; detail.innerHTML = `<h2>${esc(item.title || n.title)}</h2><div class="muted">${esc(tutorKindLabel(item.kind))} · Tutor layer · ${esc(item.origin || '')}</div><h3>Anchor</h3><p>${esc(anchor.title)}</p><h3>${esc(tutorKindLabel(item.kind))}</h3><p>${esc(item.body || item.summary || '暂无')}</p><h3>来源边界</h3><p class="muted">这是 Tutor Explanation / Tutor Analysis，保留在 tutor-state.json，不是 Paper Fact。</p>`; }
  else if (n.tutor_group) { detail.innerHTML = `<h2>${esc(n.title)}</h2><div class="muted">Tutor group · anchor: ${esc(anchor.title)}</div><h3>可见状态</h3><p>${items.length} 条 Tutor item。双击节点展开或折叠。</p><h3>说明</h3><p class="muted">Tutor 内容不会写入 paper-map.json 的 factual layer。</p>`; }
  else { detail.innerHTML = `<h2>${esc(n.title)}</h2><div class="muted">${esc(n.node_type)} · ${esc(n.claim_type)} · ${esc(n.availability)}</div><h3>摘要</h3><p>${esc(n.summary || '暂无')}</p><h3>Paper Fact</h3><p>${n.paper_fact ? esc(n.paper_fact.statement) : '<span class="muted">该节点没有独立 Paper Fact。</span>'}</p><h3>Evidence</h3><p>${(n.evidence_refs || []).map(x => `<span class="pill">${esc(x)}</span>`).join('') || '暂无精确定位。'}</p><h3>Tutor Knowledge</h3>${items.map(item => `<article class="pill"><b>[${esc(tutorKindLabel(item.kind))}] ${esc(item.title)}</b><p>${esc(item.body || item.summary)}</p><small class="muted">${esc(item.origin || '')} · source_layer=tutor</small></article>`).join('') || '<p class="muted">尚未补充。</p>'}<h3>Legacy Tutor Explanation</h3>${['mathematical_meaning', 'intuition', 'necessity', 'example', 'analogy'].map(k => t[k] ? `<p><b>${k}</b>：${esc(t[k])}</p>` : '').join('') || '<p class="muted">尚未补充。</p>'}<h3>我的问题</h3>${(t.questions || []).map(q => `<div class="question">${esc(q)}</div>`).join('') || '<p class="muted">暂无问题。</p>'}<h3>学习状态</h3><p>${esc(s.status || 'unseen')} · 掌握度 ${s.mastery || 0}/3</p><div class="progress"><i style="width:${(s.mastery || 0) * 33.33}%"></i></div><p><button onclick="setState('learning')">学习中</button> <button onclick="setState('understood')">已理解</button> <button onclick="setState('mastered')">已掌握</button></p>`; }
  if (!n.tutor_overlay && !n.tutor_group) detail.insertAdjacentHTML('beforeend', `<p class="deep-nav"><a href="${esc(deepHref(anchor.id))}">Open in Deep Reading</a> <code>anchor_node_id=${esc(anchor.id)}</code></p>${syncStatusHtml()}`);
  drawer.classList.add('open'); render(); renderFormulaDetails(anchor.id);
}
function wireTutorLayer() {
  document.querySelector('#tutor-layer').value = tutorLayer;
  document.querySelector('#tutor-layer').onchange = e => { tutorLayer = e.target.value; resetCollapsed(); fit(); };
  ['search', 'type', 'status', 'availability'].forEach(id => document.querySelector('#' + id).oninput = () => {
    if (id === 'search') { const q = document.querySelector('#search').value.toLowerCase(), hit = V.find(n => tutorAllowed(n) && tutorSearchText(n).includes(q)); if (q && hit) { let p = hit.parent_id; while (p) { collapsed.delete(p); p = vById[p]?.parent_id; } focusNode(hit.id); return; } }
    render();
  });
}
wireTutorLayer(); resetCollapsed(); fit();

// Formula experience is a presentation enhancement over the stable map
// interactions above.  Formula data is injected as a derived index; no
// Markdown or factual graph text is parsed here.
window.__formulaRenderErrors = window.__formulaRenderErrors || [];
function formulaForAnchor(anchor) {
  return (FORMULAS?.formulas || []).filter(formula => formula.anchor_node_id === anchor);
}
function formulaLayerLabel(layer) {
  return layer?.formula_kind === 'paper_formula' ? '[Paper Formula]' :
    layer?.formula_kind === 'tutor_derivation' ? '[Tutor Explanation]' : '[Tutor Example]';
}
function formulaLayerHtml(layer, formulaId, layerName) {
  if (!layer) return '';
  const label = formulaLayerLabel(layer);
  const text = layer.text || '';
  const latex = layer.latex || '';
  const renderId = `formula-render-${esc(formulaId)}-${esc(layerName)}`;
  const raw = latex ? `<details class="formula-source"><summary>Show LaTeX</summary><pre class="raw-tex" data-raw-tex="${esc(latex)}">${esc(latex)}</pre><button type="button" class="copy-tex" data-copy-tex="${esc(latex)}">Copy LaTeX</button></details>` : '';
  return `<div class="formula-layer ${esc(layerName)}"><div class="formula-badge">${esc(label)}</div>${latex ? `<div id="${renderId}" class="formula-render" data-tex="${esc(latex)}" data-display="${layer.display_mode !== false}"></div>` : ''}${text ? `<p class="formula-layer-text">${esc(text)}</p>` : ''}${raw}</div>`;
}
function renderOneFormula(target) {
  const latex = target?.dataset?.tex || '';
  if (!latex) return;
  try {
    if (!window.katex || typeof window.katex.render !== 'function') throw new Error('KaTeX unavailable');
    window.katex.render(latex, target, { displayMode: target.dataset.display !== 'false', throwOnError: true, trust: false, strict: 'warn', output: 'htmlAndMathml' });
    target.dataset.rendered = 'true';
  } catch (error) {
    window.__formulaRenderErrors.push({ latex, message: String(error?.message || error) });
    target.dataset.rendered = 'false';
    target.innerHTML = `<pre class="raw-tex formula-fallback">${esc(latex)}</pre><div class="formula-error" role="status">Formula rendering unavailable</div>`;
  }
}
function renderFormulaDetails(anchor) {
  const formulaStarted = performance.now();
  const formulas = formulaForAnchor(anchor);
  if (!formulas.length) return;
  const host = document.querySelector('#detail');
  if (!host) return;
  host.querySelectorAll('.formula-drawer-block').forEach(node => node.remove());
  const html = formulas.map(formula => {
    const paper = formula.paper_formula || {};
    const derivation = formula.tutor_derivation || {};
    const exampleLayer = formula.tutor_example || {};
    const symbols = (formula.symbols || []).map(symbol => `<li><code>${esc(symbol.symbol)}</code> ${esc(symbol.meaning)} <small class="muted">${esc(symbol.source_layer || '')}</small></li>`).join('') || `<li class="muted">Symbols not fully available in structured analysis.</li>`;
    const refs = (formula.evidence?.evidence_refs || paper.evidence_refs || []).map(ref => `<span class="pill">${esc(ref)}</span>`).join('') || '<span class="muted">No evidence reference.</span>';
    return `<section class="formula-drawer-block" data-formula-id="${esc(formula.id)}"><h3>Formula · ${esc(formula.title)}${formula.equation_label ? ` · ${esc(formula.equation_label)}` : ''}</h3><p class="deep-nav"><a href="${esc(deepHref(formula.anchor_node_id, formula.id))}">Open in Deep Reading</a> <code>anchor_node_id=${esc(formula.anchor_node_id)}</code></p>${formulaLayerHtml(paper, formula.id, 'paper-formula')}${formulaLayerHtml(derivation, formula.id, 'tutor-derivation')}${formulaLayerHtml(exampleLayer, formula.id, 'tutor-example')}<h4>Symbols</h4><ul class="formula-symbols">${symbols}</ul><h4>Mathematical Meaning</h4><p>${esc(formula.mathematical_meaning || 'Not available in the structured source.')}</p><h4>Intuition</h4><p>${esc(formula.intuition || 'Not available in the structured source.')}</p><h4>Necessity</h4><p>${esc(formula.necessity || 'Not available in the structured source.')}</p><h4>Example</h4><p>${esc(formula.example || 'Not available in the structured source.')}</p><h4>Misunderstanding</h4><p>${esc(formula.misunderstanding || 'Not available in the structured source.')}</p><h4>Evidence</h4><p>${refs}</p><h4>Source Trace</h4><pre class="source-trace">${esc(JSON.stringify(paper.source_trace || [], null, 2))}</pre></section>`;
  }).join('');
  host.insertAdjacentHTML('beforeend', html);
  host.querySelectorAll('.formula-render[data-tex]').forEach(renderOneFormula);
  host.querySelectorAll('.copy-tex').forEach(button => button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(button.dataset.copyTex || ''); button.textContent = 'Copied'; }
    catch { button.textContent = 'Copy unavailable'; }
  }));
  window.__lastFormulaRenderMs = performance.now() - formulaStarted;
}
document.querySelector('#search')?.addEventListener('input', () => {
  const q = document.querySelector('#search').value.trim().toLowerCase();
  if (!q) return;
  const formula = (FORMULAS?.formulas || []).find(item => [item.title, item.equation_label, item.paper_formula?.latex, item.mathematical_meaning, item.intuition, item.necessity, ...(item.symbols || []).flatMap(symbol => [symbol.symbol, symbol.meaning])].join(' ').toLowerCase().includes(q));
  if (!formula) return;
  let parent = formula.anchor_node_id;
  while (parent) { collapsed.delete(parent); parent = vById[parent]?.parent_id; }
  focusNode(formula.anchor_node_id);
  requestAnimationFrame(() => document.querySelector(`[data-formula-id="${CSS.escape(formula.id)}"]`)?.scrollIntoView({ block: 'nearest' }));
});

// Stable Deep ↔ Map URL contract.  Hashes are data-only and do not require a
// server or network request: #node=<paper node id> or #formula=<formula id>.
function openMapHash() {
  const raw = decodeURIComponent(window.location.hash || '');
  if (raw.startsWith('#formula=')) {
    const formulaId = raw.slice('#formula='.length);
    const formula = (FORMULAS?.formulas || []).find(item => item.id === formulaId);
    if (!formula || !vById[formula.anchor_node_id]) return;
    let parent = formula.anchor_node_id;
    while (parent) { collapsed.delete(parent); parent = vById[parent]?.parent_id; }
    focusNode(formula.anchor_node_id);
    requestAnimationFrame(() => document.querySelector(`[data-formula-id="${CSS.escape(formulaId)}"]`)?.scrollIntoView({ block: 'nearest' }));
    return;
  }
  if (raw.startsWith('#node=')) {
    const nodeId = raw.slice('#node='.length);
    if (!vById[nodeId]) return;
    let parent = nodeId;
    while (parent) { collapsed.delete(parent); parent = vById[parent]?.parent_id; }
    focusNode(nodeId);
  }
}
window.addEventListener('hashchange', openMapHash);
requestAnimationFrame(openMapHash);
if (document.querySelector('#sync-status')) document.querySelector('#sync-status').textContent = `Learning Map: ${SYNC_RECEIPTS?.length ? (SYNC_RECEIPTS.at(-1)?.status === 'failed' ? 'sync failed' : ((SYNC_RECEIPTS.at(-1)?.unresolved_total || 0) > 0 ? 'unresolved' : 'synced')) : 'not synced'}`;
