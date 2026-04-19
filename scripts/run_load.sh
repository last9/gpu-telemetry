#!/usr/bin/env bash
# run_load.sh — Drive 15 min of GPU + vLLM load to populate all metrics in Last9.
#
# Covers:
#   gpu.utilization, gpu.memory.used, gpu.power.draw, gpu.temperature,
#   gpu.pcie.throughput, gpu.clock.frequency  (l9gpu NVML — both nodes)
#   DCGM_FI_PROF_SM_ACTIVE, DCGM_FI_PROF_DRAM_ACTIVE, DCGM_FI_DEV_GPU_UTIL
#   DCGM_FI_DEV_POWER_USAGE  (dcgm-exporter — gpu-multi node, pod-attributed)
#   vllm.prompt.throughput, vllm.generation.throughput, vllm.request.latency,
#   vllm.ttft, vllm.cache.usage, vllm.requests.running/waiting  (vllm_monitor)
#
# Usage:
#   ./scripts/run_load.sh                         # 15 min, concurrency 3
#   DURATION=300 CONCURRENCY=2 ./scripts/run_load.sh
#
# Prerequisites:
#   kubectl port-forward svc/vllm-svc 8000:8000 -n monitoring  (or run this script)
#   pip install aiohttp

set -euo pipefail

DURATION="${DURATION:-900}"
CONCURRENCY="${CONCURRENCY:-3}"
ENDPOINT="${ENDPOINT:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="monitoring"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[load]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC}   $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[err]${NC}  $*" >&2; exit 1; }

cleanup() {
  echo ""
  log "Cleaning up..."
  kubectl delete job gpu-stress -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
  [[ -n "${PF_PID:-}" ]] && kill "$PF_PID" 2>/dev/null || true
  ok "Done."
}
trap cleanup EXIT INT TERM

# ── 1. Check tools ────────────────────────────────────────────────────────────
for cmd in kubectl python3; do
  command -v "$cmd" &>/dev/null || die "$cmd not found"
done
python3 -c "import aiohttp" 2>/dev/null || die "Missing: pip3 install aiohttp"

# ── 2. Kubeconfig check ───────────────────────────────────────────────────────
kubectl get nodes -o name &>/dev/null || die "kubectl cannot reach the cluster — run: aws eks update-kubeconfig --name l9gpu-test --region ap-south-1"

log "Nodes:"
kubectl get nodes -o custom-columns='NAME:.metadata.name,TYPE:.metadata.labels.node\.kubernetes\.io/instance-type,STATUS:.status.conditions[-1].type' 2>/dev/null || true
echo ""

# ── 3. Port-forward ───────────────────────────────────────────────────────────
if curl -s --max-time 2 "$ENDPOINT/v1/models" &>/dev/null; then
  ok "Port-forward already active on $ENDPOINT"
else
  log "Starting port-forward to vllm-svc:8000..."
  kubectl port-forward svc/vllm-svc 8000:8000 -n "$NAMESPACE" &>/dev/null &
  PF_PID=$!
  sleep 3
  curl -s --max-time 5 "$ENDPOINT/v1/models" &>/dev/null || die "vLLM not reachable at $ENDPOINT — is the vllm pod running?"
  ok "Port-forward established (pid=$PF_PID)"
fi

MODEL=$(curl -s "$ENDPOINT/v1/models" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")
ok "Model: $MODEL"

# ── 4. GPU stress job ─────────────────────────────────────────────────────────
log "Applying GPU stress job (3 pods × 1 GPU on gpu-multi, ${DURATION}s)..."
# Patch duration into a temp copy
TMPJOB="$(mktemp /tmp/gpu_stress_XXXX.yaml)"
sed "s/value: \"900\"/value: \"${DURATION}\"/" "$SCRIPT_DIR/gpu_stress_job.yaml" > "$TMPJOB"

kubectl delete job gpu-stress -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
kubectl apply -f "$TMPJOB" -n "$NAMESPACE"
rm -f "$TMPJOB"

log "Waiting for stress pods to start..."
for i in $(seq 1 30); do
  RUNNING=$(kubectl get pods -n "$NAMESPACE" -l app=gpu-stress --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
  [[ "$RUNNING" -ge 1 ]] && break
  sleep 2
done
ok "Stress pods running: $(kubectl get pods -n "$NAMESPACE" -l app=gpu-stress --no-headers 2>/dev/null | awk '{print $3}' | sort | uniq -c | tr '\n' ' ')"

# ── 5. vLLM load ─────────────────────────────────────────────────────────────
echo ""
log "Starting vLLM load: concurrency=${CONCURRENCY}, duration=${DURATION}s, endpoint=${ENDPOINT}"
log "Metrics populating in Last9 (k8s_cluster_name=my-eks-multigpu):"
log "  GPU:   gpu.utilization · gpu.power.draw · gpu.temperature · gpu.pcie.throughput"
log "  DCGM:  DCGM_FI_PROF_SM_ACTIVE · DCGM_FI_PROF_DRAM_ACTIVE · DCGM_FI_DEV_POWER_USAGE"
log "  vLLM:  vllm.prompt.throughput · vllm.request.latency · vllm.cache.usage · vllm.requests.running"
echo ""

python3 "$SCRIPT_DIR/vllm_load.py" \
  --endpoint "$ENDPOINT" \
  --concurrency "$CONCURRENCY" \
  --duration "$DURATION" \
  --max-tokens 200

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo ""
ok "Load run complete (${DURATION}s). Stress job may still be running."
log "Check Last9 with filter: k8s_cluster_name = my-eks-multigpu"
log "Stress pods status:"
kubectl get pods -n "$NAMESPACE" -l app=gpu-stress 2>/dev/null || true
