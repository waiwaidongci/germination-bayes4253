import {useEffect,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {useResearchData} from '../hooks/useResearch';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {StudySelector} from '../components/StudySelector';
import {DataTable} from '../components/common/DataTable';
import {Notice} from '../components/common/Notice';
import {CountBatchImport} from '../components/CountBatchImport';
import {annotateCount} from '../api/counts';
import {percent} from '../utils/format';

export function Inputs(){
  const s=useResearchData(),{user}=useAuth(),a=useAction(),[params]=useSearchParams(),
    [id,setId]=useState(Number(params.get('study'))||0),[selected,setSelected]=useState(0),[note,setNote]=useState('');
  const study=s.studies.find(x=>x.id===id)||s.studies[0];
  const count=s.counts.find(x=>x.id===selected)||s.counts[0];
  const lot=s.lots.find(x=>x.id===count?.lot_id);
  useEffect(()=>{if(study)s.loadStudy(study.id)},[study?.id,s.loadStudy]);
  useEffect(()=>setNote(count?.note||''),[count?.id,count?.note]);
  return <div className="page">
    <div className="page-title"><div>
      <p className="eyebrow">COUNTS & BATCH IDENTITIES / 02</p>
      <h1>计数来源与口径<span>n为试种粒数，k为萌发粒数；每批一条完整计数，支持带来源批号与递增版本的整批导入。</span></h1>
    </div></div>
    <Notice message={s.error||a.error} onRetry={s.refresh}/>
    <StudySelector studies={s.studies} value={study?.id||0} onChange={setId}/>
    {study&&<div className={'source-note '+(!study.supported?'warning':'')}>
      <b>{study.reason}</b><p>{study.description}</p>
      <small>{study.source} · {study.lot_count}批 / {study.reading_count}计数</small>
    </div>}
    {study&&<CountBatchImport study={study}/>}
    <div className="source-grid">
      <section>
        <div className="section-heading"><h2>独立批次计数</h2><span>原始k/n，不等于总体已知概率</span></div>
        <DataTable head={['批次','萌发k','试种n','未萌发n−k','原始率','来源 / 版本']}>
          {s.counts.map(c=><tr key={c.id} className={c.id===count?.id?'selected':''} onClick={()=>setSelected(c.id)}>
            <td>{c.lot_code}</td><td>{c.k}</td><td>{c.n}</td><td>{c.n-c.k}</td><td>{percent(c.raw_rate)}</td>
            <td><small>{c.source_batch||'手工录入'} · v{c.source_version}</small></td>
          </tr>)}
        </DataTable>
      </section>
      <aside className="count-reading">
        <span className="eyebrow">SELECTED LOT</span><h2>{lot?.code}</h2>
        <p>{lot?.name}<br/>{lot?.origin}</p>
        <div className="count-pair"><b>{count?.k}<em> / {count?.n}</em></b><span>萌发 / 试种</span></div>
        <small className="source-line">来源批号：{count?.source_batch||'手工录入'} · 版本 v{count?.source_version} · 更新 {count?.updated_at?new Date(count.updated_at).toLocaleString('zh-CN',{hour12:false}):'—'}</small>
        <label>计数批注<textarea aria-label="计数批注" value={note} disabled={user?.role==='viewer'} onChange={e=>setNote(e.target.value)}/></label>
        {user?.role!=='viewer'&&<button className="outline" disabled={a.busy||!count||note.length<8} onClick={()=>a.execute(async()=>{await annotateCount(count.id,note);await s.loadStudy(study.id)})}>保存批注</button>}
        <small>数值仅经整批导入更新；批注不随导入清空。历史研究冻结快照后不回写，新研究读取完整已发布计数。</small>
      </aside>
    </div>
  </div>;
}
