from functools import lru_cache


@lru_cache(maxsize=1)
def get_system_user():
    from django.contrib.auth.models import User
    return User.objects.get(username="system")
