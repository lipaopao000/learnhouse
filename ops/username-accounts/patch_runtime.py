"""Guarded narrow edits shared by checkout source and the pinned v3 runtime."""
from pathlib import Path


def once(text,old,new):
    assert text.count(old)==1, 'Source seam changed: '+old[:90]
    return text.replace(old,new,1)


def patch(relative,text):
    if relative=='src/db/users.py':
        text='from typing import Literal\n'+text
        start=text.index('class UserUpdate(UserBase):');end=text.index('class UserUpdatePassword',start)
        section=once(text[start:end],'email: EmailStr\n',"email: EmailStr | Literal['']\n")
        text=text[:start]+section+text[end:]
        text=once(text,'class User(UserBase, table=True):','class User(UserBase, table=True):\n    # Public UserCreate still requires EmailStr. Unbound admin accounts store an empty string.\n    email: str = ""')
    elif relative=='src/services/users/users.py':
        text='from src.security.account_identity import identity_query\n'+text
        text=once(text,'async def security_get_user(request: Request, db_session: AsyncSession, email: str) -> User | None:',
            'async def security_get_user(request: Request, db_session: AsyncSession, email: str, *, allow_username=False) -> User | None:')
        start=text.index('async def security_get_user(')
        text=text[:start]+once(text[start:],'statement = select(User).where(User.email == email)','statement = identity_query(email, allow_username=allow_username)')
        start=text.index('async def update_user(');end=text.index('async def _check_org_admin_can_edit_account',start)
        section=text[start:end]
        section=once(section,'    identity_changed = email_changed or user_object.username != user.username',
            '    if email_changed and not user_object.email:\n        raise HTTPException(400, "A bound email cannot be cleared through profile editing")\n    identity_changed = email_changed or user_object.username != user.username')
        section=once(section,'| (func.lower(User.email) == str(user_object.email).lower())',
            '| ((func.lower(User.email) == str(user_object.email).lower()) if user_object.email else False)')
        text=text[:start]+section+text[end:]
    elif relative=='src/security/auth.py':
        text=once(text,'user = await security_get_user(request, db_session, email)\n',
            'user = await security_get_user(request, db_session, email, allow_username=True)\n')
    elif relative=='src/routers/auth.py':
        text='from src.security.account_identity import identity_query\n'+text
        text=once(text,'        user_record = (await db_session.execute(\n            select(User).where(User.email == username)\n        )).scalars().first()',
            '        user_record = (await db_session.execute(\n            identity_query(username, allow_username=True)\n        )).scalars().first()')
    elif relative=='src/services/auth/session.py':
        text+='\n'
        # Import after the docstring/future imports, at an existing import seam.
        text=once(text,'import secrets\n','import secrets\nfrom src.security.account_identity import subject_for_user\n')
        text=once(text,'create_mfa_pending_token(user.email, amr, org_id, custom_domain)',
            'create_mfa_pending_token(subject_for_user(user), amr, org_id, custom_domain)')
        text=once(text,'return mint_session_tokens(user.email, amr, org_id, custom_domain)',
            'return mint_session_tokens(subject_for_user(user), amr, org_id, custom_domain)')
    elif relative=='src/routers/mfa.py':
        text='from src.security.account_identity import identity_query, subject_for_user, credentials_match_epoch\nfrom src.security.auth import decode_jwt\n'+text
        text=once(text,'select(User).where(User.email == email)','identity_query(email)')
        assert text.count('user.email, pending_amr')==2
        text=text.replace('user.email, pending_amr','subject_for_user(user), pending_amr')
        text=once(text,'data = {"sub": user.email,','data = {"sub": subject_for_user(user),')
        text=once(text,'build_provisioning_uri(secret, user.email)','build_provisioning_uri(secret, user.email or user.username)')
        login_start=text.index('async def api_login_mfa(')
        text=text[:login_start]+once(text[login_start:],'    mfa = await get_user_mfa(db_session, user.id)\n    if mfa is None or mfa.confirmed_at is None:',
            '    if not credentials_match_epoch(user, decode_jwt(form.mfa_token) or {}):\n        raise HTTPException(401, "Password changed; please sign in again")\n    mfa = await get_user_mfa(db_session, user.id)\n    if mfa is None or mfa.confirmed_at is None:')
    elif relative=='src/services/email/utils.py':
        text=once(text,'    from src.services.email.safe_text import header_safe\n',
            '    from src.services.email.safe_text import header_safe\n\n    if not to:\n        return False  # Administrator-created accounts may have no mailbox.\n')
    elif relative=='src/core/email_verification_policy.py':
        text=once(text,'import os\n','import os\nfrom src.security.account_identity import trusted_unbound\n')
        text=once(text,'    if deployment_mode == "saas":\n        return True\n',
            '    if deployment_mode == "saas":\n        return True\n    if trusted_unbound(user):\n        return False\n')
    elif relative=='src/router.py':
        assert 'account_access_router' not in text
        text+='\nfrom src.routers.account_access import router as account_access_router\nv1_router.include_router(account_access_router, prefix="/account-access", tags=["account-access"])\n'
    else:
        raise ValueError(relative)
    return text


FILES=['src/db/users.py','src/services/users/users.py','src/security/auth.py','src/routers/auth.py',
    'src/services/auth/session.py','src/routers/mfa.py','src/services/email/utils.py',
    'src/core/email_verification_policy.py','src/router.py']

if __name__=='__main__':
    import sys
    root=Path(sys.argv[1])
    for relative in FILES:
        target=root/relative;target.write_text(patch(relative,target.read_text()))
