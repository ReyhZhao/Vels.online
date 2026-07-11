"""Token authentication for service accounts (#696).

Extends DRF's ``TokenAuthentication`` with the two service-account concerns that must
happen at the moment a token is accepted: enforcing the account's optional source-IP
allowlist, and stamping its last-used time/IP for auditing.

Tokens are only ever issued to service accounts in this system; human/SSO users
authenticate via ``SessionAuthentication`` and never reach this path. A token whose
user is not a service account (which shouldn't occur) authenticates unchanged.
"""

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .client_ip import get_client_ip


class ServiceAccountTokenAuthentication(TokenAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result

        from .models import ServiceAccount

        account = ServiceAccount.objects.filter(user=user).first()
        if account is not None:
            ip = get_client_ip(request)
            if not account.is_ip_allowed(ip):
                # Rejected attempts leave the audit fields untouched — record_use runs
                # only past this gate.
                raise AuthenticationFailed(
                    "Source IP is not permitted for this service account."
                )
            account.record_use(ip)
        return user, token
