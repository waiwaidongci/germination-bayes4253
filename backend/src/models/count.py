from sqlalchemy import Text,JSON,ForeignKey,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from ..config.database import Base
from ..utils.clock import now
class LotCount(Base):
    __tablename__="lot_counts"
    id:Mapped[int]=mapped_column(primary_key=True)
    lot_id:Mapped[int]=mapped_column(ForeignKey("seed_lots.id"),unique=True)
    n:Mapped[int]
    k:Mapped[int]
    note:Mapped[str]=mapped_column(Text)
    source_batch:Mapped[str]=mapped_column(Text,default="")
    source_version:Mapped[int]=mapped_column(default=0)
    content_hash:Mapped[str]=mapped_column(Text,default="")
    updated_at:Mapped[str]=mapped_column(Text,default=now)
