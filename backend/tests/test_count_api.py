import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import get_db
from src.models import CountBatch
from src.utils.security import make_token

@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db]=lambda:db
    yield TestClient(app)
    app.dependency_overrides.clear()

def auth(user):return {'Authorization':'Bearer '+make_token(user)}

def test_endpoints_require_authentication(client,seeded):
    sid=seeded['study'].id
    assert client.get(f'/studies/{sid}/count-batches').status_code==401
    payload={'study_id':sid,'source_batch':'B','version':1,'rows':[]}
    assert client.post(f'/studies/{sid}/count-batches',json=payload).status_code==401

def test_viewer_cannot_import_but_can_read(client,seeded):
    sid=seeded['study'].id;viewer=seeded['users']['viewer'];analyst=seeded['users']['analyst']
    body={'study_id':sid,'source_batch':'B-202611','version':2,
          'rows':[{'lot_code':f'DC-T1-L{i:02}','n':100,'k':60+i-1} for i in range(1,11)]}
    r=client.post(f'/studies/{sid}/count-batches',json=body,headers=auth(viewer))
    assert r.status_code==403
    r=client.get(f'/studies/{sid}/count-batches',headers=auth(viewer))
    assert r.status_code==200 and r.json()==[]
    r=client.post(f'/studies/{sid}/count-batches',json=body,headers=auth(analyst))
    assert r.status_code==200 and r.json()['outcome']=='preview_ok'

def test_full_api_flow_publish_replay_conflict_reject(client,seeded,db):
    sid=seeded['study'].id;analyst=seeded['users']['analyst'];h=auth(analyst)
    base={'study_id':sid,'source_batch':'B-202611','version':2,
          'rows':[{'lot_code':f'DC-T1-L{i:02}','n':100,'k':60+i-1} for i in range(1,11)]}
    # 预检
    r=client.post(f'/studies/{sid}/count-batches',json=base,headers=h);assert r.status_code==200
    preview=r.json();assert preview['accepted'] is True and preview['id'] is None and len(preview['diff'])==10
    # 正式发布
    body={**base,'commit':True}
    r=client.post(f'/studies/{sid}/count-batches',json=body,headers=h);assert r.status_code==200
    published=r.json();assert published['outcome']=='published' and published['id']
    # 同版同内容重放
    r=client.post(f'/studies/{sid}/count-batches',json=body,headers=h);assert r.status_code==200
    replay=r.json();assert replay['outcome']=='replay' and replay['id']==published['id']
    # 同版异内容冲突
    bad={**base,'commit':True,'rows':[{**x,'k':99} for x in base['rows']]}
    r=client.post(f'/studies/{sid}/count-batches',json=bad,headers=h);assert r.status_code==409
    assert r.json()['detail']['conflicts'][0]['reason']=='same_version_conflict'
    # 旧版迟到
    stale={**base,'commit':True,'version':1}
    r=client.post(f'/studies/{sid}/count-batches',json=stale,headers=h);assert r.status_code==409
    assert r.json()['detail']['conflicts'][0]['reason']=='stale_version'
    # 坏行整批拒绝（200，accepted=false，原因逐行）
    broken={**base,'commit':True,'rows':[{**x} for x in base['rows']]};broken['rows'][0]['n']=0
    r=client.post(f'/studies/{sid}/count-batches',json=broken,headers=h);assert r.status_code==200
    rejected=r.json();assert rejected['accepted'] is False and rejected['rejected_rows'][0]['lot_code']=='DC-T1-L01'
    assert db.query(CountBatch).count()==1
    # 批次台账可查
    r=client.get(f'/studies/{sid}/count-batches',headers=h);assert r.status_code==200
    ledger=r.json();assert len(ledger)==1 and ledger[0]['source_batch']=='B-202611' and ledger[0]['accepted_lots']==10
    # 计数输出带来源批号与版本
    r=client.get(f'/studies/{sid}/counts',headers=h);assert r.status_code==200
    first=r.json()[0]
    assert first['source_batch']=='B-202611' and first['source_version']==2 and first['content_hash']==published['content_hash']

def test_path_study_mismatch_rejected(client,seeded):
    sid=seeded['study'].id;h=auth(seeded['users']['analyst'])
    body={'study_id':sid+999,'source_batch':'B','version':1,'rows':[]}
    r=client.post(f'/studies/{sid}/count-batches',json=body,headers=h)
    assert r.status_code==422

def test_validation_shape_constraints(client,seeded):
    sid=seeded['study'].id;h=auth(seeded['users']['analyst'])
    body={'study_id':sid,'source_batch':'','version':0,'rows':[]}
    r=client.post(f'/studies/{sid}/count-batches',json=body,headers=h)
    assert r.status_code==422
