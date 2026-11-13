from pydantic import BaseModel,Field
N_MIN,N_MAX=1,100000
class CountOutput(BaseModel):
    id:int
    lot_id:int
    lot_code:str
    lot_name:str
    n:int
    k:int
    raw_rate:float|None
    note:str
    source_batch:str
    source_version:int
    content_hash:str
    updated_at:str
class CountAnnotation(BaseModel):
    note:str=Field(min_length=8,max_length=1500)
class CountBatchRow(BaseModel):
    lot_code:str=Field(min_length=1,max_length=64)
    n:int
    k:int
class CountBatchInput(BaseModel):
    study_id:int
    source_batch:str=Field(min_length=1,max_length=120)
    version:int=Field(ge=1)
    commit:bool=False
    rows:list[CountBatchRow]=Field(min_length=1)
class RejectedRow(BaseModel):
    row:int
    lot_code:str
    reason:str
class CountBatchOutput(BaseModel):
    id:int|None=None
    study_id:int
    source_batch:str
    version:int
    content_hash:str
    commit:bool
    accepted:bool
    outcome:str
    total_lots:int
    accepted_lots:int
    rejected_rows:list[RejectedRow]
    conflicts:list[dict]
    diff:list[dict]
    published_at:str
    created_at:str
class CountBatchLedgerOutput(BaseModel):
    id:int
    study_id:int
    source_batch:str
    version:int
    content_hash:str
    content:list[dict]
    status:str
    total_lots:int
    accepted_lots:int
    rejected_rows:list[RejectedRow]
    conflict_with:int|None
    actor:str
    published_at:str
    created_at:str
