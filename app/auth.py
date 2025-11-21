# dependencies/auth.py 같은 데
from pydantic import BaseModel

class CurrentUser(BaseModel):
    id: int
    username: str

async def get_current_user() -> CurrentUser:
    # TODO: 나중에 진짜 JWT 로 바꾸기
    return CurrentUser(id=1, username="dev_user")
