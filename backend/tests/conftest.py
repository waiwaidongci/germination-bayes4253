import os
os.environ['DATABASE_URL']='sqlite+pysqlite:///:memory:'
os.environ['SEED_DEMO']='false'
os.environ['JWT_SECRET']='test-secret'
import pytest
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.config import database
from src.config.database import Base
from src import models
from src.models import User,GerminationStudy,SeedLot,LotCount
from src.utils.security import hash_password
from tests.helpers import batch_payload

engine=create_engine('sqlite+pysqlite:///:memory:',connect_args={'check_same_thread':False,'timeout':2},poolclass=StaticPool)
@event.listens_for(engine,'connect')
def _sqlite_pragma(dbapi_conn,record):
    dbapi_conn.execute('PRAGMA busy_timeout=2000')
TestSession=sessionmaker(bind=engine,expire_on_commit=False)
# 让应用代码里的 SessionLocal 指向同一测试库，支持并发线程测试
database.SessionLocal=TestSession
database.engine=engine

@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    session=TestSession()
    try:yield session
    finally:
        session.close();Base.metadata.drop_all(engine)

@pytest.fixture()
def seeded(db):
    users={r:User(email=f'{r}@duocen.demo',name=r,role=r,password_hash=hash_password('pw')) for r in ('admin','analyst','viewer')}
    db.add_all(users.values());db.flush()
    study=GerminationStudy(code='DC-T1',name='测试研究',description='d',source='test.csv');db.add(study);db.flush()
    lots=[SeedLot(study_id=study.id,code=f'DC-T1-L{i:02}',name=f'批次{i}',origin='试验室') for i in range(1,11)]
    db.add_all(lots);db.flush()
    for i,lot in enumerate(lots):
        db.add(LotCount(lot_id=lot.id,n=100,k=50+i,note='初始计数',source_batch='seed-batch',source_version=1,content_hash='seed-hash'))
    db.commit()
    return {'users':users,'study':study,'lots':lots}
