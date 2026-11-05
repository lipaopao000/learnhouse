"""Wrong-password bookkeeping must update an attached row, not insert a copy."""
from unittest.mock import patch
import pytest
from fastapi import HTTPException,Response
from starlette.requests import Request
from src.routers import auth
from src.db.users import User
from sqlmodel import select
from src.security.security import security_hash_password


@pytest.mark.asyncio
async def test_username_wrong_password_preserves_account_and_records_failure(db,regular_user,monkeypatch):
    monkeypatch.setenv('LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED','true')
    regular_user=(await db.execute(select(User).where(User.id==regular_user.id))).scalars().first()
    regular_user.email=''
    regular_user.password=security_hash_password('ActualPassword7!')
    regular_user.signup_method='admin_import'
    regular_user.extra_metadata={'admin_import':{'actor_id':1}}
    db.add(regular_user);await db.commit()
    original_id=regular_user.id
    request=Request({'type':'http','headers':[],'client':('127.0.0.1',1234),'server':('localhost',80),'scheme':'http','path':'/api/v1/auth/login','method':'POST'})
    with patch.object(auth,'check_login_rate_limit',return_value=(True,0)):
        with pytest.raises(HTTPException) as exc:
            await auth.login(request,Response(),username=regular_user.username,password='DefinitelyWrong7!',org_slug=None,db_session=db)
    assert exc.value.status_code==401
    await db.refresh(regular_user)
    assert regular_user.id==original_id and regular_user.email==''
    assert regular_user.failed_login_attempts==1
