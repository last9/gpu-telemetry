# l9gpu AWS Testing Playbook

> **How to use this file:** Work through each scenario in order. After each section, note your findings (what worked, what didn't, any errors, unexpected output) and file an issue or PR with your results so we can update docs and add test cases.

---

## Prerequisites (Complete First)

### P1. Gather credentials

```
Last9 OTLP endpoint:   ___________________________
Last9 bearer token:    ___________________________
AWS region:            ___________________________  (e.g. us-east-1)
AWS account ID:        aws sts get-caller-identity --query Account --output text
SSH key pair name:     ___________________________
```

### P2. Confirm local tools

```bash
aws --version           # AWS CLI v2
docker --version        # Docker 24+
kubectl version         # kubectl
helm version            # Helm 3+
eksctl version          # eksctl — install with: brew install eksctl
python3 --version       # Python 3.10+ (only needed for bare-metal scenarios)
```

> **Note:** `eksctl` is required for Scenario 6 (EKS cluster creation). If `eksctl: command not found`, install it before proceeding:
> ```bash
> brew install eksctl
> ```

### P2b. Create SSH key pair (if you don't have one)

```bash
aws ec2 create-key-pair \
  --key-name my-gpu-lab \
  --query "KeyMaterial" \
  --output text > ~/.ssh/my-gpu-lab.pem
chmod 400 ~/.ssh/my-gpu-lab.pem
```

### P3. Set shell variables (use throughout)

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export L9GPU_OTLP_ENDPOINT="https://<your-last9-otlp-endpoint>"
export L9GPU_OTLP_TOKEN="Basic <your-last9-token>"
export KEY_PAIR=my-gpu-lab   # or your existing key pair name
```

---

## Scenario 1: EC2 Bare-Metal — stdout sink (sanity check)

**Goal:** Verify the collector can read NVIDIA GPU metrics via NVML with no network dependency.

### 1.1 Launch EC2 GPU instance

```bash
# Find the latest Deep Learning Base OSS Nvidia Driver AMI (Ubuntu 22.04)
# This AMI has NVIDIA drivers + CUDA pre-installed — no driver setup needed.
DL_AMI=$(aws ec2 describe-images \
  --region $AWS_REGION \
  --owners amazon \
  --filters \
    "Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*" \
    "Name=state,Values=available" \
  --query "sort_by(Images, &CreationDate)[-1].ImageId" \
  --output text)
echo "Using AMI: $DL_AMI"

# Create a security group (allow SSH from your IP only)
SG_ID=$(aws ec2 create-security-group \
  --group-name my-gpu-lab-sg \
  --description "l9gpu testing" \
  --query GroupId --output text)

MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 22 --cidr ${MY_IP}/32

# Launch instance (g4dn.xlarge = NVIDIA T4, ~$0.53/hr)
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $DL_AMI \
  --instance-type g4dn.xlarge \
  --key-name $KEY_PAIR \
  --security-group-ids $SG_ID \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=my-gpu-lab}]" \
  --query "Instances[0].InstanceId" --output text)

echo "Instance: $INSTANCE_ID"
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

EC2_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
echo "IP: $EC2_IP"
```

### 1.2 Copy local source to EC2

```bash
# From your Mac — include -e to pass the SSH key
rsync -avz \
  --exclude '.git' --exclude '*.pyc' --exclude '__pycache__' \
  --exclude '.venv' --exclude 'dist' --exclude 'build' \
  -e "ssh -i ~/.ssh/${KEY_PAIR}.pem" \
  /Users/shekhar/labx/gpu-telemetry/gcm/ \
  ubuntu@${EC2_IP}:~/gcm/
```

### 1.3 Install from local source

```bash
ssh -i ~/.ssh/${KEY_PAIR}.pem ubuntu@${EC2_IP}
cd ~/gcm
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 1.4 Verify NVIDIA driver is working

```bash
nvidia-smi          # should show T4 GPU
nvcc --version      # should show CUDA version
```

### 1.5 Run collector — stdout, single shot

```bash
l9gpu nvml_monitor --sink stdout --once
```

**Expected output:** JSON or structured metrics printed to terminal for each GPU. Should include:
- `gpu.utilization`, `gpu.temperature`, `gpu.power.draw`, `gpu.memory.used.percent`
- `gpu.encode.utilization`, `gpu.decode.utilization` (encoder/decoder engine utilization)
- `gpu.xid.errors` (cumulative XID error count; 0 at idle), `gpu.pcie.replay.count` (cumulative PCIe replay events)
- `gpu.energy.consumption` (cumulative energy in mJ)
- `gpu.throttle.reason` emitted four times — once per throttle cause, with `gpu.throttle.cause` attribute set to `power_software`, `temp_hardware`, `temp_software`, or `syncboost` (value is 0 or 1)
- Resource attributes: `gpu.vendor=nvidia`, `gpu.model`, `gpu.uuid`, `host.name`

> **Note on XID errors and PCIe replay:** These are cumulative counters. At idle on a healthy GPU both should be 0 (or very low). Non-zero XID errors are a reliability signal worth alerting on.

**Report:** Paste the full output. Note any warnings or errors.

### 1.6 Run collector — stdout, continuous (30 s test)

```bash
l9gpu nvml_monitor --sink stdout --push-interval 10 --collect-interval 5 --interval 10 &
sleep 35 && kill %1
```

**Expected output:** Metrics printed every 10 seconds (3 pushes total).

---

## Scenario 2: EC2 Bare-Metal — OTLP export to Last9

**Goal:** Send real GPU metrics to Last9 from a bare-metal EC2 instance.

(Continue SSH session from Scenario 1)

### 2.1 Set credentials

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://<your-last9-otlp-endpoint>"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <your-last9-token>"
export OTEL_EXPORTER_OTLP_TIMEOUT="30"
```

> **Note on header format:** `OTEL_EXPORTER_OTLP_HEADERS` uses `key=value` syntax with no outer quotes around the value (the shell variable itself is quoted, but the value inside is literally `Authorization=Basic <token>`). Copy the exact token string from **Last9 → Integrations → OpenTelemetry** (it starts with `Basic `). Multiple headers are comma-separated: `"key1=val1,key2=val2"`.

> **Note:** `OTEL_EXPORTER_OTLP_TIMEOUT` is required by the OTLP exporter (value in seconds).

### 2.2 Single-shot OTLP export

```bash
l9gpu nvml_monitor --sink otel --once
```

**Expected:** Command exits 0 with no errors. Metrics appear in Last9 within 1–2 minutes.

### 2.3 Continuous OTLP export (5-minute soak test)

```bash
l9gpu nvml_monitor --sink otel \
  --push-interval 60 \
  --collect-interval 10 \
  --cluster "my-ec2-gpu-cluster" \
  &

# Let it run for 5 minutes, then stop
sleep 300 && kill %1
```

**Verify in Last9:** Check for metrics with `k8s.cluster.name=my-ec2-gpu-cluster`.

> **Why `k8s.cluster.name`?** The `--cluster` flag sets the `k8s.cluster.name` OTel resource
> attribute for all deployment types (not just Kubernetes). Last9 uses this attribute as the
> universal cluster grouping key, so the same PromQL filter (`k8s_cluster_name=...`) works
> across K8s and bare-metal environments.

**Report:** Did metrics arrive? Any drops or gaps? What's the metric count?

---

## Scenario 3: EC2 Bare-Metal — health_checks CLI

**Goal:** Validate the health_checks tool works on a real GPU node.

(Continue SSH session)

> **CLI note:** `health_checks` is a group with subcommands (e.g. `check-nvidia-smi`, `check-dcgmi`).
> Most subcommands take two positional arguments: `<cluster>` and `<type>` (one of `prolog`, `epilog`, `nagios`, `app`).
> Use `nagios` for standalone/K8s health checks; `prolog`/`epilog` are for Slurm job lifecycle hooks.
> **Exception:** `cuda` is itself a subgroup — use `health_checks cuda memtest <cluster> <type>` (not `health_checks cuda <cluster> <type>`).
> Run `health_checks --help` and `health_checks check-nvidia-smi --help` to see all options.

### 3.1 Run GPU health checks — stdout

> **Threshold defaults for testing:**
> - `--gpu_num` defaults to `8`. Pass `--gpu_num 1` (or however many GPUs your test instance has) to avoid a false CRITICAL.
> - `--gpu_mem_usage_threshold` defaults to `15` MiB. GPU drivers consume ~300–500 MiB at idle, so set this to `1024` or higher for a baseline-idle test.

```bash
# Run nvidia-smi GPU checks and print results to stdout (no telemetry)
health_checks check-nvidia-smi my-ec2-gpu-cluster nagios \
  --check gpu_num --gpu_num 1 \
  --check running_procs \
  --sink stdout
```

For additional checks (add as needed):

```bash
health_checks check-nvidia-smi my-ec2-gpu-cluster nagios \
  --check gpu_num --gpu_num 1 \
  --check running_procs \
  --check gpu_temperature --gpu_temperature_threshold 85 \
  --check gpu_mem_usage --gpu_mem_usage_threshold 1024 \
  --sink stdout
```

### 3.2 Run GPU health checks — OTLP

```bash
# Credentials must still be set from Scenario 2.1
health_checks check-nvidia-smi my-ec2-gpu-cluster nagios \
  --check gpu_num --gpu_num 1 \
  --check running_procs \
  --sink otel
```

### 3.3 Run CUDA health check

> **Prerequisite:** `cuda` is a subgroup — the only subcommand is `memtest`, which requires the
> `cudaMemTest` binary to be compiled from source. The Makefile has a hardcoded HPC cluster path,
> so compile directly with the system `nvcc`:
>
> ```bash
> cd ~/gcm/l9gpu/health_checks/cuda
> nvcc -Xcompiler -O3 -Xcompiler -Wall -Xcompiler -fPIC -Xcompiler -Wextra \
>   cudaMemTest.c -o cudaMemTest
> sudo cp cudaMemTest /usr/local/bin/
> ```

```bash
health_checks cuda memtest my-ec2-gpu-cluster nagios --sink stdout -gpu 0
```

**Expected:** `OK - cuda memtest` with exit code 0 if CUDA memory allocation succeeds.
**CRITICAL with `cudaMemTest: not found`** means the binary was not compiled/installed — not a hardware fault.

**Report:** What health metrics appear? Any issues flagged? Note the exit codes (0=OK, 1=WARN, 2=CRITICAL). CRITICAL on `gpu_num` without `--gpu_num` override or on `gpu_mem_usage` with default threshold indicates a config mismatch, not a hardware fault.

---

## Scenario 4: EC2 Bare-Metal — systemd Service Deployment

**Goal:** Test the production-like bare-metal deployment using systemd.

(Continue SSH session)

### 4.1 Copy systemd service files

```bash
sudo cp ~/gcm/systemd/nvml/l9gpu_nvml_monitor.service /etc/systemd/system/
sudo cp ~/gcm/systemd/nvml/l9gpu_nvml_resources.slice /etc/systemd/system/ 2>/dev/null || true
```

### 4.2 Create environment file for credentials

```bash
sudo mkdir -p /etc/l9gpu
sudo tee /etc/l9gpu/env <<EOF
OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-last9-otlp-endpoint>
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <your-last9-token>
OTEL_EXPORTER_OTLP_TIMEOUT=30
EOF
sudo chmod 600 /etc/l9gpu/env
```

### 4.3 Edit the service file for the test environment

The production service file runs as `cluster_monitor` and calls `/usr/bin/l9gpu`. For the venv-based test installation, update both:

```bash
# Check where l9gpu is installed in the venv
LGPU_BIN=$(which l9gpu)
echo "l9gpu binary: $LGPU_BIN"

# Verify the service file contents BEFORE editing
cat /etc/systemd/system/l9gpu_nvml_monitor.service

# Edit the service to use the correct binary path and run as ubuntu
sudo sed -i \
  -e "s|User=cluster_monitor|User=ubuntu|" \
  -e "s|ExecStart=/usr/bin/l9gpu|ExecStart=${LGPU_BIN}|" \
  /etc/systemd/system/l9gpu_nvml_monitor.service

# Also set the sink to otel
# The ExecStart line ends in "nvml_monitor" — append flags after it
sudo sed -i \
  's|ExecStart=\(.*\) nvml_monitor$|ExecStart=\1 nvml_monitor --sink otel --cluster my-ec2-gpu-cluster|' \
  /etc/systemd/system/l9gpu_nvml_monitor.service

# Verify the result looks correct before starting
cat /etc/systemd/system/l9gpu_nvml_monitor.service
```

> **Note:** The `sed` pattern matches lines ending exactly in `nvml_monitor`. If you see the line ends differently (e.g., trailing flags already present), skip the second `sed` and edit the file directly with `sudo nano /etc/systemd/system/l9gpu_nvml_monitor.service`.

### 4.4 Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable l9gpu_nvml_monitor
sudo systemctl start l9gpu_nvml_monitor
```

### 4.5 Check service status and logs

```bash
sudo systemctl status l9gpu_nvml_monitor
sudo journalctl -u l9gpu_nvml_monitor -f
```

**Report:** Does the service start cleanly? Any permission issues? Does it restart on failure?

---

## Scenario 5: EC2 — Docker Container (local image)

**Goal:** Test running the collector as a Docker container on a GPU EC2 instance.

### 5.1 Build Docker image on EC2

```bash
cd ~/gcm
docker build -f docker/Dockerfile -t l9gpu:test .
```

### 5.3 Run container — stdout, single shot

```bash
docker run --rm \
  --gpus all \
  l9gpu:test \
  nvml_monitor --sink stdout --once
```

### 5.4 Run container — OTLP to Last9

```bash
docker run --rm \
  --gpus all \
  -e OTEL_EXPORTER_OTLP_ENDPOINT="https://<your-last9-otlp-endpoint>" \
  -e OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <your-last9-token>" \
  -e OTEL_EXPORTER_OTLP_TIMEOUT="30" \
  l9gpu:test \
  nvml_monitor --sink otel --once
```

**Report:** Does the container start correctly? Is `--gpus all` sufficient to give NVML access? Any NVML library path issues inside the container?

---

## Scenario 6: EKS — DaemonSet (Helm, OTLP to Last9)

**Goal:** Deploy l9gpu as a DaemonSet on EKS, metrics flowing to Last9.

### 6.1 Build and push Docker image to ECR

```bash
# On your Mac (or EC2 to avoid large upload)
cd /Users/shekhar/labx/gpu-telemetry/gcm

# Build for linux/amd64
docker buildx build \
  -f docker/Dockerfile \
  --platform linux/amd64 \
  -t l9gpu:test \
  --load .

# Create ECR repository (one-time)
aws ecr create-repository \
  --repository-name l9gpu \
  --region $AWS_REGION 2>/dev/null || true

ECR_URI=${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/l9gpu

# Authenticate and push
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_URI

docker tag l9gpu:test ${ECR_URI}:test
docker push ${ECR_URI}:test
```

### 6.2 Create EKS cluster with GPU node group

```bash
eksctl create cluster \
  --name my-gpu-lab \
  --region $AWS_REGION \
  --nodegroup-name gpu-ng \
  --node-type g4dn.xlarge \
  --nodes 1 --nodes-min 1 --nodes-max 2 \
  --managed \
  --with-oidc

aws eks update-kubeconfig --name my-gpu-lab --region $AWS_REGION
kubectl get nodes
```

### 6.3 Install NVIDIA device plugin

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.18.2/deployments/static/nvidia-device-plugin.yml

# Wait for the plugin to be ready
# Note: the static manifest uses label name=nvidia-device-plugin-ds (not app=...)
kubectl wait --for=condition=ready pod -l name=nvidia-device-plugin-ds \
  -n kube-system --timeout=120s

# Verify GPU is allocatable
kubectl get nodes -o json | \
  python3 -c "import json,sys; nodes=json.load(sys.stdin)['items']; \
  [print(n['metadata']['name'], n['status']['allocatable'].get('nvidia.com/gpu','0')) \
  for n in nodes]"
```

> **Label the GPU node:** The static device plugin manifest does NOT automatically set the
> `nvidia.com/gpu.present=true` node label (that requires GPU Feature Discovery / NFD).
> The Helm chart's default `nodeSelector` uses this label, so you must apply it manually:
>
> ```bash
> # Replace the node name with your actual node name from kubectl get nodes
> kubectl label node <node-name> nvidia.com/gpu.present=true
> ```

### 6.3b Enable GPU time-slicing (required for single-GPU nodes)

The monitoring DaemonSet and the health-checks CronJob each request `nvidia.com/gpu: 1`.
On a node with a single physical GPU the CronJob will stay `Pending` unless time-slicing is
enabled so the device plugin advertises 2 virtual slots from the one physical GPU.

```bash
# 1. Create the time-slicing config (2 replicas → 2 virtual GPU slots)
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: nvidia-device-plugin-config
  namespace: kube-system
data:
  config.yaml: |
    version: v1
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 2
EOF

# 2. Patch the device plugin DaemonSet to load the config
kubectl patch daemonset nvidia-device-plugin-daemonset -n kube-system \
  --type=strategic -p '{
  "spec": {"template": {"spec": {
    "containers": [{"name": "nvidia-device-plugin-ctr",
      "env": [{"name": "CONFIG_FILE", "value": "/etc/nvidia/config.yaml"}],
      "volumeMounts": [{"name": "config", "mountPath": "/etc/nvidia"}]
    }],
    "volumes": [{"name": "config", "configMap": {"name": "nvidia-device-plugin-config"}}]
  }}}}'

kubectl rollout status daemonset/nvidia-device-plugin-daemonset -n kube-system --timeout=120s

# 3. Verify the node now advertises 2 slots
kubectl get node -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
# Expected: <node-name>   2
```

> **Multi-GPU nodes:** If your node has N GPUs and you want each to be independently allocatable
> set `replicas: 1` (the default) or omit this step entirely. Time-slicing is only needed when
> two pods both need `nvidia.com/gpu: 1` on the same single-GPU node.

### 6.4 Create monitoring namespace and Last9 credentials secret

```bash
kubectl create namespace monitoring

# The secret keys map directly to OTel SDK environment variables.
# The Helm chart mounts this secret via otlpSecretName.
kubectl create secret generic l9gpu-otlp-auth \
  -n monitoring \
  --from-literal=OTEL_EXPORTER_OTLP_ENDPOINT="https://<your-last9-otlp-endpoint>" \
  --from-literal=OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <your-last9-token>" \
  --from-literal=OTEL_EXPORTER_OTLP_TIMEOUT="30"
```

### 6.5 Deploy with Helm

Use the provided example values file — it is the recommended approach. Edit `image.repository`
and `image.tag` to match your ECR URI:

```bash
# Copy the example and fill in your ECR URI and tag
cp deploy/helm/l9gpu/examples/eks-otlp-direct.yaml /tmp/l9gpu-eks-values.yaml
# Edit image.repository → <AWS_ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/l9gpu
# Edit image.tag        → your tag (e.g. "test" or a git SHA)
# Edit healthChecks.extraArgs --gpu_num → number of GPUs on your node (default in file is 1)

helm install l9gpu ./deploy/helm/l9gpu \
  --namespace monitoring \
  --values /tmp/l9gpu-eks-values.yaml
```

> **Key settings already baked into the example values file** (do not remove):
>
> | Setting | Why it's needed |
> |---|---|
> | `monitoring.extraArgs: [--log-folder, /tmp]` | Container has `readOnlyRootFilesystem: true`; logger writes to `/tmp` which is an emptyDir mount |
> | `healthChecks.extraArgs: [--log-folder, /tmp]` | Same reason — CronJob container is also read-only root |
> | `healthChecks.extraArgs: [--gpu_num, "1"]` | `--gpu_num` defaults to `8`; mismatched count → false CRITICAL. Set to the actual GPU count on your nodes |
> | `healthChecks.resources.limits.nvidia.com/gpu: 1` | Without a GPU resource request, the NVIDIA runtime does not inject `libnvidia-ml.so.1` and `nvidia-smi` sees 0 GPUs |

> **Why use the values file instead of `--set`?**
> The `nodeSelector` value `nvidia.com/gpu.present=true` must be a string, but `--set` auto-casts
> it to a boolean, causing: `expected string, got &value.valueUnstructured{Value:true}`.
> The values file keeps it quoted. If you must use `--set`, use `--set-string` for that flag:
> ```bash
> --set-string "monitoring.nodeSelector.nvidia\\.com/gpu\\.present=true"
> ```

> **If the install fails with "release name already in use"** (e.g. after a failed install attempt):
> ```bash
> helm upgrade l9gpu ./deploy/helm/l9gpu --namespace monitoring --values /tmp/l9gpu-eks-values.yaml
> # or: helm uninstall l9gpu -n monitoring && helm install ...
> ```

> **AWS credential expiry:** If `helm upgrade/install` or `aws eks update-kubeconfig` fails with
> `ExpiredTokenException`, refresh your AWS session first (`aws sso login` or re-export keys),
> then re-run `aws eks update-kubeconfig --name my-gpu-lab --region $AWS_REGION`.

### 6.6 Verify DaemonSet and health-checks CronJob

```bash
# The DaemonSet is named l9gpu-monitoring (not l9gpu)
kubectl get daemonset/l9gpu-monitoring -n monitoring
kubectl get pods -n monitoring -o wide

# Stream logs from the monitoring pod
POD=$(kubectl get pods -n monitoring \
  -l app.kubernetes.io/name=l9gpu,app.kubernetes.io/component!=health-checks \
  -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n monitoring $POD -f

# Verify health-checks CronJob — trigger a manual run instead of waiting 15 min
kubectl create job -n monitoring --from=cronjob/l9gpu-health-checks hc-verify
kubectl wait --for=condition=complete job/hc-verify -n monitoring --timeout=60s 2>/dev/null || true
kubectl logs -n monitoring -l job-name=hc-verify
# Expected output: "OK - nvidia smi"
kubectl delete job hc-verify -n monitoring
```

> **Redeploying after code changes:**
> ```bash
> # 1. Rebuild and push (Mac arm64 → linux/amd64)
> docker buildx build --platform linux/amd64 -f docker/Dockerfile \
>   -t ${ECR_URI}:test --push .
> # 2. Upgrade
> helm upgrade l9gpu ./deploy/helm/l9gpu --namespace monitoring \
>   --values /tmp/l9gpu-eks-values.yaml
> # 3. Force pod refresh (pullPolicy: Always does not auto-restart existing pods)
> kubectl rollout restart daemonset/l9gpu-monitoring -n monitoring
> kubectl rollout status daemonset/l9gpu-monitoring -n monitoring
> ```

### 6.7 Verify in Last9

Check for metrics with resource attribute `k8s.cluster.name=my-eks-gpu-cluster`.

**Report:**
- Does `l9gpu-monitoring` DaemonSet pod reach Running state?
- Any image pull errors? (ECR auth issue — re-run `aws ecr get-login-password` if so)
- Does NVML work inside the Kubernetes pod?
- Are metrics arriving in Last9?
- Does the OTLP auth header injection work?
- Does `hc-verify` job log `OK - nvidia smi`?

---

### 6.8 Multi-GPU Node (g4dn.12xlarge — 4× T4)

**Goal:** Verify l9gpu correctly enumerates and reports per-GPU metrics for all 4 GPUs on a multi-GPU node.

> **NVIDIA_VISIBLE_DEVICES=all is required.** With `nvidia.com/gpu: 1` in resources, the device
> plugin restricts the container to 1 GPU slot — `nvmlDeviceGetCount()` returns 1 even on a 4-GPU
> node. Set `NVIDIA_VISIBLE_DEVICES=all` via `monitoring.extraEnv` (and `healthChecks.extraEnv`)
> in the values file so NVML sees all 4 physical GPUs. See `eks-multigpu-values.yaml`.
>
> **eksctl replaces the nvidia-device-plugin DaemonSet** when adding a new node group, which
> resets any time-slicing patches applied earlier. Re-apply the strategic merge patch after
> `eksctl create nodegroup` completes.

#### 6.8.1 Add gpu-multi node group

```bash
eksctl create nodegroup \
  --cluster my-gpu-lab \
  --region ap-south-1 \
  --name gpu-multi \
  --node-type g4dn.12xlarge \
  --nodes 1 --nodes-min 1 --nodes-max 1 \
  --node-labels "nvidia.com/gpu.present=true" \
  --node-zones ap-south-1a

# Wait for node to be Ready
kubectl get nodes -l alpha.eksctl.io/nodegroup-name=gpu-multi -w

# Verify 4 allocatable GPUs
kubectl describe node -l alpha.eksctl.io/nodegroup-name=gpu-multi \
  | grep "nvidia.com/gpu"
# Expected: nvidia.com/gpu: 4
```

> **Time-slicing is NOT needed** on the 4-GPU node itself. However, eksctl replaces the
> nvidia-device-plugin DaemonSet when adding the node group, resetting any time-slicing
> config on the original single-GPU node. Re-apply the ConfigMap patch so the original node
> still advertises 2 virtual GPU slots:
>
> ```bash
> # The ConfigMap already exists — just re-patch the DaemonSet
> kubectl patch daemonset nvidia-device-plugin-daemonset -n kube-system \
>   --type=strategic -p '{
>   "spec": {"template": {"spec": {
>     "containers": [{"name": "nvidia-device-plugin-ctr",
>       "env": [{"name": "CONFIG_FILE", "value": "/etc/nvidia/config.yaml"}],
>       "volumeMounts": [{"name": "config", "mountPath": "/etc/nvidia"}]
>     }],
>     "volumes": [{"name": "config", "configMap": {"name": "nvidia-device-plugin-config"}}]
>   }}}}'
> kubectl rollout status daemonset/nvidia-device-plugin-daemonset -n kube-system --timeout=120s
>
> # Verify: original node=2 slots, new node=8 slots (4 physical × replicas:2)
> kubectl get node -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
> ```

#### 6.8.2 Upgrade Helm release with multi-GPU values

A ready-to-use values file is at `deploy/helm/l9gpu/examples/eks-multigpu-values.yaml`.
It sets `cluster=my-eks-multigpu` and `--gpu_num 4`.

```bash
# Copy and fill in your ECR URI
cp deploy/helm/l9gpu/examples/eks-multigpu-values.yaml /tmp/l9gpu-eks-multigpu-values.yaml
# Edit image.repository → <AWS_ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/l9gpu
# Edit image.tag        → your tag (e.g. "test")

helm upgrade l9gpu ./deploy/helm/l9gpu \
  --namespace monitoring \
  --values /tmp/l9gpu-eks-multigpu-values.yaml

# Force pod refresh on all nodes (pullPolicy: Always does not restart existing pods)
kubectl rollout restart daemonset/l9gpu-monitoring -n monitoring
kubectl rollout status daemonset/l9gpu-monitoring -n monitoring
```

#### 6.8.3 Verify two DaemonSet pods (one per node)

```bash
# Should show 2 pods: one on the original g4dn.xlarge, one on the new g4dn.12xlarge
kubectl get pods -n monitoring -o wide

# Check logs on the multi-GPU pod (will be on the node with the gpu-multi label)
MULTI_NODE=$(kubectl get node -l alpha.eksctl.io/nodegroup-name=gpu-multi \
  -o jsonpath='{.items[0].metadata.name}')
MULTI_POD=$(kubectl get pods -n monitoring -o wide \
  --field-selector spec.nodeName=${MULTI_NODE} \
  -l app.kubernetes.io/name=l9gpu,app.kubernetes.io/component!=health-checks \
  -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n monitoring $MULTI_POD | head -40
```

#### 6.8.4 Verify in Last9

Filter `k8s.cluster.name=my-eks-multigpu`. Confirm four distinct series per metric,
one for each `gpu.index` value: `0`, `1`, `2`, `3`.

**Report:**
- Does the pod on the multi-GPU node start cleanly?
- Does NVML enumerate all 4 GPUs (check logs for per-GPU metric blocks)?
- Are `gpu.index=0,1,2,3` all visible in Last9?
- Does the `gpu_num` health check pass (expected: `OK - nvidia smi` with 4 GPUs found)?

---

### 6.9 vLLM Integration on EKS

**Goal:** Deploy a vLLM inference server and `vllm_monitor` on EKS; confirm vLLM metrics appear in Last9.

> **`vllm_monitor` is a subcommand of `l9gpu`**, not a standalone script. Use
> `command: ["l9gpu", "vllm_monitor"]` in the Deployment spec — `command: ["vllm_monitor"]`
> will fail with "executable file not found in $PATH".
>
> **New vLLM (≥0.6) changed the cache metric name.** `gpu_cache_usage_perc` and
> `cpu_cache_usage_perc` are gone; only `kv_cache_usage_perc` exists. The `vllm_monitor`
> parser automatically falls back to `kv_cache_usage_perc` (fix included in the codebase).
>
> **vLLM startup takes 3–6 minutes** on a fresh node (image pull ~9 GB + JIT CUDA compile).
> The pod will show Ready=1/1 before the HTTP server binds port 8000. Wait until
> `kubectl logs deployment/vllm | grep "Application startup complete"` appears.
>
> **T4 nodes (g4dn.xlarge, compute capability 7.5) require two extra flags:**
> `--enforce-eager` disables torch.compile/CUDA graph JIT (which crashes on T4 with vLLM ≥0.16)
> and `--max-model-len 4096` caps the KV cache to ~0.9 GB (default 32768 needs ~7 GB and OOMs).
> Flash Attention 2 is also unsupported on T4 — vLLM falls back to FLASHINFER automatically.
>
> **`vllm_monitor` runs silently** — it only logs at DEBUG level. Use `--sink stdout`
> via `kubectl exec` to verify scraping works; production OTLP push has no log output.

#### 6.9.1 Deploy vLLM server

```bash
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args: ["--model", "Qwen/Qwen2.5-3B-Instruct", "--port", "8000",
                 "--enforce-eager", "--max-model-len", "4096"]
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
            requests:
              nvidia.com/gpu: "1"
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      nodeSelector:
        nvidia.com/gpu.present: "true"
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-svc
  namespace: monitoring
spec:
  selector:
    app: vllm
  ports:
    - port: 8000
      targetPort: 8000
EOF

# Wait for vLLM to finish loading the model (can take 2–3 min on first pull)
kubectl rollout status deployment/vllm -n monitoring --timeout=300s
kubectl logs deployment/vllm -n monitoring -f &
# Wait until you see "Uvicorn running on http://0.0.0.0:8000" in the logs, then Ctrl+C
```

> **Note:** vLLM downloads `Qwen/Qwen2.5-3B-Instruct` weights on first start (~6 GB). The pod
> will show `ContainerCreating` while the image is pulled (~2–3 min for `vllm/vllm-openai:latest`),
> then spend an additional 3–5 min downloading model weights. Wait for "Application startup complete" in logs.

#### 6.9.2 Deploy vllm_monitor

`vllm_monitor` is a standalone CLI — not part of the Helm chart. Deploy it as a separate
Deployment using the same l9gpu ECR image and OTLP secret:

```bash
# Replace <AWS_ACCOUNT> and <REGION> with your values before applying
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-monitor
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-monitor
  template:
    metadata:
      labels:
        app: vllm-monitor
    spec:
      containers:
        - name: vllm-monitor
          image: <AWS_ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/l9gpu:test
          imagePullPolicy: Always
          command: ["l9gpu", "vllm_monitor"]
          args:
            - --vllm-endpoint
            - "http://vllm-svc:8000/metrics"
            - --model-name
            - "Qwen/Qwen2.5-3B-Instruct"
            - --cluster
            - "my-eks-multigpu"
            - --sink
            - "otel"
            - --push-interval
            - "30"
          envFrom:
            - secretRef:
                name: l9gpu-otlp-auth
          resources:
            limits:
              cpu: 200m
              memory: 128Mi
            requests:
              cpu: 50m
              memory: 64Mi
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
EOF

kubectl rollout status deployment/vllm-monitor -n monitoring --timeout=60s
```

> **Why `command: ["l9gpu", "vllm_monitor"]`?** The image ENTRYPOINT is `l9gpu`. The `vllm_monitor`
> function is registered as the `vllm_monitor` subcommand of the `l9gpu` CLI, not as a standalone
> script. Using `command: ["vllm_monitor"]` fails with "executable file not found in $PATH".
>
> **Why no `nvidia.com/gpu` resource request?** `vllm_monitor` only scrapes the vLLM HTTP
> `/metrics` endpoint — it does not use NVML or access the GPU directly. No GPU slot needed.

#### 6.9.3 Generate load and verify metrics

```bash
# Port-forward vLLM service
kubectl port-forward svc/vllm-svc 8000:8000 -n monitoring &
PF_PID=$!

# Wait for port-forward to establish
sleep 3

# Send a test request to populate latency histograms
curl http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-3B-Instruct","prompt":"Hello world","max_tokens":20}'

# Send a few more to generate throughput
for i in {1..5}; do
  curl -s http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"Qwen/Qwen2.5-3B-Instruct","prompt":"Explain GPU monitoring in one sentence.","max_tokens":30}' \
    > /dev/null
done

kill $PF_PID

# Verify scraping works (vllm_monitor runs silently — use exec + stdout sink to check)
kubectl exec deployment/vllm-monitor -n monitoring -- \
  l9gpu vllm_monitor --vllm-endpoint http://vllm-svc:8000/metrics --sink stdout --once
# Expected: JSON with e2e_latency_p50/p95/p99, ttft_p50/p95, gpu_cache_usage, requests_running/waiting
```

**Expected log output after two push cycles (~60 s):**

```
# First cycle (throughput=None — no previous baseline):
{"e2e_latency_p50": 0.15, "e2e_latency_p95": ..., "ttft_p50": ..., "gpu_cache_usage": 0.0, "requests_running": 0, "requests_waiting": 0}

# Second cycle (throughput populated):
{"prompt_tokens_per_sec": 0.0, "generation_tokens_per_sec": 0.0, "e2e_latency_p50": ..., "gpu_cache_usage": 0.0, ...}
```

> **vllm_monitor runs silently** — no stdout unless you use `--sink stdout`. Check via exec:
> `kubectl exec deployment/vllm-monitor -n monitoring -- l9gpu vllm_monitor --vllm-endpoint http://vllm-svc:8000/metrics --sink stdout --once`

**Verify in Last9** after ~60 s (two push cycles):

- `vllm.prompt.throughput`, `vllm.generation.throughput`
- `vllm.cache.usage` — one series: `cache.type=gpu` (new vLLM ≥0.6 only exposes KV cache)
- `vllm.requests.running`, `vllm.requests.waiting`
- `vllm.request.latency` — three series: `quantile=p50`, `quantile=p95`, `quantile=p99`
- `vllm.ttft` — two series: `quantile=p50`, `quantile=p95`

> **`vllm.requests.swapped`** is not emitted by new vLLM (≥0.6) — the `num_requests_swapped`
> metric was removed. This is expected; no alert or error.

Filter by resource attributes: `k8s.cluster.name=my-eks-multigpu` and `vllm.model.name=Qwen/Qwen2.5-3B-Instruct`.

**Clean up when done:**

```bash
kubectl delete deployment vllm vllm-monitor -n monitoring
kubectl delete service vllm-svc -n monitoring
```

**Report:**
- Does vLLM start cleanly and serve the model?
- Does `vllm_monitor` connect to `http://vllm-svc:8000/metrics` without DNS errors?
- Are throughput values non-`None` on the second push cycle?
- Are all five metric groups visible in Last9?
- Any OTLP export errors in the `vllm-monitor` logs?

---

## Scenario 7: EKS — With OTel Collector Proxy (Production Architecture)

**Goal:** Mirror the recommended production architecture: l9gpu → OTel Collector (adds auth) → Last9.

### 7.1 Deploy OpenTelemetry Collector in the cluster

```bash
# Add OTel Helm repo
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

cat > /tmp/otelcol-values.yaml <<'EOF'
mode: deployment

config:
  receivers:
    otlp:
      protocols:
        http:
          endpoint: "0.0.0.0:4318"
        grpc:
          endpoint: "0.0.0.0:4317"

  exporters:
    otlphttp:
      endpoint: "https://<your-last9-otlp-endpoint>"
      headers:
        Authorization: "Basic <your-last9-token>"

  service:
    pipelines:
      metrics:
        receivers: [otlp]
        exporters: [otlphttp]
      logs:
        receivers: [otlp]
        exporters: [otlphttp]
EOF

helm install otelcol open-telemetry/opentelemetry-collector \
  --namespace monitoring \
  --values /tmp/otelcol-values.yaml
```

### 7.2 Reconfigure l9gpu to send to OTel Collector (no auth)

```bash
helm upgrade l9gpu ./deploy/helm/l9gpu \
  --namespace monitoring \
  --set image.repository=${ECR_URI} \
  --set image.tag=test \
  --set otlpSecretName="" \
  --set monitoring.sink=otel \
  --set monitoring.cluster=my-eks-gpu-cluster \
  --set monitoring.slurmEnabled=false \
  --set "monitoring.extraArgs[0]=--sink-opt" \
  --set "monitoring.extraArgs[1]=otel_endpoint=http://otelcol-opentelemetry-collector.monitoring.svc.cluster.local:4318" \
  --set healthChecks.sink=otel \
  --set healthChecks.cluster=my-eks-gpu-cluster \
  --set "healthChecks.extraArgs[0]=--sink-opt" \
  --set "healthChecks.extraArgs[1]=otel_endpoint=http://otelcol-opentelemetry-collector.monitoring.svc.cluster.local:4318"
```

Or use the provided example values file:

```bash
cp deploy/helm/l9gpu/examples/eks-otel-proxy.yaml /tmp/l9gpu-eks-otelproxy.yaml
# Edit image.repository
helm upgrade l9gpu ./deploy/helm/l9gpu \
  --namespace monitoring \
  --values /tmp/l9gpu-eks-otelproxy.yaml
```

**Report:** Does metrics flow correctly through the OTel Collector proxy? Any attribute loss?

---

## Scenario 8: AWS ParallelCluster — Slurm Job Attribution

**Goal:** Test the Slurm job attribution feature. The collector reads `/proc/<pid>/environ` on GPU nodes to correlate GPU usage to Slurm jobs.

> **Note:** This requires AWS ParallelCluster with a GPU compute node. Skip if not available.

### 8.1 Install AWS ParallelCluster CLI

```bash
pip install aws-parallelcluster
```

### 8.2 Create a minimal ParallelCluster config

```bash
cat > /tmp/pcluster-config.yaml <<EOF
Region: $AWS_REGION
Image:
  Os: ubuntu2204

HeadNode:
  InstanceType: t3.medium
  Networking:
    SubnetId: <your-subnet-id>
  Ssh:
    KeyName: $KEY_PAIR

Scheduling:
  Scheduler: slurm
  SlurmQueues:
    - Name: gpu
      CapacityType: ONDEMAND
      ComputeResources:
        - Name: t4gpu
          InstanceType: g4dn.xlarge
          MinCount: 0
          MaxCount: 2
      Networking:
        SubnetIds:
          - <your-subnet-id>
EOF

pcluster create-cluster \
  --cluster-name l9gpu-slurm-test \
  --cluster-configuration /tmp/pcluster-config.yaml
```

### 8.3 Install l9gpu on the compute node

```bash
# SSH to head node
pcluster ssh --cluster-name l9gpu-slurm-test -i ~/.ssh/$KEY_PAIR

# Submit a GPU job so the compute node starts
sbatch --gres=gpu:1 --partition=gpu --wrap="sleep 300"
squeue   # note the node name when job is RUNNING

# SSH to the compute node (from head node)
ssh <compute-node>

# Install l9gpu
python3 -m venv /tmp/l9gpu-venv && source /tmp/l9gpu-venv/bin/activate
pip install l9gpu
```

### 8.4 Run collector and verify Slurm job attributes

```bash
# On the compute node, with the GPU job running:
export OTEL_EXPORTER_OTLP_ENDPOINT="https://<your-last9-otlp-endpoint>"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <your-last9-token>"
export OTEL_EXPORTER_OTLP_TIMEOUT="30"

l9gpu nvml_monitor --sink stdout --once
```

**Expected output:** Slurm job info appears in **OTel Logs** (not metrics). Look in
Last9's log explorer for log records with these attributes:
- `job_id`, `job_user`, `job_name`, `job_partition`, `job_num_gpus`

(Note: underscore naming, not dot notation. `job_id=-1` means no Slurm job was detected.)

**Report:** Are Slurm job attributes visible in the Last9 log explorer? Does the collector correctly read `/proc/<pid>/environ`?

---

## Scenario 9: EC2 — Different GPU Architectures

**Goal:** Validate across different GPU generations available on AWS.

| Instance | GPU | Architecture | Cost/hr |
|---|---|---|---|
| g4dn.xlarge | NVIDIA T4 | Turing | ~$0.53 |
| g5.xlarge | NVIDIA A10G | Ampere | ~$1.01 |
| p3.2xlarge | NVIDIA V100 | Volta | ~$3.06 |
| p4d.24xlarge | NVIDIA A100 | Ampere | ~$32.77 |

For each instance type:

```bash
# Launch with the same DL AMI, different instance type
NEW_INSTANCE=$(aws ec2 run-instances \
  --image-id $DL_AMI \
  --instance-type <INSTANCE_TYPE> \
  --key-name $KEY_PAIR \
  --security-group-ids $SG_ID \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=l9gpu-<TYPE>}]" \
  --query "Instances[0].InstanceId" --output text)

aws ec2 wait instance-running --instance-ids $NEW_INSTANCE

# Then repeat Scenarios 1 and 2
```

**Report for each architecture:**
- Which metrics are available vs missing?
- Are the `gpu.model` and `gpu.architecture` attributes correct?
- Any NVML API errors for specific metrics?
- NVSwitch / NVLink metrics on p4d (multi-GPU)?

---

## Scenario 10: EC2 — Multi-GPU Instance

**Goal:** Verify all GPUs are collected and per-GPU metrics are correct.

> Use g4dn.12xlarge (4× T4, ~$3.91/hr) as a budget-friendly multi-GPU instance.
> Skip p4d ($32.77/hr) unless NVLink/NVSwitch metrics are explicitly in scope.

```bash
MULTI_INSTANCE=$(aws ec2 run-instances \
  --image-id $DL_AMI \
  --instance-type g4dn.12xlarge \
  --key-name $KEY_PAIR \
  --security-group-ids $SG_ID \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=l9gpu-multigpu}]" \
  --query "Instances[0].InstanceId" --output text)

aws ec2 wait instance-running --instance-ids $MULTI_INSTANCE
# Then install and run:
l9gpu nvml_monitor --sink stdout --once
```

**Expected:** One metric data point per GPU index (0, 1, 2, 3 for g4dn.12xlarge).

**Report:**
- Are all 4 GPUs reported?
- Is `gpu.index` attribute correct for each?
- Any NVLink bandwidth metrics?

---

## Scenario 11: DCGM Profiling Metrics

**Goal:** Verify the `dcgm_monitor` command scrapes dcgm-exporter and emits SM/DRAM/tensor/FP-pipe utilization metrics.

> **Instance:** Any GPU EC2 instance from Scenarios 1–10. `g5.xlarge` (A10G) and `p4d.24xlarge` (A100) expose the full profiling metric set. `g4dn.xlarge` (T4) exposes a subset — `sm_active`, `dram_active`, and `gr_engine_active` are typically available; `tensor_active`, `fp64_active`, `fp32_active`, `fp16_active` may read 0 or be absent.

### 11.1 Start dcgm-exporter on EC2

The simplest approach is the official NVIDIA Docker image — no native DCGM install needed.

```bash
# Requires Docker with --gpus support (included in the Deep Learning Base AMI)
docker run -d \
  --gpus all \
  --rm \
  -p 9400:9400 \
  nvcr.io/nvidia/cloud-native/dcgm-exporter:latest
```

Wait ~10 seconds for the exporter to start, then verify:

### 11.2 Verify dcgm-exporter is working

```bash
curl -s http://localhost:9400/metrics | grep DCGM_FI_PROF | head -20
```

**Expected:** Lines like:
```
DCGM_FI_PROF_SM_ACTIVE{gpu="0",UUID="GPU-...",modelName="Tesla T4"} 0.012
DCGM_FI_PROF_DRAM_ACTIVE{gpu="0",...} 0.003
DCGM_FI_PROF_GR_ENGINE_ACTIVE{gpu="0",...} 0.011
```

If the output is empty, the GPU may not expose profiling metrics — see the note at the end of this scenario.

### 11.3 Run dcgm_monitor — stdout, single shot

```bash
l9gpu dcgm_monitor \
  --dcgm-endpoint http://localhost:9400/metrics \
  --once \
  --sink stdout
```

**Expected output:** One block of metrics per GPU. Should include:
- `gpu.sm.active` (SM pipe utilization, 0.0–1.0)
- `gpu.dram.active` (DRAM bandwidth utilization, 0.0–1.0)
- `gpu.gr_engine.active` (graphics/compute engine, 0.0–1.0)
- `gpu.pipe.tensor.active`, `gpu.pipe.fp64.active`, `gpu.pipe.fp32.active`, `gpu.pipe.fp16.active` (may be 0 on T4)
- Attributes: `gpu.index`, `gpu.uuid`, `gpu.model`

**Report:** Paste the full output. Note which metrics read non-zero vs zero.

### 11.4 Run dcgm_monitor — OTLP to Last9

```bash
# Credentials must be set from Scenario 2.1
l9gpu dcgm_monitor \
  --dcgm-endpoint http://localhost:9400/metrics \
  --cluster my-ec2-gpu-cluster \
  --sink otel \
  --once
```

**Expected:** Command exits 0 with no errors. Metrics appear in Last9 with `k8s.cluster.name=my-ec2-gpu-cluster`.

**Report:** Did metrics arrive? Which profiling metrics are visible in Last9?

> **Note on EC2 GPU type support:** DCGM profiling metrics require NVIDIA profiling counters to be enabled. `g4dn` (T4 / Turing) supports `sm_active`, `dram_active`, `gr_engine_active` but typically returns 0 for tensor/FP-pipe counters. `g5` (A10G / Ampere) and `p4d` (A100 / Ampere) expose the full profiling set including `tensor_active`, `fp16_active`, `fp32_active`, `fp64_active`. If all profiling metrics are 0 under load, check that the GPU workload uses the relevant compute paths.

### 11.5 EKS — Deploy dcgm-exporter as a DaemonSet

**Goal:** Run dcgm-exporter on every GPU node in the EKS cluster, expose profiling metrics on `:9400`, and forward them to Last9 via a dedicated OTel collector sidecar.

**Architecture:**
```
dcgm-exporter (DaemonSet, :9400)
    ↓  kubernetes_sd_configs pod discovery (namespace=monitoring)
otel-collector-dcgm (Deployment, 1 replica — scrapes all dcgm-exporter pods exactly once)
    ↓  OTLP HTTP + k8s_cluster_name resource attr
Last9
```

This is separate from the l9gpu NVML pipeline — l9gpu continues sending OTLP directly. The OTel collector here only handles DCGM metrics.

**Prerequisites:** Scenario 6 EKS cluster already running with `l9gpu-otlp-auth` Secret in the `monitoring` namespace.

#### 11.5.1 Add the Helm repos

```bash
# dcgm-exporter is on its own repo — NOT on helm.ngc.nvidia.com/nvidia
helm repo add dcgm-exporter https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
```

> **Gotcha:** `helm search repo nvidia/dcgm-exporter` returns nothing. The chart lives at `dcgm-exporter/dcgm-exporter`.

#### 11.5.2 Create the metrics ConfigMap

The default dcgm-exporter image only exports basic device metrics. Profiling counters (`DCGM_FI_PROF_*`) require a custom metrics CSV:

```bash
kubectl create configmap dcgm-exporter-metrics \
  --namespace monitoring \
  --from-file=dcgm-metrics.csv=deploy/helm/l9gpu/examples/dcgm-metrics.csv
```

> **CSV format gotcha:** Help strings must NOT contain commas — the CSV parser sees extra fields and exits with `wrong number of fields`. Remove commas from help text (e.g. `"KB/s, since last query"` → `"KB/s since last query"`).

> **Unknown field gotcha:** `DCGM_FI_DEV_POWER_STATE` is not recognised by dcgm-exporter v4.x — it will exit with `unknown ExporterCounter field`. Remove it from the CSV.

#### 11.5.3 Derive the OTLP auth secret

The OTel collector needs the endpoint and full `Authorization` header value separately. Derive them from the existing l9gpu secret:

```bash
ENDPOINT=$(kubectl get secret l9gpu-otlp-auth -n monitoring \
  -o jsonpath='{.data.OTEL_EXPORTER_OTLP_ENDPOINT}' | base64 -d)

HEADERS=$(kubectl get secret l9gpu-otlp-auth -n monitoring \
  -o jsonpath='{.data.OTEL_EXPORTER_OTLP_HEADERS}' | base64 -d)

# Strip "Authorization=" prefix → "Basic <token>"  (keeps the "Basic " prefix)
AUTH_VALUE="${HEADERS#Authorization=}"

kubectl create secret generic dcgm-otlp-auth \
  --namespace monitoring \
  --from-literal=LAST9_OTLP_ENDPOINT="$ENDPOINT" \
  --from-literal=LAST9_OTLP_BASIC_AUTH="$AUTH_VALUE" \
  --dry-run=client -o yaml | kubectl apply -f -
```

> **Auth header gotcha:** `LAST9_OTLP_BASIC_AUTH` is stored as the full `Basic <token>` string (the `Authorization=` key is stripped, not the `Basic ` scheme prefix). The OTel values file uses it verbatim as the `Authorization` header value — do not add another `Basic ` prefix in the config or you'll get persistent HTTP 401.

#### 11.5.4 Deploy dcgm-exporter

```bash
helm upgrade --install dcgm-exporter dcgm-exporter/dcgm-exporter \
  --namespace monitoring \
  --values deploy/helm/l9gpu/examples/dcgm-exporter-values.yaml
```

Verify pods are running (not OOMKilled):

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=dcgm-exporter
```

> **Memory gotcha:** 256Mi is not enough — dcgm-exporter OOMKills at startup. The values file uses 512Mi limit / 256Mi request. If OOMKilled again on a very busy node, increase to 768Mi.

Spot-check the metrics endpoint and confirm all GPUs are visible:

```bash
kubectl port-forward -n monitoring daemonset/dcgm-exporter 9401:9400 &
curl -s http://localhost:9401/metrics | grep 'DCGM_FI_PROF_SM_ACTIVE' | grep -o 'gpu="[^"]*"' | sort -u
pkill -f "port-forward.*9401"
```

**Expected on g4dn.12xlarge (4x T4):** `gpu="0"`, `gpu="1"`, `gpu="2"`, `gpu="3"` — one series per physical GPU.

**Expected on g4dn.xlarge (1x T4):** `gpu="0"` only.

> **Multi-GPU visibility:** `NVIDIA_VISIBLE_DEVICES=all` is already set in `dcgm-exporter-values.yaml`. Without it, the NVIDIA device plugin only injects one GPU (the allocated one) into the container, so DCGM enumerates GPU0 for every pod regardless of physical index — the same bug that affected `l9gpu-monitoring` on multi-GPU nodes.

#### 11.5.5 Deploy OTel collector for DCGM scraping

```bash
helm install otel-collector-dcgm open-telemetry/opentelemetry-collector \
  --namespace monitoring \
  --values deploy/helm/l9gpu/examples/eks-otelcol-dcgm.yaml
```

> **OTel Helm chart gotcha:** The chart merges your `config:` block with its own defaults (jaeger, zipkin, prometheus self-scraping on `:8888`). If you use `helm upgrade` after a failed install, the release may be stuck in `pending-install` state. Fix:
> ```bash
> kubectl delete secret sh.helm.release.v1.otel-collector-dcgm.v1 -n monitoring
> kubectl delete deployment -n monitoring -l app.kubernetes.io/name=opentelemetry-collector
> helm install otel-collector-dcgm ...
> ```

> **Port 8888 conflict gotcha:** The chart's default internal metrics port (8888) conflicts with other collectors. The values file remaps this to 8889. If the pod crashes with `listen tcp :8888: bind: address already in use`, patch the ConfigMap directly:
> ```bash
> # Edit the relay key — change address to 0.0.0.0:8889 under service.telemetry.metrics
> kubectl edit configmap otel-collector-dcgm-opentelemetry-collector -n monitoring
> kubectl rollout restart deployment/otel-collector-dcgm-opentelemetry-collector -n monitoring
> ```

Verify the single pod is Running and scraping:

```bash
# Confirm single Deployment pod (not multiple DaemonSet pods)
kubectl get pods -n monitoring -l app.kubernetes.io/name=opentelemetry-collector

kubectl logs -n monitoring -l app.kubernetes.io/name=opentelemetry-collector --tail=5 \
  | grep -E 'Scrape job added|Everything is ready|error'
```

**Expected:** exactly 1 pod Running.
```
Scrape job added  jobName=dcgm-exporter
Everything is ready. Begin running and processing data.
```

> **Why Deployment not DaemonSet:** A DaemonSet runs one OTel pod per node. With 2 nodes, 2 OTel pods each scrape both dcgm-exporter pods → every metric is ingested 4× instead of 2×. A single-replica Deployment with `kubernetes_sd_configs` (namespace-scoped pod discovery) scrapes every dcgm-exporter pod exactly once regardless of how many nodes are in the cluster.

#### 11.5.6 Verify metrics in Last9

After ~60 seconds, query Last9:

```
DCGM_FI_PROF_SM_ACTIVE{k8s_cluster_name="my-eks-multigpu"}
DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{k8s_cluster_name="my-eks-multigpu"}
DCGM_FI_PROF_DRAM_ACTIVE{k8s_cluster_name="my-eks-multigpu"}
```

The `05-eks-gpu-dcgm.json` Grafana dashboard uses these metrics. Import it and select the cluster to confirm data appears.

> **T4 profiling note:** On `g4dn` (T4 / Turing) nodes, `DCGM_FI_PROF_SM_ACTIVE`, `DCGM_FI_PROF_GR_ENGINE_ACTIVE`, and `DCGM_FI_PROF_DRAM_ACTIVE` show real values under load. `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE`, `DCGM_FI_PROF_PIPE_FP16_ACTIVE` etc. typically read `0` at idle and show small values only during matrix-heavy workloads. `DCGM_FI_PROF_NVLINK_*` is always `0` on T4 (no NVLink hardware).

---

## Scenario 12: vLLM Integration

**Goal:** Verify the `vllm_monitor` command scrapes a running vLLM server and emits throughput, latency, cache, and queue-depth metrics.

> **Instance:** `g5.xlarge` (A10G, 24 GB, ~$1.01/hr) is recommended. `g4dn.xlarge` (T4, 16 GB) also works — `Qwen/Qwen2.5-3B-Instruct` (~6 GB in float16) fits comfortably on both.

### 12.1 Install vLLM on EC2

```bash
# In the l9gpu venv (or a separate venv)
pip install vllm
```

> **Note:** vLLM installation pulls large CUDA-enabled wheels. On a fresh EC2 instance this can take 5–10 minutes.

### 12.2 Start vLLM server

```bash
# Works on g4dn.xlarge (T4, 16 GB) or larger
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-3B-Instruct \
  --port 8000 \
  --dtype float16 \
  --enforce-eager \
  --max-model-len 4096 \
  &

# Model weights (~6 GB) download on first run; wait until "Application startup complete"
sleep 120
curl -s http://localhost:8000/v1/models | python3 -m json.tool
```

> **On g4dn.xlarge (T4):** `--enforce-eager` and `--max-model-len 4096` are required.
> vLLM ≥0.16 uses torch.compile/CUDA graph JIT by default which crashes on T4 (compute 7.5).
> `--enforce-eager` disables JIT; `--max-model-len 4096` prevents KV cache OOM (default 32768 context needs ~7 GB on top of the 5.8 GB weights).

### 12.3 Generate traffic (so latency metrics are non-zero)

```bash
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"Qwen/Qwen2.5-3B-Instruct","prompt":"Hello, world!","max_tokens":20}' \
    > /dev/null
done
```

### 12.4 Run vllm_monitor — stdout, single shot

```bash
l9gpu vllm_monitor \
  --vllm-endpoint http://localhost:8000/metrics \
  --once \
  --sink stdout
```

**Expected output:** A single metrics block. Should include:
- `vllm.requests.running`, `vllm.requests.waiting`, `vllm.requests.swapped` (queue depths; likely 0 at idle)
- `vllm.cache.usage` with `cache.type=gpu` attribute (KV-cache fill fraction, 0.0–1.0)
- `vllm.request.latency` with `quantile=p50/p95/p99` attribute (seconds; non-zero after traffic)
- `vllm.ttft` with `quantile=p50/p95` attribute (time-to-first-token, seconds)
- `vllm.prompt.throughput`, `vllm.generation.throughput` — **will be `None` on the first `--once` call** because throughput is a rate computed from counter deltas; the first scrape has no previous baseline

> **Tip:** Run the command twice (with ~30 s between calls) or use continuous mode (`--push-interval 30` without `--once`) to see non-`None` throughput values.

**Report:** Paste the full output. Note which fields are None vs populated.

### 12.5 Run vllm_monitor — OTLP to Last9

```bash
# Credentials must be set from Scenario 2.1
l9gpu vllm_monitor \
  --vllm-endpoint http://localhost:8000/metrics \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --cluster my-ec2-gpu-cluster \
  --sink otel \
  --push-interval 30 &

# Generate traffic for 2 minutes, then stop
for i in {1..20}; do
  curl -s -X POST http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"Qwen/Qwen2.5-3B-Instruct","prompt":"Explain GPU monitoring.","max_tokens":50}' \
    > /dev/null
  sleep 5
done
kill %1
```

**Verify in Last9:** Check for metrics with resource attributes `k8s.cluster.name=my-ec2-gpu-cluster` and `vllm.model.name=Qwen/Qwen2.5-3B-Instruct`.

**Report:** Did metrics arrive? Was throughput (`prompt_tokens_per_sec`) non-zero on the second push? Any latency histogram issues?

---

## Scenario 13: NVIDIA NIM Integration (Optional)

**Goal:** Verify the `nim_monitor` command scrapes an NVIDIA NIM container and emits request, latency, cache, and queue metrics.

> **Prerequisites:** NVIDIA AI Enterprise license or NGC Early Access. An NGC API key is required to pull the NIM container image.
> **Skip this scenario** if you do not have NGC access — NIM is not freely available. The `nim_monitor` CLI can still be smoke-tested against any Prometheus endpoint returning `nvidia_nim_*` metrics.

### 13.1 Prerequisites

```bash
# Log in to NVIDIA NGC registry
docker login nvcr.io
# Username: $oauthtoken
# Password: <your-NGC-API-key>

export NGC_API_KEY="<your-ngc-api-key>"
```

### 13.2 Pull and start a NIM container

```bash
# Example: Llama 3 8B Instruct (requires g5.12xlarge or p4d for full performance)
# For a smaller footprint, use a smaller NIM model if available on your NGC account.
docker run -d \
  --gpus all \
  --name nim-test \
  -p 8000:8000 \
  -e NGC_API_KEY=${NGC_API_KEY} \
  nvcr.io/nim/meta/llama3-8b-instruct:latest
```

### 13.3 Wait for NIM to be ready

NIM downloads model weights on first start — this can take several minutes.

```bash
# Poll until the /v1/models endpoint returns 200
until curl -sf http://localhost:8000/v1/models > /dev/null; do
  echo "Waiting for NIM to be ready..."
  sleep 15
done
echo "NIM is ready."
```

### 13.4 Run nim_monitor — stdout, single shot

```bash
l9gpu nim_monitor \
  --nim-endpoint http://localhost:8000/metrics \
  --once \
  --sink stdout
```

**Expected output:** A single metrics block. Should include:
- `nim.requests.total` (cumulative request count)
- `nim.requests.failed` (cumulative failure count)
- `nim.queue.depth` (current queue depth)
- `nim.kv_cache.usage` (KV-cache fill fraction, 0.0–1.0)
- `nim.request.latency` with `quantile=p50` and `quantile=p99` attributes (seconds; non-zero after at least one request)
- `nim.batch.size` (average batch size, if NIM exposes `nvidia_nim_batch_size`)

### 13.5 Generate traffic and verify OTLP export

```bash
# Send a few requests to populate latency histograms
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"meta/llama3-8b-instruct","prompt":"Hello!","max_tokens":10}' \
    > /dev/null
done

# Credentials must be set from Scenario 2.1
l9gpu nim_monitor \
  --nim-endpoint http://localhost:8000/metrics \
  --model meta/llama3-8b-instruct \
  --cluster my-ec2-gpu-cluster \
  --sink otel \
  --once
```

**Verify in Last9:** Check for metrics with resource attributes `k8s.cluster.name=my-ec2-gpu-cluster` and `nim.model=meta/llama3-8b-instruct`.

**Report:** Did metrics arrive? Were latency percentiles non-zero? Was `kv_cache_usage` populated?

> **Note:** The exact set of `nvidia_nim_*` Prometheus metrics varies by NIM model and version. If some fields are None, the NIM container may not expose those counters — this is expected for some model types.

---

## Findings Template

After each scenario, fill in:

```
## Scenario X Results

Date/Time:
Instance type:
AMI:
l9gpu version (l9gpu --version):
NVIDIA driver (nvidia-smi | head -1):

### What worked:
-

### Errors / unexpected behavior:
-

### Missing metrics:
-

### Questions for improvement:
-

### Raw output snippet:
(paste first 50 lines of stdout output here)
```

---

## Cleanup

After all testing, avoid ongoing costs:

```bash
# Terminate EC2 instances
aws ec2 terminate-instances --instance-ids $INSTANCE_ID

# Delete EKS cluster
eksctl delete cluster --name my-gpu-lab --region $AWS_REGION

# Delete ParallelCluster
pcluster delete-cluster --cluster-name l9gpu-slurm-test

# Delete ECR images (optional)
aws ecr batch-delete-image \
  --repository-name l9gpu \
  --image-ids imageTag=test \
  --region $AWS_REGION

# Delete security group (after all instances are terminated)
aws ec2 delete-security-group --group-id $SG_ID
```

---

## Recommended Order of Execution

1. **Scenario 1** (stdout sanity check) — zero risk, validates NVML works
2. **Scenario 2** (OTLP to Last9) — validates end-to-end metric flow
3. **Scenario 3** (health_checks) — quick additional validation
4. **Scenario 5** (Docker on EC2) — validates container before pushing to EKS
5. **Scenario 6** (EKS DaemonSet) — main Kubernetes path
6. **Scenario 7** (OTel Collector proxy) — production auth architecture
7. **Scenario 4** (systemd) — optional, production bare-metal path
8. **Scenario 9** (different GPU types) — as budget permits
9. **Scenario 10** (multi-GPU) — as budget permits
10. **Scenario 8** (ParallelCluster/Slurm) — if HPC testing is in scope
11. **Scenario 11** (DCGM profiling) — on any GPU instance where dcgm-exporter Docker image is available; g5/p4d for full profiling metric set
12. **Scenario 12** (vLLM) — `g5.xlarge` recommended; `g4dn.xlarge` (T4) also works — `Qwen/Qwen2.5-3B-Instruct` (~6 GB float16) fits on both
13. **Scenario 13** (NVIDIA NIM) — optional; requires NGC API key and NVIDIA AI Enterprise access
