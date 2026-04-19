#!/bin/bash
# l9gpu Demo — full GPU + LLM observability stack
# Run 30 minutes before demo to allow GPU nodes to come up.
#
# Deploys: EKS cluster, NVIDIA device plugin, 4 inference engines
# (vLLM, SGLang, TGI, Triton), 7 l9gpu monitors (NVML, DCGM, vLLM,
# SGLang, TGI, Triton, fleet-health, cost), OTel collector, and
# a load generator.
set -e

REGION=us-west-2
CLUSTER=l9gpu-demo-v2

echo "=== Step 1: Creating EKS cluster ($CLUSTER in $REGION) ==="
echo "This takes ~15 minutes for GPU node groups..."
eksctl create cluster -f deploy/demo/eks-cluster.yaml

echo "=== Step 2: Installing NVIDIA device plugin ==="
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.0/deployments/static/nvidia-device-plugin.yml

echo "=== Step 3: Deploying full demo stack ==="
kubectl apply -f deploy/demo/00-namespace.yaml
sleep 2
kubectl apply -f deploy/demo/03-inference-engines.yaml
kubectl apply -f deploy/demo/04-l9gpu-monitors.yaml

echo "=== Step 4: Waiting for inference engines to start ==="
echo "(This may take 3-5 min for model downloads on first run)"
kubectl -n $CLUSTER wait --for=condition=available deployment/vllm-llama --timeout=300s || echo "vLLM still starting..."
kubectl -n $CLUSTER wait --for=condition=available deployment/sglang-llama --timeout=300s || echo "SGLang still starting..."
kubectl -n $CLUSTER wait --for=condition=available deployment/tgi-llama --timeout=300s || echo "TGI still starting..."
kubectl -n $CLUSTER wait --for=condition=available deployment/triton-llama --timeout=300s || echo "Triton still starting..."

echo "=== Step 5: Checking pod status ==="
kubectl -n $CLUSTER get pods -o wide

echo ""
echo "=== DEMO READY ==="
echo "Inference engines: vLLM, SGLang, TGI, Triton"
echo "Monitors: NVML, DCGM, vLLM, SGLang, TGI, Triton, fleet-health, cost"
echo "Metrics flowing to Last9. Import dashboards from dashboards/grafana/"
echo ""
echo "To generate load:"
echo "  kubectl apply -f deploy/demo/05-load-generator.yaml  # if not already running"
echo ""
echo "To tear down:"
echo "  eksctl delete cluster --name $CLUSTER --region $REGION"
