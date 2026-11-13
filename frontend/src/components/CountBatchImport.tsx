import {useEffect,useState} from 'react';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {useResearch} from '../stores/research';
import {Notice} from './common/Notice';
import {previewCountBatch,getCountBatches,BatchRow} from '../api/counts';
import {CountBatchPreview,CountBatchLedger,Study} from '../types/domain';
import {time} from '../utils/format';

const N_MIN=1,N_MAX=100000;

export function CountBatchImport({study}:{study:Study}){
  const {user}=useAuth();const a=useAction();const s=useResearch();
  const [sourceBatch,setSourceBatch]=useState('');const [version,setVersion]=useState(1);
  const [text,setText]=useState('');const [preview,setPreview]=useState<CountBatchPreview|null>(null);
  const [ledger,setLedger]=useState<CountBatchLedger[]>([]);
  const readOnly=user?.role==='viewer';
  const touch=()=>setPreview(null);

  function parseRows():{rows:BatchRow[];errors:{row:number;lot_code:string;reason:string}[]}{
    const errors:{row:number;lot_code:string;reason:string}[]=[];const rows:BatchRow[]=[];const seen=new Set<string>();
    text.split(/\r?\n/).forEach((line,idx)=>{
      const trimmed=line.trim();if(!trimmed)return;
      const parts=trimmed.split(/[,\t;，；]/).map(x=>x.trim());
      const rowNo=idx+1;
      if(parts.length!==3){errors.push({row:rowNo,lot_code:parts[0]||'',reason:'每行须为 批次编号,n,k 三列'});return;}
      const [lot_code,ns,ks]=parts;
      if(!/^-?\d+$/.test(ns)||!/^-?\d+$/.test(ks)){errors.push({row:rowNo,lot_code,reason:'n/k必须为整数'});return;}
      const n=Number(ns),k=Number(ks);
      if(seen.has(lot_code))errors.push({row:rowNo,lot_code,reason:'来源批号内批次编号重复'});
      seen.add(lot_code);rows.push({lot_code,n,k});
    });
    return {rows,errors};
  }

  async function send(commit:boolean){
    const {rows,errors}=parseRows();
    if(errors.length){setPreview({id:null,study_id:study.id,source_batch:sourceBatch,version,content_hash:'',commit,accepted:false,outcome:commit?'rejected_precheck':'preview_rejected',total_lots:rows.length+errors.length,accepted_lots:0,rejected_rows:errors,conflicts:[],diff:[],published_at:'',created_at:''});return;}
    if(!rows.length){setPreview({id:null,study_id:study.id,source_batch:sourceBatch,version,content_hash:'',commit,accepted:false,outcome:commit?'rejected_precheck':'preview_rejected',total_lots:0,accepted_lots:0,rejected_rows:[{row:0,lot_code:'',reason:'未解析到任何数据行'}],conflicts:[],diff:[],published_at:'',created_at:''});return;}
    const out=await previewCountBatch(study.id,{source_batch:sourceBatch.trim(),version,commit,rows});
    setPreview(out);
    if(commit&&out.accepted){await Promise.all([s.refresh(),s.loadStudy(study.id),loadLedger()]);}
  }

  async function loadLedger(){setLedger(await getCountBatches(study.id));}
  useEffect(()=>{loadLedger();},[study.id]);

  const outcomeText:Record<string,string>={preview_ok:'预检通过，可整批发布',preview_rejected:'预检未通过，整批拒绝',publishable:'可发布',rejected_precheck:'整批拒绝，未写入任何计数',published:'已发布：计数整批更新',replay:'重放：同版同内容，未重复写入',conflict:'冲突：同版异内容，已拒绝',stale:'旧版迟到：不回退，已拒绝'};

  return <section className="batch-import">
    <div className="section-heading"><h2>来源批号整批导入</h2><span>预检归属、整数范围与全批齐备；坏行整批拒绝</span></div>
    {readOnly&&<p className="role-note">阅读者只读；整批导入需要分析员或种质负责人权限。</p>}
    <div className="form-row">
      <label>来源批号<input aria-label="来源批号" value={sourceBatch} disabled={readOnly} maxLength={120} placeholder="例如 duocen-germination-lots-202612.csv" onChange={e=>{setSourceBatch(e.target.value);touch();}}/></label>
      <label style={{maxWidth:160}}>递增版本<input aria-label="递增版本" type="number" min={1} step={1} value={version} disabled={readOnly} onChange={e=>{setVersion(Math.max(1,Math.trunc(Number(e.target.value)||1)));touch();}}/></label>
    </div>
    <label>批次计数（每行：批次编号,n,k；支持逗号/制表符/分号分隔）
      <textarea aria-label="批次计数文本" style={{minHeight:150,fontFamily:'Courier New,monospace'}} value={text} disabled={readOnly} placeholder={'DC-01-L01,100,85\nDC-01-L02,120,90'} onChange={e=>{setText(e.target.value);touch();}}/>
    </label>
    <small>整数口径：{N_MIN}≤n≤{N_MAX}、0≤k≤n；必须覆盖研究内全部批次，不接受跨研究批次、小数或布尔值。同版同内容重放不重复写入，同版异内容报冲突，旧版迟到不回退。</small>
    {!readOnly&&<div className="form-row" style={{marginTop:14}}>
      <button className="outline" disabled={a.busy||!sourceBatch.trim()} onClick={()=>a.execute(()=>send(false))}>预检差异</button>
      <button className="primary" disabled={a.busy||!sourceBatch.trim()||!preview?.accepted||preview.commit} onClick={()=>a.execute(()=>send(true))}>整批发布</button>
      <button className="outline" onClick={loadLedger}>刷新批次台账</button>
    </div>}
    {readOnly&&<button className="outline" onClick={loadLedger}>查看批次台账</button>}
    <Notice message={a.error} onRetry={s.refresh}/>
    {preview&&<div className={'batch-result '+(preview.accepted?'ok':'reject')}>
      <div className="batch-result-head"><b>{outcomeText[preview.outcome]||preview.outcome}</b><span>{preview.accepted_lots}/{preview.total_lots} 行 · 内容指纹 {preview.content_hash.slice(0,16)}…</span></div>
      {preview.conflicts.length>0&&<div className="batch-conflicts">{preview.conflicts.map((c,i)=><p key={i} role="alert">⚠ {c.message}</p>)}</div>}
      {preview.rejected_rows.length>0&&<div className="table-wrap compact-table"><table><thead><tr><th>行号</th><th>批次</th><th>拒绝原因</th></tr></thead><tbody>
        {preview.rejected_rows.map((r,i)=><tr key={i}><td>{r.row||'—'}</td><td>{r.lot_code||'—'}</td><td className="warning">{r.reason}</td></tr>)}
      </tbody></table></div>}
      {preview.accepted&&preview.diff.length>0&&<div className="table-wrap compact-table"><table><thead><tr><th>批次</th><th>原 k/n（来源 v）</th><th>新 k/n</th></tr></thead><tbody>
        {preview.diff.map((d,i)=><tr key={i}><td>{d.lot_code}{d.is_new&&<em className="warning"> 新增</em>}</td><td>{d.previous_k??'—'}/{d.previous_n??'—'} <small>{d.previous_source_batch||'无'} v{d.previous_source_version}</small></td><td className="supported">{d.k}/{d.n}</td></tr>)}
      </tbody></table></div>}
      {preview.accepted&&preview.diff.length===0&&<p className="empty">内容与当前已发布计数完全一致，无差异；发布会按重放处理，不重复写入。</p>}
    </div>}
    {ledger.length>0&&<div className="batch-ledger">
      <div className="section-heading"><h3>批次台账</h3><span>已发布来源批号与版本</span></div>
      <div className="table-wrap compact-table"><table><thead><tr><th>时间</th><th>来源批号</th><th>版本</th><th>批次数</th><th>操作者</th><th>状态</th></tr></thead><tbody>
        {ledger.map(b=><tr key={b.id}><td>{time(b.published_at||b.created_at)}</td><td>{b.source_batch}</td><td>v{b.version}</td><td>{b.accepted_lots}/{b.total_lots}</td><td>{b.actor}</td><td className={b.status==='published'?'supported':'warning'}>{b.status}</td></tr>)}
      </tbody></table></div>
    </div>}
  </section>;
}
