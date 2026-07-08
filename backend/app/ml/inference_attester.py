import hashlib
import json
from datetime import datetime, timezone


class InferenceAttester:
    """
    Produces a deterministic SHA-256 attestation hash binding a specific
    model version, its input features, and its output direction together —
    so a stored prediction can later be verified as unmodified.
    Not a zk-SNARK, not a blockchain proof — a plain, honestly-labeled hash.
    """

    def generate_inference_attestation(self, model_version: str, features: dict, direction: str, checkpoint_sha256: str = None, graph_digest: str = None) -> dict:
        payload = {
            "model_version": model_version,
            "checkpoint_sha256": checkpoint_sha256,
            "features": {k: round(float(v), 8) for k, v in features.items()},
            "graph_digest": graph_digest,
            "direction": direction,
        }
        canonical = json.dumps(payload, sort_keys=True)
        attestation_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        
        # Add timestamp outside the hash to preserve determinism
        payload["attested_at"] = datetime.now(timezone.utc).isoformat()
        return {"attestation_hash": attestation_hash, "attested_payload": payload}
