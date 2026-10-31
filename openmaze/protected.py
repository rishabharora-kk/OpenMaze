"""The only service that holds the signing key and synthetic protected records."""

from .common import NONCE, RESOURCE, Response, error, validate
from .receipts import sign


class Protected:
    def __init__(self, policy, key):
        self.policy, self.key = policy, key
        self.operations = 0

    def __call__(self, request):
        failure = validate(request) or self.policy.check(request)
        if failure:
            return failure
        if not NONCE.fullmatch(request.get("x-openmaze-nonce")):
            return error(400, "nonce_required")
        match = RESOURCE.fullmatch(request.target)
        tenant, item = match.groups()
        records = [{"id": f"item-{i}", "tenant": tenant,
                    "description": f"Protected synthetic {tenant} record {i}"} for i in range(1, 4)]
        data = {"records": [r for r in records if item is None or r["id"] == item]}
        self.operations += 1
        return Response(200, sign(self.key, request, 200, data))
