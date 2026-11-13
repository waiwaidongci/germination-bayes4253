import pytest
from fastapi import HTTPException
from src.schemas.count import CountBatchInput
from src.services.count_service import preview_or_import,_content_hash
from src.models import LotCount,CountBatch,SeedLot,GerminationStudy,BayesRun,SamplingNote,Audit
from src.services.study_service import create_snapshot
from src.services.analysis_service import analyze_germination
from tests.helpers import batch_payload

def make(data):return CountBatchInput(**data)

def test_preview_is_readonly_and_reports_diff(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    payload=make(batch_payload(study))
    out=preview_or_import(db,payload,user)
    assert out['commit'] is False and out['accepted'] is True and out['outcome']=='preview_ok'
    assert out['id'] is None
    assert db.query(CountBatch).count()==0
    assert {d['lot_code'] for d in out['diff']}=={f'DC-T1-L{i:02}' for i in range(1,11)}
    first=out['diff'][0]
    assert first['previous_n']==100 and first['previous_k']==50 and first['n']==100 and first['k']==60
    assert first['previous_source_batch']=='seed-batch' and first['previous_source_version']==1
    assert all(d['is_new'] is False for d in out['diff'])

def test_bad_row_rejects_whole_batch_without_any_write(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    nk=[(100,60+i) for i in range(10)];nk[3]=(0,0);nk[7]=(50,60)  # n越界、k>n
    payload=make(batch_payload(study,nk=nk,commit=True))
    out=preview_or_import(db,payload,user)
    assert out['accepted'] is False and out['outcome']=='rejected_precheck'
    assert {r['lot_code'] for r in out['rejected_rows']}=={'DC-T1-L04','DC-T1-L08'}
    assert db.query(CountBatch).count()==0
    untouched=db.query(LotCount).join(SeedLot,LotCount.lot_id==SeedLot.id).filter(SeedLot.code=='DC-T1-L04').one()
    assert (untouched.n,untouched.k)==(100,53) and untouched.source_batch=='seed-batch'
    assert db.query(Audit).filter(Audit.action=='count.batch.reject_precheck').count()==1

def test_missing_lot_makes_batch_incomplete_and_rejected(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    rows=[{'lot_code':f'DC-T1-L{i:02}','n':100,'k':60} for i in range(1,10)]  # 缺L10
    payload=make({'study_id':study.id,'source_batch':'B-x','version':1,'commit':True,'rows':rows})
    out=preview_or_import(db,payload,user)
    assert out['accepted'] is False
    assert any(r['lot_code']=='DC-T1-L10' and '齐备' in r['reason'] for r in out['rejected_rows'])
    assert db.query(CountBatch).count()==0

def test_foreign_lot_rejected_as_wrong_ownership(db,seeded):
    other=GerminationStudy(code='DC-OTHER',name='其他研究',description='d',source='x.csv');db.add(other);db.flush()
    db.add(SeedLot(study_id=other.id,code='DC-OTHER-L1',name='外批',origin='x'));db.commit()
    study=seeded['study'];user=seeded['users']['analyst']
    payload=make(batch_payload(study,batch='B-foreign'))
    payload.rows[0].lot_code='DC-OTHER-L1'
    out=preview_or_import(db,payload,user)
    assert out['accepted'] is False
    assert any('不属于当前研究' in r['reason'] for r in out['rejected_rows'])

def test_integer_range_and_duplicate_rows_rejected(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    payload=make(batch_payload(study,batch='B-range'))
    payload.rows[0].n=100001
    payload.rows[1].lot_code=payload.rows[2].lot_code
    out=preview_or_import(db,payload,user)
    reasons=' '.join(r['reason'] for r in out['rejected_rows'])
    assert '100000' in reasons and '重复' in reasons

def test_publish_updates_all_counts_with_source_attribution(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    payload=make(batch_payload(study,commit=True))
    out=preview_or_import(db,payload,user)
    assert out['accepted'] is True and out['outcome']=='published' and out['id'] is not None
    batch=db.query(CountBatch).one()
    assert batch.status=='published' and batch.version==2 and batch.total_lots==10 and batch.accepted_lots==10
    assert batch.content_hash==out['content_hash'] and batch.actor==user.email
    counts=db.query(LotCount).join(SeedLot,LotCount.lot_id==SeedLot.id).order_by(SeedLot.code).all()
    assert all(c.source_batch=='B-202611' and c.source_version==2 and c.content_hash==batch.content_hash for c in counts)
    assert [c.k for c in counts]==list(range(60,70)) and [c.n for c in counts]==[100]*10
    # 批注保留，不随导入清空
    assert counts[0].note=='初始计数'
    assert db.query(Audit).filter(Audit.action=='count.batch.publish').count()==1

def test_same_version_same_content_replay_does_not_duplicate(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    first=preview_or_import(db,make(batch_payload(study,commit=True)),user)
    second=preview_or_import(db,make(batch_payload(study,commit=True)),user)
    assert second['outcome']=='replay' and second['accepted'] is True
    assert second['id']==first['id'] and second['content_hash']==first['content_hash']
    assert db.query(CountBatch).count()==1
    assert db.query(LotCount).count()==10
    assert db.query(Audit).filter(Audit.action=='count.batch.publish').count()==1
    assert db.query(Audit).filter(Audit.action=='count.batch.replay').count()==1

def test_same_version_different_content_conflicts_and_keeps_original(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    preview_or_import(db,make(batch_payload(study,commit=True)),user)
    nk=[(100,60+i) for i in range(10)];nk[0]=(100,99)
    conflict=make(batch_payload(study,nk=nk,commit=True))
    with pytest.raises(HTTPException) as exc:preview_or_import(db,conflict,user)
    assert exc.value.status_code==409
    assert exc.value.detail['conflicts'][0]['reason']=='same_version_conflict'
    assert db.query(CountBatch).count()==1
    first_count=db.query(LotCount).join(SeedLot,LotCount.lot_id==SeedLot.id).filter(SeedLot.code=='DC-T1-L01').one()
    assert first_count.k==60  # 原值未被覆盖

def test_stale_late_version_never_rolls_back(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    preview_or_import(db,make(batch_payload(study,version=3,commit=True)),user)
    stale=make(batch_payload(study,version=2,nk=[(100,1) for _ in range(10)],commit=True))
    with pytest.raises(HTTPException) as exc:preview_or_import(db,stale,user)
    assert exc.value.status_code==409 and exc.value.detail['conflicts'][0]['reason']=='stale_version'
    assert db.query(CountBatch).count()==1
    counts=db.query(LotCount).all()
    assert all(c.source_version==3 and c.k!=1 for c in counts)

def test_newer_version_publishes_and_old_one_then_rejected(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    preview_or_import(db,make(batch_payload(study,version=1,nk=[(100,10+i) for i in range(10)],commit=True)),user)
    out2=preview_or_import(db,make(batch_payload(study,version=2,nk=[(100,20+i) for i in range(10)],commit=True)),user)
    assert out2['outcome']=='published'
    assert db.query(CountBatch).count()==2
    assert all(c.source_version==2 for c in db.query(LotCount).all())
    with pytest.raises(HTTPException):preview_or_import(db,make(batch_payload(study,version=1,nk=[(100,99) for _ in range(10)],commit=True)),user)
    # 不同来源批号互不阻塞
    out_other=preview_or_import(db,make(batch_payload(study,batch='B-other',version=1,nk=[(100,30+i) for i in range(10)],commit=True)),user)
    assert out_other['outcome']=='published'

def test_content_hash_is_deterministic_and_order_independent(db,seeded):
    study=seeded['study']
    p1=make(batch_payload(study,version=5));p2=make(batch_payload(study,version=5))
    p2.rows=list(reversed(p2.rows))
    assert _content_hash(p1)==_content_hash(p2)
    p3=make(batch_payload(study,version=5));p3.rows[0].k=99
    assert _content_hash(p1)!=_content_hash(p3)

def test_unique_constraint_blocks_concurrent_same_version_insert(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    preview_or_import(db,make(batch_payload(study,commit=True)),user)
    # 模拟并发：绕过服务直接插入同(study,source,version)的冲突批次
    dup=CountBatch(study_id=study.id,source_batch='B-202611',version=2,content_hash='other',
                   content=[],status='published',total_lots=1,accepted_lots=1,rejected_rows=[],
                   actor=user.email,published_at='t',created_at='t')
    db.add(dup)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):db.commit()
    db.rollback()
