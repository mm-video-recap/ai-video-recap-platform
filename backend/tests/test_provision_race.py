"""Auto-provision race: two concurrent first requests for a new user must
not 500 on duplicate key "users_pkey" (live incident 2026-10-16: the
dashboard fires /api/auth/me and /api/videos at once, and three 500s
appeared during cutover)."""
from sqlalchemy.exc import IntegrityError

from backend.api.deps import get_current_user
from backend.database import User


def test_get_current_user_provision_race():
    existing = User(id="race1", email="race1@dev.local",
                    display_name="race1", is_admin=False)

    class _Query:
        def __init__(self, sess):
            self.sess = sess

        def filter_by(self, **kw):
            return self

        def one_or_none(self):
            # First call: no user yet (triggers insert). After the
            # rollback: the concurrent request's row is visible.
            return existing if self.sess.rolled_back else None

    class _Session:
        rolled_back = False

        def query(self, model):
            return _Query(self)

        def add(self, obj):
            pass

        def commit(self):
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

        def rollback(self):
            self.rolled_back = True

        def refresh(self, obj):
            pass

    user = get_current_user(None, "Bearer dev-token-race1", _Session())
    assert user is existing
