"""Opt-in self-hosted, human-admin user provisioning. Never sends email.

The browser generates and retains initial passwords. Only password hashes are
stored; retries are identified by an import id and never reset existing users.
"""
from datetime import datetime, timezone
import hashlib
import logging
import os
import re
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, EmailStr, Field, SecretStr, TypeAdapter, ValidationError
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.core.events.database import get_db_session
from src.core.redis import get_redis_client
from src.db.roles import Role
from src.db.usergroup_user import UserGroupUser
from src.db.usergroups import UserGroup
from src.db.user_organizations import UserOrganization
from src.db.users import AnonymousUser, APITokenUser, SuperadminAPITokenUser, User
from src.security.auth import get_current_user
from src.security.org_auth import is_org_admin, require_org_role_permission
from src.security.security import security_hash_password
from src.security.features_utils.usage import (
    _role_grants_dashboard_access, check_admin_seat_limit,
    check_limits_with_usage, increase_feature_usage,
)
from src.services.security.password_validation import validate_password_complexity
from src.services.security.profile_validation import validate_profile_fields

class ImportRoute(APIRoute):
    """Validation errors must not echo an input body containing passwords."""
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def sanitized(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, '导入数据格式不正确，请重新检查表格；每批最多 25 人')

        return sanitized


router = APIRouter(route_class=ImportRoute)
logger = logging.getLogger(__name__)
EMAIL = TypeAdapter(EmailStr)
ROLE_IDS = {'学员': 4, 'student': 4, 'user': 4, '4': 4, '讲师': 3, 'teacher': 3, 'instructor': 3, '3': 3}


class ImportRow(BaseModel):
    name: str = Field(default='', max_length=150)
    email: str = Field(default='', max_length=320)
    username: str = Field(default='', max_length=150)
    role: str = Field(default='学员', max_length=40)
    groups: list[str] = Field(default_factory=list, max_length=10)
    password: SecretStr | None = None


class PreviewBody(BaseModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=500)


class ExecuteBody(BaseModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=25)
    import_id: UUID
    confirmed: bool = False


def normalize(row: ImportRow):
    errors = []
    try:
        email = str(EMAIL.validate_python(row.email.strip())).lower()
    except ValidationError:
        email = row.email.strip().lower()
        errors.append('邮箱格式不正确')
    name = row.name.strip()
    username = row.username.strip() or 'icu_' + hashlib.sha256(email.encode()).hexdigest()[:12]
    role = ROLE_IDS.get(row.role.strip().lower())
    if not name:
        errors.append('姓名不能为空')
    if role is None:
        errors.append('角色仅支持学员或讲师；管理员请在用户列表中单独授权')
    if not re.fullmatch(r'[\w.-]{1,150}', username):
        errors.append('用户名仅支持字母、数字、中文、点、下划线和连字符')
    validation = validate_profile_fields({'username': username, 'first_name': name, 'last_name': ''})
    if not validation.is_valid:
        errors.append('姓名或用户名包含不允许的链接或字符')
    groups = list(dict.fromkeys(g.strip() for g in row.groups if g.strip()))
    if any(len(g) > 100 for g in groups):
        errors.append('分组名称过长')
    return {'name': name, 'email': email, 'username': username, 'role_id': role,
        'role': '讲师' if role == 3 else '学员', 'groups': groups, 'errors': errors}


async def guard(request, org_id, actor, db, *, writing=False):
    if os.getenv('LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED', '').lower() != 'true':
        raise HTTPException(404, 'Not found')
    if isinstance(actor, AnonymousUser):
        raise HTTPException(401, '请先登录')
    if isinstance(actor, (APITokenUser, SuperadminAPITokenUser)):
        raise HTTPException(403, '此功能仅供管理员本人登录使用')
    await require_org_role_permission(actor.id, org_id, db, 'users', 'action_create')
    if not await is_org_admin(actor.id, org_id, db):
        raise HTTPException(403, '仅管理员或维护者可导入账号')
    if writing:
        from urllib.parse import urlsplit
        origin = request.headers.get('origin', '')
        if not origin or urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower():
            raise HTTPException(403, '请从本平台网页提交')


async def prepare(rows, org_id, db, import_id=None, actor_id=None):
    group_rows = list((await db.execute(select(UserGroup).where(UserGroup.org_id == org_id))).scalars().all())
    groups_by_name = {}
    for group in group_rows:
        groups_by_name.setdefault(group.name, []).append(group.id)
    result, seen_emails, seen_names = [], set(), set()
    for index, row in enumerate(rows, 1):
        item = normalize(row)
        item['row'] = index
        item['status'] = 'ready'
        item['group_ids'] = []
        if item['email'] in seen_emails:
            item['errors'].append('表格内邮箱重复')
        if item['username'] in seen_names:
            item['errors'].append('表格内用户名重复')
        seen_emails.add(item['email'])
        seen_names.add(item['username'])
        for name in item['groups']:
            choices = groups_by_name.get(name, [])
            if len(choices) != 1:
                item['errors'].append('分组不存在或重名：' + name)
            else:
                item['group_ids'].append(choices[0])
        existing = (await db.execute(select(User).where(func.lower(User.email) == item['email']))).scalars().first()
        if existing:
            member = (await db.execute(select(UserOrganization).where(
                UserOrganization.org_id == org_id, UserOrganization.user_id == existing.id))).scalars().first()
            if member:
                metadata = (existing.extra_metadata or {}).get('admin_import', {})
                same = import_id and metadata.get('import_id') == str(import_id) and metadata.get('actor_id') == actor_id
                item['status'] = 'recovered' if same else 'existing'
                item['user_id'] = existing.id
                item['username'] = existing.username
            else:
                item['errors'].append('邮箱已有其他账号，请使用邀请加入，不能覆盖账号')
        elif (await db.execute(select(User.id).where(User.username == item['username']))).scalars().first():
            item['errors'].append('用户名已被使用')
        if item['errors']:
            item['status'] = 'error'
        result.append(item)
    return result


def public_rows(rows):
    return [{k:v for k,v in row.items() if k not in ('group_ids', 'role_id')} for row in rows]


@router.get('/{org_id}/users/import/meta')
async def metadata(org_id: int, response: Response, request: Request,
    actor=Depends(get_current_user), db: AsyncSession=Depends(get_db_session)):
    await guard(request, org_id, actor, db)
    response.headers['Cache-Control'] = 'no-store'
    groups = (await db.execute(select(UserGroup.name).where(UserGroup.org_id == org_id))).scalars().all()
    return {'roles': ['学员', '讲师'], 'groups': sorted(groups), 'max_preview_rows': 500,
        'batch_size': 25, 'login_uses_email': True, 'sends_email': False, 'force_password_change': False}


@router.post('/{org_id}/users/import/preview')
async def preview(org_id: int, body: PreviewBody, response: Response, request: Request,
    actor=Depends(get_current_user), db: AsyncSession=Depends(get_db_session)):
    await guard(request, org_id, actor, db, writing=True)
    response.headers['Cache-Control'] = 'no-store'
    rows = await prepare(body.rows, org_id, db)
    return {'rows': public_rows(rows), 'ready': sum(r['status']=='ready' for r in rows),
        'existing': sum(r['status']=='existing' for r in rows), 'errors': sum(r['status']=='error' for r in rows)}


@router.post('/{org_id}/users/import/create')
async def create(org_id: int, body: ExecuteBody, response: Response, request: Request,
    actor=Depends(get_current_user), db: AsyncSession=Depends(get_db_session)):
    await guard(request, org_id, actor, db, writing=True)
    if not body.confirmed:
        raise HTTPException(400, '请先确认人员邮箱和角色')
    response.headers['Cache-Control'] = 'no-store'
    redis = get_redis_client()
    if redis is None:
        raise HTTPException(503, '导入服务暂不可用，请稍后重试')
    lock_key, lock_value = 'learnhouse:admin_user_import_lock', str(uuid4())
    acquired = await run_in_threadpool(lambda: redis.set(lock_key, lock_value, nx=True, ex=180))
    if not acquired:
        raise HTTPException(409, '另一批导入正在进行，请稍后重试')
    try:
        rows = await prepare(body.rows, org_id, db, body.import_id, actor.id)
        for source, row in zip(body.rows, rows):
            if row['status'] != 'ready':
                continue
            password = source.password.get_secret_value() if source.password else ''
            if len(password) > 128 or not validate_password_complexity(password).is_valid:
                row['status'], row['errors'] = 'error', ['初始密码不符合复杂度要求']
                continue
            try:
                if row['groups']:
                    await require_org_role_permission(actor.id, org_id, db, 'usergroups', 'action_update')
                role = (await db.execute(select(Role).where(Role.id == row['role_id']))).scalars().first()
                if not role or (role.org_id is not None and role.org_id != org_id):
                    raise HTTPException(400, '角色不属于当前组织')
                await check_limits_with_usage('members', org_id, db)
                if _role_grants_dashboard_access(role):
                    await check_admin_seat_limit(org_id, db)
                now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
                password_hash = await run_in_threadpool(security_hash_password, password)
                user = User(username=row['username'], first_name=row['name'], last_name='', email=row['email'],
                    password=password_hash, user_uuid='user_'+str(uuid4()), email_verified=True,
                    email_verified_at=now.isoformat(), signup_method='admin_import', is_superadmin=False,
                    password_changed_at=now, creation_date=str(now), update_date=str(now),
                    extra_metadata={'admin_import': {'actor_id': actor.id, 'import_id': str(body.import_id), 'created_at': now.isoformat()}})
                db.add(user)
                await db.flush()
                created_id = user.id
                db.add(UserOrganization(user_id=user.id, org_id=org_id, role_id=role.id, creation_date=str(now), update_date=str(now)))
                for group_id in row['group_ids']:
                    db.add(UserGroupUser(user_id=user.id, usergroup_id=group_id, org_id=org_id, creation_date=str(now), update_date=str(now)))
                await db.commit()
                row.update(status='created', user_id=created_id)
                try:
                    await increase_feature_usage('members', org_id, db)
                except Exception:
                    await db.rollback()
                    logger.warning('Member usage update failed after admin import org=%s user=%s', org_id, created_id)
                logger.info('Admin import org=%s actor=%s user=%s', org_id, actor.id, created_id)
            except HTTPException as exc:
                await db.rollback()
                row['status'], row['errors'] = 'error', [str(exc.detail)]
            except Exception:
                await db.rollback()
                logger.warning('Admin import row failed org=%s actor=%s', org_id, actor.id)
                row['status'], row['errors'] = 'error', ['创建失败；请重新预览后重试，已存在账号不会覆盖']
        return {'rows': public_rows(rows)}
    finally:
        try:
            await run_in_threadpool(lambda: redis.eval(
                "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end", 1, lock_key, lock_value))
        except Exception:
            logger.warning('Admin import lock release failed; lock expires automatically')
