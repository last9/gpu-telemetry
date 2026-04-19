// Copyright (c) Last9, Inc.
// All rights reserved.
package k8shelper

// Config holds configuration for the k8shelper library.
type Config struct {
	// NodeName is the Kubernetes node name to query GPU-to-pod mappings for.
	// Usually injected via the Downward API (spec.nodeName).
	NodeName string `mapstructure:"node_name"`

	// KubeconfigPath is the path to a kubeconfig file.
	// Leave empty to use in-cluster config (default for DaemonSet pods).
	KubeconfigPath string `mapstructure:"kubeconfig_path"`

	// CacheDuration is the number of seconds to cache pod-to-GPU mappings.
	// Pods are re-queried after this interval to pick up workload changes.
	CacheDuration int `mapstructure:"cache_duration"`

	// LabelAllowList is the set of pod label keys to propagate as attributes.
	// If empty, a default set of well-known labels is used to prevent
	// unbounded cardinality from labels like pod-template-hash.
	LabelAllowList []string `mapstructure:"label_allow_list"`
}
