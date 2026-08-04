# Preparing a server to run myst-libre securely

myst-libre executes code from submitted repositories. A build clones an untrusted
repository, starts a Jupyter server from a BinderHub-built image, and runs the
notebooks in it. Every step below exists because of that: the defaults in the
library are safe, but several of the boundaries have to be enforced by the host.

This is a runbook for an OpenStack instance. Work through it in order; the
verification steps at the end are the part that actually tells you it worked.

---

## 1. Prerequisites

```bash
docker --version          # Docker Engine, iptables-nft or iptables-legacy
node --version            # required by mystmd
myst --version            # mystmd CLI
python3 -m pip install -e .   # or your deployment's install method

docker pull busybox:latest    # image used by the spawn-time metadata probe
```

Docker must be managing iptables (the default). If Docker was started with
`--iptables=false`, none of the firewall rules below take effect.

> Docker is only compatible with `iptables-nft` and `iptables-legacy`. Rules
> created directly with `nft` are not supported on a system running Docker.

---

## 2. Create the build network

Build containers get their own Docker network so firewall rules can target them
by interface without affecting your registry, the myst-libre container, or
anything else on the host.

```bash
docker network create --driver bridge \
  --opt com.docker.network.bridge.name=br-mystbuild \
  mystbuild
```

The `com.docker.network.bridge.name` option is not cosmetic. Without it Docker
generates a name like `br-1a2b3c4d5e6f`, and the rules below have nothing stable
to match on.

myst-libre does **not** create this network. A network it created automatically
would come up as a plain bridge with no rules attached — the build would succeed,
look identical, and have unrestricted egress. If the network is missing, the
spawner raises `ConfigurationError` before cloning anything.

---

## 3. Block the instance metadata service

On OpenStack, instances reach metadata at `169.254.169.254` (and `fe80::a9fe:a9fe`
if IPv6 is enabled). It serves user-data, vendordata, and the EC2-compatible API.
A notebook that can reach it can read whatever was injected into your instance.

Docker has no per-container egress ACL, so this is a host rule. Use `DOCKER-USER`,
which Docker processes *before* its own `DOCKER-FORWARD` and `DOCKER` chains:

```bash
iptables -I DOCKER-USER -i br-mystbuild -d 169.254.0.0/16 -j REJECT
```

If IPv6 is enabled on the instance:

```bash
ip6tables -I DOCKER-USER -i br-mystbuild -d fe80::a9fe:a9fe -j REJECT
```

Notes:

- `-i br-mystbuild` matches traffic *arriving from* build containers. The host's
  own access to metadata (cloud-init, etc.) is unaffected.
- The whole `169.254.0.0/16` is blocked rather than the single address. Nothing
  in link-local is legitimately needed by a build.
- This is a host-side rule, so code running as root *inside* the container cannot
  lift it. Blocking from inside the container would be bypassable.

### Optional: internal networks

Add rules for whatever internal ranges you run, for example:

```bash
iptables -I DOCKER-USER -i br-mystbuild -d 10.0.0.0/8 -j REJECT
```

> **Do not blanket-block `172.16.0.0/12`** without checking. In Docker-in-Docker
> mode myst-libre reaches the spawned Jupyter container by container IP, so
> blocking inter-container traffic breaks the build.

### Persist the rules

`DOCKER-USER` rules do not survive a reboot on their own:

```bash
apt-get install -y iptables-persistent    # Debian/Ubuntu
netfilter-persistent save
```

**This is the most likely way this setup silently degrades.** The Docker network
*does* survive a reboot — Docker recreates it from its own state, bridge name and
all — but the firewall rules do not. So after a reboot without persisted rules the
network exists, the build starts normally and looks identical, and build
containers have unrestricted access to the metadata service.

myst-libre now checks for exactly this. When `container_network` is set, the
spawner runs a throwaway container on that network before each build session and
tries to reach the metadata service; if it answers, the spawn is refused with the
rule to reinstall. The check is cached per network per process, so it costs one
probe container rather than one per build.

This means a lapsed rule fails loudly instead of quietly. Persist the rules
anyway — a refused build is better than an exposed one, but neither is what you
want on a Monday morning.

Separately, `docker network prune` (and `docker system prune`) removes networks
with no containers attached, so a cleanup cron can delete `mystbuild` between
builds. That failure is at least loud: the preflight refuses to spawn.

---

## 4. Restrict access to the Jupyter port range

**This one is not yet handled in code.** `_spawn_container` publishes the
container port with `ports={f'{port}/tcp': port}`, which binds `0.0.0.0`, and the
entrypoint passes `--ip 0.0.0.0`. The Jupyter server is an arbitrary-code-execution
endpoint guarded only by its token, so it must not be reachable from outside the
host. Ports are allocated from `DEFAULT_PORT_RANGE`, currently `8888-10000`.

Until the binding is changed to `127.0.0.1`, close the range at the host and at
your OpenStack security group:

```bash
# Host: allow only loopback to the Jupyter port range
iptables -A INPUT -p tcp --dport 8888:10000 ! -i lo -j REJECT
```

In the OpenStack security group for this instance, ensure there is **no** ingress
rule covering `8888-10000`. Verify from another machine:

```bash
nc -z -w3 <instance-ip> 8888 ; echo "exit=$?"     # non-zero = closed
```

---

## 5. Set up data staging

Data is never downloaded automatically. A repository's
`binder/data_requirement.json` can point anywhere, so myst-libre uses only what
is already staged, and warns and builds without the mount when it is absent.

```bash
mkdir -p /srv/myst_data
chown <build-user>:<build-user> /srv/myst_data
```

Pass it as `host_data_parent_dir`. The per-dataset workflow is:

1. A submission declares `projectName` in `binder/data_requirement.json`.
2. You review the source and the destination.
3. You stage the data yourself at `/srv/myst_data/<projectName>`, or run one
   build with `allow_repo2data_download=True` after approving it.
4. Subsequent builds pick it up automatically.

Dataset names are validated: absolute paths, `..` components, and names that
resolve outside `host_data_parent_dir` (via a symlink, for instance) are refused
and no volume is mounted. Data is mounted read-only.

---

## 6. Registry credentials

Credentials are read from a `.env` file at the `dotenv` path given to `REES`:

```
DOCKER_PRIVATE_REGISTRY_USERNAME=...
DOCKER_PRIVATE_REGISTRY_PASSWORD=...
CURVENOTE_TOKEN=...
```

```bash
chmod 600 /path/to/config/.env
chown <build-user>:<build-user> /path/to/config/.env
```

These stay on the host. The spawned container's environment receives only
`JUPYTER_TOKEN`, `port`, and `JUPYTER_BASE_URL` — no registry or Curvenote
credentials are passed into the execution container.

---

## 7. Build logs

The Jupyter token is redacted from everything log-bound: myst-libre's own debug
output, `get_container_logs()`, and the container log dump on cleanup. This
matters because the Jupyter server prints its own token in its startup URL, and
the entrypoint runs it at `--log-level=DEBUG`.

If you add new code paths that surface container output, route them through
`JupyterHubLocalSpawner._redact()`.

---

## 8. Verify

Run all of these. Each corresponds to a step above that fails silently if wrong.

The metadata check (step 3) is also enforced automatically at spawn time — see
section 3. Run it manually here so you find out now rather than when the next
build refuses to start.

```bash
# The bridge exists and is named as expected
ip -o link show br-mystbuild

# Metadata is NOT locally addressed (if it is, DOCKER-USER won't see the traffic)
ip addr | grep 169.254 || echo "OK: metadata not a local address"

# Metadata is unreachable from the build network
docker run --rm --network mystbuild curlimages/curl \
  -s -m 3 http://169.254.169.254/openstack/ ; echo "exit=$?"
# want: exit=7 (rejected) or exit=28 (timeout).  exit=0 = NOT blocked

# General egress still works (builds need this)
docker run --rm --network mystbuild curlimages/curl \
  -s -o /dev/null -w '%{http_code}\n' -m 10 https://pypi.org/simple/

# The rules are actually loaded
iptables -S DOCKER-USER

# The Jupyter port range is closed from outside (run from another machine)
nc -z -w3 <instance-ip> 8888 ; echo "exit=$?"
```

---

## 9. Wiring it up

```python
hub = JupyterHubLocalSpawner(
    rees,
    host_build_source_parent_dir='/srv/myst_repos',
    container_build_source_mount_dir='/home/jovyan',
    host_data_parent_dir='/srv/myst_data',
    container_data_mount_dir='/home/jovyan/data',
    container_network='mystbuild',      # section 2
    # verify_metadata_blocked defaults to True whenever container_network is set
    # metadata_probe_image defaults to 'busybox:latest'
    # allow_repo2data_download defaults to False - leave it off
    cpu_limit='max',
    memory_limit='max',
)
```

---

## What this does and does not cover

Covered: no unreviewed data downloads; dataset paths cannot escape their
directory; the metadata service is unreachable from build containers; registry
credentials stay off the execution container; the Jupyter token stays out of logs.

Not covered:

- **General network egress.** Build containers can still reach the public
  internet and anything else routable that you have not explicitly blocked.
  Notebooks legitimately fetch packages, so this is a policy decision rather than
  something to close by default.
- **Container escape.** Containers run as your build user with the repository
  directory mounted read-write. A kernel-level escape is out of scope here;
  isolate the build host from anything you care about.
- **Resource exhaustion**, if you do not set `cpu_limit` / `memory_limit`. There
  is no `pids_limit` support in myst-libre at present.
- **The 0.0.0.0 port binding** (section 4) is mitigated by host firewall rules,
  not fixed in code.

## References

- [Docker with iptables](https://docs.docker.com/engine/network/firewall-iptables/) — `DOCKER-USER` placement and precedence
- [Nova metadata](https://docs.openstack.org/nova/latest/user/metadata.html) — metadata addresses and what they expose
