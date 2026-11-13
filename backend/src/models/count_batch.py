from sqlalchemy import Text,JSON,ForeignKey,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from ..config.database import Base
from ..utils.clock import now
class CountBatch(Base):
    __tablename__="count_batches"
    __table_args__=(UniqueConstraint("study_id","source_batch","version",name="uq_count_batch_study_source_version"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    study_id:Mapped[int]=mapped_column(ForeignKey("germination_studies.id"))
    source_batch:Mapped[str]=mapped_column(Text)
    version:Mapped[int]
    content_hash:Mapped[str]=mapped_column(Text)
    content:Mapped[list]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(Text)
    total_lots:Mapped[int]
    accepted_lots:Mapped[int]=mapped_column(default=0)
    rejected_rows:Mapped[list]=mapped_column(JSON,default=list)
    conflict_with:Mapped[int]=mapped_column(ForeignKey("count_batches.id"),nullable=True)
    actor:Mapped[str]=mapped_column(Text)
    published_at:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[str]=mapped_column(Text,default=now)
