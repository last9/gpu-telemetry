// Copyright (c) Last9, Inc.
// All rights reserved.
//
// Package k8shelper maps GPU ordinal indices to Kubernetes pod metadata by
// querying the K8s API for pods scheduled on the local node that have
// requested GPU resources (nvidia.com/gpu or amd.com/gpu).
//
// Usage:
//
//	cfg := &k8shelper.Config{NodeName: "gpu-node-01", CacheDuration: 60}
//	gpu2k8s, err := k8shelper.GetGPU2K8s(cfg)
//	if err != nil { ... }
//	if meta, ok := gpu2k8s["0"]; ok {
//	    fmt.Println(meta.PodName, meta.Namespace)
//	}
package k8shelper

import (
	"context"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// K8sMetadata holds Kubernetes workload metadata for a single GPU.
type K8sMetadata struct {
	PodName         string
	Namespace       string
	NodeName        string
	ContainerName   string
	Labels          map[string]string
	JobName         string
	StatefulSetName string
	DeploymentName  string
	// Generic CRD owner (RayCluster, Workflow, etc.) from pod owner references.
	CustomOwnerKind string
	CustomOwnerName string
	// Cloud topology from node labels (topology.kubernetes.io/zone and region).
	// Same value for all GPUs on the same node.
	CloudZone   string
	CloudRegion string
}

// GPU resource request annotation keys supported by common device plugins.
var gpuResourceKeys = []string{
	"nvidia.com/gpu",
	"amd.com/gpu",
	"habana.ai/gaudi",
	"habana.ai/gaudi2",
	"habana.ai/gaudi3",
}

// defaultLabelAllowList is the set of pod label keys propagated when no
// explicit allow-list is configured. These are well-known labels that provide
// useful workload context without causing cardinality explosion.
var defaultLabelAllowList = map[string]bool{
	"app":                          true,
	"app.kubernetes.io/name":       true,
	"app.kubernetes.io/instance":   true,
	"app.kubernetes.io/version":    true,
	"app.kubernetes.io/component":  true,
	"app.kubernetes.io/part-of":    true,
	"app.kubernetes.io/managed-by": true,
	"ray.io/cluster":               true,
	"ray.io/node-type":             true,
	"ray.io/group":                 true,
	"ray.io/is-ray-node":           true,
}

// cache holds the last fetched GPU-to-K8s mapping along with its expiry time.
type cache struct {
	mu        sync.Mutex
	data      map[string]K8sMetadata
	expiresAt time.Time
}

var globalCache = &cache{}

// GetGPU2K8s returns a map of GPU ordinal (as string) → K8sMetadata for pods
// running on the configured node.  Results are cached for cfg.CacheDuration
// seconds to reduce API server load.
func GetGPU2K8s(cfg *Config) (map[string]K8sMetadata, error) {
	globalCache.mu.Lock()
	defer globalCache.mu.Unlock()

	if time.Now().Before(globalCache.expiresAt) && globalCache.data != nil {
		return globalCache.data, nil
	}

	nodeName := cfg.NodeName
	if nodeName == "" {
		// Fall back to the MY_NODE_NAME env var injected by the Helm DaemonSet.
		nodeName = os.Getenv("MY_NODE_NAME")
	}
	if nodeName == "" {
		return nil, fmt.Errorf("k8shelper: node name not configured and MY_NODE_NAME env var not set")
	}

	client, err := newClient(cfg.KubeconfigPath)
	if err != nil {
		return nil, fmt.Errorf("k8shelper: failed to create k8s client: %w", err)
	}

	result, err := buildGPU2K8s(client, nodeName, cfg.LabelAllowList)
	if err != nil {
		return nil, err
	}

	cacheDuration := cfg.CacheDuration
	if cacheDuration <= 0 {
		cacheDuration = 60
	}
	globalCache.data = result
	globalCache.expiresAt = time.Now().Add(time.Duration(cacheDuration) * time.Second)
	return result, nil
}

// newClient creates a Kubernetes clientset.  Uses in-cluster config when
// kubeconfigPath is empty (the normal case for a DaemonSet pod).
func newClient(kubeconfigPath string) (*kubernetes.Clientset, error) {
	var cfg *rest.Config
	var err error

	if kubeconfigPath != "" {
		cfg, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	} else {
		cfg, err = rest.InClusterConfig()
	}
	if err != nil {
		return nil, err
	}
	return kubernetes.NewForConfig(cfg)
}

// buildLabelFilter returns a set of allowed label keys. If the configured
// allow-list is empty, the default well-known labels are used.
func buildLabelFilter(allowList []string) map[string]bool {
	if len(allowList) == 0 {
		return defaultLabelAllowList
	}
	m := make(map[string]bool, len(allowList))
	for _, k := range allowList {
		m[k] = true
	}
	return m
}

// filterLabels returns a copy of labels containing only allowed keys.
func filterLabels(labels map[string]string, allowed map[string]bool) map[string]string {
	if len(labels) == 0 {
		return nil
	}
	filtered := make(map[string]string)
	for k, v := range labels {
		if allowed[k] {
			filtered[k] = v
		}
	}
	if len(filtered) == 0 {
		return nil
	}
	return filtered
}

// resolveOwnerRefs walks a pod's owner reference chain to find the controlling
// Job, StatefulSet, or Deployment (via ReplicaSet). Errors are logged and
// silently degraded to empty strings so they never block metric collection.
func resolveOwnerRefs(ctx context.Context, client *kubernetes.Clientset, pod *corev1.Pod) (jobName, statefulSetName, deploymentName, customOwnerKind, customOwnerName string) {
	for _, ref := range pod.OwnerReferences {
		if ref.Controller == nil || !*ref.Controller {
			continue
		}
		switch ref.Kind {
		case "Job":
			jobName = ref.Name
		case "StatefulSet":
			statefulSetName = ref.Name
		case "ReplicaSet":
			rs, err := client.AppsV1().ReplicaSets(pod.Namespace).Get(ctx, ref.Name, metav1.GetOptions{})
			if err != nil {
				log.Printf("k8shelper: failed to get ReplicaSet %s/%s: %v", pod.Namespace, ref.Name, err)
				continue
			}
			for _, rsRef := range rs.OwnerReferences {
				if rsRef.Controller != nil && *rsRef.Controller && rsRef.Kind == "Deployment" {
					deploymentName = rsRef.Name
					break
				}
			}
		default:
			// Generic CRD owner (RayCluster, Workflow, etc.).
			// No API call needed — Kind and Name come from the pod's owner ref.
			customOwnerKind = ref.Kind
			customOwnerName = ref.Name
		}
	}
	return
}

// buildGPU2K8s queries the K8s API for pods on nodeName and builds the
// GPU ordinal → K8sMetadata mapping.
func buildGPU2K8s(client *kubernetes.Clientset, nodeName string, labelAllowList []string) (map[string]K8sMetadata, error) {
	ctx := context.Background()
	pods, err := client.CoreV1().Pods("").List(ctx, metav1.ListOptions{
		FieldSelector: fmt.Sprintf("spec.nodeName=%s,status.phase=Running", nodeName),
	})
	if err != nil {
		return nil, fmt.Errorf("k8shelper: failed to list pods on node %s: %w", nodeName, err)
	}

	// Fetch node labels for cloud topology attributes (best-effort; degraded gracefully).
	cloudZone, cloudRegion := "", ""
	node, nodeErr := client.CoreV1().Nodes().Get(ctx, nodeName, metav1.GetOptions{})
	if nodeErr != nil {
		log.Printf("k8shelper: failed to get node %s (cloud labels will be missing): %v", nodeName, nodeErr)
	} else {
		cloudZone = node.Labels["topology.kubernetes.io/zone"]
		cloudRegion = node.Labels["topology.kubernetes.io/region"]
	}

	allowedLabels := buildLabelFilter(labelAllowList)
	result := make(map[string]K8sMetadata)
	gpuOrdinal := 0

	for i := range pods.Items {
		pod := &pods.Items[i]
		jobName, statefulSetName, deploymentName, customOwnerKind, customOwnerName := resolveOwnerRefs(ctx, client, pod)
		for _, container := range pod.Spec.Containers {
			gpuCount := gpuRequestCount(container)
			if gpuCount == 0 {
				continue
			}
			meta := K8sMetadata{
				PodName:         pod.Name,
				Namespace:       pod.Namespace,
				NodeName:        nodeName,
				ContainerName:   container.Name,
				Labels:          filterLabels(pod.Labels, allowedLabels),
				JobName:         jobName,
				StatefulSetName: statefulSetName,
				DeploymentName:  deploymentName,
				CustomOwnerKind: customOwnerKind,
				CustomOwnerName: customOwnerName,
				CloudZone:       cloudZone,
				CloudRegion:     cloudRegion,
			}
			for j := 0; j < gpuCount; j++ {
				result[strconv.Itoa(gpuOrdinal)] = meta
				gpuOrdinal++
			}
		}
	}

	log.Printf("k8shelper: mapped %d GPU(s) on node %s", gpuOrdinal, nodeName)
	return result, nil
}

// gpuRequestCount returns the total number of GPU units requested by a
// container across all supported GPU resource types.
func gpuRequestCount(container corev1.Container) int {
	if container.Resources.Requests == nil {
		return 0
	}
	total := 0
	for _, key := range gpuResourceKeys {
		if qty, ok := container.Resources.Requests[corev1.ResourceName(key)]; ok {
			total += int(qty.Value())
		}
	}
	return total
}

// GetGPUData returns a K8sMetadataList aggregating metadata from all mapped GPUs.
// This mirrors shelper.GetGPUData for the slurmprocessor/k8sprocessor interface.
func GetGPUData(gpu2k8s map[string]K8sMetadata) K8sMetadataList {
	result := K8sMetadataList{}
	seen := make(map[string]bool)
	for _, meta := range gpu2k8s {
		key := meta.Namespace + "/" + meta.PodName
		if !seen[key] {
			seen[key] = true
			result.PodName = append(result.PodName, meta.PodName)
			result.Namespace = append(result.Namespace, meta.Namespace)
			result.NodeName = append(result.NodeName, meta.NodeName)
			result.ContainerName = append(result.ContainerName, meta.ContainerName)
			if meta.JobName != "" {
				result.JobName = append(result.JobName, meta.JobName)
			}
			if meta.StatefulSetName != "" {
				result.StatefulSetName = append(result.StatefulSetName, meta.StatefulSetName)
			}
			if meta.DeploymentName != "" {
				result.DeploymentName = append(result.DeploymentName, meta.DeploymentName)
			}
			if meta.CustomOwnerKind != "" {
				result.CustomOwnerKind = append(result.CustomOwnerKind, meta.CustomOwnerKind)
				result.CustomOwnerName = append(result.CustomOwnerName, meta.CustomOwnerName)
			}
		}
	}
	return result
}

// K8sMetadataList holds slice-valued metadata for multi-GPU nodes.
type K8sMetadataList struct {
	PodName         []string
	Namespace       []string
	NodeName        []string
	ContainerName   []string
	JobName         []string
	StatefulSetName []string
	DeploymentName  []string
	CustomOwnerKind []string
	CustomOwnerName []string
}

// LookupByGPUEnvVar attempts to derive the GPU-to-pod mapping from
// NVIDIA_VISIBLE_DEVICES or ROCR_VISIBLE_DEVICES env vars in pod specs.
// This is a best-effort fallback when device plugin ordinal assignment order
// is unknown.
func LookupByGPUEnvVar(podSpec corev1.PodSpec) string {
	for _, container := range podSpec.Containers {
		for _, env := range container.Env {
			if env.Name == "NVIDIA_VISIBLE_DEVICES" || env.Name == "ROCR_VISIBLE_DEVICES" {
				return strings.TrimSpace(env.Value)
			}
		}
	}
	return ""
}
