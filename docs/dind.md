# Docker-in-Docker (DinD) Support


```
┌─────────────────────────────────────────────────────┐
│ Host Machine                                        │
│                                                     │
│  Docker Daemon                                      │
│  │                                                  │
│  ├─ myst-libre Container                           │
│  │  ├─ Python & MyST CLI                           │
│  │  ├─ myst-libre package                          │
│  │  └─ /workspace (mounted from host)              │
│  │      └─ /builds, /DATA, /config                 │
│  │                                                  │
│  └─ Jupyter Container (sibling)                    │
│     ├─ Jupyter Server                              │
│     ├─ Notebook Execution Environment              │
│     └─ /home/jovyan (mounted from host)            │
│         └─ Build sources & data                    │
│                                                     │
│  Key: Containers are SIBLINGS (both managed        │
│        by host Docker daemon)                       │
└─────────────────────────────────────────────────────┘
```

## How It Works

### 1. Path Translation

When myst-libre runs in a container, paths have different meanings:

**Inside myst-libre container:**
```
/workspace/builds/user/repo/latest  ← Container path
```

**On the host machine:**
```
/home/user/workspace/builds/user/repo/latest  ← Host path
```

When the myst-libre container spawns a Jupyter container, the Docker daemon interprets volume mount paths relative to the HOST, not the myst-libre container. The `host_path_prefix` parameter automatically translates paths.

### 2. Docker Socket Access

The myst-libre container accesses the host Docker daemon via the socket:
```
/var/run/docker.sock  ← Host Docker socket
```

This is mounted into the myst-libre container, allowing it to spawn containers on the host.

## Managing Secrets: Two Approaches

**CRITICAL:** Never include `.env` files in Docker images. This exposes credentials and violates security best practices.

myst-libre supports two secure approaches for providing credentials:

### Approach 1: Environment Variables (Recommended for CI/CD)

Pass credentials directly as environment variables. This is ideal for:
- CI/CD pipelines (GitHub Actions, GitLab CI, etc.)
- Container orchestration (Kubernetes, Docker Swarm)
- Cloud deployments (AWS ECS, Azure Container Instances, etc.)
- Any automated system where you don't want files in the image

**Supported credentials:**
- `DOCKER_PRIVATE_REGISTRY_USERNAME` - Username for private Docker registries
- `DOCKER_PRIVATE_REGISTRY_PASSWORD` - Password for private Docker registries
- `CURVENOTE_TOKEN` - API token for Curvenote (optional)

**With docker run:**
```bash
docker run -it --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /home/user/workspace:/workspace \
  -e HOST_WORKSPACE_PATH=/home/user/workspace \
  -e DOCKER_PRIVATE_REGISTRY_USERNAME=your_username \
  -e DOCKER_PRIVATE_REGISTRY_PASSWORD=your_password \
  -e HOST=127.0.0.1 \
  agahkarakuzu:mystlibre \
  python example_docker_in_docker.py
```

**With docker-compose:**
```yaml
environment:
  - HOST_WORKSPACE_PATH=/home/user/workspace
  - DOCKER_PRIVATE_REGISTRY_USERNAME=${DOCKER_PRIVATE_REGISTRY_USERNAME}
  - DOCKER_PRIVATE_REGISTRY_PASSWORD=${DOCKER_PRIVATE_REGISTRY_PASSWORD}
  - CURVENOTE_TOKEN=${CURVENOTE_TOKEN}
```

**Then run:**
```bash
export DOCKER_PRIVATE_REGISTRY_USERNAME=myuser
export DOCKER_PRIVATE_REGISTRY_PASSWORD=mypass
export CURVENOTE_TOKEN=mytoken
docker-compose run myst-libre python example_docker_in_docker.py
```

## Differences from Local Mode

| Aspect | Local Mode | Docker-in-Docker |
|--------|-----------|------------------|
| Execution | Host machine | Container |
| Path specification | Absolute host paths | Container paths |
| Path translation | None | Automatic (via `host_path_prefix`) |
| Docker socket | Native access | Mounted volume |
| Cleanup | Manual | Automatic (context manager) |
| Example file | `example2.py` | `example_docker_in_docker.py` |

## Reference

- [Dockerfile](../Dockerfile) - Container image definition
- [docker-compose.yml](../docker-compose.yml) - Docker Compose configuration
- [example_docker_in_docker.py](../example_docker_in_docker.py) - Working example
- [myst_libre/tools/path_utils.py](../myst_libre/tools/path_utils.py) - Path translation utilities

## Further Reading

- [Docker-in-Docker Design Patterns](https://jpetazzo.github.io/2015/09/03/do-not-use-docker-in-docker-for-ci/)
- [Docker Socket Mounting](https://docs.docker.com/engine/reference/commandline/run/#mount-volume--v---read-only)
- [MyST Documentation](https://mystmd.org/)
- [BinderHub Documentation](https://binderhub.readthedocs.io/)
