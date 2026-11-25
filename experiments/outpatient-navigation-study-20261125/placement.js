variant => {
  if (variant==='A') return;
  const prior=renderFieldKnowledgeSearch;
  const style=document.createElement('style');
  style.textContent='.study-field-action{display:inline-block;min-height:24px;margin:0;padding:0 2px;border:0;border-radius:0;background:transparent;color:#07578e;text-decoration:underline;text-underline-offset:2px;font:inherit;line-height:inherit;cursor:pointer}.study-field-action:focus-visible{outline:2px solid #07578e;outline-offset:2px}';
  document.head.append(style);
  renderFieldKnowledgeSearch=key=>{
    const html=prior(key), state=appState.fieldKnowledgeSearch[key]||{};
    if(state.status!=='ready') return html;
    const template=document.createElement('template');template.innerHTML=html;
    const button=document.createElement('button');button.type='button';button.dataset.labKey=key;
    button.className=variant==='B'?'secondary-action':'study-field-action';
    const title=FIELD_DEFS.find(([k])=>k===key)?.[1]||key;
    button.textContent=fieldEvidencePresentation(activeRecordFields()?.[key],key).action+' · '+title;
    if(variant==='D'){
      const para=template.content.querySelector('[aria-label="本次检索与来源"] > p, .empty-state > p');
      if(!para) return html;
      para.append(' ',button);
    }else template.content.prepend(button);
    return template.innerHTML;
  };
  document.getElementById('detailDrawerContent').addEventListener('click',event=>{
    const button=event.target.closest('[data-lab-key]');
    if(!button)return;
    const key=button.dataset.labKey;
    if(!currentFieldKnowledgeOpener()||currentFieldKnowledgeOpener().dataset.knowledgeField!==key)return;
    openWorkbenchDetail('field:'+key);
  });
}
