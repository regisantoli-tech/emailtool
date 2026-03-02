let currentPage = 1;
const limit = 100;
function qs(id){return document.getElementById(id);}
function setStatus(t){const el=qs("status"); if(el) el.textContent=t;}
function buildParams(page){
  const p=new URLSearchParams();
  p.set("page", page);
  p.set("limit", limit);
  const folder=(qs("folder")?.value||"").trim();
  const start_date=(qs("start_date")?.value||"").trim();
  const end_date=(qs("end_date")?.value||"").trim();
  const search=(qs("search")?.value||"").trim();
  const category=qs("category")?.value||"";
  if(folder) p.set("folder", folder);
  if(start_date) p.set("start_date", start_date);
  if(end_date) p.set("end_date", end_date);
  if(search) p.set("search", search);
  if(category) p.set("category", category);
  return p;
}
function escapeHtml(s){
  return String(s).replaceAll("&","&amp;").replaceAll("&lt;","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}
function selectedUids(){
  return Array.from(document.querySelectorAll(".cb:checked")).map(x=>x.value);
}
async function loadEmails(page){
  currentPage=page;
  setStatus("Carregando...");
  const params=buildParams(page);
  const res=await fetch(`/emails?${params.toString()}`);
  if(!res.ok){
    let msg="Erro ao carregar.";
    try{msg=(await res.json()).detail||msg;}catch{}
    setStatus(msg);
    return;
  }
  const data=await res.json();
  const tbody=qs("tbody");
  tbody.innerHTML="";
  (data.items||[]).forEach(item=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`<td><input type="checkbox" class="cb" value="${escapeHtml(item.uid)}"/></td><td>${escapeHtml(item.date||"")}</td><td>${escapeHtml(item.sender||"")}</td><td>${escapeHtml(item.subject||"")}</td><td>${escapeHtml(item.category||"")}${item.service ? "<div class='muted'>"+escapeHtml(item.service)+"</div>" : ""}</td><td>${escapeHtml(item.snippet||"")}</td>`;
    tbody.appendChild(tr);
  });
  qs("page").textContent=String(data.page||page);
  qs("total").textContent=String(data.total||0);
  qs("select_all").checked=false;
  setStatus(`Itens nesta página: ${(data.items||[]).length}`);
}
async function executeAction(){
  const action=qs("bulk_action").value;
  const folder=(qs("target_folder").value||"").trim();
  const uids=selectedUids();
  if(uids.length===0){alert("Selecione pelo menos 1 e-mail."); return;}
  if(action==="delete"){const ok=confirm("ATENÇÃO: isso vai excluir definitivamente. Deseja continuar?"); if(!ok) return;}
  if((action==="move"||action==="create_folder") && !folder){alert("Informe a pasta destino."); return;}
  setStatus("Executando...");
  const res=await fetch("/actions/execute",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action, folder, uids})});
  if(!res.ok){let msg="Falha ao executar.";try{msg=(await res.json()).detail||msg;}catch{}alert(msg);setStatus("Falha.");return;}
  await loadEmails(currentPage);
  setStatus("Concluído.");
}
function exportXlsx(){
  const params=buildParams(1);
  params.delete("page");
  params.delete("limit");
  window.location.href = `/export?${params.toString()}`;
}
function prevPage(){ if(currentPage == 1) return; loadEmails(currentPage - 1); }
function nextPage(){ loadEmails(currentPage + 1); }
document.addEventListener("DOMContentLoaded", ()=>{
  const sel=qs("select_all");
  if(sel){
    sel.addEventListener("change", (e)=>{
      const checked=e.target.checked;
      document.querySelectorAll(".cb").forEach(cb=>cb.checked=checked);
    });
  }
  loadEmails(1);
});
