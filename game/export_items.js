/* Run in the study site's page (http://127.0.0.1:8765/Mesa-Academic-League.html,
   served by game/export_server.py) with every quarter selected. Exports what the
   quiz's "Everything" set deals, with the site's own wrong answers, to game/items.json. */
(async()=>{
const SUB={MA:'math',SC:'sci',EN:'eng',SS:'ss'};
const REF={tip:'tip',caps:'cap',nick:'state',motto:'state',spell:'voc',tense:'tense',myth:'myth','mb-roots':'roots','mb-sci':'roots','mb-econ':'roots'};
const out=[], dropped=[], n={};
/* The flashcards carry a written hint for every card. A card is matched to a
   quiz question by its id (after the prefix) AND its answer, so a hint only
   goes to a question asked the same way round as its card. */
const txt=s=>{ const d=document.createElement('div'); d.innerHTML=String(s); return d.textContent; };
const norm=s=>txt(s).toLowerCase().replace(/[^a-z0-9]+/g,'');
const keyOf=id=>{ id=String(id); return id.includes(':')?id.split(':').slice(1).join(':'):id; };
const CARDH=[];
for(const k in DECKS){ const d=DECKS[k]; if(typeof d.build!=='function') continue;
  for(const c of d.build()){ if(!c[3]||!c[4]) continue;
    CARDH.push({key:keyOf(c[4]), back:norm(c[1]), h:String(c[3]).replace(/\s*The letter count is on the card\./,'')}); } }
function cardHint(x){ const k=keyOf(x.id||x.cid), a=norm(x.a); if(!a) return '';
  const m=CARDH.find(c=>c.key===k && c.back.startsWith(a)); return m?m.h:''; }
function add(x,t,set){
  const d=distractorsFor(x), base=x.id||x.cid;
  if(d.length<3){dropped.push(base);return;}
  /* The site gives every direction of one fact the same card id; the game
     tracks each question on its own, so later directions are numbered. */
  const key=set+':'+base; n[key]=(n[key]||0)+1;
  out.push({t,id:(set==='bank'?'':set+'/')+base+(n[key]>1?'~'+n[key]:''),q:x.q,a:x.a,o:d.slice(0,3),
    l:x.l||2,h:x.hint||x.h||cardHint(x)||(set==='tip'?TIPHINTS[+String(x.cid).split(':')[1]]||'':''),c:x.ref?'':(x.c||''),qtr:x.qtr||null,
    /* Tip-offs are the game's golden questions; a miss shows why. */
    w:set==='tip'?(TIPWHY[+String(x.cid).split(':')[1]]||''):''});
}
for(const s of ['MA','SC','EN','SS']) qzBank(s).forEach(x=>add(x,SUB[s],'bank'));
for(const k of refSets()){ if(!REF[k]) throw new Error('New quiz set with no gear: '+k); QSETS[k].build().forEach(x=>add(x,REF[k],k)); }
const r=await fetch('/save',{method:'POST',body:JSON.stringify(out)});
console.log(out.length+' exported, dropped: '+dropped.join(', ')+' / '+await r.text());
})();
