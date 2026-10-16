"""Fresh local-only services; heavy JVMs have independent explicit start gates."""
import copy
from contract import TRINO, require


def plan(base_plan, local_image, spark_base):
    value = copy.deepcopy(base_plan(local_image))
    require(set(value["services"]) == {"postgres", "garage", "spark"}, "FROZEN_CLOUD8_THREE_ROLE_PLAN")
    value["services"]["spark"]["command"][-1] = "/opt/silver/bootstrap_trial9.py"
    common = {"platform": "linux/amd64", "read_only": True, "cap_drop": ["ALL"],
              "security_opt": ["no-new-privileges:true"], "restart": "no", "networks": {"trial": {}}}
    value["services"]["trino"] = {**common, "image": TRINO, "user": "1000:1000", "cpus": 1,
        "mem_limit": "4g", "pids_limit": 512, "entrypoint": [], "command": ["/usr/lib/trino/bin/run-trino"],
        "env_file": ["./trino.env"], "volumes": ["./trino-config:/etc/trino:ro"],
        "tmpfs": ["/tmp:size=256m,uid=1000,gid=1000", "/data/trino:size=256m,uid=1000,gid=1000"]}
    value["services"]["reader"] = {**common, "image": spark_base, "user": "185:185", "cpus": 0.1,
        "mem_limit": "128m", "pids_limit": 16, "entrypoint": [], "command": ["python3", "/reader/s3_readonly.py"],
        "volumes": ["./reader:/reader:ro", "./silver-secrets:/run/silver-secrets:ro", "./proof:/proof"],
        "tmpfs": ["/tmp:size=16m,uid=185,gid=185"], "environment": {"PYTHONDONTWRITEBYTECODE": "1"}}
    require(len(value["services"]) == 5 and value["networks"] == {"trial": {"internal": True}}
            and all("ports" not in item for item in value["services"].values()), "NO_HOST_PUBLISH_OR_EXTERNAL_NETWORK")
    return value
