from src.schemas.count import CountBatchInput
from src.services.count_service import preview_or_import
from src.services.study_service import create_snapshot
from src.services.analysis_service import analyze_germination
from src.models import BayesRun,SamplingNote,LotCount
from src.services.run_service import export_run
from tests.helpers import batch_payload

def make(data):return CountBatchInput(**data)

def _snapshot_counts(snapshot):
    return {l['code']:(c['n'],c['k']) for l,c in zip(snapshot['lots'],snapshot['counts'])}

def test_historical_run_keeps_snapshot_after_reimport(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    before=create_snapshot(db,study)
    result_before=analyze_germination(before,.7,50)
    run=BayesRun(name='基线',study_id=study.id,threshold=.7,future_n=50,input_snapshot=before,
                 status='completed',result=result_before,owner=user.name)
    db.add(run);db.flush()
    note=SamplingNote(run_id=run.id,title='t',interpretation='i',proposal='p',status='approved',
                      owner=user.name,reviewer='admin',review_note='ok');db.add(note);db.commit()
    frozen=_snapshot_counts(run.input_snapshot);frozen_hash=run.result['input_hash']

    # 全量导入更新版计数并发布
    nk=[(120,30+i) for i in range(10)]
    out=preview_or_import(db,make(batch_payload(study,version=2,nk=nk,commit=True)),user)
    assert out['outcome']=='published'

    # 历史研究沿用原快照，未被回写
    rerun=db.get(BayesRun,run.id)
    assert _snapshot_counts(rerun.input_snapshot)==frozen
    assert rerun.result['input_hash']==frozen_hash
    assert rerun.input_snapshot['counts'][0]['n']==100

    # 获批下载仍按原快照生成
    csv_summary=export_run(db,run.id,'summary');csv_pmf=export_run(db,run.id,'predictive')
    assert 'DC-T1-L01' in csv_summary and frozen_hash in csv_summary and frozen_hash in csv_pmf

    # 新研究读取完整已发布计数
    after=create_snapshot(db,study)
    assert _snapshot_counts(after)=={f'DC-T1-L{i:02}':(120,30+i-1) for i in range(1,11)}
    result_after=analyze_germination(after,.7,50)
    assert result_after['input_hash']!=frozen_hash
    new_run=BayesRun(name='新版',study_id=study.id,threshold=.7,future_n=50,input_snapshot=after,
                     status='completed',result=result_after,owner=user.name)
    db.add(new_run);db.commit()
    assert new_run.input_snapshot['counts'][0]['n']==120

def test_rejected_batch_leaves_snapshot_intact(db,seeded):
    study=seeded['study'];user=seeded['users']['analyst']
    before=create_snapshot(db,study)
    nk=[(100,50+i) for i in range(10)];nk[2]=(10,99)  # k>n
    out=preview_or_import(db,make(batch_payload(study,version=9,nk=nk,commit=True)),user)
    assert out['accepted'] is False
    after=create_snapshot(db,study)
    assert _snapshot_counts(after)==_snapshot_counts(before)
    assert all(c.source_version==1 for c in db.query(LotCount).all())
