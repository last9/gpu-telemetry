// Copyright (c) Last9, Inc.
// All rights reserved.
package k8sprocessor

import (
	"context"
	"log"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"

	k8shelper "github.com/last9/gpu-telemetry/k8shelper"
)

// OTel semantic convention attribute keys for Kubernetes workload metadata.
const (
	K8sPodName         = "k8s.pod.name"
	K8sNamespace       = "k8s.namespace.name"
	K8sNodeName        = "k8s.node.name"
	K8sContainerName   = "k8s.container.name"
	K8sJobName         = "k8s.job.name"
	K8sStatefulSetName = "k8s.statefulset.name"
	K8sDeploymentName  = "k8s.deployment.name"
	// Generic CRD owner attributes (e.g., RayCluster, Workflow).
	K8sOwnerKind = "k8s.owner.kind"
	K8sOwnerName = "k8s.owner.name"
	// Cloud topology keys (OTel semantic convention).
	CloudAvailabilityZone = "cloud.availability_zone"
	CloudRegionAttr       = "cloud.region"
	gpuUUID               = "gpu.uuid"
	gpuIndex              = "gpu.index"
)

// K8sProcessorBase contains common fields and methods shared by all k8s processors.
type K8sProcessorBase struct {
	Config *k8shelper.Config
}

// NewK8sProcessorBase creates a new K8sProcessorBase from the component config.
func NewK8sProcessorBase(cfg component.Config) K8sProcessorBase {
	return K8sProcessorBase{
		Config: cfg.(*k8shelper.Config),
	}
}

// Capabilities returns the processor capabilities (mutates data).
func (pb *K8sProcessorBase) Capabilities() consumer.Capabilities {
	return consumer.Capabilities{MutatesData: true}
}

// Start is called when the processor starts.
func (pb *K8sProcessorBase) Start(_ context.Context, _ component.Host) error {
	log.Println("Starting k8s processor")
	return nil
}

// Shutdown is called when the processor shuts down.
func (pb *K8sProcessorBase) Shutdown(context.Context) error {
	log.Println("Shutting down k8s processor")
	return nil
}

// AddK8sMetadata enriches an attribute map with K8s pod/namespace/node metadata.
func (pb *K8sProcessorBase) AddK8sMetadata(attributes pcommon.Map, meta k8shelper.K8sMetadata) {
	attributes.PutStr(K8sPodName, meta.PodName)
	attributes.PutStr(K8sNamespace, meta.Namespace)
	attributes.PutStr(K8sNodeName, meta.NodeName)
	attributes.PutStr(K8sContainerName, meta.ContainerName)
	if meta.JobName != "" {
		attributes.PutStr(K8sJobName, meta.JobName)
	}
	if meta.StatefulSetName != "" {
		attributes.PutStr(K8sStatefulSetName, meta.StatefulSetName)
	}
	if meta.DeploymentName != "" {
		attributes.PutStr(K8sDeploymentName, meta.DeploymentName)
	}
	if meta.CustomOwnerKind != "" {
		attributes.PutStr(K8sOwnerKind, meta.CustomOwnerKind)
		attributes.PutStr(K8sOwnerName, meta.CustomOwnerName)
	}

	// Propagate well-known pod labels (app, component, etc.)
	for k, v := range meta.Labels {
		attributes.PutStr("k8s.pod.label."+k, v)
	}
}

// AddK8sMetadataSlice enriches an attribute map with slice-valued K8s metadata
// for host-level metrics that aggregate across all GPUs on the node.
func (pb *K8sProcessorBase) AddK8sMetadataSlice(attributes pcommon.Map, list k8shelper.K8sMetadataList) {
	putStrSlice(attributes, K8sPodName, list.PodName)
	putStrSlice(attributes, K8sNamespace, list.Namespace)
	putStrSlice(attributes, K8sNodeName, list.NodeName)
	putStrSlice(attributes, K8sContainerName, list.ContainerName)
	putStrSlice(attributes, K8sJobName, list.JobName)
	putStrSlice(attributes, K8sStatefulSetName, list.StatefulSetName)
	putStrSlice(attributes, K8sDeploymentName, list.DeploymentName)
	putStrSlice(attributes, K8sOwnerKind, list.CustomOwnerKind)
	putStrSlice(attributes, K8sOwnerName, list.CustomOwnerName)
}

// extractCloudInfo returns the cloud zone and region from any K8sMetadata in the
// map. All GPUs on a node share the same topology labels, so the first entry suffices.
func extractCloudInfo(gpu2k8s map[string]k8shelper.K8sMetadata) (zone, region string) {
	for _, meta := range gpu2k8s {
		return meta.CloudZone, meta.CloudRegion
	}
	return "", ""
}

// AddCloudAttrs injects cloud topology resource attributes into attrs.
// Only non-empty values are written to avoid polluting metrics from non-cloud nodes.
func (pb *K8sProcessorBase) AddCloudAttrs(attrs pcommon.Map, zone, region string) {
	if zone != "" {
		attrs.PutStr(CloudAvailabilityZone, zone)
	}
	if region != "" {
		attrs.PutStr(CloudRegionAttr, region)
	}
}

func putStrSlice(attributes pcommon.Map, key string, values []string) {
	if len(values) == 0 {
		return
	}
	es := attributes.PutEmptySlice(key)
	for _, v := range values {
		es.AppendEmpty().SetStr(v)
	}
}
