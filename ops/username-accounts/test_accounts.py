import asyncio
from datetime import datetime,timezone,timedelta
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI,HTTPException,Response
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.db.users import User,UserRead,UserCreate,AnonymousUser,APITokenUser
from src.security import account_identity as identity
from src.core.email_verification_policy import requires_email_verification
from src.routers import account_access as access
from src.routers.orgs import user_import


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv('LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED','true')
    monkeypatch.setenv('LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED','true')
    monkeypatch.setenv('LEARNHOUSE_REQUIRE_EMAIL_VERIFICATION','true')


def test_models_preserve_public_email_requirement():
    user=User(id=9,username='learner',first_name='医生',last_name='',email='',user_uuid='user_00000000-0000-0000-0000-000000000009')
    assert UserRead.model_validate(user).email==''
    with pytest.raises(ValidationError):UserCreate(username='x',first_name='x',last_name='',email='',password='Password7!')
    assert identity.subject_for_user(user)==user.user_uuid
    user.email='valid@example.com'
    assert identity.subject_for_user(user)=='valid@example.com'


def test_only_admin_created_unbound_accounts_are_exempt():
    user=SimpleNamespace(email='',signup_method='admin_import',extra_metadata={'admin_import':{'actor_id':1}},creation_date=datetime.now(timezone.utc).isoformat())
    assert not requires_email_verification('oss',user=user)
    assert requires_email_verification('saas',user=user)
    user.signup_method='email'
    assert requires_email_verification('oss',user=user)
    assert requires_email_verification('oss')


def test_token_subject_cannot_be_a_username():
    credential=identity.identity_query('doctor',allow_username=True)
    subject=identity.identity_query('doctor')
    assert 'username =' in str(credential)
    assert 'email' in str(subject) and 'username =' not in str(subject)
    assert '"user".id =' in str(identity.identity_query(''))
    uuid=identity.identity_query('user_00000000-0000-0000-0000-000000000009')
    assert 'user_uuid =' in str(uuid)


def test_old_mfa_challenge_fails_after_password_reset():
    user=SimpleNamespace(password_changed_at=datetime(2026,1,1))
    stamp=user.password_changed_at.replace(tzinfo=timezone.utc).timestamp()
    assert not identity.credentials_match_epoch(user,{'iat':stamp-1})
    assert not identity.credentials_match_epoch(user,{})
    assert identity.credentials_match_epoch(user,{'iat':stamp})


def test_blank_email_requires_username_and_is_not_duplicate():
    assert not user_import.normalize(user_import.ImportRow(name='A',username='doctor_a'))['errors']
    assert user_import.normalize(user_import.ImportRow(name='A'))['errors']
    assert user_import.normalize(user_import.ImportRow(name='A',username='doctor_a',email='bad'))['errors']


def test_mail_binding_checks_code_and_consumes_once(monkeypatch):
    user=SimpleNamespace(id=9,username='doctor',first_name='医生',email='',password_changed_at=datetime(2026,1,1),email_verified=False)
    class Redis:
        values={}
        def setex(self,key,ttl,value):self.values[key]=value
        def get(self,key):return self.values.get(key)
        def delete(self,key):return self.values.pop(key,None)
        def eval(self,script,n,key,raw):
            if self.values.get(key)==raw:self.values.pop(key);return 1
            return 0
    redis=Redis();sent=[]
    monkeypatch.setattr(access,'redis_required',lambda:redis)
    monkeypatch.setattr(access,'human',AsyncMock(return_value=user))
    monkeypatch.setattr(access,'reauthenticate',AsyncMock())
    monkeypatch.setattr(access,'limit',AsyncMock())
    monkeypatch.setattr(access,'send_email',lambda **kw:sent.append(kw))
    monkeypatch.setattr(access,'finish_credential_change',AsyncMock())
    class Result:
        def __init__(self,value):self.value=value
        def scalars(self):return self
        def first(self):return self.value
    db=SimpleNamespace(execute=AsyncMock(return_value=Result(None)))
    asyncio.run(access.request_mail(access.MailRequest(email='doctor@example.com',current_password='Private8!'),None,Response(),None,db))
    assert sent[0]['to']=='doctor@example.com'
    assert user.email==''
    code=re.search(r'letter-spacing:6px">(\d{6})',sent[0]['body']).group(1)
    assert code not in redis.values['account_email_pending:9']
    db.execute=AsyncMock(side_effect=[Result(user)])
    wrong='000000' if code!='000000' else '999999'
    with pytest.raises(HTTPException):asyncio.run(access.confirm_mail(access.MailConfirm(code=wrong),None,Response(),None,db))
    assert user.email==''
    db.execute=AsyncMock(side_effect=[Result(user),Result(None)])
    asyncio.run(access.confirm_mail(access.MailConfirm(code=code),None,Response(),None,db))
    assert user.email=='doctor@example.com' and user.email_verified
    db.execute=AsyncMock(return_value=Result(user))
    with pytest.raises(HTTPException):asyncio.run(access.confirm_mail(access.MailConfirm(code=code),None,Response(),None,db))


def test_same_second_sessions_revoked_before_response(monkeypatch):
    user=SimpleNamespace(id=9)
    db=SimpleNamespace(add=lambda obj:None,commit=AsyncMock(),rollback=AsyncMock())
    cutoffs=[]
    monkeypatch.setattr(access,'revoke_user_sessions_before',lambda uid,cutoff:cutoffs.append(cutoff) or True)
    monkeypatch.setattr(access,'redis_required',lambda:SimpleNamespace(delete=lambda key:None))
    before=datetime.now(timezone.utc).replace(microsecond=0)
    asyncio.run(access.finish_credential_change(user,db))
    assert cutoffs[0]>before
    assert datetime.now(timezone.utc)>=cutoffs[0]
    assert not identity.credentials_match_epoch(user,{'iat':before.timestamp()})


def test_sensitive_validation_never_echoes_password():
    app=FastAPI();app.include_router(access.router)
    app.dependency_overrides[access.get_current_user]=lambda:AnonymousUser()
    async def no_db():yield None
    app.dependency_overrides[access.get_db_session]=no_db
    with TestClient(app) as client:
        response=client.post('/self/password',json={'current_password':'DO-NOT-ECHO','new_password':{'bad':'shape'}})
    assert response.status_code==422 and 'DO-NOT-ECHO' not in response.text


def test_anonymous_and_api_tokens_denied():
    request=SimpleNamespace(headers={})
    for actor,expected in [(AnonymousUser(),401),(APITokenUser(org_id=1),403)]:
        with pytest.raises(HTTPException) as exc:asyncio.run(access.human(request,actor,None,Response()))
        assert exc.value.status_code==expected
