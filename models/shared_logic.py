import sqlite3
import math
from pydantic import BaseModel
from typing import List, Optional

# [DTO] 데이터 전송 규격
class MenuSummaryDTO(BaseModel):
    menu_id: str
    menu_name: str
    price: int
    photo_url: str
    core_pros: str
    core_cons: str

class CoreInfoDTO(BaseModel):
    info_id: int
    content: str
    info_type: str  # 'PROS' or 'CONS'
    level: int      # 1 or 2
    upvotes: int
    downvotes: int

# [공통 DB 기초]
class MenuWiseDBBase:
    def __init__(self, db_path="menu_wise.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row