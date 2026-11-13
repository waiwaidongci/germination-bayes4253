from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from ..models import SeedLot,LotCount,CountBatch
from ..schemas.count import N_MIN,N_MAX
from ..utils.serialize import record
from ..utils.fingerprint import fingerprint
from ..utils.clock import now
from .study_service import get_study
from .audit_service import log

def list_counts(db,sid):
    get_study(db,sid);rows=db.query(LotCount,SeedLot).join(SeedLot,LotCount.lot_id==SeedLot.id).filter(SeedLot.study_id==sid).order_by(SeedLot.code).all()
    return [{**record(c),'lot_code':l.code,'lot_name':l.name,'raw_rate':c.k/c.n if c.n>0 else None} for c,l in rows]

def annotate(db,cid,data,user):
    row=db.get(LotCount,cid)
    if not row:raise HTTPException(404,"批次计数不存在")
    row.note=data.note;log(db,user.email,'count.annotate',cid);db.commit();return record(row)

def list_batches(db,sid):
    get_study(db,sid)
    return [record(b) for b in db.query(CountBatch).filter_by(study_id=sid).order_by(CountBatch.id.desc()).all()]

def _canonical_rows(data):
    return [{'lot_code':r.lot_code,'n':r.n,'k':r.k} for r in sorted(data.rows,key=lambda r:r.lot_code)]

def _content_hash(data):
    return fingerprint({'kind':'lot-count-batch','study_id':data.study_id,'source_batch':data.source_batch,'version':data.version,'rows':_canonical_rows(data)})

def _precheck(db,study,data):
    """坏行逐行列明；任一坏行或批次不齐都会让整批拒绝。"""
    lots=db.query(SeedLot).filter_by(study_id=study.id).order_by(SeedLot.code).all()
    lot_by_code={l.code:l for l in lots};rejected=[];seen=set();covered=set()
    for idx,row in enumerate(data.rows,start=1):
        code=row.lot_code
        if isinstance(row.n,bool) or isinstance(row.k,bool) or not isinstance(row.n,int) or not isinstance(row.k,int):
            rejected.append({'row':idx,'lot_code':code,'reason':'n/k必须为整数，不接受布尔或小数'});continue
        if not N_MIN<=row.n<=N_MAX:
            rejected.append({'row':idx,'lot_code':code,'reason':f'n须为{N_MIN}–{N_MAX}之间的整数'});continue
        if not 0<=row.k<=row.n:
            rejected.append({'row':idx,'lot_code':code,'reason':'须满足0≤k≤n'});continue
        if code in seen:
            rejected.append({'row':idx,'lot_code':code,'reason':'来源批号内批次编号重复'});continue
        if code not in lot_by_code:
            rejected.append({'row':idx,'lot_code':code,'reason':'批次不属于当前研究，拒绝跨研究写入'});continue
        seen.add(code);covered.add(lot_by_code[code].id)
    for lot in lots:
        if lot.id not in covered:
            rejected.append({'row':0,'lot_code':lot.code,'reason':'该批次缺少计数行，整批未齐备'})
    return rejected

def _same_version_batch(db,study,data):
    return db.query(CountBatch).filter_by(study_id=study.id,source_batch=data.source_batch,version=data.version).first()

def _latest_published(db,study,source_batch):
    return db.query(CountBatch).filter_by(study_id=study.id,source_batch=source_batch,status='published').order_by(CountBatch.version.desc()).first()

def _current_counts(db,study):
    out={}
    for c,l in db.query(LotCount,SeedLot).join(SeedLot,LotCount.lot_id==SeedLot.id).filter(SeedLot.study_id==study.id).all():
        out[l.code]=c
    return out

def _build_diff(db,study,data):
    current=_current_counts(db,study);diff=[]
    for row in _canonical_rows(data):
        old=current.get(row['lot_code'])
        if old is None:
            diff.append({'lot_code':row['lot_code'],'n':row['n'],'k':row['k'],'previous_n':None,'previous_k':None,'previous_source_batch':'','previous_source_version':0,'is_new':True})
        elif old.n!=row['n'] or old.k!=row['k']:
            diff.append({'lot_code':row['lot_code'],'n':row['n'],'k':row['k'],'previous_n':old.n,'previous_k':old.k,'previous_source_batch':old.source_batch,'previous_source_version':old.source_version,'is_new':False})
    return diff

def _inspect(db,study,data,content_hash):
    rejected=_precheck(db,study,data)
    conflicts=[];same=_same_version_batch(db,study,data);latest=_latest_published(db,study,data.source_batch)
    if same and same.content_hash!=content_hash:
        conflicts.append({'reason':'same_version_conflict','message':f'来源批号{data.source_batch}版本{data.version}已发布且内容不同，同版异内容冲突','existing_batch_id':same.id,'existing_hash':same.content_hash,'incoming_hash':content_hash})
    if latest and latest.version>data.version and not (same and same.content_hash==content_hash):
        conflicts.append({'reason':'stale_version','message':f'已存在更新版本v{latest.version}，旧版v{data.version}迟到，不回退已发布计数','latest_batch_id':latest.id,'latest_version':latest.version})
    diff=[] if rejected else _build_diff(db,study,data)
    if same and same.content_hash==content_hash:
        outcome='replay'
    elif conflicts:
        outcome='conflict' if any(c['reason']=='same_version_conflict' for c in conflicts) else 'stale'
    elif rejected:
        outcome='preview_rejected' if not data.commit else 'rejected_precheck'
    else:
        outcome='preview_ok' if not data.commit else 'publishable'
    return {'rejected_rows':rejected,'conflicts':conflicts,'diff':diff,'same':same,'outcome':outcome,
            'accepted':not rejected and not conflicts,'accepted_lots':0 if rejected else len(data.rows)}

def _output(data,content_hash,inspection,batch=None):
    same=inspection['same']
    return {'id':batch.id if batch else (same.id if same and inspection['outcome']=='replay' else None),
            'study_id':data.study_id,'source_batch':data.source_batch,'version':data.version,'content_hash':content_hash,
            'commit':data.commit,'accepted':inspection['accepted'],'outcome':inspection['outcome'],
            'total_lots':len(data.rows),'accepted_lots':inspection['accepted_lots'],
            'rejected_rows':inspection['rejected_rows'],'conflicts':inspection['conflicts'],'diff':inspection['diff'],
            'published_at':batch.published_at if batch else (same.published_at if same else ''),
            'created_at':batch.created_at if batch else (same.created_at if same else now())}

def preview_or_import(db,data,user):
    study=get_study(db,data.study_id);content_hash=_content_hash(data);inspection=_inspect(db,study,data,content_hash)
    if not data.commit:
        return _output(data,content_hash,inspection)
    if inspection['rejected_rows']:
        log(db,user.email,'count.batch.reject_precheck',f"{study.code}/{data.source_batch}/v{data.version}");db.commit()
        return _output(data,content_hash,inspection)
    if inspection['conflicts']:
        db.rollback();conflict=inspection['conflicts'][0];raise HTTPException(409,detail={'message':conflict['message'],'conflicts':inspection['conflicts'],'rejected_rows':[]})
    if inspection['outcome']=='replay':
        log(db,user.email,'count.batch.replay',inspection['same'].id);db.commit()
        return _output(data,content_hash,inspection)
    batch,outcome=_publish(db,study,data,content_hash,user)
    inspection['outcome']=outcome;return _output(data,content_hash,inspection,batch)

def _publish(db,study,data,content_hash,user):
    # 行锁串行化同研究并发发布；唯一约束(study,source_batch,version)是最终防线
    db.query(SeedLot).filter_by(study_id=study.id).with_for_update().all()
    same=_same_version_batch(db,study,data)
    if same:
        if same.content_hash==content_hash:
            # 并发重放：同版同内容已由另一请求发布，沿用其批次，不重复写入
            log(db,user.email,'count.batch.replay',same.id);db.commit();return same,'replay'
        db.rollback();raise HTTPException(409,detail={'message':f'来源批号{data.source_batch}版本{data.version}并发发布且内容不同，冲突拒绝','conflicts':[{'reason':'same_version_conflict','existing_batch_id':same.id}],'rejected_rows':[]})
    latest=_latest_published(db,study,data.source_batch)
    if latest and latest.version>data.version:
        db.rollback();raise HTTPException(409,detail={'message':f'并发发布只保留较新版本：当前v{latest.version}，迟到v{data.version}不回退','conflicts':[{'reason':'stale_version','latest_batch_id':latest.id,'latest_version':latest.version}],'rejected_rows':[]})
    lot_by_code={l.code:l for l in db.query(SeedLot).filter_by(study_id=study.id).all()}
    for row in _canonical_rows(data):
        lot=lot_by_code[row['lot_code']];count=db.query(LotCount).filter_by(lot_id=lot.id).first();stamp=now()
        if count:
            count.n=row['n'];count.k=row['k'];count.source_batch=data.source_batch;count.source_version=data.version
            count.content_hash=content_hash;count.updated_at=stamp
        else:
            db.add(LotCount(lot_id=lot.id,n=row['n'],k=row['k'],note='',source_batch=data.source_batch,source_version=data.version,content_hash=content_hash,updated_at=stamp))
    batch=CountBatch(study_id=study.id,source_batch=data.source_batch,version=data.version,content_hash=content_hash,
                     content=_canonical_rows(data),status='published',total_lots=len(data.rows),accepted_lots=len(data.rows),
                     rejected_rows=[],actor=user.email,published_at=now(),created_at=now())
    db.add(batch);db.flush();log(db,user.email,'count.batch.publish',batch.id)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        raced=_same_version_batch(db,study,data)
        if raced and raced.content_hash==content_hash:
            log(db,user.email,'count.batch.replay',raced.id);db.commit();return raced,'replay'
        raise HTTPException(409,detail={'message':'同版批次已由并发请求发布，请刷新后按新版本重试','conflicts':[{'reason':'same_version_conflict'}],'rejected_rows':[]})
    return batch,'published'
