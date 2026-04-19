// Copyright (c) Last9, Inc.
// All rights reserved.
package k8shelper

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func boolPtr(b bool) *bool { return &b }

func TestResolveOwnerRefs_RayCluster(t *testing.T) {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "ray-worker-gpu-abc123",
			Namespace: "default",
			OwnerReferences: []metav1.OwnerReference{
				{
					Kind:       "RayCluster",
					Name:       "my-ray-cluster",
					Controller: boolPtr(true),
				},
			},
		},
	}

	// RayCluster is a CRD — no API call needed, so nil client is safe.
	jobName, stsName, deployName, ownerKind, ownerName := resolveOwnerRefs(context.Background(), nil, pod)

	if jobName != "" {
		t.Errorf("expected empty jobName, got %q", jobName)
	}
	if stsName != "" {
		t.Errorf("expected empty statefulSetName, got %q", stsName)
	}
	if deployName != "" {
		t.Errorf("expected empty deploymentName, got %q", deployName)
	}
	if ownerKind != "RayCluster" {
		t.Errorf("expected ownerKind=RayCluster, got %q", ownerKind)
	}
	if ownerName != "my-ray-cluster" {
		t.Errorf("expected ownerName=my-ray-cluster, got %q", ownerName)
	}
}

func TestResolveOwnerRefs_StandardJob(t *testing.T) {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "training-job-xyz-pod",
			Namespace: "ml",
			OwnerReferences: []metav1.OwnerReference{
				{
					Kind:       "Job",
					Name:       "training-job-xyz",
					Controller: boolPtr(true),
				},
			},
		},
	}

	// Job case doesn't make API calls, nil client is safe.
	jobName, stsName, deployName, ownerKind, ownerName := resolveOwnerRefs(context.Background(), nil, pod)

	if jobName != "training-job-xyz" {
		t.Errorf("expected jobName=training-job-xyz, got %q", jobName)
	}
	if stsName != "" {
		t.Errorf("expected empty statefulSetName, got %q", stsName)
	}
	if deployName != "" {
		t.Errorf("expected empty deploymentName, got %q", deployName)
	}
	if ownerKind != "" {
		t.Errorf("expected empty ownerKind, got %q", ownerKind)
	}
	if ownerName != "" {
		t.Errorf("expected empty ownerName, got %q", ownerName)
	}
}

func TestResolveOwnerRefs_NoController(t *testing.T) {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "standalone-pod",
			Namespace: "default",
		},
	}

	jobName, stsName, deployName, ownerKind, ownerName := resolveOwnerRefs(context.Background(), nil, pod)

	if jobName != "" || stsName != "" || deployName != "" || ownerKind != "" || ownerName != "" {
		t.Errorf("expected all empty, got job=%q sts=%q deploy=%q kind=%q name=%q",
			jobName, stsName, deployName, ownerKind, ownerName)
	}
}

func TestDefaultLabelAllowList_IncludesRayLabels(t *testing.T) {
	rayLabels := []string{
		"ray.io/cluster",
		"ray.io/node-type",
		"ray.io/group",
		"ray.io/is-ray-node",
	}
	for _, label := range rayLabels {
		if !defaultLabelAllowList[label] {
			t.Errorf("expected %q in defaultLabelAllowList", label)
		}
	}
}

func TestFilterLabels_RayPod(t *testing.T) {
	labels := map[string]string{
		"ray.io/cluster":   "my-cluster",
		"ray.io/node-type": "worker",
		"ray.io/group":     "gpu-group",
		"noise-label":      "should-be-dropped",
		"app":              "ray",
	}

	filtered := filterLabels(labels, defaultLabelAllowList)

	expected := map[string]string{
		"ray.io/cluster":   "my-cluster",
		"ray.io/node-type": "worker",
		"ray.io/group":     "gpu-group",
		"app":              "ray",
	}

	if len(filtered) != len(expected) {
		t.Fatalf("expected %d labels, got %d: %v", len(expected), len(filtered), filtered)
	}
	for k, v := range expected {
		if filtered[k] != v {
			t.Errorf("expected filtered[%q]=%q, got %q", k, v, filtered[k])
		}
	}
	if _, ok := filtered["noise-label"]; ok {
		t.Error("noise-label should have been filtered out")
	}
}

func TestGetGPUData_WithCustomOwner(t *testing.T) {
	gpu2k8s := map[string]K8sMetadata{
		"0": {
			PodName:         "ray-worker-0",
			Namespace:       "default",
			NodeName:        "gpu-node-1",
			ContainerName:   "ray-worker",
			CustomOwnerKind: "RayCluster",
			CustomOwnerName: "my-ray-cluster",
		},
		"1": {
			PodName:         "ray-worker-0",
			Namespace:       "default",
			NodeName:        "gpu-node-1",
			ContainerName:   "ray-worker",
			CustomOwnerKind: "RayCluster",
			CustomOwnerName: "my-ray-cluster",
		},
	}

	result := GetGPUData(gpu2k8s)

	if len(result.CustomOwnerKind) != 1 {
		t.Fatalf("expected 1 CustomOwnerKind entry (deduped), got %d", len(result.CustomOwnerKind))
	}
	if result.CustomOwnerKind[0] != "RayCluster" {
		t.Errorf("expected CustomOwnerKind=RayCluster, got %q", result.CustomOwnerKind[0])
	}
	if result.CustomOwnerName[0] != "my-ray-cluster" {
		t.Errorf("expected CustomOwnerName=my-ray-cluster, got %q", result.CustomOwnerName[0])
	}
}

func TestGetGPUData_MixedOwners(t *testing.T) {
	gpu2k8s := map[string]K8sMetadata{
		"0": {
			PodName:        "deploy-pod-abc",
			Namespace:      "ml",
			NodeName:       "gpu-node-1",
			ContainerName:  "trainer",
			DeploymentName: "my-deployment",
		},
		"1": {
			PodName:         "ray-worker-xyz",
			Namespace:       "ml",
			NodeName:        "gpu-node-1",
			ContainerName:   "ray-worker",
			CustomOwnerKind: "RayCluster",
			CustomOwnerName: "my-ray-cluster",
		},
	}

	result := GetGPUData(gpu2k8s)

	if len(result.DeploymentName) != 1 {
		t.Errorf("expected 1 DeploymentName, got %d", len(result.DeploymentName))
	}
	if len(result.CustomOwnerKind) != 1 {
		t.Errorf("expected 1 CustomOwnerKind, got %d", len(result.CustomOwnerKind))
	}
}
