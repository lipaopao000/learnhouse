"""Self-service verified mail binding and audited administrator password resets."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import logging
import secrets
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, EmailStr, Field, SecretStr
from sqlmodel import select
from sqlalchemy import or_, func
from starlette.concurrency import run_in_threadpool

from src.core.events.database import get_db_session
from src.core.redis import get_redis_client
from src.db.users import User, AnonymousUser, APITokenUser, SuperadminAPITokenUser
from src.db.user_organizations import UserOrganization
from src.security.account_identity import enabled
from src.security.auth import get_current_user, revoke_user_sessions_before
from src.security.org_auth import is_user_superadmin
from src.security.security import security_hash_password, security_verify_password
from src.security.session_context import get_session_provenance
from src.routers.orgs.user_import import guard as admin_guard
from src.services.users.users import _check_org_admin_can_edit_account
from src.services.security.password_validation import validate_password_complexity
from src.services.email.utils import send_email

logger=logging.getLogger(__name__)


class SafeRoute(APIRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def safe(request):
            try:return await handler(request)
            except RequestValidationError:raise HTTPException(422,'请求参数不正确，请检查后重试')
        return safe


router=APIRouter(route_class=SafeRoute)


class MailRequest(BaseModel):
    email: EmailStr
    current_password: SecretStr


class MailConfirm(BaseModel):
    code: str = Field(pattern=r'^\d{6}$')


class PasswordChange(BaseModel):
    current_password: SecretStr
    new_password: SecretStr


class AdminReset(BaseModel):
    admin_password: SecretStr
    new_password: SecretStr
    operation_id: UUID
    confirmed: bool = False


def origin_guard(request):
    origin=request.headers.get('origin','')
    if not origin or urlsplit(origin).netloc.lower()!=request.headers.get('host','').lower():
        raise HTTPException(403,'请从本平台网页提交')


async def human(request,actor,db,response,writing=False):
    if not enabled():raise HTTPException(404,'Not found')
    if isinstance(actor,AnonymousUser):raise HTTPException(401,'请先登录')
    if isinstance(actor,(APITokenUser,SuperadminAPITokenUser)):raise HTTPException(403,'请使用本人账号登录')
    provenance=get_session_provenance()
    if provenance is not None and provenance.amr=='lti':
        raise HTTPException(403,'请直接登录本平台后管理账号')
    if writing:origin_guard(request)
    response.headers['Cache-Control']='no-store'
    user=(await db.execute(select(User).where(User.id==actor.id))).scalars().first()
    if not user:raise HTTPException(401,'请重新登录')
    return user


def redis_required():
    redis=get_redis_client()
    if redis is None:raise HTTPException(503,'账号服务暂不可用，请稍后重试')
    return redis


async def limit(key,maximum,seconds):
    redis=redis_required()
    count=await run_in_threadpool(lambda:redis.eval(
        "local n=redis.call('incr',KEYS[1]); if n==1 then redis.call('expire',KEYS[1],ARGV[1]) end; return n",1,'account_access:'+key,seconds))
    if count>maximum:raise HTTPException(429,'操作过于频繁，请稍后重试')


async def reauthenticate(user,password):
    await limit('reauth:'+str(user.id),30,600)
    def verify():
        try:return bool(user.password) and security_verify_password(password.get_secret_value(),user.password)
        except Exception:return False
    if not await run_in_threadpool(verify):raise HTTPException(401,'当前密码不正确')


def validate_new_password(password):
    value=password.get_secret_value()
    if len(value)>128 or not validate_password_complexity(value).is_valid:
        raise HTTPException(400,'密码至少 8 位，须包含大小写字母、数字和特殊字符')
    return value


async def finish_credential_change(user,db):
    # Cut at the next whole second, then wait before replying: even an old JWT
    # minted in this same second is rejected, and immediate new logins work.
    cutoff=(datetime.now(timezone.utc)+timedelta(seconds=1)).replace(microsecond=0)
    user.password_changed_at=cutoff.replace(tzinfo=None)
    user.update_date=str(datetime.now(timezone.utc))
    if not await run_in_threadpool(revoke_user_sessions_before,user.id,cutoff):
        await db.rollback();raise HTTPException(503,'暂无法结束旧登录会话，请稍后重试')
    db.add(user);await db.commit()
    try:await run_in_threadpool(lambda:redis_required().delete('session:'+str(user.id)))
    except Exception:logger.warning('Account session cache clear failed user=%s',user.id)
    await asyncio.sleep(max(0,cutoff.timestamp()-datetime.now(timezone.utc).timestamp())+0.02)


@router.get('/self')
async def self_info(request:Request,response:Response,actor=Depends(get_current_user),db=Depends(get_db_session)):
    user=await human(request,actor,db,response)
    return {'username':user.username,'name':user.first_name+' '+user.last_name,'email':user.email,
        'email_verified':user.email_verified,'has_password':bool(user.password)}


@router.post('/self/password')
async def change_password(body:PasswordChange,request:Request,response:Response,actor=Depends(get_current_user),db=Depends(get_db_session)):
    user=await human(request,actor,db,response,True)
    user=(await db.execute(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))).scalars().first()
    await reauthenticate(user,body.current_password)
    value=validate_new_password(body.new_password)
    user.password=await run_in_threadpool(security_hash_password,value)
    await finish_credential_change(user,db)
    return {'changed':True,'reauthenticate':True}


@router.post('/self/email/request')
async def request_mail(body:MailRequest,request:Request,response:Response,actor=Depends(get_current_user),db=Depends(get_db_session)):
    user=await human(request,actor,db,response,True)
    await reauthenticate(user,body.current_password)
    target=str(body.email).lower()
    if target==user.email.lower() and user.email_verified:raise HTTPException(409,'此邮箱已经绑定并验证')
    await limit('mail-minute:'+str(user.id),1,60)
    await limit('mail-hour:'+str(user.id),5,3600)
    exists=(await db.execute(select(User.id).where(func.lower(User.email)==target,User.id!=user.id))).scalars().first()
    if exists:raise HTTPException(409,'无法绑定此邮箱，请换用本人其他邮箱')
    code=f'{secrets.randbelow(1000000):06d}';salt=secrets.token_hex(16)
    payload={'email':target,'salt':salt,'digest':hashlib.sha256((salt+code).encode()).hexdigest(),
        'credential_epoch':str(user.password_changed_at)}
    redis=redis_required();key='account_email_pending:'+str(user.id)
    await run_in_threadpool(lambda:redis.setex(key,600,json.dumps(payload)))
    message=f'<div style="font-family:sans-serif;line-height:1.8"><h2>绑定 ICU 教学平台邮箱</h2><p>{html.escape(user.first_name or user.username)}，您好。</p><p>请在账号设置页面输入验证码：</p><p style="font-size:28px;letter-spacing:6px">{code}</p><p>10 分钟内有效。若非本人操作，请忽略本邮件。</p></div>'
    try:await run_in_threadpool(send_email,to=target,subject='ICU教学平台：绑定邮箱验证码',body=message)
    except Exception:
        await run_in_threadpool(lambda:redis.delete(key))
        raise HTTPException(503,'验证邮件暂未发出，请稍后重试')
    return {'sent':True,'expires_in':600}


@router.post('/self/email/confirm')
async def confirm_mail(body:MailConfirm,request:Request,response:Response,actor=Depends(get_current_user),db=Depends(get_db_session)):
    user=await human(request,actor,db,response,True)
    await limit('mail-code:'+str(user.id),10,600)
    user=(await db.execute(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))).scalars().first()
    redis=redis_required();key='account_email_pending:'+str(user.id)
    raw=await run_in_threadpool(lambda:redis.get(key))
    if not raw:raise HTTPException(400,'验证码已失效，请重新发送')
    payload=json.loads(raw)
    if payload.get('credential_epoch')!=str(user.password_changed_at):raise HTTPException(400,'密码已变更，请重新发送验证码')
    digest=hashlib.sha256((payload['salt']+body.code).encode()).hexdigest()
    if not secrets.compare_digest(digest,payload['digest']):raise HTTPException(400,'验证码不正确')
    existing=(await db.execute(select(User.id).where(func.lower(User.email)==payload['email'],User.id!=user.id))).scalars().first()
    if existing:raise HTTPException(409,'无法绑定此邮箱，请重新选择')
    consumed=await run_in_threadpool(lambda:redis.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",1,key,raw))
    if not consumed:raise HTTPException(400,'验证码已使用或已更新')
    previous=user.email
    user.email=payload['email'];user.email_verified=True;user.email_verified_at=datetime.now(timezone.utc).isoformat()
    try:await finish_credential_change(user,db)
    except HTTPException:raise
    except Exception:
        await db.rollback();raise HTTPException(409,'邮箱绑定未完成，请重新发送验证码')
    if previous and previous!=user.email:
        from src.services.users.emails import send_email_changed_notice
        try:await run_in_threadpool(send_email_changed_notice,email=previous,new_email=user.email,username=user.username)
        except Exception:logger.warning('Email change notice failed user=%s',user.id)
    return {'bound':True,'reauthenticate':True}


@router.get('/orgs/{org_id}/search')
async def search_users(org_id:int,q:str,request:Request,response:Response,actor=Depends(get_current_user),db=Depends(get_db_session)):
    await human(request,actor,db,response)
    await admin_guard(request,org_id,actor,db)
    q=q.strip()
    if not 1<=len(q)<=150:raise HTTPException(400,'请输入姓名、用户名或邮箱')
    # Literal substring matching, with LIKE metacharacters escaped.
    escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    pattern='%'+escaped+'%'
    users=(await db.execute(select(User).join(UserOrganization,UserOrganization.user_id==User.id).where(
        UserOrganization.org_id==org_id,or_(User.username.ilike(pattern,escape='\\'),User.email.ilike(pattern,escape='\\'),User.first_name.ilike(pattern,escape='\\'))).limit(30))).scalars().all()
    return {'users':[{'id':u.id,'username':u.username,'name':u.first_name+' '+u.last_name,'email':u.email} for u in users]}


@router.post('/orgs/{org_id}/users/{user_id}/reset-password')
async def reset_password(org_id:int,user_id:int,body:AdminReset,request:Request,response:Response,actor=Depends(get_current_user),db=Depends(get_db_session)):
    administrator=await human(request,actor,db,response,True)
    await admin_guard(request,org_id,actor,db,writing=True)
    if not body.confirmed:raise HTTPException(400,'请先确认用户身份和重置操作')
    if actor.id==user_id:raise HTTPException(400,'自己的密码请在账号设置中修改')
    await reauthenticate(administrator,body.admin_password)
    target=(await db.execute(select(User).join(UserOrganization,UserOrganization.user_id==User.id).where(
        User.id==user_id,UserOrganization.org_id==org_id).with_for_update(of=User))).scalars().first()
    if not target:raise HTTPException(404,'当前组织中找不到该账号')
    if not await is_user_superadmin(actor.id,db):await _check_org_admin_can_edit_account(target,db)
    prior=(target.extra_metadata or {}).get('admin_password_reset',{})
    if prior.get('operation_id')==str(body.operation_id) and prior.get('actor_id')==actor.id:
        return {'reset':True,'recovered':True,'username':target.username}
    value=validate_new_password(body.new_password)
    target.password=await run_in_threadpool(security_hash_password,value)
    target.failed_login_attempts=0;target.locked_until=None
    target.extra_metadata={**(target.extra_metadata or {}),'admin_password_reset':{
        'operation_id':str(body.operation_id),'actor_id':actor.id,'time':datetime.now(timezone.utc).isoformat()}}
    await finish_credential_change(target,db)
    logger.info('Admin reset org=%s actor=%s target=%s',org_id,actor.id,user_id)
    return {'reset':True,'username':target.username,'sessions_revoked':True}
