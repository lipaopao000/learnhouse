"""Run inside the API image with PYTHONPATH=/app/api, without production writes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from src.routers.orgs import user_import as module


def test_normalization_and_roles():
    row = module.normalize(module.ImportRow(name=' 李医生 ', email='Doctor@EXAMPLE.com', groups=['本院医师','本院医师']))
    assert row['email'] == 'doctor@example.com'
    assert row['name'] == '李医生'
    assert row['username'].startswith('icu_')
    assert row['groups'] == ['本院医师']
    assert row['errors'] == []
    assert module.normalize(module.ImportRow(name='A',email='x@example.com',role='管理员'))['errors']
    assert module.normalize(module.ImportRow(name='',email='invalid',username='https://bad.example'))['errors']


def test_human_admin_and_csrf_guards(monkeypatch):
    monkeypatch.setenv('LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED','true')
    monkeypatch.setattr(module,'require_org_role_permission',AsyncMock())
    monkeypatch.setattr(module,'is_org_admin',AsyncMock(return_value=True))
    actor=SimpleNamespace(id=1)
    good=SimpleNamespace(headers={'origin':'https://syyedu.toofun.fun','host':'syyedu.toofun.fun'})
    asyncio.run(module.guard(good,1,actor,None,writing=True))
    bad=SimpleNamespace(headers={'origin':'https://other.example','host':'syyedu.toofun.fun'})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(module.guard(bad,1,actor,None,writing=True))
    assert exc.value.status_code == 403
    monkeypatch.setattr(module,'is_org_admin',AsyncMock(return_value=False))
    with pytest.raises(HTTPException):
        asyncio.run(module.guard(good,1,actor,None))
    monkeypatch.setenv('LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED','false')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(module.guard(good,1,actor,None))
    assert exc.value.status_code == 404


def test_validation_never_echoes_password(monkeypatch):
    app=FastAPI();app.include_router(module.router)
    app.dependency_overrides[module.get_current_user]=lambda:SimpleNamespace(id=1)
    async def no_db(): yield None
    app.dependency_overrides[module.get_db_session]=no_db
    with TestClient(app) as client:
        result=client.post('/1/users/import/create',json={'rows':[], 'import_id':'invalid','password':'DO-NOT-ECHO-THIS'})
    assert result.status_code == 422
    assert 'DO-NOT-ECHO-THIS' not in result.text


def test_retry_and_existing_users(monkeypatch):
    class Result:
        def __init__(self,value):self.value=value
        def scalars(self):return self
        def all(self):return self.value
        def first(self):return self.value
    batch='b70659d5-26b1-46c3-a079-9dcb44f6dfef'
    user=SimpleNamespace(id=9, username='existing',extra_metadata={'admin_import':{'actor_id':1,'import_id':batch}})
    class DB:
        def __init__(self):self.items=iter([[],user,object()])
        async def execute(self,query):return Result(next(self.items))
    row=module.ImportRow(name='医生',email='doctor@example.com')
    recovered=asyncio.run(module.prepare([row],1,DB(),batch,1))[0]
    assert recovered['status']=='recovered' and recovered['user_id']==9
    skipped=asyncio.run(module.prepare([row],1,DB(),batch,2))[0]
    assert skipped['status']=='existing'
