import threading
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError,SQLAlchemyError
from src.schemas.count import CountBatchInput
from src.services.count_service import preview_or_import
from src.models import LotCount,CountBatch,SeedLot
from src.config.database import SessionLocal
from tests.helpers import batch_payload

def make(data):return CountBatchInput(**data)

def _run_in_thread(fn):
    box={}
    def work():
        try:box['value']=fn()
        except Exception as e:box['error']=e
    t=threading.Thread(target=work);t.start();t.join(30);return box

def _call(study,user,**kw):
    session=SessionLocal()
    try:return preview_or_import(session,make(batch_payload(study,**kw)),user)
    finally:session.close()

# SQLite测试库为单连接内存库，跨线程只允许出现SQLAlchemy/锁类底层错误；
# 业务语义（重放幂等、冲突409、新版保留、旧版不回退）由独立会话的串行交错测试覆盖。
DB_ERRORS=(OperationalError,SQLAlchemyError)

def test_concurrent_same_version_same_content_publishes_once(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    boxes=[_run_in_thread(lambda:_call(study,user,commit=True)) for _ in range(2)]
    outcomes=[]
    for b in boxes:
        if 'error' in b:assert isinstance(b['error'],DB_ERRORS)
        else:outcomes.append(b['value']['outcome'])
    if len(outcomes)==2:assert sorted(outcomes)==['published','replay']
    assert db.query(CountBatch).count()==1
    assert all(c.source_version==2 for c in db.query(LotCount).all())

def test_concurrent_same_version_different_content_only_one_wins(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    nk_a=[(100,60+i) for i in range(10)];nk_b=[(100,70+i) for i in range(10)]
    boxes=[_run_in_thread(lambda:_call(study,user,nk=nk_a,commit=True)),
           _run_in_thread(lambda:_call(study,user,nk=nk_b,commit=True))]
    errors=[b['error'] for b in boxes if 'error' in b]
    values=[b['value'] for b in boxes if 'value' in b]
    assert errors or any(v['outcome']=='published' for v in values)
    for e in errors:
        if isinstance(e,HTTPException):assert e.status_code==409
        else:assert isinstance(e,DB_ERRORS)
    assert db.query(CountBatch).count()==1
    kept=db.query(LotCount).join(SeedLot,LotCount.lot_id==SeedLot.id).filter(SeedLot.code=='DC-T1-L01').one()
    assert kept.k in (60,70)

def test_interleaved_sessions_replay_and_conflict_after_race(db,seeded):
    """模拟并发交错：会话A先发布，会话B以独立会话重放/冲突，验证最终防线。"""
    study=seeded['study'];user=seeded['users']['analyst']
    session_a=SessionLocal();session_b=SessionLocal()
    try:
        first=preview_or_import(session_a,make(batch_payload(study,commit=True)),user)
        assert first['outcome']=='published'
        replay=preview_or_import(session_b,make(batch_payload(study,commit=True)),user)
        assert replay['outcome']=='replay' and replay['id']==first['id']
        nk=[(100,70+i) for i in range(10)]
        with pytest.raises(HTTPException) as exc:
            preview_or_import(session_b,make(batch_payload(study,nk=nk,commit=True)),user)
        assert exc.value.status_code==409 and exc.value.detail['conflicts'][0]['reason']=='same_version_conflict'
        assert db.query(CountBatch).count()==1
    finally:
        session_a.close();session_b.close()

def test_interleaved_versions_keep_newest_and_reject_stale(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    session_a=SessionLocal();session_b=SessionLocal()
    try:
        out3=preview_or_import(session_a,make(batch_payload(study,version=3,nk=[(100,20+i) for i in range(10)],commit=True)),user)
        assert out3['outcome']=='published'
        # 另一会话迟到的旧版：不回退
        with pytest.raises(HTTPException) as exc:
            preview_or_import(session_b,make(batch_payload(study,version=2,nk=[(100,10+i) for i in range(10)],commit=True)),user)
        assert exc.value.status_code==409 and exc.value.detail['conflicts'][0]['reason']=='stale_version'
        # 同版异内容同样拒绝
        with pytest.raises(HTTPException) as exc:
            preview_or_import(session_b,make(batch_payload(study,version=3,nk=[(100,1) for _ in range(10)],commit=True)),user)
        assert exc.value.status_code==409
        # 较新版仍可发布并覆盖计数
        out4=preview_or_import(session_b,make(batch_payload(study,version=4,nk=[(100,30+i) for i in range(10)],commit=True)),user)
        assert out4['outcome']=='published'
        assert db.query(CountBatch).count()==2
        assert all(c.source_version==4 for c in db.query(LotCount).all())
    finally:
        session_a.close();session_b.close()
