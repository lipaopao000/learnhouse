"""Username credentials and stable token subjects for administrator-created accounts."""
import os
import re
from datetime import timezone
from sqlalchemy import func
from sqlmodel import select
from src.db.users import User


def enabled():
    return os.getenv('LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED','').lower() == 'true'


def trusted_unbound(user):
    return bool(enabled() and user is not None and not getattr(user,'email',None)
        and getattr(user,'signup_method',None) == 'admin_import'
        and (getattr(user,'extra_metadata',None) or {}).get('admin_import'))


def subject_for_user(user):
    return user.email or user.user_uuid


def credentials_match_epoch(user,payload):
    cutoff=getattr(user,'password_changed_at',None)
    if cutoff is None:return True
    issued=payload.get('iat')
    if not isinstance(issued,(int,float)):return False
    cutoff=cutoff.replace(tzinfo=timezone.utc) if cutoff.tzinfo is None else cutoff
    return issued>=cutoff.timestamp()


def identity_query(value, *, allow_username=False):
    value = (value or '').strip()
    if not value:
        return select(User).where(User.id == -1)
    if allow_username and enabled() and '@' not in value:
        return select(User).where(User.username == value)
    if not allow_username and re.fullmatch(r'user_[0-9a-fA-F-]{36}',value):
        return select(User).where(User.user_uuid == value)
    return select(User).where(func.lower(User.email) == value.lower())
